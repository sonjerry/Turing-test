# OpenMP 중복 초기화 오류 해결
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import threading
import tkinter as tk
from tkinter import ttk

import macro
import gui  # PreviewStackgui 사용
import schedular



def main():
    # ----------------------------
    # Tk 루트 + gui.PreviewStackgui 생성
    # ----------------------------
    root = tk.Tk()
    root.title("Macro Main Controller")

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
    log_frame.pack(side="bottom", fill="x")

    log_label = ttk.Label(log_frame, text="캡쳐 로그", font=("맑은 고딕", 10, "bold"))
    log_label.pack(anchor="w", padx=6, pady=(4, 0))

    log_text = tk.Text(log_frame, height=5, state="disabled")
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
        
        # chatting_room 업데이트 시 schedular 호출
        def call_scheduler():
            def on_tag_received(tag):
                # 메인 스레드에서 GUI 업데이트
                root.after(0, lambda t=tag: app.update_tag(t))
            
            schedular.schedule_chatting_room_update(
                title_key=title_key,
                on_tag_received=on_tag_received
            )
        
        # 별도 스레드에서 schedular 호출 (API 호출이 블로킹될 수 있음)
        scheduler_thread = threading.Thread(target=call_scheduler, daemon=True)
        scheduler_thread.start()

    # ----------------------------
    # 프로그램 시작 5초 대기 후 감시 시작
    # ----------------------------
    def start_watcher_after_delay():
        import time
        print("[main] 프로그램 시작, 5초 대기 중...")
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
    
    # 별도 스레드에서 5초 대기 후 감시 시작 (GUI 블로킹 방지)
    delay_thread = threading.Thread(target=start_watcher_after_delay, daemon=True)
    delay_thread.start()

    # ----------------------------
    # Tk 메인 루프
    # ----------------------------
    root.mainloop()


if __name__ == "__main__":
    main()
