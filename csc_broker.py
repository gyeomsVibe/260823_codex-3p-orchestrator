#!/usr/bin/env python
"""
Codex Swarm Command (CSC) - Real-time Local Broker Server
Provides low-latency, port-based, asynchronous Pub/Sub messaging backed by csc_storage.
Guarantees at-least-once delivery + message_id idempotency.
NOTE: Does NOT claim or guarantee exactly-once delivery.
"""

import os
import sys
import json
import time
import socket
import asyncio
import argparse
from datetime import datetime, timezone
from typing import Dict, Set

import csc_storage

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
PROJECT_ROOT_ENV = "CSC_PROJECT_ROOT"
SWARM_DIRNAME = ".agent-swarm"


def resolve_project_root(explicit: "str | None" = None) -> str:
    """Resolves the canonical project root.

    Precedence: explicit argument > CSC_PROJECT_ROOT env var > directory that
    actually contains this script. The script directory is the canonical
    fallback so that `python csc.py` behaves identically no matter which
    working directory the caller happens to be in.
    """
    if explicit:
        return os.path.abspath(explicit)
    env_root = os.environ.get(PROJECT_ROOT_ENV)
    if env_root:
        return os.path.abspath(env_root)
    return os.path.dirname(os.path.abspath(__file__))


def swarm_dir(project_root: "str | None" = None) -> str:
    return os.path.join(resolve_project_root(project_root), SWARM_DIRNAME)


def broker_meta_path(project_root: "str | None" = None) -> str:
    return os.path.join(swarm_dir(project_root), "broker.json")


PROJECT_ROOT = resolve_project_root()
# Kept as module constants for backward compatibility with existing callers.
SWARM_DIR = swarm_dir()
BROKER_META_FILE = broker_meta_path()

# Types that are relayed to every other connected subscriber and persisted.
# This set is the superset of every type csc.py is allowed to send.
BROADCAST_TYPES = (
    "ACK", "PROPOSAL", "RISK", "RESULT", "BLOCKED", "CALL_OUT", "WHISTLEBLOW",
    "TASK", "EVENT", "REPORT",
)
# Connection-level control types handled inline, never broadcast.
CONTROL_TYPES = ("REGISTER", "PING", "ROSTER")
SUPPORTED_TYPES = BROADCAST_TYPES + CONTROL_TYPES


def get_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_available_port(start_port: int = DEFAULT_PORT, max_attempts: int = 10) -> int:
    """Finds an available TCP port on localhost."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((DEFAULT_HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port available in range {start_port} - {start_port + max_attempts}")


class SwarmBroker:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.clients: Dict[str, asyncio.StreamWriter] = {}
        self.subscribers: Set[asyncio.StreamWriter] = set()
        self.running = False
        self.server = None

    async def broadcast(self, message: dict, sender_writer=None):
        """Broadcasts a canonical JSON message to other registered subscriber clients.

        Note: Does NOT append to queue.jsonl. Persistence is handled in csc_storage
        prior to calling this broadcast function.
        """
        payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        for writer in list(self.subscribers):
            if writer is not sender_writer:
                try:
                    writer.write(payload)
                    await writer.drain()
                except Exception:
                    self.subscribers.discard(writer)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client_name = "unknown"
        peername = writer.get_extra_info("peername")

        try:
            while self.running:
                line = await reader.readline()
                if not line:
                    break

                raw_str = line.decode("utf-8").strip()
                if not raw_str:
                    continue

                try:
                    msg = json.loads(raw_str)
                except json.JSONDecodeError:
                    err_resp = {"status": "error", "error": "Invalid JSON", "raw": raw_str}
                    writer.write((json.dumps(err_resp) + "\n").encode("utf-8"))
                    await writer.drain()
                    continue

                msg_type = msg.get("type", "UNKNOWN")

                # Registration Handshake
                if msg_type == "REGISTER":
                    client_name = msg.get("agent", "unknown")
                    self.clients[client_name] = writer
                    resp = {
                        "type": "REGISTER_ACK",
                        "status": "ok",
                        "agent": client_name,
                        "timestamp": get_utc_iso(),
                        "registered_agents": list(self.clients.keys())
                    }
                    writer.write((json.dumps(resp) + "\n").encode("utf-8"))
                    await writer.drain()

                    # Connection is now an active registered subscriber
                    self.subscribers.add(writer)

                    # Connection event is appended to audit.jsonl only (never in business queue)
                    csc_storage.append_audit({
                        "type": "REGISTER",
                        "agent": client_name,
                        "timestamp": get_utc_iso()
                    }, base_dir=SWARM_DIR)

                    # Notify other registered subscribers
                    await self.broadcast({
                        "type": "AGENT_JOINED",
                        "agent": client_name,
                        "timestamp": get_utc_iso()
                    }, sender_writer=writer)
                    continue

                # Ping / Heartbeat
                elif msg_type == "PING":
                    resp = {"type": "PONG", "timestamp": get_utc_iso(), "agent": client_name}
                    writer.write((json.dumps(resp) + "\n").encode("utf-8"))
                    await writer.drain()
                    continue

                # Live socket roster. This reports current connections, not
                # stale metadata files, and is never persisted as business data.
                elif msg_type == "ROSTER":
                    resp = {
                        "type": "ROSTER",
                        "status": "ok",
                        "timestamp": get_utc_iso(),
                        "registered_agents": sorted(self.clients.keys()),
                        "count": len(self.clients),
                    }
                    writer.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
                    await writer.drain()
                    continue

                # Publish Business Event / Message
                elif msg_type in BROADCAST_TYPES:
                    if "sender" not in msg and "from" not in msg:
                        msg["sender"] = client_name

                    try:
                        canonical = csc_storage.canonicalize_envelope(msg)
                    except Exception as e:
                        err_ack = {
                            "status": "error",
                            "persisted": False,
                            "error": f"Invalid envelope: {e}",
                            "type": msg_type,
                            "msg_id": msg.get("message_id") or msg.get("id"),
                        }
                        writer.write((json.dumps(err_ack, ensure_ascii=False) + "\n").encode("utf-8"))
                        await writer.drain()
                        continue

                    # 1. Complete persistence in SSOT storage first
                    try:
                        persist_res = csc_storage.persist_message(canonical, base_dir=SWARM_DIR)
                        is_dedup = bool(persist_res.get("deduplicated", False))
                    except Exception as e:
                        err_ack = {
                            "status": "error",
                            "persisted": False,
                            "error": f"Persistence failed: {e}",
                            "type": msg_type,
                            "msg_id": canonical.get("message_id"),
                        }
                        writer.write((json.dumps(err_ack, ensure_ascii=False) + "\n").encode("utf-8"))
                        await writer.drain()
                        continue

                    # 2. Immediately send & drain ACK to sender
                    ack = {
                        "status": "ok",
                        "persisted": True,
                        "deduplicated": is_dedup,
                        "msg_id": canonical.get("message_id"),
                        "message_id": canonical.get("message_id"),
                    }
                    writer.write((json.dumps(ack, ensure_ascii=False) + "\n").encode("utf-8"))
                    await writer.drain()

                    # 3. Broadcast canonical envelope to other registered subscribers
                    await self.broadcast(canonical, sender_writer=writer)

                # Unsupported type: never silently dropped, always ACKed as error
                else:
                    err_ack = {
                        "status": "error",
                        "delivered": False,
                        "error": f"Unsupported message type '{msg_type}'",
                        "type": msg_type,
                        "msg_id": msg.get("message_id") or msg.get("id"),
                        "supported_types": list(SUPPORTED_TYPES),
                    }
                    writer.write((json.dumps(err_ack, ensure_ascii=False) + "\n").encode("utf-8"))
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"⚠️ [Broker] Client error ({client_name} @ {peername}): {e}")
        finally:
            self.subscribers.discard(writer)
            if client_name in self.clients and self.clients[client_name] == writer:
                del self.clients[client_name]
                csc_storage.append_audit({
                    "type": "AGENT_LEFT",
                    "agent": client_name,
                    "timestamp": get_utc_iso()
                }, base_dir=SWARM_DIR)
                await self.broadcast({
                    "type": "AGENT_LEFT",
                    "agent": client_name,
                    "timestamp": get_utc_iso()
                })
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self):
        self.port = find_available_port(self.port)
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self.running = True

        # Save broker metadata for CLI clients to discover
        os.makedirs(SWARM_DIR, exist_ok=True)
        meta = {
            "host": self.host,
            "port": self.port,
            "pid": os.getpid(),
            "started_at": get_utc_iso(),
            "status": "RUNNING"
        }
        with open(BROKER_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        print(f"🚀 [CSC Broker] Real-time Swarm Server listening on {self.host}:{self.port} (PID: {os.getpid()})")

        async with self.server:
            await self.server.serve_forever()

    def stop(self):
        self.running = False
        if self.server:
            self.server.close()
        if os.path.exists(BROKER_META_FILE):
            try:
                os.remove(BROKER_META_FILE)
            except Exception:
                pass
        print("🛑 [CSC Broker] Swarm Server stopped.")


async def run_broker_daemon(port: int = DEFAULT_PORT):
    broker = SwarmBroker(port=port)
    try:
        await broker.start()
    except KeyboardInterrupt:
        broker.stop()


# Synchronous helper client for CLI scripts
class SwarmClientSync:
    def __init__(self):
        self.host = DEFAULT_HOST
        self.port = DEFAULT_PORT
        self.meta = self._load_meta()

    def _load_meta(self) -> dict:
        if os.path.exists(BROKER_META_FILE):
            try:
                with open(BROKER_META_FILE, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    self.host = meta.get("host", DEFAULT_HOST)
                    self.port = meta.get("port", DEFAULT_PORT)
                    return meta
            except Exception:
                pass
        return {}

    def is_running(self) -> bool:
        if not os.path.exists(BROKER_META_FILE):
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect((self.host, self.port))
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                return False

    def send_message(self, message: dict, agent_name: str = "cli") -> dict:
        """Sends a message to the broker and waits for ACK."""
        if not self.is_running():
            return {"status": "fallback", "error": "Broker offline, using JSONL fallback"}

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.host, self.port))
                rfile = s.makefile("r", encoding="utf-8")

                # Handshake
                reg_payload = json.dumps({"type": "REGISTER", "agent": agent_name}) + "\n"
                s.sendall(reg_payload.encode("utf-8"))
                reg_line = rfile.readline()
                if not reg_line:
                    return {"status": "error", "error": "Broker closed connection on REGISTER"}

                # Send actual message (canonical envelope)
                msg_payload = json.dumps(message, ensure_ascii=False) + "\n"
                s.sendall(msg_payload.encode("utf-8"))

                # Read lines until ACK containing 'status' is encountered
                while True:
                    line = rfile.readline()
                    if not line:
                        return {"status": "error", "error": "Connection closed before ACK"}
                    ack_data = json.loads(line.strip())
                    if message.get('type') == 'PING' and ack_data.get('type') == 'PONG': return ack_data
                    if "status" in ack_data:
                        return ack_data
        except Exception as e:
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CSC Swarm Real-time Local Broker Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--status", action="store_true", help="Check broker running status")
    parser.add_argument("--test-ping", action="store_true", help="Send test ping to running broker")
    args = parser.parse_args()

    if args.status:
        client = SwarmClientSync()
        if client.is_running():
            print(f"🟢 [CSC Broker] Server is ACTIVE on {client.host}:{client.port} (Meta: {client.meta})")
            sys.exit(0)
        else:
            print("🔴 [CSC Broker] Server is INACTIVE.")
            sys.exit(1)

    elif args.test_ping:
        client = SwarmClientSync()
        res = client.send_message({"type": "PING"}, agent_name="test_client")
        print(f"📡 [CSC Broker Test] Response: {res}")
        sys.exit(0 if res.get("status") == "ok" or res.get("type") == "PONG" else 1)

    else:
        asyncio.run(run_broker_daemon(port=args.port))
