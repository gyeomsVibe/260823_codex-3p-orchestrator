#!/usr/bin/env python
"""Auditable unanimity and emergency-quorum policy for CSC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


AGENTS: Tuple[str, ...] = ("codex", "claude", "antigravity")
VALID_VOTES = {"YES", "NO", "PENDING", "ABSTAIN"}
VERIFIED_UNAVAILABLE_CODES = {
    "quota_exhausted",
    "credit_exhausted",
    "auth_unavailable",
    "binary_missing",
    "runtime_start_failed",
}


@dataclass(frozen=True)
class DecisionContext:
    risk: str
    reversible: bool
    requires_user_approval: bool = False


@dataclass(frozen=True)
class ConsensusResult:
    status: str
    mode: str
    active_agents: Tuple[str, ...]
    unavailable_agents: Tuple[str, ...]
    reason: str


def _verified_unavailable(
    agent: str,
    votes: Mapping[str, str],
    availability: Mapping[str, Mapping[str, Any]],
) -> bool:
    # Dissent is a vote, never an availability failure.
    if votes.get(agent, "PENDING").upper() == "NO":
        return False
    evidence = availability.get(agent, {})
    code = str(evidence.get("code", "")).lower()
    proof = str(evidence.get("evidence", "")).strip()
    return code in VERIFIED_UNAVAILABLE_CODES and bool(proof)


def evaluate_consensus(
    votes: Mapping[str, str],
    availability: Mapping[str, Mapping[str, Any]],
    context: DecisionContext,
) -> ConsensusResult:
    normalized = {agent: str(votes.get(agent, "PENDING")).upper() for agent in AGENTS}
    invalid = {agent: vote for agent, vote in normalized.items() if vote not in VALID_VOTES}
    if invalid:
        raise ValueError(f"invalid votes: {invalid}")

    unavailable = tuple(
        agent for agent in AGENTS if _verified_unavailable(agent, normalized, availability)
    )
    active = tuple(agent for agent in AGENTS if agent not in unavailable)

    if context.requires_user_approval:
        return ConsensusResult(
            "USER_APPROVAL_REQUIRED", "HUMAN_GATE", active, unavailable,
            "Agent consensus cannot replace a required user approval.",
        )

    if any(normalized[agent] == "NO" for agent in active):
        return ConsensusResult(
            "BLOCKED_DISSENT", "NO_CONSENSUS", active, unavailable,
            "At least one available agent voted NO.",
        )

    if len(unavailable) >= 2:
        return ConsensusResult(
            "BLOCKED_NO_QUORUM", "NO_QUORUM", active, unavailable,
            "Two or more agents are unavailable; mutations are not authorized.",
        )

    if not unavailable:
        if all(normalized[agent] == "YES" for agent in AGENTS):
            return ConsensusResult(
                "APPROVED_UNANIMOUS", "3_OF_3", active, unavailable,
                "All three agents explicitly voted YES.",
            )
        return ConsensusResult(
            "PENDING", "AWAITING_VOTES", active, unavailable,
            "Unanimity is the default and at least one vote is pending.",
        )

    # Exactly one agent is empirically unavailable. Emergency approval is
    # intentionally narrow: LOW risk, reversible, and 2/2 active YES.
    if str(context.risk).upper() != "LOW" or not context.reversible:
        return ConsensusResult(
            "BLOCKED_SCOPE", "NO_CONSENSUS", active, unavailable,
            "Emergency quorum is limited to reversible LOW-risk work.",
        )
    if all(normalized[agent] == "YES" for agent in active):
        return ConsensusResult(
            "APPROVED_DEGRADED", "2_OF_3_EMERGENCY", active, unavailable,
            "One verified unavailable agent; both active agents voted YES.",
        )
    return ConsensusResult(
        "PENDING", "AWAITING_ACTIVE_VOTES", active, unavailable,
        "Emergency quorum requires explicit YES from both active agents.",
    )
