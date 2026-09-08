#!/usr/bin/env python
"""Lifecycle manager for the CSC broker and persistent CLI adapters."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from csc_worker import initialize_cursor_at_queue_end, metadata_is_stale, pid_is_alive


DEFAULT_AGENTS = ("claude", "antigravity")


class ActivationError(RuntimeError):
    pass


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    # CREATE_NO_WINDOW hides console window while preserving valid redirected handles.
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.CREATE_NEW_PROCESS_GROUP | create_no_window


def _terminate_pid_tree(pid: int) -> None:
    if not pid_is_alive(pid):
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    else:
        os.kill(pid, 15)


def _broker_metadata(project_root: Path) -> Dict[str, Any]:
    return _read_json(project_root / ".agent-swarm" / "broker.json")


def broker_is_running(project_root: os.PathLike[str] | str) -> bool:
    root = Path(project_root).resolve()
    metadata = _broker_metadata(root)
    try:
        with socket.create_connection(
            (str(metadata.get("host", "127.0.0.1")), int(metadata.get("port", 8765))),
            timeout=0.5,
        ) as sock:
            sock.sendall(b'{"type":"PING"}\n')
            sock.settimeout(0.5)
            return json.loads(sock.recv(4096).split(b"\n", 1)[0])["type"] == "PONG"
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def ensure_broker(
    project_root: os.PathLike[str] | str,
    port: int = 8765,
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    existing = _broker_metadata(root)
    if broker_is_running(root):
        return {"action": "reused", "pid": existing.get("pid"), "port": existing.get("port", port)}

    logs = root / ".agent-swarm" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = str(logs / "broker-runtime.log")
    log_fd = os.open(log_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY)
    try:
        process = popen_factory(
            [sys.executable, str(root / "csc_broker.py"), "--port", str(port)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            creationflags=_creation_flags(),
        )
    finally:
        os.close(log_fd)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if broker_is_running(root):
            metadata = _broker_metadata(root)
            return {"action": "started", "pid": metadata.get("pid", process.pid), "port": metadata.get("port", port)}
        time.sleep(0.05)
    raise ActivationError("broker failed its bounded PING readiness check")


def worker_is_fresh(
    agent: str,
    project_root: os.PathLike[str] | str,
    stale_after: float = 10.0,
) -> bool:
    root = Path(project_root).resolve()
    metadata = _read_json(root / ".agent-swarm" / "workers" / f"{agent}.json")
    return bool(metadata) and not metadata_is_stale(metadata, stale_after)


def ensure_worker(
    agent: str,
    project_root: os.PathLike[str] | str,
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    registered_agents: Optional[set[str]] = None,
) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    metadata_path = root / ".agent-swarm" / "workers" / f"{agent}.json"
    metadata = _read_json(metadata_path)
    fresh = worker_is_fresh(agent, root)
    connected = registered_agents is None or agent in registered_agents

    if fresh and connected:
        return {"agent": agent, "action": "reused", "pid": metadata.get("pid")}

    old_pid = metadata.get("pid")
    if isinstance(old_pid, int) and pid_is_alive(old_pid):
        _terminate_pid_tree(old_pid)
    # First activation is a new subscription boundary, not a replay of stale history.
    initialize_cursor_at_queue_end(agent, root)

    logs = root / ".agent-swarm" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = str(logs / f"{agent}-worker.log")
    log_fd = os.open(log_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        process = popen_factory(
            [
                sys.executable, str(root / "csc_agent_worker.py"),
                "--agent", agent, "--project-root", str(root),
            ],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            creationflags=_creation_flags(),
            env=env,
        )
    finally:
        os.close(log_fd)
    return {"agent": agent, "action": "started", "pid": process.pid}


def query_roster(
    project_root: os.PathLike[str] | str,
    timeout: float = 1.0,
) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    metadata = _broker_metadata(root)
    host = str(metadata.get("host", "127.0.0.1"))
    port = int(metadata.get("port", 8765))
    control_name = f"codex-control-{os.getpid()}"
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((json.dumps({"type": "REGISTER", "agent": control_name}) + "\n").encode())
        rfile = sock.makefile("r", encoding="utf-8")
        register_ack = json.loads(rfile.readline())
        if register_ack.get("type") != "REGISTER_ACK":
            raise ActivationError("broker did not acknowledge control registration")
        sock.sendall(b'{"type":"ROSTER"}\n')
        while True:
            line = rfile.readline()
            if not line:
                raise ActivationError("broker closed before ROSTER response")
            response = json.loads(line)
            if response.get("type") == "ROSTER":
                response["registered_agents"] = [
                    name for name in response.get("registered_agents", [])
                    if not str(name).startswith("codex-control-")
                ]
                response["count"] = len(response["registered_agents"])
                return response


def activate(
    project_root: os.PathLike[str] | str,
    timeout: float = 10.0,
    poll_interval: float = 0.1,
) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    (root / ".agent-swarm" / "workers").mkdir(parents=True, exist_ok=True)
    broker = ensure_broker(root)
    initial_roster: set[str] = set()
    try:
        initial_roster = set(query_roster(root, timeout=0.5).get("registered_agents", []))
    except Exception:
        pass
    workers = [ensure_worker(agent, root, registered_agents=initial_roster) for agent in DEFAULT_AGENTS]
    expected = set(DEFAULT_AGENTS)
    deadline = time.monotonic() + timeout
    midpoint = time.monotonic() + (timeout / 2)
    healed = False
    last_roster: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last_roster = query_roster(root, timeout=min(1.0, max(0.1, poll_interval * 5)))
        except (OSError, ValueError, ActivationError, json.JSONDecodeError):
            last_roster = {}
        registered = set(last_roster.get("registered_agents", []))
        fresh = all(worker_is_fresh(agent, root) for agent in expected)
        if expected.issubset(registered) and fresh:
            return {
                "status": "ready",
                "broker": broker,
                "workers": workers,
                "registered_agents": sorted(expected),
            }
        # 절반 경과 후에도 미등록된 워커가 있으면 강제 재기동 1회 수행 (Self-Healing)
        if not healed and time.monotonic() > midpoint:
            missing = expected - registered
            for missing_agent in missing:
                ensure_worker(missing_agent, root, registered_agents=registered)
            healed = True
        time.sleep(poll_interval)
    raise ActivationError(
        "activation timed out: expected live socket registrations and fresh heartbeats "
        f"for {sorted(expected)}; last roster={last_roster.get('registered_agents', [])}"
    )
