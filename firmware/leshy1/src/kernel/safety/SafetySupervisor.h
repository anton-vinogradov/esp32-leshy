#pragma once

#include <cstdint>

namespace leshy1::kernel::safety {

constexpr std::uint32_t kSafetyRetainedMagic = 0x4C534631U;
constexpr std::uint32_t kSafetyRetainedSchema = 2U;

enum class SafetyReason : std::uint32_t {
    None = 0,
    RuntimeWatchdog = 1,
    SupervisorUnavailable = 2,
    OutputInvariant = 3,
    WorkerDeadline = 4,
};

enum class SafetyState : std::uint8_t {
    Startup,
    Armed,
    Latched,
    ClearPending,
};

// The retained record uses value/complement pairs so a reset during an ISR
// update cannot turn a torn write into a valid safety event.
struct SafetyRetainedRecord final {
    std::uint32_t magic;
    std::uint32_t schema;
    std::uint32_t appIdentity;
    std::uint32_t appIdentityInverse;
    std::uint32_t reason;
    std::uint32_t reasonInverse;
    std::uint32_t tripCount;
    std::uint32_t tripCountInverse;
    std::uint32_t quiesceCount;
    std::uint32_t quiesceCountInverse;
    // Zero means the ISR record has not yet been accepted after its matching
    // watchdog reset. The ISR preloads latchConfirmedInverse with ~1 so task
    // context confirms the latch with one aligned 32-bit store and no invalid
    // intermediate record.
    std::uint32_t latchConfirmed;
    std::uint32_t latchConfirmedInverse;
};

SafetyRetainedRecord makeSafetyRetainedRecord(
    std::uint32_t appIdentity, SafetyReason reason, std::uint32_t tripCount,
    std::uint32_t quiesceCount, bool latchConfirmed = true);
bool validateSafetyRetainedRecord(const SafetyRetainedRecord& record,
                                  std::uint32_t appIdentity);
bool shouldLatchSafetyStop(const SafetyRetainedRecord& record,
                           std::uint32_t appIdentity,
                           bool watchdogReset);
const char* safetyReasonName(SafetyReason reason);
const char* safetyStateName(SafetyState state);

class SafetySupervisor final {
public:
    void restore(const SafetyRetainedRecord& record,
                 std::uint32_t appIdentity, bool watchdogReset);
    bool arm();
    bool latch(SafetyReason reason, std::uint32_t tripCount = 1,
               std::uint32_t quiesceCount = 1);
    bool requestClear();
    bool cancelClear();
    bool confirmClear(bool explicitConfirmation);

    SafetyState state() const { return state_; }
    SafetyReason reason() const { return reason_; }
    std::uint32_t tripCount() const { return tripCount_; }
    std::uint32_t quiesceCount() const { return quiesceCount_; }
    bool armed() const { return state_ == SafetyState::Armed; }
    bool latched() const {
        return state_ == SafetyState::Latched ||
               state_ == SafetyState::ClearPending;
    }
    bool clearPending() const { return state_ == SafetyState::ClearPending; }

private:
    SafetyState state_ = SafetyState::Startup;
    SafetyReason reason_ = SafetyReason::None;
    std::uint32_t tripCount_ = 0;
    std::uint32_t quiesceCount_ = 0;
};

}  // namespace leshy1::kernel::safety
