import os
import sys
import json
import socket
import asyncio
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csc_broker
from csc_broker import SwarmBroker, BROADCAST_TYPES


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestCscBrokerProtocol(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        swarm_dir = os.path.join(self.temp_dir.name, ".agent-swarm")
        meta_file = os.path.join(swarm_dir, "broker.json")
        self.swarm_dir = swarm_dir

        self.patch_swarm_dir = patch("csc_broker.SWARM_DIR", swarm_dir)
        self.patch_meta_file = patch("csc_broker.BROKER_META_FILE", meta_file)
        self.patch_swarm_dir.start()
        self.patch_meta_file.start()

        self.port = find_free_port()
        self.broker = SwarmBroker(host="127.0.0.1", port=self.port)
        self.broker_task = asyncio.create_task(self.broker.start())

        # Wait until broker starts listening
        for _ in range(50):
            if self.broker.running and self.broker.server is not None:
                break
            await asyncio.sleep(0.02)

        self.assertTrue(self.broker.running)
        self.assertIsNotNone(self.broker.server)

    async def asyncTearDown(self):
        if hasattr(self, "broker") and self.broker:
            self.broker.stop()
        if hasattr(self, "broker_task") and self.broker_task:
            try:
                await asyncio.wait_for(self.broker_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                self.broker_task.cancel()
                try:
                    await self.broker_task
                except (asyncio.CancelledError, Exception):
                    pass

        self.patch_meta_file.stop()
        self.patch_swarm_dir.stop()
        self.temp_dir.cleanup()

    async def test_protocol_flow(self):
        self.assertIn("PROPOSAL", BROADCAST_TYPES)

        # 1. Connect two clients
        reader1, writer1 = await asyncio.open_connection(self.broker.host, self.broker.port)
        reader2, writer2 = await asyncio.open_connection(self.broker.host, self.broker.port)

        try:
            # 2. Register Client 1
            reg1_payload = {"type": "REGISTER", "agent": "client_alpha"}
            writer1.write((json.dumps(reg1_payload) + "\n").encode("utf-8"))
            await writer1.drain()

            raw_resp1 = await reader1.readline()
            resp1 = json.loads(raw_resp1.decode("utf-8"))
            self.assertEqual(resp1.get("type"), "REGISTER_ACK")
            self.assertEqual(resp1.get("status"), "ok")
            self.assertEqual(resp1.get("agent"), "client_alpha")

            # 3. Register Client 2
            reg2_payload = {"type": "REGISTER", "agent": "client_beta"}
            writer2.write((json.dumps(reg2_payload) + "\n").encode("utf-8"))
            await writer2.drain()

            raw_resp2 = await reader2.readline()
            resp2 = json.loads(raw_resp2.decode("utf-8"))
            self.assertEqual(resp2.get("type"), "REGISTER_ACK")
            self.assertEqual(resp2.get("status"), "ok")
            self.assertEqual(resp2.get("agent"), "client_beta")

            # Client 1 should receive AGENT_JOINED broadcast for Client 2
            raw_joined = await reader1.readline()
            joined_msg = json.loads(raw_joined.decode("utf-8"))
            self.assertEqual(joined_msg.get("type"), "AGENT_JOINED")
            self.assertEqual(joined_msg.get("agent"), "client_beta")

            # 4. Client 1 sends PROPOSAL (canonical format)
            proposal_payload = {
                "type": "PROPOSAL",
                "message_id": "prop-001",
                "sender": "client_alpha",
                "recipient": "client_beta",
                "body": "Proposal details",
            }
            writer1.write((json.dumps(proposal_payload) + "\n").encode("utf-8"))
            await writer1.drain()

            # Verify sender receives status ok, persisted true, deduplicated false ACK
            raw_ack = await reader1.readline()
            ack = json.loads(raw_ack.decode("utf-8"))
            self.assertEqual(ack.get("status"), "ok")
            self.assertTrue(ack.get("persisted"))
            self.assertFalse(ack.get("deduplicated"))
            self.assertEqual(ack.get("msg_id"), "prop-001")

            # Verify subscriber (Client 2) receives canonical broadcast
            raw_broadcast = await reader2.readline()
            broadcast_msg = json.loads(raw_broadcast.decode("utf-8"))
            self.assertEqual(broadcast_msg.get("type"), "PROPOSAL")
            self.assertEqual(broadcast_msg.get("message_id"), "prop-001")
            self.assertEqual(broadcast_msg.get("sender"), "client_alpha")
            self.assertEqual(broadcast_msg.get("recipient"), "client_beta")
            self.assertEqual(broadcast_msg.get("body"), "Proposal details")
            self.assertIn("timestamp", broadcast_msg)

            # Test idempotency: send same message_id a second time
            writer1.write((json.dumps(proposal_payload) + "\n").encode("utf-8"))
            await writer1.drain()

            raw_ack2 = await reader1.readline()
            ack2 = json.loads(raw_ack2.decode("utf-8"))
            self.assertEqual(ack2.get("status"), "ok")
            self.assertTrue(ack2.get("persisted"))
            self.assertTrue(ack2.get("deduplicated"))
            self.assertEqual(ack2.get("msg_id"), "prop-001")

            # 5. Client 1 sends UNKNOWN message type
            unknown_payload = {
                "type": "UNKNOWN",
                "message_id": "unk-999",
                "foo": "bar",
            }
            writer1.write((json.dumps(unknown_payload) + "\n").encode("utf-8"))
            await writer1.drain()

            # Verify sender receives status error ACK
            raw_err_ack = await reader1.readline()
            err_ack = json.loads(raw_err_ack.decode("utf-8"))
            self.assertEqual(err_ack.get("status"), "error")
            self.assertFalse(err_ack.get("delivered"))
            self.assertEqual(err_ack.get("type"), "UNKNOWN")
            self.assertEqual(err_ack.get("msg_id"), "unk-999")
            self.assertIn("Unsupported message type", err_ack.get("error", ""))

            # 6. Verify SSOT persistence layer state
            messages_dir = os.path.join(self.swarm_dir, "messages")
            queue_file = os.path.join(messages_dir, "queue.jsonl")
            inbox_file = os.path.join(messages_dir, "client_beta_inbox.jsonl")
            audit_file = os.path.join(messages_dir, "audit.jsonl")

            self.assertTrue(os.path.exists(queue_file))
            with open(queue_file, "r", encoding="utf-8") as f:
                q_lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(q_lines), 1)
            self.assertEqual(q_lines[0]["message_id"], "prop-001")

            self.assertTrue(os.path.exists(inbox_file))
            with open(inbox_file, "r", encoding="utf-8") as f:
                i_lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(i_lines), 1)
            self.assertEqual(i_lines[0]["message_id"], "prop-001")

            self.assertTrue(os.path.exists(audit_file))
            with open(audit_file, "r", encoding="utf-8") as f:
                audit_lines = [json.loads(line) for line in f if line.strip()]
            self.assertTrue(any(a.get("type") == "REGISTER" and a.get("agent") == "client_alpha" for a in audit_lines))

        finally:
            writer1.close()
            writer2.close()
            await writer1.wait_closed()
            await writer2.wait_closed()


if __name__ == "__main__":
    unittest.main()
