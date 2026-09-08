#!/usr/bin/env python
"""진단 실행기 (clinic runner) — 훅과 스케줄러가 부를 수 있는 껍데기.

왜 이 파일이 있는가
    진단 항목(.vibe-clinic/diagnostics/*.clinic.js)은 vibe-clinic MCP 도구로 돌릴 수 있다.
    그런데 훅(hook, 특정 시점에 자동 실행되는 짧은 명령)과
    스케줄러(scheduler, 정해진 시각에 자동 실행하는 장치)는 MCP 도구를 부를 수 없다.

    그래서 같은 진단 파일을 Node.js 로 직접 돌리는 껍데기를 둔다.
    진단 내용을 복사하지 않는다 — 같은 파일을 두 경로에서 부를 뿐이다.
    같은 판정을 두 곳에서 따로 계산하면 언젠가 서로 다른 답을 낸다.

자동 발동 조건
    .agent-swarm/BUILD_PHASE 가 있으면    -> 만드는 단계. 진단하지 않는다
    .agent-swarm/BUILD_PHASE 가 없으면    -> 고치는 단계. 진단을 돌린다

    새 신호를 만들지 않았다. 이미 있는 단계 표시가 곧 방아쇠다.

반드시 지키는 계약
    1. 진단이 0개면 실패로 처리한다. "검사할 것이 없음" 을 "이상 없음" 으로 쓰지 않는다
    2. 실행 기록을 파일로 남긴다. 침묵과 미실행을 구분한다
    3. 통과에도 "무엇을 검사하지 않았는지" 를 함께 보여준다
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SWARM = os.path.join(HERE, ".agent-swarm")
PHASE_FILE = os.path.join(SWARM, "BUILD_PHASE")
DIAG_DIR = os.path.join(HERE, ".vibe-clinic", "diagnostics")
RUN_LOG = os.path.join(SWARM, "clinic_runs.jsonl")
REPORT_DIR = os.path.join(SWARM, "clinic_reports")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def build_phase() -> bool:
    """지금이 '먼저 만드는 단계' 인가. csc_audit 과 같은 파일을 본다."""
    return os.path.exists(PHASE_FILE)


def diagnostics() -> list[str]:
    """진단 파일 목록. 밑줄로 시작하는 것은 공용 도구이므로 뺀다."""
    if not os.path.isdir(DIAG_DIR):
        return []
    return sorted(
        f for f in os.listdir(DIAG_DIR)
        if f.endswith(".clinic.js") and not f.startswith("_")
    )


# Node 로 진단 하나를 돌리는 짧은 스크립트.
# 진단 파일의 계약(module.exports = {id, name, run(ctx)})을 그대로 따른다.
_NODE_RUNNER = r"""
const path = require('path');
// node -e 로 실행하면 argv 에 스크립트 경로가 들어가지 않는다.
//   node script.js A B  ->  argv = [node, script.js, A, B]   (인수는 [2]부터)
//   node -e "..."  A B  ->  argv = [node, A, B]              (인수는 [1]부터)
// 처음에 [2],[3] 으로 썼다가 진단 네 개가 전부 '모듈을 못 찾음' 으로 터졌다.
const file = process.argv[1], root = process.argv[2];
(async () => {
  try {
    const mod = require(file);
    const r = await mod.run({ projectDir: root, cwd: root });
    process.stdout.write(JSON.stringify({
      id: mod.id, name: mod.name, status: r.status, details: r.details }));
  } catch (e) {
    // 진단이 터진 것과 진단이 문제를 찾은 것은 다르다. 구분해서 내보낸다.
    process.stdout.write(JSON.stringify({
      id: path.basename(file), name: path.basename(file),
      status: 'ERROR', details: '진단 자체가 실패했습니다: ' + (e && e.message) }));
  }
})();
"""


def run_one(filename: str) -> dict:
    path = os.path.join(DIAG_DIR, filename)
    try:
        proc = subprocess.run(
            ["node", "-e", _NODE_RUNNER, path, HERE],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300, cwd=HERE,
        )
    except Exception as exc:
        return {"id": filename, "name": filename, "status": "ERROR",
                "details": f"실행하지 못했습니다: {exc}"}
    out = (proc.stdout or "").strip()
    if not out:
        # 출력이 없는 것을 통과로 읽지 않는다. 이 프로젝트가 반복해서 데인 형태다.
        return {"id": filename, "name": filename, "status": "ERROR",
                "details": "진단이 아무 결과도 내지 않았습니다. "
                           f"종료코드 {proc.returncode}. "
                           f"오류: {(proc.stderr or '').strip()[:200]}"}
    try:
        return json.loads(out)
    except Exception:
        return {"id": filename, "name": filename, "status": "ERROR",
                "details": f"결과를 읽지 못했습니다: {out[:200]}"}


def record(payload: dict) -> None:
    """실행 기록. 침묵과 미실행을 구분하기 위해 항상 남긴다."""
    try:
        os.makedirs(os.path.dirname(RUN_LOG), exist_ok=True)
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def run_all() -> dict:
    files = diagnostics()
    started = datetime.now().astimezone().isoformat()

    # 계약 1: 진단이 0개면 실패다.
    # "검사할 것이 없음" 과 "이상 없음" 은 다르다.
    # 아무것도 검사하지 않고 100% 건강을 보고하는 것이 이 프로젝트가 싸워 온 형태다.
    if not files:
        out = {"at": started, "phase": "구현" if build_phase() else "수정",
               "total": 0, "status": "ERROR",
               "reason": "진단 항목이 하나도 없습니다. 검사한 것이 없으므로 통과라고 말할 수 없습니다.",
               "results": []}
        record(out)
        return out

    results = [run_one(f) for f in files]
    err = sum(1 for r in results if r.get("status") == "ERROR")
    warn = sum(1 for r in results if r.get("status") == "WARNING")
    ok = sum(1 for r in results if r.get("status") == "OK")
    out = {
        "at": started, "phase": "구현" if build_phase() else "수정",
        "total": len(results), "ok": ok, "warning": warn, "error": err,
        "status": "ERROR" if err else ("WARNING" if warn else "OK"),
        "health_percent": round(ok * 100 / len(results)),
        "results": results,
    }
    record(out)
    return out


def render(out: dict) -> str:
    icon = {"OK": "🟢", "WARNING": "🟡", "ERROR": "🔴"}
    lines = [
        "=" * 68,
        f"자가진단 결과 — {icon.get(out['status'], '?')} {out['status']}"
        + (f"  (건강도 {out['health_percent']}%)" if "health_percent" in out else ""),
        f"단계: {out['phase']} · 검사 {out.get('total', 0)}개"
        + (f" (정상 {out.get('ok',0)} · 주의 {out.get('warning',0)} · 문제 {out.get('error',0)})"
           if out.get("total") else ""),
        "=" * 68,
    ]
    if not out.get("results"):
        lines.append(f"🔴 {out.get('reason', '결과 없음')}")
        return "\n".join(lines)
    for r in out["results"]:
        lines.append(f"\n{icon.get(r.get('status'), '?')} {r.get('name')}")
        for ln in str(r.get("details", "")).split("\n"):
            lines.append(f"   {ln}")
    lines.append("\n" + "-" * 68)
    lines.append("※ '정상' 은 '문제가 없다' 가 아니라 '검사한 범위에서 못 찾았다' 는 뜻입니다.")
    lines.append("   각 항목의 '검사하지 않은 것' 을 함께 읽으세요.")
    return "\n".join(lines)


def milestone_slug(value: str) -> str:
    """Turn a user label into one bounded filename component."""
    original = value.strip()
    if not original:
        raise ValueError("마일스톤 이름은 비워 둘 수 없습니다")
    slug = re.sub(r"[^\w-]+", "_", original, flags=re.UNICODE).strip("_-")[:80]
    if not slug:
        raise ValueError("마일스톤 이름에는 문자나 숫자가 하나 이상 필요합니다")
    return slug


def current_git_head() -> tuple[str, str]:
    """Return the current commit and a visible diagnostic when Git is unavailable."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "UNKNOWN", f"{type(exc).__name__}: {exc}"
    head = (proc.stdout or "").strip()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        detail = (proc.stderr or proc.stdout or "유효한 커밋 해시가 없습니다").strip()
        return "UNKNOWN", detail[:300]
    return head, ""


def write_milestone_report(
    milestone: str,
    out: dict,
    now: datetime | None = None,
) -> str:
    """Write one collision-safe runtime draft and return its absolute path."""
    slug = milestone_slug(milestone)
    observed = now or datetime.now().astimezone()
    stamp = observed.strftime("%Y%m%dT%H%M%S%f%z")
    head, head_error = current_git_head()
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f"{slug}-{stamp}.md")
    payload = json.dumps(out, ensure_ascii=False, indent=2)
    lines = [
        "# 마일스톤 자가진단 초안 보고서",
        "",
        f"- 마일스톤 원문: {json.dumps(milestone.strip(), ensure_ascii=False)}",
        f"- 보고서 생성 시각: `{observed.isoformat()}`",
        f"- Git HEAD: `{head}`",
        f"- 진단 상태: `{out.get('status', 'UNKNOWN')}`",
    ]
    if head_error:
        lines.append(f"- Git HEAD 조회 오류: {json.dumps(head_error, ensure_ascii=False)}")
    lines.extend(["", "## 기계 진단 결과(JSON)", ""])
    lines.extend(f"    {line}" for line in payload.splitlines())
    lines.append("")
    with open(path, "x", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="진단을 돌린다. 고치는 단계에서 자동 발동한다")
    ap.add_argument("--force", action="store_true",
                    help="만드는 단계여도 강제로 돌린다")
    ap.add_argument("--check-phase", action="store_true",
                    help="단계만 확인하고 끝낸다 (훅이 쓴다)")
    ap.add_argument("--milestone",
                    help="명시한 마일스톤을 진단하고 런타임 초안 보고서를 남긴다")
    args = ap.parse_args()

    if args.check_phase:
        print("구현" if build_phase() else "수정")
        return 0

    if args.milestone is not None:
        try:
            milestone_slug(args.milestone)
        except ValueError as exc:
            ap.error(str(exc))

    if build_phase() and not args.force and args.milestone is None:
        print("지금은 '먼저 만드는 단계' 입니다. 진단을 돌리지 않습니다.")
        print("고칠 준비가 되면 .agent-swarm/BUILD_PHASE 파일을 지우세요.")
        print("지금 바로 보고 싶으면 --force 를 붙이세요.")
        return 0

    out = run_all()
    print(render(out))
    if args.milestone is not None:
        try:
            report_path = write_milestone_report(args.milestone, out)
        except (OSError, ValueError) as exc:
            print(f"🔴 마일스톤 초안 보고서를 쓰지 못했습니다: {exc}", file=sys.stderr)
            return 2
        print(f"\n초안 보고서: {report_path}")
    return 0 if out["status"] == "OK" else (1 if out["status"] == "WARNING" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
