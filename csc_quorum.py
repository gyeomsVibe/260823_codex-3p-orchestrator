#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSC 정족수 합의 — 사용자 제안 "출석한 도구들의 만장일치"를 안전하게 정제한 구현.

사용자 원안:
    "무조건 만장일치가 아니라, 3대 도구 중 출석(부재는 제외)한 도구들의 만장일치"

원안의 문제 (그대로 두면 위험):
    P0-1  정족수 하한이 없다 -> 1명만 남으면 그 1명이 곧 만장일치가 된다(독재).
    P0-2  '출석'을 선언으로 정하면 반대자를 부재 처리해 이길 수 있다.
          실제로 Codex 가 2명 미참여 상태에서 만장일치를 선언한 사건(T4)이 있었고,
          원안 그대로면 그 위반이 합법이 된다.
    P0-3  분할(split-brain). 서로를 부재로 보는 두 무리가 각자 '만장일치'를 낼 수 있다.
    P0-4  부재자가 이미 걸어둔 BLOCKED 가 부재를 이유로 증발한다.

정제안 (분산 합의의 표준 해법을 적용):
    Q = floor(N/2)+1  ...  '출석 인원'이 아니라 '전체 설정 인원'의 과반.
    N=3 이면 Q=2. 크기 2인 서로소 집합 두 개는 3명에서 만들 수 없으므로
    두 개의 정족수가 동시에 성립할 수 없다 -> 분할 시에도 결정은 하나뿐이다.

    출석은 하트비트로 '측정'한다. 선언으로 인정하지 않는다.
    부재자의 미해결 BLOCKED 는 부재 중에도 유효하다.
    정족수 미달이면 자동 진행이 아니라 사용자에게 에스컬레이션한다.
    되돌릴 수 없는 행위는 정족수와 무관하게 사용자 승인이 필요하다(불변).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

ENC = "utf-8"
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding=ENC, errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
SWARM = os.path.join(ROOT, ".agent-swarm")
WORKERS = os.path.join(SWARM, "workers")

MEMBERS = ("codex", "claude", "antigravity")     # 전체 설정 인원 N
HEARTBEAT_MAX_AGE_S = 180                        # 이보다 오래되면 부재로 측정

# 정족수와 무관하게 사용자 승인이 필요한 행위. 합의로 우회할 수 없다.
IRREVERSIBLE = ("commit", "push", "deploy", "install", "delete",
                "credential_change", "external_send")


def quorum_size(n=len(MEMBERS)):
    """전체 인원의 과반. 출석 인원 기준이 아니다."""
    return n // 2 + 1


def measure_presence(now=None, workers_dir=None, max_age=HEARTBEAT_MAX_AGE_S):
    """하트비트 파일로 출석을 '측정'한다. 자기 신고를 믿지 않는다."""
    now = now if now is not None else time.time()
    wd = workers_dir or WORKERS
    presence = {}
    for m in MEMBERS:
        path = os.path.join(wd, "%s.json" % m)
        try:
            with open(path, encoding=ENC) as f:
                meta = json.load(f)
            age = now - float(meta.get("heartbeat_epoch", 0))
            presence[m] = {
                "present": age <= max_age and meta.get("status") == "ready",
                "age_s": round(age, 1),
                "status": meta.get("status"),
            }
        except Exception as exc:
            presence[m] = {"present": False, "age_s": None,
                           "status": "unmeasurable", "error": type(exc).__name__}
    return presence


def decide(votes, presence=None, open_blocks=None, action_kind="local",
           user_approved=False, now=None):
    """정족수 합의를 판정한다.

    ⚠️ 이 함수는 `csc_decide.decide()` 로 대체됐다 (2026-09-06).

    남겨 두는 이유는 정족수 계산 규칙(전체 과반)과 부재자 BLOCKED 처리 근거를
    기록으로 보존하기 위해서다. **새 안건 판정에는 쓰지 않는다.**

    왜 대체됐나 — 이 함수는 부재를 사실상 거부권으로 취급해 교착을 만든다.
      · open_blocks 가 있으면 만료·소유자와 무관하게 무조건 BLOCKED
      · 출석했는데 침묵하면 마감 없이 영원히 PENDING
      · 사용량 한도로 인한 일시 부재와 사망을 구분하지 않는다
    부재를 기권으로 명시하고 모든 대기에 마감을 두는 쪽이 csc_decide 다.

    같은 일을 하는 판정기가 둘이면 언젠가 서로 다른 답을 낸다.
    그래서 판정 권한은 csc_decide 하나로 모은다.

    votes        {member: "READY"|"BLOCKED"|"ABSTAIN"} — 이번 안건에 실제로 낸 표
    presence     measure_presence() 결과. 없으면 실측한다
    open_blocks  {member: "사유"} — 미해결 BLOCKED. 부재자 것도 유효하다
    action_kind  "local" | IRREVERSIBLE 중 하나
    user_approved 사용자 승인 여부 (되돌릴 수 없는 행위에 필요)
    """
    presence = presence if presence is not None else measure_presence(now=now)
    open_blocks = open_blocks or {}
    q = quorum_size()

    present = [m for m in MEMBERS if presence.get(m, {}).get("present")]
    # 출석했는데 표를 안 낸 것은 찬성이 아니다(규약 제9조: 침묵 != 동의).
    silent = [m for m in present if m not in votes]
    voted = {m: v for m, v in votes.items() if m in present}
    blocked_now = [m for m, v in voted.items() if v == "BLOCKED"]

    result = {
        "at": datetime.now(timezone.utc).isoformat(),
        "N": len(MEMBERS), "quorum_required": q,
        "present": present, "present_count": len(present),
        "votes": voted, "silent_present": silent,
        "open_blocks": open_blocks, "action_kind": action_kind,
    }

    # 1) 부재자의 미해결 BLOCKED 는 부재를 이유로 사라지지 않는다.
    if open_blocks:
        result.update(decision="BLOCKED",
                      reason="미해결 BLOCKED 존재(부재자 포함): %s"
                             % ", ".join(sorted(open_blocks)))
        return result

    # 2) 정족수 미달이면 자동 진행이 아니라 사용자에게 올린다.
    if len(present) < q:
        result.update(decision="ESCALATE_TO_USER",
                      reason="출석 %d명 < 정족수 %d명. 남은 인원만으로 결정하지 않는다."
                             % (len(present), q))
        return result

    # 3) 출석했는데 침묵한 표는 찬성으로 세지 않는다.
    if silent:
        result.update(decision="PENDING",
                      reason="출석했으나 미투표: %s. 침묵은 동의가 아니다." % ", ".join(silent))
        return result

    # 4) 출석자 중 한 명이라도 반대하면 진행하지 않는다(출석자 만장일치).
    if blocked_now:
        result.update(decision="BLOCKED",
                      reason="출석자 중 BLOCKED: %s" % ", ".join(blocked_now))
        return result

    # 5) 되돌릴 수 없는 행위는 합의로 우회할 수 없다.
    if action_kind in IRREVERSIBLE and not user_approved:
        result.update(decision="NEEDS_USER_APPROVAL",
                      reason="'%s' 는 되돌릴 수 없다. 합의가 있어도 사용자 승인이 필요하다."
                             % action_kind)
        return result

    result.update(decision="APPROVED",
                  reason="출석 %d/%d(정족수 %d) 전원 READY" % (len(present), len(MEMBERS), q))
    return result


# --------------------------------------------------------------- 검증
def _p(present_map, age=1.0):
    return {m: {"present": bool(present_map.get(m)), "age_s": age,
                "status": "ready" if present_map.get(m) else "stale"}
            for m in MEMBERS}


def selftest():
    print("=" * 70)
    print("csc_quorum 정족수 합의 검증  (N=%d, Q=%d)" % (len(MEMBERS), quorum_size()))
    print("=" * 70)
    cases = []

    def case(name, expect, **kw):
        r = decide(**kw)
        ok = r["decision"] == expect
        cases.append(ok)
        print("  %s %-46s 기대=%-20s 실제=%s"
              % ("[OK]" if ok else "[FAIL]", name, expect, r["decision"]))
        if not ok:
            print("        %s" % r["reason"])

    # 정상 경로
    case("출석 2/3 전원 READY -> 승인", "APPROVED",
         votes={"codex": "READY", "claude": "READY"},
         presence=_p({"codex": 1, "claude": 1}))
    case("출석 3/3 전원 READY -> 승인", "APPROVED",
         votes={m: "READY" for m in MEMBERS}, presence=_p({m: 1 for m in MEMBERS}))

    # REDTEAM P0-1: 1명 독재
    case("REDTEAM 1명만 출석 -> 사용자 에스컬레이션", "ESCALATE_TO_USER",
         votes={"codex": "READY"}, presence=_p({"codex": 1}))

    # REDTEAM P0-2: 반대자를 부재 처리해 통과 시도 -> 정족수가 막는다
    case("REDTEAM 반대자 배제 후 단독 통과 시도", "ESCALATE_TO_USER",
         votes={"codex": "READY"}, presence=_p({"codex": 1}))

    # REDTEAM P0-4: 부재자의 기존 BLOCKED 는 살아 있다
    case("REDTEAM 부재자 BLOCKED 무시 시도", "BLOCKED",
         votes={"codex": "READY", "claude": "READY"},
         presence=_p({"codex": 1, "claude": 1}),
         open_blocks={"antigravity": "고아 락 미해결"})

    # 침묵을 찬성으로 세지 않는다
    case("출석했으나 미투표 -> 보류", "PENDING",
         votes={"codex": "READY"}, presence=_p({"codex": 1, "claude": 1}))

    # 출석자 중 반대
    case("출석자 중 BLOCKED -> 차단", "BLOCKED",
         votes={"codex": "READY", "claude": "BLOCKED"},
         presence=_p({"codex": 1, "claude": 1}))

    # 되돌릴 수 없는 행위는 합의로 못 넘는다
    case("만장일치라도 push 는 사용자 승인 필요", "NEEDS_USER_APPROVAL",
         votes={m: "READY" for m in MEMBERS}, presence=_p({m: 1 for m in MEMBERS}),
         action_kind="push")
    case("사용자 승인 있으면 push 승인", "APPROVED",
         votes={m: "READY" for m in MEMBERS}, presence=_p({m: 1 for m in MEMBERS}),
         action_kind="push", user_approved=True)

    # REDTEAM P0-3: 분할. 크기 2인 서로소 정족수 두 개는 3명에서 불가능하다.
    import itertools
    q = quorum_size()
    groups = [set(c) for c in itertools.combinations(MEMBERS, q)]
    disjoint = [(a, b) for a, b in itertools.combinations(groups, 2) if not (a & b)]
    ok = not disjoint
    cases.append(ok)
    print("  %s %-46s 서로소 정족수 쌍 %d개"
          % ("[OK]" if ok else "[FAIL]", "REDTEAM 분할(split-brain) 불가능성", len(disjoint)))

    print("-" * 70)
    print("통과 %d / %d" % (sum(cases), len(cases)))
    return 0 if all(cases) else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "presence":
        print(json.dumps(measure_presence(), ensure_ascii=False, indent=2))
        sys.exit(0)
    sys.exit(selftest())
