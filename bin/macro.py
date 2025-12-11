import os
import time
import json
import hashlib
import re
from datetime import datetime

import cv2
import pyautogui
import numpy as np
from PIL import ImageGrab
import pyperclip

# OCR 라이브러리 (한글 인식용)
try:
    import easyocr
    OCR_AVAILABLE = True
    # EasyOCR reader 초기화 (한글+영어 지원)
    # GPU 사용 가능하면 자동으로 사용, 없으면 CPU 사용
    _ocr_reader = None
    def get_ocr_reader():
        global _ocr_reader
        if _ocr_reader is None:
            _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=False)  # GPU 사용하려면 gpu=True
        return _ocr_reader
except ImportError:
    OCR_AVAILABLE = False
    print("[warning] easyocr이 설치되지 않았습니다. pip install easyocr로 설치하세요.")

# ---------------------
# 설정 파일 로드 (TRIGGER_REGION 제거 버전)
# ---------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "macro_config.json")

# 기본 REGIONS (카톡 목록에서 title / preview 위치)
DEFAULT_REGIONS = {
    "title":   [141, 132, 260, 18],
    "preview": [141, 150, 714, 25],
}

# 기본 chatting_room 사각형 (left, top, width, height)
DEFAULT_CHATTING_ROOM = [0, 0, 0, 0]
# 기본 chatting_room_center 좌표 (x, y)
DEFAULT_CHATTING_ROOM_CENTER = [0, 0]


def load_config(path: str = CONFIG_PATH):
    """
    JSON 설정 파일에서 REGIONS, chatting_room 사각형, chatting_room_center 좌표를 읽어옴.
    - 파일이 없으면 기본값으로 새로 만들고 기본값 사용
    - 파일이 깨졌으면 에러 출력 후 기본값 사용
    """
    regions = DEFAULT_REGIONS.copy()
    chatting_room = DEFAULT_CHATTING_ROOM.copy()
    chatting_room_center = DEFAULT_CHATTING_ROOM_CENTER.copy()

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)

            if "REGIONS" in user_cfg and isinstance(user_cfg["REGIONS"], dict):
                for k, v in user_cfg["REGIONS"].items():
                    regions[k] = v

            if "chatting_room" in user_cfg and isinstance(user_cfg["chatting_room"], list) and len(user_cfg["chatting_room"]) == 4:
                chatting_room = user_cfg["chatting_room"]

            if "chatting_room_center" in user_cfg and isinstance(user_cfg["chatting_room_center"], list) and len(user_cfg["chatting_room_center"]) == 2:
                chatting_room_center = user_cfg["chatting_room_center"]

            print("[config] 로드됨:", path)
        except Exception as e:
            print(f"[config] {path} 로드 실패, 기본값 사용:", e)
    else:
        # 파일이 없으면 기본값으로 새로 생성
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "REGIONS": DEFAULT_REGIONS,
                    "chatting_room": DEFAULT_CHATTING_ROOM,
                    "chatting_room_center": DEFAULT_CHATTING_ROOM_CENTER
                }, f, ensure_ascii=False, indent=2)
            print(f"[config] {path} 기본 설정 파일 생성됨. REGIONS, chatting_room, chatting_room_center를 편집해서 사용하세요.")
        except Exception as e:
            print(f"[config] {path} 기본 설정 파일 생성 실패:", e)

    print("[config] REGIONS:", regions)
    print("[config] chatting_room:", chatting_room)
    print("[config] chatting_room_center:", chatting_room_center)
    return regions, chatting_room, chatting_room_center


# 설정 로드
_REGIONS, _CHATTING_ROOM, _CHATTING_ROOM_CENTER = load_config()

# tuple로 변환 (좌표용)
REGIONS = {k: tuple(v) for k, v in _REGIONS.items()}

# chatting_room 사각형 (left, top, width, height)
CHATTING_ROOM = tuple(_CHATTING_ROOM)
# chatting_room_center 좌표 (x, y)
CHATTING_ROOM_CENTER = tuple(_CHATTING_ROOM_CENTER)

# 실제 캡쳐에는 테두리 안쪽만 쓰기 위한 마진
CAPTURE_MARGIN = 4
CAPTURE_REGIONS = {}

for key, (left, top, width, height) in REGIONS.items():
    cl = left + CAPTURE_MARGIN
    ct = top + CAPTURE_MARGIN
    cw = max(1, width - CAPTURE_MARGIN * 2)
    ch = max(1, height - CAPTURE_MARGIN * 2)

    CAPTURE_REGIONS[key] = (cl, ct, cw, ch)

print("[config] CAPTURE_REGIONS (margin 적용):", CAPTURE_REGIONS)
print("[config] CHATTING_ROOM:", CHATTING_ROOM)
print("[config] CHATTING_ROOM_CENTER:", CHATTING_ROOM_CENTER)

# ---------------------
# 매크로 설정
# ---------------------

# 트리거 쿨다운 (초) – 텍스트가 자꾸 바뀌어도 연속 트리거 방지
TRIGGER_COOLDOWN_SEC = 0.5

# 기본 폴링 간격 (초) - CPU 부하와 감지 속도 균형
DEFAULT_POLL_INTERVAL = 0.5

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
# preview 스택 딕셔너리 & 예외 타이틀
# ---------------------

# title을 key로, 값은 "\n[title_or_???] [오후 4:33] preview" 형식 문자열 누적
PREVIEW_DICT = {}  # {title: str}

# 예외 title 리스트 (GUI / main.py에서 import해서 수정)
EXCEPTION_TITLES = [
    # 예: "행복한 우리집", "가족방"
]


def save_chatting_content(title_key: str, content: str):
    """
    chatting_room에서 복사한 내용을 title_key를 key로 하여 PREVIEW_DICT에 저장.
    title_key는 title 영역의 이미지 해시 또는 실제 title 문자열.
    """
    if not title_key:
        title_key = "unknown"
    
    if not content:
        print(f"[warning] title_key '{title_key}'에 대한 내용이 비어있습니다.")
        return
    
    # 기존 내용이 있으면 덮어쓰기 (통채로 저장)
    PREVIEW_DICT[title_key] = content
    print(f"[STACK][{title_key}] 내용 저장 완료 (길이: {len(content)} 문자)")


# ---------------------
# 클릭 및 복사 함수
# ---------------------

def double_click_preview_center():
    """
    preview 영역의 정중앙을 더블클릭 (클릭 간격 0.3초)
    """
    preview_region = REGIONS.get("preview")
    if not preview_region:
        print("[error] preview 영역이 설정되지 않았습니다.")
        return False
    
    left, top, width, height = preview_region
    center_x = left + width // 2
    center_y = top + height // 2
    
    pyautogui.click(center_x, center_y)
    time.sleep(0.3)
    pyautogui.click(center_x, center_y)
    print(f"[click] preview 정중앙 더블클릭: ({center_x}, {center_y})")
    return True


def copy_chatting_room_content():
    """
    chatting_room_center 좌표를 클릭한 후 ctrl-A, ctrl-C로 내용을 복사하여 반환.
    최대한 빠르게 수행.
    복사 진행 중에는 플래그를 설정하여 감지를 방지.
    """
    global copying_in_progress
    
    if not CHATTING_ROOM_CENTER or CHATTING_ROOM_CENTER == (0, 0):
        print("[error] chatting_room_center 좌표가 설정되지 않았습니다.")
        return None
    
    x, y = CHATTING_ROOM_CENTER
    
    # 복사 시작 플래그 설정
    copying_in_progress = True
    
    try:
        # chatting_room_center 좌표 클릭
        pyautogui.click(x, y)
        time.sleep(0.1)  # 클릭 후 약간의 대기
        
        # ctrl-A (전체 선택)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.05)
        
        # ctrl-C (복사)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.1)  # 클립보드 복사 대기
        
        # 클립보드에서 내용 가져오기
        try:
            content = pyperclip.paste()
            print(f"[copy] chatting_room 내용 복사 완료 (길이: {len(content)} 문자)")
            return content
        except Exception as e:
            print(f"[error] 클립보드 읽기 실패: {e}")
            return None
    finally:
        # 복사 완료 플래그 해제
        copying_in_progress = False


def extract_last_speaker(content: str) -> str:
    """
    채팅 내용에서 마지막 발화자를 추출.
    포맷: [발화자] [시간] 내용
    
    Args:
        content: 채팅 내용 문자열
        
    Returns:
        마지막 발화자 문자열 (예: "이가을") 또는 None
    """
    if not content:
        return None
    
    lines = content.strip().split('\n')
    
    # 역순으로 순회하여 마지막 메시지 라인 찾기
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        
        # 날짜 헤더 패턴 제외 (예: "2025년 12월 6일 토요일")
        if re.match(r'\d+년 \d+월 \d+일', line):
            continue
        
        # [발화자] [시간] 내용 패턴 매칭
        match = re.match(r'\[([^\]]+)\]', line)
        if match:
            speaker = match.group(1)
            return speaker
    
    return None


# ---------------------
# 트리거: title / preview 텍스트 변화 감지
# ---------------------

last_title_hash = None
last_preview_hash = None
last_chatting_room_hash = None

# 감시 중지 플래그 (기존 title/preview 감시용)
watch_stopped = False

# chatting_room 감시 중지 플래그
chatting_room_watch_stopped = False

# 복사 진행 중 플래그 (CTRL-A, CTRL-C 진행 중 감지 방지)
copying_in_progress = False


def get_region_image_hash(region):
    """
    영역의 이미지를 빠르게 캡처하여 해시값 반환.
    OCR보다 훨씬 빠르게 변경 감지 가능.
    최적화: PIL ImageGrab 사용, 작은 크기로 리사이즈, 그레이스케일 변환.
    """
    if region is None:
        return None
    
    left, top, width, height = region
    # PIL ImageGrab이 pyautogui.screenshot보다 더 빠름
    # bbox는 (left, top, right, bottom) 형식
    img = ImageGrab.grab(bbox=(left, top, left + width, top + height))
    img_np = np.array(img)
    
    # 더 작은 크기로 리사이즈 (16x16) - 변경 감지 목적이므로 충분
    # INTER_NEAREST가 가장 빠른 보간법
    small = cv2.resize(img_np, (16, 16), interpolation=cv2.INTER_NEAREST)
    
    # RGB를 그레이스케일로 변환하여 데이터량 1/3로 감소
    if len(small.shape) == 3:
        gray_small = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    else:
        gray_small = small
    
    # 바이트로 변환하여 해시 계산
    img_bytes = gray_small.tobytes()
    return hashlib.md5(img_bytes).hexdigest()


def trigger_region_changed():
    """
    title / preview 영역의 픽셀 변경을 빠르게 감지.
    변경이 감지되면 True를 반환.
    
    최적화: 해시 계산을 최소화하고, 변경이 없을 때는 즉시 반환.
    """
    global last_title_hash, last_preview_hash

    title_region = REGIONS.get("title")
    preview_region = REGIONS.get("preview")

    # 이미지 해시로 빠른 변경 감지
    curr_title_hash = get_region_image_hash(title_region) if title_region else None
    
    # 첫 프레임: 기준만 세팅하고 False
    if last_title_hash is None:
        last_title_hash = curr_title_hash
        last_preview_hash = get_region_image_hash(preview_region) if preview_region else None
        return False

    # title 해시가 같으면 preview 해시도 확인
    title_unchanged = (curr_title_hash == last_title_hash)
    
    if title_unchanged:
        # title이 안 바뀌었으면 preview만 확인
        curr_preview_hash = get_region_image_hash(preview_region) if preview_region else None
        preview_unchanged = (curr_preview_hash == last_preview_hash)
        
        # 둘 다 안 바뀌었으면 즉시 반환
        if preview_unchanged:
            return False
    else:
        # title이 바뀌었으면 preview도 확인
        curr_preview_hash = get_region_image_hash(preview_region) if preview_region else None

    # 해시가 다르면 변경 감지
    changed = (curr_title_hash != last_title_hash) or (curr_preview_hash != last_preview_hash)

    # 해시 업데이트
    last_title_hash = curr_title_hash
    last_preview_hash = curr_preview_hash

    return changed


# ---------------------
# 감시 루프 (main.py에서 스레드로 돌림)
# ---------------------

def get_region_image_text(region):
    """
    영역의 이미지를 OCR로 인식하여 텍스트를 반환.
    한글 인식 지원.
    """
    if region is None:
        return None
    
    if not OCR_AVAILABLE:
        print("[error] OCR이 사용 불가능합니다. easyocr을 설치하세요.")
        return None
    
    try:
        left, top, width, height = region
        # PIL ImageGrab으로 이미지 캡처
        img = ImageGrab.grab(bbox=(left, top, left + width, top + height))
        img_np = np.array(img)
        
        # EasyOCR은 numpy array를 직접 받을 수 있음
        reader = get_ocr_reader()
        results = reader.readtext(img_np)
        
        # OCR 결과에서 텍스트 추출 (공백 제거)
        text_parts = []
        for (bbox, text, confidence) in results:
            if confidence > 0.5:  # 신뢰도 50% 이상만 사용
                text_parts.append(text.strip())
        
        # 여러 텍스트를 공백으로 연결
        full_text = ' '.join(text_parts).strip()
        
        if not full_text:
            print("[warning] OCR로 텍스트를 인식하지 못했습니다.")
            return None
        
        return full_text
    except Exception as e:
        print(f"[error] OCR 처리 중 오류: {e}")
        return None


def get_current_title_text():
    """
    현재 title 영역의 OCR 텍스트를 반환.
    title을 구분하는 key로 사용.
    """
    title_region = REGIONS.get("title")
    if not title_region:
        return None
    return get_region_image_text(title_region)


def get_current_title_hash():
    """
    현재 title 영역의 이미지 해시를 반환.
    (하위 호환성을 위해 유지, 하지만 OCR 텍스트를 우선 사용)
    """
    title_region = REGIONS.get("title")
    if not title_region:
        return None
    return get_region_image_hash(title_region)


def trigger_chatting_room_changed():
    """
    chatting_room 사각형 영역의 픽셀 변경을 빠르게 감지.
    변경이 감지되면 True를 반환.
    복사 진행 중일 때는 감지하지 않음.
    """
    global last_chatting_room_hash, copying_in_progress
    
    # 복사 진행 중이면 감지하지 않음
    if copying_in_progress:
        return False
    
    if not CHATTING_ROOM or CHATTING_ROOM == (0, 0, 0, 0):
        return False
    
    # chatting_room을 region으로 변환 (left, top, width, height)
    chatting_room_region = CHATTING_ROOM
    
    # 이미지 해시로 빠른 변경 감지
    curr_hash = get_region_image_hash(chatting_room_region)
    
    # 첫 프레임: 기준만 세팅하고 False
    if last_chatting_room_hash is None:
        last_chatting_room_hash = curr_hash
        return False
    
    # 해시가 다르면 변경 감지
    changed = (curr_hash != last_chatting_room_hash)
    
    # 해시 업데이트
    last_chatting_room_hash = curr_hash
    
    return changed


def watch_chatting_room(title_key, on_detect=None, poll_interval=0.1):
    """
    chatting_room 사각형 영역의 변경을 감시하고, 변경이 감지되면 복사하여 딕셔너리 갱신.
    픽셀이 5초 이상 변하지 않았을 때도 복사하여 딕셔너리 갱신하고, 마지막 발화자가 '이가을'이면 종료 처리.
    
    Args:
        title_key: title 텍스트 또는 해시 (딕셔너리 key로 사용)
        on_detect: 콜백 함수 (title_key, content)
        poll_interval: 폴링 간격 (초)
    """
    global chatting_room_watch_stopped
    chatting_room_watch_stopped = False  # 감시 시작 시 플래그 초기화
    
    # 마지막 변경 시간 추적
    last_change_time = time.time()
    STALE_THRESHOLD = 5.0  # 5초 이상 변하지 않았을 때 체크
    
    print("[watch_chatting_room] chatting_room 감시 시작...")
    
    while not chatting_room_watch_stopped:
        try:
            changed = trigger_chatting_room_changed()
            
            if changed:
                print("[watch_chatting_room] chatting_room 변경 감지됨")
                last_change_time = time.time()  # 변경 시간 업데이트
                time.sleep(0.1)  # 0.1초 대기
                
                # chatting_room_center 클릭 후 ctrl-A, ctrl-C로 복사
                content = copy_chatting_room_content()
                if content is not None:
                    # 딕셔너리 갱신
                    save_chatting_content(title_key, content)
                    
                    # on_detect 콜백
                    if on_detect is not None:
                        try:
                            on_detect(title_key, content)
                        except Exception as e:
                            print("on_detect callback error:", e)
                    
                    print("[watch_chatting_room] chatting_room 내용 갱신 완료")
                else:
                    print("[watch_chatting_room] chatting_room 내용 복사 실패")
            else:
                # 변경이 없을 때, 5초 이상 변하지 않았는지 체크
                current_time = time.time()
                time_since_last_change = current_time - last_change_time
                
                if time_since_last_change >= STALE_THRESHOLD:
                    print(f"[watch_chatting_room] 5초 이상 변경 없음, 딕셔너리 갱신 체크...")
                    last_change_time = current_time  # 체크 시간 업데이트 (중복 체크 방지)
                    
                    # chatting_room_center 클릭 후 ctrl-A, ctrl-C로 복사
                    content = copy_chatting_room_content()
                    if content is not None:
                        # 딕셔너리 갱신
                        save_chatting_content(title_key, content)
                        
                        # 마지막 발화자 추출
                        last_speaker = extract_last_speaker(content)
                        print(f"[watch_chatting_room] 마지막 발화자: {last_speaker}")
                        
                        # 마지막 발화자가 '이가을'이면 종료 처리
                        if last_speaker == "이가을":
                            print("[watch_chatting_room] 마지막 발화자가 '이가을'이므로 종료 처리")
                            try:
                                import schedular
                                schedular.process_finish_action()
                                print("[watch_chatting_room] finish 액션 완료")
                            except Exception as e:
                                print(f"[error] finish 액션 실행 실패: {e}")
                        else:
                            print("[watch_chatting_room] 마지막 발화자가 '이가을'이 아니므로 계속 감시")
                        
                        # on_detect 콜백
                        if on_detect is not None:
                            try:
                                on_detect(title_key, content)
                            except Exception as e:
                                print("on_detect callback error:", e)
                    else:
                        print("[watch_chatting_room] chatting_room 내용 복사 실패")
            
            time.sleep(poll_interval)
            
        except Exception as e:
            print(f"[watch_chatting_room] error: {e}")
            time.sleep(1.0)
    
    print("[watch_chatting_room] chatting_room 감시 종료됨")


def process_chatting_change(on_detect=None):
    """
    title/preview 변경 감지 후 처리 프로세스:
    1. 2초 대기
    2. preview 정중앙 더블클릭 (클릭 간격 0.3초)
    3. chatting_room_center 클릭 후 1회의 ctrl-A, ctrl-C로 복사
    4. 딕셔너리에 저장
    
    Returns:
        tuple: (title_key, content) 또는 None
    """
    global watch_stopped
    
    print("[process] title/preview 변경 감지, 2초 후 처리 시작...")
    time.sleep(2.0)
    
    # 현재 title 텍스트 가져오기 (OCR로 인식, key로 사용)
    title_key = get_current_title_text()
    
    # OCR 실패 시 해시로 대체
    if not title_key:
        print("[warning] OCR로 title을 인식하지 못했습니다. 해시를 사용합니다.")
        title_key = get_current_title_hash()
        if not title_key:
            print("[error] title을 가져올 수 없습니다.")
            return None
    
    print(f"[process] title key: {title_key}")
    
    # preview 정중앙 더블클릭
    if not double_click_preview_center():
        print("[error] preview 더블클릭 실패")
        return None
    
    # 더블클릭 후 약간 대기 (채팅방이 열리는 시간)
    time.sleep(0.5)
    
    # chatting_room_center 클릭 후 1회의 ctrl-A, ctrl-C로 복사
    content = copy_chatting_room_content()
    if content is not None:
        # 딕셔너리에 저장
        save_chatting_content(title_key, content)
        
        # on_detect 콜백
        if on_detect is not None:
            try:
                on_detect(title_key, content)
            except Exception as e:
                print("on_detect callback error:", e)
        
        print("[process] chatting_room 내용 복사 및 저장 완료")
        
        # chatting_room 감시 시작 (별도 스레드) - 이후 변경사항 감지용
        import threading
        thread = threading.Thread(
            target=watch_chatting_room,
            args=(title_key, on_detect),
            kwargs={"poll_interval": 0.1},
            daemon=True
        )
        thread.start()
        print("[process] chatting_room 감시 시작됨")
        
        # 기존 감시 멈춤
        watch_stopped = True
        print("[process] 기존 감시 중지됨")
        
        return (title_key, content)
    else:
        print("[error] chatting_room 내용 복사 실패")
        return None


def watcher_loop(on_detect=None, 
                 cooldown=TRIGGER_COOLDOWN_SEC, poll_interval=DEFAULT_POLL_INTERVAL):
    """
    on_detect(title: str, content: str): 감지 시 호출되는 콜백
      - title: 채팅방 제목
      - content: 복사된 채팅 내용

    - title / preview 픽셀이 바뀌면 트리거
    - 쿨다운 시간 내에는 중복 감지 방지
    - 이미지 해시를 사용하여 빠른 변경 감지
    - watch_stopped 플래그가 True이면 감시 중지
    """
    global watch_stopped
    last_trigger_time = 0.0
    last_trigger_hash = None

    while True:
        try:
            # 감시 중지 플래그 확인
            if watch_stopped:
                time.sleep(poll_interval)
                continue
            
            changed = trigger_region_changed()
            
            if changed:
                now = time.time()
                
                # 쿨다운 체크
                if now - last_trigger_time > cooldown:
                    # 현재 해시 계산 (중복 방지용)
                    title_region = REGIONS.get("title")
                    preview_region = REGIONS.get("preview")
                    curr_title_hash = get_region_image_hash(title_region) if title_region else None
                    curr_preview_hash = get_region_image_hash(preview_region) if preview_region else None
                    combined_hash = f"{curr_title_hash}_{curr_preview_hash}"
                    
                    if combined_hash != last_trigger_hash:
                        last_trigger_time = now
                        last_trigger_hash = combined_hash

                        print("[watcher] title/preview 변경 감지됨")
                        
                        # 별도 스레드에서 처리 (GUI 블로킹 방지)
                        import threading
                        def process_in_thread():
                            result = process_chatting_change(on_detect)
                            # result는 (title_key, None)이므로 content 저장은 하지 않음
                            # chatting_room 감시에서 처리됨
                        
                        thread = threading.Thread(target=process_in_thread, daemon=True)
                        thread.start()

            time.sleep(poll_interval)

        except Exception as e:
            print("watcher_loop error:", e)
            time.sleep(1.0)
