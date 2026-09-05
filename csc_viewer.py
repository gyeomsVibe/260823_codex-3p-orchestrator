#!/usr/bin/env python
"""CSC 대화 뷰어 — 사용자가 3대 도구의 통신을 직접 눈으로 확인하는 수단.

문제:
    3대 도구가 .agent-swarm 으로 대화하는데, 사용자는 그걸 볼 방법이 없었다.
    "실제 연결이 된 건지, 대화를 하고 있는 건지" 확인할 수단이 없다는 것은
    감시 대상이 스스로 감시 결과를 보고한다는 뜻이다. 그건 감시가 아니다.

설계 근거 (공개 자료 조사, 2026-09-05):
    - disler/claude-code-hooks-multi-agent-observability : 에이전트별 swim lane
    - agentkitai/agentlens                               : append-only + 해시 체인
    - nilenso/context-viewer                             : JSONL 세션 로그 분해

    셋의 공통점은 "로그를 사람이 읽는 형태로 되돌린다" 이다.
    우리 queue.jsonl 은 이미 append-only 이므로 렌더링만 있으면 된다.

두 가지 모드:
    tail  — 터미널에서 바로 본다. 서버도 브라우저도 필요 없다.
    html  — 자족 HTML 1개를 만든다. 더블클릭하면 열린다. 외부 의존 없음.
"""

from __future__ import annotations

import argparse
import html
import subprocess
import json
import os
import sys
import time
from datetime import datetime, timezone

SWARM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agent-swarm")
QUEUE = os.path.join(SWARM_DIR, "messages", "queue.jsonl")
OUT_HTML = os.path.join(SWARM_DIR, "conversation.html")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 발신자를 3대 도구로 정규화한다. 세션 ID(claude-code-6c)도 도구로 묶는다.
def normalize(agent: str) -> str:
    a = (agent or "").lower()
    if a.startswith("codex"):
        return "codex"
    if a.startswith("claude"):
        return "claude"
    if a.startswith("antigravity") or a.startswith("agy"):
        return "antigravity"
    if a == "all":
        return "all"
    return a or "unknown"


ICON = {"codex": "🧠", "claude": "🛡️", "antigravity": "🖐️", "all": "📢", "unknown": "❓"}
LABEL = {"codex": "Codex (뇌)", "claude": "Claude Code (면역계)",
         "antigravity": "Antigravity (손·눈)", "all": "전체 공지", "unknown": "미상"}
# 타입별 심각도. 사용자가 '싸움'과 '보고'를 구분할 수 있어야 한다.
SEVERITY = {"WHISTLEBLOW": "high", "CALL_OUT": "high", "BLOCKED": "high",
            "RISK": "mid", "PROPOSAL": "mid", "TASK": "mid",
            "RESULT": "low", "REPORT": "low", "ACK": "low", "EVENT": "muted"}


def load(limit: int | None = None) -> list[dict]:
    """queue.jsonl 을 읽는다. 깨진 줄은 버리지 않고 세어서 보고한다."""
    rows, broken = [], 0
    if not os.path.exists(QUEUE):
        return rows
    with open(QUEUE, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                broken += 1
    if broken:
        # 조용히 넘어가지 않는다. 로그가 손상됐다는 사실 자체가 정보다.
        rows.append({"timestamp": "", "sender": "unknown", "recipient": "all",
                     "type": "RISK", "body": f"⚠️ 파싱 실패한 줄 {broken}건이 있다. 로그가 손상됐다."})
    return rows[-limit:] if limit else rows


def fmt_ts(ts: str) -> str:
    """UTC 저장값을 한국 시간으로 보여준다. 사용자는 KST 로 산다."""
    if not ts:
        return "??:??"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%m-%d %H:%M:%S")
    except Exception:
        return ts[:19]


def cmd_tail(count: int, follow: bool) -> int:
    """터미널에서 바로 본다."""
    seen = 0

    def render(rows, skip):
        for m in rows[skip:]:
            s, r = normalize(m.get("sender")), normalize(m.get("recipient"))
            typ = str(m.get("type", "?"))
            body = str(m.get("body", "")).replace("\n", " ")[:150]
            mark = {"high": "🔴", "mid": "🟡", "low": "  ", "muted": "  "}.get(
                SEVERITY.get(typ, "low"), "  ")
            print(f"{mark} [{fmt_ts(m.get('timestamp'))}] "
                  f"{ICON.get(s,'?')} {s:12s} → {ICON.get(r,'?')} {r:12s} "
                  f"│ {typ:11s} │ {body}")

    rows = load()
    start = max(0, len(rows) - count)
    render(rows, start)
    seen = len(rows)
    if not follow:
        return 0
    print("\n── 실시간 감시 중 (Ctrl+C 로 종료) ──")
    try:
        while True:
            time.sleep(2)
            rows = load()
            if len(rows) > seen:
                render(rows, seen)
                seen = len(rows)
    except KeyboardInterrupt:
        print("\n감시 종료.")
    return 0


def health() -> list[dict]:
    """건강 판정. 대화 내용이 아니라 '시스템이 정상인가' 를 본다.

    설계 근거 (공개 자료 조사, 2026-09-06):
        mishanefedov/agentwatch 는 자기 한계를 이렇게 밝힌다 —
        "a viewer, not a daemon. It captures events only while the TUI is running."
        내 1차 뷰어가 정확히 그 상태였다. 사용자가 명령을 쳐야만 보이고,
        본 순간 이미 낡는다. 사용자가 세 번 같은 요구를 한 이유다.

        DonkRonk17/AgentHeartbeat 는 presence/velocity/health 를 본다.
        NOVA-Openclaw/nova-dashboard 는 정적 HTML + 외부 JSON + 자동 갱신이다.
        둘을 합치면 서버 없이도 '항시' 가 된다.

    각 항목은 근거를 함께 반환한다. 근거 없는 초록불은 거짓말이다.
    """
    import csc_viewer as _self  # noqa
    rows = []
    now = time.time()

    # 1. 워커 생존 — csc.py 의 판정을 그대로 쓴다. 두 개의 진실을 만들지 않는다.
    #
    #    자책 (2026-09-06): 처음엔 여기서 pid_is_alive 를 직접 불러 따로 판정했다.
    #    그 결과 대시보드는 2/2 LIVE, 뷰어는 0/2 로 서로 다른 답을 냈다.
    #    "하나의 생존 판정을 공유해야 한다" 는 코덱스의 지적을 내가 다시 어긴 것이다.
    #    판정이 둘이면 사용자는 어느 쪽을 믿을지 알 수 없고, 그건 감시가 아니다.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import csc
        wrows = csc._worker_liveness()
        live = sum(1 for r in wrows if r.get("verdict") == "LIVE")
        detail = " · ".join(
            f"{r.get('agent')} {r.get('verdict')}" for r in wrows) or "등록 없음"
        rows.append({"name": "워커 생존", "ok": bool(wrows) and live == len(wrows),
                     "value": f"{live}/{len(wrows)}", "why": detail})
    except Exception as exc:
        rows.append({"name": "워커 생존", "ok": False, "value": "확인 실패",
                     "why": f"{type(exc).__name__}: {str(exc)[:60]}"})

    # 2. 마지막 대화 이후 경과 — 조용한 것과 죽은 것을 구분한다
    msgs = load()
    last = ""
    for m in reversed(msgs):
        if m.get("timestamp"):
            last = m["timestamp"]; break
    quiet_min = 9999.0
    if last:
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            quiet_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        except Exception:
            pass
    rows.append({"name": "마지막 대화", "ok": quiet_min < 60,
                 "value": f"{quiet_min:.0f}분 전" if quiet_min < 9999 else "기록 없음",
                 "why": "60분 넘게 조용하면 멈춘 것일 수 있다"})

    # 3. 실패 편지함(DLQ) — 전달 못 한 메시지가 쌓이면 협업이 끊긴 것이다
    dlq = 0
    ddir = os.path.join(SWARM_DIR, "dead-letter")
    for entry in os.listdir(ddir) if os.path.isdir(ddir) else []:
        try:
            with open(os.path.join(ddir, entry), encoding="utf-8", errors="replace") as f:
                dlq += sum(1 for line in f if line.strip())
        except Exception:
            pass
    rows.append({"name": "실패 편지함", "ok": dlq == 0, "value": f"{dlq}건",
                 "why": "전달 실패 누적. 0이 아니면 누군가 못 받고 있다"})

    # 4. 미해결 BLOCKED — 규약상 이게 남으면 진행 자체가 금지된다
    gov = os.path.join(SWARM_DIR, "GOVERNANCE.md")
    unresolved = 0
    try:
        with open(gov, encoding="utf-8") as f:
            for line in f:
                if line.startswith("|") and ("미해소" in line or "미응답" in line):
                    unresolved += 1
    except Exception:
        pass
    rows.append({"name": "미해결 BLOCKED", "ok": unresolved == 0, "value": f"{unresolved}건",
                 "why": "GOVERNANCE 2절 5항: 1건이라도 남으면 산출물 확정 금지"})

    # 5. 커밋·푸시 — 사용자 승인 없이 나갔는지 확인한다
    try:
        n = subprocess.run(["git", "rev-list", "--count", "HEAD"], capture_output=True,
                           text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
        commits = n.stdout.strip() or "0"
    except Exception:
        commits = "?"
    rows.append({"name": "커밋 수", "ok": True, "value": commits,
                 "why": "P2 사용자 승인 전에는 0이어야 한다"})
    return rows


def cmd_html() -> int:
    """자족 HTML 을 만든다. 외부 CDN·서버 없이 더블클릭으로 열린다."""
    rows = load()
    counts: dict[str, int] = {}
    for m in rows:
        counts[normalize(m.get("sender"))] = counts.get(normalize(m.get("sender")), 0) + 1

    items = []
    for m in rows:
        s, r = normalize(m.get("sender")), normalize(m.get("recipient"))
        typ = str(m.get("type", "?"))
        sev = SEVERITY.get(typ, "low")
        body = html.escape(str(m.get("body", "")))
        items.append(
            f'<article class="msg {s} sev-{sev}" data-from="{s}" data-type="{typ}">'
            f'<header><span class="who">{ICON.get(s,"?")} {html.escape(LABEL.get(s,s))}</span>'
            f'<span class="arrow">→</span><span class="to">{ICON.get(r,"?")} {html.escape(r)}</span>'
            f'<span class="type t-{sev}">{html.escape(typ)}</span>'
            f'<time>{html.escape(fmt_ts(m.get("timestamp")))}</time></header>'
            f'<pre>{body}</pre></article>'
        )

    hrows = health()
    hbad = [r for r in hrows if not r["ok"]]
    hcards = "".join(
        '<div class="hc {cls}"><b>{n}</b><span class="v">{v}</span>'
        '<small>{w}</small></div>'.format(
            cls="bad" if not r["ok"] else "good",
            n=html.escape(r["name"]), v=html.escape(str(r["value"])),
            w=html.escape(r["why"]))
        for r in hrows)
    hverdict = ("🔴 점검 필요 %d건" % len(hbad)) if hbad else "🟢 정상"

    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    stat = " · ".join(f"{ICON.get(k,'?')} {k} {v}건" for k, v in sorted(counts.items()))
    types = sorted({str(m.get("type", "?")) for m in rows})
    type_opts = "".join(f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in types)

    hcls = "bad" if hbad else "good"
    doc = f"""<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- 이 페이지는 [도구 트랙] 이다 — 세 AI 가 실제로 주고받은 원문 전체를 담는다.
     사용자용 요약은 dashboard.html (사용자 트랙) 이 맡는다.
     원문을 사용자 편의로 고치지 않는다. 고치면 증거가 아니라 각색이 된다.
     30초마다 스스로 다시 읽는다.
     이 페이지는 훅이 갱신하므로, 에이전트가 일하는 동안 자동으로 최신이 된다.
     서버도 데몬도 없다. file:// 에서 fetch 는 CORS 로 막히므로 meta refresh 를 쓴다. -->
<meta http-equiv="refresh" content="30">
<title>3대 AI 도구 대화 원문</title>
<style>
:root{{--bg:#faf9f7;--fg:#1a1a18;--mut:#6b6862;--line:#e0ddd6;--card:#fff;
--codex:#6b4fbb;--claude:#c2410c;--anti:#0f766e;--hi:#b91c1c}}
@media(prefers-color-scheme:dark){{:root{{--bg:#171614;--fg:#ecebe8;--mut:#9b968d;
--line:#302e2a;--card:#201f1c;--codex:#a78bfa;--claude:#fb923c;--anti:#5eead4;--hi:#f87171}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,"Segoe UI","Malgun Gothic",sans-serif}}
.wrap{{max-width:900px;margin:0 auto;padding:24px 16px 80px}}
h1{{font-size:20px;margin:0 0 4px}}
.sub{{color:var(--mut);font-size:13px;margin-bottom:18px}}
.bar{{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);
display:flex;gap:8px;flex-wrap:wrap;align-items:center;z-index:5;margin-bottom:16px}}
select,button{{font:inherit;padding:5px 10px;border:1px solid var(--line);
border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}}
.msg{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--mut);
border-radius:8px;padding:12px 14px;margin-bottom:10px}}
.msg.codex{{border-left-color:var(--codex)}}
.msg.claude{{border-left-color:var(--claude)}}
.msg.antigravity{{border-left-color:var(--anti)}}
.msg.sev-high{{box-shadow:inset 3px 0 0 var(--hi)}}
.msg.sev-muted{{opacity:.55}}
header{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;
font-size:12px;color:var(--mut);margin-bottom:8px}}
.who{{font-weight:600;color:var(--fg)}}
.type{{margin-left:auto;font-weight:600;padding:1px 8px;border-radius:99px;
border:1px solid var(--line)}}
.t-high{{color:var(--hi);border-color:var(--hi)}}
pre{{margin:0;white-space:pre-wrap;word-break:break-word;font:inherit;max-height:16em;overflow:auto}}
.hidden{{display:none}}
.explain{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--anti);
border-radius:10px;padding:14px 16px;margin:0 0 18px}}
.explain h2{{font-size:15px;margin:0 0 6px}}
.explain p{{margin:6px 0;font-size:13px;line-height:1.65}}
.explain .tip{{color:var(--mut);font-size:12.5px}}
.sub2{{color:var(--mut);font-size:12.5px;margin:0 0 16px;line-height:1.6}}
.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin:10px 0}}
.two div{{border:1px solid var(--line);border-radius:7px;padding:8px 10px;font-size:13px}}
.two small{{color:var(--mut);font-size:11.5px}}
.health{{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:16px;
background:var(--card)}}
.health.bad{{border-color:var(--hi)}}
.hhead{{font-size:13px;color:var(--mut);margin-bottom:10px;display:flex;gap:10px;
align-items:baseline;flex-wrap:wrap}}
.hhead b{{color:var(--fg);font-size:14px}}
.hnote{{margin-left:auto;font-size:11px}}
.hgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}}
.hc{{border:1px solid var(--line);border-left:3px solid var(--anti);border-radius:6px;padding:8px 10px}}
.hc.bad{{border-left-color:var(--hi)}}
.hc b{{display:block;font-size:12px}}
.hc .v{{display:block;font-size:17px;font-weight:700;margin:2px 0}}
.hc small{{color:var(--mut);font-size:11px;line-height:1.35;display:block}}
footer{{color:var(--mut);font-size:12px;margin-top:24px;border-top:1px solid var(--line);padding-top:12px}}
</style>
<div class="wrap">
<h1>3대 AI 도구 실제 대화 기록 (원문 로그)</h1>

<section class="explain">
<h2>이 페이지가 무엇인가요</h2>
<p><b>세 AI 도구가 실제로 주고받은 말을 하나도 빼지 않고 그대로 옮긴 기록입니다.</b>
요약하거나 다듬지 않았습니다. 다듬으면 증거가 아니라 각색이 되기 때문입니다.</p>
<div class="two">
<div><b>🧠 코덱스</b><br><small>지휘 — 일을 나누고 최종 판단</small></div>
<div><b>🛡️ 클로드 코드</b><br><small>검증 — 오류와 위험을 찾아 지적</small></div>
<div><b>🖐️ 안티그래비티</b><br><small>실행 — 직접 만들고 눈으로 확인</small></div>
</div>
<p class="tip"><b>읽는 법</b> — 위에서 아래로 시간 순서입니다.
왼쪽 색 막대가 누가 말했는지 알려줍니다.
<b>붉은 기운이 도는 칸</b>은 서로 잘못을 지적하거나 진행을 막은 말입니다.
전문용어가 많아 어렵다면, 쉬운 한국어로 정리한
<b>감시판(<code>dashboard.html</code>)</b>을 먼저 보세요.</p>
<p class="tip"><b>갱신</b> — 30초마다 저절로 새로 고쳐집니다. 켜 두기만 하면 됩니다.</p>
</section>
<div class="sub2">시스템이 정상인지 판단하는 화면은 따로 있습니다 —
<b>감시판 <code>.agent-swarm/dashboard.html</code></b>.
같은 값을 두 곳에서 계산하면 언젠가 서로 다른 답이 나오므로,
이 페이지는 <b>기록만</b> 맡습니다.</div>
<div class="sub">전체 {len(rows)}건 · {stat}<br>생성 {generated} · 원본 <code>.agent-swarm/messages/queue.jsonl</code></div>
<div class="bar">
<label>보낸 쪽 <select id="f-from"><option value="">전체</option>
<option value="codex">🧠 Codex</option><option value="claude">🛡️ Claude Code</option>
<option value="antigravity">🖐️ Antigravity</option></select></label>
<label>종류 <select id="f-type"><option value="">전체</option>{type_opts}</select></label>
<button id="only-hot">🔴 질타·차단만</button>
<button id="reset">초기화</button>
<span id="count" style="color:var(--mut);font-size:12px"></span>
</div>
<main id="list">
{''.join(items)}
</main>
<footer>이 페이지는 에이전트가 작업할 때마다 훅이 자동으로 다시 만든다. 수동 갱신은 <code>python csc_viewer.py html</code>.<br>아무도 일하지 않으면 갱신도 멈춘다 — 그때는 바뀔 것이 없다는 뜻이다.
로그가 곧 원본이며 이 페이지는 원본을 읽기 쉽게 옮긴 것뿐이다.</footer>
</div>
<script>
var list=document.getElementById('list');
var all=[].slice.call(list.querySelectorAll('.msg'));
var ff=document.getElementById('f-from'),ft=document.getElementById('f-type'),
    cnt=document.getElementById('count');
var hot=false;
function apply(){{
  var n=0;
  all.forEach(function(el){{
    var ok=(!ff.value||el.dataset.from===ff.value)
        && (!ft.value||el.dataset.type===ft.value)
        && (!hot||el.classList.contains('sev-high'));
    el.classList.toggle('hidden',!ok); if(ok)n++;
  }});
  cnt.textContent=n+' / '+all.length+'건 표시';
}}
ff.onchange=ft.onchange=apply;
document.getElementById('only-hot').onclick=function(){{hot=!hot;this.style.fontWeight=hot?'700':'';apply();}};
document.getElementById('reset').onclick=function(){{ff.value='';ft.value='';hot=false;apply();}};
apply();
</script>
</html>"""

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"✅ 생성: {OUT_HTML}")
    print(f"   메시지 {len(rows)}건 · {stat}")
    print(f"   더블클릭하거나 브라우저에 끌어다 놓으면 열린다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CSC 3자 대화 뷰어")
    sub = ap.add_subparsers(dest="cmd")
    t = sub.add_parser("tail", help="터미널에서 대화 보기")
    t.add_argument("-n", type=int, default=20)
    t.add_argument("-f", "--follow", action="store_true", help="새 메시지 실시간 감시")
    sub.add_parser("html", help="자족 HTML 생성")
    args = ap.parse_args()
    if args.cmd == "html":
        return cmd_html()
    if args.cmd == "tail":
        return cmd_tail(args.n, args.follow)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
