import tkinter as tk
from tkinter import ttk, messagebox

import macro  # PREVIEW_DICT, EXCEPTION_TITLES 사용


class PreviewStackGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("매크로")

        # 전체를 세로로 나누는 PanedWindow (3등분)
        self.paned = ttk.Panedwindow(master, orient="vertical")
        self.paned.pack(fill="both", expand=True)

        # 첫 번째 영역: 채팅방 로그
        self.chat_frame = ttk.Frame(self.paned)
        self.paned.add(self.chat_frame, weight=1)

        # 두 번째 영역: 태그 3개
        self.tag_frame = ttk.Frame(self.paned)
        self.paned.add(self.tag_frame, weight=1)

        # 세 번째 영역: 지연 큐
        self.queue_frame = ttk.Frame(self.paned)
        self.paned.add(self.queue_frame, weight=1)

        # 각 패널 구성
        self._build_chat_panel()
        self._build_tag_panel()
        self._build_queue_panel()
        
        # 현재 활성화된 태그 (None이면 모두 비활성화)
        self.current_tag = None

        # title별 위젯 상태 저장용
        # { title: {"frame": Frame, "header_btn": Button, "content_label": Label, "expanded": bool} }
        self.title_widgets = {}

        # 주기적으로 PREVIEW_DICT 반영
        self._refresh_interval_ms = 1000  # 1초
        self._schedule_refresh()
        
        # 주기적으로 큐 상태 반영
        self._schedule_queue_refresh()

    # ------------------------------
    # 첫 번째 패널: 채팅방 로그
    # ------------------------------
    def _build_chat_panel(self):
        # 제목
        title_label = ttk.Label(
            self.chat_frame,
            text="채팅방 로그",
            font=("맑은 고딕", 11, "bold"),
        )
        title_label.pack(anchor="w", padx=6, pady=(6, 4))

        # 스크롤 영역용 캔버스 + 프레임
        self.chat_canvas = tk.Canvas(self.chat_frame)
        self.chat_scrollbar = ttk.Scrollbar(
            self.chat_frame, orient="vertical", command=self.chat_canvas.yview
        )
        self.chat_canvas.configure(yscrollcommand=self.chat_scrollbar.set)

        self.chat_canvas.pack(side="left", fill="both", expand=True)
        self.chat_scrollbar.pack(side="right", fill="y")

        # 캔버스 안에 실제 내용을 넣을 프레임
        self.inner_chat_frame = ttk.Frame(self.chat_canvas)
        self.chat_canvas.create_window(
            (0, 0), window=self.inner_chat_frame, anchor="nw"
        )

        # 스크롤 영역 리사이즈 처리
        self.inner_chat_frame.bind(
            "<Configure>",
            lambda e: self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox("all")
            ),
        )

    def _create_title_widget(self, chat_title):
        """
        아직 UI에 없는 title에 대해,
        헤더 버튼 + 펼쳐지는 내용 Label을 가진 프레임 생성
        """
        outer = ttk.Frame(self.inner_chat_frame)
        outer.pack(fill="x", padx=4, pady=2, anchor="n")

        # 헤더 버튼 (클릭 시 펼치기/접기)
        header_btn = ttk.Button(
            outer,
            text=chat_title if chat_title else "(제목 없음)",
            style="TitleButton.TButton",
            command=lambda t=chat_title: self._toggle_title(t),
        )
        header_btn.pack(fill="x", padx=2, pady=1)

        # 내용 Label (처음에는 감춰진 상태로, pack_forget)
        content_label = tk.Label(
            outer,
            text="",
            justify="left",
            anchor="w",
            font=("맑은 고딕", 9),
            bg="white",
            fg="black",
            relief="solid",
            bd=1,
        )
        # 펼쳐지기 전까지는 안 보이게
        # (toggle에서 pack/pack_forget으로 제어)
        # content_label.pack(fill="x", padx=14, pady=(2, 4))

        self.title_widgets[chat_title] = {
            "frame": outer,
            "header_btn": header_btn,
            "content_label": content_label,
            "expanded": False,
        }

    def _toggle_title(self, chat_title):
        """
        title 버튼 클릭 시, value(누적 문자열)을 펼치거나 접는다.
        """
        info = self.title_widgets.get(chat_title)
        if not info:
            return

        expanded = info["expanded"]
        label = info["content_label"]

        if not expanded:
            # 펼치기: 최신 내용 업데이트 후 pack
            value = macro.PREVIEW_DICT.get(chat_title, "")
            # 맨 앞에 붙은 \n 지워주면 보기 좋음
            value = value.lstrip("\n")
            if not value:
                value = "(아직 수집된 내용이 없습니다.)"

            label.configure(text=value)
            label.pack(fill="x", padx=14, pady=(2, 4))
            info["expanded"] = True
        else:
            # 접기: pack_forget
            label.pack_forget()
            info["expanded"] = False

    def _refresh_titles_from_dict(self):
        """
        macro.PREVIEW_DICT를 읽어서
        - 새로운 title에 대한 UI 생성
        - 이미 펼쳐져 있는 항목은 value를 최신 값으로 갱신
        """
        # 새로 생긴 key들에 대해 UI 없으면 생성
        for chat_title in macro.PREVIEW_DICT.keys():
            if chat_title not in self.title_widgets:
                self._create_title_widget(chat_title)

        # 이미 존재하면서 펼쳐져 있는 항목은 내용 갱신
        for chat_title, info in self.title_widgets.items():
            if info["expanded"]:
                value = macro.PREVIEW_DICT.get(chat_title, "")
                value = value.lstrip("\n")
                if not value:
                    value = "(아직 수집된 내용이 없습니다.)"
                info["content_label"].configure(text=value)

    def _schedule_refresh(self):
        """
        주기적으로 PREVIEW_DICT를 읽어서 채팅방 로그 UI 갱신
        """
        self._refresh_titles_from_dict()
        self.master.after(self._refresh_interval_ms, self._schedule_refresh)

    # ------------------------------
    # 두 번째 패널: 태그 3개
    # ------------------------------
    def _build_tag_panel(self):
        # 제목
        tag_title = ttk.Label(
            self.tag_frame,
            text="스케줄러 태그",
            font=("맑은 고딕", 11, "bold"),
        )
        tag_title.pack(anchor="w", padx=6, pady=(6, 4))

        # 설명
        desc = ttk.Label(
            self.tag_frame,
            text="모델의 응답 태그",
            justify="left",
        )
        desc.pack(anchor="w", padx=6, pady=(0, 8))

        # 태그 컨테이너 프레임
        tag_container = ttk.Frame(self.tag_frame)
        tag_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # 3개 태그 라벨 생성 및 저장
        self.tag_labels = {}
        tags = ["<INSTANT>", "<WAIT>"]
        
        for tag in tags:
            label = tk.Label(
                tag_container,
                text=tag,
                font=("맑은 고딕", 12, "bold"),
                bg="white",
                fg="black",
                relief="solid",
                bd=2,
                padx=10,
                pady=10
            )
            label.pack(fill="x", padx=4, pady=4)
            self.tag_labels[tag] = label

    # ------------------------------
    # 세 번째 패널: 지연 큐
    # ------------------------------
    def _build_queue_panel(self):
        # 큐 리스트 제목
        queue_title = ttk.Label(
            self.queue_frame,
            text="지연 큐",
            font=("맑은 고딕", 11, "bold"),
        )
        queue_title.pack(anchor="w", padx=6, pady=(6, 4))
        
        # 큐 리스트 스크롤 영역
        queue_canvas = tk.Canvas(self.queue_frame)
        queue_scrollbar = ttk.Scrollbar(
            self.queue_frame, orient="vertical", command=queue_canvas.yview
        )
        queue_canvas.configure(yscrollcommand=queue_scrollbar.set)
        
        queue_canvas.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 6))
        queue_scrollbar.pack(side="right", fill="y", padx=(0, 6), pady=(0, 6))
        
        # 큐 리스트 내부 프레임
        self.queue_inner_frame = ttk.Frame(queue_canvas)
        queue_canvas.create_window((0, 0), window=self.queue_inner_frame, anchor="nw")
        
        # 스크롤 영역 리사이즈 처리
        self.queue_inner_frame.bind(
            "<Configure>",
            lambda e: queue_canvas.configure(
                scrollregion=queue_canvas.bbox("all")
            ),
        )
        
        # 큐 항목 위젯 저장용
        # {title: Label}
        self.queue_widgets = {}

    def update_tag(self, tag: str):
        """
        스케줄러가 반환한 태그에 따라 태그 색상 변경
        - <INSTANT>: 파란색
        - <WAIT>: 빨간색
        - 다른 태그는 검은색
        
        Args:
            tag: 스케줄러가 반환한 태그 (<INSTANT>, <WAIT>)
        """
        try:
            # 태그가 유효한지 확인
            if tag not in self.tag_labels:
                return
            
            # 모든 태그를 검은색으로 초기화
            for tag_name, label in self.tag_labels.items():
                label.configure(fg="black", bg="white")
            
            # 해당 태그에 따라 색상 변경
            target_label = self.tag_labels[tag]
            if tag == "<INSTANT>":
                target_label.configure(fg="blue", bg="#e6f3ff")
            elif tag == "<WAIT>":
                target_label.configure(fg="red", bg="#ffe6e6")
            else:
                target_label.configure(fg="black", bg="white")
            
            self.current_tag = tag
        except Exception as e:
            print(f"[GUI] [ERROR] update_tag 실행 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
    
    def _refresh_queue_list(self):
        """
        지연 큐 상태를 읽어서 GUI에 표시.
        """
        # 기존 위젯 제거
        for widget in self.queue_inner_frame.winfo_children():
            widget.destroy()
        self.queue_widgets.clear()
        
        # 큐에서 모든 항목 가져오기
        for title in macro.DELAY_QUEUE.keys():
            queue_status = macro.get_queue_status(title)
            if queue_status is None:
                continue
            
            status = queue_status["status"]
            remaining_seconds = queue_status["remaining_seconds"]
            
            # 상태에 따라 표시 텍스트 생성
            if status == "waiting":
                display_text = f"{title}: Wait..."
            else:
                # 남은 시간을 MM:SS 형식으로 변환
                minutes = int(remaining_seconds // 60)
                seconds = int(remaining_seconds % 60)
                display_text = f"{title}: {minutes:02d}:{seconds:02d}"
            
            # 라벨 생성
            label = tk.Label(
                self.queue_inner_frame,
                text=display_text,
                font=("맑은 고딕", 9),
                bg="white",
                fg="black",
                relief="solid",
                bd=1,
                padx=6,
                pady=4
            )
            label.pack(fill="x", padx=4, pady=2)
            self.queue_widgets[title] = label
    
    def _schedule_queue_refresh(self):
        """
        주기적으로 큐 상태를 읽어서 지연 큐 UI 갱신
        """
        self._refresh_queue_list()
        self.master.after(self._refresh_interval_ms, self._schedule_queue_refresh)


def main():
    root = tk.Tk()

    # 타이틀 버튼 스타일 약간 변경 (굵게)
    style = ttk.Style()
    style.configure("TitleButton.TButton", font=("맑은 고딕", 10, "bold"))

    app = PreviewStackGUI(root)
    
    # 창 크기 업데이트 후 오른쪽 아래에 배치
    root.update_idletasks()
    window_width = root.winfo_width()
    window_height = root.winfo_height()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    x = screen_width - window_width
    y = screen_height - window_height
    root.geometry(f"+{x}+{y}")
    
    root.mainloop()


if __name__ == "__main__":
    main()
