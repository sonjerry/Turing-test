import os
import time
import threading
import pyautogui
import pyperclip
from typing import Optional, Callable, Tuple

import macro
import schedular

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "macro_config.json")
PROMPT_PATH = os.path.join(BASE_DIR, "..", "프롬프트", "generator.txt")


def load_prompt(path: str = PROMPT_PATH) -> str:
    """프롬프트 파일을 읽어옴"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def calculate_send_delay(message: str) -> float:
    """
    메시지 길이에 따른 전송 버튼 클릭 후 지연 시간 계산
    짧은 메시지는 빠르게, 긴 메시지는 더 긴 지연
    """
    length = len(message)
    if length <= 10:
        return 0.3
    elif length <= 30:
        return 0.5
    elif length <= 50:
        return 0.7
    else:
        return 1.0


def calculate_input_delay(message: str) -> float:
    """
    메시지 길이에 따른 입력 전 지연 시간 계산
    두 번째 메시지부터 사용
    짧은 메시지는 짧은 딜레이, 긴 메시지는 긴 딜레이
    """
    length = len(message)
    if length <= 10:
        return 0.2
    elif length <= 30:
        return 0.4
    elif length <= 50:
        return 0.6
    elif length <= 100:
        return 0.8
    else:
        return 1.2


def send_message(message: str, chat_input_coord: tuple, send_button_coord: tuple) -> bool:
    """
    단일 메시지를 전송
    1. 채팅입력칸 클릭
    2. 메시지를 클립보드에 복사 후 ctrl-V로 붙여넣기
    3. 전송버튼 클릭
    4. 지연 시간 적용
    
    Returns:
        성공 여부
    """
    # 채팅 입력 중 픽셀 검사 방지를 위한 플래그 설정
    macro.clicking_in_progress = True
    try:
        x_input, y_input = chat_input_coord
        x_send, y_send = send_button_coord
        
        # 채팅입력칸 클릭
        pyautogui.click(x_input, y_input)
        time.sleep(0.2)
        
        # 기존 내용 선택 및 삭제 (혹시 모를 기존 텍스트 제거)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.05)
        
        # 메시지를 클립보드에 복사
        pyperclip.copy(message)
        time.sleep(0.05)
        
        # ctrl-V로 붙여넣기
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.1)
        
        # 입력 완료 후 전송 버튼 클릭 전 1초 딜레이
        time.sleep(1.0)
        
        # 전송버튼 클릭
        pyautogui.click(x_send, y_send)
        
        # 메시지 길이에 따른 지연
        delay = calculate_send_delay(message)
        time.sleep(delay)
        
        return True
    except Exception as e:
        return False
    finally:
        # 채팅 입력 완료 후 플래그 해제
        macro.clicking_in_progress = False


def check_chatting_room_changed(before_content: str) -> Tuple[bool, Optional[str]]:
    """
    전송 완료 후 chatting_room 내용 변경 여부 확인
    제네레이터가 입력한 메시지들 사이에 상대방 발화가 있었는지 체크
    
    chatting_room_center 클릭 후 ctrl-A, ctrl-C로 내용 복사하여
    전송 전 내용과 비교하여 상대방 발화 여부 확인
    
    Returns:
        (변경 감지 여부, 현재 내용)
        - changed: True면 전송 중 상대방 발화가 있었음
    """
    try:
        current_content = macro.copy_chatting_room_content()
        if current_content is None:
            return False, None
        
        # 전송 전 내용과 전송 후 내용 비교
        # 내용이 다르면 제네레이터가 입력한 메시지들 사이에 상대방 발화가 있었던 것
        changed = (current_content != before_content)
        return changed, current_content
    except Exception as e:
        return False, None


def call_generator_api(
    title_key: str,
    message_context: str,
    relationship: str = "FRIEND",
    model_name: str = "gpt-5.1"  # fine-tuning 모델 이름 (예시)
) -> Optional[str]:
    """
    OpenAI API를 호출하여 제네레이터 응답을 받음
    
    Args:
        title_key: 채팅방 제목
        message_context: 채팅 내용 (PREVIEW_DICT에서 가져온 값)
        relationship: 관계 유형 (FAMILY / CLOSE_FRIEND / FRIEND / STRANGER / GROUP_MIXED)
        model_name: fine-tuning된 모델 이름
    
    Returns:
        생성된 메시지 문자열 (<split> 태그 포함 가능)
    """
    if not macro.OPENAI_AVAILABLE:
        return None
    
    client = macro.get_openai_client()
    if not client:
        return None
    
    prompt = load_prompt()
    if not prompt:
        return None
    
    current_time = macro.format_korean_time()
    
    # 프롬프트에 입력 정보 추가
    user_message = f"""TIME: {current_time}
RELATIONSHIP: {relationship}

MESSAGE_CONTEXT:
{message_context}

위 정보를 바탕으로 이가을의 응답 메시지를 생성하세요."""

    # API로 보낼 입력을 그대로 로그로 출력
    print(f"[generator] [{title_key}] 요청 메시지:\n{user_message}")
    
    
    try:
        response = client.chat.completions.create(
            model="ft:gpt-4.1-mini-2025-04-14:personal:generator-gpt4-1mini:CkpPWFZH",  # fine-tuning된 모델
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            max_completion_tokens=500
        )
        
        if not response or not response.choices:
            return None
        
        response_text = response.choices[0].message.content
        
        return response_text
        
    except Exception as e:
        return None


def send_messages_with_split_check(
    messages: list[str],
    title_key: str,
    chat_input_coord: tuple,
    send_button_coord: tuple,
    before_content: str
) -> Tuple[bool, Optional[str], bool]:
    """
    <split>으로 분할된 메시지들을 순차적으로 전송
    모든 입력 완료 후 한 번만 chatting_room 변경 체크
    (제네레이터가 입력한 메시지들 사이에 상대방 발화가 있었는지 확인)
    
    Args:
        messages: 전송할 메시지 리스트
        title_key: 채팅방 제목
        chat_input_coord: 채팅입력칸 좌표 (x, y)
        send_button_coord: 전송버튼 좌표 (x, y)
        before_content: 전송 시작 전 chatting_room 내용
    
    Returns:
        (성공 여부, 최종 chatting_room 내용, 변경 감지 여부)
        - changed: True면 전송 중 상대방 발화가 있었음
    """
    # 채팅방 감시 중지
    macro.chatting_room_watching = True
    
    try:
        # 모든 메시지 전송
        for i, message in enumerate(messages):
            message = message.strip()
            if not message:
                continue
            
            # 두 번째 메시지부터는 메시지 길이에 따른 딜레이 부여
            if i > 0:
                delay = calculate_input_delay(message)
                print(f"[generator] 두 번째 메시지부터 딜레이 적용: {delay}초 (메시지 길이: {len(message)} 문자)")
                time.sleep(delay)
            
            # 메시지 전송
            success = send_message(message, chat_input_coord, send_button_coord)
            if not success:
                continue
        
        # 전송 완료 후 chatting_room_center 클릭 후 ctrl-A, ctrl-C로 변경 체크
        # 제네레이터가 입력한 메시지들 사이에 상대방 발화가 있었는지 1회 체크
        time.sleep(0.5)  # 마지막 전송 후 대기
        changed, final_content = check_chatting_room_changed(before_content)
        
        return True, final_content, changed
        
    finally:
        # 채팅방 감시 재개
        macro.chatting_room_watching = False


def generate_and_send_message(
    title_key: str,
    on_scheduler_callback: Optional[Callable[[str, str], None]] = None
):
    """
    제네레이터를 호출하여 메시지를 생성하고 전송
    전송 완료 후 상대방 발화 여부를 확인하여 스케줄러 재호출
    스케줄러의 태그가 <INSTANT>일 때만 제네레이터가 호출됨
    
    Args:
        title_key: 채팅방 제목
        on_scheduler_callback: 스케줄러 호출 콜백 (title_key, content)
    """
    if title_key not in macro.PREVIEW_DICT:
        print(f"[generator] [{title_key}] PREVIEW_DICT에 내용이 없습니다.")
        return
    
    message_context = macro.PREVIEW_DICT[title_key]
    
    # 날짜 줄 제거
    message_context = macro.remove_date_header(message_context)
    
    # 관계 유형 결정
    relationship = macro.get_chat_relationship_tag(title_key)
    
    # 전송 시작 전 chatting_room 내용 저장
    before_content = macro.copy_chatting_room_content()
    if before_content is None:
        return
    
    # 설정 파일에서 좌표 읽기
    config = macro.load_config_dict(CONFIG_PATH)
    chat_input = config.get("chat_input", [1000, 800])
    send_button = config.get("send_button", [1500, 800])
    
    if len(chat_input) != 2 or len(send_button) != 2:
        return
    
    chat_input_coord = tuple(chat_input)
    send_button_coord = tuple(send_button)
    
    # OpenAI API 호출하여 메시지 생성
    response_text = call_generator_api(
        title_key=title_key,
        message_context=message_context,
        relationship=relationship
    )
    
    if not response_text:
        return
    
    # <split> 태그로 메시지 분할
    messages = [msg.strip() for msg in response_text.split("<split>") if msg.strip()]
    
    if not messages:
        return
    
    # 제네레이터 메시지 반환 로그
    from datetime import datetime
    time_str = datetime.now().strftime("%H:%M:%S")
    message_preview = messages[0][:30] + "..." if len(messages[0]) > 30 else messages[0]
    if len(messages) > 1:
        macro.log_message(f"[{time_str}] [제네레이터] {title_key}: {message_preview} (총 {len(messages)}개 메시지)")
    else:
        macro.log_message(f"[{time_str}] [제네레이터] {title_key}: {message_preview}")
    
    # 메시지 전송
    success, final_content, changed = send_messages_with_split_check(
        messages=messages,
        title_key=title_key,
        chat_input_coord=chat_input_coord,
        send_button_coord=send_button_coord,
        before_content=before_content
    )
    
    if not success or final_content is None:
        return
    
    # 마지막 발화자 확인
    last_speaker = macro.extract_last_speaker(final_content)
    
    # 상대방 발화가 있었거나, 마지막 발화가 이가을이 아니면 스케줄러 호출
    # changed: 제네레이터가 입력한 메시지들 사이에 상대방 발화가 있었는지 여부
    # last_speaker != "이가을": 마지막 발화자가 상대방인 경우
    should_recall = changed or (last_speaker != "이가을")
    
    # PREVIEW_DICT 갱신 (콜백 호출은 skip_callback으로 막음)
    # 스케줄러 호출은 should_recall 조건일 때만 수행
    macro.save_chatting_content(title_key, final_content, skip_callback=True)
    
    if should_recall:
        # 상대방 발화가 있었거나 상대방이 마지막 발화자인 경우 스케줄러 호출
        if on_scheduler_callback:
            try:
                on_scheduler_callback(title_key, final_content)
            except Exception as e:
                print(f"[generator] [ERROR] 스케줄러 콜백 호출 중 오류: {e}")
                import traceback
                traceback.print_exc()
    else:
        # 마지막 발화자가 나(이가을)이고 상대방 발화가 없었으면 8초 동안 감시 후 finish 액션 실행
        def watch_and_finish():
            watch_duration = 8.0
            check_interval = 0.1
            start_time = time.time()
            last_content = final_content
            
            while time.time() - start_time < watch_duration:
                # PREVIEW_DICT에서 변경 감지 (watch_chatting_room이 갱신했을 수 있음)
                if title_key in macro.PREVIEW_DICT:
                    current_content = macro.PREVIEW_DICT[title_key]
                    
                    # 내용이 변경되었는지 확인
                    if current_content != last_content:
                        # 상대방이 메시지를 보냈으므로 스케줄러 재호출
                        if on_scheduler_callback:
                            try:
                                on_scheduler_callback(title_key, current_content)
                            except Exception as e:
                                pass
                        return
                
                time.sleep(check_interval)
            
            # 8초 동안 변경이 없었으면 finish 액션 실행
            try:
                import schedular
                schedular.process_finish_action(title_key)
            except Exception as e:
                pass
        
        finish_thread = threading.Thread(target=watch_and_finish, daemon=True)
        finish_thread.start()


def generate_chatting_room_update(
    title_key: str,
    on_scheduler_callback: Optional[Callable[[str, str], None]] = None
):
    """
    chatting_room이 업데이트될 때마다 호출되는 함수
    PREVIEW_DICT에서 해당 title_key의 내용을 가져와서 제네레이터 호출
    
    Args:
        title_key: 채팅방 제목
        on_scheduler_callback: 스케줄러 호출 콜백 (title_key, content)
    """
    if title_key not in macro.PREVIEW_DICT:
        return
    
    generate_and_send_message(
        title_key=title_key,
        on_scheduler_callback=on_scheduler_callback
    )

