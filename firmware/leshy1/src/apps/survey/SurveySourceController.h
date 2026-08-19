#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/hardware/HardwareInventory.h"

namespace leshy1::apps::survey {

enum class SurveySetupView : std::uint8_t {
    Plan,
    Sources,
};

enum class SurveySourceKind : std::uint8_t {
    Wifi,
    Ble,
};

enum class SurveySourceScope : std::uint8_t {
    All,
    WifiOnly,
    BleOnly,
};

enum class SurveySourceState : std::uint8_t {
    Available,
    Unavailable,
    Conflicted,
    Fault,
};

enum class SurveySetupActivation : std::uint8_t {
    None,
    OpenedSources,
    OpenedSpectrum,
    SourceChanged,
    SourceUnavailable,
    StartRequested,
    StartBlocked,
};

const char* surveySetupViewName(SurveySetupView view);
const char* surveySourceKindName(SurveySourceKind kind);
const char* surveySourceScopeName(SurveySourceScope scope);
const char* surveySourceStateName(SurveySourceState state);
const char* surveySetupActivationName(SurveySetupActivation activation);

struct SurveySourceOption final {
    const char* id = nullptr;
    SurveySourceKind kind = SurveySourceKind::Wifi;
    SurveySourceState state = SurveySourceState::Unavailable;
    const char* reason = nullptr;
    bool selected = false;

    bool available() const { return state == SurveySourceState::Available; }
};

// Allocation-free draft plan for UX-S02. Availability is projected from the
// boot inventory, while selection remains a user choice. A source can never be
// selected merely because it was declared or detected.
class SurveySourceController final {
public:
    static constexpr std::size_t kSourceCount = 2;
    static constexpr std::uint8_t kPlanItemCount = 3;

    void rebuild(const domain::hardware::HardwareInventory& inventory,
                 bool simulatedPreview = false,
                 SurveySourceScope scope = SurveySourceScope::All);

    bool previous();
    bool next();
    SurveySetupActivation activate();
    bool back();

    SurveySetupView view() const { return view_; }
    std::uint8_t selection() const { return selection_; }
    const SurveySourceOption* get(std::size_t index) const;
    const SurveySourceOption* find(SurveySourceKind kind) const;
    std::size_t selectedCount() const;
    std::uint8_t selectedMask() const;
    bool canStart() const { return selectedCount() != 0 || simulatedPreview_; }
    bool simulatedPreview() const { return simulatedPreview_; }
    SurveySourceScope scope() const { return scope_; }
    std::uint8_t planItemCount() const {
        return scope_ == SurveySourceScope::All ? kPlanItemCount : 1U;
    }

private:
    std::array<SurveySourceOption, kSourceCount> sources_{};
    SurveySetupView view_ = SurveySetupView::Plan;
    std::uint8_t selection_ = 0;
    bool simulatedPreview_ = false;
    SurveySourceScope scope_ = SurveySourceScope::All;
};

}  // namespace leshy1::apps::survey
