#include <cstdlib>
#include <cstring>
#include <iostream>

#include "domain/targets/TargetMerge.h"
#include "services/targets/TargetMergeService.h"

using namespace leshy1::domain::targets;
using namespace leshy1::services::targets;

namespace {

int failures = 0;

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            std::cerr << __FILE__ << ':' << __LINE__                            \
                      << ": check failed: " #expression << '\n';               \
            ++failures;                                                         \
        }                                                                       \
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

TargetIdentity identity(std::uint8_t suffix) {
    TargetIdentity result{};
    result.kind = suffix % 2U == 0 ? TargetIdentityKind::BleAddress
                                   : TargetIdentityKind::WifiBssid;
    result.length = result.value.size();
    result.value = {0x02, 0x11, 0x22, 0x33, 0x44, suffix};
    result.discriminator = result.kind == TargetIdentityKind::BleAddress ? 1 : 0;
    return result;
}

TargetEvidenceRef evidence(std::uint8_t suffix, std::uint64_t sequence = 1) {
    TargetEvidenceRef result{};
    result.sourceId = sourceId(suffix);
    result.sourceGeneration = 7;
    result.observationSequence = sequence;
    result.observedMonotonicUs = 10000U + suffix * 100U + sequence;
    return result;
}

TargetMergeId operationId(std::uint8_t suffix) {
    TargetMergeId id{};
    id.bytes[0] = 0x4d;
    id.bytes[1] = 0x47;
    id.bytes.back() = suffix;
    return id;
}

bool textEqual(const char* left, std::size_t leftLength,
               const char* right, std::size_t rightLength) {
    return leftLength == rightLength &&
        std::memcmp(left, right, leftLength) == 0;
}

void checkSameGraph(const TargetCatalog& left, const TargetCatalog& right) {
    CHECK(left.size() == right.size());
    for (std::size_t index = 0; index < left.size(); ++index) {
        const TargetRecord* leftRecord = left.get(index);
        const TargetRecord* rightRecord = right.get(index);
        CHECK(leftRecord != nullptr);
        CHECK(rightRecord != nullptr);
        if (leftRecord != nullptr && rightRecord != nullptr) {
            CHECK(targetRecordGraphEqual(*leftRecord, *rightRecord));
        }
    }
}

void checkDescriptors() {
    const TargetMergeActionDescriptor* merge =
        targetMergeActionDescriptor(TargetMergeActionKind::Merge);
    const TargetMergeActionDescriptor* split =
        targetMergeActionDescriptor(TargetMergeActionKind::Split);
    CHECK(merge != nullptr);
    CHECK(split != nullptr);
    CHECK(std::strcmp(merge->id, "target.merge") == 0);
    CHECK(std::strcmp(split->id, "target.split") == 0);
    CHECK(merge->requiredResources == split->requiredResources);
    CHECK(merge->requiredResources != 0);
    CHECK(!merge->cancellable);
    CHECK(!split->cancellable);
    CHECK(targetMergeActionDescriptor(
              static_cast<TargetMergeActionKind>(0)) == nullptr);
}

void checkMergeSplitAndAudit() {
    TargetCatalog catalog;
    CHECK(catalog.create(targetId(1), identity(1), evidence(1)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.create(targetId(2), identity(2), evidence(2)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.create(targetId(3), identity(3), evidence(3)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.create(targetId(4), identity(4), evidence(4)) ==
          TargetMutationStatus::Created);
    const char destinationName[] = "receiver";
    const char sourceName[] = "tracker";
    CHECK(catalog.setName(targetId(3), destinationName,
                          sizeof(destinationName) - 1U) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.setName(targetId(1), sourceName,
                          sizeof(sourceName) - 1U) ==
          TargetMutationStatus::Applied);
    const TargetCatalog before = catalog;
    const std::uint32_t destinationRevision =
        catalog.find(targetId(3))->revision;
    const std::uint32_t sourceRevision = catalog.find(targetId(1))->revision;

    TargetMergeHistory history;
    TargetMergeService service(catalog, history);
    TargetMergeAction merge{};
    merge.kind = TargetMergeActionKind::Merge;
    merge.operationId = operationId(1);
    merge.destinationId = targetId(3);
    merge.sourceId = targetId(1);
    merge.expectedDestinationRevision = destinationRevision;
    merge.expectedSourceRevision = sourceRevision;
    const TargetMergeActionResult merged = service.execute(merge);
    CHECK(merged.status == TargetMergeStatus::Merged);
    CHECK(merged.applied());
    CHECK(merged.destinationRevision == destinationRevision + 1U);
    CHECK(merged.sourceRevision == 0);
    CHECK(catalog.size() == before.size() - 1U);
    CHECK(catalog.find(targetId(1)) == nullptr);
    const TargetRecord* destination = catalog.find(targetId(3));
    CHECK(destination != nullptr);
    CHECK(destination->identityCount == 2);
    CHECK(destination->evidenceCount == 2);
    CHECK(targetIdentityEqual(destination->identities[1], identity(1)));
    CHECK(targetEvidenceEqual(destination->evidence[1], evidence(1)));

    const TargetMergeRecord* audit = history.find(operationId(1));
    CHECK(audit != nullptr);
    CHECK(!audit->split);
    CHECK(audit->sourceIndex == 0);
    CHECK(audit->destinationIndex == 2);
    CHECK(textEqual(audit->sourceBefore.name.data(),
                    audit->sourceBefore.nameLength, sourceName,
                    sizeof(sourceName) - 1U));
    CHECK(textEqual(audit->destinationBefore.name.data(),
                    audit->destinationBefore.nameLength, destinationName,
                    sizeof(destinationName) - 1U));

    CHECK(service.execute(merge).status == TargetMergeStatus::Unchanged);
    TargetMergeAction collision = merge;
    collision.sourceId = targetId(2);
    CHECK(service.execute(collision).status ==
          TargetMergeStatus::OperationIdConflict);
    // An unrelated Target may continue evolving; split must preserve it.
    CHECK(catalog.setFavorite(targetId(4), true) ==
          TargetMutationStatus::Applied);

    TargetMergeAction split{};
    split.kind = TargetMergeActionKind::Split;
    split.operationId = operationId(1);
    const TargetMergeActionResult restored = service.execute(split);
    CHECK(restored.status == TargetMergeStatus::Split);
    CHECK(restored.destinationRevision == destinationRevision + 2U);
    CHECK(restored.sourceRevision == sourceRevision + 1U);
    checkSameGraph(catalog, before);
    CHECK(catalog.find(targetId(4))->favorite);
    CHECK(history.find(operationId(1))->split);
    CHECK(service.execute(split).status == TargetMergeStatus::Unchanged);
    CHECK(service.execute(merge).status == TargetMergeStatus::AlreadySplit);
}

void checkChangedTargetFailsClosed() {
    TargetCatalog catalog;
    CHECK(catalog.create(targetId(1), identity(1), evidence(1)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.create(targetId(2), identity(2), evidence(2)) ==
          TargetMutationStatus::Created);
    TargetMergeHistory history;
    CHECK(history.merge(catalog, operationId(2), targetId(1), targetId(2),
                        1, 1) == TargetMergeStatus::Merged);
    const char edited[] = "edited after merge";
    CHECK(catalog.setNotes(targetId(1), edited, sizeof(edited) - 1U) ==
          TargetMutationStatus::Applied);
    const TargetCatalog beforeSplit = catalog;
    CHECK(history.split(catalog, operationId(2)) ==
          TargetMergeStatus::TargetChanged);
    checkSameGraph(catalog, beforeSplit);
    CHECK(!history.find(operationId(2))->split);
}

void checkBoundsFailWithoutMutation() {
    TargetCatalog catalog;
    CHECK(catalog.create(targetId(1), identity(1), evidence(1)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.attachEvidence(targetId(1), identity(3), evidence(3)) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.attachEvidence(targetId(1), identity(5), evidence(5)) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.attachEvidence(targetId(1), identity(7), evidence(7)) ==
          TargetMutationStatus::Applied);
    CHECK(catalog.create(targetId(2), identity(2), evidence(2)) ==
          TargetMutationStatus::Created);
    const TargetCatalog before = catalog;
    TargetMergeHistory history;
    CHECK(history.merge(catalog, operationId(3), targetId(1), targetId(2),
                        4, 1) == TargetMergeStatus::IdentityFull);
    CHECK(history.size() == 0);
    checkSameGraph(catalog, before);

    TargetCatalog evidenceCatalog;
    CHECK(evidenceCatalog.create(targetId(1), identity(1), evidence(1)) ==
          TargetMutationStatus::Created);
    for (std::uint8_t suffix = 10; suffix < 17; ++suffix) {
        CHECK(evidenceCatalog.attachEvidence(
                  targetId(1), identity(1), evidence(suffix, suffix)) ==
              TargetMutationStatus::Applied);
    }
    CHECK(evidenceCatalog.create(targetId(2), identity(2), evidence(2)) ==
          TargetMutationStatus::Created);
    const TargetCatalog evidenceBefore = evidenceCatalog;
    CHECK(history.merge(evidenceCatalog, operationId(4), targetId(1),
                        targetId(2), 8, 1) ==
          TargetMergeStatus::EvidenceFull);
    CHECK(history.size() == 0);
    checkSameGraph(evidenceCatalog, evidenceBefore);
}

void checkMalformedHistoryFailsClosed() {
    TargetCatalog catalog;
    CHECK(catalog.create(targetId(1), identity(1), evidence(1)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.create(targetId(2), identity(2), evidence(2)) ==
          TargetMutationStatus::Created);
    TargetMergeHistory sourceHistory;
    CHECK(sourceHistory.merge(catalog, operationId(5), targetId(1),
                              targetId(2), 1, 1) ==
          TargetMergeStatus::Merged);
    TargetMergeRecord malformed = *sourceHistory.get(0);
    malformed.id = operationId(6);
    malformed.originalCatalogSize = 1;
    TargetMergeHistory restored;
    CHECK(restored.restore(malformed) == TargetMergeStatus::InvalidArgument);
    CHECK(restored.size() == 0);
}

void checkPersistenceRestoreSlotIsTransactional() {
    TargetCatalog catalog;
    CHECK(catalog.create(targetId(1), identity(1), evidence(1)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.create(targetId(2), identity(2), evidence(2)) ==
          TargetMutationStatus::Created);
    TargetMergeHistory source;
    CHECK(source.merge(catalog, operationId(7), targetId(1), targetId(2),
                       1, 1) == TargetMergeStatus::Merged);
    const TargetMergeRecord valid = *source.get(0);

    TargetMergeHistory restored;
    TargetMergeRecord* slot = restored.beginPersistenceRestore();
    CHECK(slot != nullptr);
    CHECK(restored.size() == 0);
    CHECK(restored.get(0) == nullptr);
    CHECK(restored.beginPersistenceRestore() == nullptr);
    CHECK(restored.restore(valid) == TargetMergeStatus::InvalidArgument);
    restored.cancelPersistenceRestore();
    CHECK(restored.size() == 0);

    slot = restored.beginPersistenceRestore();
    CHECK(slot != nullptr);
    *slot = valid;
    CHECK(restored.commitPersistenceRestore() == TargetMergeStatus::Merged);
    CHECK(restored.size() == 1);
    CHECK(restored.get(0) != nullptr);

    slot = restored.beginPersistenceRestore();
    CHECK(slot != nullptr);
    *slot = valid;
    CHECK(restored.commitPersistenceRestore() ==
          TargetMergeStatus::OperationIdConflict);
    CHECK(restored.size() == 1);

    slot = restored.beginPersistenceRestore();
    CHECK(slot != nullptr);
    *slot = valid;
    slot->originalCatalogSize = 1;
    CHECK(restored.commitPersistenceRestore() ==
          TargetMergeStatus::InvalidArgument);
    CHECK(restored.size() == 1);
}

void checkHistoryBound() {
    TargetCatalog catalog;
    CHECK(catalog.create(targetId(1), identity(1), evidence(1)) ==
          TargetMutationStatus::Created);
    CHECK(catalog.create(targetId(2), identity(2), evidence(2)) ==
          TargetMutationStatus::Created);
    TargetMergeHistory history;
    for (std::size_t index = 0; index < TargetMergeHistory::kCapacity; ++index) {
        const TargetRecord* destination = catalog.find(targetId(1));
        const TargetRecord* source = catalog.find(targetId(2));
        CHECK(destination != nullptr);
        CHECK(source != nullptr);
        CHECK(history.merge(catalog, operationId(
                                static_cast<std::uint8_t>(10U + index)),
                            targetId(1), targetId(2), destination->revision,
                            source->revision) == TargetMergeStatus::Merged);
        CHECK(history.split(catalog, operationId(
                                static_cast<std::uint8_t>(10U + index))) ==
              TargetMergeStatus::Split);
    }
    const TargetRecord* destination = catalog.find(targetId(1));
    const TargetRecord* source = catalog.find(targetId(2));
    CHECK(history.merge(catalog, operationId(99), targetId(1), targetId(2),
                        destination->revision, source->revision) ==
          TargetMergeStatus::HistoryFull);
    CHECK(catalog.size() == 2);
}

void checkEnumeratedRoundTrips() {
    for (std::uint8_t destinationSuffix = 1; destinationSuffix <= 4;
         ++destinationSuffix) {
        for (std::uint8_t sourceSuffix = 1; sourceSuffix <= 4;
             ++sourceSuffix) {
            if (sourceSuffix == destinationSuffix) continue;
            TargetCatalog catalog;
            for (std::uint8_t suffix = 1; suffix <= 4; ++suffix) {
                CHECK(catalog.create(targetId(suffix), identity(suffix),
                                     evidence(suffix, suffix)) ==
                      TargetMutationStatus::Created);
            }
            const TargetCatalog before = catalog;
            TargetMergeHistory history;
            const TargetMergeId id = operationId(static_cast<std::uint8_t>(
                destinationSuffix * 16U + sourceSuffix));
            CHECK(history.merge(catalog, id, targetId(destinationSuffix),
                                targetId(sourceSuffix), 1, 1) ==
                  TargetMergeStatus::Merged);
            CHECK(history.split(catalog, id) == TargetMergeStatus::Split);
            checkSameGraph(catalog, before);
            for (std::uint8_t suffix = 1; suffix <= 4; ++suffix) {
                const TargetRecord* restored = catalog.find(targetId(suffix));
                CHECK(restored != nullptr);
                CHECK(targetEvidenceEqual(restored->evidence[0],
                                          evidence(suffix, suffix)));
            }
        }
    }
}

}  // namespace

int main() {
    checkDescriptors();
    checkMergeSplitAndAudit();
    checkChangedTargetFailsClosed();
    checkBoundsFailWithoutMutation();
    checkMalformedHistoryFailsClosed();
    checkPersistenceRestoreSlotIsTransactional();
    checkHistoryBound();
    checkEnumeratedRoundTrips();
    if (failures != 0) {
        std::cerr << failures << " target merge test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "S6 reversible Target merge/split tests passed\n";
    return EXIT_SUCCESS;
}
