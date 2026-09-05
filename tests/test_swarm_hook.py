import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = PROJECT_ROOT / ".claude" / "hooks" / "swarm_hook.py"
SPEC = importlib.util.spec_from_file_location("swarm_hook_under_test", HOOK_PATH)
swarm_hook = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(swarm_hook)


class TestChannelOwnershipHook(unittest.TestCase):
    def run_guard(self, actor: str, target: Path) -> dict:
        emitted = []
        with (
            patch.object(swarm_hook, "ME", actor),
            patch.object(
                swarm_hook,
                "_stdin_json",
                return_value={"tool_input": {"file_path": str(target)}},
            ),
            patch("builtins.print", side_effect=emitted.append),
        ):
            with self.assertRaises(SystemExit):
                swarm_hook.cmd_guard_write()
        return json.loads(emitted[-1])

    def test_denies_other_agents_top_level_channel(self):
        result = self.run_guard(
            "claude-code-6c", PROJECT_ROOT / ".agent-swarm/chat/antigravity.md"
        )
        self.assertEqual(
            result["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_allows_own_top_level_channel(self):
        result = self.run_guard(
            "claude-code-6c", PROJECT_ROOT / ".agent-swarm/chat/claude-code.md"
        )
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
