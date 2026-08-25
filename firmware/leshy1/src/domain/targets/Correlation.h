#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "Target.h"

namespace leshy1::domain::targets {

struct CorrelationProposalId final {
    static constexpr std::size_t kSize = 16;
    std::array<std::uint8_t, kSize> bytes{};
};

enum class CorrelationFeatureKind : std::uint8_t {
    AssignedVendorMatch = 1,
    AdvertisedNameMatch = 2,
    CoOccurrencePattern = 3,
    ChannelPatternMatch = 4,
    SignalTrendMatch = 5,
};

enum class CorrelationConfidence : std::uint8_t {
    Low,
    Medium,
    High,
    Stale,
};

struct CorrelationFeature final {
    CorrelationFeatureKind kind = CorrelationFeatureKind::AssignedVendorMatch;
    std::uint16_t strengthPermille = 0;
    std::uint16_t maximumPoints = 0;
    std::uint16_t awardedPoints = 0;
    // Every interpreted feature must open at least one immutable observation
    // already owned by the proposed Target.
    TargetEvidenceRef targetEvidence{};
};

struct CorrelationProposal final {
    static constexpr std::size_t kFeatureCapacity = 5;

    CorrelationProposalId id{};
    TargetId targetId{};
    TargetIdentity candidateIdentity{};
    TargetEvidenceRef candidateEvidence{};
    std::array<CorrelationFeature, kFeatureCapacity> features{};
    std::uint8_t featureCount = 0;
    std::uint16_t scorePermille = 0;
    CorrelationConfidence confidence = CorrelationConfidence::Low;
    bool stale = false;
};

enum class CorrelationDecision : std::uint8_t {
    Accept = 1,
    Reject = 2,
};

struct CorrelationDecisionRecord final {
    CorrelationProposal proposal{};
    CorrelationDecision decision = CorrelationDecision::Reject;
    std::uint32_t targetRevisionBefore = 0;
    std::uint32_t targetRevisionAfter = 0;
};

enum class CorrelationDecisionStatus : std::uint8_t {
    Accepted,
    Rejected,
    Unchanged,
    InvalidArgument,
    TargetChanged,
    IdentityConflict,
    EvidenceConflict,
    EvidenceUnavailable,
    LogFull,
    ProposalIdConflict,
    DecisionConflict,
};

const char* correlationDecisionStatusName(CorrelationDecisionStatus status);

class CorrelationDecisionLog final {
public:
    static constexpr std::size_t kCapacity = 32;

    void clear();
    std::size_t size() const { return size_; }
    const CorrelationDecisionRecord* get(std::size_t index) const;
    const CorrelationDecisionRecord* findById(
        const CorrelationProposalId& id) const;
    const CorrelationDecisionRecord* find(
        const CorrelationProposal& proposal) const;
    bool canRecord(const CorrelationProposal& proposal,
                   CorrelationDecision decision) const;
    CorrelationDecisionStatus record(
        const CorrelationProposal& proposal, CorrelationDecision decision,
        std::uint32_t revisionBefore, std::uint32_t revisionAfter);

private:
    std::array<CorrelationDecisionRecord, kCapacity> records_{};
    std::size_t size_ = 0;
};

bool correlationProposalIdValid(const CorrelationProposalId& id);
bool correlationProposalIdEqual(const CorrelationProposalId& left,
                                const CorrelationProposalId& right);
CorrelationProposalId makeCorrelationProposalId(
    const TargetId& targetId, const TargetIdentity& candidateIdentity,
    const TargetEvidenceRef& candidateEvidence);
bool correlationProposalKeyEqual(const CorrelationProposal& left,
                                 const CorrelationProposal& right);
bool correlationProposalValid(const CorrelationProposal& proposal);
std::uint16_t correlationFeatureMaximumPoints(CorrelationFeatureKind kind);

}  // namespace leshy1::domain::targets
