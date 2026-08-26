#include "TargetsController.h"

#include <cstring>
#include <new>
#include <utility>

#include "services/targets/SessionTargetAdmission.h"
#include "services/targets/SessionCorrelationReview.h"
#include "services/targets/SurveySessionTargetEvidenceLookup.h"
#include "services/targets/TargetComparisonService.h"

namespace leshy1::apps::targets {
namespace {

constexpr char kTargetNameGlyphs[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_";
constexpr char kTargetTagGlyphs[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_";
constexpr char kTargetNotesGlyphs[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-_/";

bool bindingValid(const TargetProductBinding& binding) {
    return binding.session != nullptr && binding.generation != 0 &&
        binding.session->state() == services::survey::SessionState::Stopped;
}

domain::targets::TargetComparisonSource comparisonSource(
    const TargetProductBinding& binding) {
    domain::targets::TargetComparisonSource source{};
    if (binding.session != nullptr) {
        services::targets::sourceIdForSession(*binding.session, &source.id);
    }
    source.generation = binding.generation;
    return source;
}

bool rowBefore(const TargetListRow& left, const TargetListRow& right) {
    if (left.latest.rssiDbm != right.latest.rssiDbm) {
        return left.latest.rssiDbm > right.latest.rssiDbm;
    }
    if (left.latest.monotonicUs != right.latest.monotonicUs) {
        return left.latest.monotonicUs > right.latest.monotonicUs;
    }
    return left.targetId.bytes < right.targetId.bytes;
}

std::uint8_t comparisonClassRank(
    domain::targets::TargetComparisonClass classification) {
    using domain::targets::TargetComparisonClass;
    switch (classification) {
        case TargetComparisonClass::Added: return 0;
        case TargetComparisonClass::Removed: return 1;
        case TargetComparisonClass::Changed: return 2;
        case TargetComparisonClass::Unchanged: return 3;
    }
    return 4;
}

struct RankedIdentity final {
    domain::targets::TargetIdentity identity{};
    std::int16_t rssiDbm = -128;
    std::uint64_t monotonicUs = 0;
};

bool rankedBefore(const RankedIdentity& left, const RankedIdentity& right) {
    if (left.rssiDbm != right.rssiDbm) return left.rssiDbm > right.rssiDbm;
    return left.monotonicUs > right.monotonicUs;
}

bool sessionContainsIdentity(
    const services::survey::SurveySession& session,
    const domain::targets::TargetIdentity& identity) {
    domain::targets::SourceId sourceId{};
    if (!services::targets::sourceIdForSession(session, &sourceId)) return false;
    for (std::size_t index = 0; index < session.size(); ++index) {
        const auto* observation = session.get(index);
        if (observation == nullptr) return false;
        const auto admitted = services::targets::admitObservationToTarget(
            sourceId, 1, *observation);
        if (admitted.valid() && domain::targets::targetIdentityEqual(
                                    admitted.identity, identity)) {
            return true;
        }
    }
    return false;
}

bool laterIdentityExists(const services::survey::SurveySession& session,
                         std::size_t after,
                         const domain::targets::SourceId& sourceId,
                         const domain::targets::TargetIdentity& identity) {
    for (std::size_t index = after + 1; index < session.size(); ++index) {
        const auto* observation = session.get(index);
        if (observation == nullptr) return false;
        const auto admitted = services::targets::admitObservationToTarget(
            sourceId, 1, *observation);
        if (admitted.valid() && domain::targets::targetIdentityEqual(
                                    admitted.identity, identity)) {
            return true;
        }
    }
    return false;
}

bool appendStrongest(
    const services::survey::SurveySession& session,
    const services::survey::SurveySession* exclude,
    std::array<RankedIdentity,
               domain::targets::TargetCatalog::kCapacity>* ranked,
    std::size_t* rankedSize,
    std::size_t* uniqueCount) {
    if (ranked == nullptr || rankedSize == nullptr || uniqueCount == nullptr) {
        return false;
    }
    domain::targets::SourceId sourceId{};
    if (!services::targets::sourceIdForSession(session, &sourceId)) return false;
    for (std::size_t index = 0; index < session.size(); ++index) {
        const auto* observation = session.get(index);
        if (observation == nullptr) return false;
        const auto admitted = services::targets::admitObservationToTarget(
            sourceId, 1, *observation);
        if (!admitted.valid()) return false;
        if (laterIdentityExists(session, index, sourceId, admitted.identity) ||
            (exclude != nullptr &&
             sessionContainsIdentity(*exclude, admitted.identity))) {
            continue;
        }
        ++*uniqueCount;
        RankedIdentity candidate{admitted.identity, observation->rssiDbm,
                                 observation->monotonicUs};
        std::size_t insert = *rankedSize;
        while (insert > 0 &&
               rankedBefore(candidate, (*ranked)[insert - 1])) {
            --insert;
        }
        if (insert >= ranked->size()) continue;
        const std::size_t last = *rankedSize < ranked->size()
            ? *rankedSize : ranked->size() - 1;
        for (std::size_t move = last; move > insert; --move) {
            (*ranked)[move] = (*ranked)[move - 1];
        }
        (*ranked)[insert] = candidate;
        if (*rankedSize < ranked->size()) ++*rankedSize;
    }
    return true;
}

bool selectStrongestIdentities(
    const TargetProductBinding& baseline,
    const TargetProductBinding& current, bool compare,
    services::targets::SessionTargetIdentityFilter* filter,
    std::size_t* sourceIdentityCount) {
    if (filter == nullptr || sourceIdentityCount == nullptr ||
        current.session == nullptr) {
        return false;
    }
    *filter = {};
    *sourceIdentityCount = 0;
    std::array<RankedIdentity,
               domain::targets::TargetCatalog::kCapacity> ranked{};
    std::size_t rankedSize = 0;
    if (!appendStrongest(*current.session, nullptr, &ranked, &rankedSize,
                         sourceIdentityCount)) {
        return false;
    }
    if (compare && (baseline.session == nullptr ||
        !appendStrongest(*baseline.session, current.session, &ranked,
                         &rankedSize, sourceIdentityCount))) {
        return false;
    }
    for (std::size_t index = 0; index < rankedSize; ++index) {
        filter->identities[filter->size++] = ranked[index].identity;
    }
    return true;
}

void removePendingCorrelations(
    const services::targets::SessionCorrelationProposalSet& proposals,
    services::targets::SessionTargetIdentityFilter* filter) {
    if (filter == nullptr) return;
    const std::size_t originalSize = filter->size;
    std::size_t output = 0;
    for (std::size_t index = 0; index < originalSize; ++index) {
        if (services::targets::sessionCorrelationCandidatePending(
                proposals, filter->identities[index])) {
            continue;
        }
        filter->identities[output++] = filter->identities[index];
    }
    filter->size = output;
    while (output < originalSize) filter->identities[output++] = {};
}

}  // namespace

const char* targetsLoadStatusName(TargetsLoadStatus status) {
    switch (status) {
        case TargetsLoadStatus::Ready: return "ready";
        case TargetsLoadStatus::InvalidArgument: return "invalid_argument";
        case TargetsLoadStatus::SessionUnavailable:
            return "session_unavailable";
        case TargetsLoadStatus::AdmissionRejected:
            return "admission_rejected";
        case TargetsLoadStatus::EvidenceUnavailable:
            return "evidence_unavailable";
        case TargetsLoadStatus::CompareRejected: return "compare_rejected";
    }
    return "invalid_argument";
}

void TargetsController::reset() {
    resetTransient(true);
}

void TargetsController::resetTransient(bool clearPersistentState) {
    if (clearPersistentState) {
        workspace_.catalog.clear();
        workspace_.decisions.clear();
    }
    workspace_.correlations = {};
    domain::targets::resetTargetComparisonResult(&workspace_.comparison);
    rows_.fill({});
    baseline_ = {};
    current_ = {};
    rowCount_ = 0;
    selection_ = 0;
    comparisonOrder_.fill(0xffU);
    comparisonSelection_ = 0;
    actionSelection_ = 0;
    nameEditorSelection_ = 0;
    nameEditorText_.fill('\0');
    nameEditorLength_ = 0;
    originalName_.fill('\0');
    originalNameLength_ = 0;
    nameEditorGlyphSelection_ = 0;
    tagSelection_ = 0;
    tagEditorSelection_ = 0;
    tagEditorText_.fill('\0');
    tagEditorLength_ = 0;
    tagEditorGlyphSelection_ = 0;
    notesEditorSelection_ = 0;
    notesEditorText_.fill('\0');
    notesEditorLength_ = 0;
    originalNotes_.fill('\0');
    originalNotesLength_ = 0;
    notesEditorGlyphSelection_ = 0;
    correlationSelection_ = 0;
    correlationReviewSelection_ = 0;
    correlationEvidenceCandidate_ = false;
    view_ = TargetsView::List;
    status_ = TargetsLoadStatus::SessionUnavailable;
    comparisonAvailable_ = false;
    sourceIdentityCount_ = 0;
    truncated_ = false;
    lastAdmission_ = {};
    lastAdmissionStage_ = "none";
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& current) {
    return loadBindings({}, current, false);
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& current,
    const domain::targets::TargetCatalog& persisted) {
    return loadBindings({}, current, false, &persisted);
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& current,
    const domain::targets::TargetCatalog& persisted,
    const domain::targets::CorrelationDecisionLog& decisions) {
    return loadBindings({}, current, false, &persisted, &decisions);
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& baseline,
    const TargetProductBinding& current) {
    return loadBindings(baseline, current, true);
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& baseline,
    const TargetProductBinding& current,
    const domain::targets::TargetCatalog& persisted) {
    return loadBindings(baseline, current, true, &persisted);
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& baseline,
    const TargetProductBinding& current,
    const domain::targets::TargetCatalog& persisted,
    const domain::targets::CorrelationDecisionLog& decisions) {
    return loadBindings(baseline, current, true, &persisted, &decisions);
}

TargetsLoadStatus TargetsController::loadBindings(
    const TargetProductBinding& baseline,
    const TargetProductBinding& current, bool compare,
    const domain::targets::TargetCatalog* persisted,
    const domain::targets::CorrelationDecisionLog* decisions) {
    const bool catalogInPlace = persisted == &workspace_.catalog;
    const bool decisionsInPlace = decisions == &workspace_.decisions;
    if ((persisted != nullptr && catalogInPlace != decisionsInPlace) ||
        (decisions != nullptr && catalogInPlace != decisionsInPlace)) {
        reset();
        status_ = TargetsLoadStatus::InvalidArgument;
        return status_;
    }
    resetTransient(catalogInPlace && decisionsInPlace ? false : true);
    if (!bindingValid(current) || (compare && !bindingValid(baseline)) ||
        (compare && baseline.session == current.session)) {
        status_ = TargetsLoadStatus::InvalidArgument;
        return status_;
    }
    if (persisted != nullptr && !catalogInPlace) workspace_.catalog = *persisted;
    if (decisions != nullptr && !decisionsInPlace) {
        workspace_.decisions = *decisions;
    }
    baseline_ = baseline;
    current_ = current;
    services::targets::SessionTargetIdentityFilter filter{};
    if (!selectStrongestIdentities(baseline, current, compare, &filter,
                                   &sourceIdentityCount_)) {
        reset();
        status_ = TargetsLoadStatus::AdmissionRejected;
        return status_;
    }
    truncated_ = sourceIdentityCount_ > filter.size;
    auto* scratch = new (std::nothrow) domain::targets::TargetCatalog();
    if (scratch == nullptr) {
        reset();
        status_ = TargetsLoadStatus::AdmissionRejected;
        return status_;
    }
    if (compare) {
        const auto admittedBaseline = services::targets::admitSessionTargets(
            *baseline.session, baseline.generation, workspace_.catalog,
            *scratch, &filter);
        if (!admittedBaseline.valid()) {
            delete scratch;
            reset();
            lastAdmission_ = admittedBaseline;
            lastAdmissionStage_ = "baseline";
            status_ = TargetsLoadStatus::AdmissionRejected;
            return status_;
        }
        lastAdmission_ = admittedBaseline;
        lastAdmissionStage_ = "baseline";
        if (admittedBaseline.capacitySkipped != 0) truncated_ = true;
        const auto baselineSource = comparisonSource(baseline);
        const auto currentSource = comparisonSource(current);
        const auto correlationStatus =
            services::targets::buildSessionCorrelationReview(
                {baselineSource, baseline.session},
                {currentSource, current.session}, workspace_.catalog,
                workspace_.decisions, &workspace_.correlations);
        if (correlationStatus !=
            services::targets::SessionCorrelationReviewStatus::Ready) {
            delete scratch;
            reset();
            status_ = TargetsLoadStatus::EvidenceUnavailable;
            return status_;
        }
        removePendingCorrelations(workspace_.correlations, &filter);
    }
    const auto admittedCurrent = services::targets::admitSessionTargets(
        *current.session, current.generation, workspace_.catalog,
        *scratch, &filter);
    delete scratch;
    if (!admittedCurrent.valid()) {
        reset();
        lastAdmission_ = admittedCurrent;
        lastAdmissionStage_ = "current";
        status_ = TargetsLoadStatus::AdmissionRejected;
        return status_;
    }
    lastAdmission_ = admittedCurrent;
    lastAdmissionStage_ = "current";
    if (admittedCurrent.capacitySkipped != 0) truncated_ = true;
    if (!rebuildRows()) {
        reset();
        status_ = TargetsLoadStatus::EvidenceUnavailable;
        return status_;
    }
    if (compare) {
        const auto baselineSource = comparisonSource(baseline);
        const auto currentSource = comparisonSource(current);
        services::targets::SurveySessionTargetEvidenceLookup lookup(
            {baselineSource, baseline.session},
            {currentSource, current.session});
        services::targets::TargetComparisonService comparison(
            workspace_.catalog, lookup);
        comparison.executeInto(
            {services::targets::kTargetComparisonActionSchemaVersion,
             baselineSource, currentSource},
            &workspace_.comparison);
        if (!workspace_.comparison.compared()) {
            reset();
            status_ = TargetsLoadStatus::CompareRejected;
            return status_;
        }
        if (!rebuildComparisonOrder()) {
            reset();
            status_ = TargetsLoadStatus::EvidenceUnavailable;
            return status_;
        }
        comparisonAvailable_ = true;
    }
    status_ = TargetsLoadStatus::Ready;
    return status_;
}

bool TargetsController::loadExact(
    const domain::targets::TargetEvidenceRef& evidence,
    domain::observations::Observation* output) const {
    if (output == nullptr || !domain::targets::targetEvidenceValid(evidence)) {
        return false;
    }
    const std::array<TargetProductBinding, 2> bindings{{baseline_, current_}};
    for (const TargetProductBinding& binding : bindings) {
        if (!bindingValid(binding)) continue;
        domain::targets::SourceId sourceId{};
        if (!services::targets::sourceIdForSession(*binding.session,
                                                   &sourceId) ||
            sourceId.bytes != evidence.sourceId.bytes ||
            binding.generation != evidence.sourceGeneration) {
            continue;
        }
        for (std::size_t index = 0; index < binding.session->size(); ++index) {
            const auto* observation = binding.session->get(index);
            if (observation != nullptr &&
                observation->sequence == evidence.observationSequence &&
                observation->monotonicUs == evidence.observedMonotonicUs) {
                *output = *observation;
                return true;
            }
        }
        return false;
    }
    return false;
}

bool TargetsController::rebuildRows() {
    rows_.fill({});
    rowCount_ = 0;
    for (std::size_t targetIndex = 0;
         targetIndex < workspace_.catalog.size(); ++targetIndex) {
        const auto* target = workspace_.catalog.get(targetIndex);
        if (target == nullptr || target->evidenceCount == 0 ||
            rowCount_ >= rows_.size()) {
            return false;
        }
        bool found = false;
        TargetListRow row{};
        row.targetId = target->id;
        for (std::size_t evidenceIndex = 0;
             evidenceIndex < target->evidenceCount; ++evidenceIndex) {
            domain::observations::Observation observation{};
            if (!loadExact(target->evidence[evidenceIndex], &observation)) {
                continue;
            }
            const bool observationIsCurrent =
                target->evidence[evidenceIndex].sourceGeneration ==
                    current_.generation;
            const bool selectedIsCurrent = found &&
                row.evidence.sourceGeneration == current_.generation;
            if (!found || (observationIsCurrent && !selectedIsCurrent) ||
                (observationIsCurrent == selectedIsCurrent &&
                 observation.monotonicUs > row.latest.monotonicUs)) {
                row.latest = observation;
                row.evidence = target->evidence[evidenceIndex];
                found = true;
            }
        }
        // A durable catalog can contain identities from visits outside the two
        // currently open Sessions. They remain retained state, but are not list
        // rows until exact evidence for this view is available.
        if (!found) continue;
        bool identityFound = false;
        for (std::size_t identityIndex = 0;
             identityIndex < target->identityCount; ++identityIndex) {
            const auto& identity = target->identities[identityIndex];
            if (identity.length == row.latest.identityLength &&
                identity.value == row.latest.identity) {
                row.identity = identity;
                identityFound = true;
                break;
            }
        }
        if (!identityFound) return false;
        rows_[rowCount_++] = row;
    }
    for (std::size_t index = 1; index < rowCount_; ++index) {
        std::size_t current = index;
        while (current > 0 && rowBefore(rows_[current], rows_[current - 1])) {
            std::swap(rows_[current], rows_[current - 1]);
            --current;
        }
    }
    return true;
}

bool TargetsController::loadComparisonSide(
    const domain::targets::TargetComparisonItem& item, bool current,
    TargetComparisonSide* output) const {
    if (output == nullptr) return false;
    *output = {};
    const auto& evidence = current ? item.currentEvidence
                                   : item.baselineEvidence;
    const std::size_t count = current ? item.currentEvidenceCount
                                      : item.baselineEvidenceCount;
    for (std::size_t index = 0; index < count; ++index) {
        domain::observations::Observation observation{};
        if (!loadExact(evidence[index].reference, &observation)) return false;
        if (!output->present ||
            observation.rssiDbm > output->observation.rssiDbm ||
            (observation.rssiDbm == output->observation.rssiDbm &&
             observation.monotonicUs > output->observation.monotonicUs)) {
            output->identity = evidence[index].identity;
            output->evidence = evidence[index].reference;
            output->observation = observation;
            output->present = true;
        }
    }
    return true;
}

bool TargetsController::comparisonItemBefore(std::uint8_t left,
                                             std::uint8_t right) const {
    const auto* leftItem = workspace_.comparison.get(left);
    const auto* rightItem = workspace_.comparison.get(right);
    if (leftItem == nullptr || rightItem == nullptr) return false;
    const std::uint8_t leftRank = comparisonClassRank(leftItem->classification);
    const std::uint8_t rightRank = comparisonClassRank(rightItem->classification);
    if (leftRank != rightRank) return leftRank < rightRank;

    TargetComparisonSide leftSignal{};
    TargetComparisonSide rightSignal{};
    if (!loadComparisonSide(*leftItem,
                            leftItem->currentEvidenceCount != 0,
                            &leftSignal) ||
        !loadComparisonSide(*rightItem,
                            rightItem->currentEvidenceCount != 0,
                            &rightSignal)) {
        return leftItem->targetId.bytes < rightItem->targetId.bytes;
    }
    if (leftSignal.observation.rssiDbm != rightSignal.observation.rssiDbm) {
        return leftSignal.observation.rssiDbm >
               rightSignal.observation.rssiDbm;
    }
    if (leftSignal.observation.monotonicUs !=
        rightSignal.observation.monotonicUs) {
        return leftSignal.observation.monotonicUs >
               rightSignal.observation.monotonicUs;
    }
    return leftItem->targetId.bytes < rightItem->targetId.bytes;
}

bool TargetsController::rebuildComparisonOrder() {
    comparisonOrder_.fill(0xffU);
    comparisonSelection_ = 0;
    for (std::size_t index = 0; index < workspace_.comparison.size; ++index) {
        comparisonOrder_[index] = static_cast<std::uint8_t>(index);
    }
    for (std::size_t index = 1; index < workspace_.comparison.size; ++index) {
        std::size_t current = index;
        while (current > 0 && comparisonItemBefore(
                   comparisonOrder_[current], comparisonOrder_[current - 1])) {
            std::swap(comparisonOrder_[current],
                      comparisonOrder_[current - 1]);
            --current;
        }
    }
    return true;
}

bool TargetsController::next() {
    if (view_ == TargetsView::List) {
        if (selection_ + 1 >= entryCount()) return false;
        ++selection_;
        return true;
    }
    if (view_ == TargetsView::Compare) {
        if (comparisonSelection_ + 1 >= comparisonSize()) return false;
        ++comparisonSelection_;
        return true;
    }
    if (view_ == TargetsView::Actions) {
        if (actionSelection_ + 1 >= kActionCount) return false;
        ++actionSelection_;
        return true;
    }
    if (view_ == TargetsView::NameEdit) {
        if (nameEditorSelection_ + 1 >= kNameEditControlCount) return false;
        ++nameEditorSelection_;
        return true;
    }
    if (view_ == TargetsView::TagList) {
        if (tagSelection_ + 1 >= tagEntryCount()) return false;
        ++tagSelection_;
        return true;
    }
    if (view_ == TargetsView::TagEdit) {
        if (tagEditorSelection_ + 1 >= kTagEditControlCount) return false;
        ++tagEditorSelection_;
        return true;
    }
    if (view_ == TargetsView::NotesEdit) {
        if (notesEditorSelection_ + 1 >= kNotesEditControlCount) return false;
        ++notesEditorSelection_;
        return true;
    }
    if (view_ == TargetsView::CorrelationList) {
        if (correlationSelection_ + 1 >= selectedCorrelationCount()) {
            return false;
        }
        ++correlationSelection_;
        return true;
    }
    if (view_ == TargetsView::CorrelationReview) {
        if (correlationReviewSelection_ + 1 >=
            kCorrelationReviewControlCount) {
            return false;
        }
        ++correlationReviewSelection_;
        return true;
    }
    return false;
}

bool TargetsController::previous() {
    if (view_ == TargetsView::List) {
        if (selection_ == 0) return false;
        --selection_;
        return true;
    }
    if (view_ == TargetsView::Compare) {
        if (comparisonSelection_ == 0) return false;
        --comparisonSelection_;
        return true;
    }
    if (view_ == TargetsView::Actions) {
        if (actionSelection_ == 0) return false;
        --actionSelection_;
        return true;
    }
    if (view_ == TargetsView::NameEdit) {
        if (nameEditorSelection_ == 0) return false;
        --nameEditorSelection_;
        return true;
    }
    if (view_ == TargetsView::TagList) {
        if (tagSelection_ == 0) return false;
        --tagSelection_;
        return true;
    }
    if (view_ == TargetsView::TagEdit) {
        if (tagEditorSelection_ == 0) return false;
        --tagEditorSelection_;
        return true;
    }
    if (view_ == TargetsView::NotesEdit) {
        if (notesEditorSelection_ == 0) return false;
        --notesEditorSelection_;
        return true;
    }
    if (view_ == TargetsView::CorrelationList) {
        if (correlationSelection_ == 0) return false;
        --correlationSelection_;
        return true;
    }
    if (view_ == TargetsView::CorrelationReview) {
        if (correlationReviewSelection_ == 0) return false;
        --correlationReviewSelection_;
        return true;
    }
    return false;
}

bool TargetsController::openSelected() {
    if (view_ == TargetsView::List && entryCount() != 0) {
        view_ = selectedIsCompare() ? TargetsView::Compare
                                    : TargetsView::Detail;
        if (view_ == TargetsView::Compare) comparisonSelection_ = 0;
        return true;
    }
    if (view_ == TargetsView::Compare && comparisonSize() != 0) {
        view_ = TargetsView::CompareDetail;
        return true;
    }
    if (view_ == TargetsView::Detail && selectedTarget() != nullptr) {
        view_ = TargetsView::Actions;
        actionSelection_ = 0;
        return true;
    }
    if (view_ == TargetsView::CorrelationList &&
        selectedCorrelationCount() != 0) {
        view_ = TargetsView::CorrelationReview;
        correlationReviewSelection_ = 0;
        return true;
    }
    if (view_ == TargetsView::CorrelationReview &&
        correlationReviewSelection_ < 2 &&
        reviewedCorrelationProposal() != nullptr) {
        correlationEvidenceCandidate_ = correlationReviewSelection_ == 1;
        view_ = TargetsView::CorrelationEvidence;
        return true;
    }
    return false;
}

bool TargetsController::openNameEditor() {
    if (view_ != TargetsView::Actions ||
        selectedAction() != TargetActionItem::Name) {
        return false;
    }
    const auto* target = selectedTarget();
    if (target == nullptr || target->nameLength > target->name.size() - 1U) {
        return false;
    }
    nameEditorText_.fill('\0');
    originalName_.fill('\0');
    if (target->nameLength != 0) {
        std::memcpy(nameEditorText_.data(), target->name.data(),
                    target->nameLength);
        std::memcpy(originalName_.data(), target->name.data(),
                    target->nameLength);
    }
    nameEditorLength_ = target->nameLength;
    originalNameLength_ = target->nameLength;
    nameEditorSelection_ = 0;
    nameEditorGlyphSelection_ = 0;
    view_ = TargetsView::NameEdit;
    return true;
}

TargetActionItem TargetsController::selectedAction() const {
    switch (actionSelection_) {
        case 0: return TargetActionItem::Favorite;
        case 1: return TargetActionItem::Name;
        case 2: return TargetActionItem::Tags;
        case 3: return TargetActionItem::Notes;
        default: return TargetActionItem::Correlations;
    }
}

std::size_t TargetsController::tagEntryCount() const {
    const auto* target = selectedTarget();
    if (target == nullptr) return 0;
    return target->tagCount +
        (target->tagCount <
                 domain::targets::TargetRecord::kTagCountCapacity
             ? 1U : 0U);
}

bool TargetsController::selectedTagIsAdd() const {
    const auto* target = selectedTarget();
    return target != nullptr &&
        target->tagCount <
            domain::targets::TargetRecord::kTagCountCapacity &&
        tagSelection_ == target->tagCount;
}

const char* TargetsController::selectedTagText() const {
    const auto* target = selectedTarget();
    return target != nullptr && tagSelection_ < target->tagCount
        ? target->tags[tagSelection_].data() : "";
}

std::size_t TargetsController::selectedTagLength() const {
    const auto* target = selectedTarget();
    return target != nullptr && tagSelection_ < target->tagCount
        ? target->tagLengths[tagSelection_] : 0U;
}

bool TargetsController::openTagList() {
    if (view_ != TargetsView::Actions ||
        selectedAction() != TargetActionItem::Tags ||
        selectedTarget() == nullptr) {
        return false;
    }
    tagSelection_ = 0;
    view_ = TargetsView::TagList;
    return true;
}

bool TargetsController::openTagEditor() {
    if (view_ != TargetsView::TagList || !selectedTagIsAdd()) return false;
    tagEditorText_.fill('\0');
    tagEditorLength_ = 0;
    tagEditorSelection_ = 0;
    tagEditorGlyphSelection_ = 0;
    view_ = TargetsView::TagEdit;
    return true;
}

char TargetsController::tagEditorGlyph() const {
    constexpr std::size_t count = sizeof(kTargetTagGlyphs) - 1U;
    return kTargetTagGlyphs[tagEditorGlyphSelection_ % count];
}

bool TargetsController::cycleTagEditorGlyph() {
    if (view_ != TargetsView::TagEdit) return false;
    constexpr std::size_t count = sizeof(kTargetTagGlyphs) - 1U;
    tagEditorGlyphSelection_ = (tagEditorGlyphSelection_ + 1U) % count;
    return true;
}

bool TargetsController::appendTagEditorGlyph() {
    if (view_ != TargetsView::TagEdit || !tagEditorCanAppend()) return false;
    tagEditorText_[tagEditorLength_++] = tagEditorGlyph();
    tagEditorText_[tagEditorLength_] = '\0';
    return true;
}

bool TargetsController::eraseTagEditorGlyph() {
    if (view_ != TargetsView::TagEdit || tagEditorLength_ == 0) return false;
    tagEditorText_[--tagEditorLength_] = '\0';
    return true;
}

bool TargetsController::openNotesEditor() {
    if (view_ != TargetsView::Actions ||
        selectedAction() != TargetActionItem::Notes) {
        return false;
    }
    const auto* target = selectedTarget();
    if (target == nullptr || target->notesLength > target->notes.size() - 1U) {
        return false;
    }
    notesEditorText_.fill('\0');
    originalNotes_.fill('\0');
    if (target->notesLength != 0) {
        std::memcpy(notesEditorText_.data(), target->notes.data(),
                    target->notesLength);
        std::memcpy(originalNotes_.data(), target->notes.data(),
                    target->notesLength);
    }
    notesEditorLength_ = target->notesLength;
    originalNotesLength_ = target->notesLength;
    notesEditorSelection_ = 0;
    notesEditorGlyphSelection_ = 0;
    view_ = TargetsView::NotesEdit;
    return true;
}

bool TargetsController::openCorrelationList() {
    if (view_ != TargetsView::Actions ||
        selectedAction() != TargetActionItem::Correlations ||
        selectedTarget() == nullptr || selectedCorrelationCount() == 0) {
        return false;
    }
    correlationSelection_ = 0;
    view_ = TargetsView::CorrelationList;
    return true;
}

char TargetsController::notesEditorGlyph() const {
    constexpr std::size_t count = sizeof(kTargetNotesGlyphs) - 1U;
    return kTargetNotesGlyphs[notesEditorGlyphSelection_ % count];
}

bool TargetsController::notesEditorDirty() const {
    return view_ == TargetsView::NotesEdit &&
        (notesEditorLength_ != originalNotesLength_ ||
         std::memcmp(notesEditorText_.data(), originalNotes_.data(),
                     notesEditorLength_) != 0);
}

bool TargetsController::cycleNotesEditorGlyph() {
    if (view_ != TargetsView::NotesEdit) return false;
    constexpr std::size_t count = sizeof(kTargetNotesGlyphs) - 1U;
    notesEditorGlyphSelection_ = (notesEditorGlyphSelection_ + 1U) % count;
    return true;
}

bool TargetsController::appendNotesEditorGlyph() {
    if (view_ != TargetsView::NotesEdit || !notesEditorCanAppend()) return false;
    notesEditorText_[notesEditorLength_++] = notesEditorGlyph();
    notesEditorText_[notesEditorLength_] = '\0';
    return true;
}

bool TargetsController::eraseNotesEditorGlyph() {
    if (view_ != TargetsView::NotesEdit || notesEditorLength_ == 0) return false;
    std::size_t start = notesEditorLength_ - 1U;
    while (start > 0U &&
           (static_cast<unsigned char>(notesEditorText_[start]) & 0xc0U) ==
               0x80U) {
        --start;
    }
    for (std::size_t index = start; index <= notesEditorLength_; ++index) {
        notesEditorText_[index] = '\0';
    }
    notesEditorLength_ = start;
    return true;
}

char TargetsController::nameEditorGlyph() const {
    constexpr std::size_t count = sizeof(kTargetNameGlyphs) - 1U;
    return kTargetNameGlyphs[nameEditorGlyphSelection_ % count];
}

bool TargetsController::nameEditorDirty() const {
    return view_ == TargetsView::NameEdit &&
        (nameEditorLength_ != originalNameLength_ ||
        std::memcmp(nameEditorText_.data(), originalName_.data(),
                    nameEditorLength_) != 0);
}

bool TargetsController::cycleNameEditorGlyph() {
    if (view_ != TargetsView::NameEdit) return false;
    constexpr std::size_t count = sizeof(kTargetNameGlyphs) - 1U;
    nameEditorGlyphSelection_ = (nameEditorGlyphSelection_ + 1U) % count;
    return true;
}

bool TargetsController::appendNameEditorGlyph() {
    if (view_ != TargetsView::NameEdit || !nameEditorCanAppend()) return false;
    nameEditorText_[nameEditorLength_++] = nameEditorGlyph();
    nameEditorText_[nameEditorLength_] = '\0';
    return true;
}

bool TargetsController::eraseNameEditorGlyph() {
    if (view_ != TargetsView::NameEdit || nameEditorLength_ == 0) return false;
    std::size_t start = nameEditorLength_ - 1U;
    while (start > 0U &&
           (static_cast<unsigned char>(nameEditorText_[start]) & 0xc0U) ==
               0x80U) {
        --start;
    }
    for (std::size_t index = start; index <= nameEditorLength_; ++index) {
        nameEditorText_[index] = '\0';
    }
    nameEditorLength_ = start;
    return true;
}

bool TargetsController::openCompare() {
    if (view_ != TargetsView::List || !comparisonAvailable_) return false;
    view_ = TargetsView::Compare;
    comparisonSelection_ = 0;
    return true;
}

bool TargetsController::back() {
    if (view_ == TargetsView::List) return false;
    if (view_ == TargetsView::NameEdit) {
        view_ = TargetsView::Actions;
        return true;
    }
    if (view_ == TargetsView::TagEdit) {
        view_ = TargetsView::TagList;
        return true;
    }
    if (view_ == TargetsView::TagList) {
        view_ = TargetsView::Actions;
        return true;
    }
    if (view_ == TargetsView::NotesEdit) {
        view_ = TargetsView::Actions;
        return true;
    }
    if (view_ == TargetsView::CorrelationEvidence) {
        view_ = TargetsView::CorrelationReview;
        return true;
    }
    if (view_ == TargetsView::CorrelationReview) {
        view_ = TargetsView::CorrelationList;
        return true;
    }
    if (view_ == TargetsView::CorrelationList) {
        view_ = TargetsView::Actions;
        return true;
    }
    if (view_ == TargetsView::Actions) {
        view_ = TargetsView::Detail;
        return true;
    }
    if (view_ == TargetsView::CompareDetail) {
        view_ = TargetsView::Compare;
        return true;
    }
    view_ = TargetsView::List;
    return true;
}

bool TargetsController::selectTarget(
    const domain::targets::TargetId& id) {
    for (std::size_t index = 0; index < rowCount_; ++index) {
        if (!domain::targets::targetIdEqual(rows_[index].targetId, id)) continue;
        selection_ = index + (comparisonAvailable_ ? 1U : 0U);
        return true;
    }
    return false;
}

const TargetListRow* TargetsController::row(std::size_t index) const {
    return index < rowCount_ ? &rows_[index] : nullptr;
}

const TargetListRow* TargetsController::selectedRow() const {
    if (selectedIsCompare()) return nullptr;
    const std::size_t rowIndex = comparisonAvailable_ ? selection_ - 1U
                                                       : selection_;
    return row(rowIndex);
}

const domain::targets::TargetRecord* TargetsController::selectedTarget() const {
    const TargetListRow* selected = selectedRow();
    return selected == nullptr ? nullptr
                               : workspace_.catalog.find(selected->targetId);
}

std::size_t TargetsController::selectedCorrelationCount() const {
    const auto* target = selectedTarget();
    if (target == nullptr) return 0;
    std::size_t count = 0;
    for (std::size_t index = 0; index < workspace_.correlations.size;
         ++index) {
        if (domain::targets::targetIdEqual(
                workspace_.correlations.values[index].targetId, target->id)) {
            ++count;
        }
    }
    return count;
}

const domain::targets::CorrelationProposal*
TargetsController::selectedCorrelationProposal(std::size_t index) const {
    const auto* target = selectedTarget();
    if (target == nullptr) return nullptr;
    std::size_t found = 0;
    for (std::size_t proposalIndex = 0;
         proposalIndex < workspace_.correlations.size; ++proposalIndex) {
        const auto& proposal = workspace_.correlations.values[proposalIndex];
        if (!domain::targets::targetIdEqual(proposal.targetId, target->id)) {
            continue;
        }
        if (found++ == index) return &proposal;
    }
    return nullptr;
}

const domain::targets::CorrelationProposal*
TargetsController::reviewedCorrelationProposal() const {
    return selectedCorrelationProposal(correlationSelection_);
}

bool TargetsController::correlationEvidence(
    bool candidate, domain::observations::Observation* output) const {
    const auto* proposal = reviewedCorrelationProposal();
    if (proposal == nullptr || output == nullptr) return false;
    if (candidate) return loadExact(proposal->candidateEvidence, output);
    if (proposal->featureCount == 0) return false;
    return loadExact(proposal->features[0].targetEvidence, output);
}

const domain::targets::TargetComparisonItem* TargetsController::comparisonItem(
    std::size_t index) const {
    if (!comparisonAvailable_ || index >= workspace_.comparison.size) {
        return nullptr;
    }
    return workspace_.comparison.get(comparisonOrder_[index]);
}

const domain::targets::TargetComparisonItem*
TargetsController::selectedComparisonItem() const {
    return comparisonItem(comparisonSelection_);
}

const TargetListRow* TargetsController::comparisonTargetRow(
    std::size_t index) const {
    const auto* item = comparisonItem(index);
    if (item == nullptr) return nullptr;
    for (std::size_t rowIndex = 0; rowIndex < rowCount_; ++rowIndex) {
        if (domain::targets::targetIdEqual(rows_[rowIndex].targetId,
                                           item->targetId)) {
            return &rows_[rowIndex];
        }
    }
    return nullptr;
}

bool TargetsController::comparisonSide(std::size_t index, bool current,
                                       TargetComparisonSide* output) const {
    const auto* item = comparisonItem(index);
    return item != nullptr && loadComparisonSide(*item, current, output);
}

}  // namespace leshy1::apps::targets
