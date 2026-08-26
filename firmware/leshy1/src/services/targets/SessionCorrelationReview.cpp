#include "SessionCorrelationReview.h"

#include <cstring>

#include "services/targets/ObservationTargetAdapter.h"

namespace leshy1::services::targets {
namespace {

using domain::observations::Observation;
using domain::observations::RadioKind;
using domain::targets::CorrelationProposal;
using domain::targets::TargetEvidenceRef;
using domain::targets::TargetIdentity;
using domain::targets::TargetRecord;

bool bindingValid(const TargetComparisonSessionBinding& binding) {
    return binding.session != nullptr && binding.source.generation != 0 &&
        binding.session->state() == survey::SessionState::Stopped;
}

bool latestIdentity(const survey::SurveySession& session, std::size_t index,
                    const domain::targets::SourceId& source,
                    std::uint32_t generation,
                    const TargetIdentity& identity) {
    for (std::size_t later = index + 1; later < session.size(); ++later) {
        const Observation* observation = session.get(later);
        if (observation == nullptr) return false;
        const auto admitted = admitObservationToTarget(
            source, generation, *observation);
        if (admitted.valid() && domain::targets::targetIdentityEqual(
                                    admitted.identity, identity)) {
            return false;
        }
    }
    return true;
}

bool sameLabel(const Observation& left, const Observation& right) {
    return left.labelLength != 0 && left.labelLength == right.labelLength &&
        std::memcmp(left.label.data(), right.label.data(),
                    left.labelLength) == 0;
}

bool eligibleRadioPair(const Observation& target,
                       const Observation& candidate) {
    return target.radio != RadioKind::Wifi ||
        candidate.radio != RadioKind::Wifi;
}

std::uint16_t signalStrength(std::int16_t left, std::int16_t right) {
    const std::int16_t difference = left > right ? left - right : right - left;
    if (difference > 20) return 0;
    return static_cast<std::uint16_t>(1000 - difference * 25);
}

bool proposalBefore(const CorrelationProposal& left,
                    const CorrelationProposal& right) {
    if (left.scorePermille != right.scorePermille) {
        return left.scorePermille > right.scorePermille;
    }
    return left.candidateEvidence.observedMonotonicUs >
        right.candidateEvidence.observedMonotonicUs;
}

void appendProposal(SessionCorrelationProposalSet* output,
                    const CorrelationProposal& proposal) {
    std::size_t insert = output->size;
    while (insert > 0 && proposalBefore(proposal,
                                        output->values[insert - 1U])) {
        --insert;
    }
    if (insert >= output->values.size()) {
        output->truncated = true;
        return;
    }
    const std::size_t last = output->size < output->values.size()
        ? output->size : output->values.size() - 1U;
    for (std::size_t move = last; move > insert; --move) {
        output->values[move] = output->values[move - 1U];
    }
    output->values[insert] = proposal;
    if (output->size < output->values.size()) {
        ++output->size;
    } else {
        output->truncated = true;
    }
}

}  // namespace

void resetSessionCorrelationProposalSet(
    SessionCorrelationProposalSet* output) {
    if (output == nullptr) return;
    std::memset(static_cast<void*>(output), 0, sizeof(*output));
}

SessionCorrelationReviewStatus buildSessionCorrelationReview(
    const TargetComparisonSessionBinding& baseline,
    const TargetComparisonSessionBinding& current,
    domain::targets::TargetCatalog& catalog,
    domain::targets::CorrelationDecisionLog& decisions,
    SessionCorrelationProposalSet* output) {
    if (output == nullptr || !bindingValid(baseline) ||
        !bindingValid(current) || baseline.session == current.session ||
        domain::targets::targetComparisonSourceEqual(baseline.source,
                                                      current.source)) {
        return SessionCorrelationReviewStatus::InvalidArgument;
    }
    resetSessionCorrelationProposalSet(output);
    SurveySessionTargetEvidenceLookup lookup(baseline, current);
    CorrelationService service(catalog, decisions, lookup);
    for (std::size_t index = 0; index < current.session->size(); ++index) {
        const Observation* candidateObservation = current.session->get(index);
        if (candidateObservation == nullptr) {
            resetSessionCorrelationProposalSet(output);
            return SessionCorrelationReviewStatus::EvidenceUnavailable;
        }
        const auto candidate = admitObservationToTarget(
            current.source.id, current.source.generation,
            *candidateObservation);
        if (!candidate.valid()) {
            resetSessionCorrelationProposalSet(output);
            return SessionCorrelationReviewStatus::EvidenceUnavailable;
        }
        if (!latestIdentity(*current.session, index, current.source.id,
                            current.source.generation, candidate.identity) ||
            catalog.findByIdentity(candidate.identity) != nullptr ||
            candidateObservation->labelLength == 0) {
            continue;
        }

        const TargetRecord* matchingTarget = nullptr;
        TargetEvidenceRef matchingEvidence{};
        std::int16_t matchingRssi = -128;
        std::size_t matchingTargets = 0;
        for (std::size_t targetIndex = 0;
             targetIndex < catalog.size(); ++targetIndex) {
            const TargetRecord* target = catalog.get(targetIndex);
            if (target == nullptr) {
                resetSessionCorrelationProposalSet(output);
                return SessionCorrelationReviewStatus::EvidenceUnavailable;
            }
            bool targetMatched = false;
            TargetEvidenceRef bestEvidence{};
            std::int16_t bestRssi = -128;
            std::int16_t bestDifference = 32767;
            for (std::size_t evidenceIndex = 0;
                 evidenceIndex < target->evidenceCount; ++evidenceIndex) {
                const TargetEvidenceRef& evidence =
                    target->evidence[evidenceIndex];
                if (evidence.sourceId.bytes != baseline.source.id.bytes ||
                    evidence.sourceGeneration !=
                        baseline.source.generation) {
                    continue;
                }
                Observation targetObservation{};
                if (!lookup.loadExact(evidence, &targetObservation)) continue;
                const std::uint16_t strength = signalStrength(
                    targetObservation.rssiDbm, candidateObservation->rssiDbm);
                if (!sameLabel(targetObservation, *candidateObservation) ||
                    !eligibleRadioPair(targetObservation,
                                       *candidateObservation) ||
                    strength == 0) {
                    continue;
                }
                const std::int16_t difference =
                    targetObservation.rssiDbm > candidateObservation->rssiDbm
                    ? targetObservation.rssiDbm - candidateObservation->rssiDbm
                    : candidateObservation->rssiDbm - targetObservation.rssiDbm;
                if (!targetMatched || difference < bestDifference ||
                    (difference == bestDifference &&
                     evidence.observedMonotonicUs >
                         bestEvidence.observedMonotonicUs)) {
                    targetMatched = true;
                    bestDifference = difference;
                    bestEvidence = evidence;
                    bestRssi = targetObservation.rssiDbm;
                }
            }
            if (targetMatched) {
                ++matchingTargets;
                matchingTarget = target;
                matchingEvidence = bestEvidence;
                matchingRssi = bestRssi;
            }
        }
        // Ambiguous names remain independent Targets. Never let signal alone
        // choose ownership between two equally plausible source objects.
        if (matchingTargets != 1 || matchingTarget == nullptr) continue;
        const std::uint16_t strength = signalStrength(
            matchingRssi, candidateObservation->rssiDbm);
        const std::array<CorrelationFeatureInput, 2> features{{
            {domain::targets::CorrelationFeatureKind::AdvertisedNameMatch,
             1000, matchingEvidence},
            {domain::targets::CorrelationFeatureKind::SignalTrendMatch,
             strength, matchingEvidence},
        }};
        const CorrelationProposalResult proposed = service.propose(
            matchingTarget->id, candidate.identity, candidate.evidence,
            features.data(), features.size(), false);
        if (proposed.status == CorrelationProposalStatus::Proposed &&
            proposed.proposal.confidence !=
                domain::targets::CorrelationConfidence::Low) {
            appendProposal(output, proposed.proposal);
        }
    }
    return SessionCorrelationReviewStatus::Ready;
}

bool sessionCorrelationCandidatePending(
    const SessionCorrelationProposalSet& proposals,
    const TargetIdentity& identity) {
    for (std::size_t index = 0; index < proposals.size; ++index) {
        if (domain::targets::targetIdentityEqual(
                proposals.values[index].candidateIdentity, identity)) {
            return true;
        }
    }
    return false;
}

}  // namespace leshy1::services::targets
