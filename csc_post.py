"""비상 발신기 — csc.py 가 죽어 있을 때만 쓰는 최소 경로.

━━ 왜 이 파일이 따로 있는가 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2026-09-07 23:48, 발신이 실제로 죽었다.

    $ python csc.py send ...
    SyntaxError: unmatched ')' at csc_worker.py:222
    exit 1

메시지를 잃어서가 아니다. csc.py 가 csc_runtime -> csc_worker 를 import 하는데,
그때 동료가 csc_worker.py 를 편집 중이었다. 편집 중인 파일은 잠시 문법이 깨진다.

그래서 **동료가 작업하는 동안 아무도 서로에게 말을 걸 수 없다.**
그리고 하필 그때가 서로에게 말을 걸어야 하는 순간이다.

원인은 유실이 아니라 의존이다. 통신 수단이 통신 대상 코드에 묶여 있었다.
확률이 아니라 구조라서, 같은 조건이면 반드시 또 일어난다.

━━ 그래서 이 파일이 지키는 단 하나의 규칙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**프로젝트 모듈을 하나도 import 하지 않는다.** 표준 라이브러리만 쓴다.
이 규칙을 어기는 순간 이 파일은 존재 이유를 잃는다. 기능을 늘리지 마라.

━━ 하지 않는 것 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
읽기, 라우팅, 감사, 서명. 전부 csc.py 에 있고 여기로 옮기지 않는다.
특히 **서명은 하지 않는다.** 그래서 인증 모드에서는 아예 거부한다(아래 참조).
비상구가 인증 우회로가 되면 비상구가 아니라 뒷문이다.
    — 이 거부 조건은 Codex 가 D1 표결에서 단 조건이다 (MSG-20260907-164525-778679-82fe4ccf-COD-CLA)

합의 근거 (규약 11-1: 구성원별 발화를 남긴다)
    claude-code-6c  MSG-20260907-162731-639845-9e247601-CLA-ALL  제안 및 찬성
    codex           MSG-20260907-164525-778679-82fe4ccf-COD-CLA  "D1 비상 발신기 방향은 AGREE"
    antigravity     응답 없음 -> 규약 13-1 에 따라 기권(ABSTAIN)
    정족수 3명 중 2명. 충족.
"""
import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone

TYPES = ("ACK", "PROPOSAL", "RISK", "RESULT", "BLOCKED", "CALL_OUT",
         "WHISTLEBLOW", "TASK", "EVENT", "REPORT")

ROOT = os.path.dirname(os.path.abspath(__file__))
MESSAGES = os.path.join(ROOT, ".agent-swarm", "messages")

# message_id 뒤에 붙는 세 글자 약호. csc.py 가 쓰는 것과 같은 규칙이다.
def _code(name):
    return "".join(c for c in name.upper() if c.isalnum())[:3] or "UNK"


def authenticated_mode(messages_dir=MESSAGES, sample=200):
    """인증 모드인지 파일 증거만으로 판정한다.

    서명된 메시지는 envelope 에 "auth" 필드를 단다(csc_auth.sign_envelope).
    최근 메시지 중 하나라도 그것을 달고 있으면 이 저장소는 인증 모드로 돌고 있다.

    왜 import 로 확인하지 않는가: import 하는 순간 이 파일이 존재하는 이유가 사라진다.
    csc.py 가 죽어 있을 때 쓰라고 만든 것이기 때문이다.

    판정을 못 하면 인증 모드로 본다. 모를 때는 막는 쪽이 안전하다.
    """
    path = os.path.join(messages_dir, "queue.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-sample:]
    except FileNotFoundError:
        return False                      # 큐가 없으면 아직 아무도 서명하지 않았다
    except OSError:
        return True                       # 읽을 수 없으면 판단 불가 -> 막는다
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            if isinstance(json.loads(line).get("auth"), dict):
                return True
        except (ValueError, AttributeError):
            continue
    return False


def build_envelope(sender, recipient, mtype, body, in_reply_to="none",
                   correlation_id=None):
    now = datetime.now(timezone.utc)
    mid = "MSG-%s-%06d-%s-%s-%s" % (
        now.strftime("%Y%m%d-%H%M%S"), now.microsecond,
        secrets.token_hex(4), _code(sender), _code(recipient),
    )
    env = {
        "message_id": mid,
        "timestamp": now.isoformat(),
        "sender": sender,
        "recipient": recipient,
        "type": mtype,
        "in_reply_to": in_reply_to or "none",
        "body": body,
    }
    if correlation_id:
        env["correlation_id"] = correlation_id
    return env


def _inbox_name(recipient):
    """csc_storage.persist_message 와 같은 규칙으로 수신함 이름을 만든다."""
    if recipient.strip().lower() == "all":
        return "all_inbox.jsonl"
    safe = "".join(c for c in recipient.strip()
                   if c.isalnum() or c in ("-", "_")).lower() or "unknown"
    return "%s_inbox.jsonl" % safe


def _append(path, envelope):
    """한 줄 이어쓴다. 같은 message_id 가 이미 있으면 쓰지 않는다.

    중복 방지는 message_id 로만 한다. 본문 비교는 하지 않는다 —
    같은 id 면 같은 메시지라는 것이 이 시스템의 약속이기 때문이다.
    """
    mid = envelope["message_id"]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if mid in line:
                    return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = (json.dumps(envelope, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        while data:                       # os.write 는 일부만 쓸 수 있다. 끝까지 쓴다
            data = data[os.write(fd, data):]
    finally:
        os.close(fd)
    return True


def post(sender, recipient, mtype, body, in_reply_to="none",
         correlation_id=None, messages_dir=MESSAGES):
    if mtype not in TYPES:
        raise ValueError("unknown type %r (allowed: %s)" % (mtype, ", ".join(TYPES)))
    if not body or not body.strip():
        raise ValueError("body is empty — 빈 메시지는 보내지 않는다")
    if authenticated_mode(messages_dir):
        raise PermissionError(
            "인증 모드에서는 csc_post 를 쓸 수 없다. 이 발신기는 서명하지 않는다.\n"
            "비상구가 인증 우회로가 되면 안 된다. csc.py 를 고쳐서 정상 경로로 보내라."
        )
    env = build_envelope(sender, recipient, mtype, body, in_reply_to, correlation_id)
    q = _append(os.path.join(messages_dir, "queue.jsonl"), env)
    i = _append(os.path.join(messages_dir, _inbox_name(recipient)), env)
    return {"message_id": env["message_id"], "queue_appended": q,
            "inbox_appended": i, "deduplicated": not (q or i)}


def main(argv=None):
    p = argparse.ArgumentParser(
        description="비상 발신기. csc.py 가 죽었을 때만 쓴다. 평시에는 csc.py send 를 쓴다.")
    p.add_argument("--sender", required=True)
    p.add_argument("--recipient", required=True)
    p.add_argument("--type", required=True, choices=TYPES)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--body")
    g.add_argument("--body-file", help="본문을 파일에서 읽는다. 셸이 본문을 삼키는 사고를 막는다")
    p.add_argument("--in-reply-to", default="none")
    p.add_argument("--correlation-id")
    a = p.parse_args(argv)

    body = a.body
    if a.body_file:
        with open(a.body_file, encoding="utf-8") as f:
            body = f.read()
    try:
        r = post(a.sender, a.recipient, a.type, body, a.in_reply_to, a.correlation_id)
    except PermissionError as e:
        print("거부: %s" % e, file=sys.stderr)
        return 3
    except ValueError as e:
        print("오류: %s" % e, file=sys.stderr)
        return 2
    print("[비상 발신] %s (%s) %s -> %s%s"
          % (r["message_id"], a.type, a.sender, a.recipient,
             "  [중복이라 쓰지 않음]" if r["deduplicated"] else ""))
    print("  주의: 이 경로는 서명하지 않는다. csc.py 가 살아나면 정상 경로를 쓴다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
