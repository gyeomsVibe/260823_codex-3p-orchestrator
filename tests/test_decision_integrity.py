"""실제 구성원의 표만 집계하고, 화면이 표결을 만들어내지 않도록 검증한다."""
import unittest

import csc_decide as decision
import csc_dashboard as dashboard


class DecisionIntegrityTests(unittest.TestCase):
    def test_unregistered_votes_cannot_create_quorum(self):
        with self.assertRaises(ValueError):
            decision.decide("candidate", {"ghost1": "AGREE", "ghost2": "AGREE"}, {})

    def test_unknown_member_is_rejected_even_with_valid_quorum(self):
        with self.assertRaises(ValueError):
            decision.decide("candidate", {"codex": "AGREE", "claude": "AGREE",
                                          "ghost": "ABSTAIN"}, {})

    def test_invalid_vote_cannot_hide_dissent(self):
        for value in ("reject", "YES", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decision.decide("candidate", {"codex": "AGREE", "claude": "AGREE",
                                              "antigravity": value}, {})

    def test_actual_dissent_still_blocks_majority(self):
        result = decision.decide("candidate", {"codex": "AGREE", "claude": "AGREE",
                                               "antigravity": "REJECT"}, {})
        self.assertEqual(result["decision"], "REJECTED")

    def test_dashboard_does_not_invent_current_topic_vote(self):
        for rows in ([], [{"sender": "claude", "timestamp": "2026-09-06T00:00:00Z",
                           "type": "RESULT", "body": "unrelated historical reply"}]):
            with self.subTest(rows=rows):
                item = next(item for item in dashboard.checks(rows, 0)
                            if item["title"] == "결정이 멈춰 있는가")
                self.assertEqual(item["value"], "판정 미검증")
                self.assertFalse(item["ok"])
                self.assertIn("queue.jsonl", item["src"])


if __name__ == "__main__":
    unittest.main()
