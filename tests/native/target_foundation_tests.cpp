#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>

#include "domain/targets/TargetCatalog.h"
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
}

void testTargetBoundsFailClosedWithoutPartialIdentityAttachment() {
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
    CHECK(catalog.attachEvidence(
              id, bleIdentity(8, 0), evidence(5, 41, 1)) ==
          TargetMutationStatus::EvidenceFull);
    const TargetRecord* after = catalog.find(id);
    CHECK(after->identityCount == identityCount);
    CHECK(after->revision == revision);
    CHECK(catalog.findByIdentity(bleIdentity(8, 0)) == nullptr);
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
    CHECK(setTargetActionText(&rename, "Office AP", std::strlen("Office AP")));
    result = service.execute(rename);
    CHECK(result.applied());
    CHECK(result.revision == 2);
    CHECK(std::strcmp(catalog.find(create.targetId)->name.data(), "Office AP") == 0);

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

}  // namespace

int main() {
    testTargetOwnsExactIdentitiesAndImmutableEvidence();
    testTargetMetadataIsBoundedIdempotentAndUnicodeSafe();
    testTargetBoundsFailClosedWithoutPartialIdentityAttachment();
    testTypedTargetActionsHaveOneStableMutationBoundary();
    testTargetWorkingSetHasAnExplicitNoEvictionBound();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "S6 Target foundation contract tests passed\n";
    return EXIT_SUCCESS;
}
