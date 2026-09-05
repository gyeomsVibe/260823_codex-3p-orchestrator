#!/usr/bin/env python
"""교착 없는 의사결정 (Deadlock-Free Decision).

━━ 문제 진단 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용자 지적 (2026-09-06):
    "진행 막힘(BLOCKED) 현상도 문제다. 빠른 의사결정이 이루어져야 하는데
     3대 도구의 사용량 제한 등 제약조건이 달라서 현재 로직에 문제가 많아 보인다."

맞다. 우리는 한 결함을 고치면서 그 거울상을 만들었다.

    사건 020 이전 : 부재 = 동의   ->  유령 만장일치 (없는 합의를 기록)
    사건 020 이후 : 부재 = 거부   ->  영구 교착 (아무것도 못 함)

11-2 조항은 "부재는 동의가 아니다" 까지만 말하고 **부재가 무엇인지는 정하지 않았다.**
정의되지 않은 상태는 기본값으로 굴러떨어졌고, 그 기본값이 거부권이었다.

실제로 지금 이 프로젝트가 그 상태다 —
Codex 사용량 한도, Antigravity 무응답. 남은 한 명은 아무것도 결정할 수 없다.
**결정권자(사용자)는 바로 옆에 있는데 시스템이 그를 정족수에서 빼놨다.**

━━ 설계 근거 (공개 자료 조사, 2026-09-06) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • 합의 교착은 "라운드 상한 + 타임아웃 + 단일 에이전트 출력으로 폴백" 으로 완화한다
    (Zylos, Consensus Protocols for Multi-Agent Decision Making)
  • DEGRADED 모드에는 **2차 타임아웃**이 필요하다 — 사람의 재정을 기다리는 시간에도
    상한을 두고, 넘으면 자동 중단한다 (AgentCity, 헌법적 거버넌스)
  • 회로 차단기(circuit breaker): 연속 N회 실패하면 재시도를 멈춘다.
    LLM 게이트웨이에서 429 연속 발생 시 회로를 열어 재시도 폭풍을 막는 것과 같다
  • 사용량 한도는 '영구 부재' 가 아니라 **복귀 시각이 있는 일시 부재**다.
    429 응답의 retry-after 를 다루듯 취급해야 한다

━━ 해법 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 부재를 **기권(ABSTAIN)** 으로 명시한다. 동의도 거부도 아니다. 기록에 남는다.
2. 모든 대기에 **마감 시각**을 둔다. 마감이 지나면 기권으로 확정하고 다음으로 간다.
3. 부재 사유를 구분한다 — 한도 소진(복귀 시각 있음) / 사망 / 확인 불가.
   한도 소진은 기다릴 가치가 있고, 사망은 기다릴 가치가 없다.
4. `BLOCKED` 에 **소유자와 만료**를 붙인다. 주인 없는 무기한 거부권을 없앤다.
5. 결정을 **되돌림 가능성**으로 나눈다. 되돌릴 수 있으면 적은 표로 간다.
   되돌릴 수 없으면 표가 아무리 많아도 사용자 승인이 필요하다.
6. 정족수를 채울 수 없으면 **사용자에게 올린다.** 사용자는 언제나 유효한 결정권자다.
   교착은 결정이 아니다. 아무도 결정하지 않는 것을 안전이라 부르지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SWARM = os.path.join(HERE, ".agent-swarm")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

MEMBERS = ("codex", "claude", "antigravity")

# 되돌릴 수 없는 행위. 표로 우회할 수 없다.
IRREVERSIBLE = frozenset({
    "commit", "push", "deploy", "publish", "delete", "install",
    "credential_change", "external_send",
})

# 부재 사유. 기다릴 가치가 있는지 없는지가 다르다.
AVAILABLE = "available"          # 지금 응답할 수 있다
RATE_LIMITED = "rate_limited"    # 사용량 한도. 복귀 시각이 있다
OFFLINE = "offline"              # 꺼져 있다. 사람이 켜야 한다
UNKNOWN = "unknown"              # 확인 불가

# 기본 대기 시간. 사유별로 다르게 준다.
WAIT_SECONDS = {
    AVAILABLE: 180,          # 응답 가능한데 침묵 -> 3분 기다린다
    RATE_LIMITED: 3600,      # 한도 소진 -> 최대 1시간. 그 이상은 사용자 판단
    OFFLINE: 0,              # 꺼져 있으면 기다릴 이유가 없다. 즉시 기권 처리
    UNKNOWN: 300,
}

# 회로 차단기: 같은 상대에게 연속 이만큼 실패하면 재시도를 멈춘다.
CIRCUIT_OPEN_AFTER = 3

BLOCK_TTL_SECONDS = 24 * 3600    # BLOCKED 기본 유효기간. 지나면 사용자에게 올린다


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def quorum_size(n: int = len(MEMBERS)) -> int:
    """전체 구성원 과반. 출석 과반이 아니다.

    출석 과반으로 하면 혼자 남은 도구가 스스로를 정족수라고 부를 수 있다.
    """
    return n // 2 + 1


# ── 가용성 ───────────────────────────────────────────────────────────────────
def availability(agent: str, hint: dict | None = None, now: datetime | None = None) -> dict:
    """한 도구가 지금 응답할 수 있는지, 못 한다면 언제 돌아오는지.

    hint 는 외부에서 관측한 사실을 넣는 자리다 (예: CLI 가 알려준 한도 복귀 시각).
    추측하지 않는다. 모르면 UNKNOWN 이라고 말한다.
    """
    now = now or now_utc()
    hint = hint or {}
    state = hint.get("state")
    if state in (AVAILABLE, RATE_LIMITED, OFFLINE, UNKNOWN):
        out = {"agent": agent, "state": state, "why": hint.get("why", "")}
        if state == RATE_LIMITED and hint.get("resets_at"):
            out["resets_at"] = hint["resets_at"]
        return out
    return {"agent": agent, "state": UNKNOWN, "why": "가용성 정보를 얻지 못했다"}


def wait_deadline(state: str, started: datetime | None = None) -> datetime:
    """이 상태의 상대를 언제까지 기다릴지. 무한 대기는 없다."""
    started = started or now_utc()
    return started + timedelta(seconds=WAIT_SECONDS.get(state, 300))


# ── BLOCKED 관리 ─────────────────────────────────────────────────────────────
def classify_blocks(blocks: list[dict], now: datetime | None = None) -> dict:
    """미해결 BLOCKED 를 살아있는 것과 만료된 것으로 가른다.

    주인 없고 만료도 없는 BLOCKED 는 무기한 거부권이 된다.
    실제로 이 프로젝트에서 018·021 은 구현이 끝난 뒤에도 '미응답' 으로 남아
    아무도 손대지 않은 채 진행을 막고 있었다.
    """
    now = now or now_utc()
    live, expired = [], []
    for b in blocks:
        raised = b.get("raised_at")
        ttl = int(b.get("ttl_seconds") or BLOCK_TTL_SECONDS)
        try:
            dt = datetime.fromisoformat(str(raised).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            # 시각을 알 수 없는 BLOCKED 는 만료를 계산할 수 없다.
            # 그렇다고 영원히 유효하다고 보지 않는다. 사용자 판단 대상으로 올린다.
            expired.append({**b, "why_expired": "제기 시각이 없어 유효기간을 계산할 수 없다"})
            continue
        if (now - dt).total_seconds() > ttl:
            expired.append({**b, "why_expired": f"{ttl // 3600}시간 경과"})
        else:
            live.append(b)
    return {"live": live, "expired": expired}


# ── 결정 ─────────────────────────────────────────────────────────────────────
def decide(
    topic: str,
    votes: dict,
    avail: dict,
    action_kind: str = "local",
    user_approved: bool = False,
    blocks: list[dict] | None = None,
    started: datetime | None = None,
    now: datetime | None = None,
    circuit: dict | None = None,
) -> dict:
    """하나의 안건을 판정한다. 교착으로 끝나지 않는 것이 이 함수의 계약이다.

    votes  {member: "AGREE"|"REJECT"|"ABSTAIN"}
    avail  {member: availability() 결과}
    """
    # 등록되지 않은 이름을 찬성표에 더하면 전체 구성원 과반이라는 경계가 무너진다.
    # 잘못된 표를 기권으로 바꾸지도 않는다. 호출자가 입력을 바로잡아야 한다.
    if any(member not in MEMBERS for member in votes):
        raise ValueError("votes contains an unregistered member")
    if any(value not in ("AGREE", "REJECT", "ABSTAIN") for value in votes.values()):
        raise ValueError("votes contains an invalid vote value")

    now = now or now_utc()
    started = started or now
    blocks = blocks or []
    circuit = circuit or {}
    q = quorum_size()

    # 마감이 지난 상대는 기권으로 확정한다. 동의도 거부도 아니다.
    effective, waiting, abstained = dict(votes), [], []
    for m in MEMBERS:
        if m in votes:
            continue
        st = avail.get(m, {}).get("state", UNKNOWN)
        if circuit.get(m, 0) >= CIRCUIT_OPEN_AFTER:
            effective[m] = "ABSTAIN"
            abstained.append((m, f"연속 {circuit[m]}회 무응답 — 회로 차단"))
            continue
        deadline = wait_deadline(st, started)
        if now >= deadline:
            effective[m] = "ABSTAIN"
            abstained.append((m, f"{st} 상태로 마감({deadline.strftime('%H:%M')}) 경과"))
        else:
            waiting.append((m, st, deadline))

    agree = [m for m, v in effective.items() if v == "AGREE"]
    reject = [m for m, v in effective.items() if v == "REJECT"]
    abst = [m for m, v in effective.items() if v == "ABSTAIN"]

    out = {
        "topic": topic, "at": now.isoformat(), "N": len(MEMBERS),
        "quorum_required": q, "action_kind": action_kind,
        "agree": sorted(agree), "reject": sorted(reject), "abstain": sorted(abst),
        "waiting": [{"agent": m, "state": s, "until": d.isoformat()} for m, s, d in waiting],
        "abstain_reasons": [{"agent": m, "why": w} for m, w in abstained],
    }

    # 1) 살아있는 BLOCKED 가 있으면 막힌다. 단 만료된 것은 막지 못한다.
    split = classify_blocks(blocks, now=now)
    out["blocks_live"] = split["live"]
    out["blocks_expired"] = split["expired"]
    if split["live"]:
        out.update(decision="BLOCKED",
                   reason="유효한 진행 막힘 %d건: %s" % (
                       len(split["live"]),
                       ", ".join(str(b.get("id", "?")) for b in split["live"])),
                   next_step="해당 항목의 소유자가 해소하거나 사용자에게 올린다")
        return out
    if split["expired"]:
        out.update(decision="ESCALATE_TO_USER",
                   reason="유효기간이 지난 진행 막힘 %d건이 방치돼 있다" % len(split["expired"]),
                   next_step="사용자가 해소·연장·폐기 중 하나를 정해야 한다. "
                             "주인 없는 거부권을 그대로 두지 않는다")
        return out

    # 2) 되돌릴 수 없는 행위는 표로 우회할 수 없다. 순서상 여기서 먼저 막는다.
    if action_kind in IRREVERSIBLE and not user_approved:
        out.update(decision="NEEDS_USER_APPROVAL",
                   reason=f"'{action_kind}' 는 되돌릴 수 없다. 만장일치도 이를 갈음하지 못한다",
                   next_step="사용자에게 위험과 대안을 설명하고 명시 승인을 받는다")
        return out

    # 3) 반대가 있으면 진행하지 않는다. 반대는 부재와 다르다 — 사람이 실제로 낸 표다.
    if reject:
        out.update(decision="REJECTED",
                   reason="반대: %s" % ", ".join(sorted(reject)),
                   next_step="반대 사유를 처리한 뒤 재상정한다")
        return out

    # 4) 아직 마감 전인 상대가 있으면 기다린다. 단 언제까지인지 말한다.
    if waiting and len(agree) < q:
        soonest = min(d for _, _, d in waiting)
        out.update(decision="WAITING",
                   reason="찬성 %d표 < 정족수 %d표. 응답 대기 중: %s" % (
                       len(agree), q, ", ".join(m for m, _, _ in waiting)),
                   next_step=f"{soonest.strftime('%H:%M')} 까지 기다린다. "
                             "그 뒤에는 기권으로 확정하고 다음 단계로 간다")
        return out

    # 5) 정족수를 채웠다.
    if len(agree) >= q:
        out.update(decision="APPROVED",
                   reason="찬성 %d표 >= 정족수 %d표 (기권 %d)" % (len(agree), q, len(abst)),
                   next_step="실행한다")
        return out

    # 6) 여기까지 왔다면 기다려도 정족수를 못 채운다.
    #    이때 침묵하는 것이 가장 위험하다. 아무도 결정하지 않는 것은 안전이 아니다.
    out.update(decision="ESCALATE_TO_USER",
               reason="찬성 %d표, 기권 %d표. 기다려도 정족수 %d표를 채울 수 없다" % (
                   len(agree), len(abst), q),
               next_step="사용자에게 올린다. 사용자는 언제나 유효한 결정권자이며 "
                         "교착 상태보다 낫다. 기권한 도구와 사유를 함께 보고한다")
    return out


def explain(result: dict) -> str:
    """사용자에게 보여줄 한국어 설명. 용어를 그대로 던지지 않는다."""
    ko = {
        "APPROVED": "진행해도 됩니다",
        "REJECTED": "반대가 있어 진행하지 않습니다",
        "BLOCKED": "막혀 있습니다",
        "WAITING": "응답을 기다리는 중입니다",
        "ESCALATE_TO_USER": "제가 정할 수 없어 사용자 판단이 필요합니다",
        "NEEDS_USER_APPROVAL": "되돌릴 수 없는 일이라 승인이 필요합니다",
    }
    d = result.get("decision", "?")
    lines = [f"판정: {ko.get(d, d)} ({d})",
             f"  왜: {result.get('reason', '')}",
             f"  다음: {result.get('next_step', '')}"]
    if result.get("abstain_reasons"):
        lines.append("  기권한 도구:")
        for a in result["abstain_reasons"]:
            lines.append(f"    - {a['agent']}: {a['why']}")
    if result.get("waiting"):
        for w in result["waiting"]:
            lines.append(f"  대기: {w['agent']} ({w['state']}) — {w['until'][:16]} 까지")
    return "\n".join(lines)


# ── 자체검증 ─────────────────────────────────────────────────────────────────
def selftest() -> int:
    t0 = datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc)
    ok, fail = 0, 0

    def case(name, expect, **kw):
        nonlocal ok, fail
        r = decide(**kw)
        got = r["decision"]
        if got == expect:
            ok += 1
            print(f"  통과  {name}")
        else:
            fail += 1
            print(f"  실패  {name}: 기대 {expect}, 실제 {got} ({r.get('reason')})")

    A = {m: {"state": AVAILABLE} for m in MEMBERS}
    LIMITED = {"codex": {"state": RATE_LIMITED}, "claude": {"state": AVAILABLE},
               "antigravity": {"state": OFFLINE}}

    print("교착 없는 의사결정 자체검증")

    case("전원 찬성 -> 승인", "APPROVED",
         topic="t", votes={m: "AGREE" for m in MEMBERS}, avail=A, now=t0)

    case("과반 찬성 + 기권 1 -> 승인", "APPROVED",
         topic="t", votes={"claude": "AGREE", "codex": "AGREE"}, avail=A,
         started=t0, now=t0 + timedelta(hours=2))

    # 핵심: 혼자 남아도 교착으로 끝나지 않는다
    case("혼자 찬성 + 나머지 부재 -> 사용자 판단", "ESCALATE_TO_USER",
         topic="t", votes={"claude": "AGREE"}, avail=LIMITED,
         started=t0, now=t0 + timedelta(hours=2))

    case("마감 전이면 기다린다", "WAITING",
         topic="t", votes={"claude": "AGREE"}, avail=A,
         started=t0, now=t0 + timedelta(seconds=60))

    case("꺼진 도구는 기다리지 않는다", "ESCALATE_TO_USER",
         topic="t", votes={"claude": "AGREE"},
         avail={"claude": {"state": AVAILABLE}, "codex": {"state": OFFLINE},
                "antigravity": {"state": OFFLINE}},
         started=t0, now=t0 + timedelta(seconds=200))

    case("회로 차단 -> 무한 재시도 안 함", "ESCALATE_TO_USER",
         topic="t", votes={"claude": "AGREE"}, avail=A,
         circuit={"codex": 3, "antigravity": 3}, started=t0, now=t0)

    case("반대는 부재와 다르다", "REJECTED",
         topic="t", votes={"claude": "AGREE", "codex": "REJECT", "antigravity": "AGREE"},
         avail=A, now=t0)

    case("되돌릴 수 없으면 만장일치도 안 된다", "NEEDS_USER_APPROVAL",
         topic="t", votes={m: "AGREE" for m in MEMBERS}, avail=A,
         action_kind="push", now=t0)

    case("사용자 승인 있으면 진행", "APPROVED",
         topic="t", votes={m: "AGREE" for m in MEMBERS}, avail=A,
         action_kind="push", user_approved=True, now=t0)

    case("살아있는 막힘은 막는다", "BLOCKED",
         topic="t", votes={m: "AGREE" for m in MEMBERS}, avail=A,
         blocks=[{"id": "B1", "raised_at": t0.isoformat()}], now=t0)

    # 핵심: 만료된 막힘이 영구 거부권이 되지 않는다
    case("만료된 막힘은 사용자에게 올린다", "ESCALATE_TO_USER",
         topic="t", votes={m: "AGREE" for m in MEMBERS}, avail=A,
         blocks=[{"id": "B1", "raised_at": t0.isoformat()}],
         now=t0 + timedelta(hours=30))

    case("시각 없는 막힘도 영구 거부권이 아니다", "ESCALATE_TO_USER",
         topic="t", votes={m: "AGREE" for m in MEMBERS}, avail=A,
         blocks=[{"id": "B-old"}], now=t0)

    print(f"\n결과: {ok}/{ok + fail} 통과")
    if fail == 0:
        print("\n예시 출력:")
        r = decide(topic="C1 마감", votes={"claude": "AGREE"}, avail=LIMITED,
                   started=t0, now=t0 + timedelta(hours=2))
        print(explain(r))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
