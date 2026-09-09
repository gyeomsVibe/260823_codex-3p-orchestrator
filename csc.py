#!/usr/bin/env python
"""
Codex Swarm Command (CSC) v2.0 - Cross-Platform Swarm CLI & Real-time Protocol Runtime
Built under the 3-way unanimous consensus of Codex, Claude Code, and Antigravity.
Integrates file-based fallback and high-speed port-based socket event broker.

Guarantee Contract:
  - At-least-once delivery with message_id idempotency.
  - Does NOT claim or guarantee exactly-once execution.
"""

import os
import sys
import json
import time
import uuid
import hashlib
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from csc_auth import AuthenticationError, ReplayWindow, verify_envelope
import csc_storage
import csc_runtime
from c3p_trigger import (
    is_budget_saving_trigger,
    is_runtime_activation_trigger,
    is_user_absence_trigger,
)
from c3p_absence_state_store import arm_user_absence_mode
from csc_worker import pid_is_alive

SWARM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agent-swarm")

# Import broker client helper
try:
    from csc_broker import SwarmClientSync, BROKER_META_FILE, DEFAULT_PORT
except ImportError:
    SwarmClientSync = None
    BROKER_META_FILE = os.path.join(SWARM_DIR, "broker.json")
    DEFAULT_PORT = 8765

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

LOCK_TTL_SECONDS = 300  # 5 minutes Step-Touch TTL

# 하트비트가 이보다 오래되면 프로세스가 살아 있어도 '멈춘 것'으로 본다.
WORKER_HEARTBEAT_STALE_SECONDS = 120

# 고아 락(meta 없는 lock 디렉터리) 회수 전 유예.
# acquire 가 mkdir 과 meta 쓰기 사이에 있는 정상 상태를 고아로 오인하지 않기 위함.
ORPHAN_GRACE_SECONDS = 30


def _emit_lock_event(action: str, resource_path: str, owner, idle_s=None) -> None:
    """락 관련 사건을 브로커에 알린다. 실패해도 락 로직을 막지 않는다.

    STALE 을 자동 회수하지 않기로 했으므로(조용한 동시 쓰기 방지),
    대신 '시끄럽게' 알리는 경로가 반드시 있어야 한다.
    """
    if not SwarmClientSync:
        return
    try:
        client = SwarmClientSync()
        if not client.is_running():
            return
        payload = {"action": action, "resource": resource_path, "owner": owner}
        if idle_s is not None:
            payload["idle_s"] = idle_s
        evt_id = f"EVT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        client.send_message({
            "type": "EVENT", "message_id": evt_id,
            "sender": str(owner or "unknown"), "recipient": "all",
            "body": json.dumps(payload, ensure_ascii=False),
            **payload,
        }, agent_name=str(owner or "unknown"))
    except Exception:
        pass

def get_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def hash_resource(resource_path: str) -> str:
    norm_path = os.path.normpath(resource_path).replace("\\", "/")
    return hashlib.sha256(norm_path.encode("utf-8")).hexdigest()[:16]

def init_swarm(force: bool = False):
    """Initializes .agent-swarm directory structure idempotently."""
    base_dir = SWARM_DIR
    sub_dirs = ["tasks", "locks", "messages", "chat", "chat/sessions", "results"]

    print(f"🚀 [CSC] Initializing Swarm Infrastructure (Base: {base_dir})...")
    for sub in sub_dirs:
        path = os.path.join(base_dir, sub)
        os.makedirs(path, exist_ok=True)
        print(f"  └─ Directory verified: {path}")

    # Initialize Task Boards (JSONL) if not exist
    for board in ["backlog.jsonl", "in_progress.jsonl", "completed.jsonl"]:
        board_path = os.path.join(base_dir, "tasks", board)
        if not os.path.exists(board_path):
            with open(board_path, "w", encoding="utf-8") as f:
                pass
            print(f"  └─ Created empty board: {board_path}")
        else:
            print(f"  └─ Preserved existing board: {board_path}")

    # Initialize Message Queue if not exist
    queue_path = os.path.join(base_dir, "messages", "queue.jsonl")
    if not os.path.exists(queue_path):
        with open(queue_path, "w", encoding="utf-8") as f:
            pass
        print(f"  └─ Created message queue: {queue_path}")

    print("✨ [CSC] Swarm infrastructure ready. No existing data was overwritten.")

def acquire_lock(resource_path: str, owner: str) -> bool:
    """Acquires an atomic directory-based lock with 5-minute Step-Touch TTL."""
    lock_hash = hash_resource(resource_path)
    lock_dir = os.path.join(SWARM_DIR, "locks", f"{lock_hash}.lock")
    meta_file = os.path.join(lock_dir, "meta.json")
    now_ts = time.time()

    # Check if lock directory exists
    if os.path.exists(lock_dir):
        if not os.path.exists(meta_file):
            # 고아 락(orphaned lock): 디렉터리는 있는데 meta 가 없다.
            # 원인 (a) release 중 rmdir 실패, (b) acquire 가 mkdir 과 meta 쓰기 사이에서 죽음.
            # 이전 코드는 이 분기를 그냥 통과시켜 makedirs 가 FileExistsError 를 냈고,
            # "Contention race" 라는 잘못된 진단과 함께 아무도 획득할 수 없는 교착이 됐다.
            # (실증: 원소유자조차 재획득 실패, status 는 "Active Locks (0)" 으로 은폐)
            age = now_ts - os.path.getmtime(lock_dir)
            if age < ORPHAN_GRACE_SECONDS:
                print(f"❌ [CSC Lock] '{resource_path}' 획득이 진행 중일 수 있다 "
                      f"(meta 없음, {int(age)}s 경과 < 유예 {ORPHAN_GRACE_SECONDS}s). 잠시 후 재시도하라.")
                return False
            print(f"🧹 [CSC Lock] Orphaned lock detected on '{resource_path}' "
                  f"(meta 없음, {int(age)}s 경과). 소유자가 없으므로 회수한다.")
            try:
                os.rmdir(lock_dir)
            except OSError as e:
                print(f"❌ [CSC Lock] 고아 락 회수 실패: {e}. "
                      f"수동 복구: csc.py lock release {resource_path} --owner <you> --force")
                return False
        else:
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                last_touched = meta.get("last_touched_at_ts", 0)
                idle = int(now_ts - last_touched)
                if idle > LOCK_TTL_SECONDS:
                    # 자동 회수하지 않는다. 살아 있는 소유자의 락을 뺏으면
                    # 조용한 동시 쓰기가 발생한다(재현 확인됨). 막히는 실패가 뚫리는 실패보다 안전하다.
                    print(f"🚨 [CSC Lock] STALE LOCK — 자동 회수하지 않는다. "
                          f"resource='{resource_path}' owner='{meta.get('owner')}' idle={idle}s")
                    print(f"   소유자가 긴 단일 작업 중일 수 있다. 사람 또는 Codex 의 명시적 판정으로만 해제하라.")
                    print(f"   해제: csc.py lock release {resource_path} --owner {meta.get('owner')} --force")
                    _emit_lock_event("LOCK_STALE_REPORTED", resource_path, meta.get("owner"), idle)
                    return False
                print(f"❌ [CSC Lock] Resource '{resource_path}' is currently locked by '{meta.get('owner')}'.")
                return False
            except (json.JSONDecodeError, OSError) as e:
                print(f"❌ [CSC Lock] 손상된 lock meta ({e}). 자동 삭제하지 않는다. "
                      f"수동 복구: csc.py lock release {resource_path} --owner <you> --force")
                return False

    # Atomic directory creation
    try:
        os.makedirs(lock_dir, exist_ok=False)
    except FileExistsError:
        print(f"❌ [CSC Lock] Contention race detected on '{resource_path}' "
              f"(다른 주체가 방금 획득했다). Lock acquisition failed.")
        return False
    except Exception as e:
        print(f"❌ [CSC Lock] Failed to create lock dir: {e}")
        return False

    # Write metadata inside lock directory
    meta_data = {
        "resource": resource_path,
        "resource_hash": lock_hash,
        "owner": owner,
        "created_at": get_utc_iso(),
        "last_touched_at": get_utc_iso(),
        "last_touched_at_ts": now_ts,
        "step_count": 0
    }
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2)

    # Notify real-time broker if active
    if SwarmClientSync:
        client = SwarmClientSync()
        if client.is_running():
            evt_id = f"EVT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
            client.send_message({
                "type": "EVENT",
                "message_id": evt_id,
                "sender": owner,
                "recipient": "all",
                "body": json.dumps({"action": "LOCK_ACQUIRED", "resource": resource_path, "owner": owner}, ensure_ascii=False),
                "action": "LOCK_ACQUIRED",
                "resource": resource_path,
                "owner": owner
            }, agent_name=owner)

    print(f"🔒 [CSC Lock] Successfully acquired lock on '{resource_path}' for '{owner}'.")
    return True

def touch_lock(resource_path: str, owner: str) -> bool:
    """Updates last_touched timestamp to maintain active lock."""
    lock_hash = hash_resource(resource_path)
    meta_file = os.path.join(SWARM_DIR, "locks", f"{lock_hash}.lock", "meta.json")
    if not os.path.exists(meta_file):
        print(f"❌ [CSC Lock] Cannot touch. No active lock for '{resource_path}'.")
        return False

    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("owner") != owner:
            print(f"❌ [CSC Lock] Ownership mismatch. Cannot touch lock held by '{meta.get('owner')}'.")
            return False

        meta["last_touched_at"] = get_utc_iso()
        meta["last_touched_at_ts"] = time.time()
        meta["step_count"] = meta.get("step_count", 0) + 1
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        print(f"⏱️ [CSC Lock] Lock touched for '{resource_path}' (Step: {meta['step_count']}).")
        return True
    except Exception as e:
        print(f"❌ [CSC Lock] Touch failed: {e}")
        return False

def release_lock(resource_path: str, owner: str, force: bool = False) -> bool:
    """Releases atomic directory lock with Windows Exponential Backoff retry."""
    lock_hash = hash_resource(resource_path)
    lock_dir = os.path.join(SWARM_DIR, "locks", f"{lock_hash}.lock")
    meta_file = os.path.join(lock_dir, "meta.json")

    if not os.path.exists(lock_dir):
        print(f"ℹ️ [CSC Lock] No lock exists for '{resource_path}'.")
        return True

    if not force and os.path.exists(meta_file):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("owner") != owner:
                print(f"❌ [CSC Lock] Cannot release lock owned by '{meta.get('owner')}'.")
                return False
        except Exception:
            pass

    # Windows safe removal with backoff
    for attempt in range(5):
        try:
            if os.path.exists(meta_file):
                os.remove(meta_file)
            if os.path.exists(lock_dir):
                os.rmdir(lock_dir)

            if SwarmClientSync:
                client = SwarmClientSync()
                if client.is_running():
                    evt_id = f"EVT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
                    client.send_message({
                        "type": "EVENT",
                        "message_id": evt_id,
                        "sender": owner,
                        "recipient": "all",
                        "body": json.dumps({"action": "LOCK_RELEASED", "resource": resource_path, "owner": owner}, ensure_ascii=False),
                        "action": "LOCK_RELEASED",
                        "resource": resource_path,
                        "owner": owner
                    }, agent_name=owner)

            print(f"🔓 [CSC Lock] Released lock on '{resource_path}'.")
            return True
        except PermissionError:
            time.sleep(0.05 * (2 ** attempt))
        except Exception as e:
            print(f"❌ [CSC Lock] Release error on attempt {attempt+1}: {e}")
            time.sleep(0.05)

    print(f"❌ [CSC Lock] Failed to fully remove lock directory '{lock_dir}' after retries.")
    return False

def send_message(
    sender: str,
    recipient: str,
    msg_type: str,
    body: str,
    in_reply_to: str = "none",
    correlation_id: str = "",
) -> str:
    """Sends a message under the at-least-once delivery + message_id idempotency contract.

    Guarantees:
      - At-least-once delivery with message_id idempotency.
      - High-resolution timestamp (microseconds) + short UUID to avoid ID collisions.
      - Transmits canonical envelope directly to SwarmClientSync.
      - If broker ACK returns status ok and persisted True, local duplicate append is omitted.
      - If broker fails or times out, safely falls back to csc_storage.persist_message.
      - Honestly outputs delivery mode as 'realtime' or 'fallback'.
      - Preserves existing CLI calling conventions.
      - Audits falsifiable claims in the body BEFORE anyone receives them.
    """
    # 발신 전 주장 감사 (2026-09-06 사용자 지시).
    #
    # 오늘 잡힌 허위 주장 11건은 전부 사후에, 그것도 운 좋게 잡혔다.
    # 동료가 우연히 재현해 봤거나 내가 다른 작업 중 마주쳤거나.
    # 적발이 우연에 의존하면 그건 감사 체계가 아니다.
    #
    # 여기서 막지 못하면 거짓은 이미 상대의 판단 근거가 된 뒤다.
    # 감사기는 모델을 부르지 않는다. 전부 결정론적 재측정이다 —
    # AI 가 AI 를 판단하면 같은 환각을 공유할 수 있기 때문이다.
    try:
        import csc_audit
        _verdict = csc_audit.audit(body, msg_type, sender)
        csc_audit.record(_verdict)
        if _verdict["findings"]:
            print(csc_audit.report(_verdict), file=sys.stderr)
        # 구현 단계에서는 '경고(구현단계)' 로 내려오므로 여기서 걸리지 않는다.
        # 지적은 claim_audit.jsonl 에 그대로 쌓여 수정 단계의 작업 목록이 된다.
        if _verdict["verdict"] == "차단":
            raise ValueError(
                "발신 차단: 재측정에서 어긋난 주장이 있다. "
                "위 지적을 고치거나, 고칠 수 없으면 그 사실을 본문에 적어라. "
                "(감사 기록: .agent-swarm/messages/claim_audit.jsonl)")
    except ImportError:
        # 감사기가 없다고 발신을 막지는 않는다. 다만 조용히 넘어가지도 않는다.
        print("[경고] csc_audit 를 불러오지 못해 주장 감사를 건너뛴다.", file=sys.stderr)

    msg_types = [
        "ACK", "PROPOSAL", "RISK", "RESULT", "BLOCKED", "CALL_OUT",
        "WHISTLEBLOW", "TASK", "EVENT", "REPORT",
    ]
    if msg_type not in msg_types:
        raise ValueError(f"Invalid message type '{msg_type}'. Must be one of {msg_types}")

    now_utc = datetime.now(timezone.utc)
    short_uuid = uuid.uuid4().hex[:8]
    msg_id = f"MSG-{now_utc.strftime('%Y%m%d-%H%M%S')}-{now_utc.microsecond:06d}-{short_uuid}-{sender[:3].upper()}-{recipient[:3].upper()}"

    envelope = {
        "message_id": msg_id,
        "timestamp": get_utc_iso(),
        "sender": sender,
        "recipient": recipient,
        "type": msg_type,
        "in_reply_to": in_reply_to,
        "body": body
    }
    if correlation_id:
        envelope["correlation_id"] = correlation_id

    delivery_mode = "fallback"
    persisted_by_broker = False

    # 1. Attempt real-time socket delivery via broker
    if SwarmClientSync:
        try:
            client = SwarmClientSync()
            if client.is_running():
                # Transmit canonical envelope directly
                res = client.send_message(envelope, agent_name=sender)
                if res.get("status") == "ok" and res.get("persisted") is True:
                    delivery_mode = "realtime"
                    persisted_by_broker = True
        except Exception:
            delivery_mode = "fallback"
            persisted_by_broker = False

    # 2. Direct SSOT storage persistence fallback if broker did not persist
    if not persisted_by_broker:
        csc_storage.persist_message(envelope, base_dir=SWARM_DIR)
        delivery_mode = "fallback"

    print(f"📨 [CSC Message] {msg_id} ({msg_type}) sent from '{sender}' to '{recipient}' [{delivery_mode}].")
    return msg_id


class TaskExecutionFailed(RuntimeError):
    """Raised when an expected worker has terminally dead-lettered a TASK."""

    def __init__(self, task_id: str, failures):
        self.task_id = task_id
        self.failures = dict(failures)
        details = "; ".join(
            f"{agent}: {str(record.get('body', 'unknown failure'))[:500]}"
            for agent, record in sorted(self.failures.items())
        )
        super().__init__(f"task {task_id} failed: {details}")


class AwaitPending(RuntimeError):
    """The observation window ended while the TASK may still be running."""

    def __init__(self, task_id: str, missing, replies, elapsed_seconds: float):
        self.task_id = task_id
        self.missing = sorted(str(agent) for agent in missing)
        self.replies = dict(replies)
        self.elapsed_seconds = max(0.0, float(elapsed_seconds))
        super().__init__(
            f"task {task_id} is still pending for {self.missing}; do not resubmit"
        )


def _dead_letter_replies(task_id: str, expected, queue_path: Path):
    """Return terminal worker failures for one TASK from the durable DLQ."""
    dead_letter_dir = queue_path.parent.parent / "dead-letter"
    failures = {}
    for agent in sorted(expected):
        dlq_path = dead_letter_dir / f"{agent}.jsonl"
        if not dlq_path.exists():
            continue
        try:
            lines = dlq_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if (
                isinstance(record, dict)
                and str(record.get("sender", "")).lower() == agent
                and record.get("in_reply_to") == task_id
                and record.get("type") == "DEAD_LETTER"
            ):
                failures[agent] = record
    return failures

def wait_for_replies(
    task_id: str,
    expected_agents,
    queue_path=None,
    timeout: float = 120.0,
    poll_interval: float = 0.25,
    auth_key=None,
    auth_epoch=None,
    require_authenticated: bool = False,
    replay_window=None,
):
    """Wait for replies, failing immediately when a worker dead-letters the TASK."""
    expected = {str(agent).lower() for agent in expected_agents}
    path = Path(queue_path or (Path(SWARM_DIR) / "messages" / "queue.jsonl"))
    started = time.monotonic()
    deadline = started + timeout
    replies = {}
    if require_authenticated and (auth_key is None or not auth_epoch):
        raise ValueError("authenticated await requires auth_key and auth_epoch")
    nonce_window = replay_window or ReplayWindow()
    while time.monotonic() < deadline:
        if path.exists():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                lines = []
            for line in lines:
                try:
                    record = json.loads(line)
                except (ValueError, TypeError):
                    continue
                sender = str(record.get("sender", "")).lower()
                is_candidate = (
                    sender in expected
                    and record.get("in_reply_to") == task_id
                    and record.get("type") in {"RESULT", "BLOCKED"}
                )
                if not is_candidate:
                    continue
                if require_authenticated:
                    try:
                        record = verify_envelope(
                            record,
                            auth_key,
                            auth_epoch,
                            replay_window=nonce_window,
                        )
                    except AuthenticationError:
                        continue
                replies[sender] = record
            if expected.issubset(replies):
                return replies
        # DLQ records are local terminal execution evidence. Authenticated mode
        # deliberately ignores them because the current DLQ format is unsigned.
        if not require_authenticated:
            failures = _dead_letter_replies(task_id, expected, path)
            if failures:
                raise TaskExecutionFailed(task_id, failures)
        time.sleep(poll_interval)
    missing = sorted(expected.difference(replies))
    raise AwaitPending(task_id, missing, replies, time.monotonic() - started)


def _pid_alive(pid):
    """PID 가 실제로 살아 있는지 확인한다. 파일이 뭐라고 적어 뒀든 믿지 않는다.

    실측 근거 (2026-09-05):
      workers/claude.json 과 workers/antigravity.json 이 status "ready" 를,
      broker.json 이 status "RUNNING" 을 유지한 채로 세 프로세스가 모두 죽어 있었다.
      마지막 하트비트는 288분 전이었다. 그런데 status 대시보드는 워커를 아예
      표시하지 않았으므로 이 거짓말이 보이지 않았다.

      선언을 읽어서 상태를 보고하면 그건 상태 보고가 아니라 선언의 복창이다.
    """
    # Runtime activation and the status dashboard must share one liveness
    # predicate.  `tasklist` can return Access denied in a restricted Windows
    # host even when the process is alive, which previously produced false
    # DEAD reports immediately after a successful activation.
    return pid_is_alive(pid)


def _pid_probe(pid):
    from csc_process import probe_pid
    return probe_pid(pid)


def _worker_liveness():
    """워커 등록 파일을 읽되, status 필드는 참고값으로만 쓰고 실측으로 판정한다."""
    workers_dir = os.path.join(SWARM_DIR, "workers")
    rows = []
    if not os.path.isdir(workers_dir):
        return rows
    try:
        socket_roster = set(csc_runtime.query_roster(Path(__file__).resolve().parent).get("registered_agents", []))
    except Exception:
        socket_roster = set()
    now = time.time()
    for entry in sorted(os.listdir(workers_dir)):
        if not entry.endswith(".json") or entry.endswith(".cursor.json"):
            continue
        try:
            with open(os.path.join(workers_dir, entry), "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as exc:
            rows.append({"agent": entry, "verdict": "READ_ERROR",
                         "detail": f"{type(exc).__name__}", "declared": "?"})
            continue
        pid = meta.get("pid")
        age = now - float(meta.get("heartbeat_epoch") or 0)
        probe = _pid_probe(pid)
        fresh = age <= WORKER_HEARTBEAT_STALE_SECONDS
        agent = meta.get("agent", entry)
        registered = agent in socket_roster

        # 판정 우선순위: 확실한 부재 > 확실한 존재 > 보조 증거
        # 'gone' 은 뒤집지 않는다. 하트비트가 아무리 신선해도 그 PID 는 없다.
        # 그 경우 하트비트를 쓰는 주체는 등록된 PID 가 아니라는 뜻이므로
        # 그 사실 자체를 드러낸다 — 조용히 LIVE 로 덮으면 예전 거짓말로 돌아간다.
        if probe == "gone":
            verdict = "PID_STALE" if (fresh and registered) else "DEAD"
        elif probe == "alive":
            verdict = "LIVE" if fresh else "STALLED"
        else:  # unknown — 권한 부족. 이때만 보조 증거로 보완한다
            verdict = "LIVE" if (fresh and registered) else "UNKNOWN"
        rows.append({
            "agent": agent, "pid": pid,
            "declared": meta.get("status", "?"), "verdict": verdict,
            "age_min": age / 60.0,
        })
    return rows


def print_status():
    """Prints live swarm status including broker, locks, tasks, and recent messages."""
    print("=" * 65)
    print("📊 [CSC Status] Codex Swarm Command Live Dashboard")
    print("=" * 65)

    # 0. Broker Status
    if SwarmClientSync:
        client = SwarmClientSync()
        if client.is_running():
            print(f"🟢 [Broker Status] Active on {client.host}:{client.port} (PID: {client.meta.get('pid')})")
        else:
            print("⚪ [Broker Status] Inactive (Using reliable JSONL queue fallback)")
            # broker.json 이 RUNNING 이라고 적혀 있어도 프로세스가 죽어 있을 수 있다.
            # 실제로 그런 상태가 4시간 48분 동안 방치된 적이 있다. 거짓말을 드러낸다.
            try:
                with open(BROKER_META_FILE, "r", encoding="utf-8") as _bf:
                    _bm = json.load(_bf)
                if str(_bm.get("status", "")).upper() == "RUNNING":
                    _bp = _bm.get("pid")
                    print(f"     🚨 broker.json 은 status=RUNNING (PID {_bp}) 이라고 주장하지만 "
                          f"실제 프로세스는 {'살아있음' if _pid_alive(_bp) else '죽어 있음'}. "
                          f"파일이 낡았다 — csc.py broker start 로 재기동하라.")
            except FileNotFoundError:
                pass
            except Exception:
                pass
    print("-" * 65)

    # 0-b. Worker Liveness — 선언이 아니라 실측으로 판정한다.
    rows = _worker_liveness()
    if rows:
        bad = [r for r in rows if r.get("verdict") != "LIVE"]
        marker = "🚨" if bad else "🟢"
        print(f"{marker} Workers ({len(rows) - len(bad)}/{len(rows)} LIVE):")
        for r in rows:
            v = r.get("verdict")
            icon = {"LIVE": "🟢", "STALLED": "🟡", "DEAD": "🔴",
                    "PID_STALE": "🟠", "UNKNOWN": "⚪"}.get(v, "⚪")
            age = r.get("age_min")
            age_s = f"{age:.0f}분 전" if isinstance(age, float) else "?"
            print(f"  {icon} {str(r.get('agent')):12s} 실측={v:8s} "
                  f"파일주장='{r.get('declared')}' PID={r.get('pid')} 하트비트={age_s}")
        if bad:
            print("     ⚠️ 파일이 'ready' 라고 적혀 있어도 위 실측이 정답이다.")
            if any(r.get("verdict") == "PID_STALE" for r in rows):
                print("     🟠 PID_STALE: 기록된 PID 는 죽었는데 하트비트는 갱신되고 있다.")
                print("        살아 있는 다른 프로세스가 쓰고 있다는 뜻 — 등록 PID 가 낡았다.")
                print("        재기동으로 등록을 맞춰라: python csc.py activate")
            print("     복구: python csc.py activate  (브로커 + 워커 재기동)")
    else:
        print("⚪ Workers: 등록된 워커 없음")
    print("-" * 65)

    # 1. Active Locks
    locks_dir = os.path.join(SWARM_DIR, "locks")
    active_locks = []
    orphaned_locks = []          # meta 가 없거나 손상된 락. 이전에는 통째로 은폐됐다.
    if os.path.exists(locks_dir):
        for entry in os.listdir(locks_dir):
            if not entry.endswith(".lock"):
                continue
            lock_path = os.path.join(locks_dir, entry)
            meta_path = os.path.join(lock_path, "meta.json")
            # 락의 존재 여부는 '디렉터리'가 정한다. meta 유무가 아니다.
            # meta 없는 락도 자원을 실제로 막고 있으므로 반드시 보여야 한다.
            if not os.path.exists(meta_path):
                orphaned_locks.append({"entry": entry, "reason": "meta.json 없음",
                                       "age_s": int(time.time() - os.path.getmtime(lock_path))})
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    active_locks.append(json.load(f))
            except Exception as e:
                orphaned_locks.append({"entry": entry, "reason": f"meta 손상: {type(e).__name__}",
                                       "age_s": int(time.time() - os.path.getmtime(lock_path))})
    print(f"🔒 Active Locks ({len(active_locks)}):")
    now_ts = time.time()
    for lk in active_locks:
        idle_s = int(now_ts - lk.get("last_touched_at_ts", now_ts))
        stale_mark = " ⚠️ [STALE]" if idle_s > LOCK_TTL_SECONDS else " [ACTIVE]"
        print(f"  • {lk.get('resource')} -> Owner: {lk.get('owner')} | Idle: {idle_s}s | Steps: {lk.get('step_count')}{stale_mark}")

    # 1-b. Orphaned Locks — 자원을 실제로 막고 있으나 소유자를 알 수 없는 락.
    # 이전 status 는 meta 있는 것만 세어 이 상태를 통째로 숨겼다.
    if orphaned_locks:
        print(f"🧟 Orphaned Locks ({len(orphaned_locks)}):  ← 자원을 막고 있으나 소유자 불명")
        for ol in orphaned_locks:
            print(f"  • {ol['entry']} | {ol['reason']} | {ol['age_s']}s 경과")
        print("     복구: csc.py lock release <resource> --owner <you> --force "
              f"(또는 {ORPHAN_GRACE_SECONDS}s 유예 후 재획득 시 자동 회수)")

    # 2. Recent Messages
    queue_path = os.path.join(SWARM_DIR, "messages", "queue.jsonl")
    print(f"\n📨 Recent Swarm Messages (Last 5):")
    if os.path.exists(queue_path):
        with open(queue_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-5:]:
            try:
                msg = json.loads(line.strip())
                print(f"  [{msg.get('timestamp')[:19]}] {msg.get('sender')} -> {msg.get('recipient')} | {msg.get('type')}: {msg.get('body')[:60]}...")
            except Exception:
                pass
    print("=" * 65)

def manage_broker(action: str, port: int = DEFAULT_PORT):
    broker_script = os.path.join(os.path.dirname(__file__), "csc_broker.py")
    if action == "start":
        if SwarmClientSync and SwarmClientSync().is_running():
            print("ℹ️ [CSC Broker] Broker is already running.")
            return
        print(f"🚀 [CSC Broker] Starting background broker daemon on port {port}...")
        subprocess.Popen([sys.executable, broker_script, "--port", str(port)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
        time.sleep(0.5)
        if SwarmClientSync and SwarmClientSync().is_running():
            print("✨ [CSC Broker] Broker started successfully.")
        else:
            print("⚠️ [CSC Broker] Verification timeout. Broker may still be initializing.")
    elif action == "stop":
        if os.path.exists(BROKER_META_FILE):
            try:
                with open(BROKER_META_FILE, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                pid = meta.get("pid")
                if pid:
                    if sys.platform == "win32":
                        os.system(f"taskkill /F /PID {pid} >nul 2>&1")
                    else:
                        os.system(f"kill -9 {pid} >/dev/null 2>&1")
                os.remove(BROKER_META_FILE)
                print(f"🛑 [CSC Broker] Broker (PID: {pid}) stopped.")
            except Exception as e:
                print(f"❌ [CSC Broker] Error stopping broker: {e}")
        else:
            print("ℹ️ [CSC Broker] No active broker meta found.")
    elif action == "status":
        if SwarmClientSync and SwarmClientSync().is_running():
            client = SwarmClientSync()
            print(f"🟢 [CSC Broker] Running on {client.host}:{client.port} (PID: {client.meta.get('pid')})")
        else:
            print("🔴 [CSC Broker] Broker is stopped.")

def activate_project(project_root: Path, timeout: float, budget_saving: bool = True) -> dict:
    """C3P 런타임을 발동하고 성공·실패 모두 해당 프로젝트 감시판을 남긴다."""
    import csc_dashboard

    root = project_root.resolve()
    dashboard_root = Path(csc_dashboard.HERE).resolve()
    if dashboard_root != root:
        raise RuntimeError(
            f"WORKSPACE_MISMATCH: dashboard root={dashboard_root}, activation root={root}"
        )
    try:
        result = csc_runtime.activate(root, timeout=timeout, budget_saving=budget_saving)
    except Exception:
        try:
            csc_dashboard.write_dashboard()
        except Exception as dashboard_exc:
            print(f"⚠️ [CSC Dashboard] 실패 상태 감시판 생성 실패: {dashboard_exc}", file=sys.stderr)
        raise
    dashboard_path = Path(csc_dashboard.write_dashboard()).resolve()
    result["dashboard"] = {
        "project": root.name,
        "path": str(dashboard_path),
        "kind": "activation_snapshot",
    }
    return result


def main():
    # Delegate before the outer parser sees work-specific flags such as --db.
    # This keeps the work coordinator's CLI independently testable and avoids
    # duplicating its argument schema here.
    if len(sys.argv) > 1 and sys.argv[1] == "work":
        from csc_work_item import main as work_main
        raise SystemExit(work_main(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="Codex Swarm Command (CSC) CLI v2.0")
    subparsers = parser.add_subparsers(dest="command")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize .agent-swarm environment")
    init_parser.add_argument("--force", action="store_true", help="Force reinitialization")

    # broker
    broker_parser = subparsers.add_parser("broker", help="Manage real-time local broker server")
    broker_parser.add_argument("broker_action", choices=["start", "stop", "status"], help="Action to perform")
    broker_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")

    # persistent 3P runtime
    activate_parser = subparsers.add_parser("activate", help="Start/reuse broker and two registered CLI adapters")
    activate_parser.add_argument("--timeout", type=float, default=10.0, help="Readiness deadline in seconds")
    activate_parser.add_argument("--budget-saving", action=argparse.BooleanOptionalAction, default=True, help="Run in zero-token local standby budget-saving mode")
    trigger_parser = subparsers.add_parser(
        "trigger", help="Activate C3P only for an explicit supported phrase"
    )
    trigger_parser.add_argument("phrase", help="Exact activation phrase after whitespace normalization")
    trigger_parser.add_argument("--timeout", type=float, default=10.0, help="Readiness deadline in seconds")
    subparsers.add_parser("roster", help="Show live broker socket registrations")

    watch_parser = subparsers.add_parser("watch", help="Start zero-token real-time message watcher")
    watch_parser.add_argument("--me", default=os.environ.get("CSC_AGENT_ID", "antigravity"), help="Target agent name to watch for")
    watch_parser.add_argument("--interval", type=float, default=2.0, help="Check interval in seconds")
    watch_parser.add_argument("--max-minutes", type=float, default=0.0, help="Max run duration in minutes (0=forever)")

    await_parser = subparsers.add_parser("await", help="Observe TASK replies for a bounded window")
    await_parser.add_argument("--task-id", required=True)
    await_parser.add_argument("--agents", nargs="+", default=["claude", "antigravity"])
    await_parser.add_argument("--timeout", type=float, default=120.0)

    work_parser = subparsers.add_parser("work", help="Plan and coordinate conflict-free C3P work items")
    work_parser.add_argument("work_args", nargs=argparse.REMAINDER)

    # lock
    lock_parser = subparsers.add_parser("lock", help="Lock management")
    lock_sub = lock_parser.add_subparsers(dest="lock_action")

    acq_parser = lock_sub.add_parser("acquire", help="Acquire a resource lock")
    acq_parser.add_argument("resource", help="Resource path to lock")
    acq_parser.add_argument("--owner", required=True, help="Agent claiming lock")

    touch_parser = lock_sub.add_parser("touch", help="Touch a resource lock")
    touch_parser.add_argument("resource", help="Resource path to touch")
    touch_parser.add_argument("--owner", required=True, help="Agent claiming lock")

    rel_parser = lock_sub.add_parser("release", help="Release a resource lock")
    rel_parser.add_argument("resource", help="Resource path to release")
    rel_parser.add_argument("--owner", required=True, help="Agent claiming lock")
    rel_parser.add_argument("--force", action="store_true", help="Force release stale lock")

    # send
    send_parser = subparsers.add_parser("send", help="Send a swarm message")
    send_parser.add_argument("--sender", required=True, help="Sending agent")
    send_parser.add_argument("--recipient", required=True, help="Recipient agent")
    send_parser.add_argument("--type", required=True, choices=["ACK", "PROPOSAL", "RISK", "RESULT", "BLOCKED", "CALL_OUT", "WHISTLEBLOW", "TASK", "EVENT", "REPORT"], help="Message type")
    send_parser.add_argument("--body", required=True, help="Message body text")
    send_parser.add_argument("--in-reply-to", default="none", help="Parent message ID or SEQ")
    send_parser.add_argument("--correlation-id", default="", help="Decision or workflow correlation ID")

    # status
    subparsers.add_parser("status", help="Show swarm status dashboard")
    doctor_parser = subparsers.add_parser("doctor", help="Bounded local transport diagnosis")
    doctor_parser.add_argument("--json", action="store_true", help="Machine-readable report")
    doctor_parser.add_argument("--project-root", default=None)
    doctor_parser.add_argument("--send-test", action="store_true", help="Persist one inert diagnostic EVENT")

    args = parser.parse_args()

    if args.command == "init":
        init_swarm(args.force)
    elif args.command == "activate":
        init_swarm(False)
        try:
            result = activate_project(
                Path(__file__).resolve().parent,
                timeout=args.timeout,
                budget_saving=args.budget_saving,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except (csc_runtime.ActivationError, OSError, RuntimeError) as exc:
            print(f"❌ [CSC Activate] {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "trigger":
        if is_runtime_activation_trigger(args.phrase) or is_budget_saving_trigger(args.phrase):
            init_swarm(False)
            try:
                result = activate_project(
                    Path(__file__).resolve().parent,
                    timeout=args.timeout,
                    budget_saving=True,
                )
                result["trigger"] = args.phrase
                print(json.dumps(result, ensure_ascii=False, indent=2))
            except (csc_runtime.ActivationError, OSError, RuntimeError) as exc:
                print(f"❌ [CSC Trigger] {exc}", file=sys.stderr)
                sys.exit(1)
        elif is_user_absence_trigger(args.phrase):
            init_swarm(False)
            try:
                result = activate_project(
                    Path(__file__).resolve().parent,
                    timeout=args.timeout,
                    budget_saving=True,
                )
                result["trigger"] = args.phrase
                result["user_absence_mode"] = arm_user_absence_mode(
                    Path(__file__).resolve().parent, args.phrase
                )
                print(json.dumps(result, ensure_ascii=False, indent=2))
            except (csc_runtime.ActivationError, OSError, RuntimeError) as exc:
                print(f"❌ [CSC Trigger] {exc}", file=sys.stderr)
                sys.exit(1)
        else:
            print(
                "❌ [CSC Trigger] 지원하지 않거나 명시적이지 않은 발동문입니다. "
                "예: C3P 예산절약 모드, C3P 사용자부재 모드",
                file=sys.stderr,
            )
            sys.exit(2)
    elif args.command == "roster":
        try:
            result = csc_runtime.query_roster(Path(__file__).resolve().parent)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f"❌ [CSC Roster] {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "await":
        try:
            replies = wait_for_replies(
                args.task_id, set(args.agents), timeout=args.timeout,
            )
            print(json.dumps(replies, ensure_ascii=False, indent=2))
        except AwaitPending as pending:
            print(json.dumps({
                "status": "PENDING",
                "task_id": pending.task_id,
                "missing_agents": pending.missing,
                "received_agents": sorted(pending.replies),
                "elapsed_seconds": round(pending.elapsed_seconds, 3),
                "resubmit": False,
            }, ensure_ascii=False, indent=2))
        except TaskExecutionFailed as exc:
            print(f"❌ [CSC Await] {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "broker":
        manage_broker(args.broker_action, args.port)
    elif args.command == "lock":
        if args.lock_action == "acquire":
            success = acquire_lock(args.resource, args.owner)
            sys.exit(0 if success else 1)
        elif args.lock_action == "touch":
            success = touch_lock(args.resource, args.owner)
            sys.exit(0 if success else 1)
        elif args.lock_action == "release":
            success = release_lock(args.resource, args.owner, args.force)
            sys.exit(0 if success else 1)
        else:
            lock_parser.print_help()
    elif args.command == "send":
        try:
            send_message(
                args.sender,
                args.recipient,
                args.type,
                args.body,
                args.in_reply_to,
                args.correlation_id,
            )
        except ValueError as exc:
            # 감사 차단은 프로그램 오류가 아니라 정상적인 거절이다.
            # 스택 추적을 쏟아내면 정작 읽어야 할 지적이 묻힌다.
            print("", file=sys.stderr)
            print(str(exc), file=sys.stderr)
            sys.exit(3)
    elif args.command == "status":
        print_status()
        from csc_doctor import diagnose, print_report
        report = diagnose()
        print_report(report)
        sys.exit(report["exit_code"])
    elif args.command == "doctor":
        from csc_doctor import diagnose, print_report
        report = diagnose(args.project_root, send_test=args.send_test)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_report(report)
        sys.exit(report["exit_code"])
    elif args.command == "watch":
        import csc_watch
        sys.argv = [
            sys.argv[0],
            "--me", args.me,
            "--interval", str(args.interval),
            "--max-minutes", str(args.max_minutes),
        ]
        sys.exit(csc_watch.main())
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
