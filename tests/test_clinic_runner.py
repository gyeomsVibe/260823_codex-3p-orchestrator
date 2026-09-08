"""진단 실행기 회귀 테스트.

가장 중요한 계약 하나: **진단이 0개면 통과라고 말하지 않는다.**

이 프로젝트는 하루 종일 같은 형태의 거짓말과 싸웠다 —
아무것도 검사하지 않고 "이상 없음" 을 보고하는 것.
vibe-clinic 이 기본으로 만들어 준 예시 진단이 정확히 그랬다.
무조건 OK 를 돌려주고 건강도 100% 를 찍었다. 그래서 지웠다.

여기서 그 계약이 코드로 지켜지는지 확인한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import csc_clinic  # noqa: E402


class TestZeroDiagnosticsIsFailure(unittest.TestCase):
    """검사할 것이 없는 것과 이상이 없는 것은 다르다."""

    def test_no_diagnostics_reports_error_not_ok(self):
        with mock.patch.object(csc_clinic, "diagnostics", return_value=[]), \
             mock.patch.object(csc_clinic, "record"):
            out = csc_clinic.run_all()
        self.assertEqual(out["status"], "ERROR",
                         "진단 0개를 통과로 보고하고 있다")
        self.assertEqual(out["total"], 0)
        self.assertIn("검사한 것이 없으므로", out["reason"])

    def test_zero_diagnostics_never_claims_health(self):
        """건강도를 붙이지 않는다. 0개 검사에 건강도는 의미가 없다."""
        with mock.patch.object(csc_clinic, "diagnostics", return_value=[]), \
             mock.patch.object(csc_clinic, "record"):
            out = csc_clinic.run_all()
        self.assertNotIn("health_percent", out)


class TestPhaseGate(unittest.TestCase):
    """만드는 단계에서는 돌지 않고, 고치는 단계에서는 돈다."""

    def test_phase_follows_the_visible_file(self):
        self.assertTrue(csc_clinic.PHASE_FILE.endswith("BUILD_PHASE"))
        self.assertEqual(csc_clinic.build_phase(),
                         os.path.exists(csc_clinic.PHASE_FILE))

    def test_shared_phase_source_with_auditor(self):
        """감사기와 같은 파일을 봐야 한다. 두 곳이 다른 단계를 믿으면 안 된다."""
        import csc_audit
        self.assertEqual(os.path.normcase(csc_clinic.PHASE_FILE),
                         os.path.normcase(csc_audit.PHASE_FILE))


class TestRealDiagnosticsExist(unittest.TestCase):
    """진단 항목이 실제로 있어야 한다. 껍데기만 있으면 안 된다."""

    def test_at_least_four_diagnostics_present(self):
        files = csc_clinic.diagnostics()
        self.assertGreaterEqual(len(files), 4,
                                f"진단이 부족하다: {files}")

    def test_helper_files_are_not_counted_as_diagnostics(self):
        """_shared.js 는 공용 도구지 진단이 아니다."""
        self.assertNotIn("_shared.js", csc_clinic.diagnostics())

    def test_no_unconditional_pass_diagnostic(self):
        """무조건 OK 를 돌려주는 진단이 다시 생기지 않았는지 본다.

        vibe-clinic 기본 예시가 그랬다 — 검사 없이 OK, 건강도 100%.
        그런 것이 하나라도 섞이면 전체 건강도가 거짓이 된다.
        """
        import re
        diag_dir = os.path.join(PROJECT_ROOT, ".vibe-clinic", "diagnostics")
        for name in csc_clinic.diagnostics():
            with self.subTest(name):
                with open(os.path.join(diag_dir, name), encoding="utf-8") as f:
                    src = f.read()
                # 무언가를 실제로 재는 흔적이 있어야 한다.
                measures = bool(re.search(r"run\(|readFileSync|existsSync", src))
                self.assertTrue(measures, f"{name} 이 아무것도 측정하지 않는다")

    def test_regression_diagnostic_uses_repository_test_runner(self):
        path = os.path.join(PROJECT_ROOT, ".vibe-clinic", "diagnostics",
                            "01_regression.clinic.js")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("python -m unittest discover -s tests -q", source)
        self.assertNotIn("python -m pytest", source)


class TestResultsAlwaysDeclareLimits(unittest.TestCase):
    """통과를 참으로 읽히게 두지 않는다."""

    def test_render_warns_that_ok_is_not_truth(self):
        out = {"at": "x", "phase": "수정", "total": 1, "ok": 1, "warning": 0,
               "error": 0, "status": "OK", "health_percent": 100,
               "results": [{"name": "t", "status": "OK", "details": "d"}]}
        text = csc_clinic.render(out)
        self.assertIn("검사한 범위에서 못 찾았다", text)

    def test_render_shows_reason_when_nothing_ran(self):
        text = csc_clinic.render({"at": "x", "phase": "수정", "total": 0,
                                  "status": "ERROR", "reason": "진단 항목이 없습니다",
                                  "results": []})
        self.assertIn("진단 항목이 없습니다", text)


class TestMilestoneReports(unittest.TestCase):
    def test_slug_cannot_escape_report_directory(self):
        slug = csc_clinic.milestone_slug("../../릴리스 후보")
        self.assertEqual(slug, "릴리스_후보")
        self.assertNotIn("/", slug)
        self.assertNotIn("\\", slug)
        with self.assertRaises(ValueError):
            csc_clinic.milestone_slug("   ")

    def test_git_head_failure_is_visible_instead_of_crashing(self):
        failure = subprocess.TimeoutExpired("git", 5)
        with mock.patch.object(csc_clinic.subprocess, "run", side_effect=failure):
            head, detail = csc_clinic.current_git_head()
        self.assertEqual(head, "UNKNOWN")
        self.assertIn("TimeoutExpired", detail)

    def test_report_records_label_head_and_result_without_overwrite(self):
        out = {"at": "x", "phase": "수정", "total": 1, "ok": 1,
               "warning": 0, "error": 0, "status": "OK",
               "health_percent": 100, "results": []}
        instant = datetime(2026, 9, 8, 10, 0, 0, 123456, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(csc_clinic, "REPORT_DIR", temp_dir), \
             mock.patch.object(csc_clinic, "current_git_head",
                               return_value=("a" * 40, "")):
            path = csc_clinic.write_milestone_report("../../release", out, instant)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertEqual(os.path.dirname(path), temp_dir)
            self.assertIn('"../../release"', text)
            self.assertIn("`" + "a" * 40 + "`", text)
            self.assertIn('"status": "OK"', text)
            with self.assertRaises(FileExistsError):
                csc_clinic.write_milestone_report("../../release", out, instant)

    def test_explicit_milestone_runs_during_build_phase_and_preserves_warning(self):
        warning = {"status": "WARNING", "phase": "구현", "total": 1,
                   "ok": 0, "warning": 1, "error": 0,
                   "health_percent": 0, "results": []}
        with mock.patch.object(sys, "argv", ["csc_clinic.py", "--milestone", "m1"]), \
             mock.patch.object(csc_clinic, "build_phase", return_value=True), \
             mock.patch.object(csc_clinic, "run_all", return_value=warning) as run_all, \
             mock.patch.object(csc_clinic, "render", return_value="WARNING"), \
             mock.patch.object(csc_clinic, "write_milestone_report",
                               return_value="draft.md") as write_report, \
             mock.patch("builtins.print"):
            self.assertEqual(csc_clinic.main(), 1)
        run_all.assert_called_once_with()
        write_report.assert_called_once_with("m1", warning)


if __name__ == "__main__":
    unittest.main()
