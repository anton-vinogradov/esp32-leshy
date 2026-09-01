#!/usr/bin/env python3
"""Tests for the task-first owned Wi-Fi password check."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_my_wifi_password as journey
import test_owned_wifi_evidence_verifier as fixtures


class CheckMyWifiPasswordTests(unittest.TestCase):
    def run_journey(self, root: Path, corpus: bytes, *, resume: bool = False,
                    preview: bool = False) -> tuple[int, str, str, Path]:
        evidence = root / "exported-from-leshy.txt"
        corpus_path = root / "my-reviewed-list.txt"
        output = root / "results"
        evidence.write_text(fixtures.wpa02() + "\n", encoding="ascii")
        corpus_path.write_bytes(corpus)
        arguments = [
            "--evidence", str(evidence),
            "--corpus", str(corpus_path),
            "--list-kind", "mixed",
            "--language", "ru",
            "--max-candidates", "1",
            "--max-seconds", "10",
            "--output-directory", str(output),
            "--yes-i-am-authorized",
        ]
        if resume:
            arguments.append("--resume")
        if preview:
            arguments.append("--preview-only")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = journey.main(arguments)
        return status, stdout.getvalue(), stderr.getvalue(), output

    def test_match_is_plain_language_and_durable_report_is_private(self) \
            -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status, stdout, stderr, output = self.run_journey(
                root, fixtures.PASSPHRASE + b"\n")
            self.assertEqual(0, status, stderr)
            self.assertIn("найден слабый или заводской пароль", stdout)
            self.assertNotIn(fixtures.PASSPHRASE.decode("ascii"), stdout)
            reports = list(output.glob("*.json"))
            self.assertEqual(1, len(reports))
            report_text = reports[0].read_text(encoding="utf-8")
            self.assertNotIn(fixtures.PASSPHRASE.decode("ascii"), report_text)
            report = json.loads(report_text)
            self.assertEqual("weak_password_match", report["outcome"])
            self.assertEqual(0, report["side_effects"]["network_operations"])
            self.assertFalse(list(output.glob("*.checkpoint.json")))

    def test_no_match_never_claims_that_the_password_is_strong(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status, stdout, stderr, _ = self.run_journey(
                Path(directory), b"another-password\n")
            self.assertEqual(0, status, stderr)
            self.assertIn("не доказывает надёжность пароля", stdout)

    def test_preview_does_not_check_or_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status, stdout, stderr, output = self.run_journey(
                Path(directory), fixtures.PASSPHRASE + b"\n", preview=True)
            self.assertEqual(0, status, stderr)
            self.assertIn("Пароли не проверялись", stdout)
            self.assertFalse(output.exists())

    def test_rejected_authorization_starts_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "owned.txt"
            corpus = root / "list.txt"
            evidence.write_text(fixtures.wpa01() + "\n", encoding="ascii")
            corpus.write_bytes(fixtures.PASSPHRASE + b"\n")
            stdout = io.StringIO()
            with mock.patch("builtins.input", return_value="НЕТ"), \
                    contextlib.redirect_stdout(stdout):
                status = journey.main([
                    "--evidence", str(evidence),
                    "--corpus", str(corpus),
                    "--list-kind", "common", "--language", "ru",
                ])
            self.assertEqual(2, status)
            self.assertIn("отменена до запуска", stdout.getvalue())
            self.assertFalse((root / "leshy-results").exists())

    def test_pause_and_resume_use_exact_automatic_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = b"another-password\n" + fixtures.PASSPHRASE + b"\n"
            status, stdout, stderr, output = self.run_journey(root, corpus)
            self.assertEqual(0, status, stderr)
            self.assertIn("ПАУЗА", stdout)
            self.assertEqual(1, len(list(output.glob("*.checkpoint.json"))))

            status, stdout, stderr, output = self.run_journey(
                root, corpus, resume=True)
            self.assertEqual(0, status, stderr)
            self.assertIn("найден слабый или заводской пароль", stdout)
            self.assertFalse(list(output.glob("*.checkpoint.json")))
            report_path = next(output.glob("*.json"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(2, report["result"]["matched_rank"])


if __name__ == "__main__":
    unittest.main()
