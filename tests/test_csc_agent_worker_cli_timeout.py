import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csc_agent_worker


class TestWorkerCliTimeout(unittest.TestCase):
    @patch("csc_agent_worker._load_broker_endpoint", return_value=("127.0.0.1", 8765))
    @patch("csc_agent_worker.RegisteredQueueWorker")
    @patch("csc_agent_worker.BoundedCliExecutor")
    def test_cli_default_uses_configured_worker_timeout(
        self, executor_class, runtime_class, _endpoint
    ):
        runtime_class.return_value.run_forever.return_value = None
        argv = [
            "csc_agent_worker.py",
            "--agent",
            "claude",
            "--project-root",
            str(PROJECT_ROOT),
        ]

        with patch.dict(os.environ, {"CSC_WORKER_TIMEOUT": "600"}), patch.object(
            sys, "argv", argv
        ):
            self.assertEqual(csc_agent_worker.main(), 0)

        self.assertEqual(executor_class.call_args.kwargs["timeout"], 600.0)


if __name__ == "__main__":
    unittest.main()
