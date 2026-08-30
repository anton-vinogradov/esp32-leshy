#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/security/DeviceLock.h"

namespace leshy1::apps::device {

enum class DeviceLockView : std::uint8_t {
    Status,
    EnterPin,
    ConfirmPin,
    Working,
};

enum class DeviceLockIntent : std::uint8_t {
    None,
    Configure,
    Unlock,
};

enum class DeviceLockUiOutcome : std::uint8_t {
    None,
    Configured,
    Unlocked,
    Locked,
    PinMismatch,
    WeakPin,
    Failed,
};

enum class DeviceLockActivation : std::uint8_t {
    None,
    EditorOpened,
    LockRequested,
};

struct DeviceLockSubmission final {
    DeviceLockIntent intent = DeviceLockIntent::None;
    std::array<char,
               services::security::kDeviceLockMaximumPinDigits + 1U> pin{};
    std::size_t pinLength = 0;

    void clear();
};

// Allocation-free, six-digit product editor. The security core deliberately
// accepts 6..12 digits for future companion/CLI entry; the five-key device UI
// starts with the smallest usable shape so every digit remains legible.
class DeviceLockController final {
public:
    static constexpr std::size_t kProductPinDigits =
        services::security::kDeviceLockMinimumPinDigits;

    void enter(const services::security::DeviceLockAudit& audit);
    DeviceLockActivation activate();
    bool previousDigit();
    bool nextDigit();
    bool advance();
    bool cancel();
    bool takeSubmission(DeviceLockSubmission* output);
    void complete(const services::security::DeviceLockAudit& audit,
                  bool success);
    void noteLocked(const services::security::DeviceLockAudit& audit);

    DeviceLockView view() const { return view_; }
    DeviceLockIntent intent() const { return intent_; }
    DeviceLockUiOutcome outcome() const { return outcome_; }
    services::security::DeviceLockAudit audit() const { return audit_; }
    std::size_t cursor() const { return cursor_; }
    std::uint8_t digit() const {
        return static_cast<std::uint8_t>(pin_[cursor_] - '0');
    }
    bool submissionReady() const { return submissionReady_; }

    // Rendering never receives PIN bytes. It can draw one masked cell per
    // position and expose only the currently edited digit.
    bool positionEntered(std::size_t index) const {
        return index < cursor_ ||
            ((view_ == DeviceLockView::ConfirmPin) && index < cursor_);
    }

private:
    static void secureClear(char* bytes, std::size_t size);
    void resetEditor();
    bool finishEntry();

    DeviceLockView view_ = DeviceLockView::Status;
    DeviceLockIntent intent_ = DeviceLockIntent::None;
    DeviceLockUiOutcome outcome_ = DeviceLockUiOutcome::None;
    services::security::DeviceLockAudit audit_{};
    std::array<char, kProductPinDigits + 1U> pin_{};
    std::array<char, kProductPinDigits + 1U> firstPin_{};
    DeviceLockSubmission submission_{};
    std::size_t cursor_ = 0;
    bool submissionReady_ = false;
};

}  // namespace leshy1::apps::device
