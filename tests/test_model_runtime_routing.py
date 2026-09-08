import json
import tempfile
import unittest
from pathlib import Path

from model_runtime_routing.policy import (
    RoutingError,
    build_launch_args,
    load_catalog,
    route_task,
)


def profile(**overrides):
    base = {
        "task_id": "T-1",
        "platform": "codex",
        "task_kind": "lookup",
        "risk": "low",
        "quota_state": "normal",
        "read_only": True,
        "verifiable": True,
        "requirements_clear": True,
        "affected_items": 1,
    }
    base.update(overrides)
    return base


class ModelRoutingTests(unittest.TestCase):
    def test_small_clear_lookup_uses_economy(self):
        decision = route_task(profile())
        self.assertEqual("economy", decision.selected_tier)
        self.assertEqual("gpt-5.4-mini", decision.model)

    def test_high_risk_uses_frontier(self):
        decision = route_task(profile(task_kind="authentication", risk="high"))
        self.assertEqual("frontier", decision.selected_tier)
        self.assertEqual("gpt-6-astra", decision.model)

    def test_constrained_high_risk_never_downgrades(self):
        decision = route_task(
            profile(task_kind="security", risk="high", quota_state="constrained")
        )
        self.assertEqual("DEFER_OR_EQUIVALENT_FALLBACK", decision.status)
        self.assertIsNone(decision.model)

    def test_constrained_safe_balanced_work_can_downgrade(self):
        decision = route_task(
            profile(task_kind="bulk_evidence", affected_items=6, quota_state="constrained")
        )
        self.assertEqual("economy", decision.selected_tier)
        self.assertEqual(1, decision.max_attempts)

    def test_unknown_quota_forces_single_serial_attempt(self):
        decision = route_task(profile(quota_state="unknown"))
        self.assertEqual(1, decision.max_attempts)
        self.assertEqual(1, decision.max_parallel)
        self.assertEqual(1, decision.max_escalations)
        self.assertEqual(
            "MARK_CONSTRAINED_ON_EXPLICIT_QUOTA_SIGNAL",
            decision.quota_failure_transition,
        )
        self.assertEqual(
            "PROVIDER_RETRY_AFTER_OR_NEXT_REAL_TASK_AS_SINGLE_PROBE",
            decision.quota_reprobe,
        )
        self.assertIn("UNKNOWN_QUOTA_SINGLE_ATTEMPT", decision.reason_codes)

    def test_exhausted_quota_blocks(self):
        decision = route_task(profile(quota_state="exhausted"))
        self.assertEqual("BLOCKED", decision.status)
        self.assertEqual(0, decision.max_attempts)
        self.assertEqual(0, decision.max_escalations)
        with self.assertRaises(RoutingError):
            build_launch_args(decision)

    def test_cross_platform_change_uses_strong(self):
        decision = route_task(profile(cross_platform=True))
        self.assertEqual("strong", decision.selected_tier)

    def test_escalation_is_limited_to_one_tier_once(self):
        decision = route_task(profile(task_kind="routine_edit", read_only=False))
        self.assertEqual("strong", decision.escalation_tier)
        self.assertEqual(1, decision.max_escalations)

    def test_frontier_has_no_further_escalation(self):
        decision = route_task(profile(task_kind="security", risk="high"))
        self.assertIsNone(decision.escalation_tier)
        self.assertEqual(0, decision.max_escalations)

    def test_platform_launch_arguments_are_explicit(self):
        claude = route_task(profile(platform="claude"))
        antigravity = route_task(profile(platform="antigravity"))
        self.assertEqual(
            ["claude", "--model", "haiku", "--effort", "low"],
            build_launch_args(claude),
        )
        self.assertEqual(
            ["agy", "--model", "gemini-3.8-flash-low", "--effort", "low"],
            build_launch_args(antigravity),
        )

    def test_invalid_boolean_is_rejected(self):
        with self.assertRaises(RoutingError):
            route_task(profile(read_only="yes"))

    def test_catalog_schema_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            path.write_text(json.dumps({"schema_version": "bad"}), encoding="utf-8")
            with self.assertRaises(RoutingError):
                load_catalog(path)


if __name__ == "__main__":
    unittest.main()
