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
            "separate 11,272 B catalog, 11,272 B decision log, 7,736 B "
            "comparison" in load_product and
            "2,704 B proposals and 4,240 B controller blocks" in
                load_product and
            "overlapping transfer/runtime copies do not fit the board" in
                load_product and
            "recoverTargetDecisionStateWire(" in load_product and
            "persistedCatalog" not in load_product and
            "persistedDecisions" not in load_product and
            "reopenTargetDecisionState(" in load_product and
            "&targetsProductRuntime->workspace.catalog" in load_product and
            "&targetsProductRuntime->workspace.decisions" in load_product and
            "new (std::nothrow) TargetCatalog" in entry and
            "new (std::nothrow) CorrelationDecisionLog" in entry and
            "SessionCorrelationProposalSet();" in entry and
            "TargetComparisonResult();" in entry and
            "new (std::nothrow) TargetsWorkspace" in entry and
            "new (std::nothrow) TargetsController" in entry and
            "filesystem_mount_error" in entry,
            "Targets must checksum-select wire state without duplicate decoded "
            "copies, release FatFs before allocating split no-PSRAM runtime "
            "blocks, decode in place and expose the exact mount result")
    mutation_start = entry.index("void runTargetsMutationWorker")
    mutation_end = entry.index("bool requestTargetsFavoriteMutation")
    mutation_worker = entry[mutation_start:mutation_end]
    require(failures,
            load_product.index("TargetDecisionStateStoreWorkspace();") >
                load_product.index("filesystem.beginReadOnly()") and
            mutation_worker.index("TargetDecisionStateStoreWorkspace();") <
                mutation_worker.index("filesystem.begin()") and
            "workspace_unavailable_before_mount" in mutation_worker and
            r'\"mutation_heap_largest_before_mount\":%lu' in entry and
            "kTargetsMaximumMountAttempts = 3" in load_product and
            "filesystem.cleanupComplete()" in load_product and
            r'\"filesystem_mount_attempts\":%u' in entry and
            r'\"filesystem_mount_transient_retries\":%u' in entry,
            "Targets read recovery must mount before its optional codec "
            "allocation so a saturated visit cannot starve FatFs; the proven "
            "mutation path retains observable pre-mount contiguous-capacity "
            "admission and read recovery remains bounded/fail-closed")
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
            r'\"read_only\":false' in entry and
            r'\"write_enabled\":%s' in entry and
            r'\"mutation_state\":\"%s\"' in entry and
            "commitTargetDecisionState(" in entry and
            "recoverTargetDecisionState(" in entry and
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
            r'\"notes_editor_dirty\":%s' in entry,
            "Targets needs a machine-readable release-test state")
    require(failures,
            "buildSessionCorrelationReview(" in controller and
            "sessionCorrelationCandidatePending(" in controller and
            "CorrelationDecisionLog* targetsMutationDecisions" in entry and
            "CorrelationService service(*catalog, *decisions, lookup)" in entry and
            "requestTargetsCorrelationMutation(" in entry and
            r'\"correlation_count\":%u' in entry and
            r'\"correlation_decision_count\":%u' in entry and
            r'\"correlation_proposal_id\":\"%s\"' in entry and
            r'\"correlation_candidate_identity_hex\":\"%s\"' in entry and
            r'\"correlation_feature_kind\":\"%s\"' in entry and
            r'\"correlation_known_generation\":%lu' in entry and
            r'\"correlation_candidate_generation\":%lu' in entry and
            r'\"mutation_correlation_status\":\"%s\"' in entry,
            "Targets correlation review must keep candidates independent, "
            "show explainable proposals and atomically persist accept/reject")
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
            "checked_stack_frames = stack_frames(args.elf)" in runner and
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
            'mutation_correlation_status="accepted"' in correlation_runner and
            "correlation_decision_count=decisions_after" in
                correlation_runner and
            "targets-correlation-cold-reopen" in correlation_runner and
            "mutation_directory_syncs" in correlation_runner,
            "correlation HIL must find one bounded natural proposal, review "
            "both exact observations, atomically accept and cold-reopen the "
            "same decision log")
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
          "mount-aware codec workspace, keypad/touch and mutation state probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
