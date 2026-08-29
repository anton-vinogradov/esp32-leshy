#!/usr/bin/env python3
"""Fail-closed source guard for the first Bluetooth product function."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    entry = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
    ).read_text(encoding="utf-8")
    catalog_h = (
        ROOT / "firmware/leshy1/src/apps/ble/BleDeviceCatalog.h"
    ).read_text(encoding="utf-8")
    catalog_cpp = (
        ROOT / "firmware/leshy1/src/apps/ble/BleDeviceCatalog.cpp"
    ).read_text(encoding="utf-8")
    intelligence = (
        ROOT / "firmware/leshy1/src/apps/ble/BleDeviceIntelligence.cpp"
    ).read_text(encoding="utf-8")
    navigation = (
        ROOT / "firmware/leshy1/src/apps/ble/BleDeviceNavigationOrder.h"
    ).read_text(encoding="utf-8")
    company_database = (
        ROOT / "firmware/leshy1/src/apps/ble/BleCompanyDatabase.cpp"
    ).read_text(encoding="utf-8")
    adapter = (
        ROOT / "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.cpp"
    ).read_text(encoding="utf-8") + (
        ROOT / "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.h"
    ).read_text(encoding="utf-8")
    runner = (
        ROOT / "tools/run_1x_ble_nearby_hil.py"
    ).read_text(encoding="utf-8")
    checker = (
        ROOT / "tools/check_ble_nearby_run.py"
    ).read_text(encoding="utf-8")
    run_policy = (
        ROOT / "tools/ble_nearby_run_policy.py"
    ).read_text(encoding="utf-8")
    entry_gate = (
        ROOT / "tools/ble_nearby_entry_gate.py"
    ).read_text(encoding="utf-8")
    top_level_runner = (
        ROOT / "tools/run_1x_top_level_menu_smoke_hil.py"
    ).read_text(encoding="utf-8")
    strings = (
        ROOT / "firmware/leshy1/src/ui/UiStrings.def"
    ).read_text(encoding="utf-8")

    required_entry = (
        "BleProductView::Devices",
        "BleProductView::DeviceDetail",
        "startBleDevicesProduct()",
        "SurveySourceScope::BleOnly",
        "bleDeviceCatalog.upsert(",
        "struct BleDeviceRowVisual final",
        "bleDeviceRenderedRows",
        "renderBleDevicesData(false);",
        "The visible-row cache compares final pixels",
        "renderBleDeviceRadar(live, signal, false)",
        "renderRadioSignalCardDelta(",
        "TFT_eSprite liveTextRowSprite(&display);",
        "liveTextRowSprite.setColorDepth(1);",
        "liveTextRowSprite.pushSprite(x, y);",
        "bleDeviceAtomicTextRowPushes",
        "bleDeviceAtomicTextRowAllocationFailures",
        "bleDeviceDirectTextRowFallbacks",
        "Compose quality and dBm together",
        "bleDeviceRenderedRadar == next",
        "previousWidth - fillWidth",
        "bleDeviceListContentClears",
        "bleDeviceDetailContentClears",
        "bleDeviceRadarDeltaRepaints",
        "liveBleDeviceSignal()",
        "bleDeviceDetailStaticFieldsDiffer(",
        "bleCompanyDatabase.lookup(",
        "emitBleDeviceDetailState(",
        "leshy.ble.device_detail.v1",
        "active_probe_allowed\\\":false",
        "acknowledge the refresh without a",
        "TouchTargetLayout::HomeRows",
        "ble_product_view",
        "ble_devices_unique",
        "ble_devices_strongest_first",
        "ble_device_catalog_revision",
        "bleDeviceCatalog.indexOfIdentity(bleSelectionAnchor)",
        "bleDeviceNavigationOrder.lock(bleDeviceCatalog)",
        "bleDeviceVisibleSize()",
        "bleDeviceAt(bleDeviceSelection)",
        "renderRadioSignalCard(",
        "const bool bleReady = bleScanner.begin();",
        ": bleScanner.end();",
        "BoardBlePassiveScanner::cancelActiveScan();",
        "Each radio therefore owns a disjoint scan",
        "No radio stack survives into the other source's",
        "if (!report.scannerCleanupComplete)",
        'report.status = "scanner_cleanup_failed";',
        "bounded BLE observer is initialized only after this storage release",
        "report.admissionStatus =",
        "ProductSurveyAdmissionStatus::SourceUnavailable",
        "releaseProductSurveyAfterTerminal(event.report.status, !keepVisible);",
        "Do not queue a",
        "second incremental repaint here",
        "only this explicit user Back action closes it",
        "ble_begin_stage",
        "ble_begin_error",
        "ble_begin_heap_free_before",
        "ble_begin_heap_largest_after",
        "publishProductSurveyBleBeginDiagnostic",
        "productSurveyBleBeginDiagnosticSnapshot",
        "const bool terminalSourceUnavailable =",
        "event.report.activeSourceMask == 0",
        "render = !terminalSourceUnavailable;",
        "Multi-source degradation remains incremental",
    )
    forbidden_entry = (
        "const bool bleStackPrepared =",
        "bleStackPrepared && bleScanner.initialized()",
        "renderBleDeviceRow(index, currentFirst);",
    )
    required_catalog = (
        "static constexpr std::size_t kCapacity = 32",
        "sameIdentity",
        "visibleFieldsDiffer",
        "sortStrongestFirst",
        "entries_[position - 1U].rssiDbm < current.rssiDbm",
        "bool BleDeviceCatalog::strongestFirst() const",
        "indexOfIdentity",
        "struct BleDeviceSignalStats final",
        "signal.minimumRssiDbm",
        "signal.maximumRssiDbm",
        "signal.rssiTrendDb",
        "signalAt",
        "bool allowReplacement = true",
        "!allowReplacement",
    )
    for token in forbidden_entry:
        if token in entry:
            raise SystemExit(
                "BLE source contract retains overlapping Wi-Fi/NimBLE "
                f"lifecycle: {token}"
            )
    required_adapter = (
        "#include <esp32-hal-alloc-ble-mem.h>",
        "registers this low-level adapter as a BLE",
        "nimble_port_init()",
        "nimble_port_freertos_init(runProcessNimbleHost)",
        "ble_hs_synced()",
        "processControllerInitialized",
        "processNimbleHostRunning",
        "shutdownProcessControllerObserver",
        "nimble_port_stop()",
        "nimble_port_deinit()",
        "kHostShutdownTimeoutMs",
        "complete host lifecycle is bounded",
        "parameters.passive = 1U",
        "passive scan: never transmit scan requests",
        "no RF-TX operation",
        "ble_hs_util_ensure_addr(0)",
        "ble_hs_id_infer_auto(0, &ownAddressType)",
        "processOwnAddressType.load(std::memory_order_acquire)",
        "BLE_HS_FOREVER, &parameters, handleNimbleGapEvent",
        "ble_gap_disc_cancel()",
        "parseAdvertisementPayload",
        "RawScanContext",
        "seenAddresses",
        "maximumRecords",
        "stopPassiveScan()",
        "knownServiceMask",
        "kMaximumScanAttempts = 2U",
        "result.transientRetries",
        "BoardBleBeginDiagnostic",
        "processNimbleSyncError",
        "BoardBleBeginStage::ControllerInit",
        "BoardBleBeginStage::HostSync",
        "heap_caps_get_free_size",
        "heap_caps_get_largest_free_block",
    )
    required_runner = (
        "ENTRY_STABILITY_SECONDS = BLE_ENTRY_STABILITY_SECONDS",
        "wait_stable_ble_entry(device)",
        "BLE entry stability failed",
        '"delayed_entry_stability_gate": True',
        '"boot_recovery_continuity": boot_recovery_continuity(',
        '"product_storage_writes_measured": False',
        '"intermediate_clear_counters_checked": True',
        '"atomic_text_rows_checked": True',
        '1 <= row_repaint_delta <= 4',
        '"BLE detail signal update used a full repaint',
        '"BLE detail live text was not atomically composited',
    )
    forbidden_runner = (
        '"survey_product_store_bytes_written": 0',
        'recovery_after.get("physical_write_calls") != 0',
        '"storage_write_authorized": False',
    )
    required_checker = (
        "ble_entry_stability_evidence_failure(entry_stability) is None",
        "storage_measurement_scope_valid(scope)",
        "boot_recovery_continuity(before, after)",
        'scope.get("boot_recovery_continuity") is True',
        'first.get("survey_product_store_bytes_written") >= 0',
        '"BLE list final pixels/counters show a full or unbounded repaint"',
        '"BLE detail repaint counters show a full content clear"',
        'scope.get("intermediate_clear_counters_checked") is True',
        'scope.get("atomic_text_rows_checked") is True',
        'detail_second.get("atomic_text_row_pushes", -1) >',
        'detail_second.get("direct_text_row_fallbacks") == 0',
    )
    required_entry_gate = (
        "NIMBLE_SYNC_TIMEOUT_MS = 5000",
        "BLE_HOST_SHUTDOWN_TIMEOUT_MS = 2000",
        "BLE_SCAN_RETRY_BUDGET_MS = 6100",
        "BLE_ENTRY_STABILITY_MARGIN_MS = 1900",
        "BLE_ENTRY_STABILITY_MINIMUM_MS = (",
        "ble_entry_stability_evidence_failure(",
    )
    required_top_level_runner = (
        "BLE_MINIMUM_DWELL_SECONDS = BLE_ENTRY_STABILITY_SECONDS",
    )
    forbidden_checker = (
        'after.get("physical_write_calls") == 0',
        'scope.get("storage_write_authorized")',
    )
    required_run_policy = (
        'for key in ("generation", "observations")',
        "isinstance(before_value, int)",
        "isinstance(after_value, int)",
        'scope.get("product_storage_writes_measured") is False',
        '"storage_write_authorized" not in scope',
    )
    forbidden_adapter = (
        "BLEScan",
        "BLEAdvertisedDevice",
        "setActiveScan(true)",
        "BLEAdvertising",
        "startAdvertising",
        "new BLEAdvertisedDevice",
        "m_vectorAdvertisedDevices",
        "std::map",
        ".getScan()",
        "BLEDevice::init",
        "btStart()",
        "btStop()",
        "esp_vhci_host_register_callback",
        "esp_vhci_host_send_packet",
        "kHciReset",
        "esp_bt_controller_init",
        "ble_gap_adv_start",
        "ble_gap_connect",
        "process-lifetime",
    )
    required_strings = (
        "BleDevicesTitle",
        'u8"BLUETOOTH / РЯДОМ"',
        "BleDevicesSearching",
        "BleDeviceDetailTitle",
        "BlePassiveOnly",
        "BleVendorFormat",
        "BleTrackerFormat",
        "BleServiceFormat",
        "RadioSignalLabel",
    )
    required_intelligence = (
        "classifyBleDevice",
        "classifyBleSubtype",
        "classifyBleTracker",
        "kServiceSmartTag",
        "kServiceTile",
    )
    required_company_database = (
        "BleCompanyDatabase::lookup",
        "while (low < high)",
        "kRecordSize",
    )
    required_navigation = (
        "class BleDeviceNavigationOrder final",
        "bool lock(const BleDeviceCatalog& catalog)",
        "return locked_ ? size_ : catalog.size()",
        "catalog.indexOfIdentity(identity)",
        "BleDeviceCatalog::kCapacity",
    )

    failures = [
        f"product route token missing: {token}"
        for token in required_entry if token not in entry
    ]
    failures.extend(
        f"catalog token missing: {token}"
        for token in required_catalog
        if token not in catalog_h and token not in catalog_cpp
    )
    failures.extend(
        f"passive adapter token missing: {token}"
        for token in required_adapter if token not in adapter
    )
    failures.extend(
        f"BLE intelligence token missing: {token}"
        for token in required_intelligence if token not in intelligence
    )
    failures.extend(
        f"company database token missing: {token}"
        for token in required_company_database
        if token not in company_database and token not in catalog_h
    )
    failures.extend(
        f"navigation-order token missing: {token}"
        for token in required_navigation if token not in navigation
    )
    failures.extend(
        f"adapter contains active/TX path: {token}"
        for token in forbidden_adapter if token in adapter
    )
    failures.extend(
        f"BLE HIL lifecycle token missing: {token}"
        for token in required_runner if token not in runner
    )
    if "list_render_first = ble_detail(device)" in runner and \
            'screens["ble_devices_first"] = capture(' in runner and \
            runner.index("list_render_first = ble_detail(device)") > \
            runner.index('screens["ble_devices_first"] = capture('):
        failures.append(
            "BLE list repaint oracle must be sampled before the first frame")
    failures.extend(
        f"BLE HIL overclaims unmeasured storage state: {token}"
        for token in forbidden_runner if token in runner
    )
    failures.extend(
        f"BLE HIL checker scope token missing: {token}"
        for token in required_checker if token not in checker
    )
    failures.extend(
        f"BLE HIL entry-gate budget token missing: {token}"
        for token in required_entry_gate if token not in entry_gate
    )
    failures.extend(
        f"top-level BLE dwell token missing: {token}"
        for token in required_top_level_runner if token not in top_level_runner
    )
    failures.extend(
        f"BLE HIL checker overclaims unmeasured storage state: {token}"
        for token in forbidden_checker if token in checker
    )
    failures.extend(
        f"BLE HIL evidence-policy token missing: {token}"
        for token in required_run_policy if token not in run_policy
    )
    failures.extend(
        f"user copy token missing: {token}"
        for token in required_strings if token not in strings
    )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Bluetooth nearby contract passed: direct passive BLE list, "
        "strongest-first bounded catalog, monotonic advertisement intelligence, "
        "identity-stable navigation, offline company lookup and bounded live "
        "device radar with changed-row and changed-region repainting"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
