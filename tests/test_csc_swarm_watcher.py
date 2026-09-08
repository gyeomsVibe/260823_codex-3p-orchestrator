"""Tests for csc_swarm_watcher.py (WATCHER-R3 standard library compliance)."""

import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import csc_swarm_watcher


class TestCscSwarmWatcher(unittest.TestCase):
    def setUp(self):
        csc_swarm_watcher.reset_error_state()

    def test_poll_queue_offset_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "queue.jsonl"
            offset, msgs = csc_swarm_watcher.poll_queue_offset(p, 0)
            self.assertEqual(offset, 0)
            self.assertEqual(msgs, [])

    def test_poll_queue_offset_incremental_binary_safe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "queue.jsonl"
            msg1 = {"message_id": "MSG-001", "body": "한글 테스트 UTF-8"}
            p.write_bytes(json.dumps(msg1, ensure_ascii=False).encode("utf-8") + b"\n")

            offset1, msgs1 = csc_swarm_watcher.poll_queue_offset(p, 0)
            self.assertGreater(offset1, 0)
            self.assertEqual(len(msgs1), 1)
            self.assertEqual(msgs1[0]["body"], "한글 테스트 UTF-8")

            # Same offset produces no duplicate messages
            offset2, msgs2 = csc_swarm_watcher.poll_queue_offset(p, offset1)
            self.assertEqual(offset2, offset1)
            self.assertEqual(msgs2, [])

            # Incomplete write (without trailing newline) does not advance offset
            with p.open("ab") as f:
                f.write(b'{"message_id": "PARTIAL"')

            offset_partial, msgs_partial = csc_swarm_watcher.poll_queue_offset(p, offset1)
            self.assertEqual(offset_partial, offset1)
            self.assertEqual(msgs_partial, [])

            # Complete the partial line
            with p.open("ab") as f:
                f.write(b', "status": "OK"}\n')

            offset3, msgs3 = csc_swarm_watcher.poll_queue_offset(p, offset1)
            self.assertGreater(offset3, offset1)
            self.assertEqual(len(msgs3), 1)
            self.assertEqual(msgs3[0]["status"], "OK")

    def test_no_activity_skips_dashboard_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "queue.jsonl"
            p.write_text(json.dumps({"msg": "initial"}) + "\n", encoding="utf-8")
            current_offset = p.stat().st_size

            mock_dashboard = MagicMock()
            started_epoch = time.time()
            sig = ((), ())

            # 5 ticks with no new messages must make 0 dashboard calls
            for _ in range(5):
                current_offset, activity, sig = csc_swarm_watcher.tick_watcher(
                    queue_path=p,
                    current_offset=current_offset,
                    started_epoch=started_epoch,
                    instance_id="test-instance",
                    last_peer_signature=sig,
                    dashboard_fn=mock_dashboard,
                )
                self.assertFalse(activity)

            self.assertEqual(mock_dashboard.call_count, 0)

    def test_new_valid_message_triggers_dashboard_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "queue.jsonl"
            p.write_text(json.dumps({"msg": "initial"}) + "\n", encoding="utf-8")
            current_offset = p.stat().st_size

            mock_dashboard = MagicMock()
            started_epoch = time.time()

            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"msg": "new_task"}) + "\n")

            new_offset, activity, _ = csc_swarm_watcher.tick_watcher(
                queue_path=p,
                current_offset=current_offset,
                started_epoch=started_epoch,
                instance_id="test-instance",
                dashboard_fn=mock_dashboard,
            )

            self.assertTrue(activity)
            self.assertGreater(new_offset, current_offset)
            self.assertEqual(mock_dashboard.call_count, 1)

    def test_malformed_line_does_not_trigger_dashboard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "queue.jsonl"
            p.write_text(json.dumps({"msg": "initial"}) + "\n", encoding="utf-8")
            current_offset = p.stat().st_size

            mock_dashboard = MagicMock()
            started_epoch = time.time()

            # Append invalid non-JSON line
            with p.open("a", encoding="utf-8") as f:
                f.write("NOT_A_VALID_JSON_LINE\n")

            new_offset, activity, _ = csc_swarm_watcher.tick_watcher(
                queue_path=p,
                current_offset=current_offset,
                started_epoch=started_epoch,
                instance_id="test-instance",
                dashboard_fn=mock_dashboard,
            )

            # Offset advances past the malformed line, but dashboard is NOT triggered
            self.assertFalse(activity)
            self.assertGreater(new_offset, current_offset)
            self.assertEqual(mock_dashboard.call_count, 0)

    def test_error_and_recovered_logging(self):
        stderr_buf = io.StringIO()
        with patch.object(sys, "stderr", stderr_buf):
            # 1. Error occurs
            csc_swarm_watcher.record_error("test_comp", "network timeout")
            # 2. Same error repeated (must NOT be logged again)
            csc_swarm_watcher.record_error("test_comp", "network timeout")
            # 3. Success occurs -> logs RECOVERED
            csc_swarm_watcher.record_success("test_comp")
            # 4. Subsequent success without error -> silent
            csc_swarm_watcher.record_success("test_comp")

        output = stderr_buf.getvalue()
        self.assertEqual(output.count("[watcher:test_comp] network timeout"), 1)
        self.assertEqual(output.count("[watcher:test_comp] RECOVERED"), 1)

    def test_peer_transition_triggers_dashboard(self):
        with patch("csc_swarm_watcher.csc_heartbeat") as mock_hb:
            mock_hb.check_peers.return_value = {
                "fresh": [],
                "stale": [("codex", 45.0)],
                "missing_required": [],
            }
            mock_dashboard = MagicMock()
            started_epoch = time.time()

            with tempfile.TemporaryDirectory() as tmpdir:
                p = Path(tmpdir) / "queue.jsonl"
                # Initial tick establishes baseline
                _, _, sig1 = csc_swarm_watcher.tick_watcher(
                    queue_path=p,
                    current_offset=0,
                    started_epoch=started_epoch,
                    instance_id="test-antigravity",
                    last_peer_signature=((), ()),
                    dashboard_fn=mock_dashboard,
                )
                self.assertEqual(mock_dashboard.call_count, 1)


if __name__ == "__main__":
    unittest.main()
