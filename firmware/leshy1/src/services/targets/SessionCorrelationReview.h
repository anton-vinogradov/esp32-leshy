#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/targets/Correlation.h"
#include "domain/targets/TargetCatalog.h"
#include "services/targets/SurveySessionTargetEvidenceLookup.h"

namespace leshy1::services::targets {

enum class SessionCorrelationReviewStatus : std::uint8_t {
    Ready,
    InvalidArgument,
    EvidenceUnavailable,
};

struct SessionCorrelationProposalSet final {
    static constexpr std::size_t kCapacity = 8;

    std::array<domain::targets::CorrelationProposal, kCapacity> values{};
    std::size_t size = 0;
    bool truncated = false;
};

// Builds explainable, non-mutating proposals only for an identity that is new
// in the current Session and has one unambiguous retained Target match in the
// baseline Session.  Exact advertised-name equality plus <=20 dB signal
// proximity is the initial conservative product rule. Wi-Fi/Wi-Fi ESSID
// matches are excluded because one network commonly owns several BSSIDs.
SessionCorrelationReviewStatus buildSessionCorrelationReview(
    const TargetComparisonSessionBinding& baseline,
    const TargetComparisonSessionBinding& current,
    domain::targets::TargetCatalog& catalog,
    domain::targets::CorrelationDecisionLog& decisions,
    SessionCorrelationProposalSet* output);

bool sessionCorrelationCandidatePending(
    const SessionCorrelationProposalSet& proposals,
    const domain::targets::TargetIdentity& identity);

}  // namespace leshy1::services::targets
