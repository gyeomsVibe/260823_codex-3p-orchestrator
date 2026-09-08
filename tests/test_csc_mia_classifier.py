"""Unit tests for MIA Project Classifier (csc_mia_classifier.py)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import csc_mia_classifier


class TestMIAClassifier(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generic_empty_project(self):
        result = csc_mia_classifier.evaluate_project(self.root)
        self.assertEqual(result["status"], "GENERIC")
        self.assertFalse(result["is_fullstack"])
        self.assertFalse(result["should_split"])

    def test_frontend_only_project(self):
        (self.root / "package.json").write_text('{"name": "fe"}', encoding="utf-8")
        (self.root / "index.html").write_text("<!DOCTYPE html>", encoding="utf-8")

        result = csc_mia_classifier.evaluate_project(self.root)
        self.assertEqual(result["status"], "FRONTEND_ONLY")
        self.assertFalse(result["is_fullstack"])
        self.assertFalse(result["should_split"])
        self.assertIn("package.json", result["frontend_indicators"])
        self.assertIn("index.html", result["frontend_indicators"])

    def test_backend_only_project(self):
        (self.root / "requirements.txt").write_text("pytest>=7.0", encoding="utf-8")
        (self.root / "Dockerfile").write_text("FROM python:3.11", encoding="utf-8")

        result = csc_mia_classifier.evaluate_project(self.root)
        self.assertEqual(result["status"], "BACKEND_ONLY")
        self.assertFalse(result["is_fullstack"])
        self.assertFalse(result["should_split"])
        self.assertIn("requirements.txt", result["backend_indicators"])
        self.assertIn("Dockerfile", result["backend_indicators"])

    def test_fullstack_unsplit_recommends_split(self):
        (self.root / "package.json").write_text('{"name": "fe"}', encoding="utf-8")
        (self.root / "requirements.txt").write_text("fastapi>=0.100", encoding="utf-8")

        result = csc_mia_classifier.evaluate_project(self.root)
        self.assertEqual(result["status"], "RECOMMEND_SPLIT")
        self.assertTrue(result["is_fullstack"])
        self.assertTrue(result["should_split"])
        self.assertIsNotNone(result["proposed_paths"]["frontend"])
        self.assertIsNotNone(result["proposed_paths"]["backend"])

    def test_fullstack_already_split(self):
        (self.root / "package.json").write_text('{"name": "root"}', encoding="utf-8")
        (self.root / "requirements.txt").write_text("django", encoding="utf-8")
        (self.root / "frontend").mkdir()
        (self.root / "backend").mkdir()

        result = csc_mia_classifier.evaluate_project(self.root)
        self.assertEqual(result["status"], "ALREADY_SPLIT")
        self.assertTrue(result["is_fullstack"])
        self.assertFalse(result["should_split"])

    def test_provision_requires_split_or_force(self):
        # Generic project without force should fail safely
        res = csc_mia_classifier.provision_folders(self.root, force=False)
        self.assertFalse(res["success"])
        self.assertFalse((self.root / "frontend").exists())
        self.assertFalse((self.root / "backend").exists())

    def test_provision_succeeds_on_split_recommended(self):
        (self.root / "package.json").write_text('{"name": "fe"}', encoding="utf-8")
        (self.root / "requirements.txt").write_text("flask", encoding="utf-8")

        res = csc_mia_classifier.provision_folders(self.root, force=False)
        self.assertTrue(res["success"])
        fe_dir = self.root / "frontend"
        be_dir = self.root / "backend"
        self.assertTrue(fe_dir.is_dir())
        self.assertTrue(be_dir.is_dir())
        self.assertTrue((fe_dir / "README.md").is_file())
        self.assertTrue((be_dir / "README.md").is_file())

    def test_cli_evaluate_and_provision_guards(self):
        # 1. Evaluate returns 0
        ret = csc_mia_classifier.main(["evaluate", "--path", str(self.root), "--json"])
        self.assertEqual(ret, 0)

        # 2. Provision without --apply returns error 2
        ret = csc_mia_classifier.main(["provision", "--path", str(self.root)])
        self.assertEqual(ret, 2)

        # 3. Provision with --apply and --force succeeds
        ret = csc_mia_classifier.main(["provision", "--path", str(self.root), "--apply", "--force"])
        self.assertEqual(ret, 0)
        self.assertTrue((self.root / "frontend").is_dir())
        self.assertTrue((self.root / "backend").is_dir())


if __name__ == "__main__":
    unittest.main()
