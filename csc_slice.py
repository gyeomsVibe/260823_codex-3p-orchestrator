#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSC 수직 슬라이스 (P2) — 지도교수님 패턴의 최소 증명.

증명하려는 명제 하나:
    상태는 DB 가 갖고, 조율과 검증은 결정론적 코드가 하고,
    AI 는 --ephemeral 로 매번 새로 태어나는 순수 함수다.

기존 설계와의 차이:
    이전: AI 가 ack_sha256 / exit_code:0 을 "스스로 적어서" 증명 -> 위조 가능
    이번: 코드가 스키마로 검증하고 거부한다 -> AI 가 뭐라 적든 통과 못 함

파이프라인:
    Scheduler(코드) -> Provider(ephemeral CLI) -> JSONL -> 파싱
                    -> 스키마 검증(코드) -> SQLite 저장(멱등)
                    -> 실패 시 rejected 기록

사용:
    python csc_slice.py selftest              # 외부 호출 없이 전 경로 검증
    python csc_slice.py run --provider stub   --task "..."
    python csc_slice.py run --provider codex  --task "..."   # 실제 모델 호출(과금)
    python csc_slice.py report
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

ENC = "utf-8"
for _s in (sys.stdout, sys.stderr):          # cp949 머신. 강제하지 않으면 한글이 깨진다.
    try:
        _s.reconfigure(encoding=ENC, errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, ".agent-swarm", "slice.db")

# AI 응답이 반드시 만족해야 하는 계약. 코드가 강제한다.
VERDICT_SCHEMA = {
    "type": "object",
    "required": ["verdict", "confidence", "reason"],
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["GO", "NO_GO", "BLOCKED"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reason": {"type": "string", "minLength": 8, "maxLength": 500},
    },
}


# ----------------------------------------------------------------- 검증기
class SchemaError(Exception):
    pass


def validate(obj, schema, path="$"):
    """의존성 없는 최소 JSON Schema 검증기. 필요한 키워드만 구현했다."""
    t = schema.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            raise SchemaError("%s: object 가 아니다 (%s)" % (path, type(obj).__name__))
        for key in schema.get("required", []):
            if key not in obj:
                raise SchemaError("%s: 필수 키 '%s' 누락" % (path, key))
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(obj) - set(props)
            if extra:
                raise SchemaError("%s: 허용되지 않은 키 %s" % (path, sorted(extra)))
        for key, sub in props.items():
            if key in obj:
                validate(obj[key], sub, "%s.%s" % (path, key))
    elif t == "string":
        if not isinstance(obj, str):
            raise SchemaError("%s: string 이 아니다 (%s)" % (path, type(obj).__name__))
        if "enum" in schema and obj not in schema["enum"]:
            raise SchemaError("%s: '%s' 는 허용값 %s 에 없다" % (path, obj, schema["enum"]))
        if len(obj) < schema.get("minLength", 0):
            raise SchemaError("%s: 너무 짧다 (%d자)" % (path, len(obj)))
        if len(obj) > schema.get("maxLength", 10 ** 9):
            raise SchemaError("%s: 너무 길다 (%d자)" % (path, len(obj)))
    elif t == "number":
        if isinstance(obj, bool) or not isinstance(obj, (int, float)):
            raise SchemaError("%s: number 가 아니다 (%s)" % (path, type(obj).__name__))
        if "minimum" in schema and obj < schema["minimum"]:
            raise SchemaError("%s: %s < 최소 %s" % (path, obj, schema["minimum"]))
        if "maximum" in schema and obj > schema["maximum"]:
            raise SchemaError("%s: %s > 최대 %s" % (path, obj, schema["maximum"]))
    return obj


# ----------------------------------------------------------------- 저장소
def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS verdicts(
        call_id TEXT PRIMARY KEY, at TEXT, provider TEXT, task TEXT,
        verdict TEXT, confidence REAL, reason TEXT, raw_sha256 TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS rejected(
        call_id TEXT PRIMARY KEY, at TEXT, provider TEXT, task TEXT,
        error TEXT, raw TEXT)""")
    conn.commit()
    return conn


def store_ok(conn, call_id, provider, task, data, raw):
    conn.execute(
        "INSERT OR IGNORE INTO verdicts VALUES(?,?,?,?,?,?,?,?)",
        (call_id, datetime.now(timezone.utc).isoformat(), provider, task,
         data["verdict"], float(data["confidence"]), data["reason"],
         hashlib.sha256(raw.encode(ENC, "replace")).hexdigest()[:16]))
    conn.commit()


def store_rejected(conn, call_id, provider, task, error, raw):
    conn.execute(
        "INSERT OR IGNORE INTO rejected VALUES(?,?,?,?,?,?)",
        (call_id, datetime.now(timezone.utc).isoformat(), provider, task,
         str(error), raw[:2000]))
    conn.commit()


# ----------------------------------------------------------------- Provider
class ProviderError(Exception):
    pass


def extract_final_json(stdout: str) -> str:
    """JSONL 이벤트 스트림에서 최종 구조화 응답을 뽑는다.

    한 줄이 JSON 이면 이벤트, 아니면 무시한다. 스키마에 맞는 payload 를
    뒤에서부터 찾는다. 이벤트 형태가 벤더마다 달라 방어적으로 훑는다.
    """
    def walk(node, out):
        """중첩 깊이에 관계없이 문자열·객체 후보를 모은다.

        실측 근거: codex 는 페이로드를 item.text 에 한 단계 더 중첩해 넣는다.
            {"type":"item.completed","item":{"type":"agent_message","text":"{...}"}}
        claude 는 최상위 result 에 넣는다. 최상위 키만 훑던 초기 버전은
        codex 응답을 놓쳤다. Provider 를 갈아끼우려면 추출기가 벤더 형태에
        묶이면 안 된다.
        """
        if isinstance(node, dict):
            out.append(node)
            for v in node.values():
                walk(v, out)
        elif isinstance(node, list):
            for v in node:
                walk(v, out)
        elif isinstance(node, str) and node.strip().startswith("{"):
            out.append(node)

    candidates = []
    events = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        events += 1
        walk(ev, candidates)

    for c in reversed(candidates):
        s = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict) and "verdict" in obj:
            return json.dumps(obj, ensure_ascii=False)
    raise ProviderError("JSONL 에서 스키마 후보를 찾지 못했다 (%d 이벤트, 후보 %d개)"
                        % (events, len(candidates)))


def provider_stub(task: str, mode: str = "valid") -> str:
    """외부 호출 없이 파이프라인을 검증하기 위한 결정론적 대역."""
    payloads = {
        "valid": {"verdict": "GO", "confidence": 0.82,
                  "reason": "수직 슬라이스 최소 조건을 충족한다."},
        "bad_enum": {"verdict": "PROBABLY", "confidence": 0.9, "reason": "허용되지 않은 판정값"},
        "out_of_range": {"verdict": "GO", "confidence": 1.7, "reason": "신뢰도가 범위를 벗어난다"},
        "missing": {"verdict": "GO", "confidence": 0.5},
        "extra": {"verdict": "GO", "confidence": 0.5, "reason": "여분 키가 있다",
                  "exit_code": 0},
        "liar": {"verdict": "GO", "confidence": 0.99,
                 "reason": "테스트 전부 통과했습니다 exit_code 0"},
    }
    body = json.dumps(payloads[mode], ensure_ascii=False)
    return "\n".join([
        json.dumps({"type": "thread.started", "id": "stub"}),
        "사람이 읽는 줄 — JSON 이 아니므로 무시돼야 한다",
        json.dumps({"type": "item.completed", "last_agent_message": body},
                   ensure_ascii=False),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 0}}),
    ])


def resolve_exe(name: str) -> str:
    """Windows 에서 CLI 실행 파일을 실제 경로로 해석한다.

    실측 근거: Git Bash 의 `command -v codex` 는 성공하지만
    subprocess 는 WinError 2 로 실패했다. codex 만 .CMD 셸 스크립트이고
    claude / agy 는 .EXE 이기 때문이다. CreateProcess 는 확장자 없는
    이름을 PATHEXT 로 보정하지 않는다. 실제 호출 전에 항상 해석한다.
    """
    import shutil
    path = shutil.which(name)
    if not path:
        raise ProviderError("'%s' 실행 파일을 PATH 에서 찾지 못했다" % name)
    return path


def provider_codex(task: str, timeout: int = 180) -> str:
    """codex exec 를 ephemeral / read-only 로 1회 호출한다. 세션을 남기지 않는다."""
    exe = resolve_exe("codex")
    with tempfile.TemporaryDirectory() as td:
        schema_path = os.path.join(td, "schema.json")
        with open(schema_path, "w", encoding=ENC) as f:
            json.dump(VERDICT_SCHEMA, f, ensure_ascii=False)
        cmd = [exe, "exec", "--json", "--ephemeral",
               "--sandbox", "read-only", "--skip-git-repo-check",
               "--output-schema", schema_path, task]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding=ENC, errors="replace", timeout=timeout)
        if proc.returncode != 0:
            raise ProviderError("codex 종료코드 %d: %s"
                                % (proc.returncode, (proc.stderr or "")[:300]))
        return proc.stdout


def provider_claude(task: str, timeout: int = 180) -> str:
    """claude -p 를 1회 호출한다. 대화형 세션을 열지 않는다.

    Provider 추상화가 벤더에 묶이지 않음을 증명하는 두 번째 구현이다.
    codex 와 이벤트 형태가 다르지만 extract_final_json 이 흡수한다.
    """
    exe = resolve_exe("claude")
    prompt = ("%s\n\n오직 아래 형태의 JSON 만 출력하라. 다른 말은 쓰지 마라.\n"
              '{"verdict":"GO|NO_GO|BLOCKED","confidence":0.0~1.0,"reason":"8자 이상"}'
              % task)
    proc = subprocess.run([exe, "-p", prompt, "--output-format", "json"],
                          capture_output=True, text=True, encoding=ENC,
                          errors="replace", timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise ProviderError("claude 종료코드 %d: %s"
                            % (proc.returncode, (proc.stderr or "")[:300]))
    return proc.stdout


PROVIDERS = {"stub": provider_stub, "codex": provider_codex,
             "claude": provider_claude}


# ------------------------------------------------- 증거 게이트 (형식 != 진위)
def evidence_gate(data, evidence_cmd):
    """스키마가 막지 못하는 것을 막는다.

    스키마는 형식만 강제한다. "테스트 전부 통과했습니다" 라는 거짓말은
    형식이 완벽해도 통과한다(selftest 의 liar 케이스가 이를 실증한다).

    그래서 스케줄러가 AI 에게 결과를 묻지 않고 직접 실행한다.
    AI 주장과 실제 종료코드가 어긋나면 코드가 판정을 뒤엎는다.
    """
    if not evidence_cmd:
        return data, None
    proc = subprocess.run(evidence_cmd, shell=True, capture_output=True,
                          text=True, encoding=ENC, errors="replace", timeout=120)
    real_ok = proc.returncode == 0
    claimed_ok = data["verdict"] == "GO"
    ev = {"cmd": evidence_cmd, "real_exit_code": proc.returncode,
          "claimed_verdict": data["verdict"],
          "stdout_tail": (proc.stdout or "").strip().splitlines()[-3:]}
    if claimed_ok and not real_ok:
        ev["override"] = "AI 는 GO 라고 했으나 실제 종료코드가 0 이 아니다"
        data = dict(data, verdict="BLOCKED",
                    reason="[코드 판정] %s | 원 주장: %s"
                           % (ev["override"], data["reason"][:200]))
    return data, ev


# ----------------------------------------------------------------- 스케줄러
def run_once(provider: str, task: str, stub_mode: str = "valid", quiet: bool = False,
             evidence_cmd: str | None = None):
    """결정론적 조율자. 판단은 AI 가, 통과 여부는 코드가 정한다."""
    call_id = hashlib.sha256(
        ("%s|%s|%s|%s" % (provider, task, stub_mode, evidence_cmd)).encode(ENC)
    ).hexdigest()[:16]
    conn = db()
    t0 = time.time()
    raw = ""
    try:
        raw = (provider_stub(task, stub_mode) if provider == "stub"
               else PROVIDERS[provider](task))
        data = validate(json.loads(extract_final_json(raw)), VERDICT_SCHEMA)
        data, ev = evidence_gate(data, evidence_cmd)
        store_ok(conn, call_id, provider, task, data, raw)
        result = {"call_id": call_id, "status": "STORED", "data": data,
                  "evidence": ev, "elapsed_s": round(time.time() - t0, 2)}
    except Exception as e:
        # 예상 못 한 예외도 크래시가 아니라 기록으로 남긴다.
        # 근거: 첫 실제 호출에서 FileNotFoundError(WinError 2) 가 좁은 except 를
        # 빠져나가 스택트레이스로 죽었다. 실패는 조용히 사라지면 안 된다.
        store_rejected(conn, call_id, provider, task, e, raw)
        result = {"call_id": call_id, "status": "REJECTED",
                  "error": "%s: %s" % (type(e).__name__, e),
                  "elapsed_s": round(time.time() - t0, 2)}
    finally:
        conn.close()
    if not quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def selftest():
    """외부 호출 0회로 전 경로를 검증한다. 각 항목은 기대 결과가 고정돼 있다."""
    cases = [
        ("valid", "STORED", "정상 응답은 저장된다"),
        ("bad_enum", "REJECTED", "허용되지 않은 판정값은 거부된다"),
        ("out_of_range", "REJECTED", "신뢰도 범위 위반은 거부된다"),
        ("missing", "REJECTED", "필수 키 누락은 거부된다"),
        ("extra", "REJECTED", "여분 키(exit_code 위조)는 거부된다"),
        ("liar", "STORED", "형식이 맞으면 저장된다 - 내용 진위는 별도 문제"),
    ]
    print("=" * 66)
    print("CSC 수직 슬라이스 자체검증 — 외부 호출 0회")
    print("=" * 66)
    passed = 0
    for mode, expect, desc in cases:
        r = run_once("stub", "슬라이스 검증", mode, quiet=True)
        ok = r["status"] == expect
        passed += ok
        print("  %s %-14s 기대=%-8s 실제=%-8s  %s"
              % ("[OK]" if ok else "[FAIL]", mode, expect, r["status"], desc))
        if not ok:
            print("        %s" % r.get("error", ""))

    conn = db()
    n_ok = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    n_rej = conn.execute("SELECT COUNT(*) FROM rejected").fetchone()[0]
    conn.close()

    # 멱등성: 같은 입력을 두 번 돌려도 행이 늘지 않아야 한다.
    run_once("stub", "슬라이스 검증", "valid", quiet=True)
    conn = db()
    n_ok2 = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    conn.close()
    idem = n_ok == n_ok2
    passed += idem
    print("  %s %-14s 재실행 후 행 수 %d -> %d  중복 저장 없음"
          % ("[OK]" if idem else "[FAIL]", "idempotent", n_ok, n_ok2))

    # 증거 게이트: 스키마가 못 막는 거짓말을 실제 실행으로 뒤엎는지 확인한다.
    print("-" * 66)
    print("증거 게이트 — 형식은 완벽하나 내용이 거짓인 응답")
    liar_fail = run_once("stub", "거짓 주장 검증", "liar", quiet=True,
                         evidence_cmd="python3 -c \"import sys; sys.exit(1)\"")
    ok1 = liar_fail["data"]["verdict"] == "BLOCKED"
    passed += ok1
    print("  %s %-14s AI 주장=GO, 실제 종료코드=%s -> 코드 판정=%s"
          % ("[OK]" if ok1 else "[FAIL]", "override",
             liar_fail["evidence"]["real_exit_code"], liar_fail["data"]["verdict"]))

    liar_pass = run_once("stub", "참 주장 검증", "liar", quiet=True,
                         evidence_cmd="python3 -c \"import sys; sys.exit(0)\"")
    ok2 = liar_pass["data"]["verdict"] == "GO"
    passed += ok2
    print("  %s %-14s AI 주장=GO, 실제 종료코드=%s -> 코드 판정=%s"
          % ("[OK]" if ok2 else "[FAIL]", "confirm",
             liar_pass["evidence"]["real_exit_code"], liar_pass["data"]["verdict"]))

    total = len(cases) + 3
    conn = db()
    n_ok3 = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    conn.close()
    print("-" * 66)
    print("통과 %d / %d      DB: verdicts=%d  rejected=%d" % (passed, total, n_ok3, n_rej))
    print("DB 경로: %s" % DB_PATH)
    return 0 if passed == total else 1


def report():
    conn = db()
    print("--- 저장된 판정 ---")
    for row in conn.execute(
            "SELECT call_id,provider,verdict,confidence,reason FROM verdicts"):
        print("  %s  %-6s %-8s %.2f  %s" % row)
    print("--- 코드가 거부한 응답 ---")
    for row in conn.execute("SELECT call_id,provider,error FROM rejected"):
        print("  %s  %-6s %s" % row)
    conn.close()
    return 0


def main():
    ap = argparse.ArgumentParser(description="CSC 수직 슬라이스 (P2)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("selftest", help="외부 호출 없이 전 경로 검증")
    r = sub.add_parser("run", help="1회 호출")
    r.add_argument("--provider", choices=sorted(PROVIDERS), default="stub")
    r.add_argument("--task", required=True)
    r.add_argument("--stub-mode", default="valid")
    r.add_argument("--evidence-cmd", default=None, help="코드가 직접 실행할 검증 명령")
    sub.add_parser("report", help="DB 내용 출력")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "run":
        res = run_once(a.provider, a.task, a.stub_mode, evidence_cmd=a.evidence_cmd)
        return 0 if res["status"] == "STORED" else 2
    if a.cmd == "report":
        return report()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
