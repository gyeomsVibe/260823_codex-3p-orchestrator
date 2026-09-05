import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from csc_storage import persist_message
from csc_worker import QueueWorker, WorkerAlreadyRunning, _atomic_write_json, pid_is_alive


class TestQueueWorker(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_write_retries_transient_windows_share_violation(self):
        target = self.root / "worker.json"
        real_replace = os.replace
        attempts = []

        def flaky_replace(source, destination):
            attempts.append((source, destination))
            if len(attempts) == 1:
                raise PermissionError("transient Windows share violation")
            return real_replace(source, destination)

        with patch("csc_worker.os.replace", side_effect=flaky_replace), patch(
            "csc_worker.time.sleep"
        ) as sleeper:
            _atomic_write_json(target, {"status": "ready"})

        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "ready"})
        self.assertEqual(len(attempts), 2)
        sleeper.assert_called_once()

    def put(self, message_id, recipient="claude", body="task", correlation_id=None):
        message = {
            "message_id": message_id,
            "sender": "codex",
            "recipient": recipient,
            "type": "TASK",
            "body": body,
        }
        if correlation_id:
            message["correlation_id"] = correlation_id
        persist_message(message, base_dir=str(self.root / ".agent-swarm"))

    def executor(self, message):
        self.calls.append(message["message_id"])
        return "ok:" + message["message_id"]

    def records(self, path):
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_order_filter_correlation_and_restart_resume(self):
        self.put("T-1", correlation_id="C-1")
        self.put("T-OTHER", recipient="antigravity")
        self.put("T-ALL", recipient="all", correlation_id="C-ALL")
        worker = QueueWorker("claude", self.root, executor=self.executor)
        self.assertEqual(worker.process_available(), 2)
        self.assertEqual(self.calls, ["T-1", "T-ALL"])
        queue = self.records(self.root / ".agent-swarm/messages/queue.jsonl")
        results = [record for record in queue if record.get("type") == "RESULT"]
        self.assertEqual([r["correlation_id"] for r in results], ["C-1", "C-ALL"])

        restarted = QueueWorker("claude", self.root, executor=self.executor)
        self.assertEqual(restarted.process_available(), 0)
        self.assertEqual(self.calls, ["T-1", "T-ALL"])

    def test_duplicate_message_id_executes_once(self):
        queue = self.root / ".agent-swarm/messages/queue.jsonl"
        queue.parent.mkdir(parents=True)
        record = {"message_id": "DUP", "sender": "codex", "recipient": "claude", "type": "TASK", "body": "x"}
        queue.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n", encoding="utf-8")
        worker = QueueWorker("claude", self.root, executor=self.executor)
        self.assertEqual(worker.process_available(), 1)
        self.assertEqual(self.calls, ["DUP"])

    def test_poison_retries_then_dlq_and_does_not_block_next(self):
        self.put("BAD")
        self.put("GOOD")

        def failing(message):
            self.calls.append(message["message_id"])
            if message["message_id"] == "BAD":
                raise RuntimeError("poison")
            return "ok"

        worker = QueueWorker("claude", self.root, executor=failing, max_attempts=3)
        self.assertEqual(worker.process_available(), 0)
        self.assertEqual(worker.process_available(), 0)
        self.assertEqual(worker.process_available(), 2)
        self.assertEqual(self.calls, ["BAD", "BAD", "BAD", "GOOD"])
        dlq = self.records(self.root / ".agent-swarm/dead-letter/claude.jsonl")
        self.assertEqual(len(dlq), 1)
        self.assertEqual(dlq[0]["in_reply_to"], "BAD")

    def test_live_slot_rejected_stale_slot_replaced_and_heartbeat(self):
        worker = QueueWorker("claude", self.root, stale_after=60)
        worker.acquire()
        with self.assertRaises(WorkerAlreadyRunning):
            QueueWorker("claude", self.root, stale_after=60).acquire()
        first = json.loads(worker.metadata_path.read_text(encoding="utf-8"))
        time.sleep(0.01)
        worker.heartbeat()
        second = json.loads(worker.metadata_path.read_text(encoding="utf-8"))
        self.assertGreater(second["heartbeat_epoch"], first["heartbeat_epoch"])
        worker.release()

        # A cleanly stopped slot is immediately reusable even while the host
        # test process (and therefore its PID) is still alive.
        clean_restart = QueueWorker("claude", self.root, stale_after=60)
        clean_restart.acquire()
        clean_restart.release()

        _atomic_write_json(worker.metadata_path, {
            "agent": "claude", "pid": 99999999, "status": "ready", "heartbeat_epoch": 0
        })
        replacement = QueueWorker("claude", self.root, stale_after=60)
        replacement.acquire()
        metadata = json.loads(replacement.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["pid"], os.getpid())
        replacement.release()

    def test_verified_unavailable_becomes_blocked_without_retry_or_dlq(self):
        self.put("QUOTA")

        class QuotaError(RuntimeError):
            availability_code = "quota_exhausted"

        calls = []

        def unavailable(message):
            calls.append(message["message_id"])
            raise QuotaError("session limit with reset time")

        worker = QueueWorker("claude", self.root, executor=unavailable)
        self.assertEqual(worker.process_available(), 1)
        self.assertEqual(calls, ["QUOTA"])
        records = self.records(self.root / ".agent-swarm/messages/queue.jsonl")
        blocked = [record for record in records if record.get("type") == "BLOCKED"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["availability_code"], "quota_exhausted")
        self.assertFalse((self.root / ".agent-swarm/dead-letter/claude.jsonl").exists())
        self.assertEqual(worker.process_available(), 0)

    def test_pid_permission_denied_means_unknown_but_alive(self):
        with patch("csc_worker.os.kill", side_effect=PermissionError("denied")):
            self.assertTrue(pid_is_alive(12345))


if __name__ == "__main__":
    unittest.main()
