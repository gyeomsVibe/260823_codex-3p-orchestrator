import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from csc_runtime import ActivationError, activate, ensure_worker, worker_is_fresh


class FakeProcess:
    def __init__(self, pid):
        self.pid = pid


class TestCscRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-swarm/workers").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def write_worker(self, agent, pid=None, status="ready", age=0):
        data = {
            "agent": agent,
            "pid": os.getpid() if pid is None else pid,
            "status": status,
            "heartbeat_epoch": time.time() - age,
        }
        (self.root / f".agent-swarm/workers/{agent}.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def test_ensure_worker_reuses_fresh_live_process(self):
        self.write_worker("claude")
        popen = Mock()
        result = ensure_worker("claude", self.root, popen_factory=popen)
        self.assertEqual(result["action"], "reused")
        popen.assert_not_called()

    def test_ensure_worker_starts_when_metadata_is_stale(self):
        self.write_worker("claude", pid=99999999, age=999)
        popen = Mock(return_value=FakeProcess(5555))
        result = ensure_worker("claude", self.root, popen_factory=popen)
        self.assertEqual(result, {"agent": "claude", "action": "started", "pid": 5555})
        popen.assert_called_once()

    def test_new_worker_starts_at_current_queue_end(self):
        queue = self.root / ".agent-swarm/messages/queue.jsonl"
        queue.parent.mkdir(parents=True)
        queue.write_text('{"type":"TASK","body":"stale"}\n', encoding="utf-8")
        popen = Mock(return_value=FakeProcess(5555))

        ensure_worker("claude", self.root, popen_factory=popen)

        cursor = json.loads(
            (self.root / ".agent-swarm/workers/claude.cursor.json").read_text(encoding="utf-8")
        )
        self.assertEqual(cursor["offset"], queue.stat().st_size)
        self.assertEqual(cursor["processed_ids"], [])

    def test_worker_fresh_requires_live_pid_ready_and_recent_heartbeat(self):
        self.write_worker("claude")
        self.assertTrue(worker_is_fresh("claude", self.root, stale_after=30))
        self.write_worker("claude", status="stopped")
        self.assertFalse(worker_is_fresh("claude", self.root, stale_after=30))
        self.write_worker("claude", age=31)
        self.assertFalse(worker_is_fresh("claude", self.root, stale_after=30))

    @patch("csc_runtime.ensure_worker")
    @patch("csc_runtime.ensure_broker")
    @patch("csc_runtime.query_roster")
    @patch("csc_runtime.worker_is_fresh")
    def test_activate_requires_roster_and_fresh_heartbeat(
        self, fresh, roster, broker, worker
    ):
        broker.return_value = {"action": "reused", "pid": 1}
        worker.side_effect = [
            {"agent": "claude", "action": "started", "pid": 2},
            {"agent": "antigravity", "action": "started", "pid": 3},
        ]
        roster.return_value = {"registered_agents": ["claude", "antigravity"]}
        fresh.return_value = True
        result = activate(self.root, timeout=0.2, poll_interval=0.01)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(set(result["registered_agents"]), {"claude", "antigravity"})

    @patch("csc_runtime.ensure_worker")
    @patch("csc_runtime.ensure_broker")
    @patch("csc_runtime.query_roster")
    @patch("csc_runtime.worker_is_fresh")
    def test_activate_fails_when_socket_registration_never_appears(
        self, fresh, roster, broker, worker
    ):
        broker.return_value = {"action": "reused", "pid": 1}
        worker.return_value = {"action": "reused", "pid": 2}
        roster.return_value = {"registered_agents": ["claude"]}
        fresh.return_value = True
        with self.assertRaises(ActivationError):
            activate(self.root, timeout=0.03, poll_interval=0.01)


if __name__ == "__main__":
    unittest.main()
