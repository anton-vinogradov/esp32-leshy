#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "TargetCatalog.h"

namespace leshy1::domain::targets {

struct TargetMergeId final {
    static constexpr std::size_t kSize = 16;
    std::array<std::uint8_t, kSize> bytes{};
};

bool targetMergeIdValid(const TargetMergeId& id);
bool targetMergeIdEqual(const TargetMergeId& left,
                        const TargetMergeId& right);

enum class TargetMergeStatus : std::uint8_t {
    Merged,
    Split,
    Unchanged,
    InvalidArgument,
    NotFound,
    TargetChanged,
    IdentityFull,
    EvidenceFull,
    HistoryFull,
    OperationIdConflict,
    AlreadySplit,
    CatalogConflict,
};

const char* targetMergeStatusName(TargetMergeStatus status);

struct TargetMergeRecord final {
    TargetMergeId id{};
    TargetRecord destinationBefore{};
    TargetRecord sourceBefore{};
    std::uint8_t originalCatalogSize = 0;
    std::uint8_t destinationIndex = 0;
    std::uint8_t sourceIndex = 0;
    std::uint32_t mergedRevision = 0;
    bool split = false;
};

// Each record retains both complete pre-merge Targets. No source observation is
// copied or rewritten: identities continue to point at the same evidence refs,
// while split can reconstruct their exact previous ownership graph.
class TargetMergeHistory final {
public:
    static constexpr std::size_t kCapacity = 8;

    void clear();
    std::size_t size() const { return size_; }
    const TargetMergeRecord* get(std::size_t index) const;
    const TargetMergeRecord* find(const TargetMergeId& id) const;

    TargetMergeStatus merge(TargetCatalog& catalog,
                            const TargetMergeId& operationId,
                            const TargetId& destinationId,
                            const TargetId& sourceId,
                            std::uint32_t expectedDestinationRevision,
                            std::uint32_t expectedSourceRevision);
    TargetMergeStatus split(TargetCatalog& catalog,
                            const TargetMergeId& operationId);

    // Persistence uses restore only after decoding and validating every field.
    // The current catalog is checked separately when an actual split executes.
    TargetMergeStatus restore(const TargetMergeRecord& record);

private:
    TargetMergeRecord* findMutable(const TargetMergeId& id);

    std::array<TargetMergeRecord, kCapacity> records_{};
    std::size_t size_ = 0;
};

static_assert(sizeof(TargetMergeHistory) <= 16U * 1024U,
              "Target merge history must remain bounded to 16 KiB");

}  // namespace leshy1::domain::targets
