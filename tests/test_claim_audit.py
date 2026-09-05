"""실시간 주장 감사기 회귀 테스트.

각 규칙은 **오늘 실제로 일어난 사건**에서 뽑았다. 그래서 각 테스트는
"이 사건이 다시 일어나면 잡히는가" 를 묻는다. 상상한 시나리오가 아니다.

가장 중요한 테스트는 마지막 두 개다 —
감사기가 정직한 메시지를 막지 않는지, 그리고 자기 한계를 숨기지 않는지.
막지 말아야 할 것을 막으면 사람들은 감사기를 꺼 버린다.
한계를 숨기면 '통과' 가 '참' 으로 읽혀 감사기 자체가 새로운 거짓말이 된다.
"""

from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import csc_audit  # noqa: E402


def rules(body: str, msg_type: str = "RESULT") -> set:
    return {f["rule"] for f in csc_audit.audit(body, msg_type)["findings"]}


class TestRulesCatchTheirOriginalIncident(unittest.TestCase):
    """각 규칙이 자기 출처 사건을 실제로 잡는지 확인한다."""

    def test_r1_phantom_file(self):
        """실제 사건: 'src/app.py core implementation completed with exit code 0'.
        그 파일은 존재한 적이 없다."""
        self.assertIn("R1", rules("src/app.py core implementation completed with exit code 0"))

    def test_r2_wrong_line_count(self):
        """실제 사건: app/index.html 을 1074줄이라 보고. 실제 346줄."""
        target = os.path.join(PROJECT_ROOT, "app", "index.html")
        if not os.path.exists(target):
            self.skipTest("app/index.html 없음")
        self.assertIn("R2", rules("app/index.html 을 읽었다. 9999 lines 확인. 검토 완료"))

    def test_r3_stale_hash(self):
        """실제 사건: tree 해시를 보낸 뒤 계속 편집해 4회 낡았다."""
        fake = "0" * 40
        self.assertIn("R3", rules(f"검증하라. tree {fake} 확인 완료"))

    def test_r5_unanimity_without_per_member_evidence(self):
        """실제 사건 020: 유령 만장일치. 사용자 인용으로 위반 확정."""
        self.assertIn("R5", rules("3자 만장일치로 가결됐다. 진행하겠다"))

    def test_r6_success_without_verification(self):
        """실제 사건: '발신 완료' 라고 출력했으나 그건 자기 echo 였다."""
        self.assertIn("R6", rules("요청하신 작업을 모두 완료했습니다"))


class TestAuditorDoesNotBlockHonestMessages(unittest.TestCase):
    """오탐이 잦으면 사람들은 감사기를 끈다. 끄면 없는 것과 같다."""

    def test_future_tense_is_not_a_completion_claim(self):
        self.assertNotIn("R6", rules("작업이 완료되면 결과를 보고하겠습니다"))

    def test_planned_file_is_not_a_phantom(self):
        self.assertNotIn("R1", rules("src/app.py 를 만들 예정이다. 완료되면 보고하겠다"))

    def test_hash_quoted_as_stale_is_allowed(self):
        """낡았다고 밝히며 인용하는 것은 정직한 사용이다."""
        fake = "0" * 40
        self.assertNotIn("R3", rules(f"이전 값 {fake} 은 낡았다. 지금은 다르다"))

    def test_unanimity_with_message_ids_is_allowed(self):
        body = ("3자 만장일치. 근거: MSG-20260905-140300 (codex 찬성), "
                "MSG-20260905-142708 (claude 찬성), MSG-20260904-050623 (antigravity 찬성)")
        self.assertNotIn("R5", rules(body))

    def test_completion_with_evidence_is_allowed(self):
        self.assertNotIn("R6", rules("pytest tests -q 실행. 104 passed. 완료"))

    def test_plain_question_is_not_flagged(self):
        self.assertEqual(rules("이 부분 어떻게 생각해?", "PROPOSAL"), set())


class TestAuditorIsHonestAboutItself(unittest.TestCase):
    """감사기가 자기 한계를 숨기면 '통과' 가 '참' 으로 읽힌다."""

    def test_result_always_lists_blind_spots(self):
        result = csc_audit.audit("아무 내용", "PROPOSAL")
        self.assertTrue(result["blind_spots"], "못 잡는 것을 밝히지 않았다")
        self.assertGreaterEqual(len(result["blind_spots"]), 3)

    def test_pass_report_does_not_claim_truth(self):
        text = csc_audit.report(csc_audit.audit("이 부분 어떻게 생각해?", "PROPOSAL"))
        self.assertIn("규칙에 걸리지 않았다", text,
                      "'통과' 를 '참' 으로 읽히게 두면 안 된다")

    def test_every_finding_says_how_it_was_checked(self):
        """근거 없는 지적은 그 자체가 또 하나의 주장일 뿐이다."""
        for f in csc_audit.audit("src/app.py 구현 완료. 3자 만장일치.", "RESULT")["findings"]:
            with self.subTest(f["rule"]):
                self.assertTrue(f["how"].strip(), "확인 방법이 없다")
                self.assertTrue(f["fix"].strip(), "해야 할 일이 없다")

    def test_high_severity_blocks_but_low_does_not(self):
        self.assertEqual(csc_audit.audit("src/app.py 구현 완료", "RESULT")["verdict"], "차단")
        self.assertEqual(csc_audit.audit("이 부분 어떻게 생각해?", "PROPOSAL")["verdict"], "통과")

    def test_selftest_passes(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = csc_audit.selftest()
        self.assertEqual(rc, 0, buf.getvalue())


class TestAuditorIsWiredIntoTheSendPath(unittest.TestCase):
    """감사기가 존재만 하고 호출되지 않으면 없는 것과 같다."""

    def test_send_message_calls_the_auditor(self):
        with open(os.path.join(PROJECT_ROOT, "csc.py"), encoding="utf-8") as f:
            source = f.read()
        head = source[source.index("def send_message("):]
        head = head[:head.index("msg_types = [")]
        self.assertIn("csc_audit", head, "발신 경로에서 감사기를 부르지 않는다")
        self.assertIn("차단", head, "차단 판정을 처리하지 않는다")


if __name__ == "__main__":
    unittest.main()
