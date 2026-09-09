#!/usr/bin/env python
"""3대 도구 공통 원칙 동기화 검사기 (Cross-Platform Principle Sync Checker).

사용자 지시 (2026-09-06):
    "모르는 걸 모르는 사용자 원칙과 오류수정은 모든 3대 AI 도구에 동시 동기화되어야 한다."

왜 '있는지 확인' 만으로는 부족한가
    앞선 테스트는 각 규칙 파일에 문구가 **존재하는지**만 봤다.
    그건 세 파일이 서로 **다른 내용**을 담고 있어도 통과한다.
    한쪽만 고치면 세 도구가 서로 다른 규칙을 따르게 되고,
    그 순간 "동기화됐다" 는 말은 선언일 뿐 사실이 아니게 된다.

    이 프로젝트가 반복해서 겪은 실패가 정확히 그것이다 — 선언과 실제의 분리.

어떻게 강제하는가
    1. 정본은 `.agent-swarm/USER_FIRST_PRINCIPLE.md` 하나뿐이다.
    2. 정본에서 '핵심 계약' 문장들을 뽑아 지문(sha256)을 만든다.
    3. 각 도구 규칙 파일이 그 계약 문장을 모두 담고 있는지 대조한다.
    4. 하나라도 빠지면 어느 파일에서 무엇이 빠졌는지 이름을 대고 실패한다.

    문서 전체를 복사시키지 않는다. 파일마다 어투와 분량이 다른 것은 정상이다.
    다만 **의미를 이루는 계약 문장은 전부 있어야 한다.**
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANON = os.path.join(HERE, ".agent-swarm", "USER_FIRST_PRINCIPLE.md")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 세 도구가 반드시 공유해야 하는 계약. 표현이 아니라 '내용' 을 검사한다.
# 각 항목은 (이름, 그 계약이 담겼는지 확인할 문자열들) 이다.
# 문자열 중 하나라도 있으면 그 계약은 담긴 것으로 본다 — 어투 차이를 허용한다.
CONTRACTS = [
    ("대상 사용자 정의", ["모르는 걸 모르는 사용자"]),
    ("한국어 우선·영어 병기", ["한국어 우선", "한국어(영어)"]),
    # 2026-09-07 신설: 영어만 붙이는 것으로는 부족하다. 쉬운 설명이 있어야 뜻이 전달된다.
    ("전문용어 쉬운말 병기", ["쉬운 말과 반드시 병기", "쉬운용어와 병기", "3단 병기"]),
    ("상태 3요소", ["왜 그렇게 판단했는지", "왜 그렇게 봤나"]),
    ("사용자 행동 안내", ["무엇을 하면 되는지", "하실 일", "사용자가 할 일"]),
    ("나쁜 소식 우선", ["나쁜 소식", "미검증 항목을 성공 항목보다"]),
    ("오류수정 3도구 동시 동기화", ["오류수정은 3대 AI 도구 공통으로 동시 동기화"]),
    ("C3P 호출문 유니코드 대소문자", ["지원되는 모든 자연어 호출문은 유니코드 대소문자를 구분하지"]),
    ("위반 시 제재", ["CALL_OUT"]),
]

# 동기화 대상. 각 도구가 실제로 읽는 파일이다.
TARGETS = [
    (".agent-swarm/USER_FIRST_PRINCIPLE.md", "정본 (모든 도구)"),
    ("AGENTS.md", "3대 도구 공통 규약"),
    ("CLAUDE.md", "Claude Code"),
    ("GEMINI.md", "Antigravity"),
    (".agents/skills/codex-3p-orchestrator/SKILL.md", "Codex 스킬"),
    (".agent-swarm/GOVERNANCE.md", "거버넌스 12절"),
]


def canon_fingerprint() -> str:
    """정본의 계약 부분만으로 지문을 만든다. 오탈자 수정으로 지문이 흔들리지 않게."""
    try:
        with open(CANON, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return ""
    picked = []
    for _, needles in CONTRACTS:
        for n in needles:
            if n in text:
                picked.append(n)
                break
    return hashlib.sha256("\n".join(picked).encode("utf-8")).hexdigest()[:12]


def check() -> tuple[list[dict], bool]:
    rows, ok_all = [], True
    for rel, role in TARGETS:
        path = os.path.join(HERE, rel)
        if not os.path.exists(path):
            rows.append({"file": rel, "role": role, "ok": False,
                         "missing": ["파일 자체가 없음"]})
            ok_all = False
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        missing = [name for name, needles in CONTRACTS
                   if not any(n in text for n in needles)]
        rows.append({"file": rel, "role": role, "ok": not missing, "missing": missing})
        if missing:
            ok_all = False
    return rows, ok_all


def main() -> int:
    ap = argparse.ArgumentParser(
        description="공통 원칙과 오류수정 계약이 3대 도구에 동일하게 반영됐는지 검사한다")
    ap.add_argument("--quiet", action="store_true", help="문제가 있을 때만 출력한다")
    args = ap.parse_args()

    rows, ok_all = check()
    fp = canon_fingerprint()

    if ok_all and args.quiet:
        return 0

    print("=" * 68)
    print("3대 도구 공통 원칙 동기화 검사 (Cross-Platform Principle Sync)")
    print(f"정본: .agent-swarm/USER_FIRST_PRINCIPLE.md  지문: {fp or '없음'}")
    print("=" * 68)
    for r in rows:
        mark = "OK  " if r["ok"] else "빠짐"
        print(f"  [{mark}] {r['file']:52s} {r['role']}")
        for m in r["missing"]:
            print(f"          └─ 누락된 계약: {m}")
    print("-" * 68)
    if ok_all:
        print(f"결과: 정상 — {len(rows)}개 파일이 같은 계약 {len(CONTRACTS)}개를 모두 담고 있다.")
        return 0
    print("결과: 불일치 — 세 도구가 서로 다른 규칙을 따르고 있다.")
    print("      정본을 고친 뒤 위에 표시된 파일에 같은 계약을 반영하라.")
    print("      한쪽만 고치면 동기화가 아니라 분열이다.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
