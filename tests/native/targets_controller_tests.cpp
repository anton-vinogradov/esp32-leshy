#include <cstring>
#include <iostream>

#include "apps/targets/TargetsController.h"

using namespace leshy1::apps::targets;
using namespace leshy1::domain::observations;
using namespace leshy1::domain::targets;
using namespace leshy1::services::survey;

namespace {

struct OwnedTargetsWorkspace final {
    TargetCatalog catalog{};
    CorrelationDecisionLog decisions{};
    leshy1::services::targets::SessionCorrelationProposalSet correlations{};
    TargetComparisonResult comparison{};
    TargetsWorkspace refs{catalog, decisions, correlations, comparison};

    operator TargetsWorkspace&() { return refs; }
};

int failures = 0;
#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            std::cerr << __FILE__ << ':' << __LINE__ << ": CHECK("          \
                      << #condition << ") failed\n";                         \
            ++failures;                                                      \
        }                                                                    \
    } while (false)

Observation wifi(std::uint64_t sequence, std::uint64_t us,
                 std::uint8_t suffix, std::int16_t rssi) {
    Observation value{};
    value.sequence = sequence;
    value.monotonicUs = us;
    value.radio = RadioKind::Wifi;
    value.frequencyKhz = 2412000;
    value.channel = 1;
    value.rssiDbm = rssi;
    value.identity = {2, 0, 0, 0, 0, suffix};
    value.identityLength = 6;
    value.wifiNetwork.present = true;
    return value;
}

Observation labeled(RadioKind radio, std::uint64_t sequence, std::uint64_t us,
                    std::uint8_t suffix, std::int16_t rssi,
                    const char* label) {
    Observation value = wifi(sequence, us, suffix, rssi);
    value.radio = radio;
    value.labelLength = static_cast<std::uint8_t>(std::strlen(label));
    std::memcpy(value.label.data(), label, value.labelLength);
    if (radio == RadioKind::Ble) {
        value.wifiNetwork.present = false;
        value.bleAdvertisement.present = true;
        value.bleAdvertisement.addressType = 1;
        value.frequencyKhz = 0;
        value.channel = 0;
    }
    return value;
}

SurveySession session(const char* id, std::uint64_t base,
                      std::initializer_list<Observation> observations) {
    SurveySession result;
    CHECK(result.start(id, base) == SessionStatus::Started);
    for (const Observation& observation : observations) {
        CHECK(result.append(observation) == SessionStatus::Appended);
    }
    CHECK(result.stop(base + 100) == SessionStatus::Stopped);
    return result;
}

SurveySession rangeSession(const char* id, std::uint64_t base,
                           std::uint8_t firstSuffix, std::size_t count,
                           std::int16_t firstRssi) {
    SurveySession result;
    CHECK(result.start(id, base) == SessionStatus::Started);
    for (std::size_t index = 0; index < count; ++index) {
        CHECK(result.append(wifi(
                  index + 1, base + index + 1,
                  static_cast<std::uint8_t>(firstSuffix + index),
                  static_cast<std::int16_t>(firstRssi -
                                            static_cast<std::int16_t>(index)))) ==
              SessionStatus::Appended);
    }
    CHECK(result.stop(base + count + 1) == SessionStatus::Stopped);
    return result;
}

void pairIsUsefulFirstAndStable() {
    SurveySession baseline = session(
        "baseline", 100, {wifi(1, 110, 1, -70), wifi(2, 120, 2, -45)});
    SurveySession current = session(
        "current", 300, {wifi(1, 310, 1, -30), wifi(2, 320, 3, -55)});
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&baseline, 1}, {&current, 2}) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.size() == 3);
    CHECK(controller.entryCount() == 4);
    CHECK(controller.compareAvailable());
    CHECK(controller.row(0)->latest.rssiDbm == -30);
    CHECK(controller.row(1)->latest.rssiDbm == -45);
    CHECK(controller.row(2)->latest.rssiDbm == -55);
    CHECK(controller.comparison().added == 1);
    CHECK(controller.comparison().removed == 1);
    CHECK(controller.comparison().changed == 1);
    CHECK(controller.comparison().unchanged == 0);

    CHECK(controller.selectedIsCompare());
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::Compare);
    CHECK(controller.comparisonSize() == 3);
    CHECK(controller.comparisonSelection() == 0);
    CHECK(controller.comparisonItem(0)->classification ==
          TargetComparisonClass::Added);
    CHECK(controller.comparisonTargetRow(0)->identity.value[5] == 3);
    TargetComparisonSide side{};
    CHECK(controller.comparisonSide(0, true, &side));
    CHECK(side.present);
    CHECK(side.observation.rssiDbm == -55);
    CHECK(side.evidence.sourceGeneration == 2);
    CHECK(controller.comparisonSide(0, false, &side));
    CHECK(!side.present);
    CHECK(controller.next());
    CHECK(controller.comparisonItem(1)->classification ==
          TargetComparisonClass::Removed);
    CHECK(controller.comparisonTargetRow(1)->identity.value[5] == 2);
    CHECK(controller.comparisonSide(1, false, &side));
    CHECK(side.present);
    CHECK(side.observation.rssiDbm == -45);
    CHECK(side.evidence.sourceGeneration == 1);
    CHECK(controller.next());
    CHECK(controller.comparisonItem(2)->classification ==
          TargetComparisonClass::Changed);
    CHECK(controller.comparisonTargetRow(2)->identity.value[5] == 1);
    CHECK(controller.comparisonSide(2, true, &side));
    CHECK(side.present);
    CHECK(side.observation.rssiDbm == -30);
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::CompareDetail);
    CHECK(controller.selectedComparisonItem()->classification ==
          TargetComparisonClass::Changed);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::Compare);
    CHECK(controller.comparisonSelection() == 2);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::List);
    CHECK(controller.next());
    const TargetId selected = controller.selectedRow()->targetId;
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::Detail);
    CHECK(targetIdEqual(controller.selectedTarget()->id, selected));
    CHECK(controller.back());
    CHECK(controller.selection() == 1);
    CHECK(controller.openCompare());
    CHECK(controller.view() == TargetsView::Compare);
    CHECK(controller.comparisonSelection() == 0);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::List);

    CHECK(controller.selectTarget(selected));
    CHECK(targetIdEqual(controller.selectedRow()->targetId, selected));
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::Detail);
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::Actions);
    CHECK(controller.actionSelection() == 0);
    CHECK(controller.selectedAction() == TargetActionItem::Favorite);
    CHECK(controller.next());
    CHECK(controller.selectedAction() == TargetActionItem::Name);
    CHECK(controller.openNameEditor());
    CHECK(controller.view() == TargetsView::NameEdit);
    CHECK(controller.nameEditorLength() == 0);
    CHECK(controller.nameEditorGlyph() == 'A');
    CHECK(controller.next());
    CHECK(controller.nameEditorSelection() == 1);
    CHECK(controller.appendNameEditorGlyph());
    CHECK(std::strcmp(controller.nameEditorText(), "A") == 0);
    CHECK(controller.nameEditorDirty());
    CHECK(controller.previous());
    CHECK(controller.cycleNameEditorGlyph());
    CHECK(controller.nameEditorGlyph() == 'B');
    CHECK(controller.next());
    CHECK(controller.appendNameEditorGlyph());
    CHECK(std::strcmp(controller.nameEditorText(), "AB") == 0);
    CHECK(controller.next());
    CHECK(controller.eraseNameEditorGlyph());
    CHECK(std::strcmp(controller.nameEditorText(), "A") == 0);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::Actions);
    CHECK(controller.next());
    CHECK(controller.selectedAction() == TargetActionItem::Tags);
    CHECK(controller.openTagList());
    CHECK(controller.view() == TargetsView::TagList);
    CHECK(controller.tagEntryCount() == 1);
    CHECK(controller.selectedTagIsAdd());
    CHECK(controller.openTagEditor());
    CHECK(controller.view() == TargetsView::TagEdit);
    CHECK(controller.tagEditorGlyph() == 'A');
    CHECK(!controller.tagEditorCanSave());
    CHECK(controller.next());
    CHECK(controller.appendTagEditorGlyph());
    CHECK(std::strcmp(controller.tagEditorText(), "A") == 0);
    CHECK(controller.tagEditorCanSave());
    CHECK(controller.previous());
    CHECK(controller.cycleTagEditorGlyph());
    CHECK(controller.tagEditorGlyph() == 'B');
    CHECK(controller.next());
    CHECK(controller.appendTagEditorGlyph());
    CHECK(std::strcmp(controller.tagEditorText(), "AB") == 0);
    CHECK(controller.next());
    CHECK(controller.eraseTagEditorGlyph());
    CHECK(std::strcmp(controller.tagEditorText(), "A") == 0);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::TagList);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::Actions);
    CHECK(controller.next());
    CHECK(controller.selectedAction() == TargetActionItem::Notes);
    CHECK(controller.openNotesEditor());
    CHECK(controller.view() == TargetsView::NotesEdit);
    CHECK(controller.notesEditorLength() == 0);
    CHECK(controller.notesEditorGlyph() == 'A');
    CHECK(!controller.notesEditorDirty());
    CHECK(controller.next());
    CHECK(controller.appendNotesEditorGlyph());
    CHECK(std::strcmp(controller.notesEditorText(), "A") == 0);
    CHECK(controller.notesEditorDirty());
    CHECK(controller.previous());
    CHECK(controller.cycleNotesEditorGlyph());
    CHECK(controller.notesEditorGlyph() == 'B');
    CHECK(controller.next());
    CHECK(controller.appendNotesEditorGlyph());
    CHECK(std::strcmp(controller.notesEditorText(), "AB") == 0);
    CHECK(controller.next());
    CHECK(controller.eraseNotesEditorGlyph());
    CHECK(std::strcmp(controller.notesEditorText(), "A") == 0);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::Actions);
    CHECK(controller.next());
    CHECK(controller.selectedAction() == TargetActionItem::Correlations);
    CHECK(controller.next());
    CHECK(controller.selectedAction() == TargetActionItem::CompanionWeb);
    CHECK(controller.next());
    CHECK(controller.selectedAction() == TargetActionItem::MergeSplit);
    CHECK(controller.mergeCandidateCount() + 1U == controller.size());
    CHECK(controller.openMerge(false));
    CHECK(controller.view() == TargetsView::MergeList);
    CHECK(controller.selectedMergeCandidate() != nullptr);
    if (controller.mergeCandidateCount() > 1U) {
        CHECK(controller.next());
        CHECK(controller.mergeSelection() == 1U);
        CHECK(controller.previous());
    }
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::MergeConfirm);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::MergeList);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::Actions);
    CHECK(controller.openMerge(true));
    CHECK(controller.view() == TargetsView::SplitConfirm);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::Actions);
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::Detail);
}

void callerProvidedAdmissionScratchWorks() {
    SurveySession current = session(
        "shared-scratch", 500, {wifi(1, 510, 7, -42)});
    OwnedTargetsWorkspace workspace;
    TargetCatalog scratch;
    TargetsController controller(workspace);
    CHECK(controller.loadWithAdmissionScratch(
              {}, {&current, 7}, false, scratch) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.size() == 1);
    CHECK(controller.row(0)->latest.rssiDbm == -42);
}

void singleSessionStillListsTargets() {
    SurveySession current =
        session("only", 500, {wifi(1, 510, 4, -40)});
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&current, 7}) == TargetsLoadStatus::Ready);
    CHECK(controller.size() == 1);
    CHECK(controller.entryCount() == 1);
    CHECK(!controller.compareAvailable());
    CHECK(!controller.openCompare());
    CHECK(controller.openSelected());
}

void rejectedLoadClearsPriorRows() {
    SurveySession current =
        session("good", 700, {wifi(1, 710, 5, -40)});
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&current, 1}) == TargetsLoadStatus::Ready);
    CHECK(controller.size() == 1);
    SurveySession running;
    CHECK(running.start("running", 900) == SessionStatus::Started);
    CHECK(controller.load({&running, 2}) ==
          TargetsLoadStatus::InvalidArgument);
    CHECK(controller.size() == 0);
    CHECK(controller.catalog().size() == 0);
}

void denseAirKeepsStrongestAcrossBothVisits() {
    SurveySession baseline = rangeSession("dense-old", 10000, 1, 8, -20);
    SurveySession current = rangeSession("dense-new", 100, 20, 20, -30);
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&baseline, 10}, {&current, 11}) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.size() == TargetCatalog::kCapacity);
    CHECK(controller.entryCount() == TargetCatalog::kCapacity + 1);
    CHECK(controller.sourceIdentityCount() == 28);
    CHECK(controller.truncated());
    CHECK(controller.row(0)->identity.value[5] == 1);
    CHECK(controller.row(0)->latest.rssiDbm == -20);
    CHECK(controller.row(7)->identity.value[5] == 8);
    CHECK(controller.row(8)->identity.value[5] == 20);
    CHECK(controller.row(15)->identity.value[5] == 27);
    CHECK(controller.comparison().added == 8);
    CHECK(controller.comparison().removed == 8);
}

void denseAirRetainsCrossRadioCorrelationPair() {
    SurveySession baseline;
    CHECK(baseline.start("dense-corr-old", 20000) == SessionStatus::Started);
    CHECK(baseline.append(labeled(
              RadioKind::Wifi, 1, 20001, 80, -26,
              "LESHY-HIL-CORR")) == SessionStatus::Appended);
    for (std::size_t index = 0; index < 20; ++index) {
        CHECK(baseline.append(wifi(
                  index + 2, 20002 + index,
                  static_cast<std::uint8_t>(100 + index),
                  static_cast<std::int16_t>(-50 - index))) ==
              SessionStatus::Appended);
    }
    CHECK(baseline.stop(20100) == SessionStatus::Stopped);

    SurveySession current;
    CHECK(current.start("dense-corr-new", 30000) == SessionStatus::Started);
    CHECK(current.append(labeled(
              RadioKind::Ble, 1, 30001, 81, -40,
              "LESHY-HIL-CORR")) == SessionStatus::Appended);
    for (std::size_t index = 0; index < 20; ++index) {
        CHECK(current.append(wifi(
                  index + 2, 30002 + index,
                  static_cast<std::uint8_t>(140 + index),
                  static_cast<std::int16_t>(-5 - index))) ==
              SessionStatus::Appended);
    }
    CHECK(current.stop(30100) == SessionStatus::Stopped);

    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&baseline, 50}, {&current, 51}) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.sourceIdentityCount() == 42);
    CHECK(controller.truncated());
    CHECK(workspace.correlations.size == 1);
    CHECK(workspace.correlations.values[0].confidence ==
          CorrelationConfidence::Medium);
    CHECK(workspace.correlations.values[0].candidateIdentity.kind ==
          TargetIdentityKind::BleAddress);
}

void currentEvidenceWinsAcrossMonotonicReset() {
    SurveySession baseline = session(
        "old-boot", 10000, {wifi(1, 10010, 42, -25)});
    SurveySession current = session(
        "new-boot", 100, {wifi(1, 110, 42, -70)});
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&baseline, 20}, {&current, 21}) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.size() == 1);
    CHECK(controller.row(0)->latest.rssiDbm == -70);
    CHECK(controller.row(0)->evidence.sourceGeneration == 21);
}

void comparisonClassesThenSignalAreStable() {
    SurveySession baseline = session(
        "sort-old", 2000, {wifi(1, 2010, 1, -80)});
    SurveySession current = session(
        "sort-new", 3000,
        {wifi(1, 3010, 1, -80), wifi(2, 3020, 2, -60),
         wifi(3, 3030, 3, -20), wifi(4, 3040, 4, -40)});
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&baseline, 30}, {&current, 31}) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.comparisonSize() == 4);
    CHECK(controller.comparisonItem(0)->classification ==
          TargetComparisonClass::Added);
    CHECK(controller.comparisonTargetRow(0)->identity.value[5] == 3);
    CHECK(controller.comparisonTargetRow(1)->identity.value[5] == 4);
    CHECK(controller.comparisonTargetRow(2)->identity.value[5] == 2);
    CHECK(controller.comparisonItem(3)->classification ==
          TargetComparisonClass::Unchanged);
    CHECK(controller.comparisonTargetRow(3)->identity.value[5] == 1);
}

void persistedMetadataFollowsIdentityAcrossVisits() {
    SurveySession prior = session(
        "prior", 100, {wifi(1, 110, 9, -55), wifi(2, 120, 7, -80)});
    OwnedTargetsWorkspace priorWorkspace;
    TargetsController priorController(priorWorkspace);
    CHECK(priorController.load({&prior, 1}) == TargetsLoadStatus::Ready);
    const TargetRecord* remembered =
        priorController.catalog().findByIdentity(
            priorController.row(0)->identity);
    CHECK(remembered != nullptr);
    TargetCatalog persisted = priorController.catalog();
    CHECK(persisted.setFavorite(remembered->id, true) ==
          TargetMutationStatus::Applied);
    constexpr const char kCyrillicName[] = u8"ЦЕЛЬ";
    CHECK(persisted.setName(remembered->id, kCyrillicName,
                            std::strlen(kCyrillicName)) ==
          TargetMutationStatus::Applied);
    CHECK(persisted.addTag(remembered->id, "LAB", 3) ==
          TargetMutationStatus::Applied);
    constexpr const char kCyrillicNotes[] = u8"РЯДОМ";
    CHECK(persisted.setNotes(remembered->id, kCyrillicNotes,
                             std::strlen(kCyrillicNotes)) ==
          TargetMutationStatus::Applied);

    SurveySession current = session(
        "current-visit", 300, {wifi(1, 310, 9, -30)});
    OwnedTargetsWorkspace currentWorkspace;
    TargetsController currentController(currentWorkspace);
    CHECK(currentController.load({&current, 2}, persisted) ==
          TargetsLoadStatus::Ready);
    CHECK(currentController.size() == 1);
    CHECK(currentController.catalog().size() == 2);
    const TargetRecord* selected = currentController.selectedTarget();
    CHECK(selected != nullptr);
    CHECK(targetIdEqual(selected->id, remembered->id));
    CHECK(selected->favorite);
    CHECK(selected->nameLength == std::strlen(kCyrillicName));
    CHECK(std::memcmp(selected->name.data(), kCyrillicName,
                      selected->nameLength) == 0);
    CHECK(selected->tagCount == 1);
    CHECK(selected->tagLengths[0] == 3);
    CHECK(std::memcmp(selected->tags[0].data(), "LAB", 3) == 0);
    CHECK(selected->notesLength == std::strlen(kCyrillicNotes));
    CHECK(std::memcmp(selected->notes.data(), kCyrillicNotes,
                      selected->notesLength) == 0);
    CHECK(selected->evidenceCount == 2);
    CHECK(currentController.row(0)->latest.rssiDbm == -30);
    CHECK(currentController.row(0)->evidence.sourceGeneration == 2);
    CHECK(currentController.openSelected());
    CHECK(currentController.openSelected());
    CHECK(currentController.next());
    CHECK(currentController.openNameEditor());
    CHECK(!currentController.nameEditorDirty());
    CHECK(currentController.eraseNameEditorGlyph());
    CHECK(std::strcmp(currentController.nameEditorText(), u8"ЦЕЛ") == 0);
    CHECK(currentController.nameEditorDirty());
    CHECK(currentController.back());
    CHECK(!currentController.nameEditorDirty());
    CHECK(currentController.next());
    CHECK(currentController.selectedAction() == TargetActionItem::Tags);
    CHECK(currentController.openTagList());
    CHECK(currentController.tagEntryCount() == 2);
    CHECK(!currentController.selectedTagIsAdd());
    CHECK(currentController.selectedTagLength() == 3);
    CHECK(std::strcmp(currentController.selectedTagText(), "LAB") == 0);
    CHECK(currentController.next());
    CHECK(currentController.selectedTagIsAdd());
    CHECK(currentController.back());
    CHECK(currentController.view() == TargetsView::Actions);
    CHECK(currentController.next());
    CHECK(currentController.selectedAction() == TargetActionItem::Notes);
    CHECK(currentController.openNotesEditor());
    CHECK(!currentController.notesEditorDirty());
    CHECK(currentController.eraseNotesEditorGlyph());
    CHECK(std::strcmp(currentController.notesEditorText(), u8"РЯДО") == 0);
    CHECK(currentController.notesEditorDirty());
}

void correlationReviewKeepsCandidateUnownedUntilDecision() {
    SurveySession baseline = session(
        "corr-old", 100,
        {labeled(RadioKind::Wifi, 1, 110, 40, -50, "Beacon")});
    SurveySession current = session(
        "corr-new", 300,
        {labeled(RadioKind::Ble, 1, 310, 41, -55, "Beacon")});
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&baseline, 40}, {&current, 41}) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.catalog().size() == 1);
    CHECK(controller.size() == 1);
    CHECK(controller.next());
    CHECK(controller.openSelected());
    CHECK(controller.openSelected());
    for (std::size_t index = 0; index < 4; ++index) CHECK(controller.next());
    CHECK(controller.selectedAction() == TargetActionItem::Correlations);
    CHECK(controller.selectedCorrelationCount() == 1);
    CHECK(controller.openCorrelationList());
    CHECK(controller.view() == TargetsView::CorrelationList);
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::CorrelationReview);
    Observation proof{};
    CHECK(controller.correlationEvidence(false, &proof));
    CHECK(proof.radio == RadioKind::Wifi);
    CHECK(controller.next());
    CHECK(controller.correlationEvidence(true, &proof));
    CHECK(proof.radio == RadioKind::Ble);
    CHECK(controller.openSelected());
    CHECK(controller.view() == TargetsView::CorrelationEvidence);
    CHECK(controller.correlationEvidenceIsCandidate());
    CHECK(controller.back());
    CHECK(controller.view() == TargetsView::CorrelationReview);

    const auto* rejected = controller.reviewedCorrelationProposal();
    CHECK(rejected != nullptr);
    const auto persisted = controller.catalog();
    CorrelationDecisionLog decisions;
    CHECK(decisions.record(*rejected, CorrelationDecision::Reject,
                           persisted.find(rejected->targetId)->revision,
                           persisted.find(rejected->targetId)->revision) ==
          CorrelationDecisionStatus::Rejected);
    OwnedTargetsWorkspace reopenedWorkspace;
    TargetsController reopened(reopenedWorkspace);
    const TargetsLoadStatus reopenedStatus = reopened.load(
        {&baseline, 40}, {&current, 41}, persisted, decisions);
    if (reopenedStatus != TargetsLoadStatus::Ready) {
        std::cerr << "correlation reopen status: "
                  << targetsLoadStatusName(reopenedStatus) << '\n';
    }
    CHECK(reopenedStatus == TargetsLoadStatus::Ready);
    CHECK(reopened.catalog().size() == 2);
    CHECK(reopened.size() == 2);

    OwnedTargetsWorkspace inPlaceWorkspace;
    inPlaceWorkspace.catalog = persisted;
    inPlaceWorkspace.decisions = decisions;
    TargetsController inPlace(inPlaceWorkspace);
    CHECK(inPlace.load({&baseline, 40}, {&current, 41},
                       inPlaceWorkspace.catalog,
                       inPlaceWorkspace.decisions) ==
          TargetsLoadStatus::Ready);
    CHECK(inPlace.decisions().size() == 1);
    CHECK(inPlace.catalog().size() == 2);
    CHECK(inPlace.size() == 2);
}

void fullPersistedCatalogDoesNotBlockCurrentView() {
    SurveySession initial = rangeSession(
        "persisted-full", 1000, 1, TargetCatalog::kCapacity, -30);
    OwnedTargetsWorkspace initialWorkspace;
    TargetsController initialController(initialWorkspace);
    CHECK(initialController.load({&initial, 1}) == TargetsLoadStatus::Ready);
    const TargetCatalog persisted = initialController.catalog();
    CHECK(persisted.size() == TargetCatalog::kCapacity);

    SurveySession current = session(
        "current-overflow", 2000,
        {wifi(1, 2010, 1, -50), wifi(2, 2020, 99, -20)});
    OwnedTargetsWorkspace workspace;
    TargetsController controller(workspace);
    CHECK(controller.load({&current, 2}, persisted) ==
          TargetsLoadStatus::Ready);
    CHECK(controller.catalog().size() == TargetCatalog::kCapacity);
    CHECK(controller.size() == 1);
    CHECK(controller.sourceIdentityCount() == 2);
    CHECK(controller.truncated());
    CHECK(controller.lastAdmission().valid());
    CHECK(controller.lastAdmission().capacitySkipped == 1);
    CHECK(controller.lastAdmission().targetStatus ==
          TargetMutationStatus::CatalogFull);
    CHECK(controller.row(0)->identity.value[5] == 1);
}

void rejectedCorrelationAtCatalogBoundReopensTruncated() {
    SurveySession baseline = session(
        "full-corr-old", 3000,
        {labeled(RadioKind::Wifi, 1, 3010, 40, -50, "Beacon")});
    OwnedTargetsWorkspace baselineWorkspace;
    TargetsController baselineController(baselineWorkspace);
    CHECK(baselineController.load({&baseline, 40}) ==
          TargetsLoadStatus::Ready);

    SurveySession filler = rangeSession(
        "full-corr-filler", 4000, 1, TargetCatalog::kCapacity - 1, -60);
    OwnedTargetsWorkspace fillerWorkspace;
    TargetsController fillerController(fillerWorkspace);
    CHECK(fillerController.load({&filler, 39},
                                baselineController.catalog()) ==
          TargetsLoadStatus::Ready);
    const TargetCatalog persisted = fillerController.catalog();
    CHECK(persisted.size() == TargetCatalog::kCapacity);

    SurveySession current = session(
        "full-corr-new", 5000,
        {labeled(RadioKind::Ble, 1, 5010, 41, -55, "Beacon")});
    OwnedTargetsWorkspace reviewWorkspace;
    TargetsController review(reviewWorkspace);
    CHECK(review.load({&baseline, 40}, {&current, 41}, persisted) ==
          TargetsLoadStatus::Ready);
    CHECK(review.size() == 1);
    CHECK(review.next());
    CHECK(review.openSelected());
    CHECK(review.openSelected());
    for (std::size_t index = 0; index < 4; ++index) CHECK(review.next());
    CHECK(review.selectedCorrelationCount() == 1);
    CHECK(review.openCorrelationList());
    CHECK(review.openSelected());
    const auto* proposal = review.reviewedCorrelationProposal();
    CHECK(proposal != nullptr);

    CorrelationDecisionLog decisions;
    const auto* target = proposal == nullptr
        ? nullptr : persisted.find(proposal->targetId);
    CHECK(target != nullptr);
    if (proposal != nullptr && target != nullptr) {
        CHECK(decisions.record(*proposal, CorrelationDecision::Reject,
                               target->revision, target->revision) ==
              CorrelationDecisionStatus::Rejected);
    }

    OwnedTargetsWorkspace reopenedWorkspace;
    reopenedWorkspace.catalog = persisted;
    reopenedWorkspace.decisions = decisions;
    TargetsController reopened(reopenedWorkspace);
    CHECK(reopened.load({&baseline, 40}, {&current, 41},
                        reopenedWorkspace.catalog,
                        reopenedWorkspace.decisions) ==
          TargetsLoadStatus::Ready);
    CHECK(reopened.decisions().size() == 1);
    CHECK(reopened.catalog().size() == TargetCatalog::kCapacity);
    CHECK(reopened.catalog().findByIdentity(
              review.reviewedCorrelationProposal() == nullptr
                  ? TargetIdentity{}
                  : review.reviewedCorrelationProposal()->candidateIdentity) ==
          nullptr);
    CHECK(reopened.selectedCorrelationCount() == 0);
    CHECK(reopened.size() == 1);
    CHECK(reopened.truncated());
    CHECK(reopened.lastAdmission().valid());
    CHECK(reopened.lastAdmission().capacitySkipped == 1);
    CHECK(reopened.lastAdmission().targetStatus ==
          TargetMutationStatus::CatalogFull);
}

}  // namespace

int main() {
    pairIsUsefulFirstAndStable();
    callerProvidedAdmissionScratchWorks();
    singleSessionStillListsTargets();
    rejectedLoadClearsPriorRows();
    denseAirKeepsStrongestAcrossBothVisits();
    denseAirRetainsCrossRadioCorrelationPair();
    currentEvidenceWinsAcrossMonotonicReset();
    comparisonClassesThenSignalAreStable();
    persistedMetadataFollowsIdentityAcrossVisits();
    correlationReviewKeepsCandidateUnownedUntilDecision();
    fullPersistedCatalogDoesNotBlockCurrentView();
    rejectedCorrelationAtCatalogBoundReopensTruncated();
    if (failures != 0) {
        std::cerr << failures << " targets controller test(s) failed\n";
        return 1;
    }
    std::cout << "targets controller tests passed; workspace_refs_bytes="
              << sizeof(TargetsWorkspace) << "; runtime_component_bytes="
              << sizeof(TargetCatalog) + sizeof(CorrelationDecisionLog) +
                     sizeof(leshy1::services::targets::
                                SessionCorrelationProposalSet) +
                     sizeof(TargetComparisonResult)
              << "; controller_bytes="
              << sizeof(TargetsController) << "; catalog_bytes="
              << sizeof(leshy1::domain::targets::TargetCatalog)
              << "; decisions_bytes="
              << sizeof(leshy1::domain::targets::CorrelationDecisionLog)
              << "; correlations_bytes="
              << sizeof(leshy1::services::targets::SessionCorrelationProposalSet)
              << "; comparison_bytes="
              << sizeof(leshy1::domain::targets::TargetComparisonResult)
              << '\n';
    return 0;
}
