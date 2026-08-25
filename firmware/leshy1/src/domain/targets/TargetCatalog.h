#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "Target.h"

namespace leshy1::domain::targets {

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
};

const char* targetMutationStatusName(TargetMutationStatus status);

// Allocation-free working set. Persistent paging/codec is a later S6.1 slice;
// reaching a bound fails closed and never evicts identities or evidence.
class TargetCatalog final {
public:
    static constexpr std::size_t kCapacity = 16;

    void clear();
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
    TargetRecord* findMutable(const TargetId& id);
    TargetRecord* findMutableByIdentity(const TargetIdentity& identity);
    TargetRecord* findMutableByEvidence(const TargetEvidenceRef& evidence);

    std::array<TargetRecord, kCapacity> records_{};
    std::size_t size_ = 0;
};

}  // namespace leshy1::domain::targets
