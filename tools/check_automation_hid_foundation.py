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
HIL_FIXTURE_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardAutomationPackageHilFixture.h"
)
HIL_FIXTURE_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardAutomationPackageHilFixture.cpp"
)
ARDUINO_ENTRY = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
)
TRUST_HEADER = (
    ROOT / "firmware/leshy1/src/apps/automation/AutomationTrustStore.h"
)
TRUST_SOURCE = (
    ROOT / "firmware/leshy1/src/apps/automation/AutomationTrustStore.cpp"
)
TRUST_BUNDLE_HEADER = (
    ROOT / "firmware/leshy1/src/apps/automation/AutomationTrustBundle.h"
)
TRUST_BUNDLE_SOURCE = (
    ROOT / "firmware/leshy1/src/apps/automation/AutomationTrustBundle.cpp"
)
ARDUINO_TRUST_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoAutomationTrust.h"
)
ARDUINO_TRUST_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoAutomationTrust.cpp"
)
TRUST_BOARD_READER_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardAutomationTrustBundleReader.h"
)
TRUST_BOARD_READER_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardAutomationTrustBundleReader.cpp"
)
TRUST_BUILDER = ROOT / "tools/build_automation_trust_bundle.py"
TRUST_WORKFLOW = ROOT / ".github/workflows/automation-trust-bundle.yml"
PHYSICAL_HIL_RUNNER = ROOT / "tools/run_1x_automation_inspector_hil.py"
TRUST_UI_HIL_RUNNER = ROOT / "tools/run_1x_automation_trust_ui_hil.py"
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
    hil_fixture_header = HIL_FIXTURE_HEADER.read_text(encoding="utf-8")
    hil_fixture_source = HIL_FIXTURE_SOURCE.read_text(encoding="utf-8")
    arduino_entry = ARDUINO_ENTRY.read_text(encoding="utf-8")
    trust_header = TRUST_HEADER.read_text(encoding="utf-8")
    trust_source = TRUST_SOURCE.read_text(encoding="utf-8")
    trust_bundle_header = TRUST_BUNDLE_HEADER.read_text(encoding="utf-8")
    trust_bundle_source = TRUST_BUNDLE_SOURCE.read_text(encoding="utf-8")
    arduino_trust_header = ARDUINO_TRUST_HEADER.read_text(encoding="utf-8")
    arduino_trust_source = ARDUINO_TRUST_SOURCE.read_text(encoding="utf-8")
    trust_board_reader_header = TRUST_BOARD_READER_HEADER.read_text(
        encoding="utf-8")
    trust_board_reader_source = TRUST_BOARD_READER_SOURCE.read_text(
        encoding="utf-8")
    trust_builder = TRUST_BUILDER.read_text(encoding="utf-8")
    trust_workflow = TRUST_WORKFLOW.read_text(encoding="utf-8")
    physical_hil_runner = PHYSICAL_HIL_RUNNER.read_text(encoding="utf-8")
    trust_ui_hil_runner = TRUST_UI_HIL_RUNNER.read_text(encoding="utf-8")
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

    trust_contract = "\n".join(
        (trust_header, trust_source, trust_bundle_header, trust_bundle_source,
         arduino_trust_header, arduino_trust_source)
    )
    required_trust = (
        "kAutomationTrustMaximumKeys = 4U",
        "AutomationTrustMutationAuthorization",
        "AuthenticationRequired",
        "ConfirmationRequired",
        "encodeAutomationTrustRecord",
        "decodeAutomationTrustRecord",
        'std::memcmp(bytes, "LHAK", 4U)',
        "kAutomationTrustBundleBytes = 128U",
        'kNamespace = "leshy1-auto"',
        'kTrustRecordKey = "trust.v1"',
        "mbedtls_ecp_check_pubkey",
        "mbedtls_ecdsa_verify",
        "MBEDTLS_ECP_DP_SECP256R1",
        "deriveAutomationP256KeyId",
        "findAutomationTrustedKey",
        "&automationSignatureVerifier",
    )
    joined_trust_product = trust_contract + "\n" + arduino_entry
    for token in required_trust:
        if token not in joined_trust_product:
            failures.append(f"missing real trust boundary token: {token}")
    for token in (
        "PRIVATE KEY", "privateKey", "private_key", "ActionDispatcher",
        "USBHID", "Keyboard.", "Mouse.", "BLEHID", "execute(",
    ):
        if token in trust_contract:
            failures.append(f"trust boundary contains forbidden authority: {token}")
    for token in (
        "LESHY_AUTOMATION_P256_PRIVATE_KEY_PEM",
        "environment: automation-signing",
        "openssl pkey",
        "build_automation_trust_bundle.py",
        "contains_private_key",
        "retention-days: 14",
    ):
        if token not in trust_workflow + "\n" + trust_builder:
            failures.append(f"missing GitHub trust workflow token: {token}")
    if "write_bytes(bundle)" not in trust_builder or "public_key_sha256" not in trust_builder:
        failures.append("public-only trust bundle builder is incomplete")

    required_product = (
        (controller_header, "AutomationPackageCatalog"),
        (controller_header, "AutomationInspectorController"),
        (controller_header, "exposes no execution, Action, HID, storage or resource operation"),
        (controller_source, "secureClear(&model_, sizeof(model_))"),
        (board_reader_header, '"/leshy/automation/v1"'),
        (board_reader_header, "validAutomationPackageLibraryRoot"),
        (board_reader_source, "f_opendir(&directory, root)"),
        (board_reader_source, "f_open(&workspace_.file, path, FA_READ)"),
        (board_reader_source, "observedSize != entry.size"),
        (board_reader_source, "storage::kScratchRoot"),
        (board_reader_source, "root_"),
        (arduino_entry, "filesystem.beginReadOnly() && filesystem.readOnlyGuaranteed()"),
        (arduino_entry, "serviceAutomationPackageUi();"),
        (arduino_entry, "renderAutomationInspectorPage(clearContent)"),
        (arduino_entry, "kAutomationStorageResources"),
        (trust_board_reader_header, 'kAutomationTrustBundleName = "automation-owner.lhak"'),
        (trust_board_reader_header, 'kAutomationTrustBundleRoot = "/leshy/automation/v1"'),
        (trust_board_reader_source, "f_open(&workspace_.file, path, FA_READ)"),
        (trust_board_reader_source, "observed != output->size()"),
        (arduino_entry, "kAutomationTrustPage = 15"),
        (arduino_entry, "AutomationTrustUiView::ImportReview"),
        (arduino_entry, "AutomationTrustUiView::RevokeReview"),
        (arduino_entry, "kAutomationTrustConfirmationWindowUs = 30000000ULL"),
        (arduino_entry, "validateAutomationP256PublicKey("),
        (arduino_entry, "deriveAutomationP256KeyId("),
        (arduino_entry, "DeviceLockOperation::SensitiveSettings"),
        (arduino_entry, "renderAutomationTrustPage(clearContent)"),
        (arduino_entry, "AutomationTrustMutationAuthorization"),
        (arduino_entry, '"automation.trust.state"'),
        (arduino_entry, '"private_key_stored\\\":false'),
        (arduino_entry, '"execution_connected\\\":false'),
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

    trust_import_product = "\n".join(
        (trust_board_reader_header, trust_board_reader_source))
    for token in (
        "FA_WRITE", "FA_CREATE", "f_write(", "f_unlink(", "f_mkdir(",
        "PRIVATE KEY", "privateKey", "private_key", "ActionDispatcher",
        "USBHID", "Keyboard.", "Mouse.", "BLEHID", "execute(",
    ):
        if token in trust_import_product:
            failures.append(
                f"public-only trust import contains forbidden path: {token}")

    fixture_contract = "\n".join((hil_fixture_header, hil_fixture_source))
    required_fixture = (
        'kAutomationMalformedFixtureName = "malformed.lhau"',
        'kAutomationUnsignedFixtureName = "unsigned.lhau"',
        "kAutomationHilFixtureRequiredBytes",
        "const storage::WritePermit& permit",
        "const storage::ScratchCleanupPermit& permit",
        "io.syncFile(kAutomationMalformedFixtureName)",
        "io.syncFile(kAutomationUnsignedFixtureName)",
        "io.syncDirectory()",
        'failure = "scan_unknown_entry"',
        "Cleanup accepts a partial set of the two known files",
        "report->filesRemoved == count",
    )
    for token in required_fixture:
        if token not in fixture_contract:
            failures.append(f"missing bounded HIL fixture token: {token}")
    forbidden_fixture = (
        "kAutomationPackageLibraryRoot", "/leshy/automation/v1",
        "f_mkfs(", "format(", "WiFi.", "NimBLE", "USBHID",
        "ActionDispatcher", "Keyboard.", "Mouse.",
    )
    for token in forbidden_fixture:
        if token in fixture_contract:
            failures.append(f"HIL fixture contains forbidden path: {token}")

    required_physical = (
        '\\"leshy.automation.inspector.state.v1\\"',
        '\\"leshy.automation.inspector.fixture.v1\\"',
        "kAutomationInspectorFixtureBeginPrefix",
        "kAutomationInspectorFixtureCleanupPrefix",
        "automationInspectorHilFixtureCleanupRequired",
        '\\"status\\\":\\\"fixture_cleanup_required',
        '\\"product_namespace_written\\\":false',
        '\\"rf_transmit_attempts\\\":0',
        '\\"action_invocations\\\":0',
        '\\"hid_reports\\\":0',
    )
    for token in required_physical:
        if token not in arduino_entry:
            failures.append(f"missing physical Inspector guard: {token}")

    required_runner = (
        'BOARD_PORT = "/dev/cu.usbmodem2101"',
        'FORBIDDEN_PORTS = {"/dev/cu.usbmodem1101"}',
        "stable_capture_pair",
        'set_language(device, "en")',
        'set_language(device, "ru")',
        '"product_namespace_written": False',
        '"radio_tx_commands": 0',
        '"wifi_host_touched": False',
        '"isolated_device_lock_fixture": True',
        '"pin_or_digest_retained": False',
        "device_lock_fixture_command(device, \"cleanup\")",
        "wipe_pin(lock_pin)",
        '"full_hil": False',
        '"delta_only": True',
        '"--skip-flash"',
        '"installed_candidate_reused"',
        "run_id = secrets.token_hex(16)",
        '"automation-inspector-physical-v1"',
    )
    for token in required_runner:
        if token not in physical_hil_runner:
            failures.append(f"missing physical Inspector runner guard: {token}")

    required_trust_ui_runner = (
        'BOARD_PORT = "/dev/cu.usbmodem2101"',
        'FORBIDDEN_PORTS = {"/dev/cu.usbmodem1101"}',
        '"trust_mutation_confirmed": False',
        '"trust_namespace_written": False',
        '"sd_mount": "read_only"',
        '"sd_files_written": 0',
        '"private_key_used_or_stored": False',
        '"radio_tx_commands": 0',
        '"wifi_host_touched": False',
        '"full_hil": False',
        '"delta_only": True',
        '"--skip-flash"',
        '"installed_candidate_reused"',
        'set_language(device, "en")',
        'set_language(device, "ru")',
        'device_lock_fixture_command(device, "cleanup")',
        'wipe_pin(lock_pin)',
        'generation=trust_before["generation"]',
        'count=trust_before["count"]',
        'action_invocations=0, hid_reports=0, rf_transmit_attempts=0',
    )
    for token in required_trust_ui_runner:
        if token not in trust_ui_hil_runner:
            failures.append(f"missing physical trust UI runner guard: {token}")

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
