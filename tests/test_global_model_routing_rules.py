"""3대 도구의 모델·추론 배차 글로벌 규칙이 같은 안전 계약을 유지하는지 검사한다."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GlobalModelRoutingRuleTests(unittest.TestCase):
    def test_shared_safety_contract_is_present_in_all_tool_rules(self):
        rules = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
        }
        required = {
            "AGENTS.md": (
                "결정론적 모델·추론 배차",
                "현재 턴 교체 금지",
                "실험 전 비활성",
            ),
            "CLAUDE.md": (
                "모델·추론 배차",
                "작업 경계의 새 세션",
                "비교 실험 통과 전까지 비활성",
            ),
            "GEMINI.md": (
                "모델·추론 배차",
                "병렬 폭을 1로 제한",
                "비교 실험 통과 전까지 비활성",
            ),
        }
        for filename, clauses in required.items():
            with self.subTest(filename=filename):
                for clause in clauses:
                    self.assertIn(clause, rules[filename])

    def test_all_adapters_point_to_the_same_project_canonical_design(self):
        canonical = ROOT / "docs" / "29_C3P_AUTONOMOUS_MODEL_AND_REASONING_ROUTING_DESIGN.md"
        self.assertTrue(canonical.is_file())
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(canonical.name, agents)
        for filename in ("CLAUDE.md", "GEMINI.md"):
            text = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("AGENTS.md", text)


if __name__ == "__main__":
    unittest.main()
