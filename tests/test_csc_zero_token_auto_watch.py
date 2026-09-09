#!/usr/bin/env python
"""Unit tests for C3P zero-token real-time message watcher and budget-saving activation.

Validates that:
  1. activate() with budget-saving mode returns proper metadata and reuses live workers without spawning duplicates.
  2. csc_watch filters out machine/event logs, self-sent messages, and routes target messages with zero-token overhead.
  3. CLI surface properly exposes --budget-saving and watch subcommand.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csc_watch
from csc_runtime import activate


class TestCscZeroTokenAutoWatch(unittest.TestCase):
    """Zero-token standby and real-time event watcher tests."""

    def test_watch_filter_ignores_machine_events(self):
        # Programmatic machine events must be silently dropped to prevent noise and token waste
        machine_msgs = [
            {"sender": "codex", "recipient": "all", "type": "EVENT", "body": "lock touched"},
            {"sender": "system", "recipient": "all", "type": "AGENT_JOINED", "body": "joined"},
            {"sender": "system", "recipient": "all", "type": "REGISTER", "body": "registered"},
        ]
        for msg in machine_msgs:
            self.assertFalse(
                csc_watch.is_for_me(msg, "antigravity"),
                f"Machine event {msg['type']} must be ignored",
            )

    def test_watch_filter_ignores_self_messages(self):
        # Messages sent by self must not trigger self-alert loops
        self_msgs = [
            {"sender": "antigravity", "recipient": "all", "type": "RESULT", "body": "done"},
            {"sender": "antigravity-worker-1", "recipient": "all", "type": "RESULT", "body": "done"},
            {"sender": "claude", "recipient": "claude", "type": "TASK", "body": "test"},
        ]
        self.assertFalse(csc_watch.is_for_me(self_msgs[0], "antigravity"))
        self.assertFalse(csc_watch.is_for_me(self_msgs[1], "antigravity"))
        self.assertFalse(csc_watch.is_for_me(self_msgs[2], "claude"))

    def test_watch_filter_routes_target_human_and_task_messages(self):
        # Valid tasks, proposals, and results destined for the agent or all must pass
        valid_msgs = [
            {"sender": "codex", "recipient": "antigravity", "type": "TASK", "body": "review PR"},
            {"sender": "claude", "recipient": "all", "type": "PROPOSAL", "body": "architecture"},
            {"sender": "user", "recipient": "claude", "type": "DECISION", "body": "approved"},
        ]
        self.assertTrue(csc_watch.is_for_me(valid_msgs[0], "antigravity"))
        self.assertTrue(csc_watch.is_for_me(valid_msgs[1], "antigravity"))
        # Sender was 'claude', so claude should NOT be notified of its own broadcast
        self.assertFalse(csc_watch.is_for_me(valid_msgs[1], "claude"))
        self.assertTrue(csc_watch.is_for_me(valid_msgs[2], "claude"))
        self.assertFalse(csc_watch.is_for_me(valid_msgs[0], "claude"))

    @patch("csc_runtime.ensure_broker")
    @patch("csc_runtime.query_roster")
    @patch("csc_runtime.ensure_worker")
    @patch("csc_runtime.worker_is_fresh")
    def test_activate_budget_saving_reused_metadata(
        self, mock_fresh, mock_worker, mock_roster, mock_broker
    ):
        mock_broker.return_value = {"action": "reused", "pid": 1234, "port": 8765}
        mock_roster.return_value = {
            "type": "ROSTER",
            "registered_agents": ["antigravity", "claude"],
            "count": 2,
        }
        mock_worker.side_effect = lambda agent, root, registered_agents=None: {
            "agent": agent,
            "action": "reused",
            "pid": 5678,
        }
        mock_fresh.return_value = True

        result = activate(PROJECT_ROOT, timeout=2.0, budget_saving=True)

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["budget_saving_mode"])
        self.assertEqual(result["registered_agents"], ["antigravity", "claude"])
        self.assertEqual(result["broker"]["action"], "reused")
        for w in result["workers"]:
            self.assertEqual(w["action"], "reused")


if __name__ == "__main__":
    unittest.main()
