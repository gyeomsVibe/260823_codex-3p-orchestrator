"""Evidence-backed quota observations for the dry-run routing policy.

This module validates observations without collecting them or starting a model.
It deliberately keeps an absent observation distinct from a claim that quota is
normal: absence maps to the policy's existing ``unknown`` state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Iterable, Mapping

from .policy import RoutingDecision, route_task as policy_route_task


class RuntimeMode(str, Enum):
    """Controller mode derived from an evidence-backed quota observation."""

    NORMAL = "normal"
    BUDGET = "budget"
    CRITICAL = "critical"


_VALID_SOURCES = frozenset({"provider", "user"})
_VALID_STATES = frozenset({"normal", "constrained", "exhausted"})


@dataclass(frozen=True)
class QuotaObservation:
    """A quota fact supplied by a provider or explicitly by the user."""

    source: str
    state: str
    observed_at: str
    evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or self.source not in _VALID_SOURCES:
            raise ValueError(f"source must be one of {sorted(_VALID_SOURCES)}")
        if not isinstance(self.state, str) or self.state not in _VALID_STATES:
            raise ValueError(f"state must be one of {sorted(_VALID_STATES)}")
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise ValueError("evidence must be a non-empty string")
        if not isinstance(self.observed_at, str) or not self.observed_at.strip():
            raise ValueError("observed_at must be a non-empty UTC ISO-8601 string")

        try:
            timestamp = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be a UTC ISO-8601 timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("observed_at must use the UTC offset (+00:00 or Z)")


def resolve_runtime_mode(
    observation: QuotaObservation | None, *, policy_disabled: bool = False
) -> RuntimeMode:
    """Derive mode without mutating the observation.

    ``policy_disabled`` selects NORMAL policy for this invocation only when not
    exhausted; exhausted observations always map to CRITICAL. It does not
    rewrite, discard, or otherwise alter the recorded observation.
    """

    if observation is not None and observation.state == "exhausted":
        return RuntimeMode.CRITICAL
    if policy_disabled or observation is None or observation.state == "normal":
        return RuntimeMode.NORMAL
    if observation.state == "constrained":
        return RuntimeMode.BUDGET
    return RuntimeMode.CRITICAL


def route_with_observation(
    profile: Mapping[str, Any],
    observation: QuotaObservation | None = None,
    *,
    policy_disabled: bool = False,
    catalog: Mapping[str, Any] | None = None,
) -> RoutingDecision:
    """Call the existing policy with a quota state derived from observation.

    The original mapping is copied rather than mutated. Exhausted observations
    always preserve their blocked status regardless of policy_disabled.
    """

    effective_profile = dict(profile)
    if observation is not None and observation.state == "exhausted":
        effective_profile["quota_state"] = "exhausted"
    elif policy_disabled:
        effective_profile["quota_state"] = "normal"
    elif observation is None:
        effective_profile["quota_state"] = "unknown"
    else:
        effective_profile["quota_state"] = observation.state
    return policy_route_task(effective_profile, catalog=catalog)


def consume_unique_logical_replies(
    replies: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Return each logical reply once, distinguishing distinct senders.

    This is a pure helper for Codex's approval aggregation. It never changes
    the append-only queue or transport-level ``message_id`` deduplication.
    """

    seen: set[tuple[str, str, str, str]] = set()
    unique: list[Mapping[str, Any]] = []
    for reply in replies:
        digest = hashlib.sha256(
            str(reply.get("body", "")).strip().encode("utf-8")
        ).hexdigest()
        sender = str(reply.get("sender", "")).strip()
        key = (
            sender,
            str(reply.get("in_reply_to", "")),
            str(reply.get("correlation_id", "")),
            digest,
        )
        if key not in seen:
            seen.add(key)
            unique.append(reply)
    return unique
