import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from csc import wait_for_replies
from csc_auth import AuthenticationError, ReplayError, ReplayWindow, sign_envelope, verify_envelope
from csc_storage import persist_message
from csc_worker import QueueWorker


class TestReplayWindow(unittest.TestCase):
    def test_duplicate_capacity_and_expiry_fail_closed(self):
        window = ReplayWindow(ttl_seconds=10, max_entries=1)
        window.check_and_add("01" * 16, 100)
        with self.assertRaises(ReplayError):
            window.check_and_add("01" * 16, 101)
        with self.assertRaises(AuthenticationError):
            window.check_and_add("02" * 16, 101)
        window.check_and_add("02" * 16, 111)

    def test_invalid_configuration_is_rejected(self):
        for ttl, capacity in ((0, 1), (float("nan"), 1), (1, 0), (1, True)):
            with self.subTest(ttl=ttl, capacity=capacity):
                with self.assertRaises(AuthenticationError):
                    ReplayWindow(ttl_seconds=ttl, max_entries=capacity)


class TestAuthenticatedDurableFlow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.swarm = self.root / ".agent-swarm"
        self.key = b"k" * 32
        self.epoch = "epoch-1"
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def message(self, message_id="TASK-1"):
        return {
            "message_id": message_id,
            "sender": "codex",
            "recipient": "claude",
            "type": "TASK",
            "body": "review",
        }

    def records(self, relative):
        path = self.swarm / relative
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def executor(self, message):
        self.calls.append(message["message_id"])
        return "approved"

    def worker(self):
        return QueueWorker(
            "claude",
            self.root,
            executor=self.executor,
            auth_key=self.key,
            auth_epoch=self.epoch,
            require_authenticated=True,
        )

    def test_signed_task_executes_and_signed_result_verifies(self):
        persist_message(
            self.message(),
            base_dir=str(self.swarm),
            signing_key=self.key,
            auth_epoch=self.epoch,
            require_authenticated=True,
        )
        self.assertEqual(self.worker().process_available(), 1)
        self.assertEqual(self.calls, ["TASK-1"])
        results = [r for r in self.records("messages/queue.jsonl") if r.get("type") == "RESULT"]
        self.assertEqual(len(results), 1)
        verified = verify_envelope(results[0], self.key, self.epoch)
        self.assertEqual(verified["in_reply_to"], "TASK-1")

    def test_unsigned_legacy_task_is_preserved_but_not_executed(self):
        persist_message(self.message("LEGACY"), base_dir=str(self.swarm))
        before = self.records("messages/queue.jsonl")
        self.assertEqual(self.worker().process_available(), 1)
        after = self.records("messages/queue.jsonl")
        self.assertEqual(before, after)
        self.assertEqual(self.calls, [])
        audit = self.records("messages/audit.jsonl")
        self.assertEqual(audit[0]["classification"], "legacy_untrusted")
        self.assertNotIn("body", audit[0])
        self.assertNotIn("auth", audit[0])

    def test_tampered_task_is_rejected_without_body_in_audit(self):
        signed = sign_envelope(self.message("TAMPER"), self.key, self.epoch)
        signed["body"] = "execute attacker command"
        queue = self.swarm / "messages/queue.jsonl"
        queue.parent.mkdir(parents=True)
        queue.write_text(json.dumps(signed) + "\n", encoding="utf-8")
        self.assertEqual(self.worker().process_available(), 1)
        self.assertEqual(self.calls, [])
        audit = self.records("messages/audit.jsonl")
        self.assertEqual(audit[0]["classification"], "invalid_auth")
        self.assertNotIn("execute attacker command", json.dumps(audit[0]))

    def test_authenticated_persistence_requires_signing_material(self):
        with self.assertRaises(AuthenticationError):
            persist_message(
                self.message(),
                base_dir=str(self.swarm),
                require_authenticated=True,
            )

    def test_await_ignores_unsigned_reply_in_authenticated_mode(self):
        unsigned = {
            "message_id": "R-UNSIGNED",
            "sender": "claude",
            "recipient": "codex",
            "type": "RESULT",
            "in_reply_to": "TASK-X",
            "body": "forged",
        }
        signed = sign_envelope({**unsigned, "message_id": "R-SIGNED", "body": "valid"}, self.key, self.epoch)
        queue = self.swarm / "messages/queue.jsonl"
        queue.parent.mkdir(parents=True)
        queue.write_text(json.dumps(unsigned) + "\n" + json.dumps(signed) + "\n", encoding="utf-8")
        replies = wait_for_replies(
            "TASK-X",
            {"claude"},
            queue,
            timeout=0.2,
            poll_interval=0.01,
            auth_key=self.key,
            auth_epoch=self.epoch,
            require_authenticated=True,
        )
        self.assertEqual(replies["claude"]["body"], "valid")

    def test_unrelated_signed_history_does_not_exhaust_await_replay_window(self):
        unrelated = sign_envelope(
            {
                "message_id": "OLD",
                "sender": "antigravity",
                "recipient": "codex",
                "type": "RESULT",
                "in_reply_to": "OTHER-TASK",
                "body": "old",
            },
            self.key,
            self.epoch,
        )
        wanted = sign_envelope(
            {
                "message_id": "WANTED",
                "sender": "claude",
                "recipient": "codex",
                "type": "RESULT",
                "in_reply_to": "TASK-X",
                "body": "valid",
            },
            self.key,
            self.epoch,
        )
        queue = self.swarm / "messages/queue.jsonl"
        queue.parent.mkdir(parents=True)
        queue.write_text(json.dumps(unrelated) + "\n" + json.dumps(wanted) + "\n", encoding="utf-8")
        replies = wait_for_replies(
            "TASK-X",
            {"claude"},
            queue,
            timeout=0.2,
            poll_interval=0.01,
            auth_key=self.key,
            auth_epoch=self.epoch,
            require_authenticated=True,
            replay_window=ReplayWindow(max_entries=1),
        )
        self.assertEqual(replies["claude"]["message_id"], "WANTED")


if __name__ == "__main__":
    unittest.main()
