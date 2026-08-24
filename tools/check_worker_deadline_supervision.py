#!/usr/bin/env python3
"""Fail-closed source contract for the first real worker deadline boundary."""

from __future__ import annotations

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
    tests = (ROOT / "tests/native/clean_target_tests.cpp").read_text(
        encoding="utf-8")
    platform = (ROOT / "firmware/leshy1/platformio.ini").read_text(
        encoding="utf-8")
    profile = (ROOT / "firmware/leshy1/src/boards/esp32_div_v2/"
               "BoardProfile.h").read_text(encoding="utf-8")

    require(header, (
        "enum class SupervisedWorker", "ProductSurvey", "lastHeartbeatUs",
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
        "armProductSurveyWorkerDeadline(workerStartedUs)",
        "heartbeatProductSurveyWorker();",
        "disarmProductSurveyWorkerDeadline();",
        "consumeProductSurveyWorkerDeadlineInjection()",
    ), "real Product Survey worker integration")
    if worker.count("heartbeatProductSurveyWorker();") < 5:
        raise AssertionError("worker lacks heartbeat coverage around waits/scans")
    scan_at = worker.index("wifiScanner.scan(")
    before_scan = worker.rfind("heartbeatProductSurveyWorker();", 0, scan_at)
    after_scan = worker.find("heartbeatProductSurveyWorker();", scan_at)
    if before_scan < 0 or after_scan < scan_at:
        raise AssertionError("blocking hardware scan is not heartbeat-bracketed")

    require(entry, (
        "kProductSurveyWorkerDeadlineUs = 6000000ULL",
        "serviceWorkerDeadlineSupervisor();",
        "requestProductSurveyWorkerStop(true);",
        "xSemaphoreGive(productSurveyScanStartGate);",
        "if (appRuntime.running()) appRuntime.stop();",
        "latchSafetyStopInTask(SafetyReason::WorkerDeadline);",
        "safety.worker-deadline-test confirm",
        r'\"worker_supervision\":true',
    ), "platform deadline response")
    service_at = entry.index("serviceWorkerDeadlineSupervisor();")
    normal_service_at = entry.index("serviceProductSurveyWorker();", service_at)
    if service_at >= normal_service_at:
        raise AssertionError("deadline evaluation must precede normal worker service")
    require(tests, (
        "testWorkerDeadlineSupervisorTripsOnceAndRetainsEvidence",
        "snapshot.tripCount == 1", "supervisor.evaluate(6999)",
    ), "native deadline matrix")
    if 'LESHY1_VERSION=\\"0.133.0-worker-deadline-supervision\\"' not in platform:
        raise AssertionError("exact candidate version is not bound")
    if "kRfCarrierChipSelectCharacterizationOnly = false" not in profile:
        raise AssertionError("diagnostic-only carrier gate remains active")

    print(
        "worker deadline contract passed: real Survey heartbeat, 6 s deadline, "
        "cancel/quiesce/retained Safe Mode"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
