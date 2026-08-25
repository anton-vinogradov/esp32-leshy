#include "SurveySessionTargetEvidenceLookup.h"

namespace leshy1::services::targets {
namespace {

bool bindingAvailable(
    const TargetComparisonSessionBinding& binding,
    const domain::targets::TargetComparisonSource& source) {
    return domain::targets::targetComparisonSourceEqual(binding.source,
                                                         source) &&
        binding.session != nullptr &&
        binding.session->state() == survey::SessionState::Stopped;
}

bool pairAvailable(
    const std::array<TargetComparisonSessionBinding, 2>& bindings) {
    return bindings[0].session != nullptr && bindings[1].session != nullptr &&
        bindings[0].session != bindings[1].session &&
        domain::targets::targetComparisonSourceValid(bindings[0].source) &&
        domain::targets::targetComparisonSourceValid(bindings[1].source) &&
        !domain::targets::targetComparisonSourceEqual(bindings[0].source,
                                                       bindings[1].source) &&
        bindings[0].session->state() == survey::SessionState::Stopped &&
        bindings[1].session->state() == survey::SessionState::Stopped;
}

}  // namespace

bool SurveySessionTargetEvidenceLookup::sourceAvailable(
    const domain::targets::TargetComparisonSource& source) const {
    if (!domain::targets::targetComparisonSourceValid(source) ||
        !pairAvailable(bindings_)) {
        return false;
    }
    for (const TargetComparisonSessionBinding& binding : bindings_) {
        if (bindingAvailable(binding, source)) return true;
    }
    return false;
}

bool SurveySessionTargetEvidenceLookup::loadExact(
    const domain::targets::TargetEvidenceRef& evidence,
    domain::observations::Observation* output) const {
    if (output == nullptr ||
        !domain::targets::targetEvidenceValid(evidence) ||
        !pairAvailable(bindings_)) {
        return false;
    }
    const domain::targets::TargetComparisonSource source{
        evidence.sourceId, evidence.sourceGeneration};
    for (const TargetComparisonSessionBinding& binding : bindings_) {
        if (!bindingAvailable(binding, source)) continue;
        for (std::size_t index = 0; index < binding.session->size(); ++index) {
            const domain::observations::Observation* observation =
                binding.session->get(index);
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

bool SurveySessionTargetEvidenceLookup::containsExact(
    const domain::targets::TargetEvidenceRef& evidence) const {
    domain::observations::Observation observation{};
    return loadExact(evidence, &observation);
}

}  // namespace leshy1::services::targets
