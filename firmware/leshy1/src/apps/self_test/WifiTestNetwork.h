#pragma once
#include <cstdint>

namespace leshy1::apps::self_test {

// Product session, not a HIL personality. No IO, allocation, or auto-start.
class WifiTestNetwork final {
public:
    static constexpr std::uint32_t kLimitMs = 60000;
    static constexpr std::uint8_t kChannel = 6;
    enum class StopReason : std::uint8_t { None, User, Deadline, Safety, Failed };

    bool begin(std::uint32_t now, bool explicitlyConfirmed, bool admitted) {
        if (running_ || !explicitlyConfirmed || !admitted) return false;
        started_ = now;
        running_ = true;
        reason_ = StopReason::None;
        return true;
    }
    bool due(std::uint32_t now) const {
        return running_ && static_cast<std::uint32_t>(now - started_) >= kLimitMs;
    }
    std::uint32_t remainingSeconds(std::uint32_t now) const {
        if (!running_ || due(now)) return 0;
        return (kLimitMs - static_cast<std::uint32_t>(now - started_) + 999U) / 1000U;
    }
    void stop(StopReason reason) { running_ = false; reason_ = reason; }
    bool running() const { return running_; }
    StopReason reason() const { return reason_; }
private:
    std::uint32_t started_ = 0;
    bool running_ = false;
    StopReason reason_ = StopReason::None;
};
}  // namespace leshy1::apps::self_test
