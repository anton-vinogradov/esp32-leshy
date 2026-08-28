#!/usr/bin/env python3
"""Fail-closed source contract for the first real worker deadline boundary."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(text: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise AssertionError(f"{label} missing: {', '.join(missing)}")


def main() -> int:
    header = (ROOT / "firmware/leshy1/src/kernel/safety/"
              "WorkerDeadlineSupervisor.h").read_text(encoding="utf-8")
    core = (ROOT / "firmware/leshy1/src/kernel/safety/"
            "WorkerDeadlineSupervisor.cpp").read_text(encoding="utf-8")
    safety = (ROOT / "firmware/leshy1/src/kernel/safety/"
              "SafetySupervisor.cpp").read_text(encoding="utf-8")
    entry = (ROOT / "firmware/leshy1/src/platform/arduino/"
             "ArduinoEntry.cpp").read_text(encoding="utf-8")
    ble_header = (ROOT / "firmware/leshy1/src/platform/arduino/"
                  "BoardBlePassiveScanner.h").read_text(encoding="utf-8")
    ble_source = (ROOT / "firmware/leshy1/src/platform/arduino/"
                  "BoardBlePassiveScanner.cpp").read_text(encoding="utf-8")
    tests = (ROOT / "tests/native/clean_target_tests.cpp").read_text(
        encoding="utf-8")
    ir_runner = (ROOT / "tools/run_1x_infrared_store_deadline_hil.py").read_text(
        encoding="utf-8")
    platform = (ROOT / "firmware/leshy1/platformio.ini").read_text(
        encoding="utf-8")
    profile = (ROOT / "firmware/leshy1/src/boards/esp32_div_v2/"
               "BoardProfile.h").read_text(encoding="utf-8")

    require(header, (
        "enum class SupervisedWorker", "ProductSurveyPreparation",
        "ProductSurvey", "WifiCaptureStore", "SubGhzCaptureStore",
        "InfraredCaptureStore", "TargetsStore", "AirspaceGuardBle",
        "lastHeartbeatUs",
        "deadlineUs", "heartbeatCount", "tripCount", "bool evaluate",
    ), "deadline core API")
    require(core, (
        "nowUs < state_.lastHeartbeatUs", "state_.expired = true",
        "state_.lastExpiredWorker", "++state_.tripCount",
    ), "deadline fail-closed core")
    require(safety, ("SafetyReason::WorkerDeadline", "worker_deadline"),
            "retained safety reason")

    worker_start = entry.index("void runProductSurveyWorker(")
    worker_end = entry.index("bool initializeProductSurveyWorker()", worker_start)
    worker = entry[worker_start:worker_end]
    require(worker, (
        "armProductSurveyPreparationDeadline(preparationStartedUs)",
        "disarmProductSurveyPreparationDeadline();",
        "consumeProductSurveyPreparationDeadlineInjection()",
        "armProductSurveyWorkerDeadline(workerStartedUs)",
        "heartbeatProductSurveyWorker();",
        "disarmProductSurveyWorkerDeadline();",
        "consumeProductSurveyWorkerDeadlineInjection()",
    ), "real Product Survey worker integration")
    preparation_start = entry.index("ProductSurveyWorkerReport prepareProductSurveyWorker(")
    preparation_end = entry.index("void runProductSurveyWorker(", preparation_start)
    preparation = entry[preparation_start:preparation_end]
    if preparation.count("heartbeatProductSurveyPreparation();") < 8:
        raise AssertionError(
            "preparation lacks heartbeat coverage around identity/mount/scanners")
    if worker.count("heartbeatProductSurveyWorker();") < 5:
        raise AssertionError("worker lacks heartbeat coverage around waits/scans")
    scan_at = worker.index("wifiScanner.scan(")
    before_scan = worker.rfind("heartbeatProductSurveyWorker();", 0, scan_at)
    after_scan = worker.find("heartbeatProductSurveyWorker();", scan_at)
    if before_scan < 0 or after_scan < scan_at:
        raise AssertionError("blocking hardware scan is not heartbeat-bracketed")

    guard_start = entry.index("void runAirspaceGuardBleWorker()")
    guard_end = entry.index("void runProductSurveyWorker(", guard_start)
    guard_worker = entry[guard_start:guard_end]
    require(guard_worker, (
        "armAirspaceGuardBleWorkerDeadline(startedUs)",
        "heartbeatAirspaceGuardBleWorker();",
        "airspaceGuardBleScanPlan()", "scanner.begin()", "scanner.scan(",
        "scanner.end()", "scanner.cleanupComplete()",
        "disarmAirspaceGuardBleWorkerDeadline();",
        "const std::uint32_t completedGeneration = event.generation",
        "xQueueOverwrite(airspaceGuardBleWorkerEvents,",
        "&completedGeneration)",
    ), "Airspace Guard BLE worker integration")
    if "xTaskCreate" in guard_worker:
        raise AssertionError(
            "Airspace Guard BLE must reuse the persistent Survey worker")

    capture_start = entry.index("void runCaptureStoreWorker(")
    capture_end = entry.index("bool requestWifiFrameCapturePersist()", capture_start)
    capture_store = entry[capture_start:capture_end]
    require(capture_store, (
        "armWifiCaptureStoreDeadline(startedUs)",
        "consumeWifiCaptureStoreDeadlineInjection()",
        "kWifiCaptureStoreDeadlineInjectionMs",
        "wifiCaptureStoreDeadlineCancelled()",
        "disarmWifiCaptureStoreDeadline();",
        "xQueueOverwrite(captureStoreEvents, &event)",
    ), "Wi-Fi Capture Store deadline integration")
    if capture_store.count("supervisedCheckpoint()") < 8:
        raise AssertionError(
            "Capture Store lacks heartbeat coverage around storage boundaries")
    injection_at = capture_store.index(
        "consumeWifiCaptureStoreDeadlineInjection()")
    transport_at = capture_store.index("BoardSdSpiTransport transport;")
    if injection_at >= transport_at:
        raise AssertionError("Capture Store injection must precede SD hardware")

    pulse_start = entry.index("void runPulseCaptureStoreWorker(")
    pulse_end = entry.index("void runSubGhzCaptureStoreWorker(", pulse_start)
    pulse_store = entry[pulse_start:pulse_end]
    require(pulse_store, (
        "armPulseCaptureStoreDeadline(worker, startedUs)",
        "consumePulseCaptureStoreDeadlineInjection(worker)",
        "kPulseCaptureStoreDeadlineInjectionMs",
        "pulseCaptureStoreDeadlineCancelled(worker)",
        "disarmPulseCaptureStoreDeadline(worker)",
        "xQueueOverwrite(events, &event)",
    ), "pulse Capture Store deadline integration")
    if pulse_store.count("supervisedCheckpoint()") < 8:
        raise AssertionError(
            "pulse Capture Store lacks heartbeat coverage around storage "
            "boundaries")
    pulse_injection_at = pulse_store.index(
        "consumePulseCaptureStoreDeadlineInjection(worker)")
    pulse_transport_at = pulse_store.index("BoardSdSpiTransport transport;")
    if pulse_injection_at >= pulse_transport_at:
        raise AssertionError(
            "pulse Capture Store injection must precede SD hardware")

    targets_fixture_start = entry.index(
        "void runTargetsMergeFixtureMutationWorker(")
    targets_start = entry.index("void runTargetsMutationWorker(",
                                targets_fixture_start)
    targets_end = entry.index("bool requestTargetsFavoriteMutation()",
                              targets_start)
    targets_fixture_store = entry[targets_fixture_start:targets_start]
    targets_store = entry[targets_start:targets_end]
    require(targets_fixture_store, (
        "supervisedCheckpoint = targetsStoreSupervisedCheckpoint",
        "ArduinoLittleFsSessionStoreIo(\n            filesystem, "
        "supervisedCheckpoint)",
    ), "Targets fixture cooperative storage supervision")
    require(targets_store, (
        "armTargetsStoreDeadline(startedUs == 0 ? 1 : startedUs)",
        "targetsStoreDeadlineCancelled()",
        "supervisedCheckpoint = targetsStoreSupervisedCheckpoint",
        "sdSessionStoreIoWorkspace,\n            supervisedCheckpoint",
        "disarmTargetsStoreDeadline();",
        "xQueueOverwrite(targetsMutationEvents, &event)",
    ), "Targets Store deadline integration")
    if targets_store.count("supervisedCheckpoint()") < 6:
        raise AssertionError(
            "Targets Store lacks heartbeat coverage around storage boundaries")

    require(entry, (
        "bool targetsStoreSupervisedCheckpoint()",
        "const bool accepted = heartbeatTargetsStoreDeadline();",
        "if (accepted) vTaskDelay(pdMS_TO_TICKS(1));",
        "return accepted && !targetsStoreDeadlineCancelled();",
    ), "Targets Store cooperative checkpoint")

    require(entry, (
        "kProductSurveyPreparationDeadlineUs = 8000000ULL",
        "kProductSurveyPreparationDeadlineInjectionMs = 10000",
        "kProductSurveyWorkerDeadlineUs = 8000000ULL",
        "kAirspaceGuardBleWorkerDeadlineUs = 25000000ULL",
        "kProductSurveyWorkerDeadlineInjectionMs = 10000",
        "kWifiCaptureStoreDeadlineUs = 8000000ULL",
        "kWifiCaptureStoreDeadlineInjectionMs = 10000",
        "kPulseCaptureStoreDeadlineUs = 8000000ULL",
        "kTargetsStoreDeadlineUs = 8000000ULL",
        "kPulseCaptureStoreDeadlineInjectionMs = 10000",
        "BoardBlePassiveScanner::worstCaseScanDurationUs(",
        "serviceWorkerDeadlineSupervisor();",
        "requestProductSurveyWorkerStop(true);",
        "xSemaphoreGive(productSurveyScanStartGate);",
        "if (appRuntime.running()) appRuntime.stop();",
        "latchSafetyStopInTask(SafetyReason::WorkerDeadline);",
        "safety.worker-deadline-test confirm",
        "safety.worker-preparation-deadline-test confirm",
        "safety.capture-store-deadline-test confirm",
        "safety.capture-ir-store-deadline-test confirm",
        "safety.capture-subghz-store-deadline-test confirm",
        "worker.lastExpiredWorker == SupervisedWorker::WifiCaptureStore",
        "requestWifiCaptureStoreDeadlineCancel();",
        "worker.lastExpiredWorker ==\n               SupervisedWorker::SubGhzCaptureStore",
        "worker.lastExpiredWorker ==\n               SupervisedWorker::InfraredCaptureStore",
        "requestPulseCaptureStoreDeadlineCancel(",
        "worker.lastExpiredWorker ==\n               SupervisedWorker::TargetsStore",
        "requestTargetsStoreDeadlineCancel();",
        "worker.lastExpiredWorker ==\n               SupervisedWorker::AirspaceGuardBle",
        "requestAirspaceGuardBleWorkerCancel();",
        r'\"worker_supervision\":true',
    ), "platform deadline response")
    service_at = entry.index("serviceWorkerDeadlineSupervisor();")
    normal_service_at = entry.index("serviceProductSurveyWorker();", service_at)
    if service_at >= normal_service_at:
        raise AssertionError("deadline evaluation must precede normal worker service")
    require(tests, (
        "testWorkerDeadlineSupervisorTripsOnceAndRetainsEvidence",
        "snapshot.tripCount == 1", "supervisor.evaluate(6999)",
        "SupervisedWorker::SubGhzCaptureStore",
        "SupervisedWorker::InfraredCaptureStore",
        "SupervisedWorker::TargetsStore",
        "SupervisedWorker::AirspaceGuardBle",
    ), "native deadline matrix")
    require(ir_runner, (
        "safety.capture-ir-store-deadline-test confirm",
        "infrared_capture_store", "fixture.ir.nec.once",
        "post-flash-ready-seconds", "records[\"post_flash\"]",
        "post-flash boot contract failed",
        "capture_reconnecting_until_ready",
        "restart_usb_disconnects", "restart_usb_open_attempts",
        "clear_usb_disconnects", "clear_usb_open_attempts",
        "normal IR store heartbeat coverage incomplete",
        "fault_injection_before_storage_hardware",
        "fault_injection_physical_write_calls", "safety_after_restart",
        "safety_final", "two_bounded_fixture_emissions",
    ), "automated two-board IR Store deadline HIL")
    if "capture_until_ready(" in ir_runner:
        raise AssertionError(
            "IR deadline HIL must not retain a stale native-USB handle "
            "across restart")
    clear_start = entry.index("[[noreturn]] void clearSafetyStopAndRestart()")
    clear_end = entry.index("void recoverProductCatalogAtBoot()", clear_start)
    restart_start = entry.index("void restartLatchedSafetyStopForTest(")
    restart_end = entry.index("void clearSafetyStopFromConsole(", restart_start)
    for label, reset_path in (
        ("confirmed safety clear", entry[clear_start:clear_end]),
        ("retained-latch restart", entry[restart_start:restart_end]),
    ):
        if "esp_restart_noos();" not in reset_path or \
                "esp_restart();" in reset_path:
            raise AssertionError(
                f"{label} must bypass potentially locked shutdown handlers")
    require(ble_header, (
        "kMaximumScanAttempts = 2U", "kCompletionGraceMs = 1000U",
        "kRetryDelayMs = 100U", "worstCaseScanDurationUs",
        "static std::atomic_bool cancelRequested_",
    ), "bounded BLE scan deadline")
    require(ble_source, (
        "cancelRequested_.store(true, std::memory_order_release)",
        "!cancelRequested_.load(std::memory_order_acquire)",
    ), "BLE pre-start cancellation latch")
    version = re.search(
        r'LESHY1_VERSION=\\"(\d+)\.(\d+)\.(\d+)[^\\"]*\\"', platform)
    if version is None or tuple(map(int, version.groups())) < (0, 138, 0):
        raise AssertionError(
            "candidate predates the complete worker-deadline integration")
    if "kRfCarrierChipSelectCharacterizationOnly = false" not in profile:
        raise AssertionError("diagnostic-only carrier gate remains active")

    print(
        "worker deadline contract passed: preparation + real Survey/Wi-Fi/"
        "Sub-GHz/IR Capture, Targets Store and Airspace Guard BLE heartbeat, "
        "bounded deadlines, "
        "cancel/quiesce/"
        "retained Safe Mode"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
