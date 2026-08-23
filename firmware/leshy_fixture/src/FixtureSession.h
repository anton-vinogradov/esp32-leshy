#pragma once

#include <cstdint>

namespace leshy::hil::fixture {

constexpr std::uint32_t kSessionLifetimeMs = 5000;
constexpr std::uint32_t kMaximumEmissionUs = 100000;
constexpr const char* kNecVectorId = "nec-10-34";

enum class FixtureState : std::uint8_t {
    Idle,
    Armed,
    Running,
    Complete,
    Stopped,
    Expired,
    Panicked,
    Fault,
};

const char* fixtureStateName(FixtureState state);

struct FixtureReport final {
    FixtureState state = FixtureState::Idle;
    std::uint32_t deadlineMs = 0;
    std::uint32_t startCount = 0;
    std::uint32_t stopCount = 0;
    std::uint32_t panicCount = 0;
    std::uint32_t emissionCount = 0;
    std::uint32_t lastDurationUs = 0;
    bool outputInactive = true;
    const char* lastError = "none";
};

// Pure, allocation-free admission controller for a single fixed IR vector.
// Hardware modulation is deliberately kept in the separate fixture image.
class FixtureSession final {
public:
    bool begin(const char* sessionId, const char* requestedAppSha256,
               const char* runningAppSha256, const char* requestedFixtureId,
               const char* runningFixtureId, std::uint32_t nowMs,
               bool outputInactive);
    bool authorizeNecOnce(const char* sessionId, const char* vectorId,
                          std::uint32_t nowMs);
    bool complete(std::uint32_t durationUs, bool outputInactive);
    bool stop(const char* sessionId, bool outputInactive);
    void panic(bool outputInactive);
    bool service(std::uint32_t nowMs, bool outputInactive);

    const FixtureReport& report() const { return report_; }
    const char* sessionId() const { return sessionId_; }

private:
    static bool validHex(const char* value, std::uint8_t length,
                         bool uppercaseOnly);
    static bool same(const char* left, const char* right);
    void reject(const char* reason);

    FixtureReport report_{};
    char sessionId_[33]{};
};

}  // namespace leshy::hil::fixture
