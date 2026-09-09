import unittest
from unittest import mock

import csc
from c3p_trigger import (
    classify_call_phrase,
    is_budget_saving_trigger,
    is_runtime_activation_trigger,
    normalize_trigger,
)


class C3PBudgetSavingTriggerTests(unittest.TestCase):
    def test_explicit_korean_variants_and_ascii_case_are_recognized(self):
        for phrase in (
            "C3P 예산절약 모드",
            "c3p 예산절약 모드 발동",
            "  C3p   예산절약  모드  ",
            "예산절약 모드",
            "예산절약 모드 발동",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_budget_saving_trigger(phrase))

    def test_discussion_and_unrelated_text_do_not_activate(self):
        self.assertFalse(is_budget_saving_trigger("예산절약 모드의 설계를 검토한다"))
        self.assertFalse(is_budget_saving_trigger("C3P 예산절약 모드로 만들어 줘"))
        self.assertFalse(is_budget_saving_trigger("c3p 발동"))

    def test_runtime_activation_is_exact_and_case_insensitive(self):
        self.assertTrue(is_runtime_activation_trigger("C3P 발동"))
        self.assertFalse(is_runtime_activation_trigger("c3p"))
        self.assertEqual("council_review_request", classify_call_phrase("C3P 협의체와 검토해줘"))
        self.assertEqual("ambiguous", classify_call_phrase("C3P협의체"))

    def test_cli_runtime_activation_uses_the_same_safe_runtime_path(self):
        with mock.patch.object(csc, "init_swarm"), mock.patch.object(
            csc, "activate_project", return_value={"status": "ready"}
        ) as activate, mock.patch("sys.argv", ["csc.py", "trigger", "C3P 발동"]):
            csc.main()
        activate.assert_called_once()
        self.assertTrue(activate.call_args.kwargs["budget_saving"])

    def test_normalization_is_whitespace_and_case_only(self):
        self.assertEqual("c3p 예산절약 모드", normalize_trigger(" C3P  예산절약 모드 "))
        self.assertTrue(is_budget_saving_trigger("C3P 예산절약 모드"))
        with self.assertRaises(TypeError):
            normalize_trigger(None)  # type: ignore[arg-type]

    def test_cli_trigger_uses_existing_budget_saving_activation_path(self):
        with mock.patch.object(csc, "init_swarm"), mock.patch.object(
            csc, "activate_project", return_value={"status": "ready"}
        ) as activate, mock.patch("sys.argv", ["csc.py", "trigger", "C3P 예산절약 모드"]):
            csc.main()
        activate.assert_called_once()
        self.assertTrue(activate.call_args.kwargs["budget_saving"])

    def test_cli_trigger_user_absence_mode(self):
        armed = {"state": "ARMED", "trigger": "C3P 사용자부재 모드"}
        with mock.patch.object(csc, "init_swarm"), mock.patch.object(
            csc, "activate_project", return_value={"status": "ready"}
        ) as activate, mock.patch.object(csc, "arm_user_absence_mode", return_value=armed) as arm, mock.patch(
            "sys.argv", ["csc.py", "trigger", "C3P 사용자부재 모드"]
        ):
            csc.main()
        activate.assert_called_once()
        self.assertTrue(activate.call_args.kwargs["budget_saving"])
        arm.assert_called_once()

    def test_explicit_user_absence_korean_variants_recognized(self):
        from c3p_trigger import is_user_absence_trigger

        for phrase in (
            "c3p 사용자부재 모드",
            "c3p 사용자부재 모드 발동",
            "  C3P   사용자부재  모드  ",
            "사용자부재 모드",
            "사용자부재 모드 발동",
            "c3p user-absence mode",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_user_absence_trigger(phrase))

        self.assertFalse(is_user_absence_trigger("사용자부재 모드의 개선안"))
        self.assertFalse(is_user_absence_trigger("사용자부재 모드로 작동해 줘"))

    def test_cli_rejects_discussion_without_starting_processes(self):
        with mock.patch.object(csc, "init_swarm") as init, mock.patch.object(
            csc, "activate_project"
        ) as activate, mock.patch(
            "sys.argv", ["csc.py", "trigger", "예산절약 모드의 설계를 검토한다"]
        ):
            with self.assertRaises(SystemExit) as stopped:
                csc.main()
        self.assertEqual(2, stopped.exception.code)
        init.assert_not_called()
        activate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
