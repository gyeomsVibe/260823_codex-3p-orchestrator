import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csc
import csc_storage


class TestCscDelivery(unittest.TestCase):
    def test_swarm_dir_is_absolute_and_matches_parent(self):
        """(1) csc.SWARM_DIR이 절대경로이며 Path(csc.__file__).parent / '.agent-swarm'과 같은지 검증."""
        self.assertTrue(os.path.isabs(csc.SWARM_DIR))
        expected_dir = Path(csc.__file__).parent / ".agent-swarm"
        self.assertEqual(Path(csc.SWARM_DIR), expected_dir)

    def test_broker_persisted_skips_storage_persist(self):
        """(2) temp .agent-swarm으로 csc.SWARM_DIR을 patch하고 fake SwarmClientSync의
        is_running=True, send_message 반환={'status':'ok','persisted':True}일 때
        csc_storage.persist_message mock이 호출되지 않는지 검증.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_swarm_dir = str(Path(temp_dir) / ".agent-swarm")
            fake_client = MagicMock()
            fake_client.is_running.return_value = True
            fake_client.send_message.return_value = {"status": "ok", "persisted": True}
            fake_client_cls = MagicMock(return_value=fake_client)

            with patch("csc.SWARM_DIR", temp_swarm_dir), \
                 patch("csc.SwarmClientSync", fake_client_cls), \
                 patch("csc_storage.persist_message") as mock_persist, \
                 redirect_stdout(io.StringIO()):
                csc.send_message(
                    sender="alice",
                    recipient="bob",
                    msg_type="PROPOSAL",
                    body="Test message via broker",
                )
                mock_persist.assert_not_called()

    def test_broker_not_running_fallback_persists_to_queue_and_bob_inbox(self):
        """(3) fake is_running=False일 때 send_message 후 temp messages/queue.jsonl 및
        bob_inbox.jsonl이 각각 1줄이고 두 레코드가 canonical 7필드와 동일 message_id를 가지는지 검증.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_swarm_dir = str(Path(temp_dir) / ".agent-swarm")
            fake_client = MagicMock()
            fake_client.is_running.return_value = False
            fake_client_cls = MagicMock(return_value=fake_client)

            with patch("csc.SWARM_DIR", temp_swarm_dir), \
                 patch("csc.SwarmClientSync", fake_client_cls), \
                 redirect_stdout(io.StringIO()):
                msg_id = csc.send_message(
                    sender="alice",
                    recipient="bob",
                    msg_type="PROPOSAL",
                    body="Fallback message to bob",
                )

            queue_file = Path(temp_swarm_dir) / "messages" / "queue.jsonl"
            inbox_file = Path(temp_swarm_dir) / "messages" / "bob_inbox.jsonl"

            self.assertTrue(queue_file.exists(), f"Expected {queue_file} to exist")
            self.assertTrue(inbox_file.exists(), f"Expected {inbox_file} to exist")

            with open(queue_file, "r", encoding="utf-8") as f:
                q_lines = [line.strip() for line in f if line.strip()]
            with open(inbox_file, "r", encoding="utf-8") as f:
                b_lines = [line.strip() for line in f if line.strip()]

            self.assertEqual(len(q_lines), 1, "messages/queue.jsonl must contain exactly 1 line")
            self.assertEqual(len(b_lines), 1, "messages/bob_inbox.jsonl must contain exactly 1 line")

            q_record = json.loads(q_lines[0])
            b_record = json.loads(b_lines[0])

            canonical_fields = {
                "message_id",
                "timestamp",
                "sender",
                "recipient",
                "type",
                "in_reply_to",
                "body",
            }
            self.assertEqual(set(q_record.keys()), canonical_fields)
            self.assertEqual(set(b_record.keys()), canonical_fields)
            self.assertEqual(q_record["message_id"], msg_id)
            self.assertEqual(b_record["message_id"], msg_id)
            self.assertEqual(q_record["message_id"], b_record["message_id"])


if __name__ == "__main__":
    unittest.main()
