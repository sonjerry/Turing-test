import json
import random
import argparse
from typing import List, Dict, Any


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                data.append(obj)
            except json.JSONDecodeError:
                print(f"[WARN] JSON 파싱 실패: {line[:50]}...")
    return data


def pretty_print_sample(sample: Dict[str, Any]) -> None:
    messages = sample.get("messages", [])
    print("=" * 60)
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        print(f"[{role.upper()}]")
        print(content)
        print("-" * 60)
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="jsonl 파인튜닝 샘플 랜덤 체크용")
    parser.add_argument("jsonl_path", help="검사할 jsonl 파일 경로")
    args = parser.parse_args()

    data = load_jsonl(args.jsonl_path)
    if not data:
        print("데이터가 없습니다. jsonl 내용을 확인해주세요.")
        return

    print(f"로드된 샘플 수: {len(data)}")
    print("1 입력 시 랜덤 샘플을 하나 보여줍니다. (q 입력 시 종료)")

    while True:
        cmd = input("입력 (1 / q): ").strip()
        if cmd == "q":
            print("종료합니다.")
            break
        if cmd == "1":
            sample = random.choice(data)
            pretty_print_sample(sample)
        else:
            print("1 또는 q만 입력 가능합니다.")


if __name__ == "__main__":
    main()
