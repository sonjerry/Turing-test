import tkinter as tk
from tkinter import ttk, messagebox

import macro  # PREVIEW_DICT, EXCEPTION_TITLES 사용


class PreviewStackGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Macro Preview Stack Viewer")

        # 전체를 가로로 나누는 PanedWindow
        self.paned = ttk.Panedwindow(master, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        # 좌측 영역 (타이틀 / 프리뷰)
        self.left_frame = ttk.Frame(self.paned)
        self.paned.add(self.left_frame, weight=3)

        # 우측 영역 (스케줄러 태그 표시)
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=1)

        # 왼쪽 스크롤 가능한 리스트 영역 구성
        self._build_left_panel()

        # 오른쪽 스케줄러 태그 패널 구성
        self._build_right_panel()
        
        # 현재 활성화된 태그 (None이면 모두 비활성화)
        self.current_tag = None

        # title별 위젯 상태 저장용
        # { title: {"frame": Frame, "header_btn": Button, "content_label": Label, "expanded": bool} }
        self.title_widgets = {}

        # 주기적으로 PREVIEW_DICT 반영
        self._refresh_interval_ms = 1000  # 1초
        self._schedule_refresh()

    # ------------------------------
    # 좌측 패널: PREVIEW_DICT 뷰어
    # ------------------------------
    def _build_left_panel(self):
        # 스크롤 영역용 캔버스 + 프레임
        self.left_canvas = tk.Canvas(self.left_frame)
        self.left_scrollbar = ttk.Scrollbar(
            self.left_frame, orient="vertical", command=self.left_canvas.yview
        )
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)

        self.left_canvas.pack(side="left", fill="both", expand=True)
        self.left_scrollbar.pack(side="right", fill="y")

        # 캔버스 안에 실제 내용을 넣을 프레임
        self.inner_left_frame = ttk.Frame(self.left_canvas)
        self.left_canvas.create_window(
            (0, 0), window=self.inner_left_frame, anchor="nw"
        )

        # 스크롤 영역 리사이즈 처리
        self.inner_left_frame.bind(
            "<Configure>",
            lambda e: self.left_canvas.configure(
                scrollregion=self.left_canvas.bbox("all")
            ),
        )

        # 제목
        title_label = ttk.Label(
            self.inner_left_frame,
            text="채팅방별 PREVIEW 스택",
            font=("맑은 고딕", 11, "bold"),
        )
        title_label.pack(anchor="w", padx=6, pady=(6, 4))

    def _create_title_widget(self, chat_title):
        """
        아직 UI에 없는 title에 대해,
        헤더 버튼 + 펼쳐지는 내용 Label을 가진 프레임 생성
        """
        outer = ttk.Frame(self.inner_left_frame)
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
        주기적으로 PREVIEW_DICT를 읽어서 좌측 UI 갱신
        """
        self._refresh_titles_from_dict()
        self.master.after(self._refresh_interval_ms, self._schedule_refresh)

    # ------------------------------
    # 우측 패널: 스케줄러 태그 표시
    # ------------------------------
    def _build_right_panel(self):
        # 제목
        right_title = ttk.Label(
            self.right_frame,
            text="스케줄러 태그",
            font=("맑은 고딕", 11, "bold"),
        )
        right_title.pack(anchor="w", padx=6, pady=(6, 4))

        # 설명
        desc = ttk.Label(
            self.right_frame,
            text="모델의 응답 태그",
            justify="left",
        )
        desc.pack(anchor="w", padx=6, pady=(0, 8))

        # 태그 프레임
        tag_frame = ttk.Frame(self.right_frame)
        tag_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # 3개 태그 라벨 생성 및 저장
        self.tag_labels = {}
        tags = ["<INSTANT>", "<WAIT>", "<FINISH>"]
        
        for tag in tags:
            label = tk.Label(
                tag_frame,
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

    def update_tag(self, tag: str):
        """
        모델의 리턴 태그에 따라 해당 태그를 빨간색으로 변경
        다른 태그는 기본 색상(검은색)으로 변경
        
        Args:
            tag: 모델이 반환한 태그 (<INSTANT>, <WAIT>, <FINISH> 중 하나)
        """
        # 모든 태그를 기본 색상으로 초기화
        for tag_name, label in self.tag_labels.items():
            label.configure(fg="black", bg="white")
        
        # 해당 태그를 빨간색으로 변경
        if tag in self.tag_labels:
            self.tag_labels[tag].configure(fg="red", bg="#ffe6e6")
            self.current_tag = tag
        else:
            print(f"[warning] 알 수 없는 태그: {tag}")
            self.current_tag = None


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
