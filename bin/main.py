import threading

import tkinter as tk
from tkinter import ttk

import macro  # watcher_loop 사용

# ---------------------
# 디버그 오버레이 설정
# ---------------------
DEBUG_OVERLAY = True          # False로 바꾸면 박스 안 뜸
# region_overlays = {}          # {key: Toplevel}

# ---------------------
# 스택/리스트 저장 구조
# ---------------------
message_stack = []

# GUI 전역 변수
text_area = None


# ---------------------
# 화면 오버레이(디버그 박스) 구현
# ---------------------

def create_overlay_window(key, region, color="#ff0000"):
    """
    region: (left, top, width, height)
    화면 절대좌표에 박스를 표시하는 작은 투명/얇은 윈도우 생성.
    """
    import tkinter as tk

    if not DEBUG_OVERLAY or region is None:
        return

    if len(region) != 4:
        print(f"[WARN] {key} region length != 4: {region}")
        return

    x, y, w, h = region

    # 박스용 최상위 창
    win = tk.Toplevel()
    win.overrideredirect(True)    # 타이틀바 제거
    win.attributes("-topmost", True)
    try:
        win.attributes("-alpha", 0.7)   # 일부 OS에서 투명도 적용
    except Exception:
        pass

    # 테두리만 표시되는 프레임
    frame = tk.Frame(
        win, bg=color, highlightthickness=2, highlightbackground=color
    )
    frame.pack(fill="both", expand=True)

    win.geometry(f"{w}x{h}+{x}+{y}")

    # 별도의 딕셔너리에 저장하지 않고, 함수 범위 내에서만 띄움
    # 필요 시 갱신 로직을 추가할 수 있음


def init_region_overlays():
    """macro.TRIGGER_REGION / REGIONS 에 등록된 위치에 디버그 박스 표시."""
    if not DEBUG_OVERLAY:
        return

    # 트리거 박스
    trigger_region = getattr(macro, "TRIGGER_REGION", None)
    create_overlay_window("TRIGGER", trigger_region, color="#00ff00")

    # 텍스트 추출용 영역들
    regions = getattr(macro, "REGIONS", None)
    if isinstance(regions, dict):
        for key, reg in regions.items():
            create_overlay_window(key, reg, color="#ff0000")


# ---------------------
# 매크로에서 인식 감지될 때 callback
# ---------------------

def on_detect(data: dict):
    """
    data 예:
    {
        "timestamp": "...",
        "title": "...",
        "preview": "...",
        "time": "..."
    }
    """
    # 새 메시지를 스택에 쌓기
    message_stack.append(data)
    print("감지됨:", data)

    # GUI 갱신: 메인 스레드에서 수행해야 함
    if text_area is not None:
        root.after(0, update_text_area)


def update_text_area():
    """Stack 내용을 text_area에 표시."""
    if text_area is None:
        return

    text_area.config(state="normal")
    text_area.delete("1.0", "end")

    # 단순하게 message_stack 전체를 문자열로 보여줌
    for msg in message_stack:
        title = msg.get("title", "")
        preview = msg.get("preview", "")
        time_str = msg.get("time", "")
        ts = msg.get("timestamp", "")
        text_area.insert("end", f"[{ts}] {title} / {preview} / {time_str}\n")

    text_area.config(state="disabled")


def on_flash():
    """매크로의 트리거 바운스(깜빡임) 이벤트 콜백. 여기서는 단순 출력."""
    print("FLASH detected - 트리거 깜빡임")


# ---------------------
# GUI 초기화
# ---------------------

def init_gui():
    global text_area, root

    root = tk.Tk()
    root.title("카카오톡 메시지 디버그 뷰어")
    root.geometry("800x600")

    # 스크롤바 + Text 영역
    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True)

    text_area_local = tk.Text(frame, wrap="none", state="disabled")
    text_area_local.pack(side="left", fill="both", expand=True)

    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text_area_local.yview)
    scrollbar.pack(side="right", fill="y")

    text_area_local.configure(yscrollcommand=scrollbar.set)

    text_area = text_area_local

    # 디버그 박스(화면 오버레이) 생성
    init_region_overlays()

    return root


# ---------------------
# 메인 실행
# ---------------------

def main():
    root = init_gui()

    # 감시 스레드 시작 (매크로 watcher)
    t = threading.Thread(
        target=macro.watcher_loop,
        args=(on_detect, on_flash),
        daemon=True
    )
    t.start()

    root.mainloop()


if __name__ == "__main__":
    main()
