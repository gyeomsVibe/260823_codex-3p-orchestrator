#!/usr/bin/env python
"""Persistent CSC adapter for Claude Code and Antigravity CLIs.

The Python adapter remains connected; the interactive CLI does not. Each TASK
starts one bounded, non-interactive, read-only CLI turn using cached auth.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from csc_worker import QueueWorker


SUPPORTED_AGENTS = {"claude", "antigravity"}
QUOTA_MARKERS = (
    "session limit", "usage limit", "rate limit", "quota", "credit exhausted",
    "too many requests", "http 429", "resets ",
)
AUTH_MARKERS = (
    "not logged in", "login required", "authentication required", "unauthorized",
    "http 401", "please sign in",
)


class AgentUnavailable(RuntimeError):
    def __init__(self, availability_code: str, message: str):
        super().__init__(message)
        self.availability_code = availability_code


def terminate_process_tree(process: subprocess.Popen) -> None:
    """Terminate exactly one spawned CLI process tree after a timeout."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    else:
        process.kill()


class BoundedCliExecutor:
    """Runs one read-only agent turn with a hard deadline."""

    def __init__(
        self,
        agent: str,
        project_root: os.PathLike[str] | str,
        # 실측 근거 (2026-09-05): 120초는 '실제로 파일을 읽고 검토하는' 과업에 부족했다.
        #   도구를 막았을 때는 20초 만에 지어내서 끝났으므로 120초로 충분해 보였다.
        #   도구를 허용하자 진짜 작업이 시작됐고 120초에서 잘려 2회 재시도 후 실패했다.
        #   즉 이전의 '넉넉한 타임아웃'은 할루시네이션이 만든 착시였다.
        # CSC_WORKER_TIMEOUT 환경변수로 재정의 가능.
        timeout: float = float(os.environ.get("CSC_WORKER_TIMEOUT", "600")),
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        process_tree_terminator: Callable[[subprocess.Popen], None] = terminate_process_tree,
    ) -> None:
        normalized = agent.strip().lower()
        if normalized not in SUPPORTED_AGENTS:
            raise ValueError(f"unsupported agent: {agent}")
        self.agent = normalized
        self.project_root = Path(project_root).resolve()
        self.timeout = timeout
        self.popen_factory = popen_factory
        self.process_tree_terminator = process_tree_terminator

    def command_for(self, prompt: str) -> list[str]:
        if self.agent == "claude":
            # 읽기 전용 도구를 허용한다.
            #
            # 실증 근거 (2026-09-05, app/index.html 3분할 1차 실행):
            #   --tools "" 로 도구를 전부 막은 채 "파일을 직접 읽고 검토하라"고 지시했더니
            #   모델이 "못 읽는다"고 말하는 대신 도구 호출과 그 출력을 **지어냈다**.
            #   "1074 lines" 라고 보고했으나 실제 파일은 346 lines 였다.
            #
            # 즉 능력을 뺏은 채 그 능력을 요구하면 할루시네이션을 유도하게 된다.
            # 쓰기·실행 도구는 여전히 주지 않는다(읽기 전용 유지).
            # --max-turns 도 1 -> 6 으로 늘린다. 1턴이면 읽고 판단할 여지가 없다.
            return [
                "claude", "--safe-mode", "--restricted",
                "--permission-mode", "plan",
                "--permission-prompts", "none",
                "--tools", "Read,Grep,Glob",
                "--allowed-tools", "Read,Grep,Glob",
                "--output-format", "text", "--max-turns", "6", "-p", prompt,
            ]
        seconds = max(1, int(self.timeout))
        return [
            "agy", "--mode", "plan", "--sandbox", "--disable-slash-commands",
            "--output-format", "text", "--print-timeout", f"{seconds}s",
            "--print", prompt,
        ]

    def __call__(self, message: Dict[str, Any]) -> str:
        prompt = str(message.get("body", "")).strip()
        if not prompt:
            raise ValueError("TASK body must not be empty")
        command = self.command_for(prompt)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        try:
            process = self.popen_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self.project_root),
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            raise AgentUnavailable("binary_missing", f"{self.agent} CLI is not installed") from exc

        try:
            stdout, stderr = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            self.process_tree_terminator(process)
            raise TimeoutError(f"{self.agent} CLI exceeded {self.timeout:.1f}s") from exc

        combined = "\n".join(part for part in (stdout, stderr) if part).strip()
        if process.returncode != 0:
            lowered = combined.lower()
            if any(marker in lowered for marker in QUOTA_MARKERS):
                raise AgentUnavailable("quota_exhausted", combined or "CLI quota exhausted")
            if any(marker in lowered for marker in AUTH_MARKERS):
                raise AgentUnavailable("auth_unavailable", combined or "CLI authentication unavailable")
            raise RuntimeError(f"{self.agent} CLI failed with exit code {process.returncode}: {combined[:500]}")
        if not stdout.strip():
            # stderr 를 버리지 않는다.
            #
            # 실측 근거 (2026-09-05, antigravity 무응답 4건 규명):
            #   CLI 는 정확한 원인을 stderr 로 알려주고 있었다 —
            #   'a tool required the "escalate_admin" permission that headless mode
            #    cannot prompt for, so it was auto-denied.'
            #   그런데 이 줄이 "returned no output" 으로 뭉개져 DLQ 에 기록됐고,
            #   그 결과 원인 규명에 몇 시간이 걸렸다.
            #   진단을 버리는 오류 메시지는 오류를 숨기는 것과 같다.
            detail = (stderr or "").strip()
            raise RuntimeError(
                f"{self.agent} CLI returned no output"
                + (f" | stderr: {detail[:600]}" if detail else " | stderr 도 비어 있음")
            )
        return stdout.strip()


class RegisteredQueueWorker:
    """Keeps a broker registration alive and consumes the durable queue."""

    def __init__(
        self,
        agent: str,
        project_root: os.PathLike[str] | str,
        executor: Optional[Callable[[Dict[str, Any]], Any]] = None,
        host: str = "127.0.0.1",
        port: int = 8765,
        poll_interval: float = 0.25,
    ) -> None:
        self.agent = agent.strip().lower()
        self.project_root = Path(project_root).resolve()
        self.executor = executor or BoundedCliExecutor(self.agent, self.project_root)
        self.queue_worker = QueueWorker(self.agent, self.project_root, executor=self.executor)
        self.host = host
        self.port = port
        self.poll_interval = max(0.02, poll_interval)
        self._socket: Optional[socket.socket] = None

    def _connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=2.0)
        sock.settimeout(2.0)
        sock.sendall((json.dumps({"type": "REGISTER", "agent": self.agent}) + "\n").encode("utf-8"))
        buffer = b""
        while b"\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("broker closed during REGISTER")
            buffer += chunk
        ack = json.loads(buffer.split(b"\n", 1)[0].decode("utf-8"))
        if ack.get("type") != "REGISTER_ACK" or ack.get("status") != "ok":
            raise ConnectionError(f"broker rejected REGISTER: {ack}")
        sock.settimeout(self.poll_interval)
        self._socket = sock

    def _disconnect(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None

    def run_forever(self, stop_event: Optional[threading.Event] = None) -> None:
        stop = stop_event or threading.Event()
        self.queue_worker.acquire()
        heartbeat_stop = threading.Event()
        heartbeat_errors: list[Exception] = []
        heartbeat_interval = max(0.05, min(1.0, self.poll_interval * 2))

        def maintain_heartbeat() -> None:
            while not heartbeat_stop.wait(heartbeat_interval):
                try:
                    self.queue_worker.heartbeat()
                except Exception as exc:
                    heartbeat_errors.append(exc)
                    stop.set()
                    return

        heartbeat_thread = threading.Thread(
            target=maintain_heartbeat,
            name=f"csc-{self.agent}-heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()
        reconnect_delay = self.poll_interval
        try:
            while not stop.is_set():
                if heartbeat_errors:
                    raise heartbeat_errors[0]
                if self._socket is None:
                    try:
                        self._connect()
                        reconnect_delay = self.poll_interval
                    except (OSError, ValueError, ConnectionError):
                        stop.wait(reconnect_delay)
                        reconnect_delay = min(2.0, reconnect_delay * 2)
                        continue

                self.queue_worker.process_available(limit=20)
                if heartbeat_errors:
                    raise heartbeat_errors[0]
                try:
                    chunk = self._socket.recv(65536) if self._socket is not None else b""
                    if not chunk:
                        self._disconnect()
                except socket.timeout:
                    pass
                except OSError:
                    self._disconnect()
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2.0)
            self._disconnect()
            self.queue_worker.release()


def _load_broker_endpoint(project_root: Path) -> tuple[str, int]:
    meta_path = project_root / ".agent-swarm" / "broker.json"
    with meta_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    return str(metadata.get("host", "127.0.0.1")), int(metadata.get("port", 8765))


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent CSC CLI adapter")
    parser.add_argument("--agent", required=True, choices=sorted(SUPPORTED_AGENTS))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    host, port = _load_broker_endpoint(root)
    executor = BoundedCliExecutor(args.agent, root, timeout=args.timeout)
    runtime = RegisteredQueueWorker(
        args.agent, root, executor=executor, host=host, port=port,
        poll_interval=args.poll_interval,
    )
    try:
        runtime.run_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
