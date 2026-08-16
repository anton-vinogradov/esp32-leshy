#!/usr/bin/env python3
"""Fail if the clean 1.x target drifts into legacy or unsafe implicit probing."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "firmware" / "leshy1"


def main() -> int:
    errors: list[str] = []
    config = (TARGET / "platformio.ini").read_text(encoding="utf-8")
    source_paths = [
        path for path in sorted((TARGET / "src").rglob("*")) if path.is_file()
    ]
    physical_sd_adapter = TARGET / "src" / "platform" / "arduino" / "BoardSdSpiTransport.cpp"
    physical_sd_filesystem = TARGET / "src" / "platform" / "arduino" / "BoardSdFilesystem.cpp"
    session_store_filesystem = TARGET / "src" / "platform" / "arduino" / "ArduinoFsSessionStoreIo.cpp"
    passive_wifi_adapter = TARGET / "src" / "platform" / "arduino" / "BoardWifiPassiveScanner.cpp"
    safe_outputs_adapter = TARGET / "src" / "platform" / "arduino" / "BoardSafeOutputs.cpp"
    arduino_entry = TARGET / "src" / "platform" / "arduino" / "ArduinoEntry.cpp"
    survey_workflow_path = TARGET / "src" / "apps" / "survey" / "SurveyWorkflow.cpp"
    survey_pipeline_path = TARGET / "src" / "apps" / "survey" / "SurveyPipeline.cpp"
    product_survey_policy_path = TARGET / "src" / "apps" / "survey" / "ProductSurveyAdmission.cpp"
    product_store_policy_path = TARGET / "src" / "storage" / "ProductStorePolicy.cpp"
    session_catalog_path = TARGET / "src" / "apps" / "library" / "SessionCatalog.cpp"
    sector_inspection = TARGET / "src" / "storage" / "SdSectorInspection.cpp"
    reset_runner_path = ROOT / "tools" / "run_1x_sd_reset_matrix.py"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
    implicit_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in source_paths
        if path not in (
            physical_sd_adapter,
            physical_sd_filesystem,
            passive_wifi_adapter,
            safe_outputs_adapter,
        )
    )

    required = (
        "55.03.39/platform-espressif32.zip",
        "board_build.flash_size = 16MB",
        "board_build.partitions = partitions_16MB.csv",
        "-std=gnu++17",
        "bodmer/TFT_eSPI@2.5.43",
        "-D TFT_RST=-1",
    )
    for value in required:
        if value not in config:
            errors.append(f"missing pinned clean-target setting: {value}")

    forbidden_config = ("../src", "../../src", "TFT_RST=0")
    for value in forbidden_config:
        if value in config:
            errors.append(f"clean target reaches outside its tree or adds unreviewed deps: {value}")

    for pattern in (r"\bpinMode\s*\(", r"\bdigitalWrite\s*\(", r"\banalogRead\s*\("):
        if re.search(pattern, implicit_sources):
            errors.append(
                "measurement target performs GPIO probing outside the explicit "
                f"board adapters: {pattern}"
            )

    if not safe_outputs_adapter.is_file():
        errors.append("explicit board safe-output adapter is missing")
    else:
        safe_outputs = safe_outputs_adapter.read_text(encoding="utf-8")
        required_safe_output_markers = (
            "BoardProfile::kBuzzerPin",
            "digitalWrite(BoardProfile::kBuzzerPin, LOW)",
            "pinMode(BoardProfile::kBuzzerPin, OUTPUT)",
            "gpio_get_level",
        )
        for marker in required_safe_output_markers:
            if marker not in safe_outputs:
                errors.append(f"board safe-output adapter is missing invariant: {marker}")
        for pattern in (
            r"digitalWrite\s*\(\s*BoardProfile::kBuzzerPin\s*,\s*HIGH\s*\)",
            r"\btone\s*\(",
            r"\bledcAttach\s*\(",
            r"\banalogRead\s*\(",
        ):
            if re.search(pattern, safe_outputs):
                errors.append(f"board safe-output adapter can activate buzzer: {pattern}")

    entry = arduino_entry.read_text(encoding="utf-8")
    buzzer_boot = "BoardSafeOutputs::establishBootInvariant();"
    serial_boot = "Serial.begin(kConsoleBaud);"
    if buzzer_boot not in entry or serial_boot not in entry or entry.find(buzzer_boot) > entry.find(serial_boot):
        errors.append("buzzer inactive invariant must be established before console startup")

    if not survey_workflow_path.is_file():
        errors.append("product Survey workflow is missing")
    else:
        survey_workflow = survey_workflow_path.read_text(encoding="utf-8")
        for marker in (
            "SurveyWorkflowStatus::AlreadyCommitted",
            "storage::commitNextSession",
            "storage::recoverSession",
            "apps::library::LibraryController replacement",
            "replacement.replaceWithOwnedCopy",
            "library_ = replacement",
        ):
            if marker not in survey_workflow:
                errors.append(f"product Survey workflow is missing: {marker}")

    if not session_catalog_path.is_file():
        errors.append("read-only Session catalog is missing")
    else:
        session_catalog = session_catalog_path.read_text(encoding="utf-8")
        for marker in (
            "storage::recoverSession",
            "replacement.replaceWithOwnedCopy",
            "library = replacement",
            "SessionIntegrity::RecoveredFallback",
            "library.add",
        ):
            if marker not in session_catalog:
                errors.append(f"read-only Session catalog is missing: {marker}")

    if not survey_pipeline_path.is_file():
        errors.append("product Survey pipeline is missing")
    else:
        survey_pipeline = survey_pipeline_path.read_text(encoding="utf-8")
        for marker in (
            "queue_.push",
            "queue_.pop",
            "capacityDropped_",
            "services::survey::sessionBatchTrigger",
            "SurveyPipelineStatus::AlreadyCommitted",
        ):
            if marker not in survey_pipeline:
                errors.append(f"product Survey pipeline is missing: {marker}")

    if not physical_sd_adapter.is_file():
        errors.append("explicit physical SD adapter is missing")
    else:
        adapter = physical_sd_adapter.read_text(encoding="utf-8")
        required_adapter_markers = (
            "kSdIdentificationSpiHz",
            "kSdPowerUpClockBytes = 20",
            "kSdCmd0WireAttempts = 3",
            "kNrfCePins",
            "digitalWrite(pin, LOW)",
            "digitalWrite(BoardProfile::kSdCsPin, HIGH)",
            "SPI_MODE0",
            "cleanupComplete_",
        )
        for marker in required_adapter_markers:
            if marker not in adapter:
                errors.append(f"physical SD adapter is missing safety marker: {marker}")
        for pattern in (
            r"\bSD\s*\.\s*begin",
            r"\bSD_MMC\b",
            r"\bFILE_WRITE\b",
            r"\bformat\s*\(",
            r"\bremove\s*\(",
            r"\bmkdir\s*\(",
        ):
            if re.search(pattern, adapter):
                errors.append(f"physical SD adapter contains forbidden storage API: {pattern}")

    if not physical_sd_filesystem.is_file():
        errors.append("explicit guarded SD filesystem adapter is missing")
    else:
        filesystem_adapter = physical_sd_filesystem.read_text(encoding="utf-8")
        for marker in (
            "BoardSdSpiTransport::holdRadioTransmitPathsInactive",
            "kSpiHz = 4000000",
            "formatAllowed() const { return false; }",
            "spi_bus_initialize",
            "esp_vfs_fat_sdspi_mount",
            "mount.format_if_mount_failed = false",
            "ff_diskio_get_pdrv_card",
            "guardSharedChipSelect",
        ):
            combined = filesystem_adapter + "\n" + (
                physical_sd_filesystem.with_suffix(".h").read_text(encoding="utf-8")
            )
            if marker not in combined:
                errors.append(f"guarded SD filesystem adapter is missing: {marker}")
        for pattern in (r"\bSD\s*\.\s*writeRAW", r"\bformat\s*\("):
            if re.search(pattern, filesystem_adapter):
                errors.append(f"guarded SD filesystem adapter bypasses scope: {pattern}")

    if not session_store_filesystem.is_file():
        errors.append("guarded filesystem SessionStore adapter is missing")
    else:
        session_adapter = session_store_filesystem.read_text(encoding="utf-8")
        for marker in (
            "safeRelativePath",
            "storage::kScratchRoot",
            "directoryExists(permit.scratchPath)",
            "f_mkdir",
            "bytesWritten_ > byteLimit_",
            "FA_WRITE | FA_CREATE_ALWAYS",
            "f_write",
            "f_sync",
            "f_close",
            "f_stat",
            "writable_ = false",
        ):
            if marker not in session_adapter:
                errors.append(f"guarded SessionStore adapter is missing: {marker}")
        for pattern in (
            r"\bremove\s*\(", r"\brmdir\s*\(", r"\brename\s*\(",
            r"\bf_unlink\s*\(",
        ):
            if re.search(pattern, session_adapter):
                errors.append(f"guarded SessionStore adapter can mutate existing paths: {pattern}")

    for policy_path, markers in (
        (
            product_store_policy_path,
            (
                'kProductSessionStoreRoot',
                'ExplicitSelectionRequired',
                'ReadOnlyDriverRequired',
                'WritableDriverRequired',
                'FormatForbidden',
                'ResourcesMissing',
            ),
        ),
        (
            product_survey_policy_path,
            (
                'validatePassivePlan',
                'ExplicitStartRequired',
                'WritableStoreRequired',
                'ResourcesMissing',
                'simulated',
            ),
        ),
    ):
        if not policy_path.is_file():
            errors.append(f"product fail-closed policy is missing: {policy_path.name}")
            continue
        policy = policy_path.read_text(encoding="utf-8")
        policy_header = policy_path.with_suffix(".h")
        if policy_header.is_file():
            policy += "\n" + policy_header.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in policy:
                errors.append(
                    f"product fail-closed policy {policy_path.name} is missing: {marker}"
                )

    for marker in (
        "survey.product.admission",
        '\\"simulated_fallback\\":false',
        '\\"hardware_touched\\":false',
        '\\"storage_mounted\\":false',
        '\\"storage_written\\":false',
    ):
        if marker not in entry:
            errors.append(f"product admission diagnostic is missing: {marker}")

    for marker in (
        "storage.sd.session-store disposable-write ",
        "storage.sd.session-store throughput disposable-write ",
        "storage.sd.session-store batch-throughput disposable-write ",
        "survey.wifi.passive-persist disposable-write ",
        "storage.sd.session-store reset disposable-write ",
        "storage.sd.session-store recover disposable-read-only ",
        "kSdThroughputSamples = 32",
        "SessionStoreBoundaryIo",
        "restartAtSessionStoreBoundary",
        "authorizeExistingScratchRead",
        "summarizeStorageTimings",
        '\\"existing_paths_deleted\\":false',
        '\\"format_allowed\\":false',
        '\\"writes_bounded_to_scratch\\"',
        '\\"reset_injection\\":true',
        '\\"physical_power_cut\\":false',
    ):
        if marker not in entry:
            errors.append(f"guarded physical SessionStore command is missing: {marker}")

    if not reset_runner_path.is_file():
        errors.append("guarded SD reset matrix runner is missing")
    else:
        reset_runner = reset_runner_path.read_text(encoding="utf-8")
        for marker in (
            "retryable_media_readiness",
            '"read_permit_status": "missing_media"',
            '"fingerprint_matched": False',
            '"bytes_written": 0',
            '"file_syncs": 0',
            '"directory_syncs": 0',
            '"cleanup_complete": True',
            '"recovery_attempts": attempts',
            'parser.add_argument("--recovery-attempts", type=int, default=3)',
            'parser.add_argument("--recovery-backoff", type=float, default=1.0)',
        ):
            if marker not in reset_runner:
                errors.append(f"guarded reset retry policy is missing: {marker}")

    if not passive_wifi_adapter.is_file():
        errors.append("explicit passive Wi-Fi adapter is missing")
    else:
        wifi_adapter = passive_wifi_adapter.read_text(encoding="utf-8")
        for marker in (
            "init.nvs_enable = 0",
            "esp_wifi_set_storage(WIFI_STORAGE_RAM)",
            "esp_wifi_set_mode(WIFI_MODE_STA)",
            "config.ssid = nullptr",
            "config.bssid = nullptr",
            "config.scan_type = WIFI_SCAN_TYPE_PASSIVE",
            "esp_wifi_scan_start(&config, true)",
            "esp_wifi_scan_get_ap_record",
            "esp_wifi_clear_ap_list",
            "esp_wifi_stop()",
            "esp_wifi_deinit()",
            "validatePassivePlan(plan)",
        ):
            if marker not in wifi_adapter:
                errors.append(f"passive Wi-Fi adapter is missing: {marker}")
        for pattern in (
            r"\bWIFI_SCAN_TYPE_ACTIVE\b",
            r"\bWIFI_MODE_(?:AP|APSTA)\b",
            r"\besp_wifi_connect\s*\(",
            r"\besp_wifi_set_config\s*\(",
            r"\besp_wifi_80211_tx\s*\(",
            r"\besp_wifi_set_promiscuous\s*\(",
            r"\bWiFi\s*\.\s*(?:begin|softAP)\s*\(",
        ):
            if re.search(pattern, wifi_adapter):
                errors.append(f"passive Wi-Fi adapter contains TX/config path: {pattern}")
        for marker in (
            "survey.wifi.passive-ingress measure passive-only ",
            "resourceMask(Resource::EspRf)",
            '\\"physical_no_tx_verified\\":false',
            '\\"application_connect_calls\\":0',
            '\\"application_raw_tx_calls\\":0',
            '\\"storage_written\\":false',
            '\\"user_identifiers_emitted\\":false',
            '\\"user_identifiers_retained\\":false',
            "measurementSession.reset()",
            "sessionStoreWorkspace.segment.fill(0)",
        ):
            if marker not in entry:
                errors.append(f"passive Wi-Fi command is missing safety evidence: {marker}")
        survey_session = (
            TARGET / "src" / "services" / "survey" / "SurveySession.cpp"
        ).read_text(encoding="utf-8")
        if "observations_.fill(domain::observations::Observation{})" not in survey_session:
            errors.append("SurveySession reset does not scrub retained observations")

    privacy_sources = arduino_entry.read_text(encoding="utf-8") + "\n" + \
        sector_inspection.read_text(encoding="utf-8")
    for marker in (
        "counts_hash_only",
        "names_retained",
        "directory_names_retained",
        "directorySector.fill(0)",
        "fat_entries_inspected",
        "fat_chain_followed",
        "fatSector.fill(0)",
    ):
        if marker not in privacy_sources:
            errors.append(f"metadata-only directory path is missing privacy marker: {marker}")
    for pattern in (
        r'"(?:file_?)?names?"\s*:',
        r'"(?:short|long)_?name"\s*:',
    ):
        if re.search(pattern, privacy_sources, re.IGNORECASE):
            errors.append(f"directory evidence may retain a name field: {pattern}")

    for pattern in (r"#include\s*[<\"]WiFi\.h[>\"]", r"\besp_wifi_", r"\bWiFi\."):
        if re.search(pattern, implicit_sources):
            errors.append(f"measurement target starts an unapproved Wi-Fi path: {pattern}")

    if re.search(r"legacy_sources.{0,8}false", sources) is None:
        errors.append("boot evidence does not declare legacy_sources=false")

    if errors:
        print("clean 1.x target checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("clean 1.x target checks passed: pinned, isolated, and no implicit GPIO probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
