#pragma once

#include <cstddef>
#include <cstdint>

#include "services/serial/SerialConsoleContract.h"

namespace leshy1::services::actions {

constexpr std::size_t kActionsCliMaximumLineLength = 256U;

enum class ActionsCliRequestKind : std::uint8_t {
    Preview,
    Run,
    Status,
    Cancel,
};

enum class ActionsCliParseStatus : std::uint8_t {
    Parsed,
    Empty,
    TooLarge,
    Malformed,
    UnsupportedCommand,
    UnsupportedAction,
    UnknownField,
    DuplicateField,
    MissingField,
    InvalidValue,
    ConfirmationRequired,
};

const char* actionsCliParseStatusName(ActionsCliParseStatus status);

struct ActionsCliRequest final {
    ActionsCliRequestKind kind = ActionsCliRequestKind::Preview;
    serial::SerialConsoleConfig serialConfig{};
    bool confirmed = false;
};

// One strict, allocation-free transport adapter for the same typed Action used
// by the on-device UI. Unknown fields fail closed; there is intentionally no
// arbitrary GPIO command or pin-number field.
ActionsCliParseStatus parseActionsCliRequest(
    const char* line, std::size_t length, ActionsCliRequest* output);

}  // namespace leshy1::services::actions
