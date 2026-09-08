"""실시간 감시 필터 회귀 테스트.

가장 중요한 계약: **소음을 만들지 않는다.**

알림이 잦으면 사람은 알림을 끈다. 끄면 없는 것과 같다.
이 프로젝트는 그 교훈을 두 번 얻었다 —
거짓 빨간불(없는 경고를 매번 띄움), 그리고 연결 부기가 대화보다 12배 많았던 로그.

그래서 필터가 느슨해지는 방향의 변경을 여기서 막는다.
"""

from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import csc_watch  # noqa: E402

ME = "claude-code-6c"


def msg(sender, recipient, mtype="TASK"):
    return {"sender": sender, "recipient": recipient, "type": mtype, "body": "x"}


class TestOnlyRelevantMessagesAlert(unittest.TestCase):

    def test_peer_message_to_me_alerts(self):
        self.assertTrue(csc_watch.is_for_me(msg("codex", "claude"), ME))

    def test_broadcast_alerts(self):
        self.assertTrue(csc_watch.is_for_me(msg("antigravity", "all"), ME))

    def test_my_own_message_never_alerts(self):
        """내가 보낸 것에 내가 알림을 받으면 그건 메아리다."""
        for sender in ("claude-code-6c", "claude", "claude-code-9b"):
            with self.subTest(sender):
                self.assertFalse(csc_watch.is_for_me(msg(sender, "codex"), ME))

    def test_machine_records_never_alert(self):
        """프로그램이 남긴 흔적은 사람의 말이 아니다.

        실측 근거: 이 프로젝트의 연결 부기가 1,930건으로 실제 대화 161건의 12배였다.
        그걸 전부 알렸다면 알림은 즉시 무시됐을 것이다.
        """
        for t in ("EVENT", "AGENT_JOINED", "AGENT_LEFT", "REGISTER"):
            with self.subTest(t):
                self.assertFalse(csc_watch.is_for_me(msg("codex", "all", t), ME))

    def test_message_to_someone_else_does_not_alert(self):
        self.assertFalse(csc_watch.is_for_me(msg("codex", "antigravity"), ME))


class TestFilterActuallyReducesNoise(unittest.TestCase):
    """필터가 이름만 필터가 아닌지 실제 기록으로 확인한다."""

    def test_real_queue_is_substantially_filtered(self):
        import json
        path = os.path.join(PROJECT_ROOT, ".agent-swarm", "messages", "queue.jsonl")
        if not os.path.exists(path):
            self.skipTest("기록 파일 없음")
        total = kept = 0
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except Exception:
                    continue
                total += 1
                if csc_watch.is_for_me(m, ME):
                    kept += 1
        self.assertGreater(total, 0)
        # 절반 이상 걸러지지 않으면 필터가 제 역할을 못 하는 것이다.
        self.assertLess(kept, total * 0.5,
                        f"필터가 너무 느슨하다: {total}건 중 {kept}건 통과")


class TestWatcherIsEventDrivenNotPolling(unittest.TestCase):
    """무엇을 얼마나 자주 하는지 계약을 고정한다."""

    def test_default_check_is_cheap(self):
        """파일 줄 수만 센다. 바뀐 게 없으면 아무 일도 하지 않는다.

        주기를 줄이는 것이 답이 아니라는 판단의 근거가 여기 있다 —
        확인 자체가 싸기 때문에 3초 간격이어도 부담이 되지 않는다.
        비싼 것은 확인이 아니라 에이전트를 깨우는 일이다.
        """
        import inspect
        src = inspect.getsource(csc_watch.main)
        self.assertIn("if now <= seen:", src)
        self.assertIn("continue", src)

    def test_starts_from_now_not_from_history(self):
        """시작할 때 지난 메시지를 몰아서 쏟지 않는다. 그게 소음이다."""
        import inspect
        src = inspect.getsource(csc_watch.main)
        self.assertIn("seen = line_count(QUEUE)", src)


if __name__ == "__main__":
    unittest.main()
