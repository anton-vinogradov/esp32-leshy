#pragma once

#include <array>

#include "domain/targets/TargetComparison.h"
#include "services/survey/SurveySession.h"

namespace leshy1::services::targets {

struct TargetComparisonSessionBinding final {
    domain::targets::TargetComparisonSource source{};
    const survey::SurveySession* session = nullptr;
};

// Exact read-only bridge over the two recovered/retained Sessions selected by
// the user. It never falls through to another generation or a newer record.
class SurveySessionTargetEvidenceLookup final
    : public domain::targets::TargetComparisonEvidenceLookup {
public:
    SurveySessionTargetEvidenceLookup(
        const TargetComparisonSessionBinding& baseline,
        const TargetComparisonSessionBinding& current)
        : bindings_{{baseline, current}} {}

    bool sourceAvailable(
        const domain::targets::TargetComparisonSource& source) const override;
    bool loadExact(
        const domain::targets::TargetEvidenceRef& evidence,
        domain::observations::Observation* output) const override;

private:
    std::array<TargetComparisonSessionBinding, 2> bindings_{};
};

}  // namespace leshy1::services::targets
