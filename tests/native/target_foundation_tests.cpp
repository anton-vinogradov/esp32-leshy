#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "domain/targets/TargetCatalog.h"
#include "services/targets/ObservationTargetAdapter.h"
#include "services/targets/TargetService.h"
#include "storage/SessionStoreBoundary.h"
#include "storage/TargetCodec.h"
#include "storage/TargetStore.h"

using namespace leshy1::domain::targets;
using namespace leshy1::services::targets;
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
    id.bytes[id.bytes.size() - 1U] = suffix;
    return id;
}

SourceId sourceId(std::uint8_t suffix) {
    SourceId id{};
    id.bytes[0] = 0x53;
    id.bytes[1] = 0x36;
    id.bytes[id.bytes.size() - 1U] = suffix;
    return id;
}

TargetIdentity wifiIdentity(std::uint8_t suffix,
                            TargetIdentityKind kind =
                                TargetIdentityKind::WifiBssid) {
    TargetIdentity identity{};
    identity.kind = kind;
    identity.length = identity.value.size();
    identity.value = {0x02, 0x11, 0x22, 0x33, 0x44, suffix};
    return identity;
}

TargetIdentity bleIdentity(std::uint8_t suffix, std::uint8_t addressType) {
    TargetIdentity identity{};
    identity.kind = TargetIdentityKind::BleAddress;
    identity.length = identity.value.size();
    identity.value = {0xc0, 0xde, 0x22, 0x33, 0x44, suffix};
    identity.discriminator = addressType;
    return identity;
}

TargetEvidenceRef evidence(std::uint8_t source, std::uint32_t generation,
                           std::uint64_t sequence) {
    TargetEvidenceRef reference{};
    reference.sourceId = sourceId(source);
    reference.sourceGeneration = generation;
    reference.observationSequence = sequence;
    reference.observedMonotonicUs = 1000U + sequence;
    return reference;
}

class FakeTargetStoreIo final : public SessionStoreIo {
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
        std::memcpy(output, found->second.data(), found->second.size());
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
        found->second[offset] ^= 0x80U;
        working_ = durable_;
        return true;
    }

    std::size_t durableFileCount() const { return durable_.size(); }

private:
    std::map<std::string, std::vector<std::uint8_t>> working_{};
    std::map<std::string, std::vector<std::uint8_t>> durable_{};
    std::string syncedPath_{};
};

void testTargetOwnsExactIdentitiesAndImmutableEvidence() {
    TargetCatalog catalog;
    const TargetId first = targetId(1);
    const TargetIdentity wifi = wifiIdentity(1);
    const TargetEvidenceRef wifiEvidence = evidence(1, 20, 1);
    CHECK(catalog.create(first, wifi, wifiEvidence) ==
          TargetMutationStatus::Created);
    CHECK(catalog.size() == 1);
    CHECK(catalog.find(first) != nullptr);
    CHECK(catalog.findByIdentity(wifi) == catalog.find(first));
    CHECK(catalog.findByEvidence(wifiEvidence) == catalog.find(first));

    const TargetIdentity ble = bleIdentity(2, 1);
    const TargetEvidenceRef bleEvidence = evidence(2, 21, 3);
    CHECK(catalog.attachEvidence(first, ble, bleEvidence) ==
          TargetMutationStatus::Applied);
    const TargetRecord* record = catalog.find(first);
    CHECK(record != nullptr);
    CHECK(record->identityCount == 2);
    CHECK(record->evidenceCount == 2);
    CHECK(record->revision == 2);
    CHECK(targetEvidenceEqual(record->evidence[0], wifiEvidence));
    CHECK(targetEvidenceEqual(record->evidence[1], bleEvidence));

    CHECK(catalog.attachEvidence(first, ble, bleEvidence) ==
          TargetMutationStatus::Unchanged);
    CHECK(catalog.find(first)->revision == 2);
    CHECK(catalog.create(targetId(2), wifi, evidence(3, 22, 1)) ==
          TargetMutationStatus::IdentityConflict);
    CHECK(catalog.create(targetId(2), wifiIdentity(9), wifiEvidence) ==
          TargetMutationStatus::EvidenceConflict);
    TargetEvidenceRef alteredEvidence = wifiEvidence;
    alteredEvidence.observedMonotonicUs += 1;
    CHECK(catalog.attachEvidence(first, wifi, alteredEvidence) ==
          TargetMutationStatus::EvidenceConflict);
    CHECK(catalog.size() == 1);
}

void testTargetMetadataIsBoundedIdempotentAndUnicodeSafe() {
    TargetCatalog catalog;
    const TargetId id = targetId(3);
    CHECK(catalog.create(id, wifiIdentity(3), evidence(3, 30, 1)) ==
          TargetMutationStatus::Created);

    const char name[] = "Домашний роутер";
    CHECK(catalog.setName(id, name, std::strlen(name)) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.setName(id, name, std::strlen(name)) ==
          TargetMutationStatus::Unchanged);
    const char notes[] = "Замечен у окна; проверить во второй Survey";
    CHECK(catalog.setNotes(id, notes, std::strlen(notes)) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.addTag(id, "дом", std::strlen("дом")) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.addTag(id, "дом", std::strlen("дом")) ==
          TargetMutationStatus::Unchanged);
    CHECK(catalog.setFavorite(id, true) == TargetMutationStatus::Applied);
    CHECK(catalog.setFavorite(id, true) == TargetMutationStatus::Unchanged);

    const TargetRecord* record = catalog.find(id);
    CHECK(record != nullptr);
    CHECK(std::strcmp(record->name.data(), name) == 0);
    CHECK(std::strcmp(record->notes.data(), notes) == 0);
    CHECK(record->tagCount == 1);
    CHECK(record->favorite);
    CHECK(record->revision == 5);
    CHECK(catalog.removeTag(id, "дом", std::strlen("дом")) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.removeTag(id, "дом", std::strlen("дом")) ==
          TargetMutationStatus::Unchanged);

    std::array<char, TargetRecord::kNameCapacity + 2U> tooLong{};
    tooLong.fill('x');
    tooLong.back() = '\0';
    const std::uint32_t revision = catalog.find(id)->revision;
    CHECK(catalog.setName(id, tooLong.data(), tooLong.size() - 1U) ==
          TargetMutationStatus::TextTooLong);
    CHECK(catalog.find(id)->revision == revision);

    const std::array<char, 3> exactBytes{{'A', 'P', '1'}};
    CHECK(catalog.setName(id, exactBytes.data(), exactBytes.size()) ==
          TargetMutationStatus::Applied);

    const char malformedUtf8[] = {static_cast<char>(0xc0),
                                  static_cast<char>(0xaf), '\0'};
    CHECK(catalog.setName(id, malformedUtf8, 2) ==
          TargetMutationStatus::InvalidArgument);
    CHECK(catalog.find(id)->revision == revision + 1U);
}

void testTargetBoundsKeepRecentEvidenceWithoutPartialIdentityAttachment() {
    TargetCatalog catalog;
    const TargetId id = targetId(4);
    const TargetIdentity identity = wifiIdentity(4);
    CHECK(catalog.create(id, identity, evidence(4, 40, 1)) ==
          TargetMutationStatus::Created);
    for (std::size_t index = 1;
         index < TargetRecord::kEvidenceCapacity; ++index) {
        CHECK(catalog.attachEvidence(
                  id, identity, evidence(4, 40, index + 1U)) ==
              TargetMutationStatus::Applied);
    }
    const TargetRecord* before = catalog.find(id);
    CHECK(before != nullptr);
    CHECK(before->evidenceCount == TargetRecord::kEvidenceCapacity);
    const std::uint8_t identityCount = before->identityCount;
    const std::uint32_t revision = before->revision;
    const TargetEvidenceRef previousOldest = before->evidence[0];
    const TargetEvidenceRef previousNewest =
        before->evidence[TargetRecord::kEvidenceCapacity - 1U];
    const TargetEvidenceRef nextEvidence = evidence(5, 41, 1);
    CHECK(catalog.attachEvidence(
              id, bleIdentity(8, 0), nextEvidence) ==
          TargetMutationStatus::Applied);
    const TargetRecord* after = catalog.find(id);
    CHECK(after->identityCount == identityCount + 1U);
    CHECK(after->revision == revision + 1U);
    CHECK(after->evidenceCount == TargetRecord::kEvidenceCapacity);
    CHECK(targetEvidenceEqual(after->evidence[0], evidence(4, 40, 2)));
    CHECK(targetEvidenceEqual(
        after->evidence[TargetRecord::kEvidenceCapacity - 2U],
        previousNewest));
    CHECK(targetEvidenceEqual(
        after->evidence[TargetRecord::kEvidenceCapacity - 1U],
        nextEvidence));
    CHECK(catalog.findByEvidence(previousOldest) == nullptr);
    CHECK(catalog.findByEvidence(nextEvidence) == after);
    CHECK(catalog.findByIdentity(bleIdentity(8, 0)) == after);
}

void testTypedTargetActionsHaveOneStableMutationBoundary() {
    const std::array<const char*, 7> expectedIds{{
        "target.create", "target.evidence.attach", "target.name.set",
        "target.notes.set", "target.tag.add", "target.tag.remove",
        "target.favorite.set",
    }};
    for (std::size_t index = 0; index < expectedIds.size(); ++index) {
        const auto kind = static_cast<TargetActionKind>(index + 1U);
        const TargetActionDescriptor* descriptor = targetActionDescriptor(kind);
        CHECK(descriptor != nullptr);
        CHECK(std::strcmp(descriptor->id, expectedIds[index]) == 0);
        CHECK(descriptor->requestSchemaVersion == 1);
        CHECK(descriptor->resultSchemaVersion == 1);
        CHECK(descriptor->requiredResources ==
              leshy1::kernel::runtime::resourceMask(
                  leshy1::kernel::runtime::Resource::Storage));
        CHECK(!descriptor->cancellable);
    }
    CHECK(targetActionDescriptor(static_cast<TargetActionKind>(0)) == nullptr);
    CHECK(targetActionDescriptor(static_cast<TargetActionKind>(8)) == nullptr);

    TargetCatalog catalog;
    TargetService service(catalog);
    TargetAction create{};
    create.targetId = targetId(5);
    create.identity = wifiIdentity(5);
    create.evidence = evidence(5, 50, 1);
    TargetActionResult result = service.execute(create);
    CHECK(result.applied());
    CHECK(result.status == TargetMutationStatus::Created);
    CHECK(result.revision == 1);

    TargetAction rename{};
    rename.kind = TargetActionKind::SetName;
    rename.targetId = create.targetId;
    rename.expectedRevision = 1;
    CHECK(setTargetActionText(&rename, "Office AP", std::strlen("Office AP")));
    result = service.execute(rename);
    CHECK(result.applied());
    CHECK(result.revision == 2);
    CHECK(std::strcmp(catalog.find(create.targetId)->name.data(), "Office AP") == 0);

    rename.expectedRevision = 1;
    result = service.execute(rename);
    CHECK(result.status == TargetMutationStatus::RevisionConflict);
    CHECK(result.revision == 2);

    rename.expectedRevision = 2;
    rename.schemaVersion = 2;
    result = service.execute(rename);
    CHECK(result.status == TargetMutationStatus::InvalidArgument);
    CHECK(result.revision == 0);
    CHECK(catalog.find(create.targetId)->revision == 2);
}

void testTargetWorkingSetHasAnExplicitNoEvictionBound() {
    TargetCatalog catalog;
    for (std::size_t index = 0; index < TargetCatalog::kCapacity; ++index) {
        CHECK(catalog.create(
                  targetId(static_cast<std::uint8_t>(index + 1U)),
                  wifiIdentity(static_cast<std::uint8_t>(index + 1U)),
                  evidence(static_cast<std::uint8_t>(index + 1U),
                           static_cast<std::uint32_t>(100U + index), 1)) ==
              TargetMutationStatus::Created);
    }
    CHECK(catalog.create(targetId(99), wifiIdentity(99),
                         evidence(99, 999, 1)) ==
          TargetMutationStatus::CatalogFull);
    CHECK(catalog.size() == TargetCatalog::kCapacity);
    CHECK(sizeof(TargetCatalog) <= 16U * 1024U);
}

void testObservationAdmissionKeepsExactSourceEvidence() {
    leshy1::domain::observations::Observation observation{};
    observation.sequence = 44;
    observation.monotonicUs = 123456;
    observation.radio = leshy1::domain::observations::RadioKind::Wifi;
    observation.identity = {0x02, 0x10, 0x20, 0x30, 0x40, 0x50};
    observation.identityLength = observation.identity.size();
    const SourceId source = sourceId(7);
    ObservationTargetAdmission admitted =
        admitObservationToTarget(source, 9, observation);
    CHECK(admitted.valid());
    CHECK(admitted.identity.kind == TargetIdentityKind::WifiBssid);
    CHECK(admitted.identity.value == observation.identity);
    CHECK(admitted.evidence.sourceId.bytes == source.bytes);
    CHECK(admitted.evidence.sourceGeneration == 9);
    CHECK(admitted.evidence.observationSequence == observation.sequence);
    CHECK(admitted.evidence.observedMonotonicUs == observation.monotonicUs);

    observation.radio = leshy1::domain::observations::RadioKind::Ble;
    admitted = admitObservationToTarget(source, 9, observation);
    CHECK(admitted.status ==
          ObservationTargetStatus::BleAddressTypeUnavailable);
    observation.bleAdvertisement.present = true;
    observation.bleAdvertisement.addressType = 2;
    admitted = admitObservationToTarget(source, 9, observation);
    CHECK(admitted.valid());
    CHECK(admitted.identity.kind == TargetIdentityKind::BleAddress);
    CHECK(admitted.identity.discriminator == 2);

    observation.identityLength = 5;
    admitted = admitObservationToTarget(source, 9, observation);
    CHECK(admitted.status == ObservationTargetStatus::IdentityUnavailable);
}

void testTargetCodecIsDeterministicAndRejectsCorruption() {
    TargetCatalog catalog;
    const TargetId id = targetId(8);
    CHECK(catalog.create(id, wifiIdentity(8), evidence(8, 80, 4)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.setName(id, "Точка", std::strlen("Точка")) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.addTag(id, "важное", std::strlen("важное")) ==
          TargetMutationStatus::Applied);

    std::array<std::uint8_t, kTargetCatalogMaxBytes> first{};
    std::array<std::uint8_t, kTargetCatalogMaxBytes> second{};
    std::array<std::uint8_t, kTargetManifestMaxBytes> manifest{};
    std::size_t firstSize = 0;
    std::size_t secondSize = 0;
    std::size_t manifestSize = 0;
    CHECK(encodeTargetCatalog(catalog, first.data(), first.size(), &firstSize) ==
          TargetCodecStatus::Valid);
    CHECK(encodeTargetCatalog(catalog, second.data(), second.size(),
                              &secondSize) == TargetCodecStatus::Valid);
    CHECK(firstSize == secondSize);
    CHECK(std::memcmp(first.data(), second.data(), firstSize) == 0);
    CHECK(encodeTargetManifest(catalog, first.data(), firstSize,
                               manifest.data(), manifest.size(),
                               &manifestSize) == TargetCodecStatus::Valid);

    TargetCatalog reopened;
    CHECK(reopenTargetCatalog(manifest.data(), manifestSize, first.data(),
                              firstSize, &reopened) == TargetCodecStatus::Valid);
    const TargetRecord* restored = reopened.find(id);
    CHECK(restored != nullptr);
    CHECK(restored->revision == catalog.find(id)->revision);
    CHECK(std::strcmp(restored->name.data(), "Точка") == 0);
    CHECK(restored->evidenceCount == 1);
    CHECK(targetEvidenceEqual(restored->evidence[0], evidence(8, 80, 4)));

    first[firstSize / 2U] ^= 0x01U;
    CHECK(reopenTargetCatalog(manifest.data(), manifestSize, first.data(),
                              firstSize, &reopened) ==
          TargetCodecStatus::ChecksumMismatch);
}

void testTargetStoreRecoversLatestAndFallsBackFromCorruption() {
    char path[kTargetStorePathMax] = {};
    CHECK(formatTargetStorePath(TargetStoreFileKind::Catalog, UINT32_MAX,
                                path, sizeof(path)));
    CHECK(std::strcmp(path, "target-catalog-4294967295.bin") == 0);
    CHECK(std::strchr(path, '/') == nullptr);

    FakeTargetStoreIo io;
    TargetStoreWorkspace workspace;
    TargetCatalog catalog;
    TargetCatalog scratch;
    const TargetId id = targetId(9);
    CHECK(catalog.create(id, wifiIdentity(9), evidence(9, 90, 1)) ==
          TargetMutationStatus::Created);
    TargetStoreCommitResult committed =
        commitNextTargetCatalog(io, workspace, catalog, scratch);
    CHECK(committed.complete());
    CHECK(committed.generation == 1);
    CHECK(committed.publishedSlot == HeadSlot::A);

    CHECK(catalog.setFavorite(id, true) == TargetMutationStatus::Applied);
    committed = commitNextTargetCatalog(io, workspace, catalog, scratch);
    CHECK(committed.complete());
    CHECK(committed.generation == 2);
    CHECK(committed.publishedSlot == HeadSlot::B);

    TargetCatalog recovered;
    TargetStoreRecoveryResult recovery =
        recoverTargetCatalog(io, workspace, &recovered);
    CHECK(recovery.valid());
    CHECK(recovery.generation == 2);
    CHECK(recovered.find(id) != nullptr);
    CHECK(recovered.find(id)->favorite);

    CHECK(io.flipDurableByte("target-catalog-00000002.bin", 0));
    recovery = recoverTargetCatalog(io, workspace, &recovered);
    CHECK(recovery.valid());
    CHECK(recovery.generation == 1);
    CHECK(recovered.find(id) != nullptr);
    CHECK(!recovered.find(id)->favorite);
}

void testTargetStoreCommitBoundariesNeverLosePublishedCatalog() {
    const std::array<CommitStage, 6> boundaries{{
        CommitStage::WritePayloads, CommitStage::SyncPayloads,
        CommitStage::WriteManifest, CommitStage::SyncManifest,
        CommitStage::WriteHead, CommitStage::SyncHead,
    }};
    FakeTargetStoreIo baseline;
    TargetStoreWorkspace baseWorkspace;
    TargetCatalog catalog;
    TargetCatalog scratch;
    const TargetId id = targetId(10);
    CHECK(catalog.create(id, wifiIdentity(10), evidence(10, 100, 1)) ==
          TargetMutationStatus::Created);
    CHECK(commitNextTargetCatalog(baseline, baseWorkspace, catalog, scratch)
              .complete());
    CHECK(catalog.setFavorite(id, true) == TargetMutationStatus::Applied);

    for (const CommitStage boundary : boundaries) {
        FakeTargetStoreIo interrupted = baseline;
        TargetStoreWorkspace workspace;
        TargetCatalog validation;
        SessionStoreBoundaryIo boundaryIo(interrupted, boundary);
        const TargetStoreCommitResult commit = commitNextTargetCatalog(
            boundaryIo, workspace, catalog, validation);
        CHECK(!commit.complete());
        CHECK(boundaryIo.stopped());
        CHECK(boundaryIo.sequenceValid());
        interrupted.crash();

        TargetCatalog recovered;
        const TargetStoreRecoveryResult recovery =
            recoverTargetCatalog(interrupted, workspace, &recovered);
        CHECK(recovery.valid());
        const std::uint32_t expectedGeneration =
            boundary == CommitStage::SyncHead ? 2U : 1U;
        CHECK(recovery.generation == expectedGeneration);
        CHECK(recovered.find(id) != nullptr);
        CHECK(recovered.find(id)->favorite == (expectedGeneration == 2U));
    }

    FakeTargetStoreIo empty;
    TargetStoreWorkspace emptyWorkspace;
    TargetCatalog emptyCatalog;
    TargetCatalog emptyScratch;
    CHECK(commitNextTargetCatalog(empty, emptyWorkspace, emptyCatalog,
                                  emptyScratch).status ==
          TargetStoreStatus::InvalidArgument);
    CHECK(empty.durableFileCount() == 0);
}

}  // namespace

int main() {
    testTargetOwnsExactIdentitiesAndImmutableEvidence();
    testTargetMetadataIsBoundedIdempotentAndUnicodeSafe();
    testTargetBoundsKeepRecentEvidenceWithoutPartialIdentityAttachment();
    testTypedTargetActionsHaveOneStableMutationBoundary();
    testTargetWorkingSetHasAnExplicitNoEvictionBound();
    testObservationAdmissionKeepsExactSourceEvidence();
    testTargetCodecIsDeterministicAndRejectsCorruption();
    testTargetStoreRecoversLatestAndFallsBackFromCorruption();
    testTargetStoreCommitBoundariesNeverLosePublishedCatalog();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "S6 Target foundation and persistence tests passed\n";
    return EXIT_SUCCESS;
}
