import asyncio
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from csc_broker import SwarmBroker


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestBrokerRoster(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        swarm = os.path.join(self.temp.name, ".agent-swarm")
        self.patches = [
            patch("csc_broker.SWARM_DIR", swarm),
            patch("csc_broker.BROKER_META_FILE", os.path.join(swarm, "broker.json")),
        ]
        for item in self.patches:
            item.start()
        self.broker = SwarmBroker(port=free_port())
        self.task = asyncio.create_task(self.broker.start())
        for _ in range(50):
            if self.broker.running:
                break
            await asyncio.sleep(0.01)

    async def asyncTearDown(self):
        self.broker.stop()
        try:
            await asyncio.wait_for(self.task, 1)
        except (asyncio.CancelledError, Exception):
            self.task.cancel()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    async def register(self, agent):
        reader, writer = await asyncio.open_connection(self.broker.host, self.broker.port)
        writer.write((json.dumps({"type": "REGISTER", "agent": agent}) + "\n").encode())
        await writer.drain()
        ack = json.loads((await reader.readline()).decode())
        self.assertEqual(ack["type"], "REGISTER_ACK")
        return reader, writer

    async def test_roster_reports_only_live_registered_connections(self):
        c_reader, c_writer = await self.register("claude")
        a_reader, a_writer = await self.register("antigravity")
        try:
            # consume AGENT_JOINED delivered to claude
            await c_reader.readline()
            control_reader, control_writer = await self.register("codex-control")
            try:
                await c_reader.readline()
                await a_reader.readline()
                control_writer.write(b'{"type":"ROSTER"}\n')
                await control_writer.drain()
                response = json.loads((await control_reader.readline()).decode())
                self.assertEqual(response["type"], "ROSTER")
                self.assertEqual(response["status"], "ok")
                self.assertEqual(
                    set(response["registered_agents"]),
                    {"claude", "antigravity", "codex-control"},
                )
            finally:
                control_writer.close()
                await control_writer.wait_closed()
        finally:
            c_writer.close()
            a_writer.close()
            await c_writer.wait_closed()
            await a_writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
