#!/usr/bin/env python3
import unittest
from unittest.mock import patch
from ci_change_scope import changed_paths, docs_only


class ScopeTests(unittest.TestCase):
    def test_documentation(self):
        self.assertTrue(docs_only(["README.ru.md", "docs/v1/a b.md"]))
        self.assertTrue(docs_only(["tools/export_wifi_map.py"]))

    def test_any_other_path_requires_full_gates(self):
        for path in ("firmware/a.cpp", "tests/native/a.cpp", "platformio.ini",
                     ".github/workflows/quality.yml", "tools/test.sh",
                     "tools/ci_change_scope.py", "other/docs/file.md"):
            with self.subTest(path=path):
                self.assertFalse(docs_only(["docs/v1/map.md", path]))
        self.assertFalse(docs_only([]))

    def test_manual_and_unknown_events_are_full(self):
        for name in ("workflow_dispatch", "release", "unknown"):
            self.assertEqual(changed_paths({}, name), [])

    def test_missing_base_is_full(self):
        self.assertEqual(changed_paths(
            {"before": "0" * 40, "after": "a" * 40}, "push"), [])

    @patch("ci_change_scope.subprocess.run")
    def test_pr_uses_merge_base_and_nul_paths(self, run):
        run.return_value.stdout = b"docs/a b.md\0README.md\0"
        self.assertEqual(changed_paths({"pull_request": {
            "base": {"sha": "a" * 40}, "head": {"sha": "b" * 40}
        }}, "pull_request"), ["docs/a b.md", "README.md"])
        self.assertIn("a" * 40 + "..." + "b" * 40, run.call_args.args[0])
        self.assertIn("--no-renames", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
