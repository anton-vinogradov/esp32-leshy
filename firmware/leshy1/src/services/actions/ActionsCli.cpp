#include "ActionsCli.h"

#include <array>
#include <climits>
#include <cstring>

namespace leshy1::services::actions {
namespace {

struct Token final {
    const char* data = nullptr;
    std::size_t length = 0;
};

constexpr std::size_t kMaximumTokens = 10U;

bool equals(const Token& token, const char* value) {
    const std::size_t length = std::strlen(value);
    return token.length == length &&
        std::memcmp(token.data, value, length) == 0;
}

bool splitField(const Token& token, Token* key, Token* value) {
    if (key == nullptr || value == nullptr) return false;
    for (std::size_t index = 0; index < token.length; ++index) {
        if (token.data[index] != '=') continue;
        if (index == 0U || index + 1U >= token.length) return false;
        key->data = token.data;
        key->length = index;
        value->data = token.data + index + 1U;
        value->length = token.length - index - 1U;
        return true;
    }
    return false;
}

bool parseUnsigned(const Token& token, std::uint32_t* output) {
    if (output == nullptr || token.length == 0U ||
        (token.length > 1U && token.data[0] == '0')) {
        return false;
    }
    std::uint32_t value = 0;
    for (std::size_t index = 0; index < token.length; ++index) {
        const char character = token.data[index];
        if (character < '0' || character > '9') return false;
        const std::uint32_t digit =
            static_cast<std::uint32_t>(character - '0');
        if (value > UINT32_MAX / 10U ||
            (value == UINT32_MAX / 10U && digit > UINT32_MAX % 10U)) {
            return false;
        }
        value = value * 10U + digit;
    }
    *output = value;
    return true;
}

enum Field : std::uint8_t {
    ProfileField = 1U << 0U,
    TargetField = 1U << 1U,
    BaudField = 1U << 2U,
    FramingField = 1U << 3U,
    ModeField = 1U << 4U,
    DurationField = 1U << 5U,
    ConfirmField = 1U << 6U,
};

constexpr std::uint8_t kConfigurationFields =
    ProfileField | TargetField | BaudField | FramingField | ModeField |
    DurationField;

ActionsCliParseStatus parseConfigurationField(
    const Token& key, const Token& value, std::uint8_t* fields,
    ActionsCliRequest* request) {
    if (fields == nullptr || request == nullptr) {
        return ActionsCliParseStatus::Malformed;
    }
    std::uint8_t field = 0;
    if (equals(key, "profile")) field = ProfileField;
    else if (equals(key, "target")) field = TargetField;
    else if (equals(key, "baud")) field = BaudField;
    else if (equals(key, "framing")) field = FramingField;
    else if (equals(key, "mode")) field = ModeField;
    else if (equals(key, "duration_ms")) field = DurationField;
    else if (equals(key, "confirm")) field = ConfirmField;
    else return ActionsCliParseStatus::UnknownField;
    if ((*fields & field) != 0U) {
        return ActionsCliParseStatus::DuplicateField;
    }
    *fields = static_cast<std::uint8_t>(*fields | field);

    if (field == ProfileField) {
        if (!equals(value, "mux56-3v3")) {
            return ActionsCliParseStatus::InvalidValue;
        }
        request->serialConfig.pinProfile =
            serial::SerialConsolePinProfile::Mux56_3v3;
    } else if (field == TargetField) {
        if (!serial::setSerialConsoleTarget(
                &request->serialConfig, value.data, value.length)) {
            return ActionsCliParseStatus::InvalidValue;
        }
    } else if (field == BaudField) {
        if (!parseUnsigned(value, &request->serialConfig.baud)) {
            return ActionsCliParseStatus::InvalidValue;
        }
    } else if (field == FramingField) {
        if (equals(value, "8N1")) {
            request->serialConfig.framing =
                serial::SerialConsoleFraming::Data8None1;
        } else if (equals(value, "8E1")) {
            request->serialConfig.framing =
                serial::SerialConsoleFraming::Data8Even1;
        } else if (equals(value, "8O1")) {
            request->serialConfig.framing =
                serial::SerialConsoleFraming::Data8Odd1;
        } else if (equals(value, "8N2")) {
            request->serialConfig.framing =
                serial::SerialConsoleFraming::Data8None2;
        } else {
            return ActionsCliParseStatus::InvalidValue;
        }
    } else if (field == ModeField) {
        if (equals(value, "monitor")) {
            request->serialConfig.mode =
                serial::SerialConsoleMode::Monitor;
        } else if (equals(value, "bridge")) {
            request->serialConfig.mode =
                serial::SerialConsoleMode::Bridge;
        } else {
            return ActionsCliParseStatus::InvalidValue;
        }
    } else if (field == DurationField) {
        if (!parseUnsigned(value, &request->serialConfig.durationMs)) {
            return ActionsCliParseStatus::InvalidValue;
        }
    } else if (field == ConfirmField) {
        if (!equals(value, "yes")) {
            return ActionsCliParseStatus::InvalidValue;
        }
        request->confirmed = true;
    }
    return ActionsCliParseStatus::Parsed;
}

}  // namespace

const char* actionsCliParseStatusName(ActionsCliParseStatus status) {
    switch (status) {
        case ActionsCliParseStatus::Parsed: return "parsed";
        case ActionsCliParseStatus::Empty: return "empty";
        case ActionsCliParseStatus::TooLarge: return "too_large";
        case ActionsCliParseStatus::Malformed: return "malformed";
        case ActionsCliParseStatus::UnsupportedCommand:
            return "unsupported_command";
        case ActionsCliParseStatus::UnsupportedAction:
            return "unsupported_action";
        case ActionsCliParseStatus::UnknownField: return "unknown_field";
        case ActionsCliParseStatus::DuplicateField:
            return "duplicate_field";
        case ActionsCliParseStatus::MissingField: return "missing_field";
        case ActionsCliParseStatus::InvalidValue: return "invalid_value";
        case ActionsCliParseStatus::ConfirmationRequired:
            return "confirmation_required";
    }
    return "invalid_status";
}

ActionsCliParseStatus parseActionsCliRequest(
    const char* line, std::size_t length, ActionsCliRequest* output) {
    if (line == nullptr || output == nullptr) {
        return ActionsCliParseStatus::Malformed;
    }
    if (length == 0U) return ActionsCliParseStatus::Empty;
    if (length > kActionsCliMaximumLineLength) {
        return ActionsCliParseStatus::TooLarge;
    }
    std::array<Token, kMaximumTokens> tokens{};
    std::size_t tokenCount = 0;
    std::size_t offset = 0;
    while (offset < length) {
        if (line[offset] == ' ' || line[offset] == '\t' ||
            line[offset] == '\r' || line[offset] == '\n') {
            return ActionsCliParseStatus::Malformed;
        }
        const std::size_t start = offset;
        while (offset < length && line[offset] != ' ') ++offset;
        if (tokenCount >= tokens.size()) {
            return ActionsCliParseStatus::TooLarge;
        }
        tokens[tokenCount++] = {line + start, offset - start};
        if (offset < length) ++offset;
    }
    if (tokenCount < 2U) return ActionsCliParseStatus::Malformed;

    ActionsCliRequest request{};
    if (equals(tokens[0], "action.preview")) {
        request.kind = ActionsCliRequestKind::Preview;
    } else if (equals(tokens[0], "action.run")) {
        request.kind = ActionsCliRequestKind::Run;
    } else if (equals(tokens[0], "action.status")) {
        request.kind = ActionsCliRequestKind::Status;
    } else if (equals(tokens[0], "action.cancel")) {
        request.kind = ActionsCliRequestKind::Cancel;
    } else {
        return ActionsCliParseStatus::UnsupportedCommand;
    }
    if (!equals(tokens[1], "serial.console.start")) {
        return ActionsCliParseStatus::UnsupportedAction;
    }
    if (request.kind == ActionsCliRequestKind::Status ||
        request.kind == ActionsCliRequestKind::Cancel) {
        if (tokenCount != 2U) return ActionsCliParseStatus::UnknownField;
        *output = request;
        return ActionsCliParseStatus::Parsed;
    }

    std::uint8_t fields = 0;
    for (std::size_t index = 2U; index < tokenCount; ++index) {
        Token key{};
        Token value{};
        if (!splitField(tokens[index], &key, &value)) {
            return ActionsCliParseStatus::Malformed;
        }
        const ActionsCliParseStatus fieldStatus =
            parseConfigurationField(key, value, &fields, &request);
        if (fieldStatus != ActionsCliParseStatus::Parsed) return fieldStatus;
    }
    if ((fields & kConfigurationFields) != kConfigurationFields) {
        return ActionsCliParseStatus::MissingField;
    }
    if (request.kind == ActionsCliRequestKind::Preview &&
        (fields & ConfirmField) != 0U) {
        return ActionsCliParseStatus::UnknownField;
    }
    if (request.kind == ActionsCliRequestKind::Run && !request.confirmed) {
        return ActionsCliParseStatus::ConfirmationRequired;
    }
    *output = request;
    return ActionsCliParseStatus::Parsed;
}

}  // namespace leshy1::services::actions
