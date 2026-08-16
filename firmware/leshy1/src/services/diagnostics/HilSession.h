#pragma once

#include <array>
#include <cstddef>

namespace leshy1::services::diagnostics {

enum class HilSessionStatus {
    Begun,
    Ended,
    InvalidSessionId,
    InvalidAppIdentity,
    AppIdentityMismatch,
    AlreadyActive,
    NotActive,
    SessionMismatch,
};

const char* hilSessionStatusName(HilSessionStatus status);

class HilSession final {
public:
    static constexpr std::size_t kSessionIdLength = 32;
    static constexpr std::size_t kAppIdentityLength = 64;

    HilSessionStatus begin(const char* sessionId,
                           const char* candidateAppIdentity,
                           const char* runningAppIdentity);
    HilSessionStatus end(const char* sessionId);

    bool active() const { return active_; }
    const char* id() const { return id_.data(); }

private:
    std::array<char, kSessionIdLength + 1> id_{};
    bool active_ = false;
};

}  // namespace leshy1::services::diagnostics
