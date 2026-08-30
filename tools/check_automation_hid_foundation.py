#!/usr/bin/env python3
"""Fail closed unless CAP-054 remains a bounded passive foundation."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/apps/automation/AutomationPackage.h"
SOURCE = ROOT / "firmware/leshy1/src/apps/automation/AutomationPackage.cpp"
CONTROLLER_HEADER = (
    ROOT / "firmware/leshy1/src/apps/automation/AutomationInspectorController.h"
)
CONTROLLER_SOURCE = (
    ROOT / "firmware/leshy1/src/apps/automation/AutomationInspectorController.cpp"
)
BOARD_READER_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardAutomationPackageReader.h"
)
BOARD_READER_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardAutomationPackageReader.cpp"
)
ARDUINO_ENTRY = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
)
TEST = ROOT / "tests/native/automation_package_tests.cpp"
DOC = ROOT / "docs/v1/AUTOMATION_HID.md"
DOC_RU = ROOT / "docs/v1/AUTOMATION_HID.ru.md"


def main() -> int:
    failures: list[str] = []
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    controller_header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    controller_source = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    board_reader_header = BOARD_READER_HEADER.read_text(encoding="utf-8")
    board_reader_source = BOARD_READER_SOURCE.read_text(encoding="utf-8")
    arduino_entry = ARDUINO_ENTRY.read_text(encoding="utf-8")
    test = TEST.read_text(encoding="utf-8")
    docs = DOC.read_text(encoding="utf-8")
    docs_ru = DOC_RU.read_text(encoding="utf-8")

    required_header = (
        "kAutomationMaximumPackageBytes = 4096U",
        "kAutomationMaximumSteps = 32U",
        "kAutomationMaximumEvents = 128U",
        "kAutomationMaximumRuntimeMs = 300000U",
        "EcdsaP256Sha256",
        "AutomationSignatureVerifier",
        "actionsInvoked = 0U",
        "hidReportsEmitted = 0U",
        "resourcesAcquired = 0U",
        "admitAutomationExecution",
    )
    for token in required_header:
        if token not in header:
            failures.append(f"missing contract token: {token}")

    required_source = (
        'std::memcmp(bytes, "LHAU", 4U)',
        "signedBytes + kAutomationSignatureBytes != totalBytes",
        "result.requestedPermissions != result.impliedPermissions",
        "aggregateDuration > result.runtimeCeilingMs",
        "verifier->verify(",
        "bytes, signedBytes, result.keyId, signature)",
        "constantTimeEqual(context.selectedTargetFingerprint",
        "context.grantedPermissions != inspection.requestedPermissions",
    )
    for token in required_source:
        if token not in source:
            failures.append(f"missing fail-closed source token: {token}")

    forbidden_source = (
        "#include <vector>", "#include <string>", "std::vector", "std::string",
        "new ", "malloc(", "calloc(", "realloc(", "free(", "Arduino.h",
        "USBHID", "Keyboard.", "Mouse.", "NimBLE", "BLEHID",
        "ActionDispatcher", "Serial1", "WiFi.",
    )
    for token in forbidden_source:
        if token in header or token in source:
            failures.append(f"passive foundation contains forbidden path: {token}")

    required_product = (
        (controller_header, "AutomationPackageCatalog"),
        (controller_header, "AutomationInspectorController"),
        (controller_header, "exposes no execution, Action, HID, storage or resource operation"),
        (controller_source, "secureClear(&model_, sizeof(model_))"),
        (board_reader_header, '"/leshy/automation/v1"'),
        (board_reader_source, "f_opendir(&directory, root)"),
        (board_reader_source, "f_open(&workspace_.file, path, FA_READ)"),
        (board_reader_source, "observedSize != entry.size"),
        (arduino_entry, "filesystem.beginReadOnly() && filesystem.readOnlyGuaranteed()"),
        (arduino_entry, "serviceAutomationPackageUi();"),
        (arduino_entry, "renderAutomationInspectorPage(clearContent)"),
        (arduino_entry, "kAutomationStorageResources"),
    )
    for text, token in required_product:
        if token not in text:
            failures.append(f"missing passive product token: {token}")

    passive_product = "\n".join(
        (controller_header, controller_source, board_reader_header,
         board_reader_source)
    )
    forbidden_product = (
        "FA_WRITE", "FA_CREATE", "f_write(", "f_unlink(", "f_mkdir(",
        "ActionDispatcher", "USBHID", "Keyboard.", "Mouse.", "BLEHID",
        "resourceBroker", "appRuntime.launch", "execute(",
    )
    for token in forbidden_product:
        if token in passive_product:
            failures.append(f"passive product contains forbidden path: {token}")

    required_tests = (
        "testTrustedActionPackageIsInspectedWithoutExecution",
        "testUsbAndBleKindsDeriveExactPermissions",
        "testSignatureStatesNeverBecomeExecutionAuthority",
        "testMutationAndFramingFailClosed",
        "testPolicyRejectsPrivilegeKindAndBounds",
        "testAdmissionOrderBindsAuthenticationPermissionAndTarget",
        "CHECK(!inspected.executionEligible)",
        "inspected.hidReportsEmitted == 0U",
        "inspected.actionsInvoked == 0U",
        "testPassiveInspectorRetainsSummaryButNeverPackageBytes",
        "testInspectorCatalogAndSourceFailuresAreBounded",
    )
    for token in required_tests:
        if token not in test:
            failures.append(f"missing negative/side-effect test: {token}")

    for path, text in ((DOC, docs), (DOC_RU, docs_ru)):
        contract_tokens = (
            "CAP-054",
            "4,096" if path == DOC else "4 096",
            "verified_trusted",
            "physical-stop HIL" if path == DOC else "physical stop",
        )
        for token in contract_tokens:
            if token not in text:
                failures.append(f"{path.name} missing contract token: {token}")
        if "active HID" not in text and "Active HID" not in text:
            failures.append(f"{path.name} does not disclaim active HID")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "Automation/HID foundation acceptance passed: canonical signed package, "
        "strict least privilege, passive zero-output inspector, target-bound admission"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
