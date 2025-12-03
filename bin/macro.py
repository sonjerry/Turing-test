# macro.py

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import cv2
import time
import json
from datetime import datetime  # ← OS 시간용

import pyautogui
import easyocr
import numpy as np

# ---------------------
# 설정 파일 로드
# ---------------------

# macro.py가 있는 폴더 기준으로 config 경로 고정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "macro_config.json")

DEFAULT_CONFIG = {
    "TRIGGER_REGION": [870, 120, 120, 40],  # 현재는 사용하지 않지만, 호환 위해 남겨둠
    "REGIONS": {
        "title":   [141, 132, 260, 18],
        "preview": [141, 150, 714, 25],
        # "time" 은 화면에서 OCR 안 하고 OS 시간으로 채울 거라 좌표는 의미 없음
        "time":    [876, 130, 65, 21],
    }
}


def load_config(path: str = CONFIG_PATH):
    """
    JSON 설정 파일에서 좌표를 읽어옴.
    - 파일이 없으면 DEFAULT_CONFIG로 파일을 새로 만들고, 기본값 사용
    - 파일이 깨졌으면 에러 출력 후 기본값 사용
    """
    # 얕은 복사 + REGIONS는 한 번 더 복사
    config = DEFAULT_CONFIG.copy()
    config["REGIONS"] = DEFAULT_CONFIG["REGIONS"].copy()

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)

            if "TRIGGER_REGION" in user_cfg:
                config["TRIGGER_REGION"] = user_cfg["TRIGGER_REGION"]

            if "REGIONS" in user_cfg and isinstance(user_cfg["REGIONS"], dict):
                # 기본 REGIONS 위에 덮어쓰기
                for k, v in user_cfg["REGIONS"].items():
                    config["REGIONS"][k] = v

            print("[config] 로드됨:", path)
        except Exception as e:
            print(f"[config] {path} 로드 실패, 기본값 사용:", e)
    else:
        # 파일이 없으면 기본값으로 새로 생성
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            print(f"[config] {path} 기본 설정 파일 생성됨. 좌표를 편집해서 사용하세요.")
        except Exception as e:
            print(f"[config] {path} 기본 설정 파일 생성 실패:", e)

    print("[config] TRIGGER_REGION:", config["TRIGGER_REGION"])
    print("[config] REGIONS:", config["REGIONS"])
    return config


_cfg = load_config()

# tuple로 변환해서 사용
TRIGGER_REGION = tuple(_cfg["TRIGGER_REGION"])  # 현재는 사용 안 함
REGIONS = {k: tuple(v) for k, v in _cfg["REGIONS"].items()}

# 실제 캡쳐(ocr/트리거)에는 테두리 안쪽만 쓰기 위한 마진
CAPTURE_MARGIN = 12

CAPTURE_REGIONS = {}

for key, (left, top, width, height) in REGIONS.items():
    
    if key == "time":
        continue

    cl = left + CAPTURE_MARGIN
    ct = top + CAPTURE_MARGIN
    cw = max(1, width - CAPTURE_MARGIN * 2)
    ch = max(1, height - CAPTURE_MARGIN * 2)

    CAPTURE_REGIONS[key] = (cl, ct, cw, ch)




# ---------------------
# EasyOCR 리더 초기화
# ---------------------
reader = easyocr.Reader(['ko', 'en'], gpu=True)

# ---------------------
# 매크로 설정 영역
# ---------------------

# 트리거 감지 쿨다운 (초)
TRIGGER_COOLDOWN_SEC = 0.5


# ---------------------
# 시간 포맷 함수 (OS 시간 사용)
# ---------------------

def format_korean_time(dt=None):
    """
    현재 OS 시간을 '오전 11:59' 형태의 문자열로 반환
    """
    if dt is None:
        dt = datetime.now()

    hour = dt.hour
    minute = dt.minute

    ampm = "오전" if hour < 12 else "오후"
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12

    return f"{ampm} {hour_12}:{minute:02d}"


# ---------------------
# OCR/데이터 함수
# ---------------------


def ocr_region(region):
    """
    region: (left, top, width, height)
    해당 화면 영역을 캡처 후 EasyOCR로 텍스트 추출
    """
    left, top, width, height = region
    img = pyautogui.screenshot(region=(left, top, width, height))

    # PIL Image -> numpy array
    img_np = np.array(img)

    # 1) 그레이스케일
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # 2) 확대 (2~3배 정도)
    gray = cv2.resize(
        gray,
        None,
        fx=2.0,
        fy=2.0,
        interpolation=cv2.INTER_CUBIC
    )

    # 3) 이진화 (배경/글자 대비 강화)
    _, th = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # EasyOCR에 넣기 (detail=0 → 텍스트 문자열 리스트만 반환)
    result = reader.readtext(th, detail=0, paragraph=False)

    text = " ".join(result).strip()
    return text
 # 파일 상단에 이미 있으면 생략

def format_korean_time(dt=None):
    """
    현재 OS 시간을 '오전 11:59' 형태의 문자열로 반환
    """
    if dt is None:
        dt = datetime.now()

    hour = dt.hour
    minute = dt.minute

    ampm = "오전" if hour < 12 else "오후"
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12

    return f"{ampm} {hour_12}:{minute:02d}"


def capture_all_regions():
    """
    title/preview 구역의 텍스트를 읽어 dict로 반환.
    - 화면에서 'time' OCR은 하지 않고, OS 시간으로 채움.
    - 실제 캡쳐는 CAPTURE_REGIONS(테두리 안쪽) 사용
    """
    data = {}
    for key, region in CAPTURE_REGIONS.items():
        try:
            data[key] = ocr_region(region)
        except Exception as e:
            print(f"OCR 오류 ({key}):", e)
            data[key] = ""

    # OS 시간 추가 (예: '오후 11:59')
    data["time"] = format_korean_time()

    return data


    # OS 시간 추가 (예: '오후 11:59')
    data["time"] = format_korean_time()

    return data


# ---------------------
# 트리거: title/preview 텍스트 변화 감지
# ---------------------

last_title_text = None
last_preview_text = None
last_title_text = None
last_preview_text = None


def trigger_region_changed():
    """
    title / preview 영역의 텍스트가 이전과 달라졌는지 확인.
    둘 중 하나라도 변경되면 True 반환.
    캡쳐 영역은 CAPTURE_REGIONS(테두리 안쪽)를 사용.
    """
    global last_title_text, last_preview_text

    title_region = CAPTURE_REGIONS.get("title")
    preview_region = CAPTURE_REGIONS.get("preview")

    curr_title = ocr_region(title_region) if title_region else ""
    curr_preview = ocr_region(preview_region) if preview_region else ""

    # 첫 프레임은 기준만 잡고 False
    if last_title_text is None and last_preview_text is None:
        last_title_text, last_preview_text = curr_title, curr_preview
        return False

    changed = (curr_title != last_title_text) or (curr_preview != last_preview_text)

    # 기준 업데이트
    last_title_text, last_preview_text = curr_title, curr_preview

    return changed


# ---------------------
# 감시 루프 (메인에서 스레드로 돌릴 것)
# ---------------------

def watcher_loop(on_detect, flash_callback=None,
                 cooldown=TRIGGER_COOLDOWN_SEC, poll_interval=0.2):
    """
    on_detect: 감지 시 호출되는 콜백 함수. 인자 1개 (data: dict)
    flash_callback: 깜빡이기 등 시각 효과 콜백. 인자 없음.
    cooldown: 트리거 쿨다운 시간(초)
    poll_interval: 루프 딜레이(초)
    """
    last_trigger_time = 0.0

    while True:
        try:
            # 1) title/preview 텍스트 변화 감지
            if trigger_region_changed():
                now = time.time()

                # 쿨다운 체크
                if now - last_trigger_time > cooldown:
                    last_trigger_time = now

                    # 2) 텍스트 구역들 OCR + OS 시간
                    data = capture_all_regions()
                    print("감지됨:", data)

                    # 3) 시각 효과 콜백
                    if flash_callback is not None:
                        try:
                            flash_callback()
                        except Exception as e:
                            print("flash_callback error:", e)

                    # 4) 데이터 처리 콜백
                    if on_detect is not None:
                        try:
                            on_detect(data)
                        except Exception as e:
                            print("on_detect callback error:", e)

            time.sleep(poll_interval)

        except Exception as e:
            print("watcher_loop error:", e)
            time.sleep(1.0)
