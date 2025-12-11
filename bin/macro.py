import os
import time
import json
import hashlib
import re
import threading
import random
from datetime import datetime

import cv2
import pyautogui
import numpy as np
from PIL import ImageGrab, Image
import pyperclip

# OCR 라이브러리 (한글 인식용)
try:
    import easyocr
    OCR_AVAILABLE = True
    
    # EasyOCR reader 초기화 (한글 지원)
    _ocr_reader = None
    
    def initialize_ocr():
        """OCR reader를 GPU를 사용하여 강제 초기화"""
        global _ocr_reader
        if _ocr_reader is not None:
            return _ocr_reader
        
        try:
            _ocr_reader = easyocr.Reader(['ko'], gpu=True)
            return _ocr_reader
        except Exception as e:
            return None
    
    def get_ocr_reader():
        """OCR reader 반환"""
        global _ocr_reader
        if _ocr_reader is None:
            return None
        return _ocr_reader
except ImportError:
    OCR_AVAILABLE = False
    
    def initialize_ocr():
        """OCR 초기화 (easyocr이 없을 때 더미 함수)"""
        return None
    
    def get_ocr_reader():
        """OCR reader 반환 (easyocr이 없을 때 더미 함수)"""
        return None

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
        except Exception as e:
            pass
    else:
        # 파일이 없으면 기본값으로 새로 생성
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "REGIONS": DEFAULT_REGIONS,
                    "chatting_room": DEFAULT_CHATTING_ROOM,
                    "chatting_room_center": DEFAULT_CHATTING_ROOM_CENTER
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            pass
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

# ---------------------
# 매크로 설정
# ---------------------

# 트리거 쿨다운 (초) – 텍스트가 자꾸 바뀌어도 연속 트리거 방지
TRIGGER_COOLDOWN_SEC = 0.5

# 기본 폴링 간격 (초) - CPU 부하와 감지 속도 균형
DEFAULT_POLL_INTERVAL = 0.5

# ---------------------
# OpenAI 클라이언트 관련
# ---------------------

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None
except Exception:
    OPENAI_AVAILABLE = False
    OpenAI = None

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# .env 파일 로드
if DOTENV_AVAILABLE:
    ENV_PATH = os.path.join(BASE_DIR, "..", ".env")
    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH)


def get_openai_client():
    """OpenAI 클라이언트 생성 (.env 파일 또는 환경 변수에서 API 키 읽기)"""
    if not OPENAI_AVAILABLE:
        return None
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return None
    
    try:
        client = OpenAI(api_key=api_key)
        return client
    except Exception:
        return None


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
# 설정 파일 유틸리티 함수
# ---------------------

def load_config_dict(path: str = CONFIG_PATH):
    """설정 파일에서 좌표 등을 Dict 형태로 읽어옴 (generator, schedular용)"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ---------------------
# 텍스트 처리 유틸리티 함수
# ---------------------

def remove_date_header(message_context: str) -> str:
    """채팅 내용에서 날짜 줄 제거 (예: "2025년 12월 6일 토요일")"""
    if not message_context:
        return ""
    message_context = re.sub(r'^\d+년 \d+월 \d+일 \w+일\s*\n?', '', message_context, flags=re.MULTILINE)
    return message_context.strip()


# ---------------------
# preview 스택 딕셔너리 & 예외 타이틀
# ---------------------

# title을 key로, 값은 "\n[title_or_???] [오후 4:33] preview" 형식 문자열 누적
PREVIEW_DICT = {}  # {title: str}

# 예외 title 리스트 (GUI / main.py에서 import해서 수정)
EXCEPTION_TITLES = [
    # 예: "행복한 우리집", "가족방"
]

# ---------------------
# 채팅방 태그 관리
# ---------------------

# 채팅방 제목별 관계 태그 매핑
CHAT_TAG_MAP = {
    "FAMILY": [
        "행복한우리집",
        "아빠",
        "엄마",
        "이고은"
    ],
    "FRIEND": [
        "최지원",
        "김준석",
        "강성민"
    ],
    "GROUP_MIXED": []
}

# 기본 태그 (리스트에 없는 경우)
DEFAULT_TAG = "STRANGER"


def get_chat_relationship_tag(title_key: str) -> str:
    """
    채팅방 제목에 해당하는 관계 태그를 반환.
    
    Args:
        title_key: 채팅방 제목 (정제된 key)
        
    Returns:
        관계 태그 (FAMILY / FRIEND / STRANGER / GROUP_MIXED)
    """
    # 정제된 key로 태그 찾기
    for tag, titles in CHAT_TAG_MAP.items():
        # 정확히 일치하는 경우
        if title_key in titles:
            return tag
    
    # 리스트에 없으면 기본값 반환
    return DEFAULT_TAG


def sanitize_dict_key(key: str) -> str:
    """
    딕셔너리 key를 정제하여 초성, 영어, 숫자를 제거하고 완성형 한글과 공백만 남김.
    
    Args:
        key: 원본 key 문자열
        
    Returns:
        정제된 key 문자열 (완성형 한글과 공백만 포함)
    """
    if not key:
        return "unknown"
    
    # 완성형 한글 범위: U+AC00 (가) ~ U+D7A3 (힣)
    # 공백도 허용
    result = []
    for char in key:
        # 완성형 한글이거나 공백이면 유지
        if '\uAC00' <= char <= '\uD7A3' or char == ' ':
            result.append(char)
    
    # 정제된 결과가 비어있으면 "unknown" 반환
    sanitized = ''.join(result).strip()
    if not sanitized:
        return "unknown"
    
    return sanitized


# 딕셔너리 변경 감지용 콜백
_dict_change_callback = None

# 로그 콜백 (GUI 하단 로그에 메시지 출력용)
_log_callback = None

def set_dict_change_callback(callback):
    """딕셔너리 변경 감지 콜백 설정"""
    global _dict_change_callback
    _dict_change_callback = callback

def set_log_callback(callback):
    """로그 콜백 설정 (GUI 하단 로그 출력용)"""
    global _log_callback
    _log_callback = callback

def log_message(message: str):
    """로그 메시지 출력 (콜백이 설정되어 있으면 호출)"""
    global _log_callback
    if _log_callback:
        try:
            _log_callback(message)
        except Exception:
            pass

def save_chatting_content(title_key: str, content: str, skip_callback: bool = False) -> str:
    """
    chatting_room에서 복사한 내용을 title_key를 key로 하여 PREVIEW_DICT에 저장.
    title_key는 title 영역의 이미지 해시 또는 실제 title 문자열.
    key는 정제되어 초성, 영어, 숫자가 제거됨.
    딕셔너리가 변경되었을 때만 콜백 호출.
    
    Args:
        title_key: 채팅방 제목
        content: 채팅 내용
        skip_callback: True면 콜백 호출을 건너뜀
    
    Returns:
        정제된 title_key
    """
    global _dict_change_callback
    
    if not title_key:
        title_key = "unknown"
    
    # key 정제: 초성, 영어, 숫자 제거
    title_key = sanitize_dict_key(title_key)
    
    if not content:
        return title_key
    
    # 기존 내용 확인
    old_content = PREVIEW_DICT.get(title_key)
    
    # 딕셔너리 갱신
    PREVIEW_DICT[title_key] = content
    
    # 딕셔너리 업데이트 로그
    if old_content != content:
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M:%S")
        log_message(f"[{time_str}] [딕셔너리 업데이트] {title_key} (길이: {len(content)} 문자)")
    
    # 내용이 변경되었을 때만 콜백 호출 (skip_callback이 False일 때만)
    if old_content != content and not skip_callback:
        print(f"[macro] 딕셔너리 내용 변경 감지: {title_key}")
        print(f"[macro]   - 기존 내용 길이: {len(old_content) if old_content else 0}")
        print(f"[macro]   - 새 내용 길이: {len(content)}")
        print(f"[macro]   - 콜백 존재: {_dict_change_callback is not None}")
        
        if _dict_change_callback is not None:
            try:
                print(f"[macro] 딕셔너리 변경 콜백 호출 시작: {title_key}")
                _dict_change_callback(title_key, content)
                print(f"[macro] 딕셔너리 변경 콜백 호출 완료: {title_key}")
            except Exception as e:
                print(f"[macro] [ERROR] 딕셔너리 변경 콜백 호출 중 오류: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[macro] [WARNING] 딕셔너리 변경 콜백이 None입니다!")
    
    return title_key


# ---------------------
# 클릭 및 복사 함수
# ---------------------

def double_click_preview_center():
    """
    preview 영역의 정중앙을 더블클릭 (클릭 간격 0.3초)
    """
    global clicking_in_progress
    
    preview_region = REGIONS.get("preview")
    if not preview_region:
        return False
    
    left, top, width, height = preview_region
    center_x = left + width // 2
    center_y = top + height // 2
    
    # 클릭 시작 플래그 설정
    clicking_in_progress = True
    try:
        pyautogui.click(center_x, center_y)
        time.sleep(0.3)
        pyautogui.click(center_x, center_y)
        return True
    finally:
        # 클릭 완료 플래그 해제
        clicking_in_progress = False


def copy_chatting_room_content():
    """
    chatting_room_center 좌표를 클릭한 후 ctrl-A, ctrl-C로 내용을 복사하여 반환.
    최대한 빠르게 수행.
    복사 진행 중에는 플래그를 설정하여 감지를 방지.
    """
    global copying_in_progress, clicking_in_progress
    
    if not CHATTING_ROOM_CENTER or CHATTING_ROOM_CENTER == (0, 0):
        return None
    
    x, y = CHATTING_ROOM_CENTER
    
    # 복사 및 클릭 시작 플래그 설정
    copying_in_progress = True
    clicking_in_progress = True
    
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
            return content
        except Exception as e:
            return None
    finally:
        # 복사 및 클릭 완료 플래그 해제
        copying_in_progress = False
        clicking_in_progress = False


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


def extract_last_message_time(content: str) -> str:
    """
    채팅 내용에서 마지막 발화 시간을 추출.
    포맷: [발화자] [오전/오후 HH:MM] 내용
    
    Args:
        content: 채팅 내용 문자열
        
    Returns:
        마지막 발화 시간 문자열 (예: "오후 4:19") 또는 None
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
        
        # [발화자] [오전/오후 HH:MM] 내용 패턴 매칭
        match = re.search(r'\[([^\]]+)\] \[(오전|오후) (\d{1,2}):(\d{2})\]', line)
        if match:
            time_str = f"{match.group(2)} {match.group(3)}:{match.group(4)}"
            return time_str
    
    return None


def parse_korean_time(time_str: str) -> datetime:
    """
    한국어 시간 문자열을 datetime 객체로 변환.
    포맷: "오전 8:36" 또는 "오후 4:19"
    
    Args:
        time_str: 시간 문자열 (예: "오후 4:19")
        
    Returns:
        datetime 객체 (오늘 날짜 기준) 또는 None
    """
    if not time_str:
        return None
    
    try:
        match = re.match(r'(오전|오후) (\d{1,2}):(\d{2})', time_str)
        if not match:
            return None
        
        ampm = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        # 12시간제를 24시간제로 변환
        if ampm == "오후" and hour != 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
        
        # 오늘 날짜로 datetime 객체 생성
        today = datetime.now().date()
        dt = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
        
        return dt
    except Exception as e:
        return None


def compare_message_time(content: str, threshold_minutes: int = 2) -> tuple:
    """
    채팅 내용의 마지막 발화 시간과 현재 시간을 비교.
    
    Args:
        content: 채팅 내용 문자열
        threshold_minutes: 임계값 (분) - 이 값 이상 차이나면 True 반환
        
    Returns:
        tuple: (is_delayed: bool, time_diff_seconds: float)
        - is_delayed: 2분 이상 차이나면 True
        - time_diff_seconds: 시간 차이 (초)
    """
    if not content:
        return (False, 0.0)
    
    # 마지막 발화 시간 추출
    last_time_str = extract_last_message_time(content)
    if not last_time_str:
        return (False, 0.0)
    
    # 시간 문자열을 datetime으로 변환
    last_time = parse_korean_time(last_time_str)
    if not last_time:
        return (False, 0.0)
    
    # 현재 시간
    current_time = datetime.now()
    
    # 시간 차이 계산 (초)
    time_diff = (current_time - last_time).total_seconds()
    
    # 2분 이상 차이나는지 확인
    threshold_seconds = threshold_minutes * 60
    is_delayed = time_diff >= threshold_seconds
    
    return (is_delayed, time_diff)


def add_to_delay_queue(title: str, time_diff_seconds: float):
    """
    지연 큐에 채팅방 추가.
    - 1분 이하: 2초에서 5초 랜덤 지연
    - 1분~3분: 10초 지연
    - 3분 이상: 그만큼의 차이 + 랜덤성 부여한 가감 (감소에 치중)
    - 이미 큐에 있으면 무시
    
    Args:
        title: 채팅방 제목
        time_diff_seconds: 시간 차이 (초)
    """
    # 이미 큐에 있으면 무시
    if title in DELAY_QUEUE:
        print(f"[queue] {title} 이미 큐에 있음, 무시")
        return
    
    current_time = time.time()
    one_minute = 60  # 1분
    three_minutes = 180  # 3분
    
    if time_diff_seconds <= one_minute:
        # 1분 이하: 2초에서 5초 랜덤 지연
        random_delay = random.uniform(2.0, 5.0)
        scheduled_time = current_time + random_delay
        DELAY_QUEUE[title] = {
            "scheduled_time": scheduled_time,
            "status": "pending",
            "added_time": current_time  # 선입선출을 위한 추가 시간
        }
        print(f"[queue] {title} pending 상태로 큐 추가: {random_delay:.1f}초 후 ({time.strftime('%H:%M:%S', time.localtime(scheduled_time))})")
    elif time_diff_seconds <= three_minutes:
        # 1분~3분: 10초 지연
        scheduled_time = current_time + 10.0
        DELAY_QUEUE[title] = {
            "scheduled_time": scheduled_time,
            "status": "pending",
            "added_time": current_time  # 선입선출을 위한 추가 시간
        }
        print(f"[queue] {title} pending 상태로 큐 추가: 10초 후 ({time.strftime('%H:%M:%S', time.localtime(scheduled_time))})")
    else:
        # 3분 이상: 그만큼의 차이 + 랜덤성 부여한 가감 (감소에 치중)
        # 랜덤성: -10% ~ +5% 범위 (감소에 치중)
        random_factor = random.uniform(-0.10, 0.05)
        adjusted_delay = time_diff_seconds * (1 + random_factor)
        scheduled_time = current_time + adjusted_delay
        DELAY_QUEUE[title] = {
            "scheduled_time": scheduled_time,
            "status": "pending",
            "added_time": current_time  # 선입선출을 위한 추가 시간
        }
        print(f"[queue] {title} pending 상태로 큐 추가: {adjusted_delay:.1f}초 후 (원본: {time_diff_seconds:.1f}초, 조정: {random_factor*100:.1f}%) ({time.strftime('%H:%M:%S', time.localtime(scheduled_time))})")


def get_queue_status(title: str) -> dict:
    """
    큐에서 특정 채팅방의 상태를 가져옴.
    
    Args:
        title: 채팅방 제목
        
    Returns:
        dict: {"status": str, "remaining_seconds": float} 또는 None
    """
    if title not in DELAY_QUEUE:
        return None
    
    queue_item = DELAY_QUEUE[title]
    current_time = time.time()
    scheduled_time = queue_item["scheduled_time"]
    
    remaining_seconds = max(0, scheduled_time - current_time)
    
    return {
        "status": queue_item["status"],
        "remaining_seconds": remaining_seconds
    }


def is_queue_ready(title: str) -> bool:
    """
    큐에서 특정 채팅방이 클릭할 준비가 되었는지 확인.
    
    Args:
        title: 채팅방 제목
        
    Returns:
        bool: 준비되었으면 True
    """
    if title not in DELAY_QUEUE:
        return False
    
    queue_item = DELAY_QUEUE[title]
    current_time = time.time()
    scheduled_time = queue_item["scheduled_time"]
    
    return current_time >= scheduled_time and queue_item["status"] == "pending"


def set_queue_status(title: str, status: str):
    """
    큐에서 특정 채팅방의 상태를 설정.
    
    Args:
        title: 채팅방 제목
        status: "pending", "waiting", "processing"
    """
    if title in DELAY_QUEUE:
        DELAY_QUEUE[title]["status"] = status


def remove_from_queue(title: str):
    """
    큐에서 특정 채팅방 제거.
    
    Args:
        title: 채팅방 제목
    """
    if title in DELAY_QUEUE:
        del DELAY_QUEUE[title]
        print(f"[queue] {title} 큐에서 제거됨")


def find_and_click_title_in_list(target_title: str) -> bool:
    """
    채팅방 리스트에서 title부터 title2, title3, title4 순으로 OCR로 스캔하여 target_title과 일치하는 영역을 찾아 클릭.
    찾으면 title 정중앙 더블클릭 후 chatting_room_center 좌표를 1회 클릭.
    
    Args:
        target_title: 찾을 채팅방 제목
        
    Returns:
        bool: 찾아서 클릭했으면 True, 못 찾았으면 False
    """
    # title부터 title2, title3, title4, title5, title6 순으로 영역 가져오기
    title_regions = []
    
    # title이 있으면 먼저 추가
    if "title" in REGIONS:
        title_regions.append(("title", REGIONS["title"]))
    
    # title2, title3, title4, title5, title6 순으로 추가
    for i in range(2, 7):
        region_key = f"title{i}"
        if region_key in REGIONS:
            title_regions.append((region_key, REGIONS[region_key]))
    
    if not title_regions:
        return False
    
    # 각 영역을 순회하며 OCR 수행 (찾으면 즉시 종료)
    for region_key, region in title_regions:
        try:
            # OCR로 텍스트 인식
            recognized_text = get_region_image_text(region)
            if not recognized_text:
                continue
            
            # 인식한 텍스트와 target_title 비교 (부분 일치 허용)
            if target_title in recognized_text or recognized_text in target_title:
                # 일치하는 영역을 찾았으면 클릭
                global clicking_in_progress
                clicking_in_progress = True
                try:
                    left, top, width, height = region
                    center_x = left + width // 2
                    center_y = top + height // 2
                    
                    # title 정중앙 더블클릭
                    pyautogui.click(center_x, center_y)
                    time.sleep(0.3)  # 더블클릭 간격
                    pyautogui.click(center_x, center_y)
                    time.sleep(0.3)  # 클릭 후 약간 대기
                    
                    # chatting_room_center 좌표 클릭
                    if not CHATTING_ROOM_CENTER or CHATTING_ROOM_CENTER == (0, 0):
                        return False
                    
                    x, y = CHATTING_ROOM_CENTER
                    pyautogui.click(x, y)
                    time.sleep(0.1)  # 클릭 후 약간 대기
                    return True
                finally:
                    clicking_in_progress = False
        except Exception as e:
            continue
    
    return False


def process_delay_queue(on_detect=None):
    """
    지연 큐를 주기적으로 확인하여 채팅방을 순차적으로 처리.
    - waiting 상태 채팅방들을 선입선출(FIFO)로 처리
    - pending 상태는 시간이 되면 waiting으로 변경
    - chatting_room 감시 중일 때는 대기
    
    Args:
        on_detect: 콜백 함수 (title_key, content)
    """
    global chatting_room_watching
    
    # 현재 처리 중인 채팅방 (순차 처리 보장)
    current_processing_title = None
    
    while True:
        try:
            current_time = time.time()
            
            # 현재 처리 중인 채팅방이 있으면 대기
            if current_processing_title:
                # 처리 중인 채팅방이 큐에서 제거되었는지 확인
                if current_processing_title not in DELAY_QUEUE:
                    current_processing_title = None
                time.sleep(0.5)
                continue
            
            # pending 상태 중 시간이 된 항목들을 waiting으로 변경
            for title, queue_item in DELAY_QUEUE.items():
                if queue_item["status"] == "pending" and current_time >= queue_item["scheduled_time"]:
                    set_queue_status(title, "waiting")
                    print(f"[queue] {title} pending → waiting 상태 변경")
            
            # waiting 상태 채팅방들을 선입선출로 정렬 (added_time 기준)
            waiting_titles = []
            for title, queue_item in DELAY_QUEUE.items():
                if queue_item["status"] == "waiting":
                    waiting_titles.append((title, queue_item.get("added_time", 0)))
            
            # added_time 기준으로 정렬 (오래된 것부터)
            waiting_titles.sort(key=lambda x: x[1])
            
            # waiting 상태 항목이 있고, chatting_room 감시 중이 아닐 때만 처리
            if waiting_titles and not chatting_room_watching:
                # 가장 오래된 waiting 항목 처리 (선입선출)
                title, _ = waiting_titles[0]
                
                # 처리 시작
                set_queue_status(title, "processing")
                current_processing_title = title
                print(f"[queue] {title} 처리 시작 (선입선출)")
                
                # 별도 스레드에서 처리
                import threading
                def process_in_thread():
                    global chatting_room_watching
                    nonlocal current_processing_title
                    
                    try:
                        # title2~title6 영역에서 해당 채팅방 찾아서 클릭
                        click_success = find_and_click_title_in_list(title)
                    except Exception as e:
                        print(f"[queue] {title} 클릭 중 오류: {e}")
                        click_success = False
                    
                    if click_success:
                        # 클릭 후 약간 대기 (채팅방이 열리는 시간)
                        time.sleep(0.5)
                        
                        # chatting_room_center 클릭 후 1회의 ctrl-A, ctrl-C로 복사
                        content = copy_chatting_room_content()
                        if content is not None:
                            # 딕셔너리에 저장 (key는 save_chatting_content에서 정제됨)
                            # 스케줄러 호출은 딕셔너리 변경 감지에서 처리
                            sanitized_title = save_chatting_content(title, content)
                            
                            # on_detect 콜백 호출 (처음 채팅방 내용을 복사했을 때)
                            if on_detect:
                                try:
                                    on_detect(sanitized_title, content)
                                except Exception as e:
                                    print(f"[queue] on_detect 콜백 호출 중 오류: {e}")
                            
                            # chatting_room 감시 시작 (별도 스레드)
                            chatting_room_watching = True  # 큐 처리 대기
                            thread_watch = threading.Thread(
                                target=watch_chatting_room,
                                args=(sanitized_title, on_detect),  # 정제된 title 사용
                                kwargs={"poll_interval": 0.1},
                                daemon=True
                            )
                            thread_watch.start()
                        else:
                            pass
                    else:
                        # 클릭 실패 시 큐에서 제거
                        remove_from_queue(title)
                        current_processing_title = None
                    
                    # 큐에서 제거는 finish 액션에서 수행 (성공한 경우)
                
                thread = threading.Thread(target=process_in_thread, daemon=True)
                thread.start()
            
            time.sleep(0.5)  # 0.5초마다 큐 확인
            
        except Exception as e:
            current_processing_title = None
            time.sleep(1.0)


# ---------------------
# 감시 중지 함수
# ---------------------

def stop_all_watching():
    """
    모든 감시를 중지합니다.
    - 채팅방 리스트 감시 중지
    - 채팅방 내부 감시 중지
    """
    global watch_stopped, chatting_room_watch_stopped
    watch_stopped = True
    chatting_room_watch_stopped = True


def resume_all_watching():
    """
    모든 감시를 재개합니다.
    - 채팅방 리스트 감시 재개
    - chatting_room 감시는 별도로 시작되어야 함
    """
    global watch_stopped
    watch_stopped = False


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

# chatting_room 감시 중인지 확인하는 플래그 (큐 처리 대기용)
chatting_room_watching = False

# 복사 진행 중 플래그 (CTRL-A, CTRL-C 진행 중 감지 방지)
copying_in_progress = False

# 클릭 진행 중 플래그 (모든 클릭 작업 중 감지 방지)
clicking_in_progress = False

# 지연 큐 (채팅방 클릭 지연 스케줄링)
# {title: {"scheduled_time": float, "status": str}}
# status: "pending", "waiting", "processing"
DELAY_QUEUE = {}


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
    클릭 진행 중일 때는 감지하지 않음.
    
    최적화: 해시 계산을 최소화하고, 변경이 없을 때는 즉시 반환.
    """
    global last_title_hash, last_preview_hash, clicking_in_progress
    
    # 클릭 진행 중이면 감지하지 않음
    if clicking_in_progress:
        return False

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

def get_region_image_text(region, min_confidence=0.3):
    """
    영역의 이미지를 OCR로 인식하여 텍스트를 반환.
    한글 인식 지원.
    
    Args:
        region: (left, top, width, height) 튜플
        min_confidence: 최소 신뢰도 (기본값 0.3)
    """
    if region is None:
        return None
    
    if not OCR_AVAILABLE:
        return None
    
    try:
        left, top, width, height = region
        
        # 영역 크기 검증
        if width <= 0 or height <= 0:
            return None
        
        # PIL ImageGrab으로 이미지 캡처
        img = ImageGrab.grab(bbox=(left, top, left + width, top + height))
        img_np = np.array(img)
        
        # EasyOCR은 numpy array를 직접 받을 수 있음
        reader = get_ocr_reader()
        if reader is None:
            return None
        
        results = reader.readtext(img_np)
        
        # OCR 결과에서 텍스트 추출 (공백 제거)
        text_parts = []
        for (bbox, text, confidence) in results:
            if confidence >= min_confidence:
                text_parts.append(text.strip())
        
        # 여러 텍스트를 공백으로 연결
        full_text = ' '.join(text_parts).strip()
        
        if not full_text:
            return None
        
        return full_text
    except Exception as e:
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
    복사 또는 클릭 진행 중일 때는 감지하지 않음.
    """
    global last_chatting_room_hash, copying_in_progress, clicking_in_progress
    
    # 복사 또는 클릭 진행 중이면 감지하지 않음
    if copying_in_progress or clicking_in_progress:
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
        title_key: title 텍스트 또는 해시 (딕셔너리 key로 사용, 정제됨)
        on_detect: 콜백 함수 (title_key, content)
        poll_interval: 폴링 간격 (초)
    """
    global chatting_room_watch_stopped, chatting_room_watching
    chatting_room_watch_stopped = False  # 감시 시작 시 플래그 초기화
    
    # key 정제: 초성, 영어, 숫자 제거
    sanitized_title_key = sanitize_dict_key(title_key)
    
    # 마지막 변경 시간 추적
    last_change_time = time.time()
    STALE_THRESHOLD = 8.0  # 5초 이상 변하지 않았을 때 체크
    
    while not chatting_room_watch_stopped:
        try:
            changed = trigger_chatting_room_changed()
            
            if changed:
                last_change_time = time.time()  # 변경 시간 업데이트
                
                # 채팅방 변화 감지 로그
                from datetime import datetime
                time_str = datetime.now().strftime("%H:%M:%S")
                log_message(f"[{time_str}] [채팅방 변화] {sanitized_title_key} 감지")
                
                # chatting_room_center 클릭 후 ctrl-A, ctrl-C로 복사
                content = copy_chatting_room_content()
                if content is not None:
                    # 딕셔너리 갱신만 (스케줄러 호출은 딕셔너리 변경 감지에서 처리)
                    save_chatting_content(sanitized_title_key, content)
                    
                    # on_detect 콜백 호출 (채팅방 변화 감지 시)
                    if on_detect:
                        try:
                            on_detect(sanitized_title_key, content)
                        except Exception as e:
                            print(f"[watch_chatting_room] on_detect 콜백 호출 중 오류: {e}")
            else:
                # 변경이 없을 때, 5초 이상 변하지 않았는지 체크
                current_time = time.time()
                time_since_last_change = current_time - last_change_time
                
                if time_since_last_change >= STALE_THRESHOLD:
                    last_change_time = current_time  # 체크 시간 업데이트 (중복 체크 방지)
                    
                    # chatting_room_center 클릭 후 ctrl-A, ctrl-C로 복사
                    content = copy_chatting_room_content()
                    if content is not None:
                        # 딕셔너리 갱신 (정제된 key 사용)
                        save_chatting_content(sanitized_title_key, content)
                        
                        # 마지막 발화자 추출
                        last_speaker = extract_last_speaker(content)
                        
                        # 마지막 발화자가 '이가을'이면 종료 처리
                        if last_speaker == "이가을":
                            try:
                                import schedular
                                schedular.process_finish_action(sanitized_title_key)
                            except Exception as e:
                                pass
                        else:
                            # 마지막 발화자가 '이가을'이 아니면 바로 제네레이터 호출 (스케줄러 거치지 않음)
                            try:
                                import generator
                                import threading
                                
                                def call_generator():
                                    generator.generate_chatting_room_update(
                                        title_key=sanitized_title_key,
                                        on_scheduler_callback=None  # 스케줄러 거치지 않음
                                    )
                                
                                generator_thread = threading.Thread(target=call_generator, daemon=True)
                                generator_thread.start()
                            except Exception as e:
                                pass
            
            time.sleep(poll_interval)
            
        except Exception as e:
            time.sleep(1.0)
    
    # chatting_room 감시 종료 시 플래그 해제하여 큐 처리 재개
    chatting_room_watching = False


# process_chatting_change 함수는 더 이상 사용되지 않음
# 모든 처리는 큐를 통해 process_delay_queue에서 수행됨
# def process_chatting_change(on_detect=None):
#     """이 함수는 더 이상 사용되지 않습니다. 큐 기반 처리로 변경되었습니다."""
#     pass


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
    - 변경 감지 시 title OCR 수행하여 PREVIEW_DICT에서 기존 채팅 내용 찾기
    - 마지막 발화 시간과 현재 시간 비교하여 2분 이상 차이나면 지연 큐에 추가
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
                        
                        # title/preview 픽셀 감지 로그
                        from datetime import datetime
                        time_str = datetime.now().strftime("%H:%M:%S")
                        log_message(f"[{time_str}] [픽셀 감지] title/preview 변경 감지")
                        
                        # 변경 감지 즉시 title OCR 수행 (채팅방 클릭 전)
                        title_text = get_current_title_text()
                        
                        if title_text:
                            # key 정제: 초성, 영어, 숫자 제거
                            sanitized_title = sanitize_dict_key(title_text)
                            
                            # 정제된 title로 PREVIEW_DICT에서 기존 채팅 내용 찾기
                            if sanitized_title in PREVIEW_DICT:
                                existing_content = PREVIEW_DICT[sanitized_title]
                                
                                # 마지막 발화 시간과 현재 시간 비교
                                is_delayed, time_diff = compare_message_time(existing_content, threshold_minutes=2)
                                
                                # 모든 변경을 큐에 추가 (이미 있으면 무시)
                                print(f"[watcher] {sanitized_title} 마지막 발화 시간과 {time_diff:.1f}초 차이, 큐에 추가")
                                add_to_delay_queue(sanitized_title, time_diff)
                            else:
                                # PREVIEW_DICT에 없으면 새 채팅방이므로 즉시 waiting 상태로 추가
                                print(f"[watcher] {sanitized_title} 새 채팅방, 즉시 waiting 상태로 큐 추가")
                                add_to_delay_queue(sanitized_title, 0.0)  # 시간 차이 0으로 추가

            time.sleep(poll_interval)

        except Exception as e:
            time.sleep(1.0)
