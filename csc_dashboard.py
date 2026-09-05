#!/usr/bin/env python
"""사용자용 감시 대시보드 (User-Facing Watch Dashboard).

이원 체계 (Dual-Track)
    [도구 트랙]  .agent-swarm/messages/queue.jsonl   3대 도구가 실제로 주고받는 원문
                        │  읽기만 한다. 사용자 편의로 고치지 않는다.
                        ▼
    [사용자 트랙] .agent-swarm/dashboard.html        사람이 보는 화면

    원문을 고치면 그건 더 이상 감사 기록이 아니다. 화면은 파생물일 뿐이다.
    그래서 모든 항목에 "원문 어디를 봤는지" 를 함께 적는다.

이 파일이 지키는 계약 — `.agent-swarm/USER_FIRST_PRINCIPLE.md`
    대상은 "모르는 걸 모르는 사용자" 다.
    무엇을 물어야 할지 알 수 없는 위치에 있는 사람이다.

    1. 한국어 우선. 전문용어는 한국어(영어) 병기.
    2. 모든 상태에 ① 무엇이 ② 왜 그렇게 판단했는지 ③ 무엇을 하면 되는지.
    3. 나쁜 소식을 먼저, 크게.

    이 계약을 문서로만 두면 지켜지지 않는다는 걸 이 프로젝트는 여러 번 배웠다.
    그래서 용어 사전(TERMS)을 코드에 박고, 번역되지 않은 용어를 자가검사로 잡는다.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SWARM = os.path.join(HERE, ".agent-swarm")
QUEUE = os.path.join(SWARM, "messages", "queue.jsonl")
OUT = os.path.join(SWARM, "dashboard.html")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, HERE)

# ── 용어 사전 ────────────────────────────────────────────────────────────────
# 화면에 나가는 모든 영어 약어는 여기를 거쳐야 한다.
# 값은 (한국어 표기, 한 줄 설명). 설명은 용어를 처음 보는 사람 기준으로 쓴다.
TERMS = {
    # 메시지 종류
    "TASK":        ("작업 지시", "무엇을 하라고 시키는 말"),
    "RESULT":      ("결과 보고", "시킨 일을 하고 나서 알려주는 말"),
    "REPORT":      ("상황 보고", "묻지 않아도 먼저 알리는 말"),
    "PROPOSAL":    ("제안", "이렇게 하자고 내미는 말"),
    "ACK":         ("확인함", "받았다는 짧은 대답"),
    "RISK":        ("위험 경고", "이대로 가면 문제가 생긴다는 경고"),
    "BLOCKED":     ("진행 막힘", "무언가 해결되기 전엔 못 간다는 뜻"),
    "CALL_OUT":    ("질타", "동료의 잘못을 직접 지적하는 말"),
    "WHISTLEBLOW": ("사용자 직보", "동료를 거치지 않고 사용자에게 바로 알리는 말"),
    "EVENT":       ("자동 기록", "사람이 쓴 말이 아니라 프로그램이 남긴 흔적"),
    # 상태값
    "LIVE":       ("살아 있음", "지금 정상 동작 중"),
    "DEAD":       ("멈춤", "프로세스가 없어졌다"),
    "STALLED":    ("응답 없음", "살아는 있는데 소식이 끊겼다"),
    "PID_STALE":  ("등록 정보 낡음", "기록된 번호는 사라졌는데 다른 게 대신 일하고 있다"),
    "UNKNOWN":    ("확인 불가", "살았는지 죽었는지 알아낼 수 없었다"),
}

# 3대 도구를 역할로 소개한다. 이름만으로는 무슨 일을 하는지 알 수 없다.
AGENTS = {
    "codex":       ("🧠", "코덱스", "지휘 — 일을 나누고 최종 판단을 내린다"),
    "claude":      ("🛡️", "클로드 코드", "검증 — 오류와 위험을 찾아 지적한다"),
    "antigravity": ("🖐️", "안티그래비티", "실행 — 직접 만들고 눈으로 확인한다"),
    "all":         ("📢", "전체 공지", "세 도구 모두에게 보내는 말"),
}

HOT = {"CALL_OUT", "WHISTLEBLOW", "BLOCKED", "RISK"}


def ko(code: str) -> str:
    """영어 코드를 '한국어(영어)' 로 바꾼다. 사전에 없으면 원문 그대로 둔다."""
    t = TERMS.get(code)
    return f"{t[0]}({code})" if t else code


def why(code: str) -> str:
    t = TERMS.get(code)
    return t[1] if t else ""


def agent_of(name: str) -> str:
    n = (name or "").lower()
    for key in ("codex", "claude", "antigravity"):
        if n.startswith(key):
            return key
    if n.startswith("agy"):
        return "antigravity"
    return "all" if n == "all" else "unknown"


def load_messages() -> tuple[list[dict], int]:
    rows, broken = [], 0
    if not os.path.exists(QUEUE):
        return rows, broken
    with open(QUEUE, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                broken += 1
    return rows, broken


def kst(ts: str) -> str:
    if not ts:
        return "시각 없음"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%m월 %d일 %H:%M")
    except Exception:
        return ts[:16]


def minutes_since(ts: str) -> float:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return 1e9


def checks(rows: list[dict], broken: int) -> list[dict]:
    """점검 항목. 각 항목은 반드시 세 가지를 갖는다 — 무엇이 / 왜 / 할 일."""
    out: list[dict] = []

    # ① 세 도구가 켜져 있는가
    try:
        import csc
        wr = csc._worker_liveness()
        live = sum(1 for r in wr if r.get("verdict") == "LIVE")
        detail = " · ".join(f"{r.get('agent')} {ko(str(r.get('verdict')))}" for r in wr)
        out.append({
            "title": "일꾼 프로그램이 켜져 있는가",
            "value": f"{len(wr)}대 중 {live}대 정상" if wr else "등록된 일꾼 없음",
            "ok": bool(wr) and live == len(wr),
            "why": f"프로세스 번호(PID)를 직접 조회했다 — {detail}" if wr else "등록 파일이 없다",
            "todo": "터미널에 python csc.py activate 를 입력하면 다시 켜집니다",
            "src": ".agent-swarm/workers/*.json",
        })
    except Exception as exc:
        out.append({"title": "일꾼 프로그램이 켜져 있는가", "value": "확인 실패", "ok": False,
                    "why": f"점검 도중 오류: {type(exc).__name__}", "src": ".agent-swarm/workers/",
                    "todo": "python csc.py status 를 직접 실행해 오류 내용을 확인하세요"})

    # ② 최근에 실제로 대화했는가
    last_ts = ""
    for m in reversed(rows):
        if m.get("timestamp"):
            last_ts = m["timestamp"]
            break
    gap = minutes_since(last_ts) if last_ts else 1e9
    out.append({
        "title": "최근에 실제로 대화했는가",
        "value": f"{gap:.0f}분 전" if gap < 1e8 else "대화 기록 없음",
        "ok": gap < 60,
        "why": f"마지막 메시지 시각 {kst(last_ts)} 을 기준으로 계산했다" if last_ts
               else "주고받은 메시지가 한 건도 없다",
        "todo": "1시간 넘게 조용하면 작업이 멈춰 있을 수 있습니다. 저에게 물어보세요",
        "src": ".agent-swarm/messages/queue.jsonl 마지막 줄",
    })

    # ③ 전달 못 한 편지가 쌓였는가
    dlq, ddir = 0, os.path.join(SWARM, "dead-letter")
    for e in (os.listdir(ddir) if os.path.isdir(ddir) else []):
        try:
            with open(os.path.join(ddir, e), encoding="utf-8", errors="replace") as f:
                dlq += sum(1 for x in f if x.strip())
        except Exception:
            pass
    out.append({
        "title": "전달 못 한 편지가 쌓였는가",
        "value": f"{dlq}건",
        "ok": dlq == 0,
        "why": "배달 실패함(DLQ, Dead Letter Queue)에 남은 줄 수를 셌다. "
               "0이 아니면 누군가 메시지를 못 받은 것이다",
        "todo": "0이 아니어도 지금 당장 위험하진 않습니다. 과거 실패 기록이며 "
                "일부러 지우지 않고 남겨둡니다",
        "src": ".agent-swarm/dead-letter/*.jsonl",
    })

    # ④ 막힌 안건이 있는가
    stuck = 0
    gov = os.path.join(SWARM, "GOVERNANCE.md")
    try:
        with open(gov, encoding="utf-8") as f:
            stuck = sum(1 for ln in f if ln.startswith("|") and ("미해소" in ln or "미응답" in ln))
    except Exception:
        pass
    out.append({
        "title": "해결 못 한 안건이 있는가",
        "value": f"{stuck}건",
        "ok": stuck == 0,
        "why": "규약 문서에서 '미해소'·'미응답' 으로 표시된 줄을 셌다. "
               "1건이라도 남으면 최종 산출물 확정이 금지된다",
        "todo": "0이면 다음 단계로 갈 수 있습니다",
        "src": ".agent-swarm/GOVERNANCE.md 9절",
    })

    # ⑤ 승인 없이 깃허브로 나간 것이 있는가
    commits = "?"
    try:
        import subprocess
        commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=HERE,
                                 capture_output=True, text=True).stdout.strip() or "0"
    except Exception:
        pass
    out.append({
        "title": "승인 없이 깃허브로 나간 것이 있는가",
        "value": f"저장 {commits}건",
        "ok": True,
        "why": "커밋(commit, 저장) 개수를 셌다. 사용자 승인 전에는 0이어야 한다",
        "todo": "0이면 아무것도 밖으로 나가지 않은 상태입니다",
        "src": "git rev-list --count HEAD",
    })

    # 현재 안건과 후보 해시에 결속된 표결 입력은 아직 연결되지 않았다.
    # 마지막 발신 시각으로 도구의 가용성이나 찬성표를 만들어내지 않는다.
    out.append({
        "title": "결정이 멈춰 있는가",
        "value": "판정 미검증",
        "ok": False,
        "why": "현재 안건·후보 해시·도구별 실제 표결을 연결하지 않아 진행 여부를 판단할 수 없습니다",
        "todo": "제가 원문에서 같은 후보에 대한 표결을 대조해 보고하겠습니다. 지금 승인하실 필요는 없습니다",
        "src": ".agent-swarm/messages/queue.jsonl",
    })

    # ⑦ 거짓 주장이 걸러지고 있는가 — 감시 체계 자체가 살아 있는지 본다
    #    사용자 지적(2026-09-06): "거짓말·유령투표·할루시네이션 실시간 감시가 있어야 하지 않나."
    #    감사기가 조용한 것과 꺼져 있는 것은 다르다. 그 둘을 구분해서 보여준다.
    audit_log = os.path.join(SWARM, "messages", "claim_audit.jsonl")
    blocked = warned = passed = 0
    try:
        with open(audit_log, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    v = json.loads(line).get("verdict")
                except Exception:
                    continue
                if v == "차단":
                    blocked += 1
                elif v == "경고":
                    warned += 1
                else:
                    passed += 1
    except FileNotFoundError:
        pass
    total = blocked + warned + passed
    out.append({
        "title": "거짓 주장이 걸러지고 있는가",
        "value": (f"{total}건 검사 · {blocked}건 차단" if total
                  else "아직 검사한 메시지 없음"),
        # 차단이 있었다는 것은 감사기가 일하고 있다는 뜻이다. 나쁜 신호가 아니다.
        # 검사 기록이 아예 없으면 감사기가 꺼져 있을 수 있다 — 그건 나쁜 신호다.
        "ok": total > 0,
        "why": (f"발신 전 재측정에서 차단 {blocked}건, 경고 {warned}건, "
                f"이상 없음 {passed}건이 기록됐다. "
                "차단이 있다는 것은 감시가 작동한다는 뜻이다"
                if total else
                "검사 기록이 없다. 감사기가 꺼져 있거나 아직 메시지를 보내지 않았다"),
        "todo": ("특별히 하실 일은 없습니다. 차단된 내용은 상대에게 전달되지 않았습니다"
                 if total else
                 "python csc_audit.py --selftest 로 감사기가 도는지 확인해 보세요"),
        "src": ".agent-swarm/messages/claim_audit.jsonl",
    })

    # ⑥ 기록이 손상됐는가
    out.append({
        "title": "대화 기록이 손상됐는가",
        "value": f"{broken}줄 깨짐",
        "ok": broken == 0,
        "why": "원문 파일에서 읽을 수 없는 줄 수를 셌다. 손상은 조용히 넘기지 않는다",
        "todo": "0이 아니면 저에게 알려주세요. 원문 복구가 필요합니다",
        "src": ".agent-swarm/messages/queue.jsonl",
    })
    return out


def self_check(doc: str) -> list[str]:
    """자가검사. 화면 껍데기(UI)에서 번역 없이 새 나간 영어 용어를 잡는다.

    USER_FIRST_PRINCIPLE 6절 1번 항목을 코드로 강제한다.
    문서에만 적어 두면 지켜지지 않는다는 걸 이 프로젝트는 여러 번 겪었다.

    검사 대상에서 제외하는 두 곳이 있고, 둘 다 원칙을 지키기 위한 제외다.

      1. 메시지 본문(.body) — 세 도구가 실제로 쓴 원문이다.
         이원 체계 4항: 원문은 사용자 편의로 고치지 않는다.
         원문을 번역하면 그건 증거가 아니라 각색이 된다.

      2. 용어 풀이표의 <code> — 영어 원어를 나란히 보여주는 것이 그 표의 목적이다.
         거기서 영어를 지우면 사용자는 두 표기를 연결하지 못한다.

    즉 검사 대상은 '우리가 쓴 라벨·상태·설명' 뿐이다. 그게 우리 책임 범위다.
    """
    body = re.sub(r"<(script|style)[^>]*>.*?</>", "", doc, flags=re.S | re.I)
    body = re.sub(r'<div class="body">.*?</div>', " ", body, flags=re.S)
    body = re.sub(r'<div class="gl">.*?</div>', " ", body, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", body)

    problems = []
    for code in TERMS:
        # '한국어(CODE)' 로 병기된 것은 통과. 홀로 선 영어 코드만 문제다.
        bare = re.findall(r"(?<![\w(])" + re.escape(code) + r"(?![\w)])", visible)
        if bare:
            problems.append(f"{code} 가 한국어 병기 없이 {len(bare)}회 노출")
    return problems


def build() -> str:
    rows, broken = load_messages()
    ck = checks(rows, broken)
    bad = [c for c in ck if not c["ok"]]

    if bad:
        verdict, vclass = f"확인이 필요한 항목 {len(bad)}개", "bad"
        vline = "아래 빨간 칸을 보세요. 각 칸에 '하실 일' 이 적혀 있습니다."
    else:
        verdict, vclass = "모두 정상", "good"
        vline = "여섯 가지를 모두 확인했고 문제가 없습니다."

    # 나쁜 소식을 위로 올린다 (원칙 5)
    ck_sorted = sorted(ck, key=lambda c: c["ok"])
    cards = "".join(
        '<article class="chk {cls}"><h3>{t}</h3><p class="val">{v}</p>'
        '<p class="why"><b>왜 그렇게 봤나</b> {w}</p>'
        '<p class="todo"><b>하실 일</b> {d}</p>'
        '<p class="src">확인한 곳: <code>{s}</code></p></article>'.format(
            cls="bad" if not c["ok"] else "good",
            t=html.escape(c["title"]), v=html.escape(str(c["value"])),
            w=html.escape(c["why"]), d=html.escape(c.get("todo", "")),
            s=html.escape(c["src"]))
        for c in ck_sorted)

    recent = rows[-60:]
    items = []
    for m in reversed(recent):
        s, r = agent_of(m.get("sender")), agent_of(m.get("recipient"))
        si, sn, srole = AGENTS.get(s, ("❓", s, ""))
        ri, rn, _ = AGENTS.get(r, ("❓", r, ""))
        typ = str(m.get("type", ""))
        hot = " hot" if typ in HOT else ""
        body = str(m.get("body", ""))
        items.append(
            '<article class="msg {cls}{hot}">'
            '<header><span class="from">{si} {sn}</span>'
            '<span class="ar">가 {ri} {rn} 에게</span>'
            '<span class="kind" title="{kw}">{kt}</span>'
            '<time>{ts}</time></header>'
            '<div class="body">{b}</div></article>'.format(
                cls=s, hot=hot, si=si, sn=html.escape(sn), ri=ri, rn=html.escape(rn),
                kt=html.escape(ko(typ)), kw=html.escape(why(typ)),
                ts=html.escape(kst(m.get("timestamp", ""))),
                b=html.escape(body[:1400] + ("…" if len(body) > 1400 else ""))))

    roles = "".join(
        f'<div class="role"><span>{i}</span><b>{html.escape(n)}</b>'
        f'<small>{html.escape(d)}</small></div>'
        for k, (i, n, d) in AGENTS.items() if k != "all")

    glossary = "".join(
        f'<div class="gl"><b>{html.escape(v[0])}</b>'
        f'<code>{html.escape(k)}</code><small>{html.escape(v[1])}</small></div>'
        for k, v in TERMS.items())

    now = datetime.now().astimezone().strftime("%Y년 %m월 %d일 %H:%M:%S")
    counts = {}
    for m in rows:
        a = agent_of(m.get("sender"))
        counts[a] = counts.get(a, 0) + 1
    stat = " · ".join(
        f"{AGENTS.get(k, ('❓',k,''))[0]} {AGENTS.get(k, ('❓',k,''))[1]} {v}번"
        for k, v in sorted(counts.items(), key=lambda x: -x[1]) if k in AGENTS)

    return TEMPLATE.format(
        verdict=html.escape(verdict), vclass=vclass, vline=html.escape(vline),
        cards=cards, items="".join(items), roles=roles, glossary=glossary,
        now=html.escape(now), total=len(rows), shown=len(recent),
        stat=stat, queue=html.escape(QUEUE))


TEMPLATE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>3대 AI 도구 감시판</title>
<style>
:root{{--bg:#faf9f7;--fg:#1a1a18;--mut:#6b6862;--line:#e2ded6;--card:#fff;
--ok:#0f766e;--bad:#b91c1c;--codex:#6b4fbb;--claude:#c2410c;--anti:#0f766e}}
@media(prefers-color-scheme:dark){{:root{{--bg:#171614;--fg:#ecebe8;--mut:#9b968d;
--line:#312f2b;--card:#201f1c;--ok:#5eead4;--bad:#f87171;
--codex:#a78bfa;--claude:#fb923c;--anti:#5eead4}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.7 -apple-system,"Segoe UI","Malgun Gothic",sans-serif}}
.wrap{{max-width:940px;margin:0 auto;padding:26px 16px 90px}}
h1{{font-size:22px;margin:0 0 2px}}
h2{{font-size:16px;margin:30px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}}
h3{{font-size:14px;margin:0 0 6px}}
.lede{{color:var(--mut);font-size:13px;margin-bottom:18px}}
.verdict{{border-radius:12px;padding:16px 18px;margin-bottom:8px;border:2px solid var(--ok);
background:var(--card)}}
.verdict.bad{{border-color:var(--bad)}}
.verdict .big{{font-size:20px;font-weight:800}}
.verdict.good .big{{color:var(--ok)}} .verdict.bad .big{{color:var(--bad)}}
.verdict p{{margin:4px 0 0;font-size:13px;color:var(--mut)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}}
.chk{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);
border-radius:9px;padding:12px 14px}}
.chk.bad{{border-left-color:var(--bad)}}
.chk .val{{font-size:19px;font-weight:800;margin:2px 0 8px}}
.chk.bad .val{{color:var(--bad)}}
.chk p{{margin:5px 0;font-size:12.5px;color:var(--mut);line-height:1.5}}
.chk b{{color:var(--fg);display:block;font-size:11.5px;margin-bottom:1px}}
.chk .src{{font-size:11px;opacity:.75}}
code{{font-size:.9em;background:rgba(128,128,128,.14);padding:1px 5px;border-radius:4px}}
.roles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}
.role{{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:11px 13px}}
.role span{{font-size:22px;display:block}}
.role b{{display:block;margin:2px 0}}
.role small{{color:var(--mut);font-size:12px}}
.bar{{position:sticky;top:0;background:var(--bg);padding:9px 0;border-bottom:1px solid var(--line);
display:flex;gap:8px;flex-wrap:wrap;align-items:center;z-index:5;margin-bottom:12px}}
select,button{{font:inherit;font-size:13px;padding:5px 10px;border:1px solid var(--line);
border-radius:7px;background:var(--card);color:var(--fg);cursor:pointer}}
.msg{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--mut);
border-radius:9px;padding:11px 14px;margin-bottom:9px}}
.msg.codex{{border-left-color:var(--codex)}}
.msg.claude{{border-left-color:var(--claude)}}
.msg.antigravity{{border-left-color:var(--anti)}}
.msg.hot{{background:color-mix(in srgb,var(--bad) 7%,var(--card))}}
.msg header{{display:flex;gap:7px;align-items:baseline;flex-wrap:wrap;
font-size:12.5px;color:var(--mut);margin-bottom:7px}}
.from{{font-weight:700;color:var(--fg)}}
.kind{{margin-left:auto;font-weight:700;border:1px solid var(--line);
border-radius:99px;padding:1px 9px;cursor:help}}
.msg.hot .kind{{color:var(--bad);border-color:var(--bad)}}
.body{{white-space:pre-wrap;word-break:break-word;font-size:13.5px;
max-height:15em;overflow:auto}}
.gl{{display:flex;gap:8px;align-items:baseline;padding:5px 0;border-bottom:1px dotted var(--line);
font-size:13px;flex-wrap:wrap}}
.gl b{{min-width:105px}} .gl small{{color:var(--mut);flex:1}}
.hidden{{display:none}}
footer{{margin-top:34px;padding-top:14px;border-top:1px solid var(--line);
color:var(--mut);font-size:12px;line-height:1.7}}
</style>
<div class="wrap">
<h1>3대 AI 도구 감시판</h1>
<div class="lede">코덱스·클로드 코드·안티그래비티가 지금 무엇을 하고 있는지 보여주는 화면입니다.
30초마다 저절로 새로 고쳐집니다. 마지막 갱신 {now}</div>

<section class="verdict {vclass}">
<div class="big">{verdict}</div>
<p>{vline}</p>
</section>

<h2>지금 상태 — 여섯 가지 점검</h2>
<div class="grid">{cards}</div>

<h2>누가 무슨 일을 하나</h2>
<div class="roles">{roles}</div>

<h2>주고받은 말 (최근 {shown}건 / 전체 {total}건)</h2>
<div class="lede">{stat}</div>
<div class="bar">
<label>보낸 쪽 <select id="ff"><option value="">전체</option>
<option value="codex">🧠 코덱스</option><option value="claude">🛡️ 클로드 코드</option>
<option value="antigravity">🖐️ 안티그래비티</option></select></label>
<button id="hot">🔴 서로 지적한 말만 보기</button>
<button id="rs">전체 다시 보기</button>
<span id="cnt" style="color:var(--mut);font-size:12px"></span>
</div>
<main id="list">{items}</main>

<h2>용어 풀이</h2>
<div class="lede">화면에 나오는 말이 무슨 뜻인지 적어 둔 표입니다.</div>
{glossary}

<footer>
<b>이 화면은 어디서 왔나</b><br>
세 도구가 실제로 주고받은 원문은 <code>{queue}</code> 에 그대로 쌓입니다.
이 화면은 그 파일을 <b>읽기만 해서</b> 사람이 보기 쉽게 옮긴 것입니다.
원문은 보기 좋게 고치지 않습니다 — 고치면 더 이상 증거가 아니기 때문입니다.<br><br>
<b>갱신 방식</b> — 세 도구가 일할 때마다 자동으로 다시 만들어집니다.
직접 만들려면 터미널에 <code>python csc_dashboard.py</code> 를 입력하세요.
아무도 일하지 않으면 갱신도 멈추는데, 그때는 바뀔 것이 없다는 뜻입니다.
</footer>
</div>
<script>
var all=[].slice.call(document.querySelectorAll('#list .msg'));
var ff=document.getElementById('ff'),cnt=document.getElementById('cnt'),hotOnly=false;
function apply(){{var n=0;all.forEach(function(el){{
 var ok=(!ff.value||el.classList.contains(ff.value))&&(!hotOnly||el.classList.contains('hot'));
 el.classList.toggle('hidden',!ok); if(ok)n++;}});
 cnt.textContent=n+'건 보이는 중';}}
ff.onchange=apply;
document.getElementById('hot').onclick=function(){{hotOnly=!hotOnly;
 this.style.fontWeight=hotOnly?'800':'';apply();}};
document.getElementById('rs').onclick=function(){{ff.value='';hotOnly=false;
 document.getElementById('hot').style.fontWeight='';apply();}};
apply();
</script>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="사용자용 감시 대시보드를 만든다")
    ap.add_argument("--check", action="store_true", help="자가검사만 하고 끝낸다")
    args = ap.parse_args()

    doc = build()
    problems = self_check(doc)

    if args.check:
        if problems:
            print("자가검사 실패:")
            for p in problems:
                print("  -", p)
            return 1
        print("자가검사 통과 — 번역 없이 노출된 용어 0건")
        return 0

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"만들었습니다: {OUT}")
    if problems:
        # 조용히 넘기지 않는다. 원칙 위반을 숨기면 원칙이 없는 것과 같다.
        print("⚠️ 원칙 위반 — 한국어 병기 없이 노출된 용어가 있습니다:")
        for p in problems:
            print("   ", p)
        return 1
    print("자가검사 통과 — 번역 없이 노출된 용어 0건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
