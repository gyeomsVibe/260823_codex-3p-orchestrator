"""Bounded, read-only CSC diagnostics. Optional send-test writes one inert EVENT."""

import json
import math
import shutil
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from csc_process import probe_pid

ROOT = Path(__file__).resolve().parent
AGENTS = {"claude": "claude", "antigravity": "agy"}
RECOVER = "python csc.py activate"


def read_object(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def exchange(endpoint, request, expected, timeout=0.75):
    """One bounded frame; no registration/audit writes for diagnostic controls."""
    with socket.create_connection(endpoint, timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((json.dumps(request) + "\n").encode())
        with sock.makefile("rb") as stream:
            raw = stream.readline(65537)
        if len(raw) > 65536 or not raw.endswith(b"\n"):
            raise ValueError("invalid response frame")
        response = json.loads(raw)
        if not isinstance(response, dict) or response.get("type") != expected:
            raise ValueError("unexpected response type")
        return response


def diagnose(project_root=None, send_test=False):
    root = Path(project_root).resolve() if project_root else ROOT
    rows = []

    def add(code, ok, reason, action=RECOVER):
        rows.append({"code": code, "ok": ok, "reason": reason,
                     "action": "없음" if ok else action})

    def finish(code):
        return {"schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
                "project_root": str(root), "status": code,
                "exit_code": 0 if code == "READY" else (2 if code == "PARTIAL_READY" else 1),
                "scope": "local_transport; AI 응답·인증·할당량은 미검증",
                "source_paths": [str(root / ".agent-swarm/broker.json"),
                                 str(root / ".agent-swarm/workers")], "checks": rows}

    if root != ROOT:
        add("WRONG_PROJECT", False, "실행 스크립트의 정본 프로젝트와 요청 경로가 다릅니다.",
            "정본 프로젝트의 csc.py로 다시 실행하세요.")
        return finish("WRONG_PROJECT")
    missing = [name for name in ("csc_broker.py", "csc_agent_worker.py", "csc_runtime.py")
               if not (root / name).is_file()]
    if missing:
        add("FILE_MISSING", False, "필수 파일 없음: " + ", ".join(missing), "정본 소스 파일을 복구하세요.")
        return finish("FILE_MISSING")
    add("FILES_PRESENT", True, "필수 구현 파일이 있습니다. 미설치 상태가 아닙니다.")
    try:
        meta = read_object(root / ".agent-swarm/broker.json")
        host, port = meta.get("host"), meta.get("port")
        if host != "127.0.0.1" or type(port) is not int or not 0 < port < 65536:
            raise ValueError("invalid local endpoint")
        if type(meta.get("pid")) is not int or meta["pid"] <= 0:
            raise ValueError("invalid PID")
    except FileNotFoundError:
        add("BROKER_STOPPED", False, "발견용 메타데이터가 없습니다. 파일 미설치와는 다릅니다.")
        return finish("BROKER_STOPPED")
    except (OSError, ValueError, TypeError):
        add("META_INVALID", False, "메타데이터를 읽을 수 없거나 로컬 주소·포트·PID 형식이 잘못됐습니다.")
        return finish("META_INVALID")
    pid_state = probe_pid(meta["pid"])
    add("BROKER_PID", pid_state == "alive", "프로세스 조회: " + pid_state,
        "unknown은 권한으로 확인하지 못했다는 뜻입니다. 종료로 단정하지 마세요.")
    endpoint = (host, port)
    try:
        exchange(endpoint, {"type": "PING"}, "PONG")
    except ConnectionRefusedError:
        add("SOCKET_REFUSED", False, "연결이 거절됐습니다. RUNNING 파일만으로 실행 중이라 할 수 없습니다.")
        return finish("SOCKET_REFUSED")
    except (OSError, ValueError):
        add("BROKER_UNRESPONSIVE", False, "제한 시간 안에 유효한 PONG을 받지 못했습니다.")
        return finish("BROKER_UNRESPONSIVE")
    add("BROKER_LIVE", True, "로컬 소켓에서 유효한 PONG을 받았습니다.")
    try:
        roster = exchange(endpoint, {"type": "ROSTER"}, "ROSTER")
        registered = roster.get("registered_agents")
        if not isinstance(registered, list) or not all(isinstance(x, str) for x in registered):
            raise ValueError("invalid roster")
    except (OSError, ValueError):
        add("ROSTER_MISSING", False, "유효한 연결 명단을 받지 못했습니다.")
        return finish("PARTIAL_READY")
    for agent, executable in AGENTS.items():
        add("CLI_PRESENT:" + agent, shutil.which(executable) is not None,
            executable + " 실행 파일 검색 결과입니다. 로그인·AI 응답 검증은 별도입니다.",
            "해당 CLI의 설치 상태를 확인하세요.")
        try:
            worker = read_object(root / ".agent-swarm/workers" / (agent + ".json"))
            heartbeat = worker.get("heartbeat_epoch")
            age = time.time() - heartbeat if type(heartbeat) in (int, float) else float("inf")
            fresh = math.isfinite(age) and 0 <= age <= 10
            live = (worker.get("agent") == agent and worker.get("status") == "ready"
                    and probe_pid(worker.get("pid")) == "alive" and fresh and agent in registered)
        except (OSError, ValueError, TypeError):
            live = False
        add(("WORKER_LIVE:" if live else "WORKER_STALE:") + agent, live,
            agent + ": 등록·생존·10초 이내 하트비트가 모두 일치해야 준비 상태입니다.")
    if send_test:
        # Non-TASK message addressed to a diagnostic inbox cannot trigger an AI turn.
        from csc_broker import SwarmClientSync
        message_id = "doctor-" + uuid.uuid4().hex
        request = {"type": "EVENT", "message_id": message_id, "sender": "doctor",
                   "recipient": "doctor", "body": "CSC diagnostic persistence probe"}
        response = SwarmClientSync().send_message(request, agent_name="doctor")
        found = False
        inbox = root / ".agent-swarm/messages/doctor_inbox.jsonl"
        if inbox.exists():
            with inbox.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        value = json.loads(line)
                        if isinstance(value, dict) and value.get("message_id") == message_id:
                            found = True
                            break
                    except ValueError:
                        continue
        ok = response.get("persisted") is True and response.get("message_id") == message_id and found
        add("PERSISTENCE_PROBE", ok, "진단 EVENT의 저장 ACK와 진단 inbox 회수를 대조했습니다.")
    return finish("READY" if all(row["ok"] for row in rows) else "PARTIAL_READY")


def print_report(report):
    print(f"CSC 진단: {report['status']} (종료 코드 {report['exit_code']})")
    print(f"프로젝트: {report['project_root']} | 검사 시각: {report['checked_at']}")
    print("검증 범위: " + report["scope"])
    for row in report["checks"]:
        print(f"[{row['code']}] {row['reason']} 다음 행동: {row['action']}")
