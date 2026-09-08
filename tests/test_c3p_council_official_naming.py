from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_TERM = "C3P 협의체"
FIRST_MENTION = (
    "C3P 협의체(C3P Council, Codex·Claude Code·Antigravity가 함께 검토하고 실행하는 "
    "3도구 협업 체계)"
)


class C3PCouncilOfficialNamingTests(unittest.TestCase):
    def test_all_three_project_rule_adapters_use_the_official_term(self) -> None:
        for relative_path in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            with self.subTest(path=relative_path):
                content = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn(OFFICIAL_TERM, content)
                self.assertIn("codex-3p-orchestrator", content)
                self.assertIn(FIRST_MENTION, content)

    def test_user_guide_separates_repository_runtime_and_consensus(self) -> None:
        guide = (
            ROOT / "docs" / "35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md"
        ).read_text(encoding="utf-8")
        self.assertIn(FIRST_MENTION, guide)
        self.assertIn("프로젝트 존재", guide)
        self.assertIn("세 도구 연결", guide)
        self.assertIn("세 도구 합의", guide)
        self.assertIn("resubmit: false", guide)
        self.assertIn("사용자는 지시하고 승인하는 주체", guide)
    def test_readme_uses_official_naming_and_updated_metrics(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(OFFICIAL_TERM, readme)
        self.assertIn("codex-3p-orchestrator", readme)
        self.assertIn(FIRST_MENTION, readme)
        self.assertIn("Unit_Tests-269_Passed", readme)
        self.assertIn("csc_work_item.py", readme)
        self.assertIn("c3p_local_llm.py", readme)
        self.assertNotIn("Unit_Tests-237_Passed", readme)
        self.assertNotIn("Unit_Tests-267_Passed", readme)
        self.assertNotIn("Unit_Tests-268_Passed", readme)

    def test_readme_includes_budget_saving_os_section(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("C3P 비대칭 쿼터 예산절약 모드", readme)
        self.assertIn("docs/49_C3P_BUDGET_SAVING_MODE_AND_GIT_COORDINATION_RESEARCH.md", readme)
        self.assertIn("docs/38_C3P_DELEGATED_REPORTING_AND_SPOKESPERSON_ARCHITECTURE.md", readme)
        self.assertIn("docs/39_C3P_OLLAMA_ZERO_TOKEN_HARNESS_INTEGRATED_SPEC.md", readme)
        self.assertIn("docs/42_C3P_RCS_BENCHMARK_RESULTS.md", readme)
        self.assertIn("docs/44_C3P_AUTOMATIC_WORK_COORDINATION_IMPLEMENTATION_AND_EVIDENCE.md", readme)


if __name__ == "__main__":
    unittest.main()
