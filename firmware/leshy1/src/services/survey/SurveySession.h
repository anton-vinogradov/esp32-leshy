#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::services::survey {

enum class SessionState : std::uint8_t {
    Idle,
    Running,
    Stopped,
};

enum class SessionStatus : std::uint8_t {
    Started,
    AlreadyStarted,
    InvalidSession,
    Appended,
    NotRunning,
    OutOfOrder,
    Full,
    Stopped,
    AlreadyStopped,
};

const char* sessionStatusName(SessionStatus status);

class SurveySession final {
public:
    static constexpr std::size_t kSessionIdCapacity = 31;
    static constexpr std::size_t kObservationCapacity = 64;

    void reset();
    SessionStatus start(const char* sessionId, std::uint64_t monotonicUs);
    SessionStatus append(const domain::observations::Observation& observation);
    SessionStatus stop(std::uint64_t monotonicUs);

    SessionState state() const { return state_; }
    const char* id() const { return sessionId_.data(); }
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t stoppedUs() const { return stoppedUs_; }
    std::size_t size() const { return size_; }
    std::uint32_t dropped() const { return dropped_; }
    const domain::observations::Observation* get(std::size_t index) const;

private:
    std::array<char, kSessionIdCapacity + 1> sessionId_{};
    std::array<domain::observations::Observation, kObservationCapacity> observations_{};
    SessionState state_ = SessionState::Idle;
    std::uint64_t startedUs_ = 0;
    std::uint64_t stoppedUs_ = 0;
    std::size_t size_ = 0;
    std::uint32_t dropped_ = 0;
};

}  // namespace leshy1::services::survey
