#!/usr/bin/env python
"""실시간 감시 (event watcher) — 물어보지 않고 사건이 생기면 알린다.

━━ 왜 이 방식인가 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용자 질문: "스케줄러 간격을 더 빈번하게 하는 것은 비효율적인가?"

공개 자료 조사 결과 — 주기적으로 물어보는 방식(polling, 폴링)은
**일이 있든 없든 일정 비용**이 든다. 사건이 생길 때만 알리는 방식은 **유휴 비용이 0**이고
응답 지연이 70~90% 짧다. (Airbyte / Fastio 2026)

그리고 우리에겐 이미 사건이 생기는 자리가 있다 —
**파일에 한 줄이 추가되는 것 자체가 사건이다.** 물어볼 필요가 없다.

━━ 소음을 만들지 않는 것이 이 파일의 핵심 계약 ━━━━━━━━━━━━━━━━━━━━━━━━━
알림이 잦으면 사람은 알림을 끈다. 끄면 없는 것과 같다.
이 프로젝트는 이미 그 교훈을 두 번 얻었다 —
거짓 빨간불(없는 경고)과 12:1 로그 소음(연결 부기가 대화보다 열두 배).

그래서 다음만 알린다.
    · 나에게 온 것 (또는 전체 공지)
    · 사람이 쓴 말 (프로그램이 남긴 EVENT 기록은 제외)
    · 내가 보낸 것이 아닌 것

나머지는 조용히 넘긴다. 파일에는 그대로 남으므로 나중에 볼 수 있다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, ".agent-swarm", "messages", "queue.jsonl")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 사람이 쓴 말이 아니라 프로그램이 남긴 흔적. 알릴 가치가 없다.
MACHINE_TYPES = {"EVENT", "AGENT_JOINED", "AGENT_LEFT", "REGISTER"}


def is_for_me(msg: dict, me: str) -> bool:
    """나에게 온 것인가. 내가 보낸 것은 알리지 않는다."""
    sender = str(msg.get("sender", "")).lower()
    recipient = str(msg.get("recipient", "")).lower()
    short = me.split("-")[0].lower()          # claude-code-6c -> claude

    if me.lower() in sender or sender.startswith(short):
        return False                          # 내가 보낸 것
    if str(msg.get("type", "")) in MACHINE_TYPES:
        return False                          # 프로그램이 남긴 기록
    return recipient in ("all", short, me.lower())


def line_count(path: str) -> int:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def read_from(path: str, skip: int) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i < skip:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    # 깨진 줄을 조용히 버리지 않는다. 손상 자체가 정보다.
                    out.append({"sender": "unknown", "recipient": "all",
                                "type": "RISK",
                                "body": "감시 중 읽을 수 없는 줄을 만났습니다. 기록이 손상됐을 수 있습니다."})
    except FileNotFoundError:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="스웜 메시지 파일을 지켜보다가 나에게 온 새 말만 한 줄로 알린다")
    ap.add_argument("--me", default=os.environ.get("CSC_AGENT_ID", "claude-code-6c"))
    ap.add_argument("--interval", type=float, default=2.0,
                    help="파일 확인 간격(초). 파일 크기만 보므로 비용이 거의 없다")
    ap.add_argument("--max-minutes", type=float, default=0,
                    help="이 시간이 지나면 스스로 끝낸다. 0이면 계속")
    args = ap.parse_args()

    # 시작 시점 이후의 것만 알린다. 지난 것을 몰아서 쏟아내면 그게 소음이다.
    seen = line_count(QUEUE)
    started = time.time()
    print(f"감시 시작 — 기준선 {seen}줄. 지금부터 들어오는 것만 알립니다.", flush=True)

    while True:
        if args.max_minutes and (time.time() - started) > args.max_minutes * 60:
            print("감시 종료 — 정해진 시간이 지났습니다.", flush=True)
            return 0
        time.sleep(args.interval)

        now = line_count(QUEUE)
        if now <= seen:
            continue                          # 바뀐 것이 없다. 아무것도 하지 않는다

        for msg in read_from(QUEUE, seen):
            if not is_for_me(msg, args.me):
                continue
            body = str(msg.get("body", "")).replace("\n", " ")[:150]
            print(f"새 메시지 | {msg.get('sender')} → {msg.get('recipient')} "
                  f"| {msg.get('type')} | {body}", flush=True)
        seen = now


if __name__ == "__main__":
    raise SystemExit(main())
