#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>

#include "domain/targets/TargetCatalog.h"
#include "services/targets/CorrelationService.h"
#include "services/targets/TargetService.h"

using namespace leshy1::domain::targets;
using namespace leshy1::services::targets;

namespace {

int failures = 0;

#define CHECK(expression)                                                                       \
    do {                                                                                        \
        if (!(expression)) {                                                                    \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                         \
        }                                                                                       \
    } while (false)

class FakeEvidenceLookup final : public CorrelationEvidenceLookup {
public:
    static constexpr std::size_t kCapacity = 96;

    void add(const TargetEvidenceRef& evidence) {
        if (size_ < values_.size()) values_[size_++] = evidence;
    }

    void removeExact(const TargetEvidenceRef& evidence) {
        for (std::size_t index = 0; index < size_; ++index) {
            if (!targetEvidenceEqual(values_[index], evidence)) continue;
            for (std::size_t move = index + 1; move < size_; ++move) {
                values_[move - 1U] = values_[move];
            }
            values_[--size_] = {};
            return;
        }
    }

    bool containsExact(const TargetEvidenceRef& evidence) const override {
        for (std::size_t index = 0; index < size_; ++index) {
            if (targetEvidenceEqual(values_[index], evidence)) return true;
        }
        return false;
    }

private:
    std::array<TargetEvidenceRef, kCapacity> values_{};
    std::size_t size_ = 0;
};

TargetId targetId(std::uint8_t suffix) {
    TargetId id{};
    id.bytes[0] = 0x4c;
    id.bytes[1] = 0x53;
    id.bytes.back() = suffix;
    return id;
}

SourceId sourceId(std::uint8_t suffix) {
    SourceId id{};
    id.bytes[0] = 0x53;
    id.bytes[1] = 0x36;
    id.bytes.back() = suffix;
    return id;
}

TargetIdentity wifiIdentity(std::uint8_t suffix) {
    TargetIdentity identity{};
    identity.kind = TargetIdentityKind::WifiBssid;
    identity.length = identity.value.size();
    identity.value = {0x02, 0x11, 0x22, 0x33, 0x44, suffix};
    return identity;
}

TargetIdentity bleIdentity(std::uint8_t suffix) {
    TargetIdentity identity{};
    identity.kind = TargetIdentityKind::BleAddress;
    identity.length = identity.value.size();
    identity.value = {0xc0, 0xde, 0x22, 0x33, 0x44, suffix};
    identity.discriminator = 1;
    return identity;
}

TargetEvidenceRef evidence(std::uint8_t source, std::uint64_t sequence) {
    TargetEvidenceRef result{};
    result.sourceId = sourceId(source);
    result.sourceGeneration = 7;
    result.observationSequence = sequence;
    result.observedMonotonicUs = 1000U + sequence;
    return result;
}

std::array<CorrelationFeatureInput, 3> mediumFeatures(
    const TargetEvidenceRef& targetEvidence) {
    return {{{CorrelationFeatureKind::AssignedVendorMatch, 1000,
              targetEvidence},
             {CorrelationFeatureKind::AdvertisedNameMatch, 1000,
              targetEvidence},
             {CorrelationFeatureKind::CoOccurrencePattern, 500,
              targetEvidence}}};
}

CorrelationProposalResult mediumProposal(
    CorrelationService& service, FakeEvidenceLookup& lookup,
    const TargetId& id,
    const TargetEvidenceRef& targetEvidence, std::uint8_t candidateSuffix,
    bool stale = false) {
    const auto features = mediumFeatures(targetEvidence);
    const TargetEvidenceRef candidate =
        evidence(candidateSuffix, 100U + candidateSuffix);
    lookup.add(candidate);
    return service.propose(id, bleIdentity(candidateSuffix),
                           candidate,
                           features.data(), features.size(), stale);
}

void testProposalIsDeterministicExplainableAndNonMutating() {
    TargetCatalog catalog;
    CorrelationDecisionLog log;
    FakeEvidenceLookup lookup;
    CorrelationService service(catalog, log, lookup);
    const TargetId id = targetId(1);
    const TargetEvidenceRef observed = evidence(1, 1);
    CHECK(catalog.create(id, wifiIdentity(1), observed) ==
          TargetMutationStatus::Created);
    lookup.add(observed);
    const std::uint32_t revision = catalog.find(id)->revision;

    const CorrelationProposalResult first =
        mediumProposal(service, lookup, id, observed, 21);
    const CorrelationProposalResult second =
        mediumProposal(service, lookup, id, observed, 21);
    CHECK(first.status == CorrelationProposalStatus::Proposed);
    CHECK(second.status == CorrelationProposalStatus::Proposed);
    CHECK(correlationProposalIdEqual(first.proposal.id, second.proposal.id));
    CHECK(correlationProposalKeyEqual(first.proposal, second.proposal));
    CHECK(first.proposal.scorePermille == 540);
    CHECK(first.proposal.confidence == CorrelationConfidence::Medium);
    CHECK(first.proposal.featureCount == 3);
    CHECK(first.proposal.features[0].maximumPoints == 180);
    CHECK(first.proposal.features[0].awardedPoints == 180);
    CHECK(first.proposal.features[1].maximumPoints == 260);
    CHECK(first.proposal.features[1].awardedPoints == 260);
    CHECK(first.proposal.features[2].maximumPoints == 200);
    CHECK(first.proposal.features[2].awardedPoints == 100);
    CHECK(catalog.find(id)->revision == revision);
    CHECK(catalog.findByIdentity(bleIdentity(21)) == nullptr);
    CHECK(log.size() == 0);

    CorrelationFeatureInput lowFeature{
        CorrelationFeatureKind::ChannelPatternMatch, 500, observed};
    lookup.add(evidence(22, 122));
    const CorrelationProposalResult low = service.propose(
        id, bleIdentity(22), evidence(22, 122), &lowFeature, 1, false);
    CHECK(low.proposed());
    CHECK(low.proposal.scorePermille == 70);
    CHECK(low.proposal.confidence == CorrelationConfidence::Low);
    const CorrelationProposalResult stale = service.propose(
        id, bleIdentity(22), evidence(22, 122), &lowFeature, 1, true);
    CHECK(stale.proposed());
    CHECK(stale.proposal.confidence == CorrelationConfidence::Stale);
    CHECK(stale.proposal.stale);
    CHECK(catalog.find(id)->revision == revision);
}

void testProposalValidationFailsClosed() {
    TargetCatalog catalog;
    CorrelationDecisionLog log;
    FakeEvidenceLookup lookup;
    CorrelationService service(catalog, log, lookup);
    const TargetId id = targetId(2);
    const TargetEvidenceRef observed = evidence(2, 1);
    CHECK(catalog.create(id, wifiIdentity(2), observed) ==
          TargetMutationStatus::Created);
    lookup.add(observed);
    const std::uint32_t revision = catalog.find(id)->revision;

    std::array<CorrelationFeatureInput, 2> duplicate{{
        {CorrelationFeatureKind::SignalTrendMatch, 1000, observed},
        {CorrelationFeatureKind::SignalTrendMatch, 500, observed},
    }};
    lookup.add(evidence(30, 130));
    CHECK(service.propose(id, bleIdentity(30), evidence(30, 130),
                          duplicate.data(), duplicate.size(), false).status ==
          CorrelationProposalStatus::DuplicateFeature);
    CorrelationFeatureInput missing{
        CorrelationFeatureKind::SignalTrendMatch, 1000, evidence(9, 9)};
    lookup.add(evidence(31, 131));
    CHECK(service.propose(id, bleIdentity(31), evidence(31, 131), &missing, 1,
                          false).status ==
          CorrelationProposalStatus::FeatureEvidenceMissing);
    CorrelationFeatureInput invalid{
        static_cast<CorrelationFeatureKind>(99), 1000, observed};
    lookup.add(evidence(32, 132));
    CHECK(service.propose(id, bleIdentity(32), evidence(32, 132), &invalid, 1,
                          false).status ==
          CorrelationProposalStatus::UnsupportedFeature);
    lookup.add(evidence(33, 133));
    CHECK(service.propose(id, wifiIdentity(2), evidence(33, 133), &missing, 1,
                          false).status ==
          CorrelationProposalStatus::ExistingIdentity);

    const TargetId other = targetId(3);
    const TargetEvidenceRef otherEvidence = evidence(3, 1);
    CHECK(catalog.create(other, wifiIdentity(3), otherEvidence) ==
          TargetMutationStatus::Created);
    lookup.add(otherEvidence);
    CorrelationFeatureInput valid{
        CorrelationFeatureKind::SignalTrendMatch, 1000, observed};
    lookup.add(evidence(34, 134));
    CHECK(service.propose(id, wifiIdentity(3), evidence(34, 134), &valid, 1,
                          false).status ==
          CorrelationProposalStatus::IdentityConflict);
    CHECK(service.propose(id, bleIdentity(34), otherEvidence, &valid, 1,
                          false).status ==
          CorrelationProposalStatus::EvidenceConflict);
    CHECK(service.propose(id, bleIdentity(35), evidence(35, 135), &valid, 1,
                          false).status ==
          CorrelationProposalStatus::CandidateEvidenceMissing);
    CHECK(catalog.find(id)->revision == revision);
    CHECK(log.size() == 0);
}

void testExplicitRejectIsImmutableAndIdempotent() {
    TargetCatalog catalog;
    CorrelationDecisionLog log;
    FakeEvidenceLookup lookup;
    CorrelationService service(catalog, log, lookup);
    const TargetId id = targetId(4);
    const TargetEvidenceRef observed = evidence(4, 1);
    CHECK(catalog.create(id, wifiIdentity(4), observed) ==
          TargetMutationStatus::Created);
    lookup.add(observed);
    const CorrelationProposalResult proposed =
        mediumProposal(service, lookup, id, observed, 40);
    CHECK(proposed.proposed());

    CorrelationAction reject{};
    reject.kind = CorrelationActionKind::Reject;
    reject.proposal = proposed.proposal;
    reject.expectedTargetRevision = catalog.find(id)->revision;
    CorrelationActionResult result = service.execute(reject);
    CHECK(result.status == CorrelationDecisionStatus::Rejected);
    CHECK(result.targetRevision == 1);
    CHECK(catalog.find(id)->revision == 1);
    CHECK(catalog.findByIdentity(bleIdentity(40)) == nullptr);
    CHECK(log.size() == 1);
    CHECK(log.get(0)->targetRevisionBefore == 1);
    CHECK(log.get(0)->targetRevisionAfter == 1);

    reject.expectedTargetRevision = 999;
    result = service.execute(reject);
    CHECK(result.status == CorrelationDecisionStatus::Unchanged);
    CorrelationAction opposite = reject;
    opposite.kind = CorrelationActionKind::Accept;
    result = service.execute(opposite);
    CHECK(result.status == CorrelationDecisionStatus::DecisionConflict);
    CHECK(catalog.find(id)->revision == 1);
    CHECK(mediumProposal(service, lookup, id, observed, 40).status ==
          CorrelationProposalStatus::PreviouslyRejected);
}

void testExplicitAcceptUsesOptimisticRevisionAndAttachesExactEvidence() {
    TargetCatalog catalog;
    CorrelationDecisionLog log;
    FakeEvidenceLookup lookup;
    CorrelationService service(catalog, log, lookup);
    const TargetId id = targetId(5);
    const TargetEvidenceRef observed = evidence(5, 1);
    CHECK(catalog.create(id, wifiIdentity(5), observed) ==
          TargetMutationStatus::Created);
    lookup.add(observed);
    const CorrelationProposalResult proposed =
        mediumProposal(service, lookup, id, observed, 50);
    CHECK(proposed.proposed());

    CorrelationAction accept{};
    accept.kind = CorrelationActionKind::Accept;
    accept.proposal = proposed.proposal;
    accept.expectedTargetRevision = 2;
    CorrelationActionResult result = service.execute(accept);
    CHECK(result.status == CorrelationDecisionStatus::TargetChanged);
    CHECK(catalog.find(id)->revision == 1);
    CHECK(log.size() == 0);

    accept.expectedTargetRevision = 1;
    lookup.removeExact(proposed.proposal.candidateEvidence);
    result = service.execute(accept);
    CHECK(result.status == CorrelationDecisionStatus::EvidenceUnavailable);
    CHECK(catalog.find(id)->revision == 1);
    CHECK(log.size() == 0);
    lookup.add(proposed.proposal.candidateEvidence);
    result = service.execute(accept);
    CHECK(result.status == CorrelationDecisionStatus::Accepted);
    CHECK(result.targetRevision == 2);
    CHECK(catalog.findByIdentity(proposed.proposal.candidateIdentity) ==
          catalog.find(id));
    CHECK(catalog.findByEvidence(proposed.proposal.candidateEvidence) ==
          catalog.find(id));
    CHECK(log.size() == 1);
    CHECK(log.get(0)->targetRevisionBefore == 1);
    CHECK(log.get(0)->targetRevisionAfter == 2);

    result = service.execute(accept);
    CHECK(result.status == CorrelationDecisionStatus::Unchanged);
    CHECK(catalog.find(id)->revision == 2);
    CorrelationAction opposite = accept;
    opposite.kind = CorrelationActionKind::Reject;
    CHECK(service.execute(opposite).status ==
          CorrelationDecisionStatus::DecisionConflict);

    CorrelationAction malformed = accept;
    ++malformed.proposal.scorePermille;
    CHECK(service.execute(malformed).status ==
          CorrelationDecisionStatus::InvalidArgument);
}

void testDecisionLogBoundsAndIdCollisionsFailClosed() {
    TargetCatalog catalog;
    CorrelationDecisionLog log;
    FakeEvidenceLookup lookup;
    CorrelationService service(catalog, log, lookup);
    const TargetId id = targetId(6);
    const TargetEvidenceRef observed = evidence(6, 1);
    CHECK(catalog.create(id, wifiIdentity(6), observed) ==
          TargetMutationStatus::Created);
    lookup.add(observed);
    for (std::size_t index = 0;
         index < CorrelationDecisionLog::kCapacity; ++index) {
        const std::uint8_t suffix = static_cast<std::uint8_t>(80U + index);
        const CorrelationProposalResult proposed =
            mediumProposal(service, lookup, id, observed, suffix);
        CHECK(proposed.proposed());
        CorrelationAction reject{};
        reject.kind = CorrelationActionKind::Reject;
        reject.proposal = proposed.proposal;
        reject.expectedTargetRevision = 1;
        CHECK(service.execute(reject).status ==
              CorrelationDecisionStatus::Rejected);
    }
    CHECK(log.size() == CorrelationDecisionLog::kCapacity);
    const CorrelationProposalResult overflow =
        mediumProposal(service, lookup, id, observed, 120);
    CHECK(overflow.proposed());
    CorrelationAction reject{};
    reject.kind = CorrelationActionKind::Reject;
    reject.proposal = overflow.proposal;
    reject.expectedTargetRevision = 1;
    CHECK(service.execute(reject).status == CorrelationDecisionStatus::LogFull);
    CHECK(catalog.find(id)->revision == 1);

    CorrelationDecisionLog collisionLog;
    CorrelationProposal first = overflow.proposal;
    CHECK(collisionLog.record(first, CorrelationDecision::Reject, 1, 1) ==
          CorrelationDecisionStatus::Rejected);
    CorrelationProposal collision = first;
    collision.candidateIdentity = bleIdentity(121);
    CHECK(!collisionLog.canRecord(collision, CorrelationDecision::Reject));
    CHECK(collisionLog.record(collision, CorrelationDecision::Reject, 1, 1) ==
          CorrelationDecisionStatus::InvalidArgument);
    CHECK(collisionLog.record(first, CorrelationDecision::Accept, 1, 1) ==
          CorrelationDecisionStatus::InvalidArgument);
    CHECK(collisionLog.size() == 1);
    CHECK(sizeof(CorrelationDecisionLog) <= 16U * 1024U);
}

void testActionContractAndLengthBasedTextApi() {
    const CorrelationActionDescriptor* accept =
        correlationActionDescriptor(CorrelationActionKind::Accept);
    const CorrelationActionDescriptor* reject =
        correlationActionDescriptor(CorrelationActionKind::Reject);
    CHECK(accept != nullptr);
    CHECK(reject != nullptr);
    CHECK(std::strcmp(accept->id, "correlation.accept") == 0);
    CHECK(std::strcmp(reject->id, "correlation.reject") == 0);
    CHECK(accept->requestSchemaVersion == 1);
    CHECK(accept->resultSchemaVersion == 1);
    CHECK(accept->requiredResources ==
          leshy1::kernel::runtime::resourceMask(
              leshy1::kernel::runtime::Resource::Storage));
    CHECK(correlationActionDescriptor(
              static_cast<CorrelationActionKind>(0)) == nullptr);
    CHECK(correlationActionDescriptor(
              static_cast<CorrelationActionKind>(3)) == nullptr);

    TargetAction action{};
    const std::array<char, 3> exactBytes{{'A', 'P', '1'}};
    CHECK(setTargetActionText(&action, exactBytes.data(), exactBytes.size()));
    CHECK(action.textLength == exactBytes.size());
    CHECK(std::memcmp(action.text.data(), exactBytes.data(),
                      exactBytes.size()) == 0);
    CHECK(action.text[exactBytes.size()] == '\0');
}

}  // namespace

int main() {
    testProposalIsDeterministicExplainableAndNonMutating();
    testProposalValidationFailsClosed();
    testExplicitRejectIsImmutableAndIdempotent();
    testExplicitAcceptUsesOptimisticRevisionAndAttachesExactEvidence();
    testDecisionLogBoundsAndIdCollisionsFailClosed();
    testActionContractAndLengthBasedTextApi();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "S6 explainable correlation proposal tests passed\n";
    return EXIT_SUCCESS;
}
