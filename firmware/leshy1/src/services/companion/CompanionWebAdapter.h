#pragma once

#include <cstddef>
#include <cstdint>

#include "services/companion/CompanionProtocol.h"

namespace leshy1::services::companion {

constexpr const char* kCompanionWebIndexPath = "/";
constexpr const char* kCompanionWebApiPath = "/api/v1/companion";
constexpr const char* kCompanionWebJsonContentType = "application/json";
constexpr const char* kCompanionWebHtmlContentType =
    "text/html; charset=utf-8";

enum class CompanionWebMethod : std::uint8_t {
    Get,
    Post,
    Other,
};

enum class CompanionWebRoute : std::uint8_t {
    None,
    Index,
    CompanionApi,
};

enum class CompanionWebStatus : std::uint8_t {
    Ready,
    InvalidArgument,
    SessionUnavailable,
    NotFound,
    MethodNotAllowed,
    UnsupportedMediaType,
    ChunkedUnsupported,
    UnexpectedBody,
    EmptyBody,
    LengthMismatch,
    BodyTooLarge,
};

const char* companionWebReason(CompanionWebStatus status);
std::uint16_t companionWebHttpStatus(CompanionWebStatus status);

struct CompanionWebRequestMetadata final {
    CompanionWebMethod method = CompanionWebMethod::Other;
    const char* path = nullptr;
    std::size_t pathLength = 0;
    const char* contentType = nullptr;
    std::size_t contentTypeLength = 0;
    std::size_t declaredContentLength = 0;
    bool chunked = false;
    // The network owner must bind the socket to an explicitly opened local
    // device session. Locality alone is not authorization.
    bool deviceSessionAuthorized = false;
};

struct CompanionWebRequest final {
    CompanionWebRoute route = CompanionWebRoute::None;
    const char* body = nullptr;
    std::size_t bodyLength = 0;
};

// Validates only the HTTP presentation boundary. An accepted API body is
// forwarded unchanged to the shared companion parsers; this adapter owns no
// domain command, storage, driver, radio, network or secret API.
CompanionWebStatus validateCompanionWebRequest(
    const CompanionWebRequestMetadata& metadata,
    const char* body, std::size_t bodyLength,
    CompanionWebRequest* output);

// Stable bounded JSON body for transport-level denials. All-or-nothing: an
// undersized output remains untouched and outputLength is reset to zero.
bool encodeCompanionWebError(
    CompanionWebStatus status, char* output, std::size_t capacity,
    std::size_t* outputLength);

// Self-contained offline UI. It loads no external script, font or image and
// calls only kCompanionWebApiPath with the versioned companion JSON contract.
const char* companionWebIndexHtml(std::size_t* length);

}  // namespace leshy1::services::companion
