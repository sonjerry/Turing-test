import re
import json
import argparse
from typing import List, Optional

SELF_NAMES = {"오빠", "이가을"}
DISPLAY_NAME_MAP = {"오빠": "이가을", "이가을": "이가을"}

DROP_ONLY_CONTENTS = {"이모티콘", "사진"}
HTTP_PATTERN = re.compile(r"http[s]?://\S+")
PHOTO_MULTI_PATTERN = re.compile(r"^사진\s*\d+\s*장$", re.IGNORECASE)  # "사진 3장" 제거

MAX_BUFFER_LEN = 10
SPLIT_TOKEN = "<split>"

SYSTEM_PROMPT = "너는 '이가을'이다. 이가을 말투로 채팅방에서 대화한다. 긴 대답은 <split>으로 나눈다."


class Message:
    def __init__(self, date_str: str, time_label: str, speaker: str, text: str):
        self.date_str = date_str
        self.time_label = time_label
        self.speaker = speaker.strip()
        self.text = text.strip()

    @property
    def disp(self):
        return DISPLAY_NAME_MAP.get(self.speaker, self.speaker)

    def line(self):
        return f"[{self.disp}] [{self.time_label}] {self.text}"


def parse(lines):
    messages=[]
    current_date=None

    date_re=re.compile(r"^\s*\d{4}년\s*\d{1,2}월\s*\d{1,2}일.*$")
    msg_re=re.compile(r"^\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.)\s*(오전|오후)\s*(\d{1,2}:\d{2}),\s*([^:]+?)\s*:\s*(.*)$")

    for raw in lines:
        line=raw.strip()
        if not line: continue

        if date_re.match(line):
            current_date=line; continue

        m=msg_re.match(line)
        if m:
            if current_date is None:
                current_date="알 수 없는 날짜"
            date,ampm,hm,speaker,text=m.group(1),m.group(2),m.group(3),m.group(4),m.group(5)
            messages.append(Message(current_date,f"{ampm} {hm}",speaker,text))

    return messages


def build(messages, relationship):
    examples=[]

    buffer=[]                   # 과거 로그(남+이가을 포함)
    self_block=[]               # 이번 assistant 대상
    last_user=None              # 중복 방지
    last_assist=None

    def flush():
        nonlocal buffer,self_block,last_user,last_assist
        if not self_block: return

        user_lines=[relationship]
        for msg in buffer:
            user_lines.append(msg.line())

        user="\n".join(user_lines)
        answer=SPLIT_TOKEN.join(m.text for m in self_block)

        if not(last_user==user and last_assist==answer):
            examples.append({
                "messages":[
                    {"role":"system","content":SYSTEM_PROMPT},
                    {"role":"user","content":user},
                    {"role":"assistant","content":answer}
                ]
            })
            last_user,last_assist=user,answer

        buffer.extend(self_block)                         # 과거 이가을 발화도 context에 남김
        if len(buffer)>MAX_BUFFER_LEN:
            buffer=buffer[-MAX_BUFFER_LEN:]
        self_block.clear()


    for msg in messages:
        if HTTP_PATTERN.search(msg.text): continue
        if msg.text in DROP_ONLY_CONTENTS: continue
        if PHOTO_MULTI_PATTERN.match(msg.text):continue

        if msg.speaker in SELF_NAMES:
            self_block.append(msg)
        else:
            if self_block: flush()
            buffer.append(msg)
            if len(buffer)>MAX_BUFFER_LEN:
                buffer=buffer[-MAX_BUFFER_LEN:]

    if self_block: flush()
    return examples


def main():
    parser=argparse.ArgumentParser(description="KAKAO → JSONL (TIME 제거버전)")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--relationship",default="FAMILY")
    parser.add_argument("--append",action="store_true")
    a=parser.parse_args()

    with open(a.input,encoding="utf-8") as f:
        lines=f.readlines()

    msgs=parse(lines)
    ex=build(msgs,a.relationship)

    mode="a" if a.append else "w"
    with open(a.output,mode,encoding="utf-8") as f:
        for e in ex: f.write(json.dumps(e,ensure_ascii=False)+"\n")


if __name__=="__main__":
    main()
