#!/usr/bin/env python
"""Durable single-queue worker core for Codex Swarm Command.

This S1 implementation deliberately uses an injected executor.  It never starts
Claude Code, Antigravity, or any other external CLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from csc_auth import AuthenticationError, ReplayWindow, verify_envelope
from csc_process import probe_pid
from csc_storage import append_audit, append_once, file_lock, persist_message


class WorkerAlreadyRunning(RuntimeError):
    """Raised when a live worker already owns an agent slot."""


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, value: Dict[str, Any], max_attempts: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(max_attempts):
            try:
                os.replace(temporary, path)
                return
            except (PermissionError, OSError) as exc:
                winerror = getattr(exc, "winerror", None)
                # Windows WinError 5 (Access Denied) 및 WinError 32 (Sharing Violation) 대응
                if isinstance(exc, PermissionError) or winerror in (5, 32):
                    if attempt == max_attempts - 1:
                        raise
                    # 지수 백오프: 점진적 대기 시간 증가 (0.015s ~ 최대 0.25s)
                    time.sleep(min(0.25, 0.015 * (1.5 ** attempt)))
                else:
                    raise
    finally:
        for _ in range(3):
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
                break
            except OSError:
                time.sleep(0.01)


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else dict(default)
    except (OSError, ValueError, TypeError):
        return dict(default)


def pid_is_alive(pid: int) -> bool:
    # Preserve ownership on denied observation; unknown must never reclaim a slot.
    return probe_pid(pid) != "gone"


def metadata_is_stale(metadata: Dict[str, Any], stale_after: float, now: Optional[float] = None) -> bool:
    if metadata.get("status") not in {"starting", "ready"}:
        return True
    pid = metadata.get("pid")
    if not pid_is_alive(pid):
        return True
    heartbeat = metadata.get("heartbeat_epoch")
    if not isinstance(heartbeat, (int, float)):
        return True
    return (time.time() if now is None else now) - float(heartbeat) > stale_after

def initialize_cursor_at_queue_end(agent: str, project_root: os.PathLike[str] | str) -> bool:
    """Create a first-run cursor at EOF so stale historical TASKs are not replayed."""
    root = Path(project_root).resolve()
    state_path = root / ".agent-swarm" / "workers" / f"{agent.strip().lower()}.cursor.json"
    if state_path.exists():
        return False
    queue_path = root / ".agent-swarm" / "messages" / "queue.jsonl"
    offset = queue_path.stat().st_size if queue_path.exists() else 0
    _atomic_write_json(state_path, {
        "offset": offset,
        "processed_ids": [],
        "attempts": {},
    })
    return True



class StubExecutor:
    """Deterministic executor used until a separately approved live adapter exists."""

    def __call__(self, message: Dict[str, Any]) -> str:
        return f"STUB_OK:{message['message_id']}"


class QueueWorker:
    """Consumes one canonical JSONL queue with a durable per-agent cursor."""

    def __init__(
        self,
        agent: str,
        project_root: os.PathLike[str] | str,
        executor: Optional[Callable[[Dict[str, Any]], Any]] = None,
        max_attempts: int = 3,
        stale_after: float = 30.0,
        auth_key: Optional[bytes] = None,
        auth_epoch: Optional[str] = None,
        require_authenticated: bool = False,
        replay_window: Optional[ReplayWindow] = None,
    ) -> None:
        if not agent or not agent.strip():
            raise ValueError("agent is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if require_authenticated and (auth_key is None or not auth_epoch):
            raise ValueError("authenticated worker requires auth_key and auth_epoch")
        self.agent = agent.strip().lower()
        self.project_root = Path(project_root).resolve()
        self.swarm_dir = self.project_root / ".agent-swarm"
        self.queue_path = self.swarm_dir / "messages" / "queue.jsonl"
        self.state_path = self.swarm_dir / "workers" / f"{self.agent}.cursor.json"
        self.metadata_path = self.swarm_dir / "workers" / f"{self.agent}.json"
        self.dlq_path = self.swarm_dir / "dead-letter" / f"{self.agent}.jsonl"
        self.executor = executor or StubExecutor()
        self.max_attempts = max_attempts
        self.stale_after = stale_after
        self.auth_key = auth_key
        self.auth_epoch = auth_epoch
        self.require_authenticated = require_authenticated
        self.replay_window = replay_window or ReplayWindow()
        self._owns_slot = False

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {"offset": 0, "processed_ids": [], "attempts": {}}

    def _load_state(self) -> Dict[str, Any]:
        state = _read_json(self.state_path, self._empty_state())
        if not isinstance(state.get("offset"), int) or state["offset"] < 0:
            state["offset"] = 0
        if not isinstance(state.get("processed_ids"), list):
            state["processed_ids"] = []
        if not isinstance(state.get("attempts"), dict):
            state["attempts"] = {}
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        _atomic_write_json(self.state_path, state)

    def acquire(self) -> None:
        lock_path = str(self.metadata_path) + ".lock"
        with file_lock(lock_path):
            existing = _read_json(self.metadata_path, {})
            if existing and not metadata_is_stale(existing, self.stale_after):
                raise WorkerAlreadyRunning(f"live worker already registered for {self.agent}")
            now = time.time()
            _atomic_write_json(self.metadata_path, {
                "agent": self.agent,
                "pid": os.getpid(),
                "status": "ready",
                "project_root": str(self.project_root),
                "started_at": utc_iso(),
                "heartbeat_at": utc_iso(),
                "heartbeat_epoch": now,
            })
            self._owns_slot = True

    def heartbeat(self) -> None:
        if not self._owns_slot:
            raise RuntimeError("worker slot is not owned")
        metadata = _read_json(self.metadata_path, {})
        if metadata.get("pid") != os.getpid():
            raise WorkerAlreadyRunning(f"worker slot ownership changed for {self.agent}")
        metadata.update({"status": "ready", "heartbeat_at": utc_iso(), "heartbeat_epoch": time.time()})
        _atomic_write_json(self.metadata_path, metadata)

    def release(self) -> None:
        if not self._owns_slot:
            return
        metadata = _read_json(self.metadata_path, {})
        if metadata.get("pid") == os.getpid():
            metadata.update({"status": "stopped", "heartbeat_at": utc_iso(), "heartbeat_epoch": time.time()})
            _atomic_write_json(self.metadata_path, metadata)
        self._owns_slot = False

    def _result_id(self, message: Dict[str, Any]) -> str:
        correlation = str(message.get("correlation_id") or message["message_id"])
        digest = hashlib.sha256(f"{self.agent}|{message['message_id']}|{correlation}".encode()).hexdigest()[:24]
        return f"RESULT-{digest}"

    def _persist_result(self, message: Dict[str, Any], result: Any) -> None:
        correlation = str(message.get("correlation_id") or message["message_id"])
        # 증거 게이트: RESULT 본문의 성공 주장을 코드가 직접 실행해 검증한다.
        # 근거 — 스키마는 형식만 막고 "테스트 통과했습니다" 같은 거짓말은 통과시킨다
        # (csc_slice.py 의 liar 케이스로 실증). 검증 실패가 워커를 죽이지는 않는다.
        body = str(result)
        evidence: Dict[str, Any] = {"status": "UNVERIFIED", "note": "gate not run"}
        try:
            import csc_evidence
            # 메시지는 검증 '이름'만 고를 수 있다. 명령은 운영자 소유 정책 파일에서만 온다.
            # REDTEAM 실증: 메시지가 명령을 직접 지정할 수 있으면 exit 0 한 줄로
            # 자기인증이 뚫리고, 메시지 내용이 셸에서 그대로 실행된다(RCE).
            body, evidence = csc_evidence.gate(
                body,
                evidence_check=message.get("evidence_check"),
                cwd=str(self.project_root) if hasattr(self, "project_root") else None,
            )
        except Exception as exc:                 # 게이트 자체 오류는 기록만 하고 통과시킨다
            evidence = {"status": "UNVERIFIED",
                        "error": f"{type(exc).__name__}: {exc}"}
        persist_message({
            "message_id": self._result_id(message),
            "sender": self.agent,
            "recipient": message.get("sender", "codex"),
            "type": "RESULT",
            "in_reply_to": message["message_id"],
            "correlation_id": correlation,
            "body": body,
            "evidence": evidence,
        }, base_dir=str(self.swarm_dir),
            signing_key=self.auth_key,
            auth_epoch=self.auth_epoch,
            require_authenticated=self.require_authenticated,
        )

    def _dead_letter(self, message: Dict[str, Any], error: Exception, attempts: int, blocked_id: Optional[str] = None) -> None:
        source_id = str(message.get("message_id") or "unknown")
        digest = hashlib.sha256(f"{self.agent}|{source_id}".encode()).hexdigest()[:24]
        record: Dict[str, Any] = {
            "message_id": f"DLQ-{digest}",
            "sender": self.agent,
            "recipient": "codex",
            "type": "DEAD_LETTER",
            "in_reply_to": source_id,
            "correlation_id": message.get("correlation_id", source_id),
            "body": f"failed after {attempts} attempts: {type(error).__name__}: {error}",
            "original_message": message,
        }
        if blocked_id:
            record["blocked_id"] = blocked_id
        append_once(str(self.dlq_path), record)

    def _persist_blocked(
        self,
        message: Dict[str, Any],
        error: Exception,
        code: Optional[str] = None,
        failure_code: Optional[str] = None,
    ) -> str:
        source_id = str(message.get("message_id") or "unknown")
        discriminator = str(code or failure_code or "blocked")
        digest = hashlib.sha256(f"{self.agent}|{source_id}|{discriminator}".encode()).hexdigest()[:24]
        blocked_id = f"BLOCKED-{digest}"
        payload: Dict[str, Any] = {
            "message_id": blocked_id,
            "sender": self.agent,
            "recipient": message.get("sender", "codex"),
            "type": "BLOCKED",
            "in_reply_to": source_id,
            "correlation_id": message.get("correlation_id", source_id),
            "body": str(error)[:500],
        }
        if code:
            payload["availability_code"] = code
        if failure_code:
            payload["failure_code"] = failure_code
        persist_message(
            payload,
            base_dir=str(self.swarm_dir),
            signing_key=self.auth_key,
            auth_epoch=self.auth_epoch,
            require_authenticated=self.require_authenticated,
        )
        return blocked_id

    def _audit_auth_rejection(self, message: Dict[str, Any], error: Exception) -> None:
        """Record metadata only; never preserve attacker-controlled body/auth data."""
        classification = (
            "legacy_untrusted"
            if "missing authentication metadata" in str(error)
            else "invalid_auth"
        )
        append_audit({
            "event": "AUTH_REJECTED",
            "classification": classification,
            "agent": self.agent,
            "message_id": str(message.get("message_id", "unknown")),
            "claimed_sender": str(message.get("sender", "unknown")),
            "claimed_type": str(message.get("type", "unknown")),
            "error_type": type(error).__name__,
            "reason": str(error)[:160],
        }, base_dir=str(self.swarm_dir))


    def process_available(self, limit: Optional[int] = None) -> int:
        """Process eligible messages; return the number completed or dead-lettered.

        A failure before ``max_attempts`` leaves the cursor on the failed record,
        providing at-least-once retry on the next call.
        """
        state = self._load_state()
        processed = set(str(item) for item in state["processed_ids"])
        completed = 0
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.queue_path.exists():
            return 0
        queue_size = self.queue_path.stat().st_size
        if state["offset"] > queue_size:
            state["offset"] = 0

        with self.queue_path.open("rb") as handle:
            handle.seek(state["offset"])
            while limit is None or completed < limit:
                record_start = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                next_offset = handle.tell()
                try:
                    message = json.loads(raw.decode("utf-8"))
                    if not isinstance(message, dict):
                        raise ValueError("queue record is not an object")
                    message_id = str(message["message_id"])
                except Exception as exc:
                    message = {"message_id": f"MALFORMED-{record_start}", "raw": raw.decode("utf-8", errors="replace")}
                    message_id = message["message_id"]
                    if not self._handle_failure(state, message, exc, next_offset):
                        break
                    completed += 1
                    continue

                eligible = (
                    str(message.get("type", "")).upper() == "TASK"
                    and str(message.get("recipient", "")).lower() in {self.agent, "all"}
                )
                if not eligible or message_id in processed:
                    state["offset"] = next_offset
                    self._save_state(state)
                    continue

                if self.require_authenticated:
                    try:
                        message = verify_envelope(
                            message,
                            self.auth_key,
                            self.auth_epoch,
                            replay_window=self.replay_window,
                        )
                    except AuthenticationError as exc:
                        self._audit_auth_rejection(message, exc)
                        processed.add(message_id)
                        state["processed_ids"] = list(processed)
                        state["attempts"].pop(message_id, None)
                        state["offset"] = next_offset
                        self._save_state(state)
                        completed += 1
                        continue

                try:
                    result = self.executor(message)
                    self._persist_result(message, result)
                except Exception as exc:
                    if not self._handle_failure(state, message, exc, next_offset):
                        break
                    processed.add(message_id)
                    completed += 1
                    continue

                processed.add(message_id)
                state["processed_ids"] = list(processed)
                state["attempts"].pop(message_id, None)
                state["offset"] = next_offset
                self._save_state(state)
                completed += 1
        return completed

    def _handle_failure(self, state: Dict[str, Any], message: Dict[str, Any], error: Exception, next_offset: int) -> bool:
        message_id = str(message["message_id"])
        availability_code = str(getattr(error, "availability_code", "")).strip().lower()
        if availability_code:
            self._persist_blocked(message, error, code=availability_code)
            state["attempts"].pop(message_id, None)
            state["processed_ids"].append(message_id)
            state["offset"] = next_offset
            self._save_state(state)
            return True

        attempts = int(state["attempts"].get(message_id, 0)) + 1
        state["attempts"][message_id] = attempts
        if attempts < self.max_attempts:
            self._save_state(state)
            return False
        blocked_id = self._persist_blocked(message, error, failure_code="retry_exhausted")
        self._dead_letter(message, error, attempts, blocked_id=blocked_id)
        state["attempts"].pop(message_id, None)
        state["processed_ids"].append(message_id)
        state["offset"] = next_offset
        self._save_state(state)
        return True
