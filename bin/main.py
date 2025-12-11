# OpenMP 중복 초기화 오류 해결
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import threading
import time
import tkinter as tk
from tkinter import ttk

import macro
import gui  # PreviewStackgui 사용
import schedular
import generator

# 키보드 입력 감지용
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False



def main():
    # ----------------------------
    # Tk 루트 + gui.PreviewStackgui 생성
    # ----------------------------
    root = tk.Tk()
    root.title("매크로")

    style = ttk.Style()
    style.configure("TitleButton.TButton", font=("맑은 고딕", 10, "bold"))

    # 좌우 split + PREVIEW_DICT 뷰어 / 예외 리스트 관리
    app = gui.PreviewStackGUI(root)
    
    # 창 크기 및 위치 설정: 화면 너비의 1/5, 오른쪽에 고정 배치
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    # 창 너비를 화면 너비의 1/5로 설정
    window_width = screen_width // 5
    # 창 높이는 화면 높이의 90%로 설정 (잘리지 않게)
    window_height = int(screen_height * 0.9)
    
    # 오른쪽에 배치 (x 좌표: 화면 너비 - 창 너비)
    x = screen_width - window_width
    # 상단에서 약간 아래로 배치 (화면 높이의 5%)
    y = int(screen_height * 0.05)
    
    # 창 크기와 위치 설정
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    # 창 크기 조정 비활성화 (위치 고정)
    root.resizable(False, False)

    # ----------------------------
    # 하단 로그 영역 (title / time / preview 출력)
    # ----------------------------
    log_frame = ttk.Frame(root)
    log_frame.pack(side="bottom", fill="both", expand=True)

    log_label = ttk.Label(log_frame, text="캡쳐 로그", font=("맑은 고딕", 10, "bold"))
    log_label.pack(anchor="w", padx=6, pady=(4, 0))

    log_text = tk.Text(log_frame, height=15, state="disabled")
    log_scroll = ttk.Scrollbar(
        log_frame, orient="vertical", command=log_text.yview
    )
    log_text.configure(yscrollcommand=log_scroll.set)

    log_text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 6))
    log_scroll.pack(side="right", fill="y", padx=(0, 6), pady=(0, 6))

    def append_log_line(line: str):
        log_text.configure(state="normal")
        log_text.insert("end", line + "\n")
        log_text.see("end")
        log_text.configure(state="disabled")
    
    # 로그 콜백 설정 (다른 모듈에서 사용 가능하도록)
    macro.set_log_callback(lambda msg: root.after(0, lambda: append_log_line(msg)))

    # ----------------------------
    # 캡쳐 감지 시 로그 처리
    # ----------------------------

    def _log_detection(title_key, content):
        """
        실제 로그 찍는 함수 (메인 스레드에서 실행)
        title_key: title 영역의 이미지 해시 또는 실제 title
        content: 복사된 채팅 내용
        """
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M:%S")
        
        # content의 앞부분만 미리보기로 표시 (너무 길면 잘라서)
        preview = content[:50] + "..." if len(content) > 50 else content
        
        line = f"[{time_str}] [{title_key[:8]}...] 내용 저장됨 (길이: {len(content)} 문자)"
        print(line)
        append_log_line(line)

    def on_detect(title_key, content):
        # 마찬가지로 메인 스레드에서 UI 갱신하도록 after 사용
        root.after(0, lambda tk=title_key, c=content: _log_detection(tk, c))
        
        # 제네레이터 호출을 위한 콜백 함수들 정의
        def on_scheduler_callback(tk, c):
            # 스케줄러 재호출 콜백
            print(f"[main] on_scheduler_callback 호출됨 (재호출)")
            print(f"[main]   - title_key: {tk}")
            
            def scheduler_inner():
                print(f"[main] scheduler_inner 스레드 시작 (재호출)")
                def on_tag_received_inner(tag):
                    print(f"[main] on_tag_received_inner 호출됨: tag={tag}")
                    # 태그가 <WAIT> 또는 <INSTANT>인 경우 무조건 GUI 업데이트
                    if tag in ["<WAIT>", "<INSTANT>", "<FINISH>"]:
                        # 메인 스레드에서 GUI 업데이트
                        def update_gui():
                            print(f"[main] update_gui 실행됨 (재호출): tag={tag}")
                            try:
                                app.update_tag(tag)
                                print(f"[main] app.update_tag 호출 완료 (재호출)")
                            except Exception as e:
                                print(f"[main] [ERROR] GUI 업데이트 중 오류 (재호출): {e}")
                                import traceback
                                traceback.print_exc()
                        root.after(0, update_gui)
                        # 추가 보장: after_idle도 사용
                        root.after_idle(update_gui)
                        print(f"[main] GUI 업데이트 스케줄됨: tag={tag}")
                    else:
                        print(f"[main] [WARNING] 알 수 없는 태그 (재호출): {tag}")
                    # <INSTANT> 태그일 때만 제네레이터 호출
                    if tag == "<INSTANT>":
                        call_generator_inner(tk, c)
                print(f"[main] schedule_chatting_room_update 재호출 예정: title_key={tk}")
                schedular.schedule_chatting_room_update(
                    title_key=tk,
                    on_tag_received=on_tag_received_inner
                )
                print(f"[main] schedule_chatting_room_update 재호출 완료")
            scheduler_thread = threading.Thread(target=scheduler_inner, daemon=True)
            scheduler_thread.start()
            print(f"[main] 스케줄러 재호출 스레드 시작됨")
        
        def call_generator_inner(tk, c):
            # 제네레이터 호출 함수
            generator_thread = threading.Thread(
                target=lambda: generator.generate_chatting_room_update(
                    title_key=tk,
                    on_scheduler_callback=on_scheduler_callback
                ),
                daemon=True
            )
            generator_thread.start()
        
        # 딕셔너리 변경 감지 시 스케줄러 호출
        def on_dict_change(tk, c):
            print(f"[main] on_dict_change 호출됨")
            print(f"[main]   - title_key: {tk}")
            print(f"[main]   - content 길이: {len(c)} 문자")
            
            # 스케줄러 호출 전에 GUI 태그를 instant로 설정
            def set_instant_tag():
                try:
                    app.update_tag("<INSTANT>")
                    print(f"[main] 스케줄러 호출 전 GUI 태그를 <INSTANT>로 설정")
                except Exception as e:
                    print(f"[main] [ERROR] GUI 태그 설정 중 오류: {e}")
            root.after(0, set_instant_tag)
            
            def call_scheduler():
                print(f"[main] call_scheduler 스레드 시작")
                def on_tag_received(tag):
                    print(f"[main] on_tag_received 호출됨: tag={tag}")
                    # 태그가 <WAIT> 또는 <INSTANT>인 경우 무조건 GUI 업데이트
                    if tag in ["<WAIT>", "<INSTANT>", "<FINISH>"]:
                        # 메인 스레드에서 GUI 업데이트
                        def update_gui():
                            print(f"[main] update_gui 실행됨: tag={tag}")
                            try:
                                app.update_tag(tag)
                                print(f"[main] app.update_tag 호출 완료: tag={tag}")
                                # <INSTANT> 태그인 경우 추가 확인
                                if tag == "<INSTANT>":
                                    # 잠시 후 다시 확인하여 확실히 적용되도록
                                    def verify_instant():
                                        current_tag = app.current_tag
                                        print(f"[main] <INSTANT> 태그 확인: 현재 활성 태그={current_tag}")
                                        if current_tag != "<INSTANT>":
                                            print(f"[main] [WARNING] <INSTANT> 태그가 덮어씌워짐! 다시 적용...")
                                            app.update_tag("<INSTANT>")
                                    root.after(100, verify_instant)  # 100ms 후 확인
                            except Exception as e:
                                print(f"[main] [ERROR] GUI 업데이트 중 오류: {e}")
                                import traceback
                                traceback.print_exc()
                        root.after(0, update_gui)
                        # 추가 보장: after_idle도 사용
                        root.after_idle(update_gui)
                        print(f"[main] GUI 업데이트 스케줄됨: tag={tag}")
                    else:
                        print(f"[main] [WARNING] 알 수 없는 태그: {tag}")
                    
                    # <INSTANT> 태그일 때만 제네레이터 호출
                    if tag == "<INSTANT>":
                        print(f"[main] 스케줄러 태그가 <INSTANT>이므로 제네레이터 호출")
                        # 제네레이터 호출 전에 GUI 업데이트가 완료되도록 약간의 딜레이
                        def call_generator_delayed():
                            time.sleep(0.1)  # GUI 업데이트가 완료되도록 대기
                            call_generator_inner(tk, c)
                        generator_delay_thread = threading.Thread(target=call_generator_delayed, daemon=True)
                        generator_delay_thread.start()
                
                print(f"[main] schedule_chatting_room_update 호출 예정: title_key={tk}")
                schedular.schedule_chatting_room_update(
                    title_key=tk,
                    on_tag_received=on_tag_received
                )
                print(f"[main] schedule_chatting_room_update 호출 완료")
            
            # 별도 스레드에서 schedular 호출 (API 호출이 블로킹될 수 있음)
            print(f"[main] 스케줄러 호출 스레드 생성 및 시작")
            scheduler_thread = threading.Thread(target=call_scheduler, daemon=True)
            scheduler_thread.start()
            print(f"[main] 스케줄러 호출 스레드 시작됨")
        
        # 딕셔너리 변경 감지 콜백 설정
        macro.set_dict_change_callback(on_dict_change)

    # ----------------------------
    # OCR 초기화
    # ----------------------------
    if macro.OCR_AVAILABLE:
        macro.initialize_ocr()
    
    # ----------------------------
    # 프로그램 시작 5초 대기 후 감시 시작
    # ----------------------------
    def start_watcher_after_delay():
        time.sleep(5.0)
        print("[main] 감시 시작")
        watcher_thread = threading.Thread(
            target=macro.watcher_loop,
            kwargs={
                "on_detect": on_detect,
                # cooldown, poll_interval은 macro 기본값 사용
            },
            daemon=True,
        )
        watcher_thread.start()
        
        # 지연 큐 처리 스레드 시작
        queue_thread = threading.Thread(
            target=macro.process_delay_queue,
            kwargs={
                "on_detect": on_detect,
            },
            daemon=True,
        )
        queue_thread.start()
        print("[main] 지연 큐 처리 스레드 시작")
    
    # 별도 스레드에서 5초 대기 후 감시 시작 (GUI 블로킹 방지)
    delay_thread = threading.Thread(target=start_watcher_after_delay, daemon=True)
    delay_thread.start()

    # ----------------------------
    # 키보드 입력 감지: 's' 키로 감시 중지, 'd' 키로 감시 재개
    # ----------------------------
    def keyboard_listener():
        """'s' 키를 감지하여 감시를 중지하고, 'd' 키로 감시를 재개하는 스레드"""
        if not KEYBOARD_AVAILABLE:
            return
        
        print("[main] 's' 키를 누르면 감시가 중지되고, 'd' 키를 누르면 감시가 재개됩니다.")
        s_pressed = False
        d_pressed = False
        while True:
            try:
                if keyboard.is_pressed('s') and not s_pressed:
                    print("[main] 's' 키 감지됨 - 모든 감시 중지")
                    macro.stop_all_watching()
                    s_pressed = True
                    time.sleep(0.3)  # 중복 감지 방지
                elif not keyboard.is_pressed('s'):
                    s_pressed = False
                
                if keyboard.is_pressed('d') and not d_pressed:
                    print("[main] 'd' 키 감지됨 - 감시 재개")
                    macro.resume_all_watching()
                    d_pressed = True
                    time.sleep(0.3)  # 중복 감지 방지
                elif not keyboard.is_pressed('d'):
                    d_pressed = False
                
                time.sleep(0.1)
            except Exception as e:
                time.sleep(0.1)
    
    if KEYBOARD_AVAILABLE:
        keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
        keyboard_thread.start()

    # ----------------------------
    # Tk 메인 루프
    # ----------------------------
    root.mainloop()


if __name__ == "__main__":
    main()
