"""동료 채널 무결성 2층 방어 회귀 테스트.

배경 (2026-09-05):
    Claude Code 가 chat/antigravity.md 를 Bash sed 로 수정했다. guard-write 는
    Write/Edit 만 보므로 그 아래로 지나갔다.

설계 (코덱스 A2 판정 + Claude 보강):
    1층 PreToolUse(Bash)  : 명백한 직접 수정만 차단. **보안 경계가 아니다.**
                            정규식이므로 우회 가능하다는 점을 문서와 메시지에 명시한다.
    2층 PostToolUse(Bash) : 채널 파일 sha256 대조. '명령'이 아니라 '결과'를 보므로
                            어떤 우회 수단을 쓰든 탐지된다. 이쪽이 실효 장치다.

    운영 워커의 진짜 경계는 --restricted + --tools 로 능력 자체를 제거하는 것이며,
    이 훅들은 대화형 세션용 보조 수단이다. 그 이상으로 주장하지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(PROJECT_ROOT, ".claude", "hooks", "swarm_hook.py")
STATE = os.path.join(PROJECT_ROOT, ".claude", "hooks", ".state", "channel_hashes.json")
CHAT = os.path.join(PROJECT_ROOT, ".agent-swarm", "chat")
PEER = os.path.join(CHAT, "codex.md")
MINE = os.path.join(CHAT, "sessions", "claude-code-6c.md")

ENV = dict(os.environ, CSC_AGENT_ID="claude-code-6c", PYTHONIOENCODING="utf-8")


def call_hook(command_name: str, payload: dict) -> str:
    """훅을 실제 프로세스로 돌린다. import 로는 하네스 계약을 검증할 수 없다."""
    proc = subprocess.run(
        [sys.executable, HOOK, command_name],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        # cp949 기본값이면 한글 출력이 깨져 판정이 통째로 뒤집힌다.
        # 실제로 이 테스트를 처음 돌렸을 때 7건 중 5건이 거짓 통과로 나왔다.
        encoding="utf-8",
        errors="replace",
        env=ENV,
        cwd=PROJECT_ROOT,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def decision(out: str) -> str:
    if '"deny"' in out:
        return "deny"
    if '"ask"' in out:
        return "ask"
    return "pass"


@unittest.skipUnless(os.path.exists(HOOK), "swarm_hook.py 없음")
class TestBashSpeedBump(unittest.TestCase):
    """1층. 완전하지 않다는 전제 위에서, 명백한 경우는 반드시 잡아야 한다."""

    C = ".agent-swarm/chat/"

    def test_peer_channel_writes_are_denied(self):
        for label, cmd in (
            ("sed -i", "sed -i s/x/y/ " + self.C + "antigravity.md"),
            ("리다이렉트", "echo hack >> " + self.C + "codex.md"),
            ("tee", "cat f | tee " + self.C + "codex.md"),
            ("python -c", "python -c open('" + self.C + "codex.md','a')"),
        ):
            with self.subTest(label):
                out = call_hook("guard-bash", {"tool_input": {"command": cmd}})
                self.assertEqual(decision(out), "deny", f"{label} 이 차단되지 않았다")
                self.assertIn("과속방지턱", out, "경계가 아님을 반드시 명시해야 한다")

    def test_own_channel_and_unrelated_commands_pass(self):
        for label, cmd in (
            ("내 채널", "sed -i s/x/y/ " + self.C + "sessions/claude-code-6c.md"),
            ("무관한 명령", "ls -la"),
        ):
            with self.subTest(label):
                out = call_hook("guard-bash", {"tool_input": {"command": cmd}})
                self.assertEqual(decision(out), "pass", f"{label} 을 잘못 막았다")

    def test_pre_push_gate_still_asks(self):
        """채널 검사를 추가하면서 PRE-PUSH 게이트를 깨뜨리지 않았는지 확인한다."""
        out = call_hook("guard-bash", {"tool_input": {"command": "git push origin main"}})
        self.assertEqual(decision(out), "ask")


@unittest.skipUnless(os.path.exists(HOOK) and os.path.exists(PEER),
                     "훅 또는 채널 파일 없음")
class TestChannelHashWatch(unittest.TestCase):
    """2층. 명령이 아니라 결과를 보므로 우회할 수 없다는 주장을 증명한다."""

    def setUp(self):
        self._restore = []
        for path in (PEER, MINE):
            if os.path.exists(path):
                bak = path + ".unittestbak"
                shutil.copy2(path, bak)
                self._restore.append((bak, path))
        self._had_state = os.path.exists(STATE)
        if self._had_state:
            shutil.copy2(STATE, STATE + ".unittestbak")
        if os.path.exists(STATE):
            os.remove(STATE)
        call_hook("channel-watch", {})          # 기준선 수립

    def tearDown(self):
        for bak, path in self._restore:
            shutil.move(bak, path)
        if os.path.exists(STATE):
            os.remove(STATE)
        if self._had_state:
            shutil.move(STATE + ".unittestbak", STATE)
        else:
            call_hook("channel-watch", {})      # 기준선 재수립

    def test_baseline_is_created(self):
        self.assertTrue(os.path.exists(STATE), "기준선 파일이 생기지 않았다")

    def test_no_change_is_silent(self):
        """오탐이 나면 경고가 소음이 되어 아무도 읽지 않게 된다."""
        self.assertNotIn("채널 무결성", call_hook("channel-watch", {}))

    def test_peer_change_is_detected_without_any_command(self):
        """1층이 절대 못 잡는 방법 — 명령 문자열 자체가 없는 파이썬 직접 쓰기."""
        with open(PEER, "a", encoding="utf-8") as f:
            f.write("\n<!-- integrity test -->\n")
        out = call_hook("channel-watch", {})
        self.assertIn("채널 무결성", out)
        self.assertIn("codex.md", out)

    def test_own_channel_change_is_not_flagged(self):
        with open(MINE, "a", encoding="utf-8") as f:
            f.write("\n<!-- own channel -->\n")
        self.assertNotIn("채널 무결성", call_hook("channel-watch", {}))


if __name__ == "__main__":
    unittest.main()
