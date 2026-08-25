#include "TargetsController.h"

#include <new>
#include <utility>

#include "services/targets/SessionTargetAdmission.h"
#include "services/targets/SurveySessionTargetEvidenceLookup.h"
#include "services/targets/TargetComparisonService.h"

namespace leshy1::apps::targets {
namespace {

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
    services::targets::SessionTargetIdentityFilter* filter,
    std::size_t* uniqueCount) {
    if (filter == nullptr || uniqueCount == nullptr) return false;
    std::array<RankedIdentity, domain::targets::TargetCatalog::kCapacity> ranked{};
    std::size_t rankedSize = 0;
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
        std::size_t insert = rankedSize;
        while (insert > 0 && rankedBefore(candidate, ranked[insert - 1])) {
            --insert;
        }
        if (insert >= ranked.size()) continue;
        const std::size_t last = rankedSize < ranked.size()
            ? rankedSize : ranked.size() - 1;
        for (std::size_t move = last; move > insert; --move) {
            ranked[move] = ranked[move - 1];
        }
        ranked[insert] = candidate;
        if (rankedSize < ranked.size()) ++rankedSize;
    }
    const std::size_t available = filter->identities.size() - filter->size;
    const std::size_t copyCount = rankedSize < available ? rankedSize : available;
    for (std::size_t index = 0; index < copyCount; ++index) {
        filter->identities[filter->size++] = ranked[index].identity;
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
    if (!appendStrongest(*current.session, nullptr, filter,
                         sourceIdentityCount)) {
        return false;
    }
    return !compare || (baseline.session != nullptr &&
        appendStrongest(*baseline.session, current.session, filter,
                        sourceIdentityCount));
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
    workspace_.catalog.clear();
    domain::targets::resetTargetComparisonResult(&workspace_.comparison);
    rows_.fill({});
    baseline_ = {};
    current_ = {};
    rowCount_ = 0;
    selection_ = 0;
    comparisonOrder_.fill(0xffU);
    comparisonSelection_ = 0;
    view_ = TargetsView::List;
    status_ = TargetsLoadStatus::SessionUnavailable;
    comparisonAvailable_ = false;
    sourceIdentityCount_ = 0;
    truncated_ = false;
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& current) {
    return loadBindings({}, current, false);
}

TargetsLoadStatus TargetsController::load(
    const TargetProductBinding& baseline,
    const TargetProductBinding& current) {
    return loadBindings(baseline, current, true);
}

TargetsLoadStatus TargetsController::loadBindings(
    const TargetProductBinding& baseline,
    const TargetProductBinding& current, bool compare) {
    reset();
    if (!bindingValid(current) || (compare && !bindingValid(baseline)) ||
        (compare && baseline.session == current.session)) {
        status_ = TargetsLoadStatus::InvalidArgument;
        return status_;
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
            status_ = TargetsLoadStatus::AdmissionRejected;
            return status_;
        }
    }
    const auto admittedCurrent = services::targets::admitSessionTargets(
        *current.session, current.generation, workspace_.catalog,
        *scratch, &filter);
    delete scratch;
    if (!admittedCurrent.valid()) {
        reset();
        status_ = TargetsLoadStatus::AdmissionRejected;
        return status_;
    }
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
        if (!found) return false;
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
    return false;
}

bool TargetsController::openCompare() {
    if (view_ != TargetsView::List || !comparisonAvailable_) return false;
    view_ = TargetsView::Compare;
    comparisonSelection_ = 0;
    return true;
}

bool TargetsController::back() {
    if (view_ == TargetsView::List) return false;
    if (view_ == TargetsView::CompareDetail) {
        view_ = TargetsView::Compare;
        return true;
    }
    view_ = TargetsView::List;
    return true;
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
