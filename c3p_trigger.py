"""Deterministic recognition of explicit C3P budget-saving activation phrases.

Natural-language hosts decide when to call this module.  The matcher itself is
intentionally exact after whitespace and Unicode case-fold normalization, so a
discussion *about* budget saving cannot silently activate local processes.
"""

from __future__ import annotations

import unicodedata


# Kept verbatim in the three tool adapters.  A phrase can be recognized by a
# natural-language host without granting the CLI permission to guess intent.
C3P_CALL_PHRASE_CONTRACT_V1 = "C3P_CALL_PHRASE_CONTRACT_V1"

RUNTIME_ACTIVATION_TRIGGERS = frozenset({"c3p 발동"})
COUNCIL_REVIEW_REQUESTS = frozenset({"c3p 협의체와 검토해줘"})
MIA_C3P_REQUESTS = frozenset({"mia 씨3피 발동", "mia c3p 발동"})

BUDGET_SAVING_TRIGGERS = frozenset(
    {
        "c3p 예산절약 모드",
        "c3p 예산절약 모드 발동",
        "예산절약 모드",
        "예산절약 모드 발동",
        "c3p budget-saving mode",
        "c3p budget-saving mode activate",
        "budget-saving mode",
        "budget-saving mode activate",
    }
)

USER_ABSENCE_TRIGGERS = frozenset(
    {
        "c3p 사용자부재 모드",
        "c3p 사용자부재 모드 발동",
        "사용자부재 모드",
        "사용자부재 모드 발동",
        "c3p user-absence mode",
        "c3p user-absence mode activate",
        "user-absence mode",
        "user-absence mode activate",
    }
)


def normalize_trigger(text: str) -> str:
    """Apply NFC, Unicode case folding, and whitespace normalization only."""

    if not isinstance(text, str):
        raise TypeError("trigger text must be a string")
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def is_budget_saving_trigger(text: str) -> bool:
    """Return whether *text* is an explicit budget-saving activation phrase."""

    return normalize_trigger(text) in BUDGET_SAVING_TRIGGERS


def is_user_absence_trigger(text: str) -> bool:
    """Return whether *text* is an explicit user-absence mode activation phrase."""

    return normalize_trigger(text) in USER_ABSENCE_TRIGGERS


def is_runtime_activation_trigger(text: str) -> bool:
    """Return whether an exact C3P runtime activation phrase was supplied."""

    return normalize_trigger(text) in RUNTIME_ACTIVATION_TRIGGERS


def classify_call_phrase(text: str) -> str:
    """Classify exact C3P user phrases without starting anything.

    ``c3p`` and the bare council name intentionally remain ``ambiguous``:
    names identify a capability but never authorize a local process start.
    """

    phrase = normalize_trigger(text)
    if phrase in RUNTIME_ACTIVATION_TRIGGERS:
        return "runtime_activation"
    if phrase in BUDGET_SAVING_TRIGGERS:
        return "budget_saving_activation"
    if phrase in USER_ABSENCE_TRIGGERS:
        return "user_absence_activation"
    if phrase in MIA_C3P_REQUESTS:
        return "mia_c3p_request"
    if phrase in COUNCIL_REVIEW_REQUESTS:
        return "council_review_request"
    if phrase in {"c3p", "c3p 협의체", "c3p협의체"}:
        return "ambiguous"
    return "unknown"
