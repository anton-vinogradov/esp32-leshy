#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "AtomicHead.h"
#include "SessionStore.h"
#include "TargetCodec.h"

namespace leshy1::storage {

constexpr std::size_t kTargetStorePathMax = 64;

enum class TargetStoreFileKind : std::uint8_t {
    Catalog,
    Manifest,
    HeadA,
    HeadB,
};

bool formatTargetStorePath(TargetStoreFileKind kind,
                           std::uint32_t generation, char* output,
                           std::size_t capacity);

// The byte-file interface is shared with SessionStore. Every file has a
// target- prefix so the two atomic journals cannot alias, while preserving the
// flat relative-path contract of the SD and LittleFS backends.
struct TargetStoreWorkspace final {
    std::array<std::uint8_t, kTargetCatalogMaxBytes> catalog{};
    std::array<std::uint8_t, kTargetManifestMaxBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    std::size_t catalogSize = 0;
    std::size_t manifestSize = 0;
    std::uint32_t generation = 0;
};

enum class TargetStoreStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    EncodeFailed,
    PathError,
    IoError,
    SyncError,
    Empty,
    NoGeneration,
    Conflict,
    CorruptGeneration,
};

const char* targetStoreStatusName(TargetStoreStatus status);

struct TargetStoreCommitResult final {
    TargetStoreStatus status = TargetStoreStatus::InvalidArgument;
    CommitStage stage = CommitStage::WritePayloads;
    std::uint32_t generation = 0;
    HeadSlot publishedSlot = HeadSlot::A;

    bool complete() const { return status == TargetStoreStatus::Valid; }
};

struct TargetStoreRecoveryResult final {
    TargetStoreStatus status = TargetStoreStatus::NoGeneration;
    RecoveryChoice choice = RecoveryChoice::None;
    CandidateStatus aStatus = CandidateStatus::InvalidHead;
    CandidateStatus bStatus = CandidateStatus::InvalidHead;
    std::uint32_t generation = 0;
    std::size_t targets = 0;

    bool valid() const { return status == TargetStoreStatus::Valid; }
};

TargetStoreCommitResult commitTargetCatalog(
    SessionStoreIo& io, TargetStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog, std::uint32_t generation,
    HeadSlot publishSlot);

// recoveryScratch is explicit so callers control the roughly 12 KiB catalog
// lifetime. It must not alias catalog; recovery would clear it before encode.
TargetStoreCommitResult commitNextTargetCatalog(
    SessionStoreIo& io, TargetStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    domain::targets::TargetCatalog& recoveryScratch);

TargetStoreRecoveryResult recoverTargetCatalog(
    SessionStoreIo& io, TargetStoreWorkspace& workspace,
    domain::targets::TargetCatalog* output);

}  // namespace leshy1::storage
