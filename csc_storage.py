#!/usr/bin/env python
"""
Codex Swarm Command (CSC) - Local SSOT Storage Layer
Implements at-least-once delivery with message_id idempotency.
NOTE: This layer guarantees at-least-once delivery + message_id idempotency;
it does NOT claim or guarantee exactly-once delivery.

Uses standard library only.
"""

import os
import sys
import json
import time
import uuid
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from csc_auth import AuthenticationError, sign_envelope

# In-process lock to prevent thread contention thrashing within the same process
_PROCESS_LOCK = threading.RLock()

DEFAULT_LOCK_TIMEOUT = 5.0
DEFAULT_STALE_LOCK_TTL = 10.0
DECISION_MESSAGE_TYPES = frozenset({"TASK", "RESULT", "BLOCKED", "PROPOSAL", "RISK", "ACK"})


def get_utc_iso() -> str:
    """Returns current UTC ISO-8601 formatted timestamp string."""
    return datetime.now(timezone.utc).isoformat()


def canonicalize_envelope(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Converts a message dictionary into the canonical envelope schema.

    Canonical Schema:
        message_id: str (required)
        timestamp: str (ISO-8601 UTC)
        sender: str
        recipient: str
        type: str
        in_reply_to: str
        body: str

    Wire format field conversions:
        'id' -> 'message_id'
        'from' -> 'sender'
        'to' -> 'recipient'
    """
    if not isinstance(msg, dict):
        raise TypeError(f"Message must be a dict, got {type(msg).__name__}")

    # message_id resolution (required)
    msg_id = msg.get("message_id") or msg.get("id")
    if not msg_id or not str(msg_id).strip():
        raise ValueError("message_id is required for canonical envelope")
    msg_id = str(msg_id).strip()

    sender = str(msg.get("sender") or msg.get("from") or "unknown").strip()
    recipient = str(msg.get("recipient") or msg.get("to") or "all").strip()
    msg_type = str(msg.get("type") or "UNKNOWN").strip()
    timestamp = str(msg.get("timestamp") or get_utc_iso()).strip()
    in_reply_to = str(msg.get("in_reply_to") or "none").strip()

    raw_body = msg.get("body")
    if raw_body is None:
        raw_body = msg.get("description", "")
    if isinstance(raw_body, str):
        body = raw_body
    else:
        body = json.dumps(raw_body, ensure_ascii=False)

    canonical: Dict[str, Any] = {
        "message_id": msg_id,
        "timestamp": timestamp,
        "sender": sender,
        "recipient": recipient,
        "type": msg_type,
        "in_reply_to": in_reply_to,
        "body": body,
    }

    # Preserve any caller-supplied auxiliary keys without losing payload details,
    # while omitting wire alias keys.
    for k, v in msg.items():
        if k not in (
            "id", "from", "to",
            "message_id", "timestamp", "sender", "recipient", "type", "in_reply_to", "body"
        ):
            canonical[k] = v

    return canonical


def prepare_envelope(
    envelope: Dict[str, Any],
    *,
    signing_key: Optional[bytes] = None,
    auth_epoch: Optional[str] = None,
    require_authenticated: bool = False,
) -> Dict[str, Any]:
    """Canonicalize and optionally sign a message before persistence.

    Authenticated mode is opt-in until runtime key/ACL activation. Decision
    messages fail closed if the mode is requested without signing material.
    """
    canonical = canonicalize_envelope(envelope)
    needs_auth = canonical["type"].upper() in DECISION_MESSAGE_TYPES
    if signing_key is not None:
        if not isinstance(auth_epoch, str) or not auth_epoch.strip():
            raise AuthenticationError("auth_epoch is required when signing")
        return sign_envelope(canonical, signing_key, auth_epoch)
    if require_authenticated and needs_auth:
        raise AuthenticationError("authenticated decision message requires a signing key")
    return canonical


def acquire_file_lock(lock_path: str, timeout: float = DEFAULT_LOCK_TIMEOUT, stale_timeout: float = DEFAULT_STALE_LOCK_TTL) -> int:
    """Acquires an atomic file-based lock using O_CREAT | O_EXCL.

    Implements bounded retry and stale lock recovery.
    Returns the open file descriptor on success.
    """
    start_time = time.time()
    retry_delay = 0.02
    lock_dir = os.path.dirname(lock_path)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)

    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR

    while True:
        try:
            fd = os.open(lock_path, flags)
            try:
                meta = f"{os.getpid()}:{time.time()}\n".encode("utf-8")
                os.write(fd, meta)
            except Exception:
                pass
            return fd
        except (FileExistsError, OSError):
            now = time.time()
            try:
                if os.path.exists(lock_path):
                    mtime = os.path.getmtime(lock_path)
                    if now - mtime > stale_timeout:
                        try:
                            os.remove(lock_path)
                        except OSError:
                            pass
            except OSError:
                pass

            if (time.time() - start_time) >= timeout:
                raise TimeoutError(f"Timed out after {timeout:.2f}s waiting for lock: {lock_path}")

            time.sleep(retry_delay)


def release_file_lock(fd: int, lock_path: str):
    """Releases file lock by closing file descriptor and removing lock file."""
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except OSError:
        pass


@contextmanager
def file_lock(lock_path: str, timeout: float = DEFAULT_LOCK_TIMEOUT, stale_timeout: float = DEFAULT_STALE_LOCK_TTL):
    """Context manager for acquiring and releasing atomic file lock."""
    with _PROCESS_LOCK:
        fd = acquire_file_lock(lock_path, timeout=timeout, stale_timeout=stale_timeout)
        try:
            yield
        finally:
            release_file_lock(fd, lock_path)


def append_once(
    file_path: str,
    envelope: Dict[str, Any],
    timeout: float = DEFAULT_LOCK_TIMEOUT,
    stale_timeout: float = DEFAULT_STALE_LOCK_TTL
) -> bool:
    """Appends canonical envelope to target JSONL file if message_id is not already present.

    - Protects the file with an atomic .lock file.
    - Inspects existing JSONL message_ids; preserves and skips malformed lines.
    - If message_id is already present, skips writing and returns False (idempotent deduplication).
    - If message_id is not present, writes JSON line, flushes, and calls os.fsync. Returns True.
    """
    canonical = canonicalize_envelope(envelope)
    target_id = canonical["message_id"]

    abs_path = os.path.abspath(file_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    lock_path = abs_path + ".lock"

    with file_lock(lock_path, timeout=timeout, stale_timeout=stale_timeout):
        # 1. Check existing lines for duplicate message_id
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                        if isinstance(record, dict):
                            existing_id = record.get("message_id") or record.get("id")
                            if existing_id and str(existing_id) == target_id:
                                return False
                    except Exception:
                        # Malformed existing JSON line: preserve and skip
                        continue

        # 2. Append new record
        needs_leading_newline = False
        if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
            try:
                with open(abs_path, "rb") as f:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        needs_leading_newline = True
            except OSError:
                pass

        payload_line = json.dumps(canonical, ensure_ascii=False) + "\n"
        with open(abs_path, "a", encoding="utf-8") as f:
            if needs_leading_newline:
                f.write("\n")
            f.write(payload_line)
            f.flush()
            os.fsync(f.fileno())

        return True


def resolve_messages_dir(base_dir: Optional[str] = None) -> str:
    """Resolves directory path containing message queues and inboxes."""
    if base_dir:
        base_path = os.path.abspath(base_dir)
        if os.path.basename(base_path) == "messages":
            return base_path
        if os.path.basename(base_path) == ".agent-swarm":
            return os.path.join(base_path, "messages")
        if os.path.isdir(os.path.join(base_path, ".agent-swarm")):
            return os.path.join(base_path, ".agent-swarm", "messages")
        return os.path.join(base_path, "messages")

    env_root = os.environ.get("CSC_PROJECT_ROOT")
    if env_root:
        return os.path.join(os.path.abspath(env_root), ".agent-swarm", "messages")
    return os.path.abspath(os.path.join(".agent-swarm", "messages"))


def persist_message(
    envelope: Dict[str, Any],
    base_dir: Optional[str] = None,
    *,
    signing_key: Optional[bytes] = None,
    auth_epoch: Optional[str] = None,
    require_authenticated: bool = False,
) -> Dict[str, Any]:
    """Persists a message to queue.jsonl and the appropriate inbox.

    Guarantees at-least-once delivery + message_id idempotency.
    - Always appends to queue.jsonl (idempotent).
    - If recipient == 'all', appends to all_inbox.jsonl only.
    - Otherwise appends to <recipient>_inbox.jsonl.
    """
    canonical = prepare_envelope(
        envelope,
        signing_key=signing_key,
        auth_epoch=auth_epoch,
        require_authenticated=require_authenticated,
    )
    messages_dir = resolve_messages_dir(base_dir)

    queue_file = os.path.join(messages_dir, "queue.jsonl")

    recipient_norm = canonical["recipient"].strip().lower()
    if recipient_norm == "all":
        inbox_file = os.path.join(messages_dir, "all_inbox.jsonl")
    else:
        safe_name = "".join(c for c in canonical["recipient"].strip() if c.isalnum() or c in ("-", "_")).lower()
        if not safe_name:
            safe_name = "unknown"
        inbox_file = os.path.join(messages_dir, f"{safe_name}_inbox.jsonl")

    queue_appended = append_once(queue_file, canonical)
    inbox_appended = append_once(inbox_file, canonical)

    is_deduplicated = (not queue_appended) and (not inbox_appended)

    return {
        "status": "ok",
        "persisted": True,
        "deduplicated": is_deduplicated,
        "message_id": canonical["message_id"],
        "envelope": canonical,
    }


def append_audit(event: Dict[str, Any], base_dir: Optional[str] = None) -> bool:
    """Appends connection / system audit event to messages/audit.jsonl.

    Does NOT write to the business message queue.
    """
    if not isinstance(event, dict):
        raise TypeError(f"Audit event must be a dict, got {type(event).__name__}")

    audit_entry = dict(event)
    if "timestamp" not in audit_entry:
        audit_entry["timestamp"] = get_utc_iso()

    messages_dir = resolve_messages_dir(base_dir)
    audit_file = os.path.join(messages_dir, "audit.jsonl")
    abs_path = os.path.abspath(audit_file)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    lock_path = abs_path + ".lock"

    with file_lock(lock_path):
        needs_leading_newline = False
        if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
            try:
                with open(abs_path, "rb") as f:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        needs_leading_newline = True
            except OSError:
                pass

        payload_line = json.dumps(audit_entry, ensure_ascii=False) + "\n"
        with open(abs_path, "a", encoding="utf-8") as f:
            if needs_leading_newline:
                f.write("\n")
            f.write(payload_line)
            f.flush()
            os.fsync(f.fileno())

    return True
