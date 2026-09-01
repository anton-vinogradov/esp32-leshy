#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "AtomicHead.h"
#include "ProtocolDerivedDecodeCodec.h"
#include "SessionStore.h"

namespace leshy1::storage {

constexpr std::size_t kProtocolDerivedDecodeStorePathMax = 96U;
constexpr std::size_t kProtocolDerivedDecodeManifestBytes = 16U;

enum class ProtocolDerivedDecodeStoreFileKind : std::uint8_t {
    Payload,
    Manifest,
    HeadA,
    HeadB,
};

bool formatProtocolDerivedDecodeStorePath(
    ProtocolDerivedDecodeStoreFileKind kind,
    std::uint32_t captureGeneration,
    std::uint32_t annotationStoreGeneration,
    std::uint32_t derivedStoreGeneration,
    char* output, std::size_t capacity);

struct ProtocolDerivedDecodeStoreWorkspace final {
    std::array<std::uint8_t, kProtocolDerivedDecodeWireMaxBytes> payload{};
    std::array<std::uint8_t, kProtocolDerivedDecodeManifestBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    std::size_t payloadSize = 0U;
    std::uint32_t storeGeneration = 0U;
};

enum class ProtocolDerivedDecodeStoreStatus : std::uint8_t {
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
    SourceMismatch,
    AnnotationMismatch,
};

const char* protocolDerivedDecodeStoreStatusName(
    ProtocolDerivedDecodeStoreStatus status);

struct ProtocolDerivedDecodeStoreCommitResult final {
    ProtocolDerivedDecodeStoreStatus status =
        ProtocolDerivedDecodeStoreStatus::InvalidArgument;
    CommitStage stage = CommitStage::WritePayloads;
    std::uint32_t storeGeneration = 0U;
    HeadSlot publishedSlot = HeadSlot::A;

    bool complete() const {
        return status == ProtocolDerivedDecodeStoreStatus::Valid;
    }
};

struct ProtocolDerivedDecodeStoreRecoveryResult final {
    ProtocolDerivedDecodeStoreStatus status =
        ProtocolDerivedDecodeStoreStatus::NoGeneration;
    RecoveryChoice choice = RecoveryChoice::None;
    CandidateStatus aStatus = CandidateStatus::InvalidHead;
    CandidateStatus bStatus = CandidateStatus::InvalidHead;
    std::uint32_t storeGeneration = 0U;
    std::size_t fields = 0U;

    bool valid() const {
        return status == ProtocolDerivedDecodeStoreStatus::Valid;
    }
};

ProtocolDerivedDecodeStoreCommitResult commitProtocolDerivedDecode(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolDerivedDecode& decode,
    std::uint32_t storeGeneration, HeadSlot publishSlot);

ProtocolDerivedDecodeStoreCommitResult commitNextProtocolDerivedDecode(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolDerivedDecode& decode,
    apps::protocol::ProtocolDerivedDecode& recoveryScratch);

ProtocolDerivedDecodeStoreRecoveryResult recoverProtocolDerivedDecode(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    std::uint32_t expectedAnnotationStoreGeneration,
    apps::protocol::ProtocolDerivedDecode* output);

}  // namespace leshy1::storage
