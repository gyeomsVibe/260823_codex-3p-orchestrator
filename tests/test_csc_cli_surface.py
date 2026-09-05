import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csc
from csc import send_message, wait_for_replies
from csc_storage import persist_message


class TestCscCliSurface(unittest.TestCase):
    def test_status_pid_check_uses_runtime_liveness_predicate(self):
        with patch("csc.pid_is_alive", return_value=True) as check:
            self.assertTrue(csc._pid_alive(15804))
        check.assert_called_once_with(15804)

    def _liveness_row(self, probe_result):
        """워커 1개 등록 파일을 만들고 PID 조회 결과만 바꿔가며 판정을 본다."""
        with tempfile.TemporaryDirectory() as temp:
            swarm = Path(temp) / ".agent-swarm"
            workers = swarm / "workers"
            workers.mkdir(parents=True)
            (workers / "claude.json").write_text(json.dumps({
                "agent": "claude", "pid": 15804, "status": "ready",
                "heartbeat_epoch": __import__("time").time(),
            }), encoding="utf-8")
            with patch("csc.SWARM_DIR", str(swarm)),                  patch("csc._pid_probe", return_value=probe_result),                  patch("csc.csc_runtime.query_roster",
                       return_value={"registered_agents": ["claude"]}):
                return csc._worker_liveness()[0]

    def test_denied_pid_probe_falls_back_to_heartbeat_and_roster(self):
        """Codex 의 정당한 우려: Windows 접근 거부를 사망으로 오판하면 안 된다.

        PID 를 '볼 수 없는' 것과 '없는' 것은 다르다. 볼 수 없을 때만 보조 증거를 쓴다.
        """
        self.assertEqual(self._liveness_row("unknown")["verdict"], "LIVE")

    def test_definitively_gone_pid_is_never_reported_live(self):
        """거짓 DEAD 를 막으려다 거짓 LIVE 를 만들면 안 된다.

        실측 근거 (2026-09-06): 하트비트가 0.1초 전이고 소켓 로스터에도 있는데
        기록된 PID 15804 는 os.kill 로 확실히 죽어 있었다. 그런데 status 는 LIVE 였다.
        거짓 LIVE 는 이 대시보드가 애초에 고치려던 바로 그 결함이다.

        확실한 부재는 어떤 보조 증거로도 뒤집지 않는다. 대신 PID_STALE 로
        '등록 PID 가 낡았다' 는 실제 상태를 이름 붙여 드러낸다.
        """
        verdict = self._liveness_row("gone")["verdict"]
        self.assertNotEqual(verdict, "LIVE", "확실히 죽은 PID 를 LIVE 로 보고했다")
        self.assertEqual(verdict, "PID_STALE")

    def test_alive_pid_with_fresh_heartbeat_is_live(self):
        self.assertEqual(self._liveness_row("alive")["verdict"], "LIVE")

    def test_help_exposes_activation_roster_and_await(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "csc.py"), "--help"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
        )
        self.assertIn("activate", result.stdout)
        self.assertIn("roster", result.stdout)
        self.assertIn("await", result.stdout)

    def test_send_message_accepts_task_and_correlation(self):
        with tempfile.TemporaryDirectory() as temp:
            swarm = os.path.join(temp, ".agent-swarm")
            with patch("csc.SWARM_DIR", swarm), patch("csc.SwarmClientSync", None):
                message_id = send_message(
                    "codex", "claude", "TASK", "review", correlation_id="DEC-1"
                )
            queue = Path(swarm) / "messages/queue.jsonl"
            record = json.loads(queue.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["message_id"], message_id)
            self.assertEqual(record["correlation_id"], "DEC-1")

    def test_wait_for_replies_returns_result_and_blocked_for_expected_agents(self):
        with tempfile.TemporaryDirectory() as temp:
            swarm = Path(temp) / ".agent-swarm"
            for message in (
                {"message_id": "R1", "sender": "claude", "recipient": "codex", "type": "RESULT", "in_reply_to": "TASK-1", "body": "yes"},
                {"message_id": "B1", "sender": "antigravity", "recipient": "codex", "type": "BLOCKED", "in_reply_to": "TASK-1", "availability_code": "quota_exhausted", "body": "limit"},
            ):
                persist_message(message, base_dir=str(swarm))
            replies = wait_for_replies(
                "TASK-1", {"claude", "antigravity"}, swarm / "messages/queue.jsonl",
                timeout=0.1, poll_interval=0.01,
            )
            self.assertEqual(set(replies), {"claude", "antigravity"})
            self.assertEqual(replies["antigravity"]["type"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
