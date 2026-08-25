#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "AtomicHead.h"
#include "SessionStore.h"
#include "TargetCodec.h"

namespace leshy1::storage {

constexpr std::size_t kTargetStateStorePathMax = 72;

enum class TargetStateStoreFileKind : std::uint8_t {
    State,
    Manifest,
    HeadA,
    HeadB,
};

bool formatTargetStateStorePath(TargetStateStoreFileKind kind,
                                std::uint32_t generation, char* output,
                                std::size_t capacity);

// Catalog and decision history share one deterministic CBOR payload and one
// dual-head commit point: recovery can never pair a new graph with an old
// decision log (or the reverse).
struct TargetStateStoreWorkspace final {
    std::array<std::uint8_t, kTargetStateMaxBytes> state{};
    std::array<std::uint8_t, kTargetStateManifestMaxBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    std::size_t stateSize = 0;
    std::size_t manifestSize = 0;
    std::uint32_t generation = 0;
};

// Legacy compact projection retained for decoding catalog-only schema-v3
// generations written before on-device correlation decisions were admitted.
// It rejects decision/merge history instead of silently discarding it.
struct TargetCatalogStateStoreWorkspace final {
    std::array<std::uint8_t, kTargetCatalogStateMaxBytes> state{};
    std::array<std::uint8_t, kTargetStateManifestMaxBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    std::size_t stateSize = 0;
    std::size_t manifestSize = 0;
    std::uint32_t generation = 0;
};

struct TargetDecisionStateStoreWorkspace final {
    std::array<std::uint8_t, kTargetDecisionStateMaxBytes> state{};
    std::array<std::uint8_t, kTargetStateManifestMaxBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    std::size_t stateSize = 0;
    std::size_t manifestSize = 0;
    std::uint32_t generation = 0;
};

static_assert(sizeof(TargetCatalogStateStoreWorkspace) <
              sizeof(TargetStateStoreWorkspace));
static_assert(sizeof(TargetDecisionStateStoreWorkspace) <
              sizeof(TargetStateStoreWorkspace));

enum class TargetStateStoreStatus : std::uint8_t {
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

const char* targetStateStoreStatusName(TargetStateStoreStatus status);

struct TargetStateStoreCommitResult final {
    TargetStateStoreStatus status = TargetStateStoreStatus::InvalidArgument;
    CommitStage stage = CommitStage::WritePayloads;
    std::uint32_t generation = 0;
    HeadSlot publishedSlot = HeadSlot::A;

    bool complete() const { return status == TargetStateStoreStatus::Valid; }
};

struct TargetStateStoreRecoveryResult final {
    TargetStateStoreStatus status = TargetStateStoreStatus::NoGeneration;
    RecoveryChoice choice = RecoveryChoice::None;
    CandidateStatus aStatus = CandidateStatus::InvalidHead;
    CandidateStatus bStatus = CandidateStatus::InvalidHead;
    std::uint32_t generation = 0;
    std::size_t targets = 0;
    std::size_t decisions = 0;
    std::size_t merges = 0;

    bool valid() const { return status == TargetStateStoreStatus::Valid; }
};

TargetStateStoreCommitResult commitTargetState(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    const domain::targets::TargetMergeHistory& merges,
    std::uint32_t generation, HeadSlot publishSlot);

TargetStateStoreCommitResult commitNextTargetState(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    const domain::targets::TargetMergeHistory& merges,
    domain::targets::TargetCatalog& recoveryCatalogScratch,
    domain::targets::CorrelationDecisionLog& recoveryDecisionScratch,
    domain::targets::TargetMergeHistory& recoveryMergeScratch);

TargetStateStoreRecoveryResult recoverTargetState(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions,
    domain::targets::TargetMergeHistory* merges);

// Product lifecycle variant for schema-v3 states whose decision/merge arrays
// are still empty. It uses the same files, manifests, heads and crash boundary
// as the full store while avoiding empty-history RAM on no-PSRAM hardware.
TargetStateStoreCommitResult commitTargetCatalogState(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    std::uint32_t generation, HeadSlot publishSlot);
TargetStateStoreCommitResult commitNextTargetCatalogState(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    domain::targets::TargetCatalog& recoveryCatalogScratch);
TargetStateStoreRecoveryResult recoverTargetCatalogState(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    domain::targets::TargetCatalog* catalog);

// Product S6.4 projection: graph + full correlation decision history, while
// merge history must remain empty.  It reads the existing catalog-only state
// and upgrades the next atomic generation without changing the wire schema.
TargetStateStoreCommitResult commitTargetDecisionState(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    std::uint32_t generation, HeadSlot publishSlot);
TargetStateStoreRecoveryResult recoverTargetDecisionState(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions);

}  // namespace leshy1::storage
