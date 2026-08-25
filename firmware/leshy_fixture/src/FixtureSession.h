#pragma once

#include <cstdint>

namespace leshy::hil::fixture {

constexpr std::uint32_t kSessionLifetimeMs = 5000;
constexpr std::uint32_t kMaximumIrEmissionUs = 100000;
constexpr std::uint32_t kNrf24CarrierDurationUs = 2000000;
constexpr std::uint32_t kMaximumNrf24CarrierUs = 2500000;
constexpr std::uint32_t kMaximumCc1101EmissionUs = 250000;
constexpr const char* kNecVectorId = "nec-10-34";
constexpr const char* kNrf24VectorId = "nrf24-ch42-min-2s";
constexpr const char* kCc1101OokVectorId = "cc1101-ook-433920-min";
constexpr const char* kCc1101FskVectorId = "cc1101-fsk-433920-min";

enum class FixtureSignal : std::uint8_t {
    None,
    InfraredNec,
    Nrf24Carrier,
    Cc1101Ook,
    Cc1101Fsk,
};

const char* fixtureSignalName(FixtureSignal signal);

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
    std::uint32_t maximumDurationUs = 0;
    FixtureSignal signal = FixtureSignal::None;
    bool outputInactive = true;
    const char* lastError = "none";
};

// Pure, allocation-free admission controller for one fixed bounded signal.
// Hardware emission is deliberately kept in the separate fixture image.
class FixtureSession final {
public:
    bool begin(const char* sessionId, const char* requestedAppSha256,
               const char* runningAppSha256, const char* requestedFixtureId,
               const char* runningFixtureId, std::uint32_t nowMs,
               bool outputInactive);
    bool authorizeNecOnce(const char* sessionId, const char* vectorId,
                          std::uint32_t nowMs);
    bool authorizeNrf24CarrierOnce(const char* sessionId,
                                   const char* vectorId,
                                   std::uint32_t nowMs);
    bool authorizeCc1101OokOnce(const char* sessionId,
                                const char* vectorId,
                                std::uint32_t nowMs);
    bool authorizeCc1101FskOnce(const char* sessionId,
                                const char* vectorId,
                                std::uint32_t nowMs);
    bool complete(std::uint32_t durationUs, bool outputInactive);
    bool stop(const char* sessionId, bool outputInactive);
    void panic(bool outputInactive);
    bool service(std::uint32_t nowMs, bool outputInactive);

    const FixtureReport& report() const { return report_; }
    const char* sessionId() const { return sessionId_; }
    const char* vectorId() const;

private:
    static bool validHex(const char* value, std::uint8_t length,
                         bool uppercaseOnly);
    static bool same(const char* left, const char* right);
    bool authorizeFixedOnce(const char* sessionId, const char* vectorId,
                            const char* allowedVectorId,
                            FixtureSignal signal,
                            std::uint32_t maximumDurationUs,
                            std::uint32_t nowMs);
    void reject(const char* reason);

    FixtureReport report_{};
    char sessionId_[33]{};
};

}  // namespace leshy::hil::fixture
