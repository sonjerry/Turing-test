import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from openai import OpenAI

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None
    print("[warning] openai 라이브러리가 설치되지 않았습니다. pip install openai로 설치하세요.")

import macro

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "macro_config.json")
PROMPT_PATH = os.path.join(BASE_DIR, "..", "프롬프트", "schedular.txt")


def load_prompt(path: str = PROMPT_PATH) -> str:
    """프롬프트 파일을 읽어옴"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[error] 프롬프트 파일 로드 실패: {e}")
        return ""


def load_config(path: str = CONFIG_PATH) -> Dict:
    """설정 파일에서 finish 좌표 등을 읽어옴"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[error] 설정 파일 로드 실패: {e}")
    return {}


def get_openai_client():
    """OpenAI 클라이언트 생성 (환경 변수에서 API 키 읽기)"""
    if not OPENAI_AVAILABLE:
        return None
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[error] OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        return None
    
    return OpenAI(api_key=api_key)


def format_korean_time(dt=None) -> str:
    """현재 시간을 '오전 11:59' 형태로 반환"""
    if dt is None:
        dt = datetime.now()
    
    hour = dt.hour
    minute = dt.minute
    
    ampm = "오전" if hour < 12 else "오후"
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
    
    return f"{ampm} {hour_12}:{minute:02d}"


def parse_response(response_text: str) -> str:
    """
    OpenAI 응답에서 태그 추출
    <INSTANT>, <WAIT>, <FINISH> 중 하나를 반환
    """
    response_text = response_text.strip()
    
    # 태그 패턴 매칭
    if "<INSTANT>" in response_text:
        return "<INSTANT>"
    elif "<WAIT>" in response_text:
        return "<WAIT>"
    elif "<FINISH>" in response_text:
        return "<FINISH>"
    else:
        # 태그를 찾을 수 없으면 기본값
        print(f"[warning] 응답에서 태그를 찾을 수 없습니다: {response_text}")
        return "<WAIT>"


def call_scheduler_api(
    title_key: str,
    message_context: str,
    relationship: str = "FRIEND",
    on_response: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    """
    OpenAI API를 호출하여 스케줄러 응답을 받음
    
    Args:
        title_key: 채팅방 제목
        message_context: 채팅 내용 (PREVIEW_DICT에서 가져온 값)
        relationship: 관계 유형 (FAMILY / CLOSE_FRIEND / FRIEND / STRANGER / GROUP_MIXED)
        on_response: 응답을 받았을 때 호출할 콜백 함수 (태그 문자열)
    
    Returns:
        태그 문자열 (<INSTANT>, <WAIT>, <FINISH> 중 하나)
    """
    if not OPENAI_AVAILABLE:
        print("[error] OpenAI 라이브러리를 사용할 수 없습니다.")
        return None
    
    client = get_openai_client()
    if not client:
        return None
    
    prompt = load_prompt()
    if not prompt:
        print("[error] 프롬프트를 로드할 수 없습니다.")
        return None
    
    current_time = format_korean_time()
    
    # 프롬프트에 입력 정보 추가
    user_message = f"""RELATIONSHIP: {relationship}

TIME: {current_time}

MESSAGE_CONTEXT:
{message_context}

위 정보를 바탕으로 발화 타이밍을 결정하세요."""
    
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",  # 또는 "gpt-4", "gpt-3.5-turbo" 등
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=50
        )
        
        response_text = response.choices[0].message.content
        tag = parse_response(response_text)
        
        print(f"[scheduler] [{title_key}] 응답: {tag}")
        
        # 콜백 호출
        if on_response:
            try:
                on_response(tag)
            except Exception as e:
                print(f"[error] on_response 콜백 오류: {e}")
        
        return tag
        
    except Exception as e:
        print(f"[error] OpenAI API 호출 실패: {e}")
        return None


def process_finish_action():
    """
    <FINISH> 태그가 반환되었을 때 실행할 액션
    1. config의 finish 좌표 클릭
    2. 채팅방 감시 종료
    3. title/preview 감시 재개
    """
    config = load_config()
    finish_coord = config.get("finish")
    
    if not finish_coord or len(finish_coord) != 2:
        print("[error] finish 좌표가 설정되지 않았습니다.")
        return
    
    import pyautogui
    x, y = finish_coord
    
    # finish 좌표 클릭
    pyautogui.click(x, y)
    print(f"[scheduler] finish 좌표 클릭: ({x}, {y})")
    time.sleep(0.5)
    
    # 채팅방 감시 종료
    macro.chatting_room_watch_stopped = True
    print("[scheduler] chatting_room 감시 종료됨")
    
    # title/preview 감시 재개 (watch_stopped 플래그 해제)
    macro.watch_stopped = False
    print("[scheduler] title/preview 감시 재개됨")


def schedule_chatting_room_update(
    title_key: str,
    on_tag_received: Optional[Callable[[str], None]] = None
):
    """
    chatting_room이 업데이트될 때마다 호출되는 함수
    PREVIEW_DICT에서 해당 title_key의 내용을 가져와서 API 호출
    
    Args:
        title_key: 채팅방 제목
        on_tag_received: 태그를 받았을 때 호출할 콜백 (태그 문자열)
    """
    if title_key not in macro.PREVIEW_DICT:
        print(f"[scheduler] [{title_key}] PREVIEW_DICT에 내용이 없습니다.")
        return
    
    message_context = macro.PREVIEW_DICT[title_key]
    
    # 관계 유형 결정 (기본값: FRIEND, 추후 확장 가능)
    relationship = "FRIEND"
    
    # API 호출
    tag = call_scheduler_api(
        title_key=title_key,
        message_context=message_context,
        relationship=relationship,
        on_response=lambda t: _handle_tag_response(t, on_tag_received)
    )
    
    if tag == "<FINISH>":
        process_finish_action()


def _handle_tag_response(tag: str, on_tag_received: Optional[Callable[[str], None]]):
    """태그 응답 처리"""
    if on_tag_received:
        try:
            on_tag_received(tag)
        except Exception as e:
            print(f"[error] on_tag_received 콜백 오류: {e}")
