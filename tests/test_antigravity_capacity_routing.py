import hashlib
import tempfile
import unittest
from pathlib import Path

from antigravity_capacity_routing import evaluate_pilot, route_task, validate_evidence_packet


def profile(**changes):
    value = {
        "task_id": "task-1",
        "task_kind": "research",
        "risk": "low",
        "read_only": True,
        "independent": True,
        "verifiable": True,
        "shared_write": False,
        "external_side_effect": False,
        "judgment_required": False,
        "bulk_work": True,
        "parallel_units": 3,
    }
    value.update(changes)
    return value


def metrics(**changes):
    value = {
        "codex_tokens": 600,
        "claude_tokens": 400,
        "antigravity_tokens": 0,
        "wall_seconds": 100,
        "review_minutes": 20,
        "critical_defects": 0,
        "major_defects": 1,
        "verified_findings": 4,
        "workspace_mutations": 0,
        "permission_bypasses": 0,
        "invalid_packets": 0,
        "total_packets": 1,
        "quota_failures": 0,
    }
    value.update(changes)
    return value


POLICY = {
    "min_scarce_token_reduction_pct": 30,
    "max_wall_time_increase_pct": 20,
    "max_total_token_multiplier": 5,
    "min_valid_packet_rate": 1.0,
}


class RoutingTests(unittest.TestCase):
    def test_bulk_independent_research_uses_three_antigravity_lanes(self):
        result = route_task(profile())
        self.assertEqual(result["route"], "ANTIGRAVITY_FIRST")
        self.assertEqual(result["antigravity_lanes"], 3)
        self.assertEqual(result["claude_mode"], "COMPACT_SENTINEL")
        self.assertEqual(result["council_participants"], ["codex", "claude", "antigravity"])

    def test_dependent_reading_is_one_sequential_lane(self):
        result = route_task(profile(independent=False, parallel_units=8))
        self.assertEqual(result["route"], "ANTIGRAVITY_FIRST")
        self.assertEqual(result["antigravity_lanes"], 1)

    def test_high_risk_shared_write_never_routes_to_antigravity(self):
        result = route_task(profile(
            task_kind="authentication", risk="high", read_only=False,
            shared_write=True, judgment_required=True,
        ))
        self.assertEqual(result["route"], "SCARCE_CONTROLLED")
        self.assertEqual(result["antigravity_lanes"], 0)
        self.assertEqual(result["claude_mode"], "FULL_REVIEW")
        self.assertEqual(result["antigravity_mode"], "ADVISORY_ONLY")


class EvidenceTests(unittest.TestCase):
    def test_file_anchor_hash_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
            digest = hashlib.sha256(b"beta\ngamma").hexdigest()
            packet = {
                "schema_version": "c3p-evidence-v1",
                "task_id": "task-1",
                "lane_id": "lane-1",
                "status": "COMPLETED",
                "read_only": True,
                "claims": [{
                    "claim_id": "claim-1",
                    "text": "The last two lines are beta and gamma.",
                    "locator": {
                        "type": "file", "path": "sample.txt",
                        "line_start": 2, "line_end": 3, "sha256": digest,
                    },
                }],
            }
            result = validate_evidence_packet(packet, root)
            self.assertEqual(result["status"], "VALID")
            self.assertEqual(result["deterministic_claims"], 1)

    def test_path_escape_is_rejected(self):
        packet = {
            "schema_version": "c3p-evidence-v1",
            "task_id": "task-1",
            "lane_id": "lane-1",
            "status": "COMPLETED",
            "read_only": True,
            "claims": [{
                "claim_id": "claim-1",
                "text": "outside",
                "locator": {
                    "type": "file", "path": "../outside.txt",
                    "line_start": 1, "line_end": 1, "sha256": "0" * 64,
                },
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_evidence_packet(packet, tmp)
        self.assertEqual(result["status"], "ESCALATE")
        self.assertTrue(any("escapes" in error for error in result["errors"]))

    def test_url_anchor_requires_sample_review(self):
        packet = {
            "schema_version": "c3p-evidence-v1",
            "task_id": "task-1",
            "lane_id": "lane-1",
            "status": "COMPLETED",
            "read_only": True,
            "claims": [{
                "claim_id": "claim-1",
                "text": "A source-backed research claim.",
                "locator": {
                    "type": "url", "url": "https://example.com/source",
                    "excerpt": "A short supporting excerpt.",
                },
            }],
        }
        result = validate_evidence_packet(packet, ".")
        self.assertEqual(result["status"], "SAMPLE_REVIEW")
        self.assertEqual(result["sample_review_claims"], 1)

    def test_missing_claim_id_escalates(self):
        packet = {
            "schema_version": "c3p-evidence-v1",
            "task_id": "task-1",
            "lane_id": "lane-1",
            "status": "COMPLETED",
            "read_only": True,
            "claims": [{
                "text": "A source-backed research claim.",
                "locator": {
                    "type": "url", "url": "https://example.com/source",
                    "excerpt": "A short supporting excerpt.",
                },
            }],
        }
        result = validate_evidence_packet(packet, ".")
        self.assertEqual(result["status"], "ESCALATE")
        self.assertTrue(any("claim_id" in error for error in result["errors"]))


class PilotEvaluationTests(unittest.TestCase):
    def test_scale_requires_quality_and_efficiency_to_pass_together(self):
        candidate = metrics(
            codex_tokens=350, claude_tokens=300, antigravity_tokens=4000,
            wall_seconds=115, review_minutes=15, major_defects=1,
            verified_findings=5,
        )
        result = evaluate_pilot(metrics(), candidate, POLICY)
        self.assertEqual(result["decision"], "SCALE")
        self.assertEqual(result["scarce_token_reduction_pct"], 35.0)

    def test_total_token_cap_blocks_abundant_quota_waste(self):
        candidate = metrics(
            codex_tokens=100, claude_tokens=100, antigravity_tokens=6000,
            wall_seconds=110, review_minutes=10, verified_findings=5,
        )
        result = evaluate_pilot(metrics(), candidate, POLICY)
        self.assertEqual(result["decision"], "ITERATE")
        self.assertFalse(result["checks"]["total_token_budget"])

    def test_quality_regression_stops_even_when_scarce_tokens_fall(self):
        candidate = metrics(
            codex_tokens=100, claude_tokens=100, antigravity_tokens=9000,
            critical_defects=1,
        )
        result = evaluate_pilot(metrics(), candidate, POLICY)
        self.assertEqual(result["decision"], "STOP")
        self.assertFalse(result["checks"]["quality"])

    def test_efficiency_miss_iterates_when_quality_and_safety_hold(self):
        candidate = metrics(codex_tokens=500, claude_tokens=400)
        result = evaluate_pilot(metrics(), candidate, POLICY)
        self.assertEqual(result["decision"], "ITERATE")
        self.assertFalse(result["checks"]["scarce_tokens"])


if __name__ == "__main__":
    unittest.main()
