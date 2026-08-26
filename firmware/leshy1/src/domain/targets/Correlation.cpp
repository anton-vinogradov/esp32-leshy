#include "Correlation.h"

#include <cstring>

namespace leshy1::domain::targets {
namespace {

constexpr std::array<std::uint32_t, 4> kHashSeeds{{
    0x811c9dc5U, 0x9e3779b9U, 0x85ebca6bU, 0xc2b2ae35U,
}};

void mixByte(std::array<std::uint32_t, 4>* lanes, std::uint8_t value) {
    for (std::size_t index = 0; index < lanes->size(); ++index) {
        (*lanes)[index] ^= static_cast<std::uint32_t>(
            value + static_cast<std::uint8_t>(index * 0x3dU));
        (*lanes)[index] *= 0x01000193U;
        (*lanes)[index] ^= (*lanes)[index] >> (13U + index);
    }
}

template <std::size_t Capacity>
void mixBytes(std::array<std::uint32_t, 4>* lanes,
              const std::array<std::uint8_t, Capacity>& bytes) {
    for (const std::uint8_t value : bytes) mixByte(lanes, value);
}

void mix32(std::array<std::uint32_t, 4>* lanes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        mixByte(lanes, static_cast<std::uint8_t>(value >> shift));
    }
}

void mix64(std::array<std::uint32_t, 4>* lanes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        mixByte(lanes, static_cast<std::uint8_t>(value >> shift));
    }
}

}  // namespace

bool correlationProposalIdValid(const CorrelationProposalId& id) {
    for (const std::uint8_t value : id.bytes) {
        if (value != 0) return true;
    }
    return false;
}

bool correlationProposalIdEqual(const CorrelationProposalId& left,
                                const CorrelationProposalId& right) {
    return left.bytes == right.bytes;
}

CorrelationProposalId makeCorrelationProposalId(
    const TargetId& targetId, const TargetIdentity& candidateIdentity,
    const TargetEvidenceRef& candidateEvidence) {
    std::array<std::uint32_t, 4> lanes = kHashSeeds;
    mixBytes(&lanes, targetId.bytes);
    mixByte(&lanes, static_cast<std::uint8_t>(candidateIdentity.kind));
    mixByte(&lanes, candidateIdentity.length);
    mixBytes(&lanes, candidateIdentity.value);
    mixByte(&lanes, candidateIdentity.discriminator);
    mixBytes(&lanes, candidateEvidence.sourceId.bytes);
    mix32(&lanes, candidateEvidence.sourceGeneration);
    mix64(&lanes, candidateEvidence.observationSequence);
    mix64(&lanes, candidateEvidence.observedMonotonicUs);

    CorrelationProposalId result{};
    for (std::size_t lane = 0; lane < lanes.size(); ++lane) {
        const std::uint32_t value = lanes[lane];
        for (std::size_t byte = 0; byte < 4; ++byte) {
            result.bytes[lane * 4U + byte] = static_cast<std::uint8_t>(
                value >> ((3U - byte) * 8U));
        }
    }
    return result;
}

bool correlationProposalKeyEqual(const CorrelationProposal& left,
                                 const CorrelationProposal& right) {
    return targetIdEqual(left.targetId, right.targetId) &&
        targetIdentityEqual(left.candidateIdentity,
                            right.candidateIdentity) &&
        targetEvidenceEqual(left.candidateEvidence,
                            right.candidateEvidence);
}

bool correlationProposalValid(const CorrelationProposal& proposal) {
    if (!correlationProposalIdValid(proposal.id) ||
        !targetIdValid(proposal.targetId) ||
        !targetIdentityValid(proposal.candidateIdentity) ||
        !targetEvidenceValid(proposal.candidateEvidence) ||
        proposal.featureCount == 0 ||
        proposal.featureCount > proposal.features.size() ||
        proposal.scorePermille > 1000 ||
        !correlationProposalIdEqual(
            proposal.id, makeCorrelationProposalId(
                proposal.targetId, proposal.candidateIdentity,
                proposal.candidateEvidence))) {
        return false;
    }
    std::uint16_t score = 0;
    for (std::size_t index = 0; index < proposal.featureCount; ++index) {
        const CorrelationFeature& feature = proposal.features[index];
        const std::uint16_t maximum =
            correlationFeatureMaximumPoints(feature.kind);
        if (maximum == 0 || feature.maximumPoints != maximum ||
            feature.strengthPermille == 0 ||
            feature.strengthPermille > 1000 ||
            feature.awardedPoints != static_cast<std::uint16_t>(
                (static_cast<std::uint32_t>(maximum) *
                 feature.strengthPermille) / 1000U) ||
            !targetEvidenceValid(feature.targetEvidence)) {
            return false;
        }
        score = static_cast<std::uint16_t>(score + feature.awardedPoints);
        for (std::size_t prior = 0; prior < index; ++prior) {
            if (proposal.features[prior].kind == feature.kind) return false;
        }
    }
    if (score != proposal.scorePermille) return false;
    const CorrelationConfidence expected = proposal.stale
        ? CorrelationConfidence::Stale
        : score >= 650 ? CorrelationConfidence::High
        : score >= 350 ? CorrelationConfidence::Medium
                       : CorrelationConfidence::Low;
    return proposal.confidence == expected;
}

const char* correlationDecisionStatusName(CorrelationDecisionStatus status) {
    switch (status) {
        case CorrelationDecisionStatus::Accepted: return "accepted";
        case CorrelationDecisionStatus::Rejected: return "rejected";
        case CorrelationDecisionStatus::Unchanged: return "unchanged";
        case CorrelationDecisionStatus::InvalidArgument:
            return "invalid_argument";
        case CorrelationDecisionStatus::TargetChanged:
            return "target_changed";
        case CorrelationDecisionStatus::IdentityConflict:
            return "identity_conflict";
        case CorrelationDecisionStatus::EvidenceConflict:
            return "evidence_conflict";
        case CorrelationDecisionStatus::EvidenceUnavailable:
            return "evidence_unavailable";
        case CorrelationDecisionStatus::LogFull: return "log_full";
        case CorrelationDecisionStatus::ProposalIdConflict:
            return "proposal_id_conflict";
        case CorrelationDecisionStatus::DecisionConflict:
            return "decision_conflict";
    }
    return "invalid_argument";
}

void CorrelationDecisionLog::clear() {
    std::memset(static_cast<void*>(records_.data()), 0, sizeof(records_));
    size_ = 0;
}

const CorrelationDecisionRecord* CorrelationDecisionLog::get(
    std::size_t index) const {
    return index < size_ ? &records_[index] : nullptr;
}

const CorrelationDecisionRecord* CorrelationDecisionLog::findById(
    const CorrelationProposalId& id) const {
    for (std::size_t index = 0; index < size_; ++index) {
        if (correlationProposalIdEqual(records_[index].proposal.id, id)) {
            return &records_[index];
        }
    }
    return nullptr;
}

const CorrelationDecisionRecord* CorrelationDecisionLog::find(
    const CorrelationProposal& proposal) const {
    const CorrelationDecisionRecord* byId = findById(proposal.id);
    return byId != nullptr && correlationProposalKeyEqual(
        byId->proposal, proposal) ? byId : nullptr;
}

bool CorrelationDecisionLog::canRecord(
    const CorrelationProposal& proposal, CorrelationDecision decision) const {
    if (!correlationProposalValid(proposal) ||
        (decision != CorrelationDecision::Accept &&
         decision != CorrelationDecision::Reject)) {
        return false;
    }
    const CorrelationDecisionRecord* byId = findById(proposal.id);
    if (byId != nullptr) {
        return correlationProposalKeyEqual(byId->proposal, proposal) &&
               byId->decision == decision;
    }
    return size_ < records_.size();
}

CorrelationDecisionStatus CorrelationDecisionLog::record(
    const CorrelationProposal& proposal, CorrelationDecision decision,
    std::uint32_t revisionBefore, std::uint32_t revisionAfter) {
    if (!correlationProposalValid(proposal) || revisionBefore == 0 ||
        revisionAfter == 0 ||
        (decision != CorrelationDecision::Accept &&
         decision != CorrelationDecision::Reject) ||
        (decision == CorrelationDecision::Accept &&
         (revisionBefore == UINT32_MAX ||
          revisionAfter != revisionBefore + 1U)) ||
        (decision == CorrelationDecision::Reject &&
         revisionAfter != revisionBefore)) {
        return CorrelationDecisionStatus::InvalidArgument;
    }
    const CorrelationDecisionRecord* byId = findById(proposal.id);
    if (byId != nullptr) {
        if (!correlationProposalKeyEqual(byId->proposal, proposal)) {
            return CorrelationDecisionStatus::ProposalIdConflict;
        }
        return byId->decision == decision
            ? CorrelationDecisionStatus::Unchanged
            : CorrelationDecisionStatus::DecisionConflict;
    }
    if (size_ >= records_.size()) return CorrelationDecisionStatus::LogFull;
    records_[size_++] = {proposal, decision, revisionBefore, revisionAfter};
    return decision == CorrelationDecision::Accept
        ? CorrelationDecisionStatus::Accepted
        : CorrelationDecisionStatus::Rejected;
}

std::uint16_t correlationFeatureMaximumPoints(CorrelationFeatureKind kind) {
    switch (kind) {
        case CorrelationFeatureKind::AssignedVendorMatch: return 180;
        case CorrelationFeatureKind::AdvertisedNameMatch: return 260;
        case CorrelationFeatureKind::CoOccurrencePattern: return 200;
        case CorrelationFeatureKind::ChannelPatternMatch: return 140;
        case CorrelationFeatureKind::SignalTrendMatch: return 220;
    }
    return 0;
}

}  // namespace leshy1::domain::targets
