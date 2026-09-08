import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from csc_agent_worker import AgentUnavailable, BoundedCliExecutor, RegisteredQueueWorker
from csc_broker import SwarmBroker
from csc_storage import persist_message


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeProcess:
    def __init__(self, returncode=0, stdout="OK", stderr="", timeout=False, pid=43210):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = timeout
        self.pid = pid

    def communicate(self, timeout=None):
        if self.timeout:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.stdout, self.stderr


class TestBoundedCliExecutor(unittest.TestCase):
    def test_claude_command_is_noninteractive_and_has_no_edit_tools(self):
        popen = Mock(return_value=FakeProcess(stdout="review ok"))
        rules = PROJECT_ROOT / "CLAUDE.md"
        executor = BoundedCliExecutor(
            "claude", PROJECT_ROOT, popen_factory=popen, claude_rules_path=rules,
        )
        self.assertEqual(executor({"message_id": "T1", "body": "review"}), "review ok")
        command = popen.call_args.args[0]
        self.assertIn("--permission-mode", command)
        self.assertIn("plan", command)
        self.assertIn("--restricted", command)
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertEqual(
            command[command.index("--append-system-prompt-file") + 1],
            str(rules.resolve()),
        )

        # 계약 변경 (2026-09-05): --tools "" -> --allowed-tools "Read,Grep,Glob"
        #
        # 왜 바꿨나: 도구를 전부 막은 채 "파일을 읽고 검토하라"고 지시했더니
        # 모델이 "못 읽는다"고 말하지 않고 도구 출력을 지어냈다(346줄 파일을 1074줄로 보고).
        # 능력을 뺏은 채 그 능력을 요구하면 할루시네이션을 유도하게 된다.
        #
        # 다만 이 테스트가 지키려던 진짜 불변식은 "쓰기·실행 도구가 없다" 이다.
        # 그 불변식은 그대로 검증한다. 허용 목록을 실제로 파싱해서 확인한다.
        self.assertIn("--allowed-tools", command)
        allowed = command[command.index("--allowed-tools") + 1]
        self.assertEqual(
            sorted(t.strip() for t in allowed.split(",")),
            ["Glob", "Grep", "Read"],
            "읽기 전용 도구만 허용해야 한다",
        )
        self.assertIn("--tools", command)
        exposed = command[command.index("--tools") + 1]
        self.assertEqual(
            sorted(t.strip() for t in exposed.split(",")),
            ["Glob", "Grep", "Read"],
            "Claude 컨텍스트에는 읽기 전용 도구만 노출해야 한다",
        )
        joined = " ".join(command)
        for forbidden in ("Write", "Edit", "Bash", "NotebookEdit", "WebFetch"):
            self.assertNotIn(forbidden, joined, f"{forbidden} 는 워커에 주면 안 된다")

    def test_quota_error_has_verified_unavailable_code(self):
        popen = Mock(return_value=FakeProcess(
            returncode=1,
            stdout="",
            stderr="You've hit your session limit - resets 4:20am",
        ))
        executor = BoundedCliExecutor(
            "claude", PROJECT_ROOT, popen_factory=popen,
            claude_rules_path=PROJECT_ROOT / "CLAUDE.md",
        )
        with self.assertRaises(AgentUnavailable) as caught:
            executor({"message_id": "T1", "body": "review"})
        self.assertEqual(caught.exception.availability_code, "quota_exhausted")

    def test_timeout_calls_process_tree_terminator(self):
        process = FakeProcess(timeout=True)
        popen = Mock(return_value=process)
        terminator = Mock()
        executor = BoundedCliExecutor(
            "antigravity", PROJECT_ROOT, timeout=0.01,
            popen_factory=popen, process_tree_terminator=terminator,
        )
        with self.assertRaises(TimeoutError):
            executor({"message_id": "T2", "body": "slow"})
        terminator.assert_called_once_with(process)

    def test_antigravity_stream_json_returns_response_and_records_usage(self):
        raw = (
            '{"event":"init","conversation_id":"conv-1","init":{}}\n'
            '{"event":"result","result":{"conversation_id":"conv-1","status":"SUCCESS",'
            '"response":"evidence ready","duration_seconds":2.5,"num_turns":1,'
            '"usage":{"input_tokens":100,"output_tokens":20,"thinking_tokens":5,'
            '"cache_read_tokens":10,"total_tokens":120}}}\n'
        )
        popen = Mock(return_value=FakeProcess(stdout=raw))
        recorder = Mock(return_value=PROJECT_ROOT / "telemetry.jsonl")
        executor = BoundedCliExecutor(
            "antigravity", PROJECT_ROOT, popen_factory=popen, telemetry_recorder=recorder,
        )

        result = executor({"message_id": "T3", "correlation_id": "C3", "body": "inspect"})

        self.assertEqual(result, "evidence ready")
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--output-format") + 1], "stream-json")
        self.assertNotIn("--dangerously-skip-permissions", command)
        controlled_prompt = command[command.index("--print") + 1]
        self.assertIn("Do not invoke a terminal or shell", controlled_prompt)
        self.assertIn("Do not create, modify, rename, or delete files", controlled_prompt)
        self.assertTrue(controlled_prompt.endswith("inspect"))
        record = recorder.call_args.args[0]
        self.assertEqual(record["message_id"], "T3")
        self.assertEqual(record["correlation_id"], "C3")
        self.assertEqual(record["usage"]["total_tokens"], 120)
        self.assertNotIn("response", record)

    def test_antigravity_invalid_stream_fails_closed_without_recording(self):
        popen = Mock(return_value=FakeProcess(stdout="not json"))
        recorder = Mock()
        executor = BoundedCliExecutor(
            "antigravity", PROJECT_ROOT, popen_factory=popen, telemetry_recorder=recorder,
        )

        with self.assertRaisesRegex(RuntimeError, "invalid stream-json telemetry"):
            executor({"message_id": "T4", "body": "inspect"})
        recorder.assert_not_called()

    def test_antigravity_stream_quota_error_is_classified(self):
        raw = (
            '{"event":"result","result":{"conversation_id":"conv-2","status":"ERROR",'
            '"response":"","error":"usage limit reached; resets 2:03am",'
            '"duration_seconds":1,"num_turns":0,"usage":{"total_tokens":0}}}\n'
        )
        popen = Mock(return_value=FakeProcess(stdout=raw))
        executor = BoundedCliExecutor("antigravity", PROJECT_ROOT, popen_factory=popen)

        with self.assertRaises(AgentUnavailable) as caught:
            executor({"message_id": "T5", "body": "inspect"})
        self.assertEqual(caught.exception.availability_code, "quota_exhausted")

    def test_claude_refuses_to_run_without_global_rules(self):
        popen = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "CLAUDE.md"
            executor = BoundedCliExecutor(
                "claude", PROJECT_ROOT, popen_factory=popen,
                claude_rules_path=missing,
            )
            with self.assertRaises(AgentUnavailable) as caught:
                executor({"message_id": "T1", "body": "review"})
        self.assertEqual(caught.exception.availability_code, "rules_unavailable")
        popen.assert_not_called()

    def test_antigravity_denied_action_is_not_accepted_as_success(self):
        raw = (
            '{"event":"result","result":{"conversation_id":"conv-3","status":"SUCCESS",'
            '"response":"","denied_actions":[{"action":"escalate_admin",'
            '"display_name":"Bash"}],"duration_seconds":3,"num_turns":1,'
            '"usage":{"input_tokens":20740,"output_tokens":466,"total_tokens":21206}}}\n'
        )
        popen = Mock(return_value=FakeProcess(stdout=raw))
        recorder = Mock()
        executor = BoundedCliExecutor(
            "antigravity", PROJECT_ROOT, popen_factory=popen, telemetry_recorder=recorder,
        )

        with self.assertRaises(AgentUnavailable) as caught:
            executor({"message_id": "T6", "body": "inspect"})
        self.assertEqual(caught.exception.availability_code, "permission_denied")
        recorder.assert_not_called()


class TestRegisteredQueueWorker(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        swarm = str(self.root / ".agent-swarm")
        self.patches = [
            patch("csc_broker.SWARM_DIR", swarm),
            patch("csc_broker.BROKER_META_FILE", str(self.root / ".agent-swarm/broker.json")),
        ]
        for item in self.patches:
            item.start()
        self.port = free_port()
        self.broker = SwarmBroker(port=self.port)
        self.broker_task = asyncio.create_task(self.broker.start())
        for _ in range(50):
            if self.broker.running:
                break
            await asyncio.sleep(0.01)

    async def asyncTearDown(self):
        self.broker.stop()
        try:
            await asyncio.wait_for(self.broker_task, 1)
        except (asyncio.CancelledError, Exception):
            self.broker_task.cancel()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    async def test_worker_registers_consumes_task_and_stops_cleanly(self):
        persist_message({
            "message_id": "TASK-LIVE-1",
            "sender": "codex",
            "recipient": "claude",
            "type": "TASK",
            "correlation_id": "CORR-1",
            "body": "ping",
        }, base_dir=str(self.root / ".agent-swarm"))
        stop = threading.Event()
        runtime = RegisteredQueueWorker(
            "claude", self.root, executor=lambda message: "LIVE_OK",
            host="127.0.0.1", port=self.port, poll_interval=0.03,
        )
        thread = threading.Thread(target=runtime.run_forever, args=(stop,), daemon=True)
        thread.start()

        result_seen = False
        for _ in range(100):
            await asyncio.sleep(0.03)
            queue = self.root / ".agent-swarm/messages/queue.jsonl"
            if queue.exists():
                records = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
                result_seen = any(
                    r.get("type") == "RESULT" and r.get("in_reply_to") == "TASK-LIVE-1"
                    for r in records
                )
            if result_seen and "claude" in self.broker.clients:
                break
        self.assertTrue(result_seen)
        self.assertIn("claude", self.broker.clients)

        stop.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        metadata = json.loads((self.root / ".agent-swarm/workers/claude.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "stopped")


    async def test_heartbeat_continues_while_executor_is_blocked(self):
        persist_message({
            "message_id": "TASK-SLOW-1",
            "sender": "codex",
            "recipient": "claude",
            "type": "TASK",
            "body": "slow",
        }, base_dir=str(self.root / ".agent-swarm"))
        started = threading.Event()
        release = threading.Event()

        def slow_executor(message):
            started.set()
            release.wait(2)
            return "DONE"

        stop = threading.Event()
        runtime = RegisteredQueueWorker(
            "claude", self.root, executor=slow_executor,
            host="127.0.0.1", port=self.port, poll_interval=0.03,
        )
        thread = threading.Thread(target=runtime.run_forever, args=(stop,), daemon=True)
        thread.start()

        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        self.assertTrue(started.is_set())
        metadata_path = self.root / ".agent-swarm/workers/claude.json"
        first = json.loads(metadata_path.read_text(encoding="utf-8"))["heartbeat_epoch"]

        advanced = False
        for _ in range(50):
            await asyncio.sleep(0.02)
            current = json.loads(metadata_path.read_text(encoding="utf-8"))["heartbeat_epoch"]
            if current > first:
                advanced = True
                break

        release.set()
        stop.set()
        thread.join(2)
        self.assertTrue(advanced)
        self.assertFalse(thread.is_alive())

if __name__ == "__main__":
    unittest.main()
