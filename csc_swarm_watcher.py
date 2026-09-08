#!/usr/bin/env python
"""Autonomous Swarm Watcher & Real-time Synchronizer Daemon

Runs in background to watch queue.jsonl, monitor peer activities,
keep dashboard.html updated on activity, and maintain Antigravity's heartbeat.

Specifications (Codex WATCHER-R3 Final):
1. Direct import csc_heartbeat.
2. Component active error tracking with RECOVERED log on recovery.
3. Peer state signature tracking (stale + missing_required) triggering dashboard on transitions.
4. Dashboard updated ONLY on valid parsed messages or peer transitions (0 calls on idle).
5. Binary-safe incremental queue reading (rb mode + rfind(b'\\n')).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import csc_heartbeat

PROJECT_ROOT = Path(__file__).resolve().parent
SWARM_DIR = PROJECT_ROOT / ".agent-swarm"
QUEUE_FILE = SWARM_DIR / "messages" / "queue.jsonl"
LOCKS_DIR = SWARM_DIR / "locks"
DASHBOARD_SCRIPT = PROJECT_ROOT / "csc_dashboard.py"

_ACTIVE_ERRORS: dict[str, str] = {}


def record_error(component: str, message: str) -> None:
    """Log an error to stderr at most once per unique message until recovered."""
    prev = _ACTIVE_ERRORS.get(component)
    if prev != message:
        _ACTIVE_ERRORS[component] = message
        sys.stderr.write(f"[watcher:{component}] {message}\n")
        sys.stderr.flush()


def record_success(component: str) -> None:
    """If component was previously in error, log RECOVERED once."""
    if component in _ACTIVE_ERRORS:
        del _ACTIVE_ERRORS[component]
        sys.stderr.write(f"[watcher:{component}] RECOVERED\n")
        sys.stderr.flush()


def reset_error_state() -> None:
    """Reset active error tracking (useful for test isolation)."""
    _ACTIVE_ERRORS.clear()


def update_dashboard() -> bool:
    """Execute csc_dashboard.py to refresh dashboard.html on activity."""
    try:
        res = subprocess.run(
            [sys.executable, str(DASHBOARD_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
            text=True,
        )
        if res.returncode != 0 and res.stderr:
            record_error("dashboard_process", res.stderr.strip()[:160])
            return False
        record_success("dashboard_process")
        return True
    except Exception as exc:
        record_error("update_dashboard_failed", str(exc))
        return False


def poll_queue_offset(queue_path: Path, current_offset: int) -> tuple[int, list[dict]]:
    """Incrementally read new JSON lines from queue_path using binary-safe offset cursor.

    Handles incomplete trailing lines by slicing up to the last b'\\n'.
    Returns:
        (new_offset, list_of_valid_parsed_messages)
    """
    if not queue_path.exists():
        return 0, []

    try:
        curr_size = queue_path.stat().st_size
        if curr_size < current_offset:
            # File truncated or recreated
            current_offset = 0

        if curr_size == current_offset:
            return current_offset, []

        new_messages = []
        with queue_path.open("rb") as f:
            f.seek(current_offset)
            data = f.read()

        last_nl = data.rfind(b"\n")
        if last_nl == -1:
            # Incomplete line; wait for newline to be written
            return current_offset, []

        complete_bytes = data[: last_nl + 1]
        new_offset = current_offset + len(complete_bytes)

        had_decode_error = False
        for line_bytes in complete_bytes.splitlines():
            line_bytes = line_bytes.strip()
            if line_bytes:
                try:
                    text = line_bytes.decode("utf-8", errors="replace")
                    new_messages.append(json.loads(text))
                except Exception as err:
                    had_decode_error = True
                    record_error("json_decode", str(err))

        if not had_decode_error:
            record_success("json_decode")

        record_success("poll_queue")
        return new_offset, new_messages
    except Exception as exc:
        record_error("poll_queue", str(exc))
        return current_offset, []


def tick_watcher(
    queue_path: Path,
    current_offset: int,
    started_epoch: float,
    instance_id: str,
    last_peer_signature: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
    dashboard_fn=update_dashboard,
) -> tuple[int, bool, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Execute a single tick of the watcher daemon.

    Returns:
        (updated_offset, activity_occurred, updated_peer_signature)
    """
    activity = False
    current_peer_signature: tuple[tuple[str, ...], tuple[str, ...]] = ((), ())

    # 1. Heartbeat & Peer Stale/Missing Transition
    try:
        csc_heartbeat.write_heartbeat("antigravity", instance_id=instance_id, started_epoch=started_epoch)
        record_success("write_heartbeat")

        peers = csc_heartbeat.check_peers("antigravity")
        stale_peers = tuple(sorted(name for name, _ in peers.get("stale", [])))
        missing_peers = tuple(sorted(name for name, in peers.get("missing_required", [])))
        current_peer_signature = (stale_peers, missing_peers)

        # Trigger dashboard on peer state transition
        if last_peer_signature is not None and current_peer_signature != last_peer_signature:
            activity = True
            try:
                dashboard_fn()
                record_success("dashboard_call")
            except Exception as exc:
                record_error("dashboard_call", str(exc))

        if stale_peers or missing_peers:
            record_error("peer_alert", csc_heartbeat.report("antigravity"))
        else:
            record_success("peer_alert")
    except Exception as exc:
        record_error("heartbeat", str(exc))

    # 2. Incremental Binary Queue Read (only trigger dashboard on valid messages)
    new_offset, new_msgs = poll_queue_offset(queue_path, current_offset)
    if new_msgs:
        activity = True
        try:
            dashboard_fn()
            record_success("dashboard_call")
        except Exception as exc:
            record_error("dashboard_call", str(exc))

    return new_offset, activity, current_peer_signature


def run_watcher(
    interval: float = 5.0,
    max_ticks: int | None = None,
    queue_path: Path = QUEUE_FILE,
    dashboard_fn=update_dashboard,
    instance_id: str = "antigravity-ide",
):
    """Main watcher loop without unconditional startup dashboard refresh."""
    started_epoch = time.time()
    current_offset = queue_path.stat().st_size if queue_path.exists() else 0

    try:
        csc_heartbeat.write_heartbeat("antigravity", instance_id=instance_id, started_epoch=started_epoch)
        record_success("write_heartbeat")
    except Exception as exc:
        record_error("initial_heartbeat", str(exc))

    ticks = 0
    last_peer_signature: tuple[tuple[str, ...], tuple[str, ...]] | None = None

    while max_ticks is None or ticks < max_ticks:
        try:
            time.sleep(interval)
            current_offset, _, last_peer_signature = tick_watcher(
                queue_path=queue_path,
                current_offset=current_offset,
                started_epoch=started_epoch,
                instance_id=instance_id,
                last_peer_signature=last_peer_signature,
                dashboard_fn=dashboard_fn,
            )
            ticks += 1
        except KeyboardInterrupt:
            break
        except Exception as exc:
            record_error("loop", f"{type(exc).__name__}: {exc}")
            time.sleep(interval)


if __name__ == "__main__":
    run_watcher()
