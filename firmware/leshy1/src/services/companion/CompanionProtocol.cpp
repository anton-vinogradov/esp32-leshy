#include "CompanionProtocol.h"

#include <array>
#include <cstring>

namespace leshy1::services::companion {
namespace {

struct StringToken final {
    const char* data = nullptr;
    std::size_t size = 0;
};

bool tokenEquals(const StringToken& token, const char* expected) {
    const std::size_t expectedSize = std::strlen(expected);
    return token.size == expectedSize &&
        std::memcmp(token.data, expected, expectedSize) == 0;
}

class JsonCursor final {
public:
    JsonCursor(const char* data, std::size_t size)
        : data_(data), size_(size) {}

    void skipWhitespace() {
        while (offset_ < size_) {
            const char value = data_[offset_];
            if (value != ' ' && value != '\t' && value != '\r' &&
                value != '\n') {
                break;
            }
            ++offset_;
        }
    }

    bool consume(char expected) {
        skipWhitespace();
        if (offset_ >= size_ || data_[offset_] != expected) return false;
        ++offset_;
        return true;
    }

    bool parseString(StringToken* output) {
        if (output == nullptr || !consume('"')) return false;
        const std::size_t start = offset_;
        while (offset_ < size_) {
            const unsigned char value =
                static_cast<unsigned char>(data_[offset_]);
            if (value == '"') {
                output->data = data_ + start;
                output->size = offset_ - start;
                ++offset_;
                return true;
            }
            // The connection envelope has an ASCII-only vocabulary. Reject
            // escapes and controls rather than normalizing ambiguous input.
            if (value == '\\' || value < 0x20U || value > 0x7eU) return false;
            ++offset_;
        }
        return false;
    }

    bool parseUnsigned(std::uint32_t* output) {
        if (output == nullptr) return false;
        skipWhitespace();
        if (offset_ >= size_ || data_[offset_] < '0' ||
            data_[offset_] > '9') {
            return false;
        }
        if (data_[offset_] == '0' && offset_ + 1U < size_ &&
            data_[offset_ + 1U] >= '0' && data_[offset_ + 1U] <= '9') {
            return false;
        }
        std::uint32_t value = 0;
        while (offset_ < size_ && data_[offset_] >= '0' &&
               data_[offset_] <= '9') {
            const std::uint32_t digit =
                static_cast<std::uint32_t>(data_[offset_] - '0');
            if (value > 65535U / 10U ||
                (value == 65535U / 10U && digit > 65535U % 10U)) {
                return false;
            }
            value = value * 10U + digit;
            ++offset_;
        }
        *output = value;
        return true;
    }

    bool finished() {
        skipWhitespace();
        return offset_ == size_;
    }

    bool nextIs(char expected) {
        skipWhitespace();
        return offset_ < size_ && data_[offset_] == expected;
    }

private:
    const char* data_ = nullptr;
    std::size_t size_ = 0;
    std::size_t offset_ = 0;
};

enum Field : std::uint8_t {
    SchemaField = 1U << 0U,
    KindField = 1U << 1U,
    RequestIdField = 1U << 2U,
    ProtocolField = 1U << 3U,
    ScopesField = 1U << 4U,
};

constexpr std::uint8_t kRequiredFields =
    SchemaField | KindField | RequestIdField | ProtocolField | ScopesField;

bool validRequestId(const StringToken& token) {
    if (token.size == 0 || token.size > kCompanionRequestIdCapacity) {
        return false;
    }
    for (std::size_t index = 0; index < token.size; ++index) {
        const char value = token.data[index];
        const bool valid = (value >= 'a' && value <= 'z') ||
            (value >= 'A' && value <= 'Z') ||
            (value >= '0' && value <= '9') || value == '.' || value == '_' ||
            value == '-';
        if (!valid) return false;
    }
    return true;
}

CompanionScopeMask scopeForToken(const StringToken& token) {
    if (tokenEquals(token, "session.read")) {
        return companionScopeMask(CompanionScope::SessionRead);
    }
    if (tokenEquals(token, "target.read")) {
        return companionScopeMask(CompanionScope::TargetRead);
    }
    if (tokenEquals(token, "target.compare")) {
        return companionScopeMask(CompanionScope::TargetCompare);
    }
    if (tokenEquals(token, "target.mutate")) {
        return companionScopeMask(CompanionScope::TargetMutate);
    }
    if (tokenEquals(token, "library.export")) {
        return companionScopeMask(CompanionScope::Export);
    }
    if (tokenEquals(token, "connectivity.manage")) {
        return companionScopeMask(CompanionScope::Connectivity);
    }
    if (tokenEquals(token, "capture.live.read")) {
        return companionScopeMask(CompanionScope::CaptureLiveRead);
    }
    return 0;
}

const char* scopeName(CompanionScope scope) {
    switch (scope) {
        case CompanionScope::SessionRead: return "session.read";
        case CompanionScope::TargetRead: return "target.read";
        case CompanionScope::TargetCompare: return "target.compare";
        case CompanionScope::TargetMutate: return "target.mutate";
        case CompanionScope::Export: return "library.export";
        case CompanionScope::Connectivity: return "connectivity.manage";
        case CompanionScope::CaptureLiveRead: return "capture.live.read";
    }
    return nullptr;
}

CompanionParseStatus parseScopes(JsonCursor* cursor,
                                 CompanionScopeMask* output) {
    if (cursor == nullptr || output == nullptr || !cursor->consume('[')) {
        return CompanionParseStatus::MalformedJson;
    }
    CompanionScopeMask scopes = 0;
    if (cursor->consume(']')) {
        return CompanionParseStatus::EmptyScopeSet;
    }
    while (true) {
        StringToken token{};
        if (!cursor->parseString(&token)) {
            return CompanionParseStatus::MalformedJson;
        }
        const CompanionScopeMask scope = scopeForToken(token);
        if (scope == 0) return CompanionParseStatus::UnknownScope;
        if ((scopes & scope) != 0) {
            return CompanionParseStatus::DuplicateScope;
        }
        scopes |= scope;
        if (cursor->consume(']')) break;
        if (!cursor->consume(',')) {
            return CompanionParseStatus::MalformedJson;
        }
    }
    *output = scopes;
    return CompanionParseStatus::Parsed;
}

constexpr CompanionScopeMask kTargetMutationScopes =
    companionScopeMask(CompanionScope::TargetRead) |
    companionScopeMask(CompanionScope::TargetMutate);

constexpr std::array<CompanionCapabilityDescriptor, 11> kCapabilities{{
    {"session.list", CompanionCapability::SessionList,
     companionScopeMask(CompanionScope::SessionRead),
     nullptr, 0, 0, true},
    {"session.detail", CompanionCapability::SessionDetail,
     companionScopeMask(CompanionScope::SessionRead),
     nullptr, 0, 0, true},
    {"target.list", CompanionCapability::TargetList,
     companionScopeMask(CompanionScope::TargetRead),
     nullptr, 0, 0, true},
    {"target.detail", CompanionCapability::TargetDetail,
     companionScopeMask(CompanionScope::TargetRead),
     nullptr, 0, 0, true},
    {"target.compare", CompanionCapability::TargetCompare,
     companionScopeMask(CompanionScope::SessionRead) |
         companionScopeMask(CompanionScope::TargetRead) |
         companionScopeMask(CompanionScope::TargetCompare),
     "target.compare", 1, 1, true},
    {"target.favorite.set", CompanionCapability::TargetFavoriteSet,
     kTargetMutationScopes, "target.favorite.set", 1, 1, false},
    {"target.name.set", CompanionCapability::TargetNameSet,
     kTargetMutationScopes, "target.name.set", 1, 1, false},
    {"target.notes.set", CompanionCapability::TargetNotesSet,
     kTargetMutationScopes, "target.notes.set", 1, 1, false},
    {"target.tag.add", CompanionCapability::TargetTagAdd,
     kTargetMutationScopes, "target.tag.add", 1, 1, false},
    {"target.tag.remove", CompanionCapability::TargetTagRemove,
     kTargetMutationScopes, "target.tag.remove", 1, 1, false},
    {"capture.live.wifi", CompanionCapability::CaptureLiveWifi,
     companionScopeMask(CompanionScope::CaptureLiveRead),
     nullptr, 0, 0, true},
}};

class BufferWriter final {
public:
    BufferWriter(char* output, std::size_t capacity)
        : output_(output), capacity_(capacity) {}

    bool append(const char* value) {
        return value != nullptr && append(value, std::strlen(value));
    }

    bool append(const char* value, std::size_t length) {
        if (failed_ || value == nullptr || length > capacity_ - size_) {
            failed_ = true;
            return false;
        }
        if (length != 0) std::memcpy(output_ + size_, value, length);
        size_ += length;
        return true;
    }

    bool appendQuoted(const char* value, std::size_t length) {
        return append("\"") && append(value, length) && append("\"");
    }

    bool appendSeparator(bool* first) {
        if (first == nullptr) return false;
        if (*first) {
            *first = false;
            return true;
        }
        return append(",");
    }

    bool finish(std::size_t* outputLength) {
        if (outputLength == nullptr || output_ == nullptr || failed_ ||
            size_ >= capacity_) {
            if (outputLength != nullptr) *outputLength = 0;
            return false;
        }
        output_[size_] = '\0';
        *outputLength = size_;
        return true;
    }

private:
    char* output_ = nullptr;
    std::size_t capacity_ = 0;
    std::size_t size_ = 0;
    bool failed_ = false;
};

bool scopeDependenciesSatisfied(CompanionScopeMask scopes) {
    const CompanionScopeMask compare =
        companionScopeMask(CompanionScope::TargetCompare);
    const CompanionScopeMask compareInputs =
        companionScopeMask(CompanionScope::SessionRead) |
        companionScopeMask(CompanionScope::TargetRead);
    if ((scopes & compare) != 0 && (scopes & compareInputs) != compareInputs) {
        return false;
    }
    const CompanionScopeMask mutate =
        companionScopeMask(CompanionScope::TargetMutate);
    if ((scopes & mutate) != 0 &&
        (scopes & companionScopeMask(CompanionScope::TargetRead)) == 0) {
        return false;
    }
    return true;
}

}  // namespace

const char* companionParseReason(CompanionParseStatus status) {
    switch (status) {
        case CompanionParseStatus::Parsed: return "none";
        case CompanionParseStatus::InvalidArgument: return "invalid_argument";
        case CompanionParseStatus::Empty: return "empty";
        case CompanionParseStatus::TooLarge: return "frame_too_large";
        case CompanionParseStatus::MalformedJson: return "malformed_json";
        case CompanionParseStatus::UnknownField: return "unknown_field";
        case CompanionParseStatus::DuplicateField: return "duplicate_field";
        case CompanionParseStatus::MissingField: return "missing_field";
        case CompanionParseStatus::UnsupportedSchema:
            return "unsupported_schema";
        case CompanionParseStatus::UnsupportedKind: return "unsupported_kind";
        case CompanionParseStatus::UnsupportedProtocol:
            return "unsupported_protocol";
        case CompanionParseStatus::InvalidRequestId: return "invalid_request_id";
        case CompanionParseStatus::UnknownScope: return "unknown_scope";
        case CompanionParseStatus::DuplicateScope: return "duplicate_scope";
        case CompanionParseStatus::EmptyScopeSet: return "empty_scope_set";
    }
    return "invalid_status";
}

CompanionParseStatus parseCompanionConnectRequest(
    const char* frame, std::size_t frameLength,
    CompanionConnectRequest* output) {
    if (frame == nullptr || output == nullptr) {
        return CompanionParseStatus::InvalidArgument;
    }
    if (frameLength == 0) return CompanionParseStatus::Empty;
    if (frameLength > kCompanionMaxFrameBytes) {
        return CompanionParseStatus::TooLarge;
    }

    JsonCursor cursor(frame, frameLength);
    if (!cursor.consume('{')) return CompanionParseStatus::MalformedJson;

    CompanionConnectRequest candidate{};
    StringToken schema{};
    StringToken kind{};
    StringToken requestId{};
    std::uint8_t fields = 0;
    if (cursor.consume('}')) return CompanionParseStatus::MissingField;

    while (true) {
        StringToken field{};
        if (!cursor.parseString(&field) || !cursor.consume(':')) {
            return CompanionParseStatus::MalformedJson;
        }
        std::uint8_t bit = 0;
        CompanionParseStatus status = CompanionParseStatus::Parsed;
        if (tokenEquals(field, "schema")) {
            bit = SchemaField;
            if (!cursor.parseString(&schema)) {
                return CompanionParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "kind")) {
            bit = KindField;
            if (!cursor.parseString(&kind)) {
                return CompanionParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "request_id")) {
            bit = RequestIdField;
            if (!cursor.parseString(&requestId)) {
                return CompanionParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "protocol")) {
            bit = ProtocolField;
            std::uint32_t protocol = 0;
            if (!cursor.parseUnsigned(&protocol)) {
                return CompanionParseStatus::MalformedJson;
            }
            candidate.protocolVersion = static_cast<std::uint16_t>(protocol);
        } else if (tokenEquals(field, "scopes")) {
            bit = ScopesField;
            status = parseScopes(&cursor, &candidate.requestedScopes);
            if (status != CompanionParseStatus::Parsed) return status;
        } else {
            return CompanionParseStatus::UnknownField;
        }
        if ((fields & bit) != 0) return CompanionParseStatus::DuplicateField;
        fields |= bit;
        if (cursor.consume('}')) break;
        if (!cursor.consume(',')) return CompanionParseStatus::MalformedJson;
    }
    if (!cursor.finished()) return CompanionParseStatus::MalformedJson;
    if (fields != kRequiredFields) return CompanionParseStatus::MissingField;
    if (!tokenEquals(schema, kCompanionRequestSchema)) {
        return CompanionParseStatus::UnsupportedSchema;
    }
    if (!tokenEquals(kind, "connect")) {
        return CompanionParseStatus::UnsupportedKind;
    }
    if (candidate.protocolVersion != kCompanionProtocolVersion) {
        return CompanionParseStatus::UnsupportedProtocol;
    }
    if (!validRequestId(requestId)) {
        return CompanionParseStatus::InvalidRequestId;
    }
    std::memcpy(candidate.requestId.data(), requestId.data, requestId.size);
    candidate.requestId[requestId.size] = '\0';
    candidate.requestIdLength = static_cast<std::uint8_t>(requestId.size);
    *output = candidate;
    return CompanionParseStatus::Parsed;
}

const char* companionConnectionReason(CompanionConnectionStatus status) {
    switch (status) {
        case CompanionConnectionStatus::Ready: return "none";
        case CompanionConnectionStatus::InvalidRequest: return "invalid_request";
        case CompanionConnectionStatus::ScopeDenied: return "scope_denied";
        case CompanionConnectionStatus::ScopeUnavailable:
            return "scope_unavailable";
        case CompanionConnectionStatus::ScopeDependencyMissing:
            return "scope_dependency_missing";
    }
    return "invalid_status";
}

CompanionConnection negotiateCompanionConnection(
    const CompanionConnectRequest& request,
    const CompanionConnectionPolicy& policy) {
    CompanionConnection connection{};
    connection.requestId = request.requestId;
    connection.requestIdLength = request.requestIdLength;
    if (request.protocolVersion != kCompanionProtocolVersion ||
        !validRequestId({request.requestId.data(), request.requestIdLength}) ||
        request.requestedScopes == 0 ||
        (request.requestedScopes & ~kCompanionKnownScopes) != 0) {
        connection.status = CompanionConnectionStatus::InvalidRequest;
        return connection;
    }
    if ((request.requestedScopes & ~policy.deviceSessionScopes) != 0) {
        connection.status = CompanionConnectionStatus::ScopeDenied;
        return connection;
    }
    if ((request.requestedScopes & ~policy.availableScopes) != 0) {
        connection.status = CompanionConnectionStatus::ScopeUnavailable;
        return connection;
    }
    if (!scopeDependenciesSatisfied(request.requestedScopes)) {
        connection.status =
            CompanionConnectionStatus::ScopeDependencyMissing;
        return connection;
    }
    connection.status = CompanionConnectionStatus::Ready;
    connection.grantedScopes = request.requestedScopes;
    const CompanionCapabilityMask availableCapabilities =
        policy.availableCapabilities & kCompanionKnownCapabilities;
    for (const CompanionCapabilityDescriptor& capability : kCapabilities) {
        if ((availableCapabilities &
             companionCapabilityMask(capability.capability)) != 0 &&
            (connection.grantedScopes & capability.requiredScopes) ==
                capability.requiredScopes) {
            connection.grantedCapabilities |=
                companionCapabilityMask(capability.capability);
        }
    }
    return connection;
}

std::size_t companionCapabilityCount() {
    return kCapabilities.size();
}

const CompanionCapabilityDescriptor* companionCapability(std::size_t index) {
    return index < kCapabilities.size() ? &kCapabilities[index] : nullptr;
}

bool companionCapabilityGranted(const CompanionCapabilityDescriptor& capability,
                                CompanionCapabilityMask grantedCapabilities,
                                CompanionScopeMask grantedScopes) {
    return capability.id != nullptr && capability.requiredScopes != 0 &&
        (grantedCapabilities & companionCapabilityMask(capability.capability)) != 0 &&
        (grantedScopes & capability.requiredScopes) == capability.requiredScopes;
}

bool encodeCompanionConnectResponse(
    const CompanionConnection& connection, CompanionTransport transport,
    char* output, std::size_t capacity, std::size_t* outputLength) {
    if (outputLength != nullptr) *outputLength = 0;
    if (output == nullptr || outputLength == nullptr || capacity == 0 ||
        connection.requestIdLength == 0 ||
        connection.requestIdLength > kCompanionRequestIdCapacity ||
        connection.requestId[connection.requestIdLength] != '\0' ||
        !validRequestId(
            {connection.requestId.data(), connection.requestIdLength}) ||
        (connection.ready() &&
         (connection.grantedScopes == 0 ||
          (connection.grantedScopes & ~kCompanionKnownScopes) != 0))) {
        return false;
    }
    std::array<char, kCompanionMaxFrameBytes + 1U> encoded{};
    BufferWriter writer(encoded.data(), encoded.size());
    writer.append("{\"schema\":\"");
    writer.append(kCompanionResponseSchema);
    writer.append("\",\"kind\":\"connect\",\"request_id\":");
    writer.appendQuoted(connection.requestId.data(), connection.requestIdLength);
    writer.append(",\"status\":\"");
    writer.append(connection.ready() ? "ready" : "denied");
    writer.append("\",\"reason\":\"");
    writer.append(companionConnectionReason(connection.status));
    writer.append("\",\"protocol\":1,\"transport\":\"");
    writer.append(transport == CompanionTransport::UsbSerial
                      ? "usb_serial_ndjson"
                      : "local_web_json");
    writer.append("\",\"scopes\":[");
    bool first = true;
    constexpr std::array<CompanionScope, 7> scopes{{
        CompanionScope::SessionRead,
        CompanionScope::TargetRead,
        CompanionScope::TargetCompare,
        CompanionScope::TargetMutate,
        CompanionScope::Export,
        CompanionScope::Connectivity,
        CompanionScope::CaptureLiveRead,
    }};
    if (connection.ready()) {
        for (const CompanionScope scope : scopes) {
            if ((connection.grantedScopes & companionScopeMask(scope)) == 0) {
                continue;
            }
            writer.appendSeparator(&first);
            const char* name = scopeName(scope);
            writer.appendQuoted(name, std::strlen(name));
        }
    }
    writer.append("],\"capabilities\":[");
    first = true;
    if (connection.ready()) {
        for (const CompanionCapabilityDescriptor& capability : kCapabilities) {
            if (!companionCapabilityGranted(
                    capability, connection.grantedCapabilities,
                    connection.grantedScopes)) {
                continue;
            }
            writer.appendSeparator(&first);
            writer.appendQuoted(capability.id, std::strlen(capability.id));
        }
    }
    writer.append("],\"max_frame_bytes\":512}\n");
    std::size_t encodedLength = 0;
    if (!writer.finish(&encodedLength) || encodedLength + 1U > capacity) {
        return false;
    }
    std::memcpy(output, encoded.data(), encodedLength + 1U);
    *outputLength = encodedLength;
    return true;
}

}  // namespace leshy1::services::companion
