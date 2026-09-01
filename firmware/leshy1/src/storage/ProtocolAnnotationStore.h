#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "AtomicHead.h"
#include "ProtocolAnnotationCodec.h"
#include "SessionStore.h"

namespace leshy1::storage {

constexpr std::size_t kProtocolAnnotationStorePathMax = 80U;
constexpr std::size_t kProtocolAnnotationManifestBytes = 16U;

enum class ProtocolAnnotationStoreFileKind : std::uint8_t {
    Payload,
    Manifest,
    HeadA,
    HeadB,
};

bool formatProtocolAnnotationStorePath(
    ProtocolAnnotationStoreFileKind kind, std::uint32_t captureGeneration,
    std::uint32_t storeGeneration, char* output, std::size_t capacity);

struct ProtocolAnnotationStoreWorkspace final {
    std::array<std::uint8_t, kProtocolAnnotationWireMaxBytes> payload{};
    std::array<std::uint8_t, kProtocolAnnotationManifestBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    std::size_t payloadSize = 0U;
    std::uint32_t storeGeneration = 0U;
};

enum class ProtocolAnnotationStoreStatus : std::uint8_t {
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
};

const char* protocolAnnotationStoreStatusName(
    ProtocolAnnotationStoreStatus status);

struct ProtocolAnnotationStoreCommitResult final {
    ProtocolAnnotationStoreStatus status =
        ProtocolAnnotationStoreStatus::InvalidArgument;
    CommitStage stage = CommitStage::WritePayloads;
    std::uint32_t storeGeneration = 0U;
    HeadSlot publishedSlot = HeadSlot::A;

    bool complete() const {
        return status == ProtocolAnnotationStoreStatus::Valid;
    }
};

struct ProtocolAnnotationStoreRecoveryResult final {
    ProtocolAnnotationStoreStatus status =
        ProtocolAnnotationStoreStatus::NoGeneration;
    RecoveryChoice choice = RecoveryChoice::None;
    CandidateStatus aStatus = CandidateStatus::InvalidHead;
    CandidateStatus bStatus = CandidateStatus::InvalidHead;
    std::uint32_t storeGeneration = 0U;
    std::size_t annotations = 0U;

    bool valid() const {
        return status == ProtocolAnnotationStoreStatus::Valid;
    }
};

ProtocolAnnotationStoreCommitResult commitProtocolAnnotations(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSet& annotations,
    std::uint32_t storeGeneration, HeadSlot publishSlot);

ProtocolAnnotationStoreCommitResult commitNextProtocolAnnotations(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSet& annotations,
    apps::protocol::ProtocolAnnotationSet& recoveryScratch);

ProtocolAnnotationStoreRecoveryResult recoverProtocolAnnotations(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    apps::protocol::ProtocolAnnotationSet* output);

}  // namespace leshy1::storage
