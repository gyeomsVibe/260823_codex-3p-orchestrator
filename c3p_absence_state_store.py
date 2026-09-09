"""Durable, local state for the C3P user-absence mode.

This module owns only the small runtime record under ``.agent-swarm/runtime``.
The pure transition rules remain in :mod:`c3p_absence_mode`.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_RELATIVE_PATH = Path(".agent-swarm") / "runtime" / "user_absence_mode.json"


def arm_user_absence_mode(project_root: Path, trigger: str) -> dict[str, Any]:
    """Persist an ARMED request after the C3P runtime has been activated."""

    state_path = project_root / STATE_RELATIVE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "state": "ARMED",
        "trigger": trigger,
        "armed_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(state_path, record)
    return record


def read_user_absence_mode(project_root: Path) -> dict[str, Any] | None:
    """Return the recorded state, or ``None`` when the mode was never armed."""

    state_path = project_root / STATE_RELATIVE_PATH
    try:
        with state_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    if not isinstance(data, dict) or data.get("state") not in {"ARMED", "PAUSED"}:
        raise ValueError("invalid user-absence mode state")
    return data


def _atomic_write_json(path: Path, record: dict[str, Any]) -> None:
    """Replace the runtime record atomically without touching message queues."""

    fd, temporary_name = tempfile.mkstemp(prefix=".user-absence-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
