"""C3P User-Absence Mode: State machine and bounded deliberation protocol.

This module is a pure, side-effect-free component. It contains no file I/O,
no network calls, and no active agent invocations.
"""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


class AbsenceModeState(str, enum.Enum):
    OFF = "OFF"
    ARMED = "ARMED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DECISION_READY = "DECISION_READY"
    IMPLEMENT_READY = "IMPLEMENT_READY"
    BLOCKED = "BLOCKED"
    NO_ACTIONABLE_CHANGE = "NO_ACTIONABLE_CHANGE"


class TerminalReason(str, enum.Enum):
    P2_BOUNDARY = "P2_BOUNDARY"
    MAX_MESSAGES_REACHED = "MAX_MESSAGES_REACHED"
    TIMEOUT_REACHED = "TIMEOUT_REACHED"
    DUPLICATE_HASH = "DUPLICATE_HASH"
    NO_NEW_EVIDENCE = "NO_NEW_EVIDENCE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    EXPLICIT_BLOCKED = "EXPLICIT_BLOCKED"
    SUCCESSFUL_DECISION = "SUCCESSFUL_DECISION"
    SUCCESSFUL_IMPLEMENT = "SUCCESSFUL_IMPLEMENT"
    NO_ACTIONABLE_CHANGE = "NO_ACTIONABLE_CHANGE"


# P2 boundary keywords that must trigger PAUSED immediately
P2_KEYWORDS: Set[str] = {
    "git commit",
    "git push",
    "pip install",
    "npm install",
    "rm -rf",
    "delete file",
    "drop table",
    "truncate table",
    ".env",
    "secret",
    "api_key",
    "token",
}


@dataclass(frozen=True)
class DeliberationMessage:
    step: int
    sender: str
    role: str  # "moderator" (Codex), "evidence" (Antigravity), "review" (Claude)
    content: str
    digest: str = field(default="")

    def __post_init__(self) -> None:
        if not self.digest:
            h = hashlib.sha256(self.content.strip().encode("utf-8")).hexdigest()[:16]
            object.__setattr__(self, "digest", h)


@dataclass
class AbsenceContext:
    agenda: Optional[str] = None
    is_ready: bool = False
    start_time_epoch: float = 0.0
    elapsed_seconds: float = 0.0
    messages: List[DeliberationMessage] = field(default_factory=list)
    seen_digests: Set[str] = field(default_factory=set)
    verification_exit_code: Optional[int] = None
    p2_detected: bool = False
    explicit_blocked_reason: Optional[str] = None
    max_messages: int = 5
    max_duration_seconds: float = 900.0  # 15 minutes


@dataclass(frozen=True)
class TransitionResult:
    current_state: AbsenceModeState
    next_state: AbsenceModeState
    reason: TerminalReason | str
    details: str
    action_required: str


@dataclass(frozen=True)
class AbsenceResultCard:
    status: AbsenceModeState
    reason: str
    what: str
    why: str
    user_action: str
    source_message_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "what": self.what,
            "why": self.why,
            "user_action": self.user_action,
            "source_message_id": self.source_message_id,
            "created_at": self.created_at,
        }


def check_p2_violation(text: str) -> bool:
    """Return True if text mentions any prohibited P2 boundary actions."""
    lower = text.lower()
    return any(keyword in lower for keyword in P2_KEYWORDS)


def can_arm_absence_mode(is_budget_saving_active: bool) -> bool:
    """ARMED state can be entered as long as budget saving mode is activated."""
    return is_budget_saving_active


def can_run_deliberation(is_ready: bool, agenda: Optional[str]) -> bool:
    """RUNNING state strictly requires READY status (2/2 live workers) and an agenda."""
    return bool(is_ready and agenda and agenda.strip())


def evaluate_transition(
    current_state: AbsenceModeState,
    context: AbsenceContext,
) -> TransitionResult:
    """Pure state machine evaluator for C3P User-Absence Mode."""
    # 1. Any P2 detection immediately forces PAUSED from any active state
    if context.p2_detected or (context.agenda and check_p2_violation(context.agenda)):
        return TransitionResult(
            current_state=current_state,
            next_state=AbsenceModeState.PAUSED,
            reason=TerminalReason.P2_BOUNDARY,
            details="P2 boundary action requested or detected in deliberation context.",
            action_required="사용자의 명시적 승인이 필요합니다.",
        )

    for msg in context.messages:
        if check_p2_violation(msg.content):
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.PAUSED,
                reason=TerminalReason.P2_BOUNDARY,
                details=f"P2 boundary detected in message from {msg.sender}.",
                action_required="사용자의 명시적 승인이 필요합니다.",
            )

    # 2. State transition rules
    if current_state == AbsenceModeState.OFF:
        if can_arm_absence_mode(True):
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.ARMED,
                reason="ARM_ACTIVATED",
                details="User-absence surveillance standby armed.",
                action_required="의제 대기 중입니다.",
            )
        return TransitionResult(
            current_state=current_state,
            next_state=AbsenceModeState.OFF,
            reason="REMAIN_OFF",
            details="Absence mode is disabled.",
            action_required="c3p 사용자부재 모드 활성화 필요",
        )

    if current_state == AbsenceModeState.ARMED:
        if can_run_deliberation(context.is_ready, context.agenda):
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.RUNNING,
                reason="READY_AND_AGENDA_PRESENT",
                details="Workers are strictly READY and agenda is supplied.",
                action_required="유한 토론회 진행",
            )
        return TransitionResult(
            current_state=current_state,
            next_state=AbsenceModeState.ARMED,
            reason="AWAITING_CONDITIONS",
            details="Surveillance standby: awaiting READY status or agenda.",
            action_required="대기",
        )

    if current_state == AbsenceModeState.RUNNING:
        # Check explicit blocker
        if context.explicit_blocked_reason:
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.BLOCKED,
                reason=TerminalReason.EXPLICIT_BLOCKED,
                details=context.explicit_blocked_reason,
                action_required="장애 요인 해결 필요",
            )

        # Check objective verification failure
        if context.verification_exit_code is not None and context.verification_exit_code != 0:
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.BLOCKED,
                reason=TerminalReason.VERIFICATION_FAILED,
                details=f"Objective verification failed with exit code {context.verification_exit_code}.",
                action_required="검증 실패 원인 분석 필요",
            )

        # Check message limit
        if len(context.messages) >= context.max_messages:
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.NO_ACTIONABLE_CHANGE,
                reason=TerminalReason.MAX_MESSAGES_REACHED,
                details=f"Bounded deliberation reached message limit ({context.max_messages}).",
                action_required="결과 카드 검토",
            )

        # Check timeout
        if context.elapsed_seconds > context.max_duration_seconds:
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.NO_ACTIONABLE_CHANGE,
                reason=TerminalReason.TIMEOUT_REACHED,
                details=f"Bounded deliberation reached timeout ({context.max_duration_seconds}s).",
                action_required="결과 카드 검토",
            )

        # Check duplicate logical message
        seen: Set[str] = set()
        for msg in context.messages:
            if msg.digest in seen:
                return TransitionResult(
                    current_state=current_state,
                    next_state=AbsenceModeState.NO_ACTIONABLE_CHANGE,
                    reason=TerminalReason.DUPLICATE_HASH,
                    details=f"Duplicate argument hash detected: {msg.digest}.",
                    action_required="중복 논의 차단 및 결과 카드 종결",
                )
            seen.add(msg.digest)

        # Check if successful consensus reached
        if any(msg.role == "moderator" and "IMPLEMENT_READY" in msg.content for msg in context.messages):
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.IMPLEMENT_READY,
                reason=TerminalReason.SUCCESSFUL_IMPLEMENT,
                details="Deliberation reached IMPLEMENT_READY consensus.",
                action_required="구현 카드 승인 대기",
            )

        if any(msg.role == "moderator" and "DECISION_READY" in msg.content for msg in context.messages):
            return TransitionResult(
                current_state=current_state,
                next_state=AbsenceModeState.DECISION_READY,
                reason=TerminalReason.SUCCESSFUL_DECISION,
                details="Deliberation reached DECISION_READY consensus.",
                action_required="결정 사항 사용자 확인",
            )

        # Deliberation still ongoing within bounds
        return TransitionResult(
            current_state=current_state,
            next_state=AbsenceModeState.RUNNING,
            reason="IN_PROGRESS",
            details=f"Deliberation active (msg_count={len(context.messages)}/{context.max_messages}).",
            action_required="다음 발언 진행",
        )

    # Terminal states remain stable unless explicitly reset
    return TransitionResult(
        current_state=current_state,
        next_state=current_state,
        reason="TERMINAL_STABLE",
        details=f"Remains in terminal state {current_state.value}.",
        action_required="사용자 확인",
    )


def build_result_card(
    status: AbsenceModeState,
    reason: str,
    what: str,
    why: str,
    user_action: str,
    source_message_id: Optional[str] = None,
) -> AbsenceResultCard:
    """Build a standard 3-part User-First result card."""
    return AbsenceResultCard(
        status=status,
        reason=reason,
        what=what,
        why=why,
        user_action=user_action,
        source_message_id=source_message_id,
    )
