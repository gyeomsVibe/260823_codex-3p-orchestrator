"""Pure, auditable policy for choosing a model before a new C3P invocation.

The current model never decides to downgrade itself.  This module consumes
observable task properties and returns a dry-run decision for the controller.
It does not start a model process or mutate global configuration.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


TIERS = ("economy", "balanced", "strong", "frontier")
PLATFORMS = ("codex", "claude", "antigravity")
RISKS = ("low", "medium", "high")
QUOTA_STATES = ("normal", "constrained", "exhausted", "unknown")

FRONTIER_KINDS = {"security", "authentication", "release", "destructive"}
STRONG_KINDS = {"architecture", "debugging", "refactor"}
BALANCED_KINDS = {"routine_edit", "bulk_evidence", "visual_qa"}
ECONOMY_KINDS = {"lookup", "formatting"}


class RoutingError(ValueError):
    """Raised when a task profile or catalog is invalid."""


@dataclass(frozen=True)
class RoutingDecision:
    task_id: str
    platform: str
    status: str
    preferred_tier: str
    selected_tier: str | None
    model: str | None
    effort: str | None
    reason_codes: tuple[str, ...]
    next_invocation_only: bool
    requires_fresh_session: bool
    max_attempts: int
    max_parallel: int
    max_escalations: int
    escalation_tier: str | None
    quota_failure_transition: str | None
    quota_reprobe: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_catalog(path: str | Path | None = None) -> dict[str, Any]:
    catalog_path = Path(path) if path else Path(__file__).with_name("catalog.json")
    with catalog_path.open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    if catalog.get("schema_version") != "c3p-model-catalog-v1":
        raise RoutingError("unsupported catalog schema")
    return catalog


def _required_string(profile: Mapping[str, Any], key: str) -> str:
    value = profile.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RoutingError(f"{key} must be a non-empty string")
    return value.strip()


def _bool(profile: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = profile.get(key, default)
    if not isinstance(value, bool):
        raise RoutingError(f"{key} must be a boolean")
    return value


def _preferred_tier(profile: Mapping[str, Any]) -> tuple[str, list[str]]:
    kind = _required_string(profile, "task_kind")
    risk = _required_string(profile, "risk")
    if risk not in RISKS:
        raise RoutingError(f"risk must be one of {RISKS}")
    affected = profile.get("affected_items", 1)
    if not isinstance(affected, int) or isinstance(affected, bool) or affected < 0:
        raise RoutingError("affected_items must be a non-negative integer")

    external = _bool(profile, "external_side_effect")
    destructive = _bool(profile, "destructive")
    cross_platform = _bool(profile, "cross_platform")
    clear = _bool(profile, "requirements_clear", True)
    quality_critical = _bool(profile, "quality_critical")
    read_only = _bool(profile, "read_only")
    verifiable = _bool(profile, "verifiable", True)

    if risk == "high" or kind in FRONTIER_KINDS or external or destructive:
        return "frontier", ["HIGH_IMPACT_OR_RISK"]
    if (
        risk == "medium"
        or kind in STRONG_KINDS
        or cross_platform
        or not clear
        or quality_critical
        or affected >= 10
    ):
        return "strong", ["COMPLEX_OR_QUALITY_CRITICAL"]
    if kind in BALANCED_KINDS or affected >= 4 or not read_only:
        return "balanced", ["ROUTINE_EXECUTION"]
    if kind in ECONOMY_KINDS and read_only and verifiable and clear and affected <= 3:
        return "economy", ["SMALL_CLEAR_VERIFIABLE"]
    return "balanced", ["SAFE_DEFAULT"]


def route_task(
    profile: Mapping[str, Any], catalog: Mapping[str, Any] | None = None
) -> RoutingDecision:
    """Return a deterministic pre-invocation model decision."""

    task_id = _required_string(profile, "task_id")
    platform = _required_string(profile, "platform")
    quota = _required_string(profile, "quota_state")
    if platform not in PLATFORMS:
        raise RoutingError(f"platform must be one of {PLATFORMS}")
    if quota not in QUOTA_STATES:
        raise RoutingError(f"quota_state must be one of {QUOTA_STATES}")

    preferred, reasons = _preferred_tier(profile)
    max_attempts = 2
    max_parallel = 1

    if quota == "exhausted":
        return RoutingDecision(
            task_id, platform, "BLOCKED", preferred, None, None, None,
            tuple(reasons + ["QUOTA_EXHAUSTED"]), True, True, 0, 0, 0, None,
            None, None,
        )

    selected = preferred
    if quota == "constrained" and preferred in {"strong", "frontier"}:
        return RoutingDecision(
            task_id, platform, "DEFER_OR_EQUIVALENT_FALLBACK", preferred,
            None, None, None,
            tuple(reasons + ["QUALITY_FLOOR_PROHIBITS_DOWNGRADE"]),
            True, True, 0, 0, 0, preferred, None, None,
        )
    if quota == "constrained" and preferred == "balanced":
        safe_to_downgrade = (
            _bool(profile, "read_only")
            and _bool(profile, "verifiable", True)
            and _bool(profile, "requirements_clear", True)
            and profile.get("risk") == "low"
        )
        if safe_to_downgrade:
            selected = "economy"
            reasons.append("SAFE_CONSTRAINED_DOWNGRADE")
        max_attempts = 1
    if quota == "unknown":
        max_attempts = 1
        max_parallel = 1
        reasons.append("UNKNOWN_QUOTA_SINGLE_ATTEMPT")

    resolved_catalog = catalog or load_catalog()
    try:
        choice = resolved_catalog["platforms"][platform]["tiers"][selected]
    except (KeyError, TypeError) as exc:
        raise RoutingError(f"catalog has no {platform}/{selected} entry") from exc

    escalation_index = min(TIERS.index(selected) + 1, len(TIERS) - 1)
    escalation = TIERS[escalation_index] if selected != "frontier" else None
    return RoutingDecision(
        task_id=task_id,
        platform=platform,
        status="READY",
        preferred_tier=preferred,
        selected_tier=selected,
        model=choice["model"],
        effort=choice["effort"],
        reason_codes=tuple(reasons),
        next_invocation_only=True,
        requires_fresh_session=True,
        max_attempts=max_attempts,
        max_parallel=max_parallel,
        max_escalations=0 if selected == "frontier" else 1,
        escalation_tier=escalation,
        quota_failure_transition=(
            "MARK_CONSTRAINED_ON_EXPLICIT_QUOTA_SIGNAL" if quota == "unknown" else None
        ),
        quota_reprobe=(
            "PROVIDER_RETRY_AFTER_OR_NEXT_REAL_TASK_AS_SINGLE_PROBE"
            if quota == "unknown"
            else None
        ),
    )


def build_launch_args(decision: RoutingDecision) -> list[str]:
    """Build transparent argv for a new invocation; never executes it."""

    if decision.status != "READY" or not decision.model or not decision.effort:
        raise RoutingError("only READY decisions can produce launch arguments")
    if decision.platform == "codex":
        return [
            "codex", "exec", "--model", decision.model,
            "--config", f'model_reasoning_effort="{decision.effort}"',
        ]
    if decision.platform == "claude":
        return ["claude", "--model", decision.model, "--effort", decision.effort]
    return ["agy", "--model", decision.model, "--effort", decision.effort]
