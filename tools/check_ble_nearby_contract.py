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
        "renderBleDevicesData();",
        "renderBleDeviceRow(index, currentFirst);",
        "renderBleDeviceRadar(live, signal)",
        "liveBleDeviceSignal()",
        "bleDeviceDetailStaticFieldsDiffer(",
        "bleCompanyDatabase.lookup(",
        "emitBleDeviceDetailState(",
        "leshy.ble.device_detail.v1",
        "active_probe_allowed\\\":false",
        "return true;\n        }\n        renderBleDeviceRow(",
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
    required_adapter = (
        "setActiveScan(false)",
        "setDuplicateFilter(true)",
        "maximumRecords_",
        "scanner_->erase",
        "populateAdvertisementFacts",
        "knownServiceMask",
    )
    forbidden_adapter = (
        "setActiveScan(true)",
        "BLEAdvertising",
        "startAdvertising",
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
        "device radar"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
