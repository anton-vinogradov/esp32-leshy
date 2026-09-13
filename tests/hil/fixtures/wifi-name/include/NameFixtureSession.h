#pragma once
#include <cstdint>
#include <cstring>

namespace leshy::hil {
// No automatic start, no renewable lease, no user-selected SSID/channel/traffic.
class NameFixtureSession final {
public:
    static constexpr std::uint32_t kLimitMs = 60000;
    bool begin(const char* token, std::uint32_t now) {
        if (active_ || token == nullptr || std::strlen(token) != 16U) return false;
        for (std::uint8_t i = 0; i < 16U; ++i)
            if (!((token[i] >= '0' && token[i] <= '9') ||
                  (token[i] >= 'a' && token[i] <= 'f'))) return false;
        std::memcpy(token_, token, 17U);
        started_ = now; active_ = true; hidden_ = true;
        return true;
    }
    bool setHidden(const char* token, bool hidden, std::uint32_t now) {
        expire(now);
        if (!active_ || token == nullptr || std::strcmp(token, token_) != 0) return false;
        hidden_ = hidden; return true;
    }
    bool expire(std::uint32_t now) {
        if (!active_ || static_cast<std::uint32_t>(now - started_) < kLimitMs) return false;
        stop(); return true;
    }
    void stop() { active_ = false; hidden_ = true; token_[0] = '\0'; }
    bool active() const { return active_; }
    bool hidden() const { return hidden_; }
    const char* token() const { return token_; }
private:
    char token_[17]{};
    std::uint32_t started_ = 0;
    bool active_ = false;
    bool hidden_ = true;
};
}
