import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from csc_consensus import DecisionContext, evaluate_consensus


class TestConsensusPolicy(unittest.TestCase):
    def context(self, **overrides):
        values = {"risk": "LOW", "reversible": True, "requires_user_approval": False}
        values.update(overrides)
        return DecisionContext(**values)

    def test_all_three_yes_is_unanimous(self):
        result = evaluate_consensus(
            {"codex": "YES", "claude": "YES", "antigravity": "YES"}, {}, self.context()
        )
        self.assertEqual(result.status, "APPROVED_UNANIMOUS")

    def test_one_verified_quota_failure_allows_two_active_yes_for_low_risk(self):
        result = evaluate_consensus(
            {"codex": "YES", "claude": "PENDING", "antigravity": "YES"},
            {"claude": {"code": "quota_exhausted", "evidence": "session limit with reset time"}},
            self.context(),
        )
        self.assertEqual(result.status, "APPROVED_DEGRADED")
        self.assertEqual(result.mode, "2_OF_3_EMERGENCY")

    def test_timeout_alone_is_not_verified_unavailable(self):
        result = evaluate_consensus(
            {"codex": "YES", "claude": "PENDING", "antigravity": "YES"},
            {"claude": {"code": "timeout", "evidence": "120 seconds"}},
            self.context(),
        )
        self.assertEqual(result.status, "PENDING")

    def test_no_vote_cannot_be_relabelled_as_unavailable(self):
        result = evaluate_consensus(
            {"codex": "YES", "claude": "NO", "antigravity": "YES"},
            {"claude": {"code": "quota_exhausted", "evidence": "after voting no"}},
            self.context(),
        )
        self.assertEqual(result.status, "BLOCKED_DISSENT")

    def test_degraded_quorum_cannot_approve_high_risk_or_irreversible(self):
        votes = {"codex": "YES", "claude": "PENDING", "antigravity": "YES"}
        unavailable = {"claude": {"code": "quota_exhausted", "evidence": "429"}}
        self.assertEqual(
            evaluate_consensus(votes, unavailable, self.context(risk="HIGH")).status,
            "BLOCKED_SCOPE",
        )
        self.assertEqual(
            evaluate_consensus(votes, unavailable, self.context(reversible=False)).status,
            "BLOCKED_SCOPE",
        )

    def test_user_boundary_is_never_approved_by_agents(self):
        result = evaluate_consensus(
            {"codex": "YES", "claude": "YES", "antigravity": "YES"},
            {}, self.context(requires_user_approval=True),
        )
        self.assertEqual(result.status, "USER_APPROVAL_REQUIRED")

    def test_two_unavailable_has_no_mutation_quorum(self):
        result = evaluate_consensus(
            {"codex": "YES", "claude": "PENDING", "antigravity": "PENDING"},
            {
                "claude": {"code": "quota_exhausted", "evidence": "429"},
                "antigravity": {"code": "binary_missing", "evidence": "not found"},
            },
            self.context(),
        )
        self.assertEqual(result.status, "BLOCKED_NO_QUORUM")


if __name__ == "__main__":
    unittest.main()
