"""Unit tests for C3P User-Absence Mode state machine and deliberation protocol."""

import unittest

from c3p_absence_mode import (
    AbsenceContext,
    AbsenceModeState,
    DeliberationMessage,
    TerminalReason,
    build_result_card,
    can_arm_absence_mode,
    can_run_deliberation,
    check_p2_violation,
    evaluate_transition,
    has_verified_consensus,
)


class TestC3PAbsenceMode(unittest.TestCase):
    def test_p2_violation_detection(self):
        self.assertTrue(check_p2_violation("We need to run git commit -m 'update'"))
        self.assertTrue(check_p2_violation("Please execute GIT PUSH origin main"))
        self.assertTrue(check_p2_violation("Install pip install requests now"))
        self.assertTrue(check_p2_violation("Check the .env file credentials"))
        self.assertFalse(check_p2_violation("Let us read the documentation and plan"))

    def test_arming_conditions(self):
        self.assertTrue(can_arm_absence_mode(is_budget_saving_active=True))
        self.assertFalse(can_arm_absence_mode(is_budget_saving_active=False))

    def test_running_conditions(self):
        self.assertFalse(can_run_deliberation(is_ready=False, agenda="Some agenda"))
        self.assertFalse(can_run_deliberation(is_ready=True, agenda=None))
        self.assertFalse(can_run_deliberation(is_ready=True, agenda="   "))
        self.assertTrue(can_run_deliberation(is_ready=True, agenda="Valid agenda"))

    def test_transition_off_to_armed(self):
        ctx = AbsenceContext(is_budget_saving_active=True)
        res = evaluate_transition(AbsenceModeState.OFF, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.ARMED)

    def test_transition_off_stays_off_without_budget_saving_mode(self):
        res = evaluate_transition(AbsenceModeState.OFF, AbsenceContext())
        self.assertEqual(res.next_state, AbsenceModeState.OFF)

    def test_transition_armed_stays_armed_when_not_ready(self):
        ctx = AbsenceContext(is_ready=False, agenda="Optimize cache")
        res = evaluate_transition(AbsenceModeState.ARMED, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.ARMED)

    def test_transition_armed_stays_armed_when_no_agenda(self):
        ctx = AbsenceContext(is_ready=True, agenda=None)
        res = evaluate_transition(AbsenceModeState.ARMED, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.ARMED)

    def test_transition_armed_to_running(self):
        ctx = AbsenceContext(is_ready=True, agenda="Optimize cache")
        res = evaluate_transition(AbsenceModeState.ARMED, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.RUNNING)

    def test_p2_in_agenda_forces_paused(self):
        ctx = AbsenceContext(is_ready=True, agenda="Please git push the new feature")
        res = evaluate_transition(AbsenceModeState.ARMED, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.PAUSED)
        self.assertEqual(res.reason, TerminalReason.P2_BOUNDARY)

    def test_p2_in_message_forces_paused(self):
        ctx = AbsenceContext(
            is_ready=True,
            agenda="Refactor",
            messages=[
                DeliberationMessage(
                    step=1,
                    sender="antigravity",
                    role="evidence",
                    content="We should run git commit immediately",
                )
            ],
        )
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.PAUSED)
        self.assertEqual(res.reason, TerminalReason.P2_BOUNDARY)

    def test_explicit_blocked_reason(self):
        ctx = AbsenceContext(
            is_ready=True,
            agenda="Refactor",
            explicit_blocked_reason="Upstream provider quota exhausted",
        )
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.BLOCKED)
        self.assertEqual(res.reason, TerminalReason.EXPLICIT_BLOCKED)

    def test_verification_failure_blocks(self):
        ctx = AbsenceContext(
            is_ready=True,
            agenda="Refactor",
            verification_exit_code=1,
        )
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.BLOCKED)
        self.assertEqual(res.reason, TerminalReason.VERIFICATION_FAILED)

    def test_max_messages_reached(self):
        msgs = [
            DeliberationMessage(step=i, sender=f"agent_{i}", role="test", content=f"Step {i}")
            for i in range(5)
        ]
        ctx = AbsenceContext(is_ready=True, agenda="Review", messages=msgs, max_messages=5)
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.NO_ACTIONABLE_CHANGE)
        self.assertEqual(res.reason, TerminalReason.MAX_MESSAGES_REACHED)

    def test_timeout_reached(self):
        ctx = AbsenceContext(
            is_ready=True,
            agenda="Review",
            elapsed_seconds=950.0,
            max_duration_seconds=900.0,
        )
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.NO_ACTIONABLE_CHANGE)
        self.assertEqual(res.reason, TerminalReason.TIMEOUT_REACHED)

    def test_duplicate_argument_hash_stops(self):
        msgs = [
            DeliberationMessage(step=1, sender="codex", role="moderator", content="Identical point"),
            DeliberationMessage(step=2, sender="codex", role="moderator", content="Identical point"),
        ]
        ctx = AbsenceContext(is_ready=True, agenda="Review", messages=msgs)
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.NO_ACTIONABLE_CHANGE)
        self.assertEqual(res.reason, TerminalReason.DUPLICATE_HASH)

    def test_identical_arguments_from_distinct_senders_are_not_duplicates(self):
        msgs = [
            DeliberationMessage(step=1, sender="codex", role="moderator", content="Same point"),
            DeliberationMessage(step=2, sender="antigravity", role="evidence", content="Same point"),
        ]
        ctx = AbsenceContext(is_ready=True, agenda="Review", messages=msgs)
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.RUNNING)

    def test_consensus_requires_structured_results_from_all_members(self):
        messages = [
            DeliberationMessage(
                step=1, sender=sender, role="review", content="IMPLEMENT_READY is discussed",
                correlation_id="C-1", decision="IMPLEMENT_READY",
            )
            for sender in ("codex", "claude", "antigravity")
        ]
        self.assertTrue(
            has_verified_consensus(messages, {"codex", "claude", "antigravity"}, "C-1", "IMPLEMENT_READY")
        )
        self.assertFalse(
            has_verified_consensus(messages[:-1], {"codex", "claude", "antigravity"}, "C-1", "IMPLEMENT_READY")
        )

    def test_consensus_implement_ready(self):
        msgs = [
            DeliberationMessage(step=index, sender=sender, role="review", content="Approved.",
                               correlation_id="C-IMPLEMENT", decision="IMPLEMENT_READY")
            for index, sender in enumerate(("codex", "claude", "antigravity"), 1)
        ]
        ctx = AbsenceContext(is_ready=True, agenda="Review", messages=msgs, correlation_id="C-IMPLEMENT")
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.IMPLEMENT_READY)
        self.assertEqual(res.reason, TerminalReason.SUCCESSFUL_IMPLEMENT)

    def test_consensus_decision_ready(self):
        msgs = [
            DeliberationMessage(step=index, sender=sender, role="review", content="Approved.",
                               correlation_id="C-DECISION", decision="DECISION_READY")
            for index, sender in enumerate(("codex", "claude", "antigravity"), 1)
        ]
        ctx = AbsenceContext(is_ready=True, agenda="Review", messages=msgs, correlation_id="C-DECISION")
        res = evaluate_transition(AbsenceModeState.RUNNING, ctx)
        self.assertEqual(res.next_state, AbsenceModeState.DECISION_READY)
        self.assertEqual(res.reason, TerminalReason.SUCCESSFUL_DECISION)

    def test_build_result_card(self):
        card = build_result_card(
            status=AbsenceModeState.IMPLEMENT_READY,
            reason="Consensus reached",
            what="새 트리거 연계 카드 생성",
            why="단위 테스트 100% 통과 및 설계 기준 부합",
            user_action="구현 변경 사항 승인",
            source_message_id="MSG-12345",
        )
        data = card.to_dict()
        self.assertEqual(data["status"], "IMPLEMENT_READY")
        self.assertEqual(data["what"], "새 트리거 연계 카드 생성")
        self.assertEqual(data["source_message_id"], "MSG-12345")


if __name__ == "__main__":
    unittest.main()
