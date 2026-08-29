#!/usr/bin/env python3
"""Fail closed if spectrum history again consumes permanent BLE heap."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
WORKFLOW = ROOT / "firmware/leshy1/src/apps/survey/SurveyWorkflow.h"


def function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise ValueError(f"missing function: {signature}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"missing function body: {signature}")
    depth = 0
    for offset in range(opening, len(source)):
        token = source[offset]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:offset]
    raise ValueError(f"unterminated function body: {signature}")


def ordered(body: str, *tokens: str) -> bool:
    cursor = -1
    for token in tokens:
        cursor = body.find(token, cursor + 1)
        if cursor < 0:
            return False
    return True


def contract_failures(
    source: str, workflow_source: str | None = None
) -> list[str]:
    failures: list[str] = []
    if workflow_source is None:
        workflow_source = WORKFLOW.read_text(encoding="utf-8")

    if "SpectrumViewport spectrumViewport;" in source:
        failures.append("standalone 18.6-KiB SpectrumViewport BSS reintroduced")
    if "SessionStoreWorkspace& sessionStoreWorkspace() =" in source:
        failures.append("persistent reference survives union member restart")
    for token in (
        "SpectrumViewport spectrum;",
        "sizeof(SpectrumViewport) <= sizeof(TargetsStoreCodecWorkspace)",
        "sizeof(SpectrumViewport) <=\n"
        "        sizeof(leshy1::storage::TargetDecisionStateStoreWorkspace)",
        "enum class TargetsStoreCodecWorkspaceOwner",
        "TargetsStoreCodecWorkspaceOwner::Session",
        "TargetsStoreCodecWorkspaceOwner::TargetDecision",
        "TargetsStoreCodecWorkspaceOwner::AdmissionScratch",
        "TargetsStoreCodecWorkspaceOwner::Spectrum",
        "class SpectrumViewportFacade final",
        "SpectrumViewportFacade spectrumViewport;",
        "storage::SessionStoreWorkspace* workspace_ = nullptr;",
        "void bindWorkspace(storage::SessionStoreWorkspace* workspace)",
        "return viewport_ == nullptr ? SpectrumDisplayMode::Spectrum",
        "return viewport_ == nullptr ? 0U : viewport_->rowsStored();",
    ):
        if token not in source and token not in workflow_source:
            failures.append(f"missing deterministic shared-workspace marker: {token}")

    try:
        available = function_body(source, "bool spectrumViewportWorkspaceAvailable()")
        acquire = function_body(source, "SpectrumViewport* acquireSpectrumViewportWorkspace()")
        release = function_body(
            source,
            "void releaseSpectrumViewportWorkspace(SpectrumViewport* viewport)",
        )
        nrf_start = function_body(source, "bool startNrf24Receiver(bool finder)")
        cc_start = function_body(source, "bool startCc1101Spectrum(")
        nrf_stop = function_body(source, "bool stopNrf24Spectrum(")
        cc_stop = function_body(source, "bool stopCc1101Spectrum(")
        nrf_service = function_body(source, "void serviceNrf24Spectrum()")
        cc_service = function_body(source, "void serviceCc1101Spectrum()")
        waterfall = function_body(source, "void serviceSpectrumWaterfallCadence()")
        safety = function_body(source, "void quiesceSpectrumOnSafetyStop()")
        target_acquire = function_body(
            source, "acquireTargetsStoreCodecWorkspace()"
        )
        target_release = function_body(
            source, "void releaseTargetsStoreCodecWorkspace("
        )
        admission_acquire = function_body(
            source, "TargetCatalog* acquireTargetsAdmissionScratch()"
        )
        admission_release = function_body(
            source, "void releaseTargetsAdmissionScratch(TargetCatalog* scratch)"
        )
        borrowed_commands = function_body(
            source,
            "bool commandAllowedWhileSessionWorkspaceBorrowed(const char* command)",
        )
        command_handler = function_body(source, "void handleCommand(")
        ui_action = function_body(
            source, "bool applyUiAction(UiAction action, bool render = true)"
        )
        loop = function_body(source, "void loop()")
    except ValueError as error:
        failures.append(str(error))
        return failures

    for token in (
        "TargetsStoreCodecWorkspaceOwner::Session",
        "productSurveyControl() == ProductSurveyWorkerControl::Idle",
        "!productSurveyScanActive()",
        "surveyWorkflow.state() != SurveyWorkflowState::Running",
        "targetsMutationTaskHandle == nullptr",
        "captureStoreTaskHandle == nullptr",
        "subGhzCaptureStoreTaskHandle == nullptr",
        "infraredCaptureStoreTaskHandle == nullptr",
    ):
        if token not in available:
            failures.append(f"workspace-busy guard missing before spectrum: {token}")

    if not ordered(
        acquire,
        "spectrumViewportWorkspaceAvailable()",
        "surveyWorkflow.bindWorkspace(nullptr);",
        "targetsStoreCodecWorkspace.session.~SessionStoreWorkspace();",
        "new (&targetsStoreCodecWorkspace.spectrum)",
        "TargetsStoreCodecWorkspaceOwner::Spectrum",
        "spectrumViewport.bind(viewport);",
    ):
        failures.append("spectrum acquire does not transition Session->Spectrum safely")
    if not ordered(
        release,
        "TargetsStoreCodecWorkspaceOwner::Spectrum",
        "spectrumViewport.unbind(viewport);",
        "viewport->~SpectrumViewport();",
        "new (&targetsStoreCodecWorkspace.session)",
        "TargetsStoreCodecWorkspaceOwner::Session",
        "surveyWorkflow.bindWorkspace(&targetsStoreCodecWorkspace.session);",
    ):
        failures.append("spectrum release does not reconstruct Session workspace")

    for label, acquire_body, release_body, constructed in (
        ("target decision", target_acquire, target_release, "targetDecision"),
        ("admission scratch", admission_acquire, admission_release,
         "admissionScratch"),
    ):
        if not ordered(
            acquire_body,
            "surveyWorkflow.bindWorkspace(nullptr);",
            "targetsStoreCodecWorkspace.session.~SessionStoreWorkspace();",
            f"new (&targetsStoreCodecWorkspace.{constructed})",
        ):
            failures.append(f"{label} acquire leaves a persistent workspace pointer")
        if not ordered(
            release_body,
            "new (&targetsStoreCodecWorkspace.session)",
            "TargetsStoreCodecWorkspaceOwner::Session",
            "surveyWorkflow.bindWorkspace(&targetsStoreCodecWorkspace.session);",
        ):
            failures.append(f"{label} release does not rebind SurveyWorkflow")

    for forbidden in (
        '"survey.wifi.passive-ingress',
        '"session.fixture"',
        '"session.store.fixture"',
        '"library.fixture"',
        '"storage.sd.session-store',
    ):
        if forbidden in borrowed_commands:
            failures.append(
                "session workspace consumer incorrectly allowed while borrowed: "
                f"{forbidden}"
            )
    if not ordered(
        command_handler,
        "!sessionStoreWorkspaceAvailable()",
        "!commandAllowedWhileSessionWorkspaceBorrowed(command)",
        "session_workspace_borrowed",
        "return;",
        "if (companionAllowed && command[0] == '{')",
    ):
        failures.append("console/HIL shared-workspace guard is missing or too late")

    for label, body in (("nRF24", nrf_start), ("CC1101", cc_start)):
        acquire_at = body.find("acquireSpectrumViewportWorkspace()")
        begin_at = body.find(
            "boardNrf24Spectrum.begin" if label == "nRF24"
            else "boardCc1101Spectrum.begin"
        )
        unavailable_at = body.find("_spectrum_workspace_unavailable")
        if not (0 <= acquire_at < unavailable_at < begin_at):
            failures.append(f"{label} does not fail closed before RF begin")
        if "return true;" not in body[unavailable_at:begin_at]:
            failures.append(f"{label} busy-workspace path can reach RF begin")
        failed_start = body[begin_at:]
        if not ordered(
            failed_start,
            "boardNrf24Spectrum.end()" if label == "nRF24"
            else "boardCc1101Spectrum.end()",
            "releaseSpectrumViewportWorkspace()",
        ):
            failures.append(f"{label} failed start releases workspace before RF cleanup")

    for label, body, board_end in (
        ("nRF24 stop", nrf_stop, "boardNrf24Spectrum.end()"),
        ("CC1101 stop", cc_stop, "boardCc1101Spectrum.end()"),
        ("nRF24 runtime fault", nrf_service, "boardNrf24Spectrum.end()"),
        ("CC1101 runtime fault", cc_service, "boardCc1101Spectrum.end()"),
    ):
        if not ordered(body, board_end, "releaseSpectrumViewportWorkspace()"):
            failures.append(f"{label} does not release after board cleanup")

    if not (
        ordered(
            waterfall,
            "boardCc1101Spectrum.end()",
            "releaseSpectrumViewportWorkspace()",
        )
        and ordered(
            waterfall,
            "boardNrf24Spectrum.end()",
            "releaseSpectrumViewportWorkspace()",
        )
    ):
        failures.append("waterfall history fault does not cleanup RF before release")
    if "if (!spectrumViewport.bound()) return;" in safety:
        failures.append("safety stop still depends on viewport ownership")
    for token in (
        "boardNrf24Spectrum.active()",
        "nrf24SignalFinder.state()",
        "boardNrf24Spectrum.end()",
        "nrf24SignalFinder.fail()",
        "boardCc1101Spectrum.active()",
        "cc1101SignalFinder.state()",
        "boardCc1101Spectrum.end()",
        "cc1101SignalFinder.fail()",
    ):
        if token not in safety:
            failures.append(f"safety stop does not quiesce finder path: {token}")
    if not ordered(safety, ".end()", "releaseSpectrumViewportWorkspace()"):
        failures.append("safety stop does not cleanup RF before workspace release")
    pause_fault = ui_action.find('"cc1101_spectrum_pause_failed"')
    if pause_fault < 0 or not ordered(
        ui_action[:pause_fault],
        "boardCc1101Spectrum.end()",
        "cc1101SpectrumController.fail()",
        "releaseSpectrumViewportWorkspace()",
    ):
        failures.append("CC1101 pause fault does not cleanup RF before release")
    if "quiesceSpectrumOnSafetyStop();" not in loop:
        failures.append("latched safety loop does not quiesce spectrum workspace")

    if "new (std::nothrow) SpectrumViewport" in source:
        failures.append("spectrum history must not depend on fragmented heap")
    return failures


def main() -> int:
    failures = contract_failures(ENTRY.read_text(encoding="utf-8"))
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(
        "PASS spectrum workspace: 18.6-KiB history overlays Session storage, "
        "busy paths fail before RF begin, and every terminal path reconstructs it"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
