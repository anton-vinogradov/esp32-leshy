#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "domain/targets/Correlation.h"
#include "domain/targets/TargetCatalog.h"
#include "storage/SessionStoreBoundary.h"
#include "storage/TargetCodec.h"
#include "storage/TargetStateStore.h"

using namespace leshy1::domain::targets;
using namespace leshy1::storage;

namespace {

int failures = 0;

#define CHECK(expression)                                                                       \
    do {                                                                                        \
        if (!(expression)) {                                                                    \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                         \
        }                                                                                       \
    } while (false)

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
    result.sourceGeneration = 9;
    result.observationSequence = sequence;
    result.observedMonotonicUs = 5000U + sequence;
    return result;
}

CorrelationProposal proposal(
    const TargetId& id, const TargetEvidenceRef& targetEvidence,
    std::uint8_t candidateSuffix) {
    CorrelationProposal result{};
    result.targetId = id;
    result.candidateIdentity = bleIdentity(candidateSuffix);
    result.candidateEvidence =
        evidence(candidateSuffix, 100U + candidateSuffix);
    result.id = makeCorrelationProposalId(
        result.targetId, result.candidateIdentity, result.candidateEvidence);
    result.featureCount = 1;
    result.features[0].kind =
        CorrelationFeatureKind::AssignedVendorMatch;
    result.features[0].strengthPermille = 1000;
    result.features[0].maximumPoints = 180;
    result.features[0].awardedPoints = 180;
    result.features[0].targetEvidence = targetEvidence;
    result.scorePermille = 180;
    result.confidence = CorrelationConfidence::Low;
    return result;
}

class FakeStoreIo final : public SessionStoreIo {
public:
    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override {
        if (path == nullptr || (data == nullptr && size != 0)) return false;
        std::vector<std::uint8_t>& file = working_[path];
        file.clear();
        if (size != 0) file.assign(data, data + size);
        return true;
    }

    ReadStatus readFile(const char* path, std::uint8_t* output,
                        std::size_t capacity,
                        std::size_t* outputSize) override {
        if (path == nullptr || output == nullptr || outputSize == nullptr) {
            return ReadStatus::IoError;
        }
        const auto found = working_.find(path);
        if (found == working_.end()) return ReadStatus::NotFound;
        if (found->second.size() > capacity) return ReadStatus::TooLarge;
        if (!found->second.empty()) {
            std::memcpy(output, found->second.data(), found->second.size());
        }
        *outputSize = found->second.size();
        return ReadStatus::Ok;
    }

    bool syncFile(const char* path) override {
        if (path == nullptr || working_.find(path) == working_.end()) {
            return false;
        }
        syncedPath_ = path;
        return true;
    }

    bool syncDirectory() override {
        if (syncedPath_.empty()) return false;
        durable_[syncedPath_] = working_[syncedPath_];
        syncedPath_.clear();
        return true;
    }

    void crash() {
        working_ = durable_;
        syncedPath_.clear();
    }

    bool flipDurableByte(const char* path, std::size_t offset) {
        const auto found = durable_.find(path);
        if (found == durable_.end() || offset >= found->second.size()) {
            return false;
        }
        found->second[offset] ^= 0x40U;
        working_ = durable_;
        return true;
    }

private:
    std::map<std::string, std::vector<std::uint8_t>> working_{};
    std::map<std::string, std::vector<std::uint8_t>> durable_{};
    std::string syncedPath_{};
};

void prepareGenerationOne(TargetCatalog* catalog,
                          CorrelationDecisionLog* decisions,
                          TargetId* id,
                          TargetEvidenceRef* observed) {
    *id = targetId(1);
    *observed = evidence(1, 1);
    CHECK(catalog->create(*id, wifiIdentity(1), *observed) ==
          TargetMutationStatus::Created);
    const CorrelationProposal rejected = proposal(*id, *observed, 20);
    CHECK(decisions->record(rejected, CorrelationDecision::Reject, 1, 1) ==
          CorrelationDecisionStatus::Rejected);
}

CorrelationProposal advanceToGenerationTwo(
    TargetCatalog* catalog, CorrelationDecisionLog* decisions,
    const TargetId& id, const TargetEvidenceRef& observed) {
    const CorrelationProposal accepted = proposal(id, observed, 21);
    CHECK(catalog->attachEvidence(id, accepted.candidateIdentity,
                                  accepted.candidateEvidence) ==
          TargetMutationStatus::Applied);
    CHECK(decisions->record(accepted, CorrelationDecision::Accept, 1, 2) ==
          CorrelationDecisionStatus::Accepted);
    return accepted;
}

void checkGeneration(const TargetCatalog& catalog,
                     const CorrelationDecisionLog& decisions,
                     std::size_t expectedIdentities,
                     std::size_t expectedDecisions) {
    CHECK(catalog.size() == 1);
    CHECK(catalog.get(0) != nullptr);
    CHECK(catalog.get(0)->identityCount == expectedIdentities);
    CHECK(catalog.get(0)->revision == expectedIdentities);
    CHECK(decisions.size() == expectedDecisions);
}

void testStateCodecIsDeterministicAndBindsDecisionHistory() {
    TargetCatalog catalog;
    CorrelationDecisionLog decisions;
    TargetId id{};
    TargetEvidenceRef observed{};
    prepareGenerationOne(&catalog, &decisions, &id, &observed);
    const CorrelationProposal accepted =
        advanceToGenerationTwo(&catalog, &decisions, id, observed);

    std::array<std::uint8_t, kTargetStateMaxBytes> first{};
    std::array<std::uint8_t, kTargetStateMaxBytes> second{};
    std::array<std::uint8_t, kTargetStateManifestMaxBytes> manifest{};
    std::size_t firstSize = 0;
    std::size_t secondSize = 0;
    std::size_t manifestSize = 0;
    CHECK(encodeTargetState(catalog, decisions, first.data(), first.size(),
                            &firstSize) == TargetCodecStatus::Valid);
    CHECK(encodeTargetState(catalog, decisions, second.data(), second.size(),
                            &secondSize) == TargetCodecStatus::Valid);
    CHECK(firstSize == secondSize);
    CHECK(std::memcmp(first.data(), second.data(), firstSize) == 0);
    CHECK(encodeTargetStateManifest(
              catalog, decisions, first.data(), firstSize, manifest.data(),
              manifest.size(), &manifestSize) == TargetCodecStatus::Valid);

    TargetCatalog reopenedCatalog;
    CorrelationDecisionLog reopenedDecisions;
    CHECK(reopenTargetState(
              manifest.data(), manifestSize, first.data(), firstSize,
              &reopenedCatalog, &reopenedDecisions) == TargetCodecStatus::Valid);
    checkGeneration(reopenedCatalog, reopenedDecisions, 2, 2);
    CHECK(reopenedDecisions.get(0)->decision == CorrelationDecision::Reject);
    CHECK(reopenedDecisions.get(1)->decision == CorrelationDecision::Accept);
    CHECK(correlationProposalKeyEqual(
        reopenedDecisions.get(1)->proposal, accepted));
    CHECK(reopenedDecisions.get(1)->proposal.scorePermille == 180);
    CHECK(targetEvidenceEqual(
        reopenedDecisions.get(1)->proposal.features[0].targetEvidence,
        observed));

    first[firstSize / 2U] ^= 0x01U;
    CHECK(reopenTargetState(
              manifest.data(), manifestSize, first.data(), firstSize,
              &reopenedCatalog, &reopenedDecisions) ==
          TargetCodecStatus::ChecksumMismatch);
    CHECK(reopenedCatalog.size() == 0);
    CHECK(reopenedDecisions.size() == 0);
}

void testStateStoreRecoversOnlyMatchingGraphAndHistory() {
    FakeStoreIo io;
    TargetStateStoreWorkspace workspace;
    TargetCatalog catalog;
    CorrelationDecisionLog decisions;
    TargetCatalog scratchCatalog;
    CorrelationDecisionLog scratchDecisions;
    TargetId id{};
    TargetEvidenceRef observed{};
    prepareGenerationOne(&catalog, &decisions, &id, &observed);
    TargetStateStoreCommitResult commit = commitNextTargetState(
        io, workspace, catalog, decisions, scratchCatalog, scratchDecisions);
    CHECK(commit.complete());
    CHECK(commit.generation == 1);
    CHECK(commit.publishedSlot == HeadSlot::A);

    advanceToGenerationTwo(&catalog, &decisions, id, observed);
    commit = commitNextTargetState(
        io, workspace, catalog, decisions, scratchCatalog, scratchDecisions);
    CHECK(commit.complete());
    CHECK(commit.generation == 2);
    CHECK(commit.publishedSlot == HeadSlot::B);

    TargetCatalog recoveredCatalog;
    CorrelationDecisionLog recoveredDecisions;
    TargetStateStoreRecoveryResult recovery = recoverTargetState(
        io, workspace, &recoveredCatalog, &recoveredDecisions);
    CHECK(recovery.valid());
    CHECK(recovery.generation == 2);
    checkGeneration(recoveredCatalog, recoveredDecisions, 2, 2);

    CHECK(io.flipDurableByte("target-state-00000002.cbor", 0));
    recovery = recoverTargetState(
        io, workspace, &recoveredCatalog, &recoveredDecisions);
    CHECK(recovery.valid());
    CHECK(recovery.generation == 1);
    checkGeneration(recoveredCatalog, recoveredDecisions, 1, 1);
}

void testEveryInterruptedCommitKeepsGraphAndHistoryPaired() {
    const std::array<CommitStage, 6> boundaries{{
        CommitStage::WritePayloads, CommitStage::SyncPayloads,
        CommitStage::WriteManifest, CommitStage::SyncManifest,
        CommitStage::WriteHead, CommitStage::SyncHead,
    }};
    FakeStoreIo baseline;
    TargetStateStoreWorkspace baseWorkspace;
    TargetCatalog generationTwo;
    CorrelationDecisionLog generationTwoDecisions;
    TargetCatalog scratchCatalog;
    CorrelationDecisionLog scratchDecisions;
    TargetId id{};
    TargetEvidenceRef observed{};
    prepareGenerationOne(&generationTwo, &generationTwoDecisions,
                         &id, &observed);
    CHECK(commitNextTargetState(
              baseline, baseWorkspace, generationTwo,
              generationTwoDecisions, scratchCatalog, scratchDecisions)
              .complete());
    advanceToGenerationTwo(&generationTwo, &generationTwoDecisions,
                           id, observed);

    for (const CommitStage boundary : boundaries) {
        FakeStoreIo interrupted = baseline;
        TargetStateStoreWorkspace workspace;
        TargetCatalog validationCatalog;
        CorrelationDecisionLog validationDecisions;
        SessionStoreBoundaryIo boundaryIo(interrupted, boundary);
        const TargetStateStoreCommitResult commit = commitNextTargetState(
            boundaryIo, workspace, generationTwo, generationTwoDecisions,
            validationCatalog, validationDecisions);
        CHECK(!commit.complete());
        CHECK(boundaryIo.stopped());
        CHECK(boundaryIo.sequenceValid());
        interrupted.crash();

        TargetCatalog recoveredCatalog;
        CorrelationDecisionLog recoveredDecisions;
        const TargetStateStoreRecoveryResult recovery = recoverTargetState(
            interrupted, workspace, &recoveredCatalog, &recoveredDecisions);
        CHECK(recovery.valid());
        const std::uint32_t expectedGeneration =
            boundary == CommitStage::SyncHead ? 2U : 1U;
        CHECK(recovery.generation == expectedGeneration);
        checkGeneration(recoveredCatalog, recoveredDecisions,
                        expectedGeneration, expectedGeneration);
    }
}

void testPathsAndAliasingFailClosed() {
    char path[kTargetStateStorePathMax] = {};
    CHECK(formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                     UINT32_MAX, path, sizeof(path)));
    CHECK(std::strcmp(path, "target-state-4294967295.cbor") == 0);
    CHECK(std::strchr(path, '/') == nullptr);

    FakeStoreIo io;
    TargetStateStoreWorkspace workspace;
    TargetCatalog catalog;
    CorrelationDecisionLog decisions;
    TargetId id{};
    TargetEvidenceRef observed{};
    prepareGenerationOne(&catalog, &decisions, &id, &observed);
    CorrelationDecisionLog scratchDecisions;
    CHECK(commitNextTargetState(
              io, workspace, catalog, decisions, catalog, scratchDecisions)
              .status == TargetStateStoreStatus::InvalidArgument);
    TargetCatalog scratchCatalog;
    CHECK(commitNextTargetState(
              io, workspace, catalog, decisions, scratchCatalog, decisions)
              .status == TargetStateStoreStatus::InvalidArgument);
}

}  // namespace

int main() {
    testStateCodecIsDeterministicAndBindsDecisionHistory();
    testStateStoreRecoversOnlyMatchingGraphAndHistory();
    testEveryInterruptedCommitKeepsGraphAndHistoryPaired();
    testPathsAndAliasingFailClosed();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "S6 Target graph/decision atomic persistence tests passed\n";
    return EXIT_SUCCESS;
}
