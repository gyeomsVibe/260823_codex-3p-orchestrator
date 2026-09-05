#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSC 증거 게이트 — RESULT 주장을 코드가 직접 검증한다.

왜 필요한가 (csc_slice.py 실증에서 나온 결론):
    스키마 검증은 형식만 막는다. 형식이 완벽한 거짓말은 통과한다.
        {"verdict":"GO","reason":"테스트 전부 통과했습니다 exit_code 0"}
    이 응답은 어떤 스키마 검증도 통과한다. 실행이 안 됐어도 통과한다.

    그래서 스케줄러가 에이전트에게 결과를 묻지 않고 직접 실행한다.
    주장과 실측이 어긋나면 코드가 판정을 뒤엎는다.

호출 지점:
    csc_worker.py 의 _persist_result() — RESULT 를 저장하기 직전.

설계 원칙:
    1) 증거 명령이 없으면 아무것도 하지 않는다(UNVERIFIED 로 표시만).
    2) 검증 자체가 실패해도 워커를 죽이지 않는다(fail-safe).
    3) 판정을 뒤집을 때는 원 주장을 지우지 않고 보존한다(규약 제3조).
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ENC = "utf-8"
for _s in (sys.stdout, sys.stderr):          # cp949 머신 대비
    try:
        _s.reconfigure(encoding=ENC, errors="replace")
    except Exception:
        pass

# RESULT 본문에서 "성공했다"는 주장을 찾아내는 패턴.
# 이 표현들이 있는데 증거가 없으면 UNVERIFIED 로 강등한다.
SUCCESS_CLAIM = re.compile(
    r"\b(exit[ _-]?code\s*[:=]?\s*0|passed|success|통과|성공|완료)\b",
    re.IGNORECASE)

MAX_STDOUT_LINES = 10
DEFAULT_TIMEOUT = 120


def _now():
    return datetime.now(timezone.utc).isoformat()


POLICY_PATH_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".agent-swarm", "evidence_policy.json")


class PolicyError(Exception):
    pass


def load_policy(policy_path=None):
    """운영자 소유 검증 정책을 읽는다. 메시지는 이 파일을 바꿀 수 없다."""
    path = policy_path or POLICY_PATH_DEFAULT
    try:
        with open(path, "r", encoding=ENC) as f:
            doc = json.load(f)
    except FileNotFoundError:
        raise PolicyError("검증 정책 파일이 없다: %s" % path)
    except Exception as exc:
        raise PolicyError("정책 파일을 읽을 수 없다: %s" % exc)
    checks = doc.get("checks")
    if not isinstance(checks, dict):
        raise PolicyError("정책에 'checks' 객체가 없다")
    return checks


def resolve_check(check_name, policy_path=None):
    """이름을 argv 로 해석한다. 정책에 없는 이름은 절대 실행하지 않는다.

    ★ 보안 핵심 ★
    명령은 메시지가 아니라 정책 파일에서만 온다.
    이것이 GitHub Actions 의 pull_request_target "pwn request" 와 같은
    신뢰경계 위반을 막는 유일한 방법이다.
    REDTEAM 실증: 이 분리가 없을 때 evidence_cmd="exit 0" 하나로 자기인증이 뚫렸고,
    메시지 내용이 그대로 셸에서 실행돼 임의 파일이 생성됐다.
    """
    if not isinstance(check_name, str) or not check_name:
        raise PolicyError("check 이름이 문자열이 아니다")
    checks = load_policy(policy_path)
    entry = checks.get(check_name)
    if entry is None:
        raise PolicyError("정책에 없는 check 이름: %r (허용: %s)"
                          % (check_name, ", ".join(sorted(checks))))
    argv = entry.get("argv")
    if not isinstance(argv, list) or not argv or not all(
            isinstance(a, str) for a in argv):
        raise PolicyError("check '%s' 의 argv 정의가 잘못됐다" % check_name)
    return list(argv), entry.get("desc", "")


def run_evidence(argv, cwd=None, timeout=DEFAULT_TIMEOUT):
    """정책에서 해석된 argv 를 실행한다. 셸을 절대 쓰지 않는다.

    shell=True 는 메시지 내용이 셸 메타문자로 해석되는 경로를 열어준다.
    argv 리스트만 받고 shell 은 항상 False 다.
    """
    if not isinstance(argv, list):
        raise PolicyError("argv 는 리스트여야 한다 (문자열 명령 금지)")
    exe = shutil.which(argv[0])
    # 실측 근거: Windows 에서 codex 는 .CMD 라 확장자 없는 이름이 WinError 2 를 낸다.
    if exe:
        argv = [exe] + list(argv[1:])
    try:
        proc = subprocess.run(argv, shell=False, capture_output=True,
                              text=True, encoding=ENC, errors="replace",
                              timeout=timeout, cwd=cwd,
                              stdin=subprocess.DEVNULL)
        tail = (proc.stdout or "").strip().splitlines()[-MAX_STDOUT_LINES:]
        return {"ran": True, "exit_code": proc.returncode,
                "stdout_tail": tail,
                "stderr_head": (proc.stderr or "").strip()[:400],
                "at": _now()}
    except subprocess.TimeoutExpired:
        return {"ran": False, "exit_code": None,
                "error": "timeout %ss 초과" % timeout, "at": _now()}
    except Exception as exc:                     # 검증 실패가 워커를 죽이면 안 된다.
        return {"ran": False, "exit_code": None,
                "error": "%s: %s" % (type(exc).__name__, exc), "at": _now()}


def gate(body, evidence_check=None, cwd=None, timeout=DEFAULT_TIMEOUT,
         policy_path=None):
    """RESULT 본문을 증거로 검증한다.

    `evidence_check` 는 **정책 파일에 등록된 이름**이다. 명령이 아니다.
    메시지가 실행할 명령을 직접 지정하는 경로는 존재하지 않는다.

    반환: (최종_본문, 증거_dict)
      - check 이름 없음        -> UNVERIFIED (주장일 뿐임을 명시)
      - 정책에 없는 이름       -> UNVERIFIED + POLICY_VIOLATION (실행하지 않음)
      - 종료코드 0            -> VERIFIED
      - 종료코드 != 0         -> BLOCKED (성공 주장이면 판정을 뒤집는다)
      - 실행 자체 실패        -> UNVERIFIED (조용히 통과시키지 않는다)
    """
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    claims_success = bool(SUCCESS_CLAIM.search(text))

    if not evidence_check:
        ev = {"ran": False, "status": "UNVERIFIED",
              "note": "검증 check 이름이 지정되지 않았다. 이 RESULT 는 주장일 뿐 검증되지 않았다.",
              "claims_success": claims_success, "at": _now()}
        return text, ev

    try:
        argv, desc = resolve_check(evidence_check, policy_path)
    except PolicyError as exc:
        # 정책에 없는 이름은 실행하지 않는다. 이것이 RCE 를 막는 지점이다.
        ev = {"ran": False, "status": "UNVERIFIED", "policy_violation": True,
              "check": evidence_check, "error": str(exc),
              "claims_success": claims_success, "at": _now()}
        return ("[정책 위반] 등록되지 않은 검증 이름이라 실행하지 않았다: %s\n"
                "--- 원 주장 (보존) ---\n%s" % (exc, text)), ev

    ev = run_evidence(argv, cwd=cwd, timeout=timeout)
    ev["check"] = evidence_check
    ev["desc"] = desc
    ev["argv"] = argv
    ev["claims_success"] = claims_success

    if not ev.get("ran"):
        ev["status"] = "UNVERIFIED"
        return ("[증거 미확보] %s\n--- 원 주장 (보존) ---\n%s"
                % (ev.get("error", "실행 실패"), text)), ev

    if ev["exit_code"] == 0:
        ev["status"] = "VERIFIED"
        return text, ev

    ev["status"] = "BLOCKED"
    ev["override"] = ("성공을 주장했으나 실제 종료코드가 %s 다" % ev["exit_code"]
                      if claims_success else
                      "실제 종료코드가 %s 다" % ev["exit_code"])
    # 원 주장을 삭제하지 않는다. 규약 제3조 — 정정은 덮어쓰기가 아니라 덧붙이기다.
    return ("[코드 판정: BLOCKED] %s\n실행: %s\nstdout(마지막 %d줄): %s\n"
            "--- 원 주장 (보존) ---\n%s"
            % (ev["override"], " ".join(argv), MAX_STDOUT_LINES,
               " | ".join(ev.get("stdout_tail") or []) or "(없음)", text)), ev


def selftest():
    """정책 기반 게이트를 검증한다. REDTEAM 재현 케이스를 포함한다."""
    cases = [
        ("check 이름 없음 -> UNVERIFIED", "테스트 통과했습니다", None, "UNVERIFIED"),
        ("정책 등록 check, exit 0 -> VERIFIED", "테스트 통과했습니다",
         "noop_pass", "VERIFIED"),
        ("정책 미등록 이름 -> 실행 안 함", "완료했습니다",
         "__없는check__", "UNVERIFIED"),
    ]
    print("=" * 66)
    print("csc_evidence 증거 게이트 자체검증 (정책 기반)")
    print("=" * 66)
    ok = 0
    for name, body, check, expect in cases:
        _, ev = gate(body, check)
        good = ev["status"] == expect
        ok += good
        print("  %s %-38s 기대=%-10s 실제=%s"
              % ("[OK]" if good else "[FAIL]", name, expect, ev["status"]))

    # REDTEAM A: 자기인증 시도 — 메시지가 명령을 직접 지정
    _, ev = gate("테스트 전부 통과했습니다 exit_code 0", "exit 0")
    a = ev["status"] == "UNVERIFIED" and ev.get("policy_violation") is True
    ok += a
    print("  %s %-38s 명령 문자열은 이름으로 취급돼 거부됨"
          % ("[OK]" if a else "[FAIL]", "REDTEAM A 자기인증 차단"))

    # REDTEAM B: RCE 시도 — 메시지가 임의 명령 주입
    marker = os.path.join(tempfile.gettempdir(), "csc_rce_proof.txt")
    if os.path.exists(marker):
        os.remove(marker)
    payload = 'python -c "open(r\'' + marker + '\',\'w\').write(1)"'
    _, ev = gate("완료했습니다", payload)
    b = (not os.path.exists(marker)) and ev["status"] == "UNVERIFIED"
    ok += b
    print("  %s %-38s 주입 명령 미실행, 마커 파일 없음"
          % ("[OK]" if b else "[FAIL]", "REDTEAM B RCE 차단"))
    if os.path.exists(marker):
        os.remove(marker)

    # 셸 실행 경로가 실제 호출에 남아 있지 않은지 AST 로 판정한다.
    # 문자열 검색은 두 번 오탐했다 — 주석에서 한 번, docstring 에서 한 번.
    # 설명하는 문장과 실행하는 코드는 구분돼야 한다. AST 만이 그걸 구분한다.
    import ast as _ast
    tree = _ast.parse(io.open(os.path.abspath(__file__), encoding=ENC).read())
    hits = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            for kw in node.keywords or []:
                if (kw.arg == "shell"
                        and isinstance(kw.value, _ast.Constant)
                        and kw.value.value is True):
                    hits.append(getattr(node, "lineno", "?"))
    no_shell = not hits
    ok += no_shell
    print("  %s %-38s 실제 호출에 shell=True 없음%s"
          % ("[OK]" if no_shell else "[FAIL]", "셸 경로 제거",
             "" if no_shell else " (%s행)" % hits))

    total = len(cases) + 3
    print("-" * 66)
    print("통과 %d / %d" % (ok, total))
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(selftest())
