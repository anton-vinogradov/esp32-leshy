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
        "bleDeviceCatalog.upsert(observation)",
        "renderBleDevicesData();",
        "renderBleDeviceRow(index, currentFirst);",
        "bleProductView != BleProductView::DeviceDetail",
        "return true;\n        }\n        renderBleDeviceRow(",
        "TouchTargetLayout::HomeRows",
        "ble_product_view",
        "ble_devices_unique",
        "ble_device_catalog_revision",
    )
    required_catalog = (
        "static constexpr std::size_t kCapacity = 32",
        "sameIdentity",
        "visibleFieldsDiffer",
        "sortStrongestFirst",
        "std::stable_sort",
    )
    required_adapter = (
        "setActiveScan(false)",
        "setDuplicateFilter(true)",
        "maximumRecords_",
        "scanner_->erase",
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
        "strongest-first bounded catalog, frozen detail and row-only refresh"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
