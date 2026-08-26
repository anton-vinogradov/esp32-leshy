#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/companion/CompanionProtocol.h"
#include "services/targets/TargetService.h"

namespace leshy1::services::companion {

using CompanionMutationId = std::array<std::uint8_t, 16>;

enum class CompanionMutationRequestKind : std::uint8_t {
    Preview,
    Confirm,
    Status,
};

enum class CompanionMutationParseStatus : std::uint8_t {
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
    InvalidAction,
    InvalidBase64,
    InvalidValue,
    FieldNotAllowed,
};

const char* companionMutationParseReason(
    CompanionMutationParseStatus status);

struct CompanionMutationRequest final {
    CompanionMutationRequestKind kind =
        CompanionMutationRequestKind::Preview;
    std::array<char, kCompanionRequestIdCapacity + 1U> requestId{};
    std::uint8_t requestIdLength = 0;
    services::targets::TargetAction action{};
    CompanionMutationId mutationId{};
};

// Preview frames carry one existing typed Target Action plus an exact expected
// revision. Text is canonical base64 so the full 160-byte notes bound remains
// inside the common 512-byte frame. Confirm/status frames carry only the
// one-time mutation ID returned by preview.
CompanionMutationParseStatus parseCompanionMutationRequest(
    const char* frame, std::size_t frameLength,
    CompanionMutationRequest* output);

CompanionCapability companionCapabilityForTargetAction(
    services::targets::TargetActionKind kind);

CompanionCapabilityMask companionMutationCapabilities(
    const domain::targets::TargetCatalog* targets);

enum class CompanionMutationStatus : std::uint8_t {
    Ready,
    Accepted,
    Saving,
    Saved,
    InvalidRequest,
    NotConnected,
    CapabilityDenied,
    CapabilityUnavailable,
    NotFound,
    RevisionConflict,
    InvalidValue,
    Unchanged,
    UnknownMutation,
    Busy,
    AlreadyConfirmed,
    Failed,
};

const char* companionMutationReason(CompanionMutationStatus status);

struct CompanionMutationAssessment final {
    CompanionMutationStatus status =
        CompanionMutationStatus::InvalidRequest;
    services::targets::TargetActionResult action{};

    bool ready() const { return status == CompanionMutationStatus::Ready; }
};

CompanionMutationAssessment assessCompanionMutationPreview(
    const CompanionConnection& connection,
    const domain::targets::TargetCatalog* targets,
    const CompanionMutationRequest& request);

enum class CompanionMutationState : std::uint8_t {
    None,
    Previewed,
    Accepted,
    Saving,
    Saved,
    Failed,
};

struct CompanionMutationResponse final {
    CompanionMutationRequestKind kind =
        CompanionMutationRequestKind::Preview;
    std::array<char, kCompanionRequestIdCapacity + 1U> requestId{};
    std::uint8_t requestIdLength = 0;
    CompanionMutationStatus status = CompanionMutationStatus::InvalidRequest;
    CompanionMutationState state = CompanionMutationState::None;
    CompanionMutationId mutationId{};
    services::targets::TargetActionKind actionKind =
        services::targets::TargetActionKind::Create;
    domain::targets::TargetId targetId{};
    std::uint32_t expectedRevision = 0;
    std::uint32_t targetRevision = 0;
    std::uint32_t stateGeneration = 0;
};

bool companionMutationIdValid(const CompanionMutationId& id);

// Responses are staged into a fixed 513-byte scratch object before publishing.
// Failed encoding leaves outputLength zero and the caller buffer untouched.
bool encodeCompanionMutationResponse(
    const CompanionMutationResponse& response,
    char* output, std::size_t capacity, std::size_t* outputLength);

bool encodeCompanionMutationParseError(
    CompanionMutationParseStatus status, char* output,
    std::size_t capacity, std::size_t* outputLength);

}  // namespace leshy1::services::companion
