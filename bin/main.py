# main.py

import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk

import macro  # ← 요렇게

# ---------------------
# 디버그 오버레이 설정
# ---------------------
DEBUG_OVERLAY = True          # False로 바꾸면 박스 안 뜸
region_overlays = {}          # {key: (win, frame)}
# trigger_overlay = None      # ← 트리거 박스 제거


# ---------------------
# 데이터 스택 / GUI 전역
# ---------------------
message_stack = []
root = None
tree = None


# ---------------------
# GUI와 연동되는 함수들
# ---------------------

def add_message_to_stack_and_gui(data):
    """
    OCR로 뽑은 data(dict)를 스택에 push하고,
    Tkinter Treeview에도 한 줄 추가
    """
    global message_stack, tree, root

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "timestamp": timestamp,
        "title": data.get("title", ""),
        "preview": data.get("preview", ""),
        "time": data.get("time", ""),
    }

    message_stack.append(entry)

    def _insert_row():
        tree.insert(
            "",
            "end",
            values=(entry["timestamp"], entry["title"],
                    entry["preview"], entry["time"])
        )

    root.after(0, _insert_row)


# ---------------------
# 오버레이 관련 함수
# ---------------------

def create_overlays():
    """
    title / preview 두 개만 박스로 표시
    """
    global region_overlays, root

    if not DEBUG_OVERLAY:
        return

    transparent_color = "magenta"

    # title, preview만 오버레이 생성
    for key in ("title", "preview"):
        region = macro.REGIONS.get(key)
        if region is None:
            continue

        left, top, width, height = region

        win = tk.Toplevel(root)
        win.overrideredirect(True)        # 타이틀바 제거
        win.attributes("-topmost", True)

        win.configure(bg=transparent_color)
        win.attributes("-transparentcolor", transparent_color)

        frame = tk.Frame(
            win,
            bg=transparent_color,          # 통째로 투명 처리
            highlightbackground="red",     # 테두리 색
            highlightthickness=2           # 테두리 두께
        )
        frame.pack(fill="both", expand=True)

        win.geometry(f"{width}x{height}+{left}+{top}")

        region_overlays[key] = (win, frame)


def flash_overlays(times=3, interval=150):
    """
    감지 시 title/preview 박스만 깜빡이기
    """
    if not DEBUG_OVERLAY:
        return

    def _flash(step):
        # step이 0이면 원래 색으로 초기화하고 끝
        if step <= 0:
            for key, (win, frame) in region_overlays.items():
                frame.config(highlightbackground="red")
            return

        bright = (step % 2 == 1)

        # 일반 영역만 노랑/빨강 깜빡이기
        for key, (win, frame) in region_overlays.items():
            frame.config(highlightbackground="yellow" if bright else "red")

        root.after(interval, _flash, step - 1)

    root.after(0, _flash, times * 2)


# ---------------------
# Tkinter GUI 설정
# ---------------------

def setup_gui():
    global root, tree

    root = tk.Tk()
    root.title("Turning-test 제어판")

    # 화면 크기 얻기
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    # GUI 창 크기 (원하는 대로 조절 가능)
    win_w = 600
    win_h = 300

    # 오른쪽 아래에 붙이기 (여유 20px)
    x = screen_w - win_w - 20
    y = screen_h - win_h - 60   # 작업표시줄 감안해서 살짝 위로

    root.geometry(f"{win_w}x{win_h}+{x}+{y}")

    # 상단 안내 라벨
    label = tk.Label(root, text="감지된 메시지 리스트", font=("맑은 고딕", 12))
    label.pack(pady=5)

    # Treeview (테이블 형태)
    columns = ("timestamp", "title", "preview", "time")
    tree = ttk.Treeview(root, columns=columns, show="headings", height=15)

    tree.heading("timestamp", text="감지 시각")
    tree.heading("title", text="방 제목/구역1")
    tree.heading("preview", text="메시지/구역2")
    tree.heading("time", text="시간")

    tree.column("timestamp", width=150)
    tree.column("title", width=200)
    tree.column("preview", width=300)
    tree.column("time", width=80)

    tree.pack(fill="both", expand=True, padx=10, pady=5)

    # 스크롤바
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")

    # 하단 버튼들 (예: 스택 초기화)
    button_frame = tk.Frame(root)
    button_frame.pack(pady=5)

    def clear_stack():
        message_stack.clear()
        for item in tree.get_children():
            tree.delete(item)

    clear_btn = tk.Button(button_frame, text="스택 비우기", command=clear_stack)
    clear_btn.pack(side="left", padx=5)

    # 프로그램 켜질 때 바로 오버레이 박스 생성
    create_overlays()

    return root


# ---------------------
# 메인
# ---------------------

if __name__ == "__main__":
    # GUI 세팅
    root = setup_gui()

    # 감지 콜백 정의
    def on_detect(data):
        add_message_to_stack_and_gui(data)

    # 깜빡이기 콜백 정의
    def on_flash():
        # Tkinter 메인 스레드에서 실행되도록 after 사용
        root.after(0, flash_overlays, 3, 150)

    # 감시 스레드 시작
    t = threading.Thread(
        target=macro.watcher_loop,
        args=(on_detect, on_flash),
        daemon=True
    )
    t.start()

    # Tkinter 메인 루프
    root.mainloop()
