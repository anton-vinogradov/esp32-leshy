#include "CorrelationService.h"

namespace leshy1::services::targets {
namespace {

using domain::targets::CorrelationConfidence;
using domain::targets::CorrelationDecision;
using domain::targets::CorrelationDecisionRecord;
using domain::targets::CorrelationDecisionStatus;
using domain::targets::CorrelationFeatureKind;
using domain::targets::CorrelationProposal;
using domain::targets::TargetMutationStatus;

constexpr kernel::runtime::ResourceMask kCorrelationWriteResources =
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage);

constexpr std::array<CorrelationActionDescriptor, 2> kDescriptors{{
    {"correlation.accept", 1, 1, "targets.correlate",
     "local_library_write", kCorrelationWriteResources, 50, false},
    {"correlation.reject", 1, 1, "targets.correlate",
     "local_library_write", kCorrelationWriteResources, 50, false},
}};

bool targetOwnsEvidence(const domain::targets::TargetRecord& target,
                        const domain::targets::TargetEvidenceRef& evidence) {
    for (std::size_t index = 0; index < target.evidenceCount; ++index) {
        if (domain::targets::targetEvidenceEqual(target.evidence[index],
                                                  evidence)) {
            return true;
        }
    }
    return false;
}

CorrelationDecisionStatus mutationStatus(TargetMutationStatus status) {
    switch (status) {
        case TargetMutationStatus::Applied:
        case TargetMutationStatus::Unchanged:
            return CorrelationDecisionStatus::Accepted;
        case TargetMutationStatus::IdentityConflict:
            return CorrelationDecisionStatus::IdentityConflict;
        case TargetMutationStatus::EvidenceConflict:
            return CorrelationDecisionStatus::EvidenceConflict;
        default: return CorrelationDecisionStatus::InvalidArgument;
    }
}

}  // namespace

const char* correlationProposalStatusName(CorrelationProposalStatus status) {
    switch (status) {
        case CorrelationProposalStatus::Proposed: return "proposed";
        case CorrelationProposalStatus::InvalidArgument:
            return "invalid_argument";
        case CorrelationProposalStatus::TargetNotFound:
            return "target_not_found";
        case CorrelationProposalStatus::ExistingIdentity:
            return "existing_identity";
        case CorrelationProposalStatus::IdentityConflict:
            return "identity_conflict";
        case CorrelationProposalStatus::EvidenceConflict:
            return "evidence_conflict";
        case CorrelationProposalStatus::CandidateEvidenceMissing:
            return "candidate_evidence_missing";
        case CorrelationProposalStatus::UnsupportedFeature:
            return "unsupported_feature";
        case CorrelationProposalStatus::DuplicateFeature:
            return "duplicate_feature";
        case CorrelationProposalStatus::FeatureEvidenceMissing:
            return "feature_evidence_missing";
        case CorrelationProposalStatus::ProposalIdConflict:
            return "proposal_id_conflict";
        case CorrelationProposalStatus::PreviouslyAccepted:
            return "previously_accepted";
        case CorrelationProposalStatus::PreviouslyRejected:
            return "previously_rejected";
    }
    return "invalid_argument";
}

const CorrelationActionDescriptor* correlationActionDescriptor(
    CorrelationActionKind kind) {
    const std::uint8_t raw = static_cast<std::uint8_t>(kind);
    return raw == 0 || raw > kDescriptors.size() ? nullptr
                                                 : &kDescriptors[raw - 1U];
}

CorrelationProposalResult CorrelationService::propose(
    const domain::targets::TargetId& targetId,
    const domain::targets::TargetIdentity& candidateIdentity,
    const domain::targets::TargetEvidenceRef& candidateEvidence,
    const CorrelationFeatureInput* features, std::size_t featureCount,
    bool stale) const {
    CorrelationProposalResult result{};
    if (!domain::targets::targetIdValid(targetId) ||
        !domain::targets::targetIdentityValid(candidateIdentity) ||
        !domain::targets::targetEvidenceValid(candidateEvidence) ||
        features == nullptr || featureCount == 0 ||
        featureCount > CorrelationProposal::kFeatureCapacity) {
        return result;
    }
    const domain::targets::TargetRecord* target = catalog_.find(targetId);
    if (target == nullptr) {
        result.status = CorrelationProposalStatus::TargetNotFound;
        return result;
    }
    const domain::targets::TargetRecord* identityOwner =
        catalog_.findByIdentity(candidateIdentity);
    if (identityOwner != nullptr) {
        result.status = domain::targets::targetIdEqual(identityOwner->id,
                                                       targetId)
            ? CorrelationProposalStatus::ExistingIdentity
            : CorrelationProposalStatus::IdentityConflict;
        return result;
    }
    if (catalog_.findByEvidence(candidateEvidence) != nullptr) {
        result.status = CorrelationProposalStatus::EvidenceConflict;
        return result;
    }
    if (!evidenceLookup_.containsExact(candidateEvidence)) {
        result.status = CorrelationProposalStatus::CandidateEvidenceMissing;
        return result;
    }

    CorrelationProposal proposal{};
    proposal.id = domain::targets::makeCorrelationProposalId(
        targetId, candidateIdentity, candidateEvidence);
    proposal.targetId = targetId;
    proposal.candidateIdentity = candidateIdentity;
    proposal.candidateEvidence = candidateEvidence;
    proposal.featureCount = static_cast<std::uint8_t>(featureCount);
    proposal.stale = stale;
    std::uint16_t score = 0;
    for (std::size_t index = 0; index < featureCount; ++index) {
        const CorrelationFeatureInput& input = features[index];
        const std::uint16_t maximum =
            domain::targets::correlationFeatureMaximumPoints(input.kind);
        if (maximum == 0 || input.strengthPermille == 0 ||
            input.strengthPermille > 1000) {
            result.status = CorrelationProposalStatus::UnsupportedFeature;
            return result;
        }
        for (std::size_t prior = 0; prior < index; ++prior) {
            if (features[prior].kind == input.kind) {
                result.status = CorrelationProposalStatus::DuplicateFeature;
                return result;
            }
        }
        if (!targetOwnsEvidence(*target, input.targetEvidence) ||
            !evidenceLookup_.containsExact(input.targetEvidence)) {
            result.status =
                CorrelationProposalStatus::FeatureEvidenceMissing;
            return result;
        }
        auto& output = proposal.features[index];
        output.kind = input.kind;
        output.strengthPermille = input.strengthPermille;
        output.maximumPoints = maximum;
        output.awardedPoints = static_cast<std::uint16_t>(
            (static_cast<std::uint32_t>(maximum) *
             input.strengthPermille) / 1000U);
        output.targetEvidence = input.targetEvidence;
        score = static_cast<std::uint16_t>(score + output.awardedPoints);
    }
    proposal.scorePermille = score;
    proposal.confidence = stale ? CorrelationConfidence::Stale
        : score >= 650 ? CorrelationConfidence::High
        : score >= 350 ? CorrelationConfidence::Medium
                       : CorrelationConfidence::Low;
    const CorrelationDecisionRecord* prior = decisions_.findById(proposal.id);
    if (prior != nullptr) {
        if (!domain::targets::correlationProposalKeyEqual(
                prior->proposal, proposal)) {
            result.status = CorrelationProposalStatus::ProposalIdConflict;
            return result;
        }
        result.proposal = prior->proposal;
        result.status = prior->decision == CorrelationDecision::Accept
            ? CorrelationProposalStatus::PreviouslyAccepted
            : CorrelationProposalStatus::PreviouslyRejected;
        return result;
    }
    result.status = CorrelationProposalStatus::Proposed;
    result.proposal = proposal;
    return result;
}

CorrelationActionResult CorrelationService::execute(
    const CorrelationAction& action) {
    CorrelationActionResult result{};
    result.kind = action.kind;
    result.proposalId = action.proposal.id;
    if (action.schemaVersion != kCorrelationActionSchemaVersion ||
        correlationActionDescriptor(action.kind) == nullptr ||
        !domain::targets::correlationProposalValid(action.proposal)) {
        return result;
    }
    const CorrelationDecision decision =
        action.kind == CorrelationActionKind::Accept
            ? CorrelationDecision::Accept : CorrelationDecision::Reject;
    const CorrelationDecisionRecord* existing =
        decisions_.findById(action.proposal.id);
    if (existing != nullptr) {
        if (!domain::targets::correlationProposalKeyEqual(
                existing->proposal, action.proposal)) {
            result.status = CorrelationDecisionStatus::ProposalIdConflict;
            return result;
        }
        result.status = existing->decision == decision
            ? CorrelationDecisionStatus::Unchanged
            : CorrelationDecisionStatus::DecisionConflict;
        result.targetRevision = existing->targetRevisionAfter;
        return result;
    }
    domain::targets::TargetRecord const* target =
        catalog_.find(action.proposal.targetId);
    if (target == nullptr || target->revision != action.expectedTargetRevision) {
        result.status = CorrelationDecisionStatus::TargetChanged;
        return result;
    }
    if (decision == CorrelationDecision::Accept &&
        target->revision == UINT32_MAX) {
        result.status = CorrelationDecisionStatus::TargetChanged;
        return result;
    }
    if (!evidenceLookup_.containsExact(action.proposal.candidateEvidence)) {
        result.status = CorrelationDecisionStatus::EvidenceUnavailable;
        return result;
    }
    for (std::size_t index = 0; index < action.proposal.featureCount; ++index) {
        if (!targetOwnsEvidence(*target,
                action.proposal.features[index].targetEvidence) ||
            !evidenceLookup_.containsExact(
                action.proposal.features[index].targetEvidence)) {
            result.status = CorrelationDecisionStatus::EvidenceUnavailable;
            return result;
        }
    }
    if (!decisions_.canRecord(action.proposal, decision)) {
        result.status = CorrelationDecisionStatus::LogFull;
        return result;
    }

    const std::uint32_t revisionBefore = target->revision;
    std::uint32_t revisionAfter = revisionBefore;
    if (decision == CorrelationDecision::Accept) {
        result.status = mutationStatus(catalog_.attachEvidence(
            action.proposal.targetId, action.proposal.candidateIdentity,
            action.proposal.candidateEvidence));
        if (result.status != CorrelationDecisionStatus::Accepted) return result;
        target = catalog_.find(action.proposal.targetId);
        revisionAfter = target == nullptr ? 0 : target->revision;
    }
    result.status = decisions_.record(action.proposal, decision,
                                      revisionBefore, revisionAfter);
    result.targetRevision = revisionAfter;
    return result;
}

}  // namespace leshy1::services::targets
