"""Deterministic recognition of explicit C3P budget-saving activation phrases.

Natural-language hosts decide when to call this module.  The matcher itself is
intentionally exact after whitespace and ASCII-case normalization, so a
discussion *about* budget saving cannot silently activate local processes.
"""

from __future__ import annotations

import unicodedata

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
    """Normalize only whitespace and case; do not infer activation intent."""

    if not isinstance(text, str):
        raise TypeError("trigger text must be a string")
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def is_budget_saving_trigger(text: str) -> bool:
    """Return whether *text* is an explicit budget-saving activation phrase."""

    return normalize_trigger(text) in BUDGET_SAVING_TRIGGERS


def is_user_absence_trigger(text: str) -> bool:
    """Return whether *text* is an explicit user-absence mode activation phrase."""

    return normalize_trigger(text) in USER_ABSENCE_TRIGGERS
