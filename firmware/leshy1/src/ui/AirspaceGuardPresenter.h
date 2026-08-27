#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/guard/AirspaceGuardController.h"
#include "ui/UiStrings.h"

namespace leshy1::ui {

enum class AirspaceGuardUiTone : std::uint8_t {
    Neutral,
    Healthy,
    Caution,
    Finding,
    Error,
};

struct AirspaceGuardUiRow final {
    static constexpr std::size_t kTextCapacity = 64;

    std::array<char, kTextCapacity> text{};
    bool selected = false;
};

// Allocation-free, renderer-independent product screen. Four rows match the
// established touch geometry; text always carries the meaning, so tone is never
// the only indication of a finding, incomplete evidence or error.
struct AirspaceGuardUiModel final {
    static constexpr std::size_t kVisibleRowCapacity = 4;
    static constexpr std::size_t kContextCapacity = 64;

    UiTextId title = UiTextId::AirspaceGuardTitle;
    UiTextId headline = UiTextId::AirspaceGuardReportRejected;
    UiTextId note = UiTextId::AirspaceGuardPassiveOnly;
    AirspaceGuardUiTone tone = AirspaceGuardUiTone::Error;
    std::array<char, kContextCapacity> context{};
    std::array<AirspaceGuardUiRow, kVisibleRowCapacity> rows{};
    std::size_t rowCount = 0;
    bool openable = false;
    bool evidenceIncomplete = false;
};

AirspaceGuardUiModel presentAirspaceGuard(
    const apps::guard::AirspaceGuardController& controller,
    UiLanguage language);

}  // namespace leshy1::ui
