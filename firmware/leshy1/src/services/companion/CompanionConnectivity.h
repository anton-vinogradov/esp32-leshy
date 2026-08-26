#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::services::companion {

constexpr std::uint64_t kCompanionLocalIdleTimeoutUs =
    10ULL * 60ULL * 1000000ULL;
constexpr std::uint64_t kCompanionLocalMaximumLifetimeUs =
    30ULL * 60ULL * 1000000ULL;
constexpr std::size_t kCompanionLocalSsidCapacity = 20;
constexpr std::size_t kCompanionLocalPassphraseCapacity = 12;

enum class CompanionLocalStopReason : std::uint8_t {
    None,
    User,
    LeftForeground,
    IdleTimeout,
    LifetimeTimeout,
    SafetyStop,
    StartFailed,
};

const char* companionLocalStopReasonName(CompanionLocalStopReason reason);

struct CompanionLocalCredentials final {
    std::array<char, kCompanionLocalSsidCapacity + 1U> ssid{};
    std::array<char, kCompanionLocalPassphraseCapacity + 1U> passphrase{};

    bool valid() const;
    void clear();
};

// Produces a per-run credential from caller-supplied entropy. The result is
// never persisted by this boundary and can be explicitly zeroized on stop.
bool makeCompanionLocalCredentials(
    const std::array<std::uint8_t, 6>& deviceMac,
    const std::array<std::uint8_t, 16>& entropy,
    CompanionLocalCredentials* output);

// Decodes the exact one-shot entropy shape accepted by the physical HIL
// boundary. Invalid or all-zero input fails closed and leaves output zeroed.
bool parseCompanionHilEntropyHex(
    const char* hex,
    std::array<std::uint8_t, 16>* output);

class CompanionConnectivity final {
public:
    bool authorize(std::uint64_t nowUs, std::uint32_t generation);
    bool recordActivity(std::uint64_t nowUs, std::uint32_t generation);
    bool service(std::uint64_t nowUs);
    void revoke(CompanionLocalStopReason reason);

    bool authorized() const { return authorized_; }
    std::uint32_t generation() const { return generation_; }
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t lastActivityUs() const { return lastActivityUs_; }
    CompanionLocalStopReason stopReason() const { return stopReason_; }

private:
    bool authorized_ = false;
    std::uint32_t generation_ = 0;
    std::uint64_t startedUs_ = 0;
    std::uint64_t lastActivityUs_ = 0;
    CompanionLocalStopReason stopReason_ = CompanionLocalStopReason::None;
};

}  // namespace leshy1::services::companion
