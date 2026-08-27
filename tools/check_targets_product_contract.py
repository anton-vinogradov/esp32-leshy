#!/usr/bin/env python3
"""Fail-closed source contract for the on-device Targets product slice."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    entry = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text()
    catalog = (ROOT / "firmware/leshy1/src/domain/apps/AppCatalog.cpp").read_text()
    strings = (ROOT / "firmware/leshy1/src/ui/UiStrings.def").read_text()
    controller = (ROOT / "firmware/leshy1/src/apps/targets/TargetsController.cpp").read_text()
    comparison = (ROOT / "firmware/leshy1/src/domain/targets/TargetComparison.cpp").read_text()
    comparison_header = (ROOT / "firmware/leshy1/src/domain/targets/TargetComparison.h").read_text()
    comparison_service = (ROOT / "firmware/leshy1/src/services/targets/TargetComparisonService.h").read_text()
    comparison_service_source = (ROOT / "firmware/leshy1/src/services/targets/TargetComparisonService.cpp").read_text()
    runner = (ROOT / "tools/run_1x_targets_hil.py").read_text()
    mount_runner = (ROOT / "tools/run_1x_targets_mount_regression_hil.py").read_text()
    evidence_runner = (ROOT / "tools/run_1x_targets_evidence_hil.py").read_text()
    favorite_runner = (ROOT / "tools/run_1x_targets_favorite_hil.py").read_text()
    name_runner = (ROOT / "tools/run_1x_targets_name_hil.py").read_text()
    tags_runner = (ROOT / "tools/run_1x_targets_tags_hil.py").read_text()
    notes_runner = (ROOT / "tools/run_1x_targets_notes_hil.py").read_text()
    correlation_runner = (
        ROOT / "tools/run_1x_targets_correlation_hil.py").read_text()
    correlation_recovery_runner = (
        ROOT / "tools/run_1x_targets_correlation_recovery_hil.py").read_text()
    merge_split_runner = (
        ROOT / "tools/run_1x_targets_merge_split_hil.py").read_text()
    correlation_fixture_runner = (
        ROOT / "tools/run_1x_targets_correlation_fixture_hil.py").read_text()
    correlation_fixture = (
        ROOT / "tests/hil/fixtures/correlation-beacon/src/main.cpp").read_text()
    correlation_review_header = (
        ROOT / "firmware/leshy1/src/services/targets/SessionCorrelationReview.h").read_text()
    correlation_review = (
        ROOT / "firmware/leshy1/src/services/targets/SessionCorrelationReview.cpp").read_text()
    target_catalog = (
        ROOT / "firmware/leshy1/src/domain/targets/TargetCatalog.cpp").read_text()
    correlation = (
        ROOT / "firmware/leshy1/src/domain/targets/Correlation.cpp").read_text()
    target_merge = (
        ROOT / "firmware/leshy1/src/domain/targets/TargetMerge.cpp").read_text()
    target_codec = (
        ROOT / "firmware/leshy1/src/storage/TargetCodec.cpp").read_text()
    merge_decode_start = target_codec.index("decodeAndRestoreMerge(")
    merge_decode_end = target_codec.index("}  // namespace", merge_decode_start)
    merge_decode = target_codec[merge_decode_start:merge_decode_end]
    stack_checker = (
        ROOT / "tools/check_targets_stack_elf_contract.py").read_text()
    storage_guard = (
        ROOT / "firmware/leshy1/src/storage/StorageGuard.cpp").read_text()
    disposable_ota = (
        ROOT / "firmware/leshy1/src/platform/arduino/DisposableOtaLittleFs.cpp"
    ).read_text()
    littlefs_io = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoLittleFsSessionStoreIo.cpp"
    ).read_text()
    littlefs_io_header = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoLittleFsSessionStoreIo.h"
    ).read_text()
    fs_io = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoFsSessionStoreIo.cpp"
    ).read_text()
    fs_io_header = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoFsSessionStoreIo.h"
    ).read_text()

    require(failures,
            '"targets", "TARGETS"' in catalog and
            '"saved identities / compare visits"' in catalog and
            "Resource::Storage" in catalog and "Resource::RadioSpi" in catalog,
            "Targets must be a real saved-session Home product with exact leases")
    require(failures,
            "TargetsProductRuntime* targetsProductRuntime = nullptr" in entry and
            "new (std::nothrow) TargetsProductRuntime" in entry and
            "delete targetsProductRuntime" in entry and
            "TargetsWorkspace targets" not in entry,
            "Targets workspace must have foreground-only bounded lifetime")
    load_start = entry.index("bool loadTargetsProduct")
    load_end = entry.index("bool rebuildTargetsProductFromCatalog")
    load_product = entry[load_start:load_end]
    require(failures,
            load_product.rfind("filesystem.end();") <
                load_product.rfind("allocateTargetsProduct(") and
            "product state is first decoded into the three long-lived state "
            "blocks" in load_product and
            "wire workspace is then released before the remaining runtime"
            in load_product and
            load_product.index(
                "releaseTargetsStoreCodecWorkspace(targetStateWorkspace);",
                load_product.index("reopenTargetState(")) <
                load_product.index("finishTargetsProductAllocation(",
                                   load_product.index("reopenTargetState(")) and
            "recoverTargetProductStateWire(" in load_product and
            "persistedCatalog" not in load_product and
            "persistedDecisions" not in load_product and
            "reopenTargetState(" in load_product and
            "catalog, decisions, merges);" in load_product and
            "new (std::nothrow) TargetCatalog" in entry and
            "new (std::nothrow) CorrelationDecisionLog" in entry and
            "new (std::nothrow) TargetMergeHistory" in entry and
            "SessionCorrelationProposalSet();" in entry and
            "TargetComparisonResult();" in entry and
            "new (std::nothrow) TargetsWorkspace" in entry and
            "new (std::nothrow) TargetsController" in entry and
            "filesystem_mount_error" in entry,
            "Targets must checksum-select wire state without duplicate decoded "
            "copies, release FatFs, decode into the three retained state blocks, "
            "release the wire workspace before completing the split no-PSRAM "
            "runtime, and expose the exact mount result")
    mutation_start = entry.index("void runTargetsMutationWorker")
    mutation_end = entry.index("bool requestTargetsFavoriteMutation")
    mutation_worker = entry[mutation_start:mutation_end]
    require(failures,
            load_product.index("acquireTargetsStoreCodecWorkspace()") >
                load_product.index("filesystem.beginReadOnly()") and
            "new (std::nothrow)\n"
            "                    leshy1::storage::"
            "TargetDecisionStateStoreWorkspace();" not in load_product and
            load_product.count(
                "releaseTargetsStoreCodecWorkspace(targetStateWorkspace);")
                >= 4 and
            mutation_worker.index("acquireTargetsStoreCodecWorkspace()") >
                mutation_worker.index("filesystem.begin()") and
            "shared_codec_unavailable_after_mount" in mutation_worker and
            mutation_worker.index("acquireTargetsStoreCodecWorkspace()") <
                mutation_worker.index("openExistingWritable") and
            "new (std::nothrow)\n            leshy1::storage::TargetDecisionStateStoreWorkspace" not in
                mutation_worker and
            "releaseTargetsStoreCodecWorkspace(workspace)" in mutation_worker and
            "union TargetsStoreCodecWorkspace final" in entry and
            "TargetCatalog admissionScratch" in entry and
            "loadWithAdmissionScratch(" in controller and
            "acquireTargetsAdmissionScratch()" in entry and
            "releaseTargetsAdmissionScratch(scratch)" in entry and
            "SessionStoreWorkspace& sessionStoreWorkspace" in entry and
            r'\"mutation_heap_largest_before_mount\":%lu' in entry and
            "kTargetsMaximumMountAttempts = 3" in load_product and
            "filesystem.cleanupComplete()" in load_product and
            r'\"filesystem_mount_attempts\":%u' in entry and
            r'\"filesystem_mount_transient_retries\":%u' in entry,
            "Targets read and mutation paths must mount before activating the "
            "shared session/decision codec so a saturated correlation visit "
            "cannot starve FatFs; mutation still activates it before writable "
            "open, releases it on every exit and remains fail-closed")
    require(failures,
            "new (std::nothrow) domain::targets::TargetCatalog" in controller and
            "delete scratch" in controller and
            "TargetCatalog scratch" not in controller,
            "large admission scratch must be transient, checked and released")
    require(failures,
            "compareTargetSessionsInto(" in comparison and
            "new (std::nothrow) ComparisonScratch" in comparison and
            "std::unique_ptr<ComparisonScratch>" in comparison and
            "TargetComparisonResult compareTargetSessions(" not in
                comparison_header and
            "executeInto(" in comparison_service and
            "workspace_.comparison = comparison.execute" not in controller,
            "on-device comparison must use caller-owned result storage and "
            "checked/released heap scratch, never a multi-KiB value return")
    require(failures,
            "resetTargetComparisonResult" in comparison_header and
            "std::memset(static_cast<void*>(output), 0, sizeof(*output))" in comparison and
            "workspace_.comparison = {}" not in controller and
            "resetTargetComparisonResult(&workspace_.comparison)" in controller and
            "*output = {}" not in comparison_service_source,
            "large comparison results must reset in place without aggregate "
            "stack temporaries")
    require(failures,
            "openWifiVisitProduct()" in entry and
            "WifiProductView::Visit" in entry and
            "UiTextId::WifiMenuVisit" in entry and
            "wifiProductSelection == 3" in entry and
            "Listen with every available built-in receiver" in
                entry[entry.index("bool openWifiVisitProduct()"):
                      entry.index("bool stopWifiChannelsProduct()")] and
            "SurveySourceScope::All" in
                entry[entry.index("bool openWifiVisitProduct()"):
                      entry.index("bool stopWifiChannelsProduct()")],
            "final Wi-Fi menu must expose a public persistent Visit path "
            "that defaults to every available built-in receiver")
    require(failures,
            "filesystem.beginReadOnly()" in entry and
            "recoverSessionPair(" in entry and
            "loadProductFingerprint(" in entry and
            "fingerprint_mismatch" in entry and
            "targetsBlockedWriteAttempts" in entry,
            "persistent Target reads must be exact-CID, read-only and observable")
    require(failures,
            'std::strcmp(command, "targets.state")' in entry and
            "leshy.targets.product.v1" in entry and
            r'\"catalog_count\":%u' in entry and
            r'\"catalog_capacity\":%u' in entry and
            r'\"read_only\":false' in entry and
            r'\"write_enabled\":%s' in entry and
            r'\"mutation_state\":\"%s\"' in entry and
            "commitTargetProductState(" in entry and
            "recoverTargetProductState(" in entry and
            "TargetActionKind::SetFavorite" in entry and
            "TargetActionKind::SetName" in entry and
            "TargetActionKind::SetNotes" in entry and
            "TargetActionKind::AddTag" in entry and
            "TargetActionKind::RemoveTag" in entry and
            r'\"selected_name_hex\":\"%s\"' in entry and
            r'\"name_editor_dirty\":%s' in entry and
            r'\"selected_tag_hex\":\"%s\"' in entry and
            r'\"tag_editor_can_save\":%s' in entry and
            r'\"selected_notes_prefix_hex\":\"%s\"' in entry and
            r'\"notes_editor_dirty\":%s' in entry and
            r'\"selected_graph_fingerprint\":\"%s\"' in entry and
            r'\"merge_history_count\":%u' in entry and
            r'\"mutation_merge_status\":\"%s\"' in entry,
            "Targets needs a machine-readable release-test state")
    require(failures,
            "buildSessionCorrelationReview(" in controller and
            "sessionCorrelationCandidatePending(" in controller and
            "CorrelationDecisionLog* targetsMutationDecisions" in entry and
            "TargetMergeHistory* targetsMutationMerges" in entry and
            "adoptTargetsProductState(" in entry and
            "finishTargetsProductAllocation(catalog, decisions, merges, false)" in
                entry and
            "catalog = nullptr;" in entry and
            "decisions = nullptr;" in entry and
            "merges = nullptr;" in entry and
            "event.targetId, true, event.catalogRecovered" in entry and
            "CorrelationService service(*catalog, *decisions, lookup)" in entry and
            "requestTargetsCorrelationMutation(" in entry and
            r'\"correlation_count\":%u' in entry and
            r'\"correlation_decision_count\":%u' in entry and
            r'\"correlation_proposal_id\":\"%s\"' in entry and
            r'\"correlation_candidate_identity_hex\":\"%s\"' in entry and
            r'\"correlation_feature_kind\":\"%s\"' in entry and
            r'\"correlation_known_generation\":%lu' in entry and
            r'\"correlation_candidate_generation\":%lu' in entry and
            r'\"selected_observation_radio\":%u' in entry and
            r'\"selected_observation_identity_hex\":\"%s\"' in entry and
            r'\"selected_observation_label_hex\":\"%s\"' in entry and
            r'\"mutation_correlation_status\":\"%s\"' in entry,
            "Targets correlation review must keep candidates independent, "
            "show explainable proposals, atomically persist accept/reject and "
            "adopt the verified worker state without duplicate heap blocks")
    require(failures,
            "resetSessionCorrelationProposalSet(" in correlation_review_header and
            "resetSessionCorrelationProposalSet(" in correlation_review and
            "std::memset(static_cast<void*>(output), 0, sizeof(*output))" in
                correlation_review and
            "*output = {}" not in correlation_review and
            '"buildSessionCorrelationReview(": 1024' in stack_checker and
            '"CorrelationService::propose(": 768' in stack_checker,
            "multi-KiB correlation proposal results must reset in place and "
            "the exact ELF gate must cover the complete proposal call chain")
    require(failures,
            "validateTargetRecord(record.destinationBefore)" in target_merge and
            "validateTargetRecord(record.sourceBefore)" in target_merge and
            "validateTargetRecordCompatibility(" in target_merge and
            "TargetCatalog candidate;" not in target_merge and
            "catalog.replaceAndRemove(" in target_merge and
            "catalog.replaceAndInsert(" in target_merge and
            "TargetMutationStatus TargetCatalog::replaceAndRemove(" in
                target_catalog and
            "TargetMutationStatus TargetCatalog::replaceAndInsert(" in
                target_catalog and
            "appCatalog.rebuild(inventory, "
                "targetsMergeFixtureContinuityValid())" in entry and
            "bool targetsMergeFixture" in catalog and
            "targetsAvailable" in catalog and
            "targetsSimulated" in catalog and
            "TargetCatalog validation" not in target_merge and
            "beginPersistenceRestore()" in target_merge and
            "commitPersistenceRestore()" in target_merge and
            "cancelPersistenceRestore()" in target_merge and
            "merges.beginPersistenceRestore()" in target_codec and
            "merges.cancelPersistenceRestore()" in target_codec and
            "merges.commitPersistenceRestore()" in target_codec and
            "TargetMergeRecord record{}" not in merge_decode and
            "resetDecodedAggregate(output)" in target_codec and
            "*output = {};" not in target_codec and
            "#define LESHY_CODEC_NOINLINE "
                "__attribute__((noinline, noclone))" in target_codec and
            target_codec.count("LESHY_CODEC_NOINLINE TargetCodecStatus "
                               "decode") >= 5 and
            "std::memset(static_cast<void*>(records_.data()), 0, "
                "sizeof(records_))" in target_catalog and
            "std::memset(static_cast<void*>(records_.data()), 0, "
                "sizeof(records_))" in target_merge and
            "std::memset(static_cast<void*>(records_.data()), 0, "
                "sizeof(records_))" in correlation,
            "persisted merge decode must validate in place through one "
            "invisible transactional history slot without a multi-KiB local "
            "record or validation catalog")
    require(failures,
            "TargetMutationStatus validateTargetRecord(" in target_catalog and
            "TargetMutationStatus validateTargetRecordCompatibility(" in
                target_catalog and
            '"decodeTargetState(": 256' in stack_checker and
            '"decodeRecord(": 256' in stack_checker and
            '"decodeCorrelationFeature(": 256' in stack_checker and
            '"decodeCorrelationProposal(": 256' in stack_checker and
            '"decodeCorrelationDecision(": 256' in stack_checker and
            '"decodeTargetMerge(": 256' in stack_checker and
            '"decodeAndRestoreTarget(": 1024' in stack_checker and
            '"decodeAndRestoreDecision(": 768' in stack_checker and
            '"decodeAndRestoreMerge(": 512' in stack_checker and
            '"TargetMergeHistory::commitPersistenceRestore()": 512' in
                stack_checker and
            '"validateTargetRecord(": 512' in stack_checker and
            '"validateTargetRecordCompatibility(": 256' in stack_checker and
            '"TargetMergeHistory::merge(": 3072' in stack_checker and
            '"TargetMergeHistory::split(": 2048' in stack_checker and
            '"TargetCatalog::replaceAndRemove(": 1024' in stack_checker and
            '"TargetCatalog::replaceAndInsert(": 768' in stack_checker and
            '"TargetCatalog::clear()": 128' in stack_checker and
            '"CorrelationDecisionLog::clear()": 128' in stack_checker and
            '"TargetMergeHistory::clear()": 128' in stack_checker and
            '"reopenTargetState(": 512' in stack_checker and
            '"loadTargetsProduct(": 1024' in stack_checker,
            "the exact production ELF gate must cover every frame in the "
            "Targets persistence-decode call chain")
    require(failures,
            "lastAdmissionStage()" in entry and
            "lastAdmission()" in entry and
            r'\"admission_stage\":\"%s\"' in entry and
            r'\"admission_status\":\"%s\"' in entry and
            r'\"admission_target_status\":\"%s\"' in entry and
            r'\"admission_observations\":%u' in entry and
            r'\"admission_identities\":%u' in entry and
            r'\"admission_capacity_skipped\":%u' in entry,
            "Targets must expose the exact admission stage and bounded "
            "mutation reason when a persisted projection cannot be loaded")
    require(failures,
            '"git", "rev-parse", "HEAD"' in runner and
            '"git", "status", "--porcelain"' in runner and
            "--reuse-exact-flash" in runner and
            "--reuse-existing-pair" in runner and
            '"survey_cycles_executed": 0 if args.reuse_existing_pair else 2'
                in runner and
            "checked_stack_frames = stack_frames(args.elf)" in runner and
            "def navigation_action(" in merge_split_runner and
            'state["host_navigation_action_replays"] = 0' in
                merge_split_runner and
            "minimum_target_count=1" in merge_split_runner and
            'record["targets_after_open"] = listed' in runner and
            'write_json(args.output / "run.json", record)' in runner and
            "best_effort_cleanup(device)" in runner and
            "leshy.targets_mount_regression_hil.run.v1" in mount_runner and
            "checked_stack_frames = stack_frames(args.elf)" in mount_runner and
            "storage_write_calls\": 0" in mount_runner and
            "leshy.targets_evidence_hil.run.v1" in evidence_runner and
            "validate_evidence" in evidence_runner and
            "comparison order is not class/signal stable" in evidence_runner and
            "new_passive_scans_required" not in evidence_runner,
            "Targets HIL must bind exact clean HEAD, clean up failures and "
            "use a focused read-only exact-evidence delta when no new scans "
            "are needed")
    require(failures,
            "leshy.targets_favorite_hil.run.v1" in favorite_runner and
            "exact HIL requires clean committed HEAD" in favorite_runner and
            "selected_favorite=not favorite_before" in favorite_runner and
            "target_state_generation_after" in favorite_runner and
            "targets-favorite-cold-reopen" in favorite_runner and
            "mutation_directory_syncs" in favorite_runner,
            "favorite mutation HIL must bind a clean exact candidate, atomic "
            "sync evidence and cold recovery of the same stable Target ID")
    require(failures,
            "leshy.targets_name_hil.run.v1" in name_runner and
            "exact HIL requires clean committed HEAD" in name_runner and
            "name_editor_dirty=True" in name_runner and
            "selected_name_hex=name_after.hex().upper()" in name_runner and
            "target_state_generation_after" in name_runner and
            "targets-name-cold-reopen" in name_runner and
            "mutation_directory_syncs" in name_runner,
            "name mutation HIL must bind a clean exact candidate, exercise the "
            "on-device editor, atomically sync and cold-reopen the same name")
    require(failures,
            "leshy.targets_tags_hil.run.v1" in tags_runner and
            "exact HIL requires clean committed HEAD" in tags_runner and
            "tag_editor_can_save=True" in tags_runner and
            "generation_added = generation_before + 1" in tags_runner and
            "generation_removed = generation_added + 1" in tags_runner and
            "targets-tags-added-cold-reopen" in tags_runner and
            "targets-tags-removed-cold-reopen" in tags_runner and
            "mutation_directory_syncs" in tags_runner,
            "tag mutation HIL must bind a clean exact candidate, exercise "
            "bounded add/remove and cold-reopen both durable outcomes")
    require(failures,
            "leshy.targets_notes_hil.run.v1" in notes_runner and
            "exact HIL requires clean committed HEAD" in notes_runner and
            "notes_editor_dirty=True" in notes_runner and
            "generation_set = generation_before + 1" in notes_runner and
            "generation_cleared = generation_set + 1" in notes_runner and
            "targets-notes-set-cold-reopen" in notes_runner and
            "targets-notes-clear-cold-reopen" in notes_runner and
            "mutation_directory_syncs" in notes_runner,
            "notes mutation HIL must bind a clean exact candidate, exercise "
            "bounded set/clear and cold-reopen both durable outcomes")
    require(failures,
            "leshy.targets_correlation_hil.run.v1" in correlation_runner and
            "exact HIL requires clean committed HEAD" in correlation_runner and
            "MAX_FRESH_SURVEY_CYCLES = 4" in correlation_runner and
            "validate_proposal" in correlation_runner and
            "correlation_evidence_candidate=False" in correlation_runner and
            "correlation_evidence_candidate=True" in correlation_runner and
            "host_reconnects" in correlation_runner and
            "device.open()" in correlation_runner and
            "def fixture_label" in correlation_runner and
            "def known_wifi_fixture_label" in correlation_runner and
            'PREFERRED_FIXTURE_LABEL = "Keenetic-5070"' in
                correlation_runner and
            "selected_fixture_label is None and scans" in
                correlation_runner and
            'fixture_mode(fixture, "ble")' in correlation_runner and
            'fixture_mode(fixture, "wifi")' not in correlation_runner and
            'choices=("accept", "reject")' in correlation_runner and
            'status = "accepted" if decision == "accept" else "rejected"' in
                correlation_runner and
            'target_count_before + (' in correlation_runner and
            'rejected identity did not remain independent' in
                correlation_runner and
            "correlation_decision_count=decisions_after" in
                correlation_runner and
            "source_identity_count=identities_before" in
                correlation_runner and
            "source_identity_count=identities_before + 1" not in
                correlation_runner and
            'f"targets-correlation-{args.decision}-cold-reopen"' in
                correlation_runner and
            "mutation_directory_syncs" in correlation_runner,
            "correlation HIL must find one bounded natural proposal, review "
            "both exact observations, atomically accept or reject and "
            "cold-reopen exact ownership plus the same decision log")
    require(failures,
            "leshy.targets_correlation_recovery_hil.run.v1" in
                correlation_recovery_runner and
            "exact HIL requires clean committed HEAD" in
                correlation_recovery_runner and
            "targets-correlation-recovery-cold-boot" in
                correlation_recovery_runner and
            "selected_revision=revision_before + 1" in
                correlation_recovery_runner and
            "correlation_decision_count=decisions_before + 1" in
                correlation_recovery_runner and
            "source_identity_count=identities_before" in
                correlation_recovery_runner and
            '"flash_count": 0' in correlation_recovery_runner and
            '"cardputer_ports_opened": 0' in correlation_recovery_runner,
            "correlation recovery HIL must bind the exact precursor, cold-open "
            "the advanced Target and decision log, preserve immutable source "
            "cardinality and touch only the explicit DUT port")
    require(failures,
            "leshy.targets_merge_split_hil.run.v1" in merge_split_runner and
            "exact HIL requires clean committed HEAD" in merge_split_runner and
            '"cardputer_ports_opened": 0' in merge_split_runner and
            '"port_discovery_calls": 0' in merge_split_runner and
            "targets-merge-cold-reopen" in merge_split_runner and
            "targets-split-cold-reopen" in merge_split_runner and
            "targets-merge-split-initial-boot" in merge_split_runner and
            'states["controlled_initial_boot"]' in merge_split_runner and
            "--clear-proven-preexisting-safety-latch" in merge_split_runner and
            '"safety_latched" not in predecessor_error' in
                merge_split_runner and
            'b"safety.clear confirm"' in merge_split_runner and
            "targets-merge-split-safety-cleared-boot" in merge_split_runner and
            "selected_graph_fingerprint=destination_graph" in
                merge_split_runner and
            "selected_graph_fingerprint=source_graph" in merge_split_runner and
            "mutation_merge_status=\"merged\"" in merge_split_runner and
            "mutation_merge_status=\"split\"" in merge_split_runner and
            "mutation_directory_syncs" in merge_split_runner and
            "MUTATION_ACTION_ACK_TIMEOUT = 5.0" in merge_split_runner and
            merge_split_runner.count(
                "trigger_mutation_once(device)") == 2 and
            '"action_replays": 0' in merge_split_runner and
            "capture_mutation_loss_diagnostics" in merge_split_runner and
            'b"targets.merge-split-fixture state"' in merge_split_runner and
            'b"safety.state"' in merge_split_runner and
            "kTargetsStoreTaskStackBytes = 12288U" in entry and
            entry.count("kTargetsStoreTaskStackBytes, nullptr, 1,") == 3 and
            "TargetsMergeFixtureMutationStage::CommitStarted" in entry and
            r'\"mutation_stage\":\"%s\"' in entry and
            r'\"reset_reason_code\":%u' in entry and
            "TargetsLoadWatchdogScope" in entry and
            "load_watchdog_feeds" in entry and
            "load_maximum_phase_us" in entry,
            "merge/split HIL must use only the explicit DUT port, require two "
            "explicit confirmations, atomically publish both transitions and "
            "cold-reopen both exact pre-merge ownership graphs while the "
            "bounded synchronous load keeps the hardware watchdog live")
    fixture_worker_start = entry.index(
        "void runTargetsMergeFixtureMutationWorker")
    fixture_worker_end = entry.index(
        "void runTargetsMutationWorker", fixture_worker_start)
    fixture_worker = entry[fixture_worker_start:fixture_worker_end]
    require(failures,
            "RTC_NOINIT_ATTR TargetsMergeFixtureRtcState" in entry and
            "targetsMergeFixtureContinuityValid()" in entry and
            "fixture_bypassed" in entry and
            load_product.index("targetsMergeFixtureRtcState.magic") <
                load_product.index("loadProductFingerprint(") and
            "prepareTargetsMergeSyntheticSessions()" in entry and
            "authorizeExistingScratchWrite(media, request)" in
                fixture_worker and
            "mountExistingWritable()" in fixture_worker and
            "openExistingWritable(permit)" in fixture_worker and
            "fixture_merge_split_only" in entry and
            "targets.merge-split-fixture prepare disposable-ota1" in entry and
            "targets.merge-split-fixture clear disposable-ota1" in entry,
            "the deterministic merge/split fixture must survive cold resets "
            "through authenticated RTC continuity, bypass product SD before "
            "identity access, admit only merge/split and reopen only its "
            "pre-created inactive-OTA1 scratch namespace")
    require(failures,
            "media.kind != MediaKind::LittleFs" in storage_guard and
            "authorizeExistingScratchWrite(" in storage_guard and
            "request.scratchExists" in storage_guard and
            "request.requiredBytes == 0" in storage_guard and
            "safeInactiveTarget()" in disposable_ota and
            "mountExistingWritable()" in disposable_ota and
            "openExistingPath(permit.scratchPath, permit.byteLimit, true)" in
                littlefs_io and
            "++writeCalls_" in littlefs_io,
            "fixture writes must be exact-media, LittleFS-only, bounded, "
            "pre-existing-scratch operations on the inactive OTA slot with "
            "observable physical write calls")
    require(failures,
            "using ProgressCallback = bool (*)();" in littlefs_io_header and
            "using ProgressCallback = bool (*)();" in fs_io_header and
            "progressCallback_()" in littlefs_io and
            "progressCallback_()" in fs_io and
            "ECANCELED" in littlefs_io and
            "FR_TIMEOUT" in fs_io and
            littlefs_io.count("progress(\"") >= 12 and
            fs_io.count("progress(\"") >= 12 and
            "supervisedCheckpoint = targetsStoreSupervisedCheckpoint" in
                fixture_worker and
            "filesystem, supervisedCheckpoint" in fixture_worker and
            "supervisedCheckpoint = targetsStoreSupervisedCheckpoint" in
                mutation_worker and
            "sdSessionStoreIoWorkspace,\n            supervisedCheckpoint" in
                mutation_worker and
            "bool targetsStoreSupervisedCheckpoint()" in entry and
            "if (accepted) vTaskDelay(pdMS_TO_TICKS(1));" in entry,
            "Targets atomic stores must heartbeat the bounded worker and yield "
            "the scheduler at every LittleFS/FatFs file boundary; callback "
            "cancellation remains a fail-closed storage error")
    require(failures,
            "ota1-private-backup.bin" in merge_split_runner and
            "ota1-private-backup-second.bin" in merge_split_runner and
            "ota1_before_sha == ota1_second_sha" in merge_split_runner and
            "partition-table-before-second.bin" in merge_split_runner and
            "partition_before_sha == partition_second_sha" in
                merge_split_runner and
            "validated_partition_layout(" in merge_split_runner and
            "candidate-partitions.bin" in merge_split_runner and
            "partition_table_candidate_installed" in merge_split_runner and
            "partition_table_original_restored" in merge_split_runner and
            "restore_flash(" in merge_split_runner and
            "partition_before_sha == partition_after_sha" in
                merge_split_runner and
            "targetsMergeFixture" not in merge_split_runner and
            '"opened_ports": [args.port]' in merge_split_runner and
            '"cardputer_ports_opened": 0' in merge_split_runner and
            '"port_discovery_calls": 0' in merge_split_runner and
            "list_ports" not in merge_split_runner and
            'for key in ("generation", "observations")' in
                merge_split_runner and
            "private_backup_deleted_after_verified_restore" in
                merge_split_runner,
            "fixture HIL must use one explicit DUT port, prove two identical "
            "inactive-OTA and original-table backups, install only the exact "
            "reviewed temporary app0/app1 map, restore both mutable regions "
            "byte-for-byte in cleanup, prove product generations unchanged, "
            "and leave a parallel Cardputer untouched")
    require(failures,
            'constexpr int kBleTxDbm = -12' in correlation_fixture and
            'ESP_PWR_LVL_N12' in correlation_fixture and
            'bool setLabel(const char* hex)' in correlation_fixture and
            'std::strncmp(line, "label ", 6)' in correlation_fixture and
            'advertising->setScanResponse(false)' in correlation_fixture,
            "the second-DIV fixture must use a bounded dynamic primary-PDU "
            "name at minimum BLE power without requiring an active scan")
    require(failures,
            "def wait_fixture_ready" in correlation_fixture_runner and
            "fixture_ready_attempts" in correlation_fixture_runner and
            "fixture_ready_elapsed_ms" in correlation_fixture_runner and
            "fixture_ready_stable_replies" in correlation_fixture_runner and
            "range(2)" in correlation_fixture_runner and
            "record.update(wait_fixture_ready" in correlation_fixture_runner,
            "correlation fixture orchestration must prove two stable native-USB "
            "replies after JTAG reset before the product delta starts")
    require(failures,
            "renderTargetsPage" in entry and
            "renderTargetListRow" in entry and
            "renderTargetComparisonRow" in entry and
            "renderTargetComparisonDetail" in entry and
            "fitTargetRowText" in entry and
            "Layout::FooterDividerY - Layout::ContentTop" in entry and
            "targetsFirstVisible" in entry and
            "TouchTargetLayout::HomeRows" in entry and
            "controller.openSelected()" in entry and
            "controller.openNameEditor()" in entry and
            "controller.appendNameEditorGlyph()" in entry and
            "requestTargetsNameMutation()" in entry and
            "controller.openTagList()" in entry and
            "controller.openTagEditor()" in entry and
            "requestTargetsTagAddMutation()" in entry and
            "requestTargetsTagRemoveMutation()" in entry and
            "controller.openNotesEditor()" in entry and
            "controller.appendNotesEditorGlyph()" in entry and
            "requestTargetsNotesMutation()" in entry and
            "TargetsView::CompareDetail" in entry,
            "Targets list/detail/change/name/tag/notes rows must share keypad and touch "
            "navigation while row-window redraws clear stale pixels")
    require(failures,
            "selectedIsCompare() ? TargetsView::Compare" in controller and
            "entryCount()" in controller and
            "selectStrongestIdentities" in controller and
            "sourceIdentityCount_ > filter.size" in controller and
            "comparisonClassRank" in controller and
            "comparisonItemBefore" in controller and
            "observation.rssiDbm >" in controller and
            "TargetsView::CompareDetail" in controller,
            "Compare visits must open stable class/signal-sorted rows and an "
            "exact evidence detail without losing selection")
    require(failures,
            r'\"comparison_selection\":%u' in entry and
            r'\"selected_change_class\":\"%s\"' in entry and
            r'\"baseline_observation_sequence\":%llu' in entry and
            r'\"current_observation_sequence\":%llu' in entry,
            "Targets state must expose exact selected comparison evidence")
    for text_id in ("TargetsCompareVisits", "TargetsLimitedTitleFormat", "TargetsEmpty",
                    "TargetsLoadFailed", "TargetsDetail", "TargetsCompare",
                    "TargetsCompareEvidence", "TargetsClassAdded",
                    "TargetsBeforeWifiFormat", "TargetsNowWifiFormat",
                    "TargetsChangesFormat", "TargetsNameEdit",
                    "TargetsNameAppend", "TargetsNameSave", "TargetsTagsList",
                    "TargetsTagEdit", "TargetsTagAdd", "TargetsTagRemove",
                    "TargetsTagSave", "TargetsNotes", "TargetsNotesEdit",
                    "TargetsNotesSave", "TargetsValueSavedFormat",
                    "TargetsCorrelations", "TargetsCorrelationsCountFormat",
                    "TargetsCorrelationList", "TargetsCorrelationReview",
                    "TargetsCorrelationEvidence", "TargetsCorrelationExisting",
                    "TargetsCorrelationCandidate", "TargetsCorrelationAccept",
                    "TargetsCorrelationReject",
                    "TargetsMergeAction", "TargetsSplitAction",
                    "TargetsSplitAvailable", "TargetsMergeList",
                    "TargetsMergeConfirm", "TargetsSplitConfirm",
                    "TargetsMergeConfirmAction", "TargetsSplitConfirmAction",
                    "NavDelete", "NavChanges"):
        require(failures, f"LESHY_UI_TEXT({text_id}," in strings,
                f"bilingual UI string missing: {text_id}")
    for forbidden in ("esp_wifi_80211_tx", "STX", "SFTX", "tone("):
        require(failures, forbidden not in controller,
                f"Targets controller contains forbidden active path: {forbidden}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets product contract passed: exact-CID sessions, bounded "
          "lifecycle, list/detail/compare/actions/correlation review, "
          "reversible merge/split, mount-aware codec workspace, keypad/touch "
          "and mutation state probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
