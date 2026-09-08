"""Deterministic policy for Antigravity-first C3P work.

This module does not call an AI model or execute evidence commands. It decides
whether a task is eligible for delegation, validates anchored evidence, and
evaluates an A/B pilot from recorded metrics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


EVIDENCE_SCHEMA_VERSION = "c3p-evidence-v1"
ELIGIBLE_KINDS = {"research", "code_search", "test_matrix", "visual_qa"}
CONTROLLED_KINDS = {"core_code", "architecture", "security", "authentication", "destructive"}
RISK_LEVELS = {"low", "medium", "high"}


class PolicyInputError(ValueError):
    """Raised when a routing, evidence, or metrics document is malformed."""


def _required_bool(doc: Mapping[str, Any], name: str) -> bool:
    value = doc.get(name)
    if not isinstance(value, bool):
        raise PolicyInputError(f"{name} must be a boolean")
    return value


def _non_negative_number(doc: Mapping[str, Any], name: str) -> float:
    value = doc.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise PolicyInputError(f"{name} must be a non-negative number")
    return float(value)


def route_task(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic route without asking a model for confidence."""
    task_id = profile.get("task_id")
    task_kind = profile.get("task_kind")
    risk = profile.get("risk")
    if not isinstance(task_id, str) or not task_id.strip():
        raise PolicyInputError("task_id must be a non-empty string")
    if not isinstance(task_kind, str) or not task_kind.strip():
        raise PolicyInputError("task_kind must be a non-empty string")
    if risk not in RISK_LEVELS:
        raise PolicyInputError(f"risk must be one of {sorted(RISK_LEVELS)}")

    read_only = _required_bool(profile, "read_only")
    independent = _required_bool(profile, "independent")
    verifiable = _required_bool(profile, "verifiable")
    shared_write = _required_bool(profile, "shared_write")
    external_side_effect = _required_bool(profile, "external_side_effect")
    judgment_required = _required_bool(profile, "judgment_required")
    bulk_work = _required_bool(profile, "bulk_work")
    parallel_units = profile.get("parallel_units", 1)
    if isinstance(parallel_units, bool) or not isinstance(parallel_units, int) or parallel_units < 1:
        raise PolicyInputError("parallel_units must be a positive integer")

    hard_stop_reasons: list[str] = []
    if task_kind in CONTROLLED_KINDS:
        hard_stop_reasons.append("task kind belongs to the scarce-tool control plane")
    if risk == "high":
        hard_stop_reasons.append("risk is high")
    if shared_write:
        hard_stop_reasons.append("task shares writable state")
    if external_side_effect:
        hard_stop_reasons.append("task can create an external side effect")
    if judgment_required:
        hard_stop_reasons.append("task requires architectural or acceptance judgment")
    if not read_only:
        hard_stop_reasons.append("task is not read-only")
    if not verifiable:
        hard_stop_reasons.append("output has no reproducible verification anchor")

    if hard_stop_reasons:
        return {
            "task_id": task_id,
            "route": "SCARCE_CONTROLLED",
            "council_participants": ["codex", "claude", "antigravity"],
            "antigravity_lanes": 0,
            "antigravity_mode": "ADVISORY_ONLY",
            "claude_mode": "FULL_REVIEW",
            "reasons": hard_stop_reasons,
        }

    if task_kind not in ELIGIBLE_KINDS:
        return {
            "task_id": task_id,
            "route": "SCARCE_CONTROLLED",
            "council_participants": ["codex", "claude", "antigravity"],
            "antigravity_lanes": 0,
            "antigravity_mode": "ADVISORY_ONLY",
            "claude_mode": "FULL_REVIEW",
            "reasons": ["task kind is not in the measured delegation allowlist"],
        }

    lanes = 1
    if independent and bulk_work:
        lanes = min(3, parallel_units)
    reasons = ["read-only output has reproducible anchors"]
    if lanes > 1:
        reasons.append("work has independent parallel units")
    else:
        reasons.append("work is delegated sequentially to avoid coordination overhead")
    return {
        "task_id": task_id,
        "route": "ANTIGRAVITY_FIRST",
        "council_participants": ["codex", "claude", "antigravity"],
        "antigravity_lanes": lanes,
        "antigravity_mode": "BULK_EVIDENCE",
        "claude_mode": "COMPACT_SENTINEL",
        "reasons": reasons,
    }


def _safe_file(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise PolicyInputError("locator path must be a non-empty string")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PolicyInputError("locator path escapes the project root") from exc
    return candidate


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_file_locator(locator: Mapping[str, Any], root: Path) -> tuple[bool, str]:
    path = _safe_file(root, locator.get("path"))
    if not path.is_file():
        return False, f"file does not exist: {locator.get('path')}"
    start = locator.get("line_start")
    end = locator.get("line_end")
    expected = locator.get("sha256")
    if isinstance(start, bool) or not isinstance(start, int) or start < 1:
        return False, "line_start must be a positive integer"
    if isinstance(end, bool) or not isinstance(end, int) or end < start:
        return False, "line_end must be an integer greater than or equal to line_start"
    if not isinstance(expected, str) or len(expected) != 64:
        return False, "sha256 must be a 64-character digest"
    lines = path.read_text(encoding="utf-8").splitlines()
    if end > len(lines):
        return False, "line range exceeds the file"
    actual = _sha256("\n".join(lines[start - 1:end]).encode("utf-8"))
    if actual != expected.lower():
        return False, "file-line hash mismatch"
    return True, "file lines and hash verified"


def _validate_url_locator(locator: Mapping[str, Any]) -> tuple[bool, str]:
    url = locator.get("url")
    excerpt = locator.get("excerpt")
    if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"}:
        return False, "url locator must use http or https"
    if not isinstance(excerpt, str) or not excerpt.strip():
        return False, "url locator requires a non-empty excerpt"
    return True, "URL is anchored but requires independent sample review"


def validate_evidence_packet(packet: Mapping[str, Any], project_root: str | Path) -> dict[str, Any]:
    """Validate evidence anchors without trusting the agent's success prose."""
    errors: list[str] = []
    root = Path(project_root).resolve()
    if packet.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EVIDENCE_SCHEMA_VERSION}")
    for name in ("task_id", "lane_id"):
        if not isinstance(packet.get(name), str) or not packet.get(name, "").strip():
            errors.append(f"{name} must be a non-empty string")
    if packet.get("status") not in {"COMPLETED", "NO_NEW_EVIDENCE", "BLOCKED"}:
        errors.append("status is invalid")
    if packet.get("read_only") is not True:
        errors.append("read_only must be true")
    claims = packet.get("claims")
    if not isinstance(claims, list):
        errors.append("claims must be a list")
        claims = []
    if packet.get("status") == "COMPLETED" and not claims:
        errors.append("COMPLETED packets require at least one claim")

    deterministic_claims = 0
    sample_review_claims = 0
    for index, claim in enumerate(claims):
        prefix = f"claims[{index}]"
        if not isinstance(claim, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        if not isinstance(claim.get("claim_id"), str) or not claim.get("claim_id", "").strip():
            errors.append(f"{prefix}.claim_id must be a non-empty string")
        if not isinstance(claim.get("text"), str) or not claim.get("text", "").strip():
            errors.append(f"{prefix}.text must be a non-empty string")
        locator = claim.get("locator")
        if not isinstance(locator, Mapping):
            errors.append(f"{prefix}.locator must be an object")
            continue
        locator_type = locator.get("type")
        try:
            if locator_type == "file":
                valid, note = _validate_file_locator(locator, root)
                if valid:
                    deterministic_claims += 1
            elif locator_type == "url":
                valid, note = _validate_url_locator(locator)
                if valid:
                    sample_review_claims += 1
            else:
                valid, note = False, "locator type must be file or url"
        except (OSError, UnicodeError, PolicyInputError) as exc:
            valid, note = False, str(exc)
        if not valid:
            errors.append(f"{prefix}: {note}")

    status = "ESCALATE" if errors else ("SAMPLE_REVIEW" if sample_review_claims else "VALID")
    return {
        "status": status,
        "errors": errors,
        "claims_total": len(claims),
        "deterministic_claims": deterministic_claims,
        "sample_review_claims": sample_review_claims,
    }


def evaluate_pilot(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate the candidate against a pre-registered baseline and thresholds."""
    metric_names = (
        "codex_tokens", "claude_tokens", "antigravity_tokens", "wall_seconds",
        "review_minutes", "critical_defects", "major_defects", "verified_findings",
        "workspace_mutations", "permission_bypasses", "invalid_packets",
        "total_packets", "quota_failures",
    )
    base = {name: _non_negative_number(baseline, name) for name in metric_names}
    cand = {name: _non_negative_number(candidate, name) for name in metric_names}
    min_reduction = _non_negative_number(policy, "min_scarce_token_reduction_pct")
    max_wall_increase = _non_negative_number(policy, "max_wall_time_increase_pct")
    max_total_multiplier = _non_negative_number(policy, "max_total_token_multiplier")
    required_packet_rate = _non_negative_number(policy, "min_valid_packet_rate")
    if required_packet_rate > 1:
        raise PolicyInputError("min_valid_packet_rate must be between 0 and 1")

    baseline_scarce = base["codex_tokens"] + base["claude_tokens"]
    candidate_scarce = cand["codex_tokens"] + cand["claude_tokens"]
    baseline_total = baseline_scarce + base["antigravity_tokens"]
    candidate_total = candidate_scarce + cand["antigravity_tokens"]
    if baseline_scarce <= 0:
        raise PolicyInputError("baseline scarce tokens must be greater than zero")
    scarce_reduction = (baseline_scarce - candidate_scarce) / baseline_scarce * 100
    if baseline_total <= 0:
        raise PolicyInputError("baseline total tokens must be greater than zero")
    total_multiplier = candidate_total / baseline_total
    if base["wall_seconds"] <= 0:
        raise PolicyInputError("baseline wall_seconds must be greater than zero")
    wall_increase = (cand["wall_seconds"] - base["wall_seconds"]) / base["wall_seconds"] * 100
    valid_packets = cand["total_packets"] - cand["invalid_packets"]
    packet_rate = valid_packets / cand["total_packets"] if cand["total_packets"] else 0.0

    checks = {
        "scarce_tokens": scarce_reduction >= min_reduction,
        "total_token_budget": total_multiplier <= max_total_multiplier,
        "quality": (
            cand["critical_defects"] <= base["critical_defects"]
            and cand["major_defects"] <= base["major_defects"]
            and cand["verified_findings"] >= base["verified_findings"]
        ),
        "wall_time": wall_increase <= max_wall_increase,
        "review_effort": cand["review_minutes"] <= base["review_minutes"],
        "evidence_packets": packet_rate >= required_packet_rate,
        "workspace_safety": cand["workspace_mutations"] == 0,
        "permission_safety": cand["permission_bypasses"] == 0,
        "availability": cand["quota_failures"] == 0,
    }
    safety_or_quality_failed = not (
        checks["quality"] and checks["workspace_safety"] and checks["permission_safety"]
    )
    if all(checks.values()):
        decision = "SCALE"
    elif safety_or_quality_failed:
        decision = "STOP"
    else:
        decision = "ITERATE"
    return {
        "decision": decision,
        "checks": checks,
        "scarce_token_reduction_pct": round(scarce_reduction, 2),
        "wall_time_increase_pct": round(wall_increase, 2),
        "valid_packet_rate": round(packet_rate, 4),
        "total_token_multiplier": round(total_multiplier, 4),
        "baseline_scarce_tokens": baseline_scarce,
        "candidate_scarce_tokens": candidate_scarce,
        "baseline_total_tokens": baseline_total,
        "candidate_total_tokens": candidate_total,
    }


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
