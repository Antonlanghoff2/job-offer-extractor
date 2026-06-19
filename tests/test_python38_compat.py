# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
import unittest


class Python38CompatibilityTest(unittest.TestCase):
    def test_modules_import_cleanly(self) -> None:
        modules = [
            "src.cv_parser.section_detector",
            "src.cv_parser.block_builder",
            "src.cv_parser.parser",
            "src.services.cv_parser",
            "src.user_portal",
            "src.web_app",
        ]
        for module_name in modules:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)

    def test_web_app_import_command(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "from src.web_app import app; print('Import OK')"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Import OK", result.stdout)

    def test_gunicorn_can_load_app(self) -> None:
        gunicorn = shutil.which("gunicorn")
        if gunicorn is None:
            self.skipTest("gunicorn non disponible")
        result = subprocess.run(
            [
                gunicorn,
                "--workers",
                "1",
                "--bind",
                "127.0.0.1:8001",
                "--timeout",
                "120",
                "--access-logfile",
                "-",
                "--error-logfile",
                "-",
                "--check-config",
                "src.web_app:app",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
