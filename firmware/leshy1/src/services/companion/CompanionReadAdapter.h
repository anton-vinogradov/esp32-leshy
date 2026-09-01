#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/WifiFrame.h"
#include "domain/targets/TargetCatalog.h"
#include "domain/targets/TargetComparison.h"
#include "services/companion/CompanionProtocol.h"
#include "services/survey/SurveySession.h"

namespace leshy1::services::companion {

constexpr std::size_t kCompanionReadSessionCapacity = 2;
constexpr std::size_t kCompanionReadSectionCapacity = 12;

enum class CompanionReadKind : std::uint8_t {
    SessionList,
    SessionDetail,
    TargetList,
    TargetDetail,
    TargetCompare,
    CaptureLiveRead,
};

enum class CompanionTargetDetailSection : std::uint8_t {
    Summary,
    Notes,
    Tags,
    Identities,
    Evidence,
};

enum class CompanionReadParseStatus : std::uint8_t {
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
    InvalidRequestId,
    InvalidIdentifier,
    InvalidNumber,
    InvalidSection,
    FieldNotAllowed,
};

const char* companionReadParseReason(CompanionReadParseStatus status);

struct CompanionReadRequest final {
    CompanionReadKind kind = CompanionReadKind::SessionList;
    std::array<char, kCompanionRequestIdCapacity + 1U> requestId{};
    std::uint8_t requestIdLength = 0;
    std::uint32_t offset = 0;
    domain::targets::TargetId targetId{};
    domain::targets::TargetComparisonSource source{};
    domain::targets::TargetComparisonSource baseline{};
    domain::targets::TargetComparisonSource current{};
    CompanionTargetDetailSection section =
        CompanionTargetDetailSection::Summary;
};

// Parses one post-connect request. Each kind has an exact field set; a field
// meaningful to a different operation is rejected instead of being ignored.
// Output is published only after the complete bounded frame is accepted.
CompanionReadParseStatus parseCompanionReadRequest(
    const char* frame, std::size_t frameLength, CompanionReadRequest* output);

struct CompanionReadSessionBinding final {
    domain::targets::TargetComparisonSource source{};
    const survey::SurveySession* session = nullptr;
};

// Caller-owned snapshot over the exact objects already used by the product
// Targets view. It owns no storage path and allocates no duplicate graph.
struct CompanionReadContext final {
    std::array<CompanionReadSessionBinding,
               kCompanionReadSessionCapacity> sessions{};
    std::uint8_t sessionCount = 0;
    const domain::targets::TargetCatalog* targets = nullptr;
    const domain::targets::TargetComparisonResult* comparison = nullptr;
    const domain::captures::WifiFrameSource* liveWifiCapture = nullptr;
    std::uint32_t liveWifiDropped = 0;
    bool liveWifiTerminal = false;
    bool liveWifiCleanupComplete = false;
};

CompanionCapabilityMask companionReadCapabilities(
    const CompanionReadContext& context);

enum class CompanionReadStatus : std::uint8_t {
    Ok,
    InvalidRequest,
    NotConnected,
    CapabilityDenied,
    CapabilityUnavailable,
    NotFound,
    OffsetOutOfRange,
    SourceUnavailable,
    ResultUnavailable,
};

const char* companionReadReason(CompanionReadStatus status);

// Executes one read-only projection and writes one deterministic NDJSON
// response. The caller buffer is untouched on failure and outputLength is zero.
// No function in this adapter can mutate a Session, Target, storage or radio.
bool encodeCompanionReadResponse(
    const CompanionConnection& connection,
    const CompanionReadContext& context,
    const CompanionReadRequest& request,
    char* output, std::size_t capacity, std::size_t* outputLength);

// Produces a stable response for a frame that did not parse. It intentionally
// carries an empty request_id because an invalid frame has no trusted identity.
bool encodeCompanionReadParseError(
    CompanionReadParseStatus status, char* output, std::size_t capacity,
    std::size_t* outputLength);

}  // namespace leshy1::services::companion
