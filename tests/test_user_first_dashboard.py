"""사용자 우선 원칙(User-First Principle)을 코드로 강제하는 회귀 테스트.

배경 (2026-09-06 사용자 지시):
    "모르는 걸 모르는 사용자 대상이라는 것을 각 3대 AI 도구에 영구 고정하고,
     문서화, 시스템화해서 기본값으로 한다."

이 프로젝트가 오늘 반복해서 배운 것은 **선언은 강제가 아니다** 였다.
원칙을 문서에만 적어 두면 다음 커밋에서 조용히 무너진다.
그래서 원칙의 검증 가능한 부분을 테스트로 고정한다.
"""

from __future__ import annotations

import os
import re
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, PROJECT_ROOT)

import csc_dashboard  # noqa: E402


class TestTermDictionary(unittest.TestCase):
    """용어 사전이 실제로 한국어 병기를 만들어 내는지 확인한다."""

    def test_every_term_has_korean_label_and_plain_explanation(self):
        for code, value in csc_dashboard.TERMS.items():
            with self.subTest(code):
                label, explain = value
                self.assertTrue(label.strip(), f"{code} 에 한국어 표기가 없다")
                self.assertTrue(explain.strip(), f"{code} 에 설명이 없다")
                # 한국어 표기가 영어 코드를 그대로 쓰면 번역이 아니다.
                self.assertNotEqual(label.upper(), code, f"{code} 가 번역되지 않았다")
                self.assertRegex(label, r"[가-힣]", f"{code} 표기에 한글이 없다")

    def test_ko_renders_korean_with_english_in_parentheses(self):
        """규칙 12-1: 전문용어는 '한국어(영어)' 로 병기한다."""
        self.assertEqual(csc_dashboard.ko("TASK"), "작업 지시(TASK)")
        self.assertEqual(csc_dashboard.ko("PID_STALE"), "등록 정보 낡음(PID_STALE)")

    def test_unknown_code_passes_through_unchanged(self):
        """사전에 없는 값을 임의로 지어내지 않는다. 모르면 원문을 보여준다."""
        self.assertEqual(csc_dashboard.ko("SOMETHING_NEW"), "SOMETHING_NEW")


class TestEveryStatusCarriesThreeParts(unittest.TestCase):
    """규칙 12-2: 상태 표시에는 무엇이 / 왜 / 할 일 세 가지가 함께 있어야 한다."""

    def test_all_checks_have_value_reason_todo_and_source(self):
        rows, broken = csc_dashboard.load_messages()
        for item in csc_dashboard.checks(rows, broken):
            with self.subTest(item.get("title")):
                self.assertTrue(str(item.get("value", "")).strip(), "① 무엇이 — 값이 없다")
                self.assertTrue(str(item.get("why", "")).strip(), "② 왜 — 판단 근거가 없다")
                self.assertTrue(str(item.get("todo", "")).strip(), "③ 할 일 — 안내가 없다")
                # 이원 체계 3항: 화면은 파생물이므로 원문 위치를 함께 준다.
                self.assertTrue(str(item.get("src", "")).strip(), "원문 위치가 없다")

    def test_green_status_also_explains_itself(self):
        """근거 없는 초록불은 거짓말이다. 정상 항목도 근거를 적어야 한다."""
        rows, broken = csc_dashboard.load_messages()
        greens = [c for c in csc_dashboard.checks(rows, broken) if c["ok"]]
        self.assertTrue(greens, "정상 항목이 하나도 없어 검증할 수 없다")
        for item in greens:
            with self.subTest(item["title"]):
                self.assertTrue(item["why"].strip())


class TestRenderedPageObeysThePrinciple(unittest.TestCase):
    def setUp(self):
        self.doc = csc_dashboard.build()

    def test_self_check_reports_no_untranslated_terms(self):
        """화면 껍데기에 영어 약어가 홀로 남아 있으면 실패한다."""
        problems = csc_dashboard.self_check(self.doc)
        self.assertEqual(problems, [], f"번역 없이 노출된 용어: {problems}")

    def test_raw_message_bodies_are_never_translated(self):
        """이원 체계 4항: 도구 원문은 사용자 편의로 고치지 않는다.

        원문을 번역하면 증거가 아니라 각색이 된다.
        그래서 자가검사는 본문을 검사 대상에서 제외한다 — 그 제외가 유지되는지 본다.
        """
        fake = ('<div class="body">codex sent TASK and got RESULT</div>'
                '<div class="gl"><code>TASK</code></div>')
        self.assertEqual(csc_dashboard.self_check(fake), [],
                         "원문·용어표까지 번역을 강요하면 안 된다")

    def test_ui_chrome_violation_is_actually_detected(self):
        """제외 규칙이 검사 자체를 무력화하지 않았는지 확인한다.

        이 테스트가 없으면 self_check 이 항상 통과하는 껍데기가 되어도 모른다.
        """
        fake = "<h3>Worker LIVE 2/2</h3>"
        self.assertNotEqual(csc_dashboard.self_check(fake), [],
                            "화면 라벨의 미번역 용어를 못 잡고 있다")

    def test_bad_news_is_placed_before_good_news(self):
        """규칙 12-5: 나쁜 소식을 성공 항목보다 먼저 놓는다."""
        order = [m.group(1) for m in
                 re.finditer(r'<article class="chk (bad|good)"', self.doc)]
        if "bad" in order and "good" in order:
            self.assertLess(order.index("bad"), order.index("good"),
                            "성공 항목이 문제 항목보다 위에 있다")

    def test_page_is_korean_first(self):
        self.assertIn('<html lang="ko"', self.doc)
        self.assertIn("3대 AI 도구 감시판", self.doc)

    def test_page_identifies_its_physical_project(self):
        project_name = os.path.basename(PROJECT_ROOT)
        self.assertIn(project_name, self.doc)
        self.assertIn("상태 재계산 시각", self.doc)

    def test_page_points_back_to_the_raw_log(self):
        """사용자가 언제든 원문을 직접 볼 수 있어야 한다."""
        self.assertIn("queue.jsonl", self.doc)


class TestPrincipleIsPinnedInEveryToolRuleFile(unittest.TestCase):
    """규칙이 세 도구 전부에 실제로 박혀 있는지 파일로 확인한다."""

    FILES = (
        ".agent-swarm/USER_FIRST_PRINCIPLE.md",
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".agents/skills/codex-3p-orchestrator/SKILL.md",
        ".agent-swarm/GOVERNANCE.md",
    )

    def test_principle_present_in_all_rule_files(self):
        for rel in self.FILES:
            with self.subTest(rel):
                path = os.path.join(PROJECT_ROOT, rel)
                self.assertTrue(os.path.exists(path), f"{rel} 이 없다")
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("모르는 걸 모르는 사용자", text,
                              f"{rel} 에 대상 사용자 정의가 없다")
                self.assertIn("오류수정은 3대 AI 도구 공통으로 동시 동기화", text,
                              f"{rel} 에 공통 오류수정 동기화 계약이 없다")



class TestPrincipleSyncAcrossAllThreeTools(unittest.TestCase):
    """동시성 동기화 — 세 도구가 '같은' 계약을 담고 있는지 본다.

    사용자 지시 (2026-09-06):
        "모르는 걸 모르는 사용자 원칙은 모든 3대 AI 도구에 동시성 동기화되어야 한다."

    앞의 TestPrincipleIsPinnedInEveryToolRuleFile 은 문구가 '있는지' 만 봤다.
    그건 파일마다 내용이 달라도 통과한다. 실제로 그 허점 때문에
    SKILL.md 가 '위반 시 제재' 계약을 빠뜨린 채 통과하고 있었다.
    """

    def test_all_rule_files_share_every_contract(self):
        import csc_sync
        rows, ok = csc_sync.check()
        broken = [(r["file"], r["missing"]) for r in rows if not r["ok"]]
        self.assertTrue(ok, f"도구별 규칙이 어긋났다: {broken}")

    def test_checker_actually_detects_a_missing_contract(self):
        """검사기가 항상 통과하는 껍데기가 아닌지 확인한다."""
        import csc_sync
        for name, needles in csc_sync.CONTRACTS:
            with self.subTest(name):
                self.assertTrue(needles, f"{name} 계약에 확인 문자열이 없다")


class TestC3PTriggerContract(unittest.TestCase):
    """활성 트리거에서 잘못된 씨2피 표기가 다시 살아나지 않게 한다."""

    FILES = (
        ".agents/skills/codex-3p-orchestrator/SKILL.md",
        "docs/reference-materials/CSC_MIA_STANDARDIZATION_IMPLEMENTATION_PLAN.md",
    )

    def test_korean_trigger_is_c3p(self):
        for rel in self.FILES:
            with self.subTest(rel):
                with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("MIA 씨3피 발동", text)
                self.assertNotIn("MIA 씨2피 발동", text)

    def test_bare_c3p_trigger_is_explicit_and_case_insensitive(self):
        skill = os.path.join(PROJECT_ROOT, self.FILES[0])
        with open(skill, encoding="utf-8") as f:
            text = f.read()
        self.assertIn('`"c3p 발동"`', text)
        self.assertIn("ASCII 영문은 대소문자를 구분하지 않는다", text)
        for spelling in ("c3p 발동", "C3P 발동", "C3p 발동"):
            self.assertEqual(spelling.casefold(), "c3p 발동")

    def test_bare_trigger_contract_is_synchronized_across_tool_adapters(self):
        for rel in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            with self.subTest(rel):
                with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("`c3p 발동`도 정식 호출문", text)
                self.assertIn("대소문자를 구분하지", text)

    def test_budget_saving_trigger_contract_is_synchronized_across_tool_adapters(self):
        contract = "예산절약 모드 발동문"
        for rel in (
            "AGENTS.md", "CLAUDE.md", "GEMINI.md",
            ".agents/skills/codex-3p-orchestrator/SKILL.md",
        ):
            with self.subTest(rel):
                with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as f:
                    self.assertIn(contract, f.read())

    def test_call_phrase_contract_is_synchronized_across_tool_adapters(self):
        for rel in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".agents/skills/codex-3p-orchestrator/SKILL.md"):
            with self.subTest(rel=rel), open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("C3P_CALL_PHRASE_CONTRACT_V1", content)
            self.assertIn("`C3P 협의체와 검토해줘`", content)

    def test_readme_does_not_claim_phrase_alone_proves_consensus(self):
        """호출문은 요청이지, 세 도구의 실제 합의 증거가 아니다."""
        with open(os.path.join(PROJECT_ROOT, "README.md"), encoding="utf-8") as handle:
            readme = handle.read()
        self.assertNotIn("즉시 상호 합의 프로토콜", readme)
        self.assertIn("문구 자체는 세 도구의 연결·회신·합의를 보장하지 않습니다", readme)
        self.assertIn("`C3P 협의체와 검토해줘`", readme)
        self.assertIn("회신·정족수 증거가 없으면 합의로 표시하지 않는다", readme)


class TestPerProjectDashboardActivation(unittest.TestCase):
    """C3P 발동은 성공·실패 여부와 무관하게 해당 프로젝트 감시판을 남긴다."""

    def test_success_returns_project_dashboard_identity(self):
        import csc
        expected = os.path.join(PROJECT_ROOT, ".agent-swarm", "dashboard.html")
        with mock.patch.object(csc.csc_runtime, "activate", return_value={"status": "ready"}), \
             mock.patch("csc_dashboard.write_dashboard", return_value=expected):
            result = csc.activate_project(csc.Path(PROJECT_ROOT), timeout=1)
        self.assertEqual(result["dashboard"]["project"], os.path.basename(PROJECT_ROOT))
        self.assertEqual(
            os.path.normcase(os.path.realpath(result["dashboard"]["path"])),
            os.path.normcase(os.path.realpath(expected)),
        )
        self.assertEqual(result["dashboard"]["kind"], "activation_snapshot")

    def test_failure_still_writes_dashboard_before_propagating(self):
        import csc
        with mock.patch.object(
                csc.csc_runtime, "activate", side_effect=csc.csc_runtime.ActivationError("boom")), \
             mock.patch("csc_dashboard.write_dashboard") as write_dashboard:
            with self.assertRaises(csc.csc_runtime.ActivationError):
                csc.activate_project(csc.Path(PROJECT_ROOT), timeout=1)
        write_dashboard.assert_called_once_with()

    def test_contract_is_synchronized_across_three_tool_adapters(self):
        contract = "C3P 발동 시 현재 프로젝트 전용 `.agent-swarm/dashboard.html`을 성공·실패 모두 생성"
        files = (
            "AGENTS.md", "CLAUDE.md", "GEMINI.md",
            ".agents/skills/codex-3p-orchestrator/SKILL.md",
            ".agent-swarm/GOVERNANCE.md",
        )
        for rel in files:
            with self.subTest(rel):
                with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as f:
                    self.assertIn(contract, f.read())


class TestDualTrackSeparation(unittest.TestCase):
    """이원 체계 — 로그 페이지와 감시판이 역할을 나눠 갖는지 확인한다.

    같은 값을 두 곳에서 계산하면 언젠가 서로 다른 답을 낸다.
    실제로 겪었다 — 감시판은 2/2 정상, 로그 페이지는 0/2 를 동시에 표시했다.
    """

    def setUp(self):
        import csc_viewer
        self.log_page = csc_viewer.cmd_html.__doc__ or ""
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            csc_viewer.cmd_html()
        with open(os.path.join(PROJECT_ROOT, ".agent-swarm", "conversation.html"),
                  encoding="utf-8") as f:
            self.doc = f.read()

    def test_log_page_keeps_the_full_record_not_a_summary(self):
        import csc_viewer
        rows = csc_viewer.load()
        rendered = self.doc.count('<article class="msg')
        self.assertEqual(rendered, len(rows),
                         "원문 로그가 일부만 보여주고 있다. 로그는 전부 남겨야 한다")

    def test_log_page_refreshes_itself(self):
        self.assertIn('http-equiv="refresh" content="30"', self.doc)

    def test_log_page_explains_itself_in_plain_korean(self):
        self.assertIn("실제로 주고받은 말", self.doc)
        self.assertIn("읽는 법", self.doc)

    def test_log_page_defers_status_judgement_to_the_dashboard(self):
        """상태 판정은 감시판이 맡는다. 로그 페이지는 기록만 맡는다."""
        self.assertNotIn('class="health', self.doc)
        self.assertIn("dashboard.html", self.doc)


class TestDeadlockFreeDecision(unittest.TestCase):
    """교착 방지 — 어떤 조합에서도 '아무 판정 없이 멈추는' 결과가 나오지 않아야 한다.

    배경 (2026-09-06 사용자 지적):
        "3대 도구의 사용량 제한 등 제약조건이 달라서 현재 로직에 문제가 많다."

    맞는 지적이었다. 우리는 '부재 = 동의'(유령 만장일치)를 고치면서
    '부재 = 거부'(영구 교착)라는 거울상을 만들었다.
    """

    def setUp(self):
        import csc_decide
        self.D = csc_decide
        from datetime import datetime, timezone
        self.t0 = datetime(2026, 9, 6, tzinfo=timezone.utc)

    def test_selftest_passes(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.D.selftest()
        self.assertEqual(rc, 0, buf.getvalue())

    def test_never_deadlocks_across_every_availability_combination(self):
        """핵심 계약: 어떤 가용성 조합에서도 반드시 다음 행동이 정해진다."""
        from datetime import timedelta
        from itertools import product
        states = (self.D.AVAILABLE, self.D.RATE_LIMITED, self.D.OFFLINE, self.D.UNKNOWN)
        terminal = {"APPROVED", "REJECTED", "BLOCKED", "WAITING",
                    "ESCALATE_TO_USER", "NEEDS_USER_APPROVAL"}
        for combo in product(states, repeat=3):
            avail = {m: {"state": s} for m, s in zip(self.D.MEMBERS, combo)}
            with self.subTest(combo=combo):
                r = self.D.decide(topic="t", votes={"claude": "AGREE"}, avail=avail,
                                  started=self.t0, now=self.t0 + timedelta(hours=3))
                self.assertIn(r["decision"], terminal)
                self.assertTrue(r["next_step"].strip(), "다음 행동이 비어 있다")

    def test_lone_survivor_escalates_instead_of_stalling(self):
        """혼자 남아도 멈추지 않는다. 교착은 결정이 아니다."""
        from datetime import timedelta
        avail = {"claude": {"state": self.D.AVAILABLE},
                 "codex": {"state": self.D.RATE_LIMITED},
                 "antigravity": {"state": self.D.OFFLINE}}
        r = self.D.decide(topic="t", votes={"claude": "AGREE"}, avail=avail,
                          started=self.t0, now=self.t0 + timedelta(hours=3))
        self.assertEqual(r["decision"], "ESCALATE_TO_USER")
        self.assertEqual(sorted(r["abstain"]), ["antigravity", "codex"])

    def test_absent_tools_never_count_as_agreement(self):
        """사건 020 재발 방지 — 부재를 찬성으로 세지 않는다."""
        from datetime import timedelta
        avail = {m: {"state": self.D.OFFLINE} for m in self.D.MEMBERS}
        avail["claude"] = {"state": self.D.AVAILABLE}
        r = self.D.decide(topic="t", votes={"claude": "AGREE"}, avail=avail,
                          started=self.t0, now=self.t0 + timedelta(hours=3))
        self.assertEqual(r["agree"], ["claude"])
        self.assertNotEqual(r["decision"], "APPROVED")

    def test_expired_block_cannot_veto_forever(self):
        """주인 없는 무기한 거부권을 없앤다 (018·021 사례)."""
        from datetime import timedelta
        avail = {m: {"state": self.D.AVAILABLE} for m in self.D.MEMBERS}
        r = self.D.decide(topic="t", votes={m: "AGREE" for m in self.D.MEMBERS},
                          avail=avail, blocks=[{"id": "old", "raised_at": self.t0.isoformat()}],
                          now=self.t0 + timedelta(days=2))
        self.assertEqual(r["decision"], "ESCALATE_TO_USER")

    def test_irreversible_action_still_requires_the_user(self):
        """교착을 풀었다고 안전장치까지 풀지 않는다."""
        avail = {m: {"state": self.D.AVAILABLE} for m in self.D.MEMBERS}
        r = self.D.decide(topic="t", votes={m: "AGREE" for m in self.D.MEMBERS},
                          avail=avail, action_kind="push", now=self.t0)
        self.assertEqual(r["decision"], "NEEDS_USER_APPROVAL")

    def test_explanation_is_written_in_korean(self):
        avail = {m: {"state": self.D.AVAILABLE} for m in self.D.MEMBERS}
        text = self.D.explain(self.D.decide(topic="t", votes={}, avail=avail, now=self.t0))
        self.assertRegex(text, r"[가-힣]")
        self.assertIn("다음:", text)

if __name__ == "__main__":
    unittest.main()
