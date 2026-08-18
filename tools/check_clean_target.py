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
    littlefs_partition_adapter = TARGET / "src" / "platform" / "arduino" / "DisposableOtaLittleFs.cpp"
    littlefs_session_store = TARGET / "src" / "platform" / "arduino" / "ArduinoLittleFsSessionStoreIo.cpp"
    session_store_router = TARGET / "src" / "storage" / "SessionStoreIoRouter.cpp"
    passive_wifi_adapter = TARGET / "src" / "platform" / "arduino" / "BoardWifiPassiveScanner.cpp"
    passive_ble_adapter = TARGET / "src" / "platform" / "arduino" / "BoardBlePassiveScanner.cpp"
    safe_outputs_adapter = TARGET / "src" / "platform" / "arduino" / "BoardSafeOutputs.cpp"
    keypad_frontend_path = TARGET / "src" / "ui" / "Pcf8574ButtonInput.cpp"
    arduino_entry = TARGET / "src" / "platform" / "arduino" / "ArduinoEntry.cpp"
    survey_workflow_path = TARGET / "src" / "apps" / "survey" / "SurveyWorkflow.cpp"
    survey_pipeline_path = TARGET / "src" / "apps" / "survey" / "SurveyPipeline.cpp"
    product_survey_policy_path = TARGET / "src" / "apps" / "survey" / "ProductSurveyAdmission.cpp"
    product_store_policy_path = TARGET / "src" / "storage" / "ProductStorePolicy.cpp"
    product_start_retry_path = TARGET / "src" / "storage" / "ProductStartRetry.cpp"
    session_catalog_path = TARGET / "src" / "apps" / "library" / "SessionCatalog.cpp"
    sector_inspection = TARGET / "src" / "storage" / "SdSectorInspection.cpp"
    reset_runner_path = ROOT / "tools" / "run_1x_sd_reset_matrix.py"
    littlefs_runner_path = ROOT / "tools" / "run_1x_littlefs_parity_hil.py"
    littlefs_reset_runner_path = (
        ROOT / "tools" / "run_1x_littlefs_reset_matrix_hil.py"
    )
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

    for marker in (
        "kInputProbeMaxAttempts = 8",
        "probeInputAtBoot(&lastInputRaw, &bootMetrics.inputProbeAttempts)",
        "bootMetrics.inputProbeTransientRetries",
    ):
        if marker not in entry:
            errors.append(f"bounded input boot probe is missing: {marker}")

    if not keypad_frontend_path.is_file():
        errors.append("testable physical keypad frontend is missing")
    else:
        keypad_frontend = keypad_frontend_path.read_text(encoding="utf-8")
        keypad_header = keypad_frontend_path.with_suffix(".h").read_text(encoding="utf-8")
        for marker in (
            "kPollPeriodMs = 5",
            "kDebounceMs = 12",
            "kButtonMask",
            "candidateSinceMs_",
            "ambiguousPresses",
            "maximumSampleGapMs",
        ):
            if marker not in keypad_frontend + "\n" + keypad_header:
                errors.append(f"physical keypad frontend is missing: {marker}")
        if "lastInputRaw & ~current" in entry:
            errors.append("Arduino entry bypasses the debounced physical keypad frontend")
        for marker in (
            "physicalButtonInput.sample",
            "Pcf8574ButtonInput::kPollPeriodMs",
            "xTaskCreatePinnedToCore",
            "xQueueSend",
            "xQueueReceive",
            "kPhysicalInputQueueCapacity = 64",
            "applyUiAction(inputEvent.action, false)",
            "renderInteractiveScreen(!lastUiActionUsedIncrementalRender)",
            "physicalInputQueueHighWater",
            '\\"hot_path_serial_writes\\\":0',
            "lastPhysicalInputQueueUs",
            "lastPhysicalInputEndToEndUs",
            '"input.state"',
        ):
            if marker not in entry:
                errors.append(f"Arduino entry is missing keypad integration: {marker}")
        loop_body = entry[entry.find("void loop() {"):]
        if "while (physicalInputEvents" in loop_body:
            errors.append(
                "physical keypad events are still drained as a render-coalescing batch"
            )
        if loop_body.count("xQueueReceive(physicalInputEvents") != 1:
            errors.append(
                "physical keypad loop must dispatch exactly one queued event per repaint"
            )
        input_dispatch = loop_body[loop_body.find("PhysicalInputEvent inputEvent;"):
                                   loop_body.find("delay(2);")]
        if "broadcast(" in input_dispatch or "println(" in input_dispatch:
            errors.append("physical keypad hot path contains blocking serial output")

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

    if not passive_wifi_adapter.is_file():
        errors.append("explicit passive Wi-Fi adapter is missing")
    else:
        passive_adapter = passive_wifi_adapter.read_text(encoding="utf-8")
        for marker in (
            "esp_event_loop_create_default",
            "esp_event_loop_delete_default",
            "init.nvs_enable = 0",
            "WIFI_STORAGE_RAM",
            "WIFI_SCAN_TYPE_PASSIVE",
        ):
            if marker not in passive_adapter:
                errors.append(f"passive Wi-Fi adapter is missing: {marker}")

    if not passive_ble_adapter.is_file():
        errors.append("explicit passive BLE adapter is missing")
    else:
        passive_ble = passive_ble_adapter.read_text(encoding="utf-8")
        for marker in (
            'activeScan_->setActiveScan(false)',
            "nullptr, false)",
            "activeScan_->isScanning()",
            "BoardBleScanStatus::ScanTimedOut",
            "BoundedAdvertisementCallbacks",
            "scanner_->erase(source.getAddress())",
            "activeScan_->setDuplicateFilter(true)",
            "validatePassivePlan(plan)",
            "plan.maximumRecords",
            "activeScan_->clearResults()",
            "BLEDevice::deinit(false)",
        ):
            if marker not in passive_ble:
                errors.append(f"passive BLE adapter is missing: {marker}")
        if "setActiveScan(true)" in passive_ble:
            errors.append("passive BLE adapter enables transmitting active scan")
        if "activeScan_->start(plan.durationMs / 1000U, false)" in passive_ble:
            errors.append("passive BLE adapter uses an unbounded blocking scan")

    if not physical_sd_filesystem.is_file():
        errors.append("explicit guarded SD filesystem adapter is missing")
    else:
        filesystem_adapter = physical_sd_filesystem.read_text(encoding="utf-8")
        for marker in (
            "BoardSdSpiTransport::holdRadioTransmitPathsInactive",
            "kSpiHz = 4000000",
            "formatAllowed() const { return false; }",
            "beginReadOnly",
            "readOnlyGuaranteed",
            "ff_diskio_register",
            "STA_PROTECT",
            "RES_WRPRT",
            "rejectReadOnlyWrite",
            "spi_bus_initialize",
            "esp_vfs_fat_sdspi_mount",
            "mount.format_if_mount_failed = false",
            "ff_diskio_get_pdrv_card",
            "guardSharedChipSelect",
            "cachedFreeBytes",
            "filesystem->free_clst",
            "f_opendir",
        ):
            combined = filesystem_adapter + "\n" + (
                physical_sd_filesystem.with_suffix(".h").read_text(encoding="utf-8")
            )
            if marker not in combined:
                errors.append(f"guarded SD filesystem adapter is missing: {marker}")
        for pattern in (
            r"\bSD\s*\.\s*writeRAW",
            r"\bformat\s*\(",
            r"\bsdmmc_write_sectors\s*\(",
        ):
            if re.search(pattern, filesystem_adapter):
                errors.append(f"guarded SD filesystem adapter bypasses scope: {pattern}")

    if not session_store_filesystem.is_file():
        errors.append("guarded filesystem SessionStore adapter is missing")
    else:
        session_adapter = session_store_filesystem.read_text(encoding="utf-8")
        for marker in (
            "safeRelativePath",
            "storage::kScratchRoot",
            "storage::kProductSessionStoreRoot",
            "storage::ProductStorePermit",
            "storage::ProductStoreOperation::InitializeStore",
            "storage::ProductStoreOperation::CommitSession",
            "storage::ProductStoreOperation::RecoverCatalog",
            "kProductSessionsParent",
            "openExistingWritable",
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

    if not littlefs_partition_adapter.is_file():
        errors.append("disposable OTA1 LittleFS adapter is missing")
    else:
        littlefs_partition = littlefs_partition_adapter.read_text(encoding="utf-8")
        littlefs_partition += "\n" + littlefs_partition_adapter.with_suffix(
            ".h"
        ).read_text(encoding="utf-8")
        for marker in (
            "kExpectedAddress = 0x410000",
            "kExpectedSize = 0x400000",
            'kPartitionLabel = "app1"',
            "ESP_PARTITION_SUBTYPE_APP_OTA_1",
            "esp_ota_get_running_partition",
            "esp_ota_get_boot_partition",
            'ESP_PARTITION_SUBTYPE_DATA_SPIFFS, "spiffs"',
            "config.partition = target_",
            "config.partition_label = nullptr",
            "config.format_if_mount_failed = false",
            "config.read_only = readOnly",
            "esp_littlefs_format_partition(target_)",
        ):
            if marker not in littlefs_partition:
                errors.append(
                    f"disposable OTA1 LittleFS adapter is missing: {marker}"
                )
        for pattern in (
            r"\bLittleFS\s*\.\s*begin\s*\(",
            r"\bSPIFFS\s*\.\s*begin\s*\(",
            r"\besp_littlefs_format\s*\(",
        ):
            if re.search(pattern, littlefs_partition):
                errors.append(
                    f"disposable LittleFS adapter can select a global/product target: {pattern}"
                )

    if not littlefs_session_store.is_file():
        errors.append("guarded LittleFS SessionStore adapter is missing")
    else:
        littlefs_io = littlefs_session_store.read_text(encoding="utf-8")
        littlefs_io += "\n" + littlefs_session_store.with_suffix(
            ".h"
        ).read_text(encoding="utf-8")
        for marker in (
            'kScratchParent = "/leshy-hil"',
            "storage::kScratchRoot",
            "bytesWritten_ > byteLimit_",
            "O_WRONLY | O_CREAT | O_TRUNC",
            "::write",
            "::fsync",
            "::close",
            "::stat",
            "fileSyncCoversDirectory() const { return true; }",
            "writable_ = false",
        ):
            if marker not in littlefs_io:
                errors.append(
                    f"guarded LittleFS SessionStore adapter is missing: {marker}"
                )
        for pattern in (
            r"\bremove\s*\(", r"\brmdir\s*\(", r"\brename\s*\(",
            r"\bunlink\s*\(",
        ):
            if re.search(pattern, littlefs_io):
                errors.append(
                    f"guarded LittleFS adapter can delete or rename paths: {pattern}"
                )

    for marker in (
        "recoverProductCatalogAtBoot();",
        "recoverProductCatalogForFingerprint",
        "loadProductFingerprint",
        "saveProductFingerprint",
        "clearProductFingerprint",
        "filesystem.beginReadOnly()",
        "io.openExistingReadOnly(permit)",
        "sessionCatalog.recoverLatest",
        "resourceBroker.releaseAll(kBootCatalogOwner)",
        '"storage.product.boot-recovery"',
        "storage.product.enroll disposable-read-only <CID32>",
        '"storage.product.unenroll confirm"',
        "storage.product.bootstrap disposable-write <CID32>",
        '\\"physical_write_calls\\\":0',
    ):
        if marker not in entry:
            errors.append(f"Arduino entry is missing product boot recovery: {marker}")

    for marker in (
        '"survey.persistent_passive"',
        "startProductSurvey()",
        "closeProductSurveyBackend()",
        "productSurveyFilesystem.cachedFreeBytes()",
        "productSurveyStore.openExistingWritable(storePermit)",
        "authorizeProductSurvey(surveyRequest)",
        "scanner.scan(",
        "enqueueProductSurveyWorkerRecord",
        "requestProductSurveyWorkerStop",
        "serviceProductSurveyWorker",
        "stopProductSurvey()",
        '\\"survey_product_cleanup_complete\\"',
    ):
        if marker not in entry:
            errors.append(f"Arduino entry is missing product Survey lifecycle: {marker}")

    product_prepare = entry.find("ProductSurveyWorkerReport prepareProductSurveyWorker(")
    product_worker = entry.find("void runProductSurveyWorker(", product_prepare)
    if product_prepare < 0 or product_worker <= product_prepare:
        errors.append("bounded product Survey worker preparation could not be inspected")
    else:
        product_start_body = entry[product_prepare:product_worker]
        for forbidden_call in (".freeBytes(", ".filesystemCapacityBytes("):
            if forbidden_call in product_start_body:
                errors.append(
                    "product Survey start contains unbounded FAT geometry scan: "
                    f"{forbidden_call}"
                )
        for marker in (
            "kProductStartMaximumIdentityAttempts",
            "shouldRetryProductStartIdentity",
            "productStartIdentityRetryDelayMs",
            "report.filesystemAttempted",
        ):
            if marker not in product_start_body:
                errors.append(f"product Survey start is missing bounded identity retry: {marker}")

    worker_end = entry.find("bool initializeProductSurveyWorker()", product_worker)
    if product_worker < 0 or worker_end <= product_worker:
        errors.append("product Survey terminal ownership could not be inspected")
    else:
        worker_body = entry[product_worker:worker_end]
        if "setProductSurveyControl(ProductSurveyWorkerControl::Idle)" in worker_body:
            errors.append(
                "product Survey worker exposes Idle before UI consumes terminal event"
            )
        release_start = entry.find("void releaseProductSurveyAfterTerminal(")
        service_start = entry.find("void serviceProductSurveyWorker()", release_start)
        service_end = entry.find("void recoverProductCatalogForFingerprint(", service_start)
        terminal_ui = entry[release_start:service_end]
        if terminal_ui.count(
                "setProductSurveyControl(ProductSurveyWorkerControl::Idle)") < 2:
            errors.append(
                "product Survey UI does not acknowledge both cleanup and commit terminals"
            )

    product_start = entry.find("bool startProductSurvey()")
    product_stop = entry.find("SurveyPipelineStatus stopProductSurvey()", product_start)
    if product_start < 0 or product_stop <= product_start:
        errors.append("non-blocking product Survey action could not be inspected")
    else:
        product_start_action = entry[product_start:product_stop]
        for forbidden_call in ("scanner.scan(", "productSurveyFilesystem.begin("):
            if forbidden_call in product_start_action:
                errors.append(
                    "product Survey UI action contains blocking hardware work: "
                    f"{forbidden_call}"
                )
        for marker in (
            "ProductSurveyWorkerControl::Starting",
            "xTaskNotifyGive(productSurveyWorkerTaskHandle)",
            "productSurveyRuntime.startActionUs",
        ):
            if marker not in product_start_action:
                errors.append(
                    f"product Survey UI action is missing worker handoff: {marker}"
                )

    for marker in (
        "setProductSurveyScanActive(true);",
        "setProductSurveyScanActive(false);",
        '\\"survey_product_scan_active\\"',
        "productSurveyRuntime.cancelRequestedDuringScan = scanWasActive;",
        '\\"survey_product_cancel_requested_during_scan\\"',
        "BoardWifiPassiveScanner::cancelActiveScan();",
        "BoardBlePassiveScanner::cancelActiveScan();",
    ):
        if marker not in entry:
            errors.append(
                f"product Survey active-scan cancellation evidence is missing: {marker}"
            )

    for marker in (
        "survey.product.test-source-unavailable once|clear",
        "consumeProductSurveySourceUnavailableInjection()",
        "productSurveySourceUnavailableVisible()",
        "report.sourceStartAttempted = !report.sourceFailureInjected",
        "report.storeOpenAttempted = true",
        "releaseProductSurveyAfterTerminal(event.report.status, !keepVisible)",
        "source_unavailable_waiting_back",
        '\\"survey_product_source_start_attempted\\"',
        '\\"survey_product_store_open_attempted\\"',
        '\\"survey_product_store_bytes_written\\"',
    ):
        if marker not in entry:
            errors.append(
                f"product Survey missing-source evidence is missing: {marker}"
            )
    source_failure = entry.find("report.sourceFailureInjected =")
    store_open = entry.find("report.storeOpenAttempted = true", source_failure)
    if source_failure < 0 or store_open <= source_failure:
        errors.append("missing-source/store-open ordering could not be inspected")
    else:
        source_boundary = entry[source_failure:store_open]
        for marker in (
            "wifiScanner->begin()",
            "bleScanner->begin()",
            "authorizeProductSurvey",
        ):
            if marker not in source_boundary:
                errors.append(
                    f"missing-source boundary is missing before store open: {marker}"
                )
        if "openExistingWritable" in source_boundary:
            errors.append("missing-source path can open the store before admission")

    if not product_start_retry_path.is_file():
        errors.append("Product Start identity retry policy is missing")
    else:
        product_start_retry = product_start_retry_path.read_text(encoding="utf-8")
        product_start_retry += "\n" + product_start_retry_path.with_suffix(".h").read_text(
            encoding="utf-8"
        )
        for marker in (
            "kProductStartMaximumIdentityAttempts = 8",
            "SdTransportRunStatus::ExchangeFailed",
            "SdTransportRunStatus::InitTimeout",
            "SdTransportRunStatus::ParseRejected",
            "identityCleanupComplete",
            "!evidence.filesystemAttempted",
        ):
            if marker not in product_start_retry:
                errors.append(f"Product Start identity retry policy is missing: {marker}")

    if not session_store_router.is_file():
        errors.append("allocation-free SessionStore backend router is missing")
    else:
        router = session_store_router.read_text(encoding="utf-8")
        for marker in (
            "backend_->writeFile",
            "backend_->readFile",
            "backend_->syncFile",
            "backend_->syncDirectory",
        ):
            if marker not in router:
                errors.append(f"SessionStore backend router is missing: {marker}")

    recovery_start = entry.find("void recoverProductCatalogForFingerprint(")
    recovery_end = entry.find("void recoverProductCatalogAtBoot()", recovery_start)
    if recovery_start < 0 or recovery_end <= recovery_start:
        errors.append("bounded product recovery function could not be inspected")
    else:
        recovery_body = entry[recovery_start:recovery_end]
        for forbidden_call in ("freeBytes(", "filesystemCapacityBytes("):
            if forbidden_call in recovery_body:
                errors.append(
                    "boot product recovery contains unbounded FAT geometry scan: "
                    f"{forbidden_call}"
                )

    watchdog_start = entry.find("bool IRAM_ATTR recordProductBootRecoveryTimeout(")
    watchdog_end = entry.find("bool armProductBootRecoveryWatchdog()", watchdog_start)
    if watchdog_start < 0 or watchdog_end <= watchdog_start:
        errors.append("boot recovery watchdog function could not be inspected")
    else:
        watchdog_body = entry[watchdog_start:watchdog_end]
        for marker in ("__atomic_exchange_n", "++productBootRetryRestarts",
                       "++productBootRetryTimeouts",
                       "esp_task_wdt_isr_user_handler",
                       "esp_restart_noos();"):
            if marker not in watchdog_body:
                errors.append(f"boot recovery watchdog is missing: {marker}")
        for forbidden in ("broadcast(", "Serial", ".flush(", "BoardSd",
                          "recoverProduct", "resourceBroker"):
            if forbidden in watchdog_body:
                errors.append(
                    "boot recovery watchdog contains blocking work before restart: "
                    f"{forbidden}"
                )

    watchdog_arm_start = entry.find("bool armProductBootRecoveryWatchdog()")
    watchdog_arm_end = entry.find("void recoverProductCatalogAtBoot()",
                                  watchdog_arm_start)
    if watchdog_arm_start < 0 or watchdog_arm_end <= watchdog_arm_start:
        errors.append("hardware boot recovery watchdog could not be inspected")
    else:
        watchdog_arm_body = entry[watchdog_arm_start:watchdog_arm_end]
        for marker in ("esp_task_wdt_status(nullptr)",
                       "esp_task_wdt_add(nullptr)",
                       "esp_task_wdt_reset()", "esp_task_wdt_delete(nullptr)"):
            if marker not in watchdog_arm_body:
                errors.append(
                    f"hardware boot recovery watchdog is missing: {marker}"
                )

    for marker in (
        "shouldResetProductBootRetryState",
        "isProductBootRetryReset",
        "productBootRetryAppIdentity",
        "kProductBootRecoveryWatchdogMs",
        "kProductBootRecoveryHardwareWatchdogMs",
        "recovery_timeout_exhausted",
        "storage.product.boot-watchdog-test confirm",
        '\\"timeout_restarts\\"',
    ):
        if marker not in entry:
            errors.append(f"Arduino entry is missing bounded boot recovery: {marker}")

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

    for marker in (
        "storage.littlefs.parity disposable-ota1 ",
        "DisposableOtaLittleFs filesystem",
        "filesystem.safeInactiveTarget()",
        "filesystem.hashTarget(observedFingerprint",
        "std::strcmp(expectedFingerprint, observedFingerprint) == 0",
        "filesystem.formatAndMountWritable()",
        "ArduinoLittleFsSessionStoreIo io(filesystem)",
        "filesystem.mountReadOnly()",
        '\\"product_partition_touched\\":false',
        '\\"nvs_touched\\":false',
        '\\"sd_accessed\\":false',
        '\\"radio_touched\\":false',
        '\\"ota1_restore_required\\":true',
    ):
        if marker not in entry:
            errors.append(f"guarded LittleFS parity command is missing: {marker}")
    littlefs_start = entry.find("void emitLittleFsParity(")
    littlefs_end = entry.find("void broadcast(", littlefs_start)
    if littlefs_start < 0 or littlefs_end <= littlefs_start:
        errors.append("LittleFS parity function could not be inspected")
    else:
        littlefs_body = entry[littlefs_start:littlefs_end]
        hash_check = littlefs_body.find("filesystem.hashTarget(")
        format_call = littlefs_body.find("filesystem.formatAndMountWritable()")
        if hash_check < 0 or format_call <= hash_check:
            errors.append(
                "LittleFS target must be hashed and matched before format"
            )
        for forbidden_call in (
            "BoardSd", "productSurveyFilesystem", "saveProductFingerprint",
            "clearProductFingerprint", "WiFi", "esp_wifi_",
        ):
            if forbidden_call in littlefs_body:
                errors.append(
                    "LittleFS parity can touch an unrelated product subsystem: "
                    f"{forbidden_call}"
                )

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

    if not littlefs_runner_path.is_file():
        errors.append("guarded LittleFS parity runner is missing")
    else:
        littlefs_runner = littlefs_runner_path.read_text(encoding="utf-8")
        for marker in (
            "OTA1_OFFSET = 0x410000",
            "OTA1_SIZE = 0x400000",
            "PARTITION_TABLE_OFFSET = 0x8000",
            "two independent reads differ",
            "RESTORE_ATTEMPTS = 3",
            "READ_ATTEMPTS = 3",
            "read_flash_with_retry(",
            "restore_flash(",
            "OTA1 restore remained unverified",
            "private_backup_deleted_after_verified_restore",
            "partition_table_unchanged",
            "unchanged_recovery_failures",
        ):
            if marker not in littlefs_runner:
                errors.append(f"guarded LittleFS runner is missing: {marker}")

    for marker in (
        "storage.littlefs.reset disposable-ota1 ",
        "storage.littlefs.reset recover read-only ",
        "armLittleFsResetContinuity",
        "littleFsResetContinuityValid",
        "kLittleFsResetRtcMagic",
        "restartAtLittleFsSessionStoreBoundary",
        "ESP_RST_SW",
        "filesystem.hashTarget(observedFingerprint",
        "filesystem.formatAndMountWritable()",
        "filesystem.mountReadOnly()",
        "authorizeExistingScratchRead",
        '\\"continuity_valid\\":%s',
        '\\"product_partition_touched\\":false',
        '\\"sd_accessed\\":false',
        '\\"nvs_touched\\":false',
        '\\"radio_touched\\":false',
    ):
        if marker not in entry:
            errors.append(f"guarded LittleFS reset command is missing: {marker}")
    littlefs_reset_start = entry.find("void emitLittleFsResetArm(")
    littlefs_reset_end = entry.find("void broadcast(", littlefs_reset_start)
    if littlefs_reset_start < 0 or littlefs_reset_end <= littlefs_reset_start:
        errors.append("LittleFS reset functions could not be inspected")
    else:
        littlefs_reset_body = entry[littlefs_reset_start:littlefs_reset_end]
        hash_check = littlefs_reset_body.find("filesystem.hashTarget(")
        format_call = littlefs_reset_body.find(
            "filesystem.formatAndMountWritable()"
        )
        recovery_start = littlefs_reset_body.find(
            "void emitLittleFsResetRecovery("
        )
        if hash_check < 0 or format_call <= hash_check:
            errors.append(
                "LittleFS reset target must be hashed and matched before format"
            )
        if recovery_start < 0:
            errors.append("LittleFS reset recovery function is missing")
        else:
            recovery_body = littlefs_reset_body[recovery_start:]
            if "formatAndMountWritable" in recovery_body:
                errors.append("LittleFS reset recovery can format or write target")
            for marker in (
                "littleFsResetContinuityValid(",
                "resetReason == ESP_RST_SW",
                "filesystem.mountReadOnly()",
                "io.openExistingReadOnly(permit)",
                "bytesWritten == 0",
                "fileSyncs == 0",
                "directorySyncs == 0",
            ):
                if marker not in recovery_body:
                    errors.append(
                        f"LittleFS reset read-only recovery is missing: {marker}"
                    )
        for forbidden_call in (
            "BoardSd", "productSurveyFilesystem", "saveProductFingerprint",
            "clearProductFingerprint", "WiFi", "esp_wifi_",
        ):
            if forbidden_call in littlefs_reset_body:
                errors.append(
                    "LittleFS reset can touch an unrelated product subsystem: "
                    f"{forbidden_call}"
                )

    if not littlefs_reset_runner_path.is_file():
        errors.append("guarded LittleFS reset matrix runner is missing")
    else:
        littlefs_reset_runner = littlefs_reset_runner_path.read_text(
            encoding="utf-8"
        )
        for marker in (
            "--execute-reset-matrix",
            "two independent reads differ",
            "read_flash_with_retry(",
            "restore_flash_single_write(",
            'stats["write_attempts"] = 1',
            "restore_read_attempt_limit",
            "private_backup_deleted_after_verified_restore",
            "partition_table_unchanged",
            "target_fingerprint_before",
            "continuity_valid",
            "unchanged_recovery_failures",
            'boundaries == list(BOUNDARIES)',
        ):
            if marker not in littlefs_reset_runner:
                errors.append(
                    f"guarded LittleFS reset runner is missing: {marker}"
                )

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
