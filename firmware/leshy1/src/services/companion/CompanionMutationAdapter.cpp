#include "CompanionMutationAdapter.h"

#include <array>
#include <cstdio>
#include <cstring>

namespace leshy1::services::companion {
namespace {

using leshy1::domain::targets::TargetMutationStatus;
using leshy1::services::targets::TargetActionKind;

struct StringToken final {
    const char* data = nullptr;
    std::size_t size = 0;
};

bool tokenEquals(const StringToken& token, const char* expected) {
    const std::size_t size = std::strlen(expected);
    return token.size == size &&
        std::memcmp(token.data, expected, size) == 0;
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
            if (value == '\\' || value < 0x20U || value > 0x7eU) {
                return false;
            }
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
            if (value > UINT32_MAX / 10U ||
                (value == UINT32_MAX / 10U &&
                 digit > UINT32_MAX % 10U)) {
                return false;
            }
            value = value * 10U + digit;
            ++offset_;
        }
        *output = value;
        return true;
    }

    bool parseBoolean(bool* output) {
        if (output == nullptr) return false;
        skipWhitespace();
        if (size_ - offset_ >= 4U &&
            std::memcmp(data_ + offset_, "true", 4) == 0) {
            *output = true;
            offset_ += 4U;
            return true;
        }
        if (size_ - offset_ >= 5U &&
            std::memcmp(data_ + offset_, "false", 5) == 0) {
            *output = false;
            offset_ += 5U;
            return true;
        }
        return false;
    }

    bool finished() {
        skipWhitespace();
        return offset_ == size_;
    }

private:
    const char* data_ = nullptr;
    std::size_t size_ = 0;
    std::size_t offset_ = 0;
};

enum Field : std::uint16_t {
    SchemaField = 1U << 0U,
    KindField = 1U << 1U,
    RequestIdField = 1U << 2U,
    ActionField = 1U << 3U,
    TargetIdField = 1U << 4U,
    ExpectedRevisionField = 1U << 5U,
    FavoriteField = 1U << 6U,
    ValueBase64Field = 1U << 7U,
    MutationIdField = 1U << 8U,
};

constexpr std::uint16_t kCommonFields =
    SchemaField | KindField | RequestIdField;

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

std::uint8_t hexNibble(char value) {
    if (value >= '0' && value <= '9') {
        return static_cast<std::uint8_t>(value - '0');
    }
    if (value >= 'a' && value <= 'f') {
        return static_cast<std::uint8_t>(value - 'a' + 10);
    }
    if (value >= 'A' && value <= 'F') {
        return static_cast<std::uint8_t>(value - 'A' + 10);
    }
    return 0xffU;
}

template <typename Id>
bool parseId(const StringToken& token, Id* output) {
    if (output == nullptr || token.size != Id::kSize * 2U) return false;
    Id candidate{};
    bool nonzero = false;
    for (std::size_t index = 0; index < Id::kSize; ++index) {
        const std::uint8_t high = hexNibble(token.data[index * 2U]);
        const std::uint8_t low = hexNibble(token.data[index * 2U + 1U]);
        if (high > 0x0fU || low > 0x0fU) return false;
        candidate.bytes[index] = static_cast<std::uint8_t>(
            (high << 4U) | low);
        nonzero = nonzero || candidate.bytes[index] != 0;
    }
    if (!nonzero) return false;
    *output = candidate;
    return true;
}

bool parseMutationId(const StringToken& token, CompanionMutationId* output) {
    if (output == nullptr || token.size != output->size() * 2U) return false;
    CompanionMutationId candidate{};
    bool nonzero = false;
    for (std::size_t index = 0; index < candidate.size(); ++index) {
        const std::uint8_t high = hexNibble(token.data[index * 2U]);
        const std::uint8_t low = hexNibble(token.data[index * 2U + 1U]);
        if (high > 0x0fU || low > 0x0fU) return false;
        candidate[index] = static_cast<std::uint8_t>((high << 4U) | low);
        nonzero = nonzero || candidate[index] != 0;
    }
    if (!nonzero) return false;
    *output = candidate;
    return true;
}

int base64Value(char value) {
    if (value >= 'A' && value <= 'Z') return value - 'A';
    if (value >= 'a' && value <= 'z') return value - 'a' + 26;
    if (value >= '0' && value <= '9') return value - '0' + 52;
    if (value == '+') return 62;
    if (value == '/') return 63;
    return -1;
}

bool decodeBase64(const StringToken& token, char* output,
                  std::size_t capacity, std::size_t* outputLength) {
    if (output == nullptr || outputLength == nullptr ||
        token.size % 4U != 0) {
        return false;
    }
    std::size_t written = 0;
    for (std::size_t offset = 0; offset < token.size; offset += 4U) {
        const bool last = offset + 4U == token.size;
        const int a = base64Value(token.data[offset]);
        const int b = base64Value(token.data[offset + 1U]);
        const bool padC = token.data[offset + 2U] == '=';
        const bool padD = token.data[offset + 3U] == '=';
        const int c = padC ? 0 : base64Value(token.data[offset + 2U]);
        const int d = padD ? 0 : base64Value(token.data[offset + 3U]);
        if (a < 0 || b < 0 || c < 0 || d < 0 ||
            (padC && !padD) || ((padC || padD) && !last) ||
            (padC && (b & 0x0f) != 0) ||
            (!padC && padD && (c & 0x03) != 0)) {
            return false;
        }
        const std::size_t bytes = padC ? 1U : padD ? 2U : 3U;
        if (bytes > capacity - written) return false;
        output[written++] = static_cast<char>((a << 2U) | (b >> 4U));
        if (bytes >= 2U) {
            output[written++] = static_cast<char>(
                ((b & 0x0f) << 4U) | (c >> 2U));
        }
        if (bytes == 3U) {
            output[written++] = static_cast<char>(
                ((c & 0x03) << 6U) | d);
        }
    }
    *outputLength = written;
    return true;
}

bool parseKind(const StringToken& token,
               CompanionMutationRequestKind* output) {
    if (output == nullptr) return false;
    if (tokenEquals(token, "target.mutation.preview")) {
        *output = CompanionMutationRequestKind::Preview;
    } else if (tokenEquals(token, "target.mutation.confirm")) {
        *output = CompanionMutationRequestKind::Confirm;
    } else if (tokenEquals(token, "target.mutation.status")) {
        *output = CompanionMutationRequestKind::Status;
    } else {
        return false;
    }
    return true;
}

bool parseAction(const StringToken& token, TargetActionKind* output) {
    if (output == nullptr) return false;
    if (tokenEquals(token, "target.favorite.set")) {
        *output = TargetActionKind::SetFavorite;
    } else if (tokenEquals(token, "target.name.set")) {
        *output = TargetActionKind::SetName;
    } else if (tokenEquals(token, "target.notes.set")) {
        *output = TargetActionKind::SetNotes;
    } else if (tokenEquals(token, "target.tag.add")) {
        *output = TargetActionKind::AddTag;
    } else if (tokenEquals(token, "target.tag.remove")) {
        *output = TargetActionKind::RemoveTag;
    } else {
        return false;
    }
    return true;
}

const char* requestKindName(CompanionMutationRequestKind kind) {
    switch (kind) {
        case CompanionMutationRequestKind::Preview:
            return "target.mutation.preview";
        case CompanionMutationRequestKind::Confirm:
            return "target.mutation.confirm";
        case CompanionMutationRequestKind::Status:
            return "target.mutation.status";
    }
    return "target.mutation.status";
}

const char* mutationStateName(CompanionMutationState state) {
    switch (state) {
        case CompanionMutationState::None: return "none";
        case CompanionMutationState::Previewed: return "previewed";
        case CompanionMutationState::Accepted: return "accepted";
        case CompanionMutationState::Saving: return "saving";
        case CompanionMutationState::Saved: return "saved";
        case CompanionMutationState::Failed: return "failed";
    }
    return "failed";
}

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

    bool appendUnsigned(std::uint64_t value) {
        char text[24] = {};
        const int written = std::snprintf(
            text, sizeof(text), "%llu",
            static_cast<unsigned long long>(value));
        return written > 0 && static_cast<std::size_t>(written) < sizeof(text) &&
            append(text, static_cast<std::size_t>(written));
    }

    template <typename Id>
    bool appendHex(const Id& id) {
        constexpr char kHex[] = "0123456789ABCDEF";
        for (const std::uint8_t value : id) {
            const char pair[2] = {kHex[value >> 4U], kHex[value & 0x0fU]};
            if (!append(pair, sizeof(pair))) return false;
        }
        return true;
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

bool responseTargetIdValid(const domain::targets::TargetId& id) {
    return domain::targets::targetIdValid(id);
}

bool successful(CompanionMutationStatus status) {
    return status == CompanionMutationStatus::Ready ||
        status == CompanionMutationStatus::Accepted ||
        status == CompanionMutationStatus::Saving ||
        status == CompanionMutationStatus::Saved;
}

}  // namespace

const char* companionMutationParseReason(
    CompanionMutationParseStatus status) {
    switch (status) {
        case CompanionMutationParseStatus::Parsed: return "none";
        case CompanionMutationParseStatus::InvalidArgument:
            return "invalid_argument";
        case CompanionMutationParseStatus::Empty: return "empty";
        case CompanionMutationParseStatus::TooLarge: return "frame_too_large";
        case CompanionMutationParseStatus::MalformedJson:
            return "malformed_json";
        case CompanionMutationParseStatus::UnknownField:
            return "unknown_field";
        case CompanionMutationParseStatus::DuplicateField:
            return "duplicate_field";
        case CompanionMutationParseStatus::MissingField:
            return "missing_field";
        case CompanionMutationParseStatus::UnsupportedSchema:
            return "unsupported_schema";
        case CompanionMutationParseStatus::UnsupportedKind:
            return "unsupported_kind";
        case CompanionMutationParseStatus::InvalidRequestId:
            return "invalid_request_id";
        case CompanionMutationParseStatus::InvalidIdentifier:
            return "invalid_identifier";
        case CompanionMutationParseStatus::InvalidNumber:
            return "invalid_number";
        case CompanionMutationParseStatus::InvalidAction:
            return "invalid_action";
        case CompanionMutationParseStatus::InvalidBase64:
            return "invalid_base64";
        case CompanionMutationParseStatus::InvalidValue:
            return "invalid_value";
        case CompanionMutationParseStatus::FieldNotAllowed:
            return "field_not_allowed";
    }
    return "invalid_status";
}

CompanionMutationParseStatus parseCompanionMutationRequest(
    const char* frame, std::size_t frameLength,
    CompanionMutationRequest* output) {
    if (frame == nullptr || output == nullptr) {
        return CompanionMutationParseStatus::InvalidArgument;
    }
    if (frameLength == 0) return CompanionMutationParseStatus::Empty;
    if (frameLength > kCompanionMaxFrameBytes) {
        return CompanionMutationParseStatus::TooLarge;
    }
    JsonCursor cursor(frame, frameLength);
    if (!cursor.consume('{')) {
        return CompanionMutationParseStatus::MalformedJson;
    }

    CompanionMutationRequest candidate{};
    StringToken schema{};
    StringToken kind{};
    StringToken requestId{};
    StringToken action{};
    StringToken targetId{};
    StringToken valueBase64{};
    StringToken mutationId{};
    bool favorite = false;
    std::uint32_t expectedRevision = 0;
    std::uint16_t fields = 0;
    if (cursor.consume('}')) {
        return CompanionMutationParseStatus::MissingField;
    }
    while (true) {
        StringToken field{};
        if (!cursor.parseString(&field) || !cursor.consume(':')) {
            return CompanionMutationParseStatus::MalformedJson;
        }
        std::uint16_t bit = 0;
        if (tokenEquals(field, "schema")) {
            bit = SchemaField;
            if (!cursor.parseString(&schema)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "kind")) {
            bit = KindField;
            if (!cursor.parseString(&kind)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "request_id")) {
            bit = RequestIdField;
            if (!cursor.parseString(&requestId)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "action")) {
            bit = ActionField;
            if (!cursor.parseString(&action)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "target_id")) {
            bit = TargetIdField;
            if (!cursor.parseString(&targetId)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "expected_revision")) {
            bit = ExpectedRevisionField;
            if (!cursor.parseUnsigned(&expectedRevision)) {
                return CompanionMutationParseStatus::InvalidNumber;
            }
        } else if (tokenEquals(field, "favorite")) {
            bit = FavoriteField;
            if (!cursor.parseBoolean(&favorite)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "value_base64")) {
            bit = ValueBase64Field;
            if (!cursor.parseString(&valueBase64)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "mutation_id")) {
            bit = MutationIdField;
            if (!cursor.parseString(&mutationId)) {
                return CompanionMutationParseStatus::MalformedJson;
            }
        } else {
            return CompanionMutationParseStatus::UnknownField;
        }
        if ((fields & bit) != 0) {
            return CompanionMutationParseStatus::DuplicateField;
        }
        fields |= bit;
        if (cursor.consume('}')) break;
        if (!cursor.consume(',')) {
            return CompanionMutationParseStatus::MalformedJson;
        }
    }
    if (!cursor.finished()) {
        return CompanionMutationParseStatus::MalformedJson;
    }
    if ((fields & kCommonFields) != kCommonFields) {
        return CompanionMutationParseStatus::MissingField;
    }
    if (!tokenEquals(schema, kCompanionRequestSchema)) {
        return CompanionMutationParseStatus::UnsupportedSchema;
    }
    if (!parseKind(kind, &candidate.kind)) {
        return CompanionMutationParseStatus::UnsupportedKind;
    }
    if (!validRequestId(requestId)) {
        return CompanionMutationParseStatus::InvalidRequestId;
    }
    std::memcpy(candidate.requestId.data(), requestId.data, requestId.size);
    candidate.requestId[requestId.size] = '\0';
    candidate.requestIdLength = static_cast<std::uint8_t>(requestId.size);

    if (candidate.kind == CompanionMutationRequestKind::Preview) {
        const std::uint16_t previewBase = kCommonFields | ActionField |
            TargetIdField | ExpectedRevisionField;
        if ((fields & previewBase) != previewBase) {
            return CompanionMutationParseStatus::MissingField;
        }
        if (!parseAction(action, &candidate.action.kind)) {
            return CompanionMutationParseStatus::InvalidAction;
        }
        if (!parseId(targetId, &candidate.action.targetId)) {
            return CompanionMutationParseStatus::InvalidIdentifier;
        }
        if (expectedRevision == 0) {
            return CompanionMutationParseStatus::InvalidNumber;
        }
        candidate.action.expectedRevision = expectedRevision;
        const bool favoriteAction =
            candidate.action.kind == TargetActionKind::SetFavorite;
        const std::uint16_t required = previewBase |
            (favoriteAction ? FavoriteField : ValueBase64Field);
        if (fields != required) {
            return (fields & required) == required
                ? CompanionMutationParseStatus::FieldNotAllowed
                : CompanionMutationParseStatus::MissingField;
        }
        if (favoriteAction) {
            candidate.action.favorite = favorite;
        } else {
            std::array<char,
                services::targets::TargetAction::kTextCapacity + 1U> decoded{};
            std::size_t decodedLength = 0;
            if (!decodeBase64(valueBase64, decoded.data(),
                              decoded.size() - 1U, &decodedLength)) {
                return CompanionMutationParseStatus::InvalidBase64;
            }
            const std::size_t maximum =
                candidate.action.kind == TargetActionKind::SetName
                    ? domain::targets::TargetRecord::kNameCapacity
                    : (candidate.action.kind == TargetActionKind::AddTag ||
                       candidate.action.kind == TargetActionKind::RemoveTag)
                          ? domain::targets::TargetRecord::kTagCapacity
                          : domain::targets::TargetRecord::kNotesCapacity;
            const bool tagAction =
                candidate.action.kind == TargetActionKind::AddTag ||
                candidate.action.kind == TargetActionKind::RemoveTag;
            if (decodedLength > maximum || (tagAction && decodedLength == 0) ||
                !services::targets::setTargetActionText(
                    &candidate.action, decoded.data(), decodedLength)) {
                return CompanionMutationParseStatus::InvalidValue;
            }
        }
    } else {
        const std::uint16_t required = kCommonFields | MutationIdField;
        if (fields != required) {
            return (fields & required) == required
                ? CompanionMutationParseStatus::FieldNotAllowed
                : CompanionMutationParseStatus::MissingField;
        }
        if (!parseMutationId(mutationId, &candidate.mutationId)) {
            return CompanionMutationParseStatus::InvalidIdentifier;
        }
    }
    *output = candidate;
    return CompanionMutationParseStatus::Parsed;
}

CompanionCapability companionCapabilityForTargetAction(
    TargetActionKind kind) {
    switch (kind) {
        case TargetActionKind::SetFavorite:
            return CompanionCapability::TargetFavoriteSet;
        case TargetActionKind::SetName:
            return CompanionCapability::TargetNameSet;
        case TargetActionKind::SetNotes:
            return CompanionCapability::TargetNotesSet;
        case TargetActionKind::AddTag:
            return CompanionCapability::TargetTagAdd;
        case TargetActionKind::RemoveTag:
            return CompanionCapability::TargetTagRemove;
        case TargetActionKind::Create:
        case TargetActionKind::AttachEvidence:
            return CompanionCapability::SessionList;
    }
    return CompanionCapability::SessionList;
}

CompanionCapabilityMask companionMutationCapabilities(
    const domain::targets::TargetCatalog* targets) {
    return targets == nullptr ? 0 : kCompanionTargetMutationCapabilities;
}

const char* companionMutationReason(CompanionMutationStatus status) {
    switch (status) {
        case CompanionMutationStatus::Ready: return "none";
        case CompanionMutationStatus::Accepted: return "none";
        case CompanionMutationStatus::Saving: return "none";
        case CompanionMutationStatus::Saved: return "none";
        case CompanionMutationStatus::InvalidRequest: return "invalid_request";
        case CompanionMutationStatus::NotConnected: return "not_connected";
        case CompanionMutationStatus::CapabilityDenied:
            return "capability_denied";
        case CompanionMutationStatus::CapabilityUnavailable:
            return "capability_unavailable";
        case CompanionMutationStatus::NotFound: return "not_found";
        case CompanionMutationStatus::RevisionConflict:
            return "revision_conflict";
        case CompanionMutationStatus::InvalidValue: return "invalid_value";
        case CompanionMutationStatus::Unchanged: return "unchanged";
        case CompanionMutationStatus::UnknownMutation:
            return "unknown_mutation";
        case CompanionMutationStatus::Busy: return "busy";
        case CompanionMutationStatus::AlreadyConfirmed:
            return "already_confirmed";
        case CompanionMutationStatus::Failed: return "mutation_failed";
    }
    return "invalid_status";
}

CompanionMutationAssessment assessCompanionMutationPreview(
    const CompanionConnection& connection,
    const domain::targets::TargetCatalog* targets,
    const CompanionMutationRequest& request) {
    CompanionMutationAssessment assessment{};
    assessment.action.kind = request.action.kind;
    assessment.action.targetId = request.action.targetId;
    if (request.kind != CompanionMutationRequestKind::Preview) {
        return assessment;
    }
    if (!connection.ready()) {
        assessment.status = CompanionMutationStatus::NotConnected;
        return assessment;
    }
    const CompanionCapability capability =
        companionCapabilityForTargetAction(request.action.kind);
    const CompanionCapabilityMask capabilityBit =
        companionCapabilityMask(capability);
    if ((connection.grantedScopes & kCompanionS65MutationScopes) !=
            kCompanionS65MutationScopes ||
        (connection.grantedCapabilities & capabilityBit) == 0) {
        assessment.status = CompanionMutationStatus::CapabilityDenied;
        return assessment;
    }
    if (targets == nullptr) {
        assessment.status = CompanionMutationStatus::CapabilityUnavailable;
        return assessment;
    }
    assessment.action = services::targets::previewTargetAction(
        *targets, request.action);
    switch (assessment.action.status) {
        case TargetMutationStatus::Applied:
            assessment.status = CompanionMutationStatus::Ready;
            break;
        case TargetMutationStatus::NotFound:
            assessment.status = CompanionMutationStatus::NotFound;
            break;
        case TargetMutationStatus::RevisionConflict:
            assessment.status = CompanionMutationStatus::RevisionConflict;
            break;
        case TargetMutationStatus::Unchanged:
            assessment.status = CompanionMutationStatus::Unchanged;
            break;
        default:
            assessment.status = CompanionMutationStatus::InvalidValue;
            break;
    }
    return assessment;
}

bool companionMutationIdValid(const CompanionMutationId& id) {
    for (const std::uint8_t value : id) {
        if (value != 0) return true;
    }
    return false;
}

bool encodeCompanionMutationResponse(
    const CompanionMutationResponse& response,
    char* output, std::size_t capacity, std::size_t* outputLength) {
    if (outputLength != nullptr) *outputLength = 0;
    if (output == nullptr || outputLength == nullptr || capacity == 0 ||
        response.requestIdLength == 0 ||
        response.requestIdLength > kCompanionRequestIdCapacity ||
        response.requestId[response.requestIdLength] != '\0' ||
        !validRequestId(
            {response.requestId.data(), response.requestIdLength})) {
        return false;
    }
    std::array<char, kCompanionMaxFrameBytes + 1U> scratch{};
    BufferWriter writer(scratch.data(), scratch.size());
    writer.append("{\"schema\":\"");
    writer.append(kCompanionResponseSchema);
    writer.append("\",\"kind\":\"");
    writer.append(requestKindName(response.kind));
    writer.append("\",\"request_id\":\"");
    writer.append(response.requestId.data(), response.requestIdLength);
    writer.append("\",\"status\":\"");
    writer.append(successful(response.status) ? "ok" : "error");
    writer.append("\",\"reason\":\"");
    writer.append(companionMutationReason(response.status));
    writer.append("\",\"state\":\"");
    writer.append(mutationStateName(response.state));
    writer.append("\"");
    if (companionMutationIdValid(response.mutationId)) {
        writer.append(",\"mutation_id\":\"");
        writer.appendHex(response.mutationId);
        writer.append("\"");
    }
    if (responseTargetIdValid(response.targetId)) {
        const auto* descriptor =
            services::targets::targetActionDescriptor(response.actionKind);
        writer.append(",\"action\":\"");
        writer.append(descriptor == nullptr ? "unknown" : descriptor->id);
        writer.append("\",\"target_id\":\"");
        writer.appendHex(response.targetId.bytes);
        writer.append("\",\"expected_revision\":");
        writer.appendUnsigned(response.expectedRevision);
        writer.append(",\"target_revision\":");
        writer.appendUnsigned(response.targetRevision);
        writer.append(",\"state_generation\":");
        writer.appendUnsigned(response.stateGeneration);
    }
    writer.append("}\n");
    std::size_t size = 0;
    if (!writer.finish(&size) || size + 1U > capacity) return false;
    std::memcpy(output, scratch.data(), size + 1U);
    *outputLength = size;
    return true;
}

bool encodeCompanionMutationParseError(
    CompanionMutationParseStatus status, char* output,
    std::size_t capacity, std::size_t* outputLength) {
    if (outputLength != nullptr) *outputLength = 0;
    if (output == nullptr || outputLength == nullptr) return false;
    std::array<char, 192> scratch{};
    const int length = std::snprintf(
        scratch.data(), scratch.size(),
        "{\"schema\":\"%s\",\"kind\":\"error\",\"request_id\":\"\","
        "\"status\":\"error\",\"reason\":\"%s\"}\n",
        kCompanionResponseSchema, companionMutationParseReason(status));
    if (length <= 0 || static_cast<std::size_t>(length) >= scratch.size() ||
        static_cast<std::size_t>(length) + 1U > capacity) {
        return false;
    }
    std::memcpy(output, scratch.data(), static_cast<std::size_t>(length) + 1U);
    *outputLength = static_cast<std::size_t>(length);
    return true;
}

}  // namespace leshy1::services::companion
