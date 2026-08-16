#include "SurveySession.h"

#include <cstring>

namespace leshy1::services::survey {
namespace {

bool validSessionId(const char* value) {
    if (value == nullptr || value[0] == '\0') return false;
    for (std::size_t index = 0; value[index] != '\0'; ++index) {
        const char character = value[index];
        const bool allowed = (character >= 'a' && character <= 'z') ||
                             (character >= 'A' && character <= 'Z') ||
                             (character >= '0' && character <= '9') || character == '-' ||
                             character == '_';
        if (!allowed || index >= SurveySession::kSessionIdCapacity) return false;
    }
    return true;
}

}  // namespace

const char* sessionStatusName(SessionStatus status) {
    switch (status) {
        case SessionStatus::Started: return "started";
        case SessionStatus::AlreadyStarted: return "already_started";
        case SessionStatus::InvalidSession: return "invalid_session";
        case SessionStatus::Appended: return "appended";
        case SessionStatus::NotRunning: return "not_running";
        case SessionStatus::OutOfOrder: return "out_of_order";
        case SessionStatus::Full: return "full";
        case SessionStatus::Stopped: return "stopped";
        case SessionStatus::AlreadyStopped: return "already_stopped";
    }
    return "invalid_session";
}

void SurveySession::reset() {
    sessionId_.fill('\0');
    observations_.fill(domain::observations::Observation{});
    state_ = SessionState::Idle;
    startedUs_ = 0;
    stoppedUs_ = 0;
    size_ = 0;
    dropped_ = 0;
}

SessionStatus SurveySession::start(const char* sessionId, std::uint64_t monotonicUs) {
    if (state_ != SessionState::Idle) return SessionStatus::AlreadyStarted;
    if (!validSessionId(sessionId) || monotonicUs == 0) {
        return SessionStatus::InvalidSession;
    }
    const std::size_t length = std::strlen(sessionId);
    if (length > kSessionIdCapacity) return SessionStatus::InvalidSession;
    std::memcpy(sessionId_.data(), sessionId, length + 1);
    startedUs_ = monotonicUs;
    state_ = SessionState::Running;
    return SessionStatus::Started;
}

SessionStatus SurveySession::append(const domain::observations::Observation& observation) {
    if (state_ != SessionState::Running) return SessionStatus::NotRunning;
    const std::uint64_t previousUs = size_ == 0 ? startedUs_ : observations_[size_ - 1].monotonicUs;
    if (observation.monotonicUs < previousUs) return SessionStatus::OutOfOrder;
    if (size_ >= observations_.size()) {
        ++dropped_;
        return SessionStatus::Full;
    }
    observations_[size_] = observation;
    observations_[size_].sequence = static_cast<std::uint64_t>(size_ + 1);
    ++size_;
    return SessionStatus::Appended;
}

SessionStatus SurveySession::stop(std::uint64_t monotonicUs) {
    if (state_ == SessionState::Stopped) return SessionStatus::AlreadyStopped;
    if (state_ != SessionState::Running) return SessionStatus::NotRunning;
    const std::uint64_t lastUs = size_ == 0 ? startedUs_ : observations_[size_ - 1].monotonicUs;
    if (monotonicUs < lastUs) return SessionStatus::OutOfOrder;
    stoppedUs_ = monotonicUs;
    state_ = SessionState::Stopped;
    return SessionStatus::Stopped;
}

const domain::observations::Observation* SurveySession::get(std::size_t index) const {
    return index < size_ ? &observations_[index] : nullptr;
}

}  // namespace leshy1::services::survey
