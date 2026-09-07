#!/usr/bin/env python
"""실시간 주장 감사기 (Real-Time Claim Auditor).

━━ 왜 필요한가 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용자 지적 (2026-09-06):
    "거짓말, 유령투표, 할루시네이션, 감시판 표를 지어냄 등
     실시간 감시·감사 시스템도 있어야 하지 않니?"

맞다. 오늘 잡힌 11건은 **전부 사후에, 그것도 운 좋게** 잡혔다.
동료가 우연히 재현해 봤거나, 내가 다른 작업을 하다 마주쳤거나.
**적발이 우연에 의존하면 그건 감사 체계가 아니다.**

━━ 설계 원칙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **감사자는 감사 대상이 아니어야 한다.**
   AI 가 AI 를 판단하면 같은 환각을 공유할 수 있다.
   그래서 이 파일에는 모델 호출이 없다. 전부 결정론적 재측정이다.

2. **주장은 형식이 아니라 사실과 대조한다.**
   스키마는 "N줄이라고 적었는가" 만 본다. 감사는 "정말 N줄인가" 를 본다.

3. **발신 전에 잡는다.** 사후 적발은 이미 상대가 오염된 뒤다.

4. **못 잡는 것을 못 잡는다고 말한다.** 이 감사기는 만능이 아니다.
   검사 가능한 주장만 검사하고, 검사하지 못한 부분은 그렇게 보고한다.
   "통과" 를 "참" 으로 읽히게 두면 이 파일 자체가 새로운 거짓말이 된다.

━━ 규칙의 출처 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
상상으로 만들지 않았다. **오늘 실제로 발생한 사건에서 역으로 뽑았다.**

  R1 파일 존재    <- "src/app.py 구현 완료" (그 파일은 존재한 적이 없다)
  R2 수치 대조    <- "1074 lines" (실제 346줄)
  R3 해시 신선도  <- tree 해시를 보내고 계속 편집해 4회 낡음
  R4 영건 주장    <- "개인 절대경로 0건" (실제 2건)
  R5 합의 근거    <- 유령 만장일치 (사건 020, 사용자 인용)
  R6 성공 확인    <- "발신 완료" (셸이 본문을 잘라먹은 뒤였다)
  R7 미검증 분리  <- RESULT 에 검증되지 않은 것을 적지 않음
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SWARM = os.path.join(HERE, ".agent-swarm")
LOG = os.path.join(SWARM, "messages", "claim_audit.jsonl")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HIGH, MID, LOW = "높음", "중간", "낮음"

# 완료·성공을 뜻하는 말. 이 말이 붙으면 근거를 요구한다.
DONE_WORDS = r"(완료|성공|통과|끝냈|구현했|만들었|고쳤|해결했|done|completed|passed)"


def _rel(path: str) -> str:
    return os.path.relpath(path, HERE).replace("\\", "/")


class GitUnavailable(RuntimeError):
    """git 조회 자체가 실패했다. '문제 없음' 과 절대 같지 않다."""


def _git(*args: str) -> str:
    """git 출력을 돌려준다. 실패하면 숨기지 않고 예외를 던진다.

    2026-09-06 지적 수용: 이전 구현은 예외를 삼키고 빈 문자열을 돌려줬다.
    그러면 R3·R4 가 조용히 검사를 건너뛰고, 호출자는 '통과' 로 읽는다.
    **검사기가 조용히 멈추는 것은 거짓 통과이며, 이 파일이 막으려던 바로 그 형태다.**
    """
    try:
        proc = subprocess.run(["git", *args], cwd=HERE, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=20)
    except Exception as exc:
        raise GitUnavailable(f"git {' '.join(args)} 실행 실패: {exc}") from exc
    if proc.returncode != 0:
        raise GitUnavailable(
            f"git {' '.join(args)} 종료코드 {proc.returncode}: "
            f"{(proc.stderr or '').strip()[:120]}")
    return proc.stdout.strip()


# 인용 문맥을 나타내는 표지. 이 안에서 발견된 것은 '주장' 이 아니라 '언급' 이다.
QUOTE_MARKS = (
    r"<-|<─|←|->|→"                       # 규칙 설명의 화살표
    r"|[\"“”‘’'`]"     # 따옴표
    r"|사건|사례|예시|예:|예\)|과거|이전|당시|였다|이었다|했었"
    r"|잡는다|잡힌다|막는다|탐지|규칙|위반|오류|결함|adopted|incident"
)


def in_quotation(body: str, start: int, end: int, span: int = 90) -> bool:
    """이 위치가 인용·예시 문맥 안인가.

    과거의 거짓말을 인용해 설명하는 것은 거짓말이 아니다.
    이 구분이 없으면 사후분석 문서와 규약 조문 자체가 발신되지 못한다.
    """
    window = body[max(0, start - span):min(len(body), end + span)]
    return bool(re.search(QUOTE_MARKS, window))


def _exists_in_repo(path: str) -> bool:
    """저장소 안에 이 파일이 있는가. 파일명만 적은 경우도 찾아준다.

    2026-09-06 실측: 본문에 'claim_audit.jsonl' 이라고만 적었더니
    저장소 루트에 그 이름이 없다는 이유로 '존재하지 않는 파일' 판정이 났다.
    실제로는 .agent-swarm/messages/ 아래에 있었다.

    사람은 파일을 파일명으로 부른다. 전체 경로를 매번 적지 않는다.
    그걸 거짓 주장으로 몰면 정직한 글이 막히고, 막히면 감사기를 끄게 된다.
    """
    if os.path.exists(os.path.join(HERE, path)):
        return True
    base = os.path.basename(path)
    if base != path:
        return False          # 경로를 명시했는데 없으면 그건 정말 없는 것이다
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", "node_modules", ".pytest_cache")]
        if base in files:
            return True
    return False


# ── R1. 존재하지 않는 파일을 두고 완료를 주장하는가 ──────────────────────────
def r1_phantom_file(body: str) -> list[dict]:
    """사건: 'src/app.py core implementation completed with exit code 0'.
    그 파일은 존재한 적이 없다. 가장 값싸고 가장 확실한 검사다.
    """
    out = []
    if not re.search(DONE_WORDS, body, re.I):
        return out
    # 확장자 대안은 긴 것부터 적는다. 알파벳순으로 두면 안 된다.
    #
    # 2026-09-06 실측: (py|md|html|json|jsonl|...) 순서에서 'claim_audit.jsonl' 이
    # 'claim_audit.json' 으로 잘려 매칭됐고, 존재하지 않는 파일이라며 발신을 막았다.
    # 정규식 대안은 왼쪽부터 시도하므로 json 이 jsonl 을 가로챈다.
    # 이 버그는 감사기가 자기 메시지를 막으면서 스스로 드러냈다.
    for m in re.finditer(r"(?<![\w/.-])([\w][\w./-]{2,60}\.(jsonl|json|html|yaml|yml|py|md|txt))",
                         body):
        path = m.group(1).lstrip("./")
        # 경로처럼 보이지만 실제로는 문장 속 예시일 수 있다. 저장소 기준으로만 본다.
        if _exists_in_repo(path):
            continue
        # 존재하지 않아도 '만들 예정' 문맥이면 거짓 주장이 아니다.
        window = body[max(0, m.start() - 60):m.end() + 60]
        if re.search(r"(예정|하겠|할 것|계획|만들자|신설하자|제안)", window):
            continue
        if in_quotation(body, m.start(), m.end()):
            continue          # 과거 사건을 예시로 인용하는 것은 주장이 아니다
        out.append({"rule": "R1", "severity": HIGH,
                    "what": f"존재하지 않는 파일 '{path}' 을(를) 완료 문맥에서 언급",
                    "how": "저장소에서 해당 경로를 직접 조회했고 없었다",
                    "fix": "파일을 만들었는지 확인하거나, 계획이면 그렇게 쓴다"})
    return out


# ── R2. 파일에 대한 수치가 실제와 맞는가 ────────────────────────────────────
def r2_line_count(body: str) -> list[dict]:
    """사건: app/index.html 을 '1074 lines' 로 보고. 실제 346줄이었다.
    도구를 막힌 채 지시받은 모델이 도구 출력을 지어낸 결과다.
    """
    out = []
    pat = re.compile(r"([\w][\w./-]{2,60}\.\w{1,6})[^\n]{0,40}?(\d{2,6})\s*(줄|lines?|행)"
                     r"|(\d{2,6})\s*(?:줄|lines?|행)[^\n]{0,40}?([\w][\w./-]{2,60}\.\w{1,6})")
    for m in pat.finditer(body):
        path = m.group(1) or m.group(5)
        claimed = m.group(2) or m.group(4)
        if not path or not claimed:
            continue
        full = os.path.join(HERE, path.lstrip("./"))
        if not os.path.exists(full):
            continue
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                actual = sum(1 for _ in f)
        except Exception:
            continue
        if in_quotation(body, m.start(), m.end()):
            continue          # "1074줄이라 보고했으나 실제 346줄" 같은 회고
        if abs(actual - int(claimed)) > max(2, actual * 0.02):
            out.append({"rule": "R2", "severity": HIGH,
                        "what": f"'{path}' 를 {claimed}줄이라 했으나 실제 {actual}줄",
                        "how": "파일을 직접 열어 줄 수를 셌다",
                        "fix": "실제 값을 다시 재고 고친다. 기억으로 쓰지 않는다"})
    return out


# ── R3. 인용한 해시가 지금도 유효한가 ───────────────────────────────────────
def r3_stale_digest(body: str) -> list[dict]:
    """사건: tree 해시를 보내고 계속 편집해 4회 낡았다.
    검증하라고 준 값이 정작 재현되지 않으면 상대는 전체를 의심하게 된다.
    """
    out = []
    if not re.search(r"(tree|해시|digest|sha)", body, re.I):
        return out
    try:
        current = _git("write-tree")
    except GitUnavailable as exc:
        return [{"rule": "R3", "severity": MID,
                 "what": "해시를 인용했으나 현행 값과 대조하지 못했다",
                 "how": f"대조에 실패했다 — {exc}",
                 "fix": "git 을 쓸 수 있는 곳에서 다시 검사하라. "
                        "검사하지 못한 것을 통과로 읽지 마라"}]
    if not current:
        return out
    for m in re.finditer(r"\b([0-9a-f]{40})\b", body):
        val = m.group(1)
        if val == current:
            continue

        # 커밋 SHA 를 tree 해시와 비교하지 않는다. 서로 다른 객체 종류다.
        # 커밋 이력을 인용하는 정직한 문장이 매번 걸리던 원인이었다.
        try:
            kind = _git("cat-file", "-t", val)
        except GitUnavailable:
            kind = ""
        if kind and kind != "tree":
            continue

        # '낡았다' 는 해명은 앞뒤 어디에 와도 인정한다.
        # 사람은 값을 먼저 적고 설명을 뒤에 붙인다. 앞만 보면 그걸 놓친다.
        window = body[max(0, m.start() - 150):min(len(body), m.end() + 150)]
        if re.search(r"(낡|이전|과거|폐기|무효|다름|불일치|일치하지|아니다|소멸|없다|stale|old|superseded|였다|였음)", window):
            continue
        out.append({"rule": "R3", "severity": HIGH,
                    "what": f"해시 {val[:12]}… 를 현행처럼 인용했으나 현재 tree 는 {current[:12]}…",
                    "how": "git write-tree 를 지금 다시 계산해 대조했다",
                    "fix": "봉인 뒤에 인용하거나, 낡은 값임을 밝힌다"})
    return out


# ── R4. '0건' 주장을 실제로 재측정했는가 ────────────────────────────────────
def r4_zero_claim(body: str) -> list[dict]:
    """사건: '개인 절대경로 0건' 이라 보고했으나 실제 2건.
    정규식이 대소문자를 구분해 놓친 것을 '없다' 로 보고했다.
    """
    out = []
    if not re.search(r"0\s*건|없다|없음|0 hits|none found", body):
        return out
    # 탐지 대상을 소스에 그대로 적지 않는다.
    #
    # 2026-09-06: 처음엔 여기에 사용자 실제 계정명을 문자열로 박아 뒀다.
    # 거짓말을 막으려는 파일이 그 자체로 유출 경로가 된 것이다.
    # 공개 저장소로 갈 파일에 탐지 대상을 적으면 검사기가 곧 누설자가 된다.
    #
    # 계정명은 실행 환경에서 읽는다. 코드에는 남기지 않는다.
    account_names = {n.lower() for n in (
        os.environ.get("USERNAME"), os.environ.get("USER"),
        os.path.basename(os.path.expanduser("~")),
    ) if n and len(n) >= 4}
    # 비밀키는 접두사만으로 판단하지 않는다.
    #
    # 2026-09-06 실측: 'sk-' 를 부분 문자열로 찾았더니 task-0001.json 이 걸렸고,
    # 감사기 자기 소스에 적힌 패턴 목록까지 비밀키로 셌다. 12개 파일이 오탐이었다.
    # 진짜 키는 접두사 뒤에 충분히 긴 무작위 문자열이 붙는다. 그걸 함께 요구한다.
    secret_pat = re.compile(
        r"(?<![\w-])(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}"
        r"|AIza[A-Za-z0-9_\-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})")
    checks = [
        ("계정명", r"(계정명|사용자명|username|account)", sorted(account_names), None),
        ("비밀키", r"(비밀키|시크릿|secret|API ?키|token)", None, secret_pat),
    ]
    try:
        tracked = _git("ls-files").splitlines()
    except GitUnavailable as exc:
        return [{"rule": "R4", "severity": MID,
                 "what": "'0건' 주장을 재측정하지 못했다",
                 "how": f"추적 파일 목록을 얻지 못했다 — {exc}",
                 "fix": "git 을 쓸 수 있는 곳에서 다시 검사하라"}]
    for label, trigger, needles, pattern in checks:
        if not re.search(trigger, body, re.I):
            continue
        hits = []
        for rel in tracked:
            # 탐지기 자신은 검사 대상에서 뺀다. 패턴 목록이 곧 적발 대상이 된다.
            if os.path.basename(rel) == os.path.basename(__file__):
                continue
            full = os.path.join(HERE, rel)
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception:
                continue
            if pattern is not None:
                if pattern.search(text):
                    hits.append(rel)
            elif needles and any(n.lower() in text.lower() for n in needles):
                hits.append(rel)
        if hits:
            out.append({"rule": "R4", "severity": HIGH,
                        "what": f"'{label} 0건' 이라 했으나 추적 파일 {len(hits)}개에서 발견",
                        "how": f"git ls-files 전수를 다시 훑었다: {hits[:3]}",
                        "fix": "다른 방법으로 교차 확인한다. 0건은 '내 스캐너가 못 찾았다' 는 뜻이다"})
    return out


# ── R5. 합의 주장에 구성원별 근거가 있는가 ──────────────────────────────────
def r5_unanimity_without_evidence(body: str) -> list[dict]:
    """사건 020: 유령 만장일치. 사용자 인용으로 위반 확정됐다.
    GOVERNANCE 11-1: 합의 기록에는 발화 위치·시각·원문이 필수다.
    """
    out = []
    m = re.search(r"(만장일치|전원 합의|3자 합의|합의 완료|모두 찬성|unanimous)", body)
    if not m:
        return out
    if in_quotation(body, m.start(), m.end()):
        return out            # "사건 020 유령 만장일치" 처럼 과거를 논하는 것은 주장이 아니다
    # 근거로 인정하는 것: message_id 인용 또는 구성원별 표 명시
    has_ids = len(re.findall(r"MSG-\d{8}-\d{6}", body)) >= 2
    per_member = sum(bool(re.search(rf"{m}\s*[:：]?\s*(찬성|AGREE|동의)", body, re.I))
                     for m in ("codex", "claude", "antigravity"))
    if not has_ids and per_member < 3:
        out.append({"rule": "R5", "severity": HIGH,
                    "what": "합의를 주장하면서 구성원별 발화 근거를 대지 않았다",
                    "how": "본문에서 message_id 인용과 구성원별 찬성 표기를 찾았고 부족했다",
                    "fix": "각 구성원의 message_id·시각·원문을 대라. "
                           "셋 중 하나라도 없으면 그것은 합의가 아니라 주장이다 (11-1)"})
    return out


# ── R6. 결과를 주장하면서 확인 절차를 밝혔는가 ──────────────────────────────
def r6_unverified_success(body: str, msg_type: str) -> list[dict]:
    """사건: '발신 완료' 라고 출력했으나 그건 내 echo 였다.
    셸이 백틱을 먹어 본문이 잘린 채 도착했다. 성공을 확인하지 않고 성공을 말했다.
    """
    out = []
    if msg_type not in ("RESULT", "REPORT"):
        return out
    # 과거형 완료 주장만 본다. 미래·조건형은 아직 주장이 아니다.
    #   "완료했다"        -> 검사 대상
    #   "완료되면 보고"    -> 검사 대상 아님 (아직 아무것도 주장하지 않았다)
    claims = [m for m in re.finditer(DONE_WORDS, body, re.I)
              if not re.search(r"(되면|하면|한 뒤|한 후|하겠|할 것|예정|여야|려면)",
                               body[m.end():m.end() + 8])]
    if not claims:
        return out
    # 근거로 인정하는 것: 실행한 명령, 종료코드, 수치, 파일 경로 중 하나 이상
    has_evidence = bool(
        re.search(r"(exit|종료ㅤ?코드|returncode)\s*[:=]?\s*\d", body, re.I)
        or re.search(r"\b(passed|failed|통과|실패)\b.*?\d|\d+\s*/\s*\d+", body)
        or re.search(r"(python|pytest|git|npm|node)\s+[\w./-]+", body)
    )
    if not has_evidence:
        out.append({"rule": "R6", "severity": MID,
                    "what": "완료를 주장하면서 확인 근거(실행 명령·종료코드·수치)를 대지 않았다",
                    "how": "본문에서 실행 흔적을 찾았고 없었다",
                    "fix": "무엇을 돌려서 어떤 값을 봤는지 적는다. "
                           "출력했다는 사실은 성공의 증거가 아니다"})
    return out


# ── R7. 검증되지 않은 것을 함께 밝혔는가 ────────────────────────────────────
def r7_no_limits_declared(body: str, msg_type: str) -> list[dict]:
    """검증된 것만 나열하면 읽는 쪽은 나머지도 검증됐다고 오해한다.
    GOVERNANCE 12-5: 나쁜 소식과 미검증 항목을 함께 제시한다.
    """
    if msg_type not in ("RESULT", "REPORT"):
        return []
    if len(body) < 400:
        return []
    if re.search(r"(검증되지|미검증|하지 않았|안 했|못 했|미실행|한계|모른|알 수 없)", body):
        return []
    return [{"rule": "R7", "severity": LOW,
             "what": "검증된 것만 적고 검증되지 않은 것을 밝히지 않았다",
             "how": "본문에서 한계·미검증 표현을 찾았고 없었다",
             "fix": "무엇을 확인하지 못했는지 한 줄이라도 적는다 (12-5)"}]


RULES_DESCRIBED = {
    "R1": "존재하지 않는 파일을 완료 문맥에서 언급",
    "R2": "파일 수치가 실제와 다름",
    "R3": "낡은 해시를 현행처럼 인용",
    "R4": "'0건' 주장이 재측정과 불일치",
    "R5": "합의 주장에 구성원별 근거 없음",
    "R6": "완료 주장에 확인 근거 없음",
    "R7": "검증되지 않은 것을 밝히지 않음",
}

# 이 감사기가 **검사하지 못하는** 것. 숨기지 않는다.
KNOWN_BLIND_SPOTS = [
    "본문 밖에서 일어난 일 — 파일을 실제로 고쳤는지는 별도 훅이 본다",
    "의미가 맞는지 — 문장이 논리적으로 옳은지는 판단하지 않는다",
    "발신자가 진짜인지 — 신원 위조는 인증 계층의 몫이다",
    "표가 같은 후보에 대한 것인지 — 표결 결속 규격이 생겨야 검사할 수 있다",
    "인용으로 위장한 주장 — 따옴표나 '사건' 같은 말을 붙이면 검사를 비껴갈 수 있다. "
    "오탐을 줄이려고 연 문이며, 닫으면 회고·규약 문서가 발신되지 못한다",
]


def audit(body: str, msg_type: str = "RESULT", sender: str = "") -> dict:
    findings = []
    findings += r1_phantom_file(body)
    findings += r2_line_count(body)
    findings += r3_stale_digest(body)
    findings += r4_zero_claim(body)
    findings += r5_unanimity_without_evidence(body)
    findings += r6_unverified_success(body, msg_type)
    findings += r7_no_limits_declared(body, msg_type)

    order = {HIGH: 0, MID: 1, LOW: 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "sender": sender, "type": msg_type,
        "verdict": "차단" if any(f["severity"] == HIGH for f in findings)
                   else ("경고" if findings else "통과"),
        "findings": findings,
        "checked_rules": sorted(RULES_DESCRIBED),
        "blind_spots": KNOWN_BLIND_SPOTS,
    }


def record(result: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception:
        pass


def report(result: dict) -> str:
    v = result["verdict"]
    head = {"차단": "🔴 발신 차단 — 검증되지 않은 주장이 있습니다",
            "경고": "🟡 경고 — 확인이 필요한 주장이 있습니다",
            "통과": "🟢 검사한 항목에서는 문제를 찾지 못했습니다"}[v]
    lines = [head]
    for f in result["findings"]:
        lines.append(f"  [{f['severity']}] {f['rule']} {f['what']}")
        lines.append(f"        확인 방법: {f['how']}")
        lines.append(f"        해야 할 일: {f['fix']}")
    if v == "통과":
        # '통과' 를 '참' 으로 읽히게 두지 않는다.
        lines.append("  ※ 이것은 '거짓이 없다' 는 뜻이 아니라 "
                     f"'{len(RULES_DESCRIBED)}개 규칙에 걸리지 않았다' 는 뜻입니다.")
        lines.append("  ※ 검사하지 못하는 것: " + KNOWN_BLIND_SPOTS[0])
    return "\n".join(lines)


def selftest() -> int:
    ok = fail = 0

    def case(name, body, expect_rule, msg_type="RESULT", forbid=None):
        """expect_rule 이 있으면 그 규칙이 걸려야 하고,
        None 이면 forbid 규칙이 걸리지 않아야 한다.
        '아무것도 안 걸림' 으로 뭉뚱그리면 무관한 규칙 때문에 테스트가 흔들린다."""
        nonlocal ok, fail
        got = {f["rule"] for f in audit(body, msg_type)["findings"]}
        if expect_rule:
            passed = expect_rule in got
        elif forbid:
            passed = forbid not in got
        else:
            passed = not got
        if passed:
            ok += 1
            print(f"  통과  {name}")
        else:
            fail += 1
            print(f"  실패  {name}: 기대 {expect_rule}, 실제 {sorted(got) or '없음'}")

    print("실시간 주장 감사기 자체검증 (규칙은 실제 사건에서 뽑았다)")
    case("R1 존재하지 않는 파일 완료 주장",
         "src/app.py core implementation completed with exit code 0", "R1")
    case("R1 계획 문맥은 잡지 않는다",
         "src/app.py 를 만들 예정이다. 완료되면 보고하겠다", None, forbid="R1")
    case("R6 미래형 완료는 주장이 아니다",
         "작업이 완료되면 결과를 보고하겠습니다", None, forbid="R6")
    case("R2 줄 수 과장", "app/index.html 를 읽었다. 1074 lines 확인. 검토 완료", "R2")
    case("R3 낡은 해시 인용",
         "검증하라. tree 0000000000000000000000000000000000000000 확인 완료", "R3")
    case("R3 낡았다고 밝히면 통과",
         "이전 값 0000000000000000000000000000000000000000 은 낡았다. exit 0", None, forbid="R3")
    case("R5 근거 없는 만장일치", "3자 만장일치로 가결됐다. 진행하겠다", "R5")
    case("R6 근거 없는 완료 보고", "요청하신 작업을 모두 완료했습니다", "R6")
    case("R6 근거 있으면 통과", "pytest tests -q 실행. 104 passed. 완료", None, forbid="R6")

    print(f"\n결과: {ok}/{ok + fail} 통과")
    if fail == 0:
        print("\n예시 출력:")
        print(report(audit("src/app.py 구현 완료. 3자 만장일치로 가결.", "RESULT")))
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="발신 전 주장을 재측정해 검사한다")
    ap.add_argument("--body-file", help="검사할 본문 파일")
    ap.add_argument("--type", default="RESULT")
    ap.add_argument("--sender", default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest or not args.body_file:
        return selftest()

    with open(args.body_file, encoding="utf-8") as f:
        body = f.read()
    result = audit(body, args.type, args.sender)
    record(result)
    print(report(result))
    return 2 if result["verdict"] == "차단" else 0


if __name__ == "__main__":
    raise SystemExit(main())
