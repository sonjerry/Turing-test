import os
import time
from typing import Optional, Callable

import macro

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "macro_config.json")
PROMPT_PATH = os.path.join(BASE_DIR, "..", "프롬프트", "schedular.txt")


def load_prompt(path: str = PROMPT_PATH) -> str:
    """프롬프트 파일을 읽어옴"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


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

    else:
        # 태그를 찾을 수 없으면 기본값
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
    print(f"[scheduler] call_scheduler_api 시작")
    print(f"[scheduler]   - title_key: {title_key}")
    print(f"[scheduler]   - relationship: {relationship}")
    print(f"[scheduler]   - message_context 길이: {len(message_context)} 문자")
    print(f"[scheduler]   - on_response 콜백 존재: {on_response is not None}")
    
    if not macro.OPENAI_AVAILABLE:
        print(f"[scheduler] [ERROR] OPENAI_AVAILABLE = False")
        return None
    
    client = macro.get_openai_client()
    if not client:
        print(f"[scheduler] [ERROR] OpenAI 클라이언트를 가져올 수 없음")
        return None
    print(f"[scheduler]   - OpenAI 클라이언트 획득 성공")
    
    prompt = load_prompt()
    if not prompt:
        print(f"[scheduler] [ERROR] 프롬프트를 로드할 수 없음")
        return None
    print(f"[scheduler]   - 프롬프트 로드 성공, 길이: {len(prompt)} 문자")
    
    current_time = macro.format_korean_time()
    print(f"[scheduler]   - 현재 시간: {current_time}")
    
    # 프롬프트에 입력 정보 추가
    user_message = f"""TIME: {current_time}
RELATIONSHIP: {relationship}

MESSAGE_CONTEXT:
{message_context}"""
    
    # user_message 로그 출력
    print("[scheduler] user_message:")
    print("=" * 80)
    print(user_message)
    print("=" * 80)
    
    try:
        print(f"[scheduler] OpenAI API 호출 시작 (model: gpt-5-mini)")
        response = client.chat.completions.create(
            model="gpt-5-mini",  # 또는 "gpt-4", "gpt-3.5-turbo" 등
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            max_completion_tokens=50
        )
        print(f"[scheduler] OpenAI API 호출 완료")
        
        if not response or not response.choices:
            print(f"[scheduler] [ERROR] 응답이 없거나 choices가 비어있음")
            return None
        
        response_text = response.choices[0].message.content
        print(f"[scheduler]   - 원본 응답 텍스트: {response_text}")
        
        tag = parse_response(response_text)
        print(f"[scheduler] [{title_key}] 파싱된 태그: {tag}")
        
        # 스케줄러 태그 반환 로그 (<WAIT>, <INSTANT>만)
        if tag in ["<WAIT>", "<INSTANT>"]:
            from datetime import datetime
            time_str = datetime.now().strftime("%H:%M:%S")
            macro.log_message(f"[{time_str}] [스케줄러] {title_key}: {tag}")
        
        # 콜백 호출 (무조건 실행)
        if on_response:
            try:
                print(f"[scheduler] [{title_key}] 콜백 호출 시작: tag={tag}")
                on_response(tag)
                print(f"[scheduler] [{title_key}] 콜백 호출 완료: {tag}")
            except Exception as e:
                print(f"[scheduler] [{title_key}] [ERROR] 콜백 호출 중 오류 발생: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[scheduler] [{title_key}] [WARNING] on_response 콜백이 None입니다")
        
        return tag
        
    except Exception as e:
        print(f"[scheduler] [{title_key}] API 호출 중 오류 발생: {e}")
        # 예외 발생 시에도 콜백 호출 시도 (태그는 None 또는 기본값)
        if on_response:
            try:
                on_response("<WAIT>")
                print(f"[scheduler] [{title_key}] 예외 발생 후 기본 태그 콜백 호출")
            except Exception as callback_error:
                print(f"[scheduler] [{title_key}] 예외 후 콜백 호출 중 오류: {callback_error}")
        return None


def process_finish_action(title_key: str = None):
    """
    <FINISH> 태그가 반환되었을 때 실행할 액션
    1. config의 finish 좌표 클릭
    2. 채팅방 감시 종료
    3. title/preview 감시 재개
    4. 큐에서 해당 채팅방 제거 (title_key가 제공된 경우)
    
    Args:
        title_key: 채팅방 제목 (큐에서 제거하기 위해 필요)
    """
    config = macro.load_config_dict(CONFIG_PATH)
    finish_coord = config.get("finish")
    
    if not finish_coord or len(finish_coord) != 2:
        return
    
    import pyautogui
    x, y = finish_coord
    
    # finish 좌표 클릭
    pyautogui.click(x, y)
    time.sleep(0.5)
    
    # 채팅방 감시 종료
    macro.chatting_room_watch_stopped = True
    macro.chatting_room_watching = False  # 큐 처리 재개
    
    # 큐에서 해당 채팅방 제거
    if title_key:
        macro.remove_from_queue(title_key)


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
    print(f"[scheduler] schedule_chatting_room_update 호출됨")
    print(f"[scheduler]   - title_key: {title_key}")
    print(f"[scheduler]   - on_tag_received 콜백 존재: {on_tag_received is not None}")
    print(f"[scheduler]   - PREVIEW_DICT에 title_key 존재: {title_key in macro.PREVIEW_DICT}")
    
    if title_key not in macro.PREVIEW_DICT:
        print(f"[scheduler] [ERROR] title_key가 PREVIEW_DICT에 없음: {title_key}")
        print(f"[scheduler]   - PREVIEW_DICT의 키 목록: {list(macro.PREVIEW_DICT.keys())[:5]}...")
        return
    
    message_context = macro.PREVIEW_DICT[title_key]
    print(f"[scheduler]   - message_context 길이: {len(message_context)} 문자")
    print(f"[scheduler]   - message_context 미리보기: {message_context[:100]}...")
    
    # 날짜 줄 제거
    message_context_before = len(message_context)
    message_context = macro.remove_date_header(message_context)
    message_context_after = len(message_context)
    print(f"[scheduler]   - 날짜 줄 제거 후 길이: {message_context_before} -> {message_context_after} 문자")
    
    # 관계 유형 결정
    relationship = macro.get_chat_relationship_tag(title_key)
    print(f"[scheduler]   - relationship: {relationship}")
    
    # API 호출
    print(f"[scheduler] call_scheduler_api 호출 시작...")
    received_tag = [None]  # 콜백에서 받은 태그를 저장하기 위한 리스트
    
    def ensure_callback(tag_value):
        """콜백이 확실히 호출되도록 보장하는 래퍼"""
        print(f"[scheduler] ensure_callback 호출됨: tag={tag_value}")
        received_tag[0] = tag_value
        _handle_tag_response(tag_value, on_tag_received)
    
    tag = call_scheduler_api(
        title_key=title_key,
        message_context=message_context,
        relationship=relationship,
        on_response=ensure_callback
    )
    print(f"[scheduler] call_scheduler_api 호출 완료, 반환된 tag: {tag}")
    print(f"[scheduler] 콜백에서 받은 tag: {received_tag[0]}")
    
    # 태그가 있으면 무조건 콜백 호출 (이중 보장)
    final_tag = tag or received_tag[0]
    if final_tag and final_tag in ["<WAIT>", "<INSTANT>", "<FINISH>"]:
        print(f"[scheduler] 최종 태그 확인: {final_tag}, 콜백 재호출 보장")
        if on_tag_received:
            try:
                on_tag_received(final_tag)
                print(f"[scheduler] 최종 태그 콜백 호출 완료: {final_tag}")
            except Exception as e:
                print(f"[scheduler] [ERROR] 최종 태그 콜백 호출 중 오류: {e}")
                import traceback
                traceback.print_exc()
    
    if tag == "<FINISH>":
        print(f"[scheduler] <FINISH> 태그 감지, process_finish_action 호출")
        process_finish_action(title_key)


def _handle_tag_response(tag: str, on_tag_received: Optional[Callable[[str], None]]):
    """태그 응답 처리"""
    print(f"[scheduler] _handle_tag_response 호출됨")
    print(f"[scheduler]   - tag: {tag}")
    print(f"[scheduler]   - on_tag_received 콜백 존재: {on_tag_received is not None}")
    
    if on_tag_received:
        try:
            print(f"[scheduler] on_tag_received 콜백 호출 시작")
            on_tag_received(tag)
            print(f"[scheduler] _handle_tag_response 콜백 호출 완료")
        except Exception as e:
            print(f"[scheduler] [ERROR] _handle_tag_response 콜백 호출 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[scheduler] [WARNING] on_tag_received 콜백이 None입니다 - GUI 업데이트 불가능")
