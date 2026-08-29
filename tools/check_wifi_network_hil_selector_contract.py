#!/usr/bin/env python3
"""Fail-closed source contract for the authorized Wi-Fi HIL selector."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
ORDER = ROOT / "firmware/leshy1/src/apps/wifi/WifiNetworkNavigationOrder.h"
TESTS = ROOT / "tests/native/clean_target_tests.cpp"
RUNNER = ROOT / "tools/run_1x_wifi_authentication_capture_hil.py"
RUNNER_TESTS = ROOT / "tools/test_wifi_authentication_capture_hil.py"
PLATFORMIO = ROOT / "firmware/leshy1/platformio.ini"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    entry = ENTRY.read_text(encoding="utf-8")
    order = ORDER.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    runner_tests = RUNNER_TESTS.read_text(encoding="utf-8")
    platformio = PLATFORMIO.read_text(encoding="utf-8")

    require(
        '"wifi.network.hil-select-label-fnv1a64 "' in entry,
        "missing exact HIL selector command prefix",
    )
    require(
        "std::strlen(command) != prefixLength + 16U" in entry
        and "if (parsed == 0U) return false;" in entry,
        "selector scope is not an exact non-zero 64-bit hash",
    )
    for guard in (
        "hilSession.active() && correctView",
        "wifiProductView == WifiProductView::Networks",
        "surveyWorkflow.state() == SurveyWorkflowState::Running",
        "productSurveyControl() == ProductSurveyWorkerControl::Running",
        "productSurveyRuntime.workerReady",
        'std::strcmp(appRuntime.activeApp(), "wifi") == 0',
        "resourceBroker.ownerOf(Resource::EspRf)",
        "!wifiNetworkNavigationOrder.locked()",
    ):
        require(guard in entry, f"missing fail-closed selector guard: {guard}")
    for claim in (
        r'\"rf_hardware_touched\":false',
        r'\"radio_started\":false',
        r'\"storage_mounted\":false',
        r'\"storage_written\":false',
        r'\"identifier_disclosed\":false',
    ):
        require(claim in entry, f"missing selector side-effect claim: {claim}")
    require(
        "labelHash(" in order
        and "14695981039346656037ULL" in order
        and "1099511628211ULL" in order
        and "indexOfLabelHash(" in order,
        "missing allocation-free FNV-1a 64-bit label selector",
    )
    require(
        "testWifiNetworkNavigationFindsStrongestExactLabelHash" in tests
        and "matches == 2U" in tests
        and "catalog.at(selected)->identity[5] == 0x02" in tests,
        "missing strongest exact-label native regression",
    )
    for marker in (
        'parser.add_argument("--allowed-ssid-fnv1a64", required=True)',
        "select_authorized_network(",
        '"status": "selected", "selected": True',
        '"identifier_disclosed": False',
        "network_list[\"authorized_selector\"]",
        "deadline = time.monotonic() + 30.0",
        'selected.get("status") not in ("not_found", "runtime_not_ready")',
        'selected["host_selector_transient_retries"] = attempts - 1',
    ):
        require(marker in runner, f"runner lost authorized selector: {marker}")
    result_block = runner[runner.index("    result = {"):]
    require(
        '"allowed_ssid' not in result_block
        and '"allowed_label_hash' not in result_block,
        "runner retains the authorized SSID hash in run evidence",
    )
    require(
        "test_authorized_network_selector_retains_no_identifier" in
        runner_tests
        and "test_authorized_network_selector_retries_transient_absence" in
        runner_tests,
        "missing runner privacy regression",
    )
    version = re.search(
        r'LESHY1_VERSION=\\"1\.0\.0-dev\.(\d+)\\"', platformio)
    require(
        version is not None and int(version.group(1)) >= 253,
        "selector firmware predates its dev.253 introduction",
    )
    print("wifi network HIL selector contract: PASS")


if __name__ == "__main__":
    main()
