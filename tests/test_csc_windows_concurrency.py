import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from csc_worker import _atomic_write_json
from csc_runtime import ensure_worker, worker_is_fresh


class WindowsConcurrencyAndSupervisorTests(unittest.TestCase):
    def test_atomic_write_json_retries_on_winerror_and_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test_target.json"
            calls = 0
            original_replace = os.replace

            def mock_replace(src, dst):
                nonlocal calls
                calls += 1
                if calls < 3:
                    exc = PermissionError("The process cannot access the file because it is being used by another process")
                    exc.winerror = 32
                    raise exc
                return original_replace(src, dst)

            with patch("os.replace", side_effect=mock_replace):
                _atomic_write_json(target, {"status": "ok", "retried": True})

            self.assertEqual(calls, 3)
            self.assertTrue(target.exists())

    def test_ensure_worker_restarts_when_not_connected_to_socket(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workers_dir = root / ".agent-swarm" / "workers"
            workers_dir.mkdir(parents=True, exist_ok=True)
            meta_path = workers_dir / "antigravity.json"
            now = time.time()
            meta_path.write_text(
                f'{{"agent": "antigravity", "status": "ready", "heartbeat_epoch": {now}, "pid": 99999}}',
                encoding="utf-8",
            )

            mock_proc = MagicMock()
            mock_proc.pid = 88888
            mock_popen = MagicMock(return_value=mock_proc)

            with patch("csc_runtime.pid_is_alive", return_value=True), \
                 patch("csc_runtime._terminate_pid_tree"), \
                 patch("csc_runtime.initialize_cursor_at_queue_end"):
                res = ensure_worker(
                    "antigravity",
                    root,
                    popen_factory=mock_popen,
                    registered_agents={"claude"},
                )
                self.assertEqual(res["action"], "started")
                self.assertEqual(res["pid"], 88888)

    def test_ensure_worker_reuses_when_fresh_and_connected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workers_dir = root / ".agent-swarm" / "workers"
            workers_dir.mkdir(parents=True, exist_ok=True)
            meta_path = workers_dir / "claude.json"
            now = time.time()
            meta_path.write_text(
                f'{{"agent": "claude", "status": "ready", "heartbeat_epoch": {now}, "pid": 77777}}',
                encoding="utf-8",
            )

            with patch("csc_worker.probe_pid", return_value="alive"):
                res = ensure_worker("claude", root, registered_agents={"claude"})
                self.assertEqual(res["action"], "reused")
                self.assertEqual(res["pid"], 77777)


if __name__ == "__main__":
    unittest.main()
