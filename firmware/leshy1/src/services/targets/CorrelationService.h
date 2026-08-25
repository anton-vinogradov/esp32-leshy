#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/targets/Correlation.h"
#include "domain/targets/TargetCatalog.h"
#include "kernel/runtime/Resources.h"

namespace leshy1::services::targets {

constexpr std::uint16_t kCorrelationActionSchemaVersion = 1;
constexpr std::uint16_t kCorrelationActionResultSchemaVersion = 1;

struct CorrelationFeatureInput final {
    domain::targets::CorrelationFeatureKind kind =
        domain::targets::CorrelationFeatureKind::AssignedVendorMatch;
    std::uint16_t strengthPermille = 0;
    domain::targets::TargetEvidenceRef targetEvidence{};
};

// Correlation may only explain a link with immutable source facts that can be
// opened at review time. Runtime/storage adapters implement this boundary over
// the retained Session store; tests use an exact in-memory index.
class CorrelationEvidenceLookup {
public:
    virtual ~CorrelationEvidenceLookup() = default;
    virtual bool containsExact(
        const domain::targets::TargetEvidenceRef& evidence) const = 0;
};

enum class CorrelationProposalStatus : std::uint8_t {
    Proposed,
    InvalidArgument,
    TargetNotFound,
    ExistingIdentity,
    IdentityConflict,
    EvidenceConflict,
    CandidateEvidenceMissing,
    UnsupportedFeature,
    DuplicateFeature,
    FeatureEvidenceMissing,
    ProposalIdConflict,
    PreviouslyAccepted,
    PreviouslyRejected,
};

const char* correlationProposalStatusName(CorrelationProposalStatus status);

struct CorrelationProposalResult final {
    CorrelationProposalStatus status =
        CorrelationProposalStatus::InvalidArgument;
    domain::targets::CorrelationProposal proposal{};

    bool proposed() const {
        return status == CorrelationProposalStatus::Proposed;
    }
};

enum class CorrelationDecision : std::uint8_t {
    Accept = 1,
    Reject = 2,
};

struct CorrelationDecisionRecord final {
    domain::targets::CorrelationProposal proposal{};
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
        const domain::targets::CorrelationProposalId& id) const;
    const CorrelationDecisionRecord* find(
        const domain::targets::CorrelationProposal& proposal) const;
    bool canRecord(const domain::targets::CorrelationProposal& proposal,
                   CorrelationDecision decision) const;
    CorrelationDecisionStatus record(
        const domain::targets::CorrelationProposal& proposal,
        CorrelationDecision decision, std::uint32_t revisionBefore,
        std::uint32_t revisionAfter);

private:
    std::array<CorrelationDecisionRecord, kCapacity> records_{};
    std::size_t size_ = 0;
};

enum class CorrelationActionKind : std::uint8_t {
    Accept = 1,
    Reject = 2,
};

struct CorrelationActionDescriptor final {
    const char* id = nullptr;
    std::uint16_t requestSchemaVersion = 0;
    std::uint16_t resultSchemaVersion = 0;
    const char* requiredCapability = nullptr;
    const char* requiredPermission = nullptr;
    kernel::runtime::ResourceMask requiredResources = 0;
    std::uint16_t timeoutMs = 0;
    bool cancellable = false;
};

const CorrelationActionDescriptor* correlationActionDescriptor(
    CorrelationActionKind kind);

struct CorrelationAction final {
    std::uint16_t schemaVersion = kCorrelationActionSchemaVersion;
    CorrelationActionKind kind = CorrelationActionKind::Accept;
    domain::targets::CorrelationProposal proposal{};
    // Optimistic revision prevents accepting a proposal after the Target has
    // changed under the review screen or companion client.
    std::uint32_t expectedTargetRevision = 0;
};

struct CorrelationActionResult final {
    std::uint16_t schemaVersion = kCorrelationActionResultSchemaVersion;
    CorrelationActionKind kind = CorrelationActionKind::Accept;
    CorrelationDecisionStatus status =
        CorrelationDecisionStatus::InvalidArgument;
    domain::targets::CorrelationProposalId proposalId{};
    std::uint32_t targetRevision = 0;
};

class CorrelationService final {
public:
    CorrelationService(domain::targets::TargetCatalog& catalog,
                       CorrelationDecisionLog& decisions,
                       const CorrelationEvidenceLookup& evidenceLookup)
        : catalog_(catalog), decisions_(decisions),
          evidenceLookup_(evidenceLookup) {}

    CorrelationProposalResult propose(
        const domain::targets::TargetId& targetId,
        const domain::targets::TargetIdentity& candidateIdentity,
        const domain::targets::TargetEvidenceRef& candidateEvidence,
        const CorrelationFeatureInput* features, std::size_t featureCount,
        bool stale) const;
    CorrelationActionResult execute(const CorrelationAction& action);

private:
    domain::targets::TargetCatalog& catalog_;
    CorrelationDecisionLog& decisions_;
    const CorrelationEvidenceLookup& evidenceLookup_;
};

}  // namespace leshy1::services::targets
