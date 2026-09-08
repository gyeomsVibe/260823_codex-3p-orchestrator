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

from csc_auth import verify_envelope
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
        self.assertTrue(dlq[0].get("blocked_id", "").startswith("BLOCKED-"))

        queue = self.records(self.root / ".agent-swarm/messages/queue.jsonl")
        blocked = [r for r in queue if r.get("type") == "BLOCKED"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["message_id"], dlq[0]["blocked_id"])
        self.assertEqual(blocked[0]["in_reply_to"], "BAD")
        self.assertEqual(blocked[0]["failure_code"], "retry_exhausted")

    def test_authenticated_retry_exhaustion_emits_signed_blocked(self):
        auth_key = b"k" * 32
        auth_epoch = "epoch-1"

        def failing(message):
            raise RuntimeError("authenticated poison")

        worker = QueueWorker(
            "claude",
            self.root,
            executor=failing,
            max_attempts=1,
            auth_key=auth_key,
            auth_epoch=auth_epoch,
            require_authenticated=True,
        )
        persist_message(
            {
                "message_id": "AUTH-POISON",
                "sender": "codex",
                "recipient": "claude",
                "type": "TASK",
                "body": "fail me",
            },
            base_dir=str(self.root / ".agent-swarm"),
            signing_key=auth_key,
            auth_epoch=auth_epoch,
            require_authenticated=True,
        )

        self.assertEqual(worker.process_available(), 1)

        dlq = self.records(self.root / ".agent-swarm/dead-letter/claude.jsonl")
        self.assertEqual(len(dlq), 1)
        self.assertEqual(dlq[0]["in_reply_to"], "AUTH-POISON")
        blocked_id = dlq[0]["blocked_id"]

        queue = self.records(self.root / ".agent-swarm/messages/queue.jsonl")
        blocked = [r for r in queue if r.get("type") == "BLOCKED"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["message_id"], blocked_id)
        self.assertEqual(blocked[0]["failure_code"], "retry_exhausted")

        # Must verify against the auth key and epoch
        verified = verify_envelope(blocked[0], auth_key, auth_epoch)
        self.assertEqual(verified["message_id"], blocked_id)

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
        """'모른다' 를 '죽었다' 로 바꾸지 않는다 — 이 불변식이 거짓 사망 보고를 막는다.

        수정 경위 (2026-09-06): 이 테스트는 `csc_worker.os.kill` 을 패치했으나
        실행 경로에 닿지 못해 Windows 에서 실패했다. 이유가 두 가지다.
          1. 생존 판정은 `csc_process.probe_pid` 로 옮겨졌고, Windows 에서는
             `os.kill` 대신 Win32 OpenProcess 분기를 탄다.
          2. `csc_worker` 는 `from csc_process import probe_pid` 로 이름을 직접
             묶으므로, 원본 모듈을 패치해도 이미 묶인 이름은 바뀌지 않는다.

        지켜야 할 계약은 플랫폼과 무관하다 — gone 만 사망이고 unknown 은 아니다.
        그래서 실제 이음매(`csc_worker.probe_pid`)에서 그 계약을 검증한다.
        """
        for state, expected in (("alive", True), ("unknown", True), ("gone", False)):
            with self.subTest(state=state):
                with patch("csc_worker.probe_pid", return_value=state):
                    self.assertIs(pid_is_alive(12345), expected)

    @unittest.skipIf(sys.platform == "win32", "Windows 는 os.kill 분기를 타지 않는다")
    def test_posix_permission_denied_maps_to_unknown(self):
        """POSIX 에서 권한 거부는 '존재하지만 볼 수 없다' 이지 부재가 아니다."""
        from csc_process import probe_pid as raw_probe
        with patch("csc_process.os.kill", side_effect=PermissionError("denied")):
            self.assertEqual(raw_probe(12345), "unknown")
        with patch("csc_process.os.kill", side_effect=ProcessLookupError()):
            self.assertEqual(raw_probe(12345), "gone")


if __name__ == "__main__":
    unittest.main()
