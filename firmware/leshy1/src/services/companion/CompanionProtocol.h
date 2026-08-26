#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::services::companion {

constexpr std::uint16_t kCompanionProtocolVersion = 1;
constexpr std::size_t kCompanionMaxFrameBytes = 512;
constexpr std::size_t kCompanionRequestIdCapacity = 32;
constexpr const char* kCompanionRequestSchema =
    "leshy.companion.request.v1";
constexpr const char* kCompanionResponseSchema =
    "leshy.companion.response.v1";

using CompanionScopeMask = std::uint16_t;

enum class CompanionScope : CompanionScopeMask {
    SessionRead = 1U << 0U,
    TargetRead = 1U << 1U,
    TargetCompare = 1U << 2U,
    TargetMutate = 1U << 3U,
    Export = 1U << 4U,
    Connectivity = 1U << 5U,
};

constexpr CompanionScopeMask companionScopeMask(CompanionScope scope) {
    return static_cast<CompanionScopeMask>(scope);
}

constexpr CompanionScopeMask kCompanionKnownScopes =
    companionScopeMask(CompanionScope::SessionRead) |
    companionScopeMask(CompanionScope::TargetRead) |
    companionScopeMask(CompanionScope::TargetCompare) |
    companionScopeMask(CompanionScope::TargetMutate) |
    companionScopeMask(CompanionScope::Export) |
    companionScopeMask(CompanionScope::Connectivity);

constexpr CompanionScopeMask kCompanionS65ReadScopes =
    companionScopeMask(CompanionScope::SessionRead) |
    companionScopeMask(CompanionScope::TargetRead) |
    companionScopeMask(CompanionScope::TargetCompare);

constexpr CompanionScopeMask kCompanionS65MutationScopes =
    companionScopeMask(CompanionScope::TargetRead) |
    companionScopeMask(CompanionScope::TargetMutate);

enum class CompanionParseStatus : std::uint8_t {
    Parsed,
    InvalidArgument,
    Empty,
    TooLarge,
    MalformedJson,
    UnknownField,
    DuplicateField,
    MissingField,
    UnsupportedSchema,
    UnsupportedKind,
    UnsupportedProtocol,
    InvalidRequestId,
    UnknownScope,
    DuplicateScope,
    EmptyScopeSet,
};

const char* companionParseReason(CompanionParseStatus status);

struct CompanionConnectRequest final {
    std::uint16_t protocolVersion = 0;
    std::array<char, kCompanionRequestIdCapacity + 1U> requestId{};
    std::uint8_t requestIdLength = 0;
    CompanionScopeMask requestedScopes = 0;
};

// Parses one bounded NDJSON object. The output is assigned only after the whole
// frame is accepted, so malformed or unauthorized input cannot leave a partial
// request for a caller to execute.
CompanionParseStatus parseCompanionConnectRequest(
    const char* frame, std::size_t frameLength,
    CompanionConnectRequest* output);

enum class CompanionConnectionStatus : std::uint8_t {
    Ready,
    InvalidRequest,
    ScopeDenied,
    ScopeUnavailable,
    ScopeDependencyMissing,
};

const char* companionConnectionReason(CompanionConnectionStatus status);

struct CompanionConnectionPolicy final {
    // Both masks default to zero deliberately. A transport must bind the
    // connection to an explicit device session before any scope is granted.
    CompanionScopeMask deviceSessionScopes = 0;
    CompanionScopeMask availableScopes = 0;
    std::uint16_t availableCapabilities = 0;
};

struct CompanionConnection final {
    CompanionConnectionStatus status =
        CompanionConnectionStatus::ScopeDenied;
    std::array<char, kCompanionRequestIdCapacity + 1U> requestId{};
    std::uint8_t requestIdLength = 0;
    CompanionScopeMask grantedScopes = 0;
    std::uint16_t grantedCapabilities = 0;

    bool ready() const {
        return status == CompanionConnectionStatus::Ready;
    }
};

using CompanionCapabilityMask = std::uint16_t;

enum class CompanionCapability : CompanionCapabilityMask {
    SessionList = 1U << 0U,
    SessionDetail = 1U << 1U,
    TargetList = 1U << 2U,
    TargetDetail = 1U << 3U,
    TargetCompare = 1U << 4U,
    TargetFavoriteSet = 1U << 5U,
    TargetNameSet = 1U << 6U,
    TargetNotesSet = 1U << 7U,
    TargetTagAdd = 1U << 8U,
    TargetTagRemove = 1U << 9U,
};

constexpr CompanionCapabilityMask companionCapabilityMask(
    CompanionCapability capability) {
    return static_cast<CompanionCapabilityMask>(capability);
}

constexpr CompanionCapabilityMask kCompanionKnownCapabilities =
    companionCapabilityMask(CompanionCapability::SessionList) |
    companionCapabilityMask(CompanionCapability::SessionDetail) |
    companionCapabilityMask(CompanionCapability::TargetList) |
    companionCapabilityMask(CompanionCapability::TargetDetail) |
    companionCapabilityMask(CompanionCapability::TargetCompare) |
    companionCapabilityMask(CompanionCapability::TargetFavoriteSet) |
    companionCapabilityMask(CompanionCapability::TargetNameSet) |
    companionCapabilityMask(CompanionCapability::TargetNotesSet) |
    companionCapabilityMask(CompanionCapability::TargetTagAdd) |
    companionCapabilityMask(CompanionCapability::TargetTagRemove);

constexpr CompanionCapabilityMask kCompanionReadCapabilities =
    companionCapabilityMask(CompanionCapability::SessionList) |
    companionCapabilityMask(CompanionCapability::SessionDetail) |
    companionCapabilityMask(CompanionCapability::TargetList) |
    companionCapabilityMask(CompanionCapability::TargetDetail) |
    companionCapabilityMask(CompanionCapability::TargetCompare);

constexpr CompanionCapabilityMask kCompanionTargetMutationCapabilities =
    companionCapabilityMask(CompanionCapability::TargetFavoriteSet) |
    companionCapabilityMask(CompanionCapability::TargetNameSet) |
    companionCapabilityMask(CompanionCapability::TargetNotesSet) |
    companionCapabilityMask(CompanionCapability::TargetTagAdd) |
    companionCapabilityMask(CompanionCapability::TargetTagRemove);

CompanionConnection negotiateCompanionConnection(
    const CompanionConnectRequest& request,
    const CompanionConnectionPolicy& policy);

struct CompanionCapabilityDescriptor final {
    const char* id = nullptr;
    CompanionCapability capability = CompanionCapability::SessionList;
    CompanionScopeMask requiredScopes = 0;
    const char* actionId = nullptr;
    std::uint16_t requestSchemaVersion = 0;
    std::uint16_t resultSchemaVersion = 0;
    bool readOnly = true;
};

std::size_t companionCapabilityCount();
const CompanionCapabilityDescriptor* companionCapability(std::size_t index);
bool companionCapabilityGranted(const CompanionCapabilityDescriptor& capability,
                                CompanionCapabilityMask grantedCapabilities,
                                CompanionScopeMask grantedScopes);

enum class CompanionTransport : std::uint8_t {
    UsbSerial,
    LocalWeb,
};

// Writes one deterministic response envelope and its trailing newline. No
// partial response is published: false leaves outputLength at zero.
bool encodeCompanionConnectResponse(
    const CompanionConnection& connection, CompanionTransport transport,
    char* output, std::size_t capacity, std::size_t* outputLength);

}  // namespace leshy1::services::companion
