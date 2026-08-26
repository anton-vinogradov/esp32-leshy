#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "Target.h"

namespace leshy1::domain::targets {

class TargetMergeHistory;

enum class TargetMutationStatus : std::uint8_t {
    Created,
    Applied,
    Unchanged,
    InvalidArgument,
    NotFound,
    DuplicateId,
    IdentityConflict,
    EvidenceConflict,
    CatalogFull,
    IdentityFull,
    EvidenceFull,
    TagFull,
    TextTooLong,
    RevisionConflict,
};

const char* targetMutationStatusName(TargetMutationStatus status);

// Allocation-free validators shared by catalog admission and persistence.
// Created means that the record is structurally valid, or that the pair is
// mutually conflict-free; every other result is the exact rejection reason.
TargetMutationStatus validateTargetRecord(const TargetRecord& record);
TargetMutationStatus validateTargetRecordCompatibility(
    const TargetRecord& existing, const TargetRecord& candidate);

// Allocation-free working set. Identity ownership fails closed at its bound.
// Evidence references use bounded oldest-first retention: immutable source
// Sessions remain on storage, while a frequently seen Target keeps its eight
// most recently admitted exact coordinates instead of becoming unreadable.
class TargetCatalog final {
public:
    static constexpr std::size_t kCapacity = 16;

    void clear();
    TargetMutationStatus restore(const TargetRecord& record);
    TargetMutationStatus create(const TargetId& id,
                                const TargetIdentity& identity,
                                const TargetEvidenceRef& evidence);
    TargetMutationStatus attachEvidence(const TargetId& id,
                                        const TargetIdentity& identity,
                                        const TargetEvidenceRef& evidence);
    TargetMutationStatus setName(const TargetId& id, const char* value,
                                 std::size_t length);
    TargetMutationStatus setNotes(const TargetId& id, const char* value,
                                  std::size_t length);
    TargetMutationStatus addTag(const TargetId& id, const char* value,
                                std::size_t length);
    TargetMutationStatus removeTag(const TargetId& id, const char* value,
                                   std::size_t length);
    TargetMutationStatus setFavorite(const TargetId& id, bool value);

    std::size_t size() const { return size_; }
    const TargetRecord* get(std::size_t index) const;
    const TargetRecord* find(const TargetId& id) const;
    const TargetRecord* findByIdentity(const TargetIdentity& identity) const;
    const TargetRecord* findByEvidence(const TargetEvidenceRef& evidence) const;

private:
    friend class TargetMergeHistory;

    // Merge/split rebuild the catalog in place only after validating the
    // complete resulting graph.  Keeping these bounded transactions inside
    // TargetCatalog avoids ever placing a second ~11-KiB catalog on an ESP32
    // task stack.
    TargetMutationStatus replaceAndRemove(
        std::size_t replacementIndex, const TargetRecord& replacement,
        std::size_t removalIndex);
    TargetMutationStatus replaceAndInsert(
        std::size_t currentIndex, std::size_t replacementIndex,
        const TargetRecord& replacement,
        std::size_t insertionIndex, const TargetRecord& insertion);

    TargetRecord* findMutable(const TargetId& id);
    TargetRecord* findMutableByIdentity(const TargetIdentity& identity);
    TargetRecord* findMutableByEvidence(const TargetEvidenceRef& evidence);

    std::array<TargetRecord, kCapacity> records_{};
    std::size_t size_ = 0;
};

}  // namespace leshy1::domain::targets
