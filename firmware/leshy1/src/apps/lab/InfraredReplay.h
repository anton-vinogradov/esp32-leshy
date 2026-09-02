#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/InfraredRaw.h"

namespace leshy1::apps::lab {

constexpr std::uint32_t kInfraredReplayCarrierHz = 38000U;
constexpr std::uint8_t kInfraredReplayDutyPercent = 33U;
constexpr std::uint32_t kInfraredReplayMaximumEmissionUs = 100000U;
constexpr std::size_t kInfraredReplayPulseCount = 67U;

struct InfraredReplayPlan final {
    domain::captures::InfraredProtocol protocol =
        domain::captures::InfraredProtocol::Unknown;
    std::uint32_t rawCode = 0U;
    std::uint16_t address = 0U;
    std::uint8_t command = 0U;
    std::uint32_t carrierHz = 0U;
    std::uint8_t dutyPercent = 0U;
    std::array<std::uint16_t, kInfraredReplayPulseCount> pulseDurationsUs{};
    std::size_t pulseCount = 0U;
    std::uint32_t totalDurationUs = 0U;
};

bool buildInfraredReplayPlan(
    const domain::captures::InfraredDecode& decode,
    InfraredReplayPlan* output);

enum class InfraredReplayRefusal : std::uint8_t {
    None,
    CaptureMissing,
    NotPersistent,
    Simulated,
    RecoveredFallback,
    GenerationMissing,
    Truncated,
    UnsupportedProtocol,
    IntegrityInvalid,
    CodeInvalid,
};

const char* infraredReplayRefusalName(InfraredReplayRefusal refusal);

struct InfraredReplaySource final {
    bool capturePresent = false;
    bool persistent = false;
    bool simulated = false;
    bool recoveredFallback = false;
    bool truncated = false;
    std::uint32_t generation = 0U;
    domain::captures::InfraredDecode decode{};
};

enum class InfraredReplayState : std::uint8_t {
    Idle,
    Preview,
    Confirmation,
    Running,
    Complete,
    Stopped,
    TimedOut,
    Refused,
    Fault,
};

const char* infraredReplayStateName(InfraredReplayState state);

enum class InfraredReplayOutputState : std::uint8_t {
    Idle,
    Running,
    Complete,
    Fault,
};

class InfraredReplayOutput {
public:
    virtual ~InfraredReplayOutput() = default;
    virtual bool begin(const InfraredReplayPlan& plan,
                       std::uint64_t startedUs) = 0;
    virtual InfraredReplayOutputState service(std::uint64_t nowUs) = 0;
    virtual bool stop() = 0;
    virtual bool inactive() const = 0;
};

struct InfraredReplayReport final {
    InfraredReplayState state = InfraredReplayState::Idle;
    InfraredReplayRefusal refusal = InfraredReplayRefusal::None;
    std::uint32_t sourceGeneration = 0U;
    std::uint64_t startedUs = 0U;
    std::uint64_t endedUs = 0U;
    std::uint32_t startAttempts = 0U;
    std::uint32_t emissions = 0U;
    std::uint32_t stopAttempts = 0U;
    bool deadlineExpired = false;
    bool outputInactive = true;
};

class InfraredReplayController final {
public:
    bool prepare(const InfraredReplaySource& source);
    bool requestConfirmation();
    bool cancelConfirmation();
    bool confirmAndStart(InfraredReplayOutput& output,
                         std::uint64_t startedUs);
    bool service(InfraredReplayOutput& output, std::uint64_t nowUs);
    bool stop(InfraredReplayOutput& output, std::uint64_t nowUs);
    void reset();

    const InfraredReplayPlan& plan() const { return plan_; }
    const InfraredReplayReport& report() const { return report_; }

private:
    bool finish(InfraredReplayOutput& output, std::uint64_t nowUs,
                InfraredReplayState state);
    bool refuse(InfraredReplayRefusal refusal);

    InfraredReplayPlan plan_{};
    InfraredReplayReport report_{};
};

}  // namespace leshy1::apps::lab
