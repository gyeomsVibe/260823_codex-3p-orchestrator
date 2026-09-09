import unittest

from model_runtime_routing import (
    QuotaObservation,
    RuntimeMode,
    consume_unique_logical_replies,
    resolve_runtime_mode,
    route_with_observation,
)


def profile(**overrides):
    data = {
        "task_id": "T-OBS",
        "platform": "codex",
        "task_kind": "lookup",
        "risk": "low",
        "quota_state": "normal",
        "read_only": True,
        "verifiable": True,
        "requirements_clear": True,
        "affected_items": 1,
    }
    data.update(overrides)
    return data


def observation(state="normal"):
    return QuotaObservation(
        source="provider",
        state=state,
        observed_at="2026-09-09T08:00:00Z",
        evidence="provider quota response",
    )


class ModelRuntimeObservationTests(unittest.TestCase):
    def test_observation_rejects_missing_evidence_non_utc_and_unknown_state(self):
        invalid = (
            {"evidence": " "},
            {"observed_at": "2026-09-09T08:00:00"},
            {"state": "unknown"},
            {"source": "socket"},
            {"state": ["normal"]},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                QuotaObservation(
                    source=overrides.get("source", "provider"),
                    state=overrides.get("state", "normal"),
                    observed_at=overrides.get("observed_at", "2026-09-09T08:00:00Z"),
                    evidence=overrides.get("evidence", "provider response"),
                )

    def test_none_observation_uses_existing_unknown_single_attempt_policy(self):
        decision = route_with_observation(profile(), None)
        self.assertIn("UNKNOWN_QUOTA_SINGLE_ATTEMPT", decision.reason_codes)
        self.assertEqual(1, decision.max_attempts)
        self.assertEqual(1, decision.max_parallel)
        self.assertEqual(RuntimeMode.NORMAL, resolve_runtime_mode(None))

    def test_runtime_mode_transitions_are_explicit(self):
        self.assertEqual(RuntimeMode.NORMAL, resolve_runtime_mode(observation("normal")))
        self.assertEqual(RuntimeMode.BUDGET, resolve_runtime_mode(observation("constrained")))
        self.assertEqual(RuntimeMode.CRITICAL, resolve_runtime_mode(observation("exhausted")))

    def test_constrained_high_risk_never_downgrades(self):
        decision = route_with_observation(
            profile(task_kind="security", risk="high"), observation("constrained")
        )
        self.assertEqual("DEFER_OR_EQUIVALENT_FALLBACK", decision.status)
        self.assertIsNone(decision.model)

    def test_policy_disabled_preserves_observation_and_rollback_restores_policy(self):
        constrained = observation("constrained")
        safe_balanced = profile(task_kind="bulk_evidence", affected_items=6)
        disabled = route_with_observation(safe_balanced, constrained, policy_disabled=True)
        restored = route_with_observation(safe_balanced, constrained)

        self.assertEqual("constrained", constrained.state)
        self.assertEqual("READY", disabled.status)
        self.assertEqual("READY", restored.status)
        self.assertEqual("balanced", disabled.selected_tier)
        self.assertEqual("economy", restored.selected_tier)
        self.assertEqual(RuntimeMode.NORMAL, resolve_runtime_mode(constrained, policy_disabled=True))
        self.assertEqual(RuntimeMode.BUDGET, resolve_runtime_mode(constrained))

    def test_exhausted_observation_blocks_even_when_policy_disabled(self):
        exhausted = observation("exhausted")
        safe_balanced = profile(task_kind="bulk_evidence", affected_items=6)
        decision = route_with_observation(safe_balanced, exhausted, policy_disabled=True)

        self.assertEqual("BLOCKED", decision.status)
        self.assertIn("QUOTA_EXHAUSTED", decision.reason_codes)
        self.assertEqual(RuntimeMode.CRITICAL, resolve_runtime_mode(exhausted, policy_disabled=True))
        self.assertEqual(RuntimeMode.CRITICAL, resolve_runtime_mode(exhausted))

    def test_logical_replies_are_consumed_once_without_removing_raw_records(self):
        raw = [
            {"message_id": "M1", "sender": "claude", "in_reply_to": "T1", "correlation_id": "C1", "body": "agree"},
            {"message_id": "M2", "sender": "claude", "in_reply_to": "T1", "correlation_id": "C1", "body": "agree"},
            {"message_id": "M3", "sender": "claude", "in_reply_to": "T1", "correlation_id": "C1", "body": "different"},
        ]
        unique = consume_unique_logical_replies(raw)
        self.assertEqual(["M1", "M3"], [item["message_id"] for item in unique])
        self.assertEqual(3, len(raw))

    def test_logical_replies_preserve_distinct_senders_with_identical_body(self):
        raw = [
            {"message_id": "M1", "sender": "claude", "in_reply_to": "T1", "correlation_id": "C1", "body": "agree"},
            {"message_id": "M2", "sender": "antigravity", "in_reply_to": "T1", "correlation_id": "C1", "body": "agree"},
            {"message_id": "M3", "sender": "claude", "in_reply_to": "T1", "correlation_id": "C1", "body": "agree"},
        ]
        unique = consume_unique_logical_replies(raw)
        self.assertEqual(["M1", "M2"], [item["message_id"] for item in unique])
        self.assertEqual(3, len(raw))


if __name__ == "__main__":
    unittest.main()
