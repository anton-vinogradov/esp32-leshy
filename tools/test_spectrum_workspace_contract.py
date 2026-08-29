#!/usr/bin/env python3
"""Adversarial tests for the deterministic spectrum workspace contract."""

from __future__ import annotations

import unittest

from check_spectrum_workspace_contract import ENTRY, WORKFLOW, contract_failures


def replace_in_function(
    source: str, signature: str, old: str, new: str
) -> str:
    start = source.index(signature)
    next_function = source.find("\n}\n", start)
    if next_function < 0:
        raise AssertionError(f"unterminated fixture function: {signature}")
    target = source.find(old, start, next_function)
    if target < 0:
        raise AssertionError(f"missing fixture token in {signature}: {old}")
    return source[:target] + new + source[target + len(old):]


class SpectrumWorkspaceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ENTRY.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def assertRejected(self, source: str, marker: str) -> None:
        failures = contract_failures(source)
        self.assertTrue(
            any(marker in failure for failure in failures),
            f"expected {marker!r}; got {failures!r}",
        )

    def test_current_source_passes(self) -> None:
        self.assertEqual(contract_failures(self.source), [])

    def test_rejects_standalone_bss_history(self) -> None:
        broken = self.source.replace(
            "SpectrumViewportFacade spectrumViewport;",
            "SpectrumViewport spectrumViewport;",
            1,
        )
        self.assertRejected(broken, "standalone 18.6-KiB")

    def test_rejects_union_growth_without_exact_invariant(self) -> None:
        broken = self.source.replace(
            "sizeof(SpectrumViewport) <=\n"
            "        sizeof(leshy1::storage::TargetDecisionStateStoreWorkspace)",
            "sizeof(SpectrumViewport) >\n"
            "        sizeof(leshy1::storage::TargetDecisionStateStoreWorkspace)",
            1,
        )
        self.assertRejected(broken, "missing deterministic shared-workspace marker")

    def test_rejects_busy_store_overlap(self) -> None:
        broken = replace_in_function(
            self.source,
            "bool spectrumViewportWorkspaceAvailable()",
            "subGhzCaptureStoreTaskHandle == nullptr &&",
            "true &&",
        )
        self.assertRejected(broken, "workspace-busy guard missing")

    def test_rejects_rf_begin_before_workspace_acquire(self) -> None:
        broken = self.source.replace(
            "SpectrumViewport* viewport = acquireSpectrumViewportWorkspace();",
            "SpectrumViewport* viewport = nullptr;",
            1,
        )
        self.assertRejected(broken, "nRF24 does not fail closed before RF begin")

    def test_rejects_release_before_board_cleanup(self) -> None:
        broken = replace_in_function(
            self.source,
            "bool stopCc1101Spectrum(bool returnToSourceMenu)",
            "    const bool cleanup = boardCc1101Spectrum.end();",
            "    releaseSpectrumViewportWorkspace();\n"
            "    const bool cleanup = boardCc1101Spectrum.end();",
        )
        broken = replace_in_function(
            broken,
            "bool stopCc1101Spectrum(bool returnToSourceMenu)",
            "    releaseSpectrumViewportWorkspace();\n"
            "    rfSpectrumView = returnToSourceMenu",
            "    rfSpectrumView = returnToSourceMenu",
        )
        self.assertRejected(broken, "CC1101 stop does not release after board cleanup")

    def test_rejects_missing_safety_quiesce(self) -> None:
        broken = self.source.replace(
            "        quiesceSpectrumOnSafetyStop();\n",
            "",
            1,
        )
        self.assertRejected(broken, "latched safety loop")

    def test_rejects_pause_fault_workspace_leak(self) -> None:
        broken = replace_in_function(
            self.source,
            "bool applyUiAction(UiAction action, bool render = true)",
            "                            releaseSpectrumViewportWorkspace();\n"
            "                            lastRuntimeEvent =\n"
            "                                \"cc1101_spectrum_pause_failed\";",
            "                            lastRuntimeEvent =\n"
            "                                \"cc1101_spectrum_pause_failed\";",
        )
        self.assertRejected(broken, "CC1101 pause fault")

    def test_rejects_persistent_workflow_workspace_reference(self) -> None:
        broken_workflow = self.workflow.replace(
            "storage::SessionStoreWorkspace* workspace_ = nullptr;",
            "storage::SessionStoreWorkspace& workspace_;",
            1,
        )
        failures = contract_failures(self.source, broken_workflow)
        self.assertTrue(any("missing deterministic" in item for item in failures))

    def test_rejects_spectrum_acquire_without_pointer_detach(self) -> None:
        broken = replace_in_function(
            self.source,
            "SpectrumViewport* acquireSpectrumViewportWorkspace()",
            "    surveyWorkflow.bindWorkspace(nullptr);\n",
            "",
        )
        self.assertRejected(broken, "spectrum acquire")

    def test_rejects_missing_console_owner_guard(self) -> None:
        broken = replace_in_function(
            self.source,
            "void handleCommand(",
            "    if (!sessionStoreWorkspaceAvailable() &&",
            "    if (false &&",
        )
        self.assertRejected(broken, "console/HIL shared-workspace guard")

    def test_rejects_session_fixture_allowlist_escape(self) -> None:
        broken = replace_in_function(
            self.source,
            "bool commandAllowedWhileSessionWorkspaceBorrowed(const char* command)",
            "    return std::strncmp(command, \"hil.begin \", 10) == 0 ||",
            "    return std::strcmp(command, \"session.fixture\") == 0 ||\n"
            "           std::strncmp(command, \"hil.begin \", 10) == 0 ||",
        )
        self.assertRejected(broken, "consumer incorrectly allowed")

    def test_rejects_finder_omitted_from_safety_quiesce(self) -> None:
        broken = replace_in_function(
            self.source,
            "void quiesceSpectrumOnSafetyStop()",
            "        if (nrfFinderActive) nrf24SignalFinder.fail();\n",
            "",
        )
        self.assertRejected(broken, "nrf24SignalFinder.fail()")


if __name__ == "__main__":
    unittest.main()
