"""Telemetry parsing and recording for Antigravity CLI executions.

Supports parsing `--output-format stream-json` and `--output-format json` outputs,
extracting real token usage, duration, and response text, and persisting telemetry
events to durable NDJSON logs for C3P budget accounting.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from csc_storage import file_lock


class TelemetryParseError(ValueError):
    """Raised when CLI output does not contain recognizable JSON/stream-json telemetry."""


def parse_cli_json(raw_output: str) -> dict[str, Any]:
    """Parse single-object JSON output from `agy --output-format json`.

    Ignores non-JSON leading/trailing lines such as CLI warnings.
    """
    cleaned_lines = []
    for line in raw_output.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        if line_str.startswith("{") and line_str.endswith("}"):
            cleaned_lines.append(line_str)

    if not cleaned_lines:
        raise TelemetryParseError("no valid JSON object found in output")

    # The result object is typically the last JSON line if multiple exist
    for candidate in reversed(cleaned_lines):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and ("usage" in data or "response" in data or "status" in data):
                return _normalize_result(data)
        except json.JSONDecodeError:
            continue

    raise TelemetryParseError("could not locate valid result payload in CLI output")


def parse_stream_json(raw_output: str) -> dict[str, Any]:
    """Parse newline-delimited stream-json events from `agy --output-format stream-json`."""
    events: list[dict[str, Any]] = []
    for line in raw_output.splitlines():
        line_str = line.strip()
        if not line_str or not (line_str.startswith("{") and line_str.endswith("}")):
            continue
        try:
            parsed = json.loads(line_str)
            if isinstance(parsed, dict) and "event" in parsed:
                events.append(parsed)
        except json.JSONDecodeError:
            continue

    if not events:
        raise TelemetryParseError("no stream-json events found in raw output")

    result_event = next((ev for ev in reversed(events) if ev.get("event") == "result"), None)
    if result_event and "result" in result_event and isinstance(result_event["result"], dict):
        normalized = _normalize_result(result_event["result"])
        normalized["stream_events_count"] = len(events)
        return normalized

    # Fallback: synthesize from step_update events if result event missing
    step_updates = [ev.get("step_update", {}) for ev in events if ev.get("event") == "step_update"]
    if step_updates:
        text_chunks = [su.get("text_delta", "") for su in step_updates if su.get("text_delta")]
        final_usage = next(
            (su.get("usage") for su in reversed(step_updates) if su.get("usage")),
            {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "total_tokens": 0},
        )
        return {
            "conversation_id": step_updates[-1].get("conversation_id", ""),
            "status": step_updates[-1].get("state", "UNKNOWN"),
            "response": "".join(text_chunks),
            "duration_seconds": float(step_updates[-1].get("duration_seconds", 0.0)),
            "num_turns": len(step_updates),
            "usage": final_usage,
            "stream_events_count": len(events),
        }

    raise TelemetryParseError("stream-json contained events but no result or step updates")


def extract_telemetry(raw_output: str) -> dict[str, Any]:
    """Extract telemetry from either stream-json or json CLI output format."""
    try:
        return parse_stream_json(raw_output)
    except TelemetryParseError:
        return parse_cli_json(raw_output)


def record_telemetry_event(
    event_data: Mapping[str, Any],
    log_path: Path | str,
) -> Path:
    """Append one telemetry record under the repository's cross-process lock."""
    path = Path(log_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(event_data), ensure_ascii=False, separators=(",", ":")) + "\n"
    lock_path = str(path) + ".lock"
    with file_lock(lock_path):
        with path.open("a", encoding="utf-8", newline="") as fp:
            fp.write(line)
            fp.flush()
            os.fsync(fp.fileno())
    return path


def summarize_telemetry(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize a sequence of telemetry records for A/B budget accounting."""
    total_input = 0
    total_output = 0
    total_thinking = 0
    total_tokens = 0
    total_duration = 0.0
    success_count = 0

    for rec in records:
        usage = rec.get("usage", {})
        total_input += int(usage.get("input_tokens", 0))
        total_output += int(usage.get("output_tokens", 0))
        total_thinking += int(usage.get("thinking_tokens", 0))
        total_tokens += int(usage.get("total_tokens", 0))
        total_duration += float(rec.get("duration_seconds", 0.0))
        if rec.get("status") == "SUCCESS":
            success_count += 1

    count = len(records)
    return {
        "count": count,
        "success_count": success_count,
        "success_rate": round(success_count / count, 4) if count else 0.0,
        "total_tokens": total_tokens,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "thinking_tokens": total_thinking,
        "total_duration_seconds": round(total_duration, 3),
        "avg_duration_seconds": round(total_duration / count, 3) if count else 0.0,
    }


def _normalize_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage_raw = payload.get("usage", {})
    if not isinstance(usage_raw, Mapping):
        usage_raw = {}
    denied_raw = payload.get("denied_actions", [])
    denied_actions = [dict(item) for item in denied_raw if isinstance(item, Mapping)] \
        if isinstance(denied_raw, list) else []
    return {
        "conversation_id": str(payload.get("conversation_id", "")),
        "status": str(payload.get("status", "")),
        "response": str(payload.get("response", "")),
        "error": str(payload.get("error", "")),
        "denied_actions": denied_actions,
        "duration_seconds": float(payload.get("duration_seconds", 0.0)),
        "num_turns": int(payload.get("num_turns", 1)),
        "usage": {
            "input_tokens": int(usage_raw.get("input_tokens", 0)),
            "output_tokens": int(usage_raw.get("output_tokens", 0)),
            "thinking_tokens": int(usage_raw.get("thinking_tokens", 0)),
            "cache_read_tokens": int(usage_raw.get("cache_read_tokens", 0)),
            "total_tokens": int(usage_raw.get("total_tokens", 0)),
        },
    }
