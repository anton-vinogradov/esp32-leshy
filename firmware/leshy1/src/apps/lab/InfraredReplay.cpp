#include "apps/lab/InfraredReplay.h"

#include <limits>

namespace leshy1::apps::lab {
namespace {

constexpr std::uint16_t kNecHeaderMarkUs = 9000U;
constexpr std::uint16_t kNecHeaderSpaceUs = 4500U;
constexpr std::uint16_t kNecBitMarkUs = 560U;
constexpr std::uint16_t kNecZeroSpaceUs = 560U;
constexpr std::uint16_t kNecOneSpaceUs = 1690U;

bool decodeFieldsMatch(const domain::captures::InfraredDecode& decode) {
    const std::uint8_t addressLow = static_cast<std::uint8_t>(decode.rawCode);
    const std::uint8_t addressHigh =
        static_cast<std::uint8_t>(decode.rawCode >> 8U);
    const std::uint8_t command =
        static_cast<std::uint8_t>(decode.rawCode >> 16U);
    const std::uint8_t commandInverse =
        static_cast<std::uint8_t>(decode.rawCode >> 24U);
    if (static_cast<std::uint8_t>(command ^ commandInverse) != 0xFFU ||
        command != decode.command) {
        return false;
    }
    if (decode.protocol == domain::captures::InfraredProtocol::Nec) {
        return static_cast<std::uint8_t>(addressLow ^ addressHigh) == 0xFFU &&
               decode.address == addressLow;
    }
    if (decode.protocol ==
        domain::captures::InfraredProtocol::NecExtended) {
        return static_cast<std::uint8_t>(addressLow ^ addressHigh) != 0xFFU &&
               decode.address == static_cast<std::uint16_t>(
                   addressLow |
                   (static_cast<std::uint16_t>(addressHigh) << 8U));
    }
    return false;
}

InfraredReplayRefusal sourceRefusal(const InfraredReplaySource& source) {
    if (!source.capturePresent) return InfraredReplayRefusal::CaptureMissing;
    if (!source.persistent) return InfraredReplayRefusal::NotPersistent;
    if (source.simulated) return InfraredReplayRefusal::Simulated;
    if (source.recoveredFallback) {
        return InfraredReplayRefusal::RecoveredFallback;
    }
    if (source.generation == 0U) {
        return InfraredReplayRefusal::GenerationMissing;
    }
    if (source.truncated) return InfraredReplayRefusal::Truncated;
    if (source.decode.protocol != domain::captures::InfraredProtocol::Nec &&
        source.decode.protocol !=
            domain::captures::InfraredProtocol::NecExtended) {
        return InfraredReplayRefusal::UnsupportedProtocol;
    }
    if (!source.decode.integrityValid) {
        return InfraredReplayRefusal::IntegrityInvalid;
    }
    if (!decodeFieldsMatch(source.decode)) {
        return InfraredReplayRefusal::CodeInvalid;
    }
    return InfraredReplayRefusal::None;
}

}  // namespace

bool buildInfraredReplayPlan(
    const domain::captures::InfraredDecode& decode,
    InfraredReplayPlan* output) {
    if (output == nullptr || !decode.integrityValid ||
        !decodeFieldsMatch(decode)) {
        return false;
    }
    InfraredReplayPlan plan{};
    plan.protocol = decode.protocol;
    plan.rawCode = decode.rawCode;
    plan.address = decode.address;
    plan.command = decode.command;
    plan.carrierHz = kInfraredReplayCarrierHz;
    plan.dutyPercent = kInfraredReplayDutyPercent;
    plan.pulseDurationsUs[plan.pulseCount++] = kNecHeaderMarkUs;
    plan.pulseDurationsUs[plan.pulseCount++] = kNecHeaderSpaceUs;
    for (std::size_t bit = 0U; bit < 32U; ++bit) {
        plan.pulseDurationsUs[plan.pulseCount++] = kNecBitMarkUs;
        plan.pulseDurationsUs[plan.pulseCount++] =
            (decode.rawCode & (1UL << bit)) != 0U
                ? kNecOneSpaceUs : kNecZeroSpaceUs;
    }
    plan.pulseDurationsUs[plan.pulseCount++] = kNecBitMarkUs;
    std::uint32_t total = 0U;
    for (std::size_t index = 0U; index < plan.pulseCount; ++index) {
        if (total > std::numeric_limits<std::uint32_t>::max() -
                        plan.pulseDurationsUs[index]) {
            return false;
        }
        total += plan.pulseDurationsUs[index];
    }
    if (plan.pulseCount != kInfraredReplayPulseCount || total == 0U ||
        total > kInfraredReplayMaximumEmissionUs) {
        return false;
    }
    plan.totalDurationUs = total;
    *output = plan;
    return true;
}

const char* infraredReplayRefusalName(InfraredReplayRefusal refusal) {
    switch (refusal) {
        case InfraredReplayRefusal::None: return "none";
        case InfraredReplayRefusal::CaptureMissing: return "capture_missing";
        case InfraredReplayRefusal::NotPersistent: return "not_persistent";
        case InfraredReplayRefusal::Simulated: return "simulated";
        case InfraredReplayRefusal::RecoveredFallback:
            return "recovered_fallback";
        case InfraredReplayRefusal::GenerationMissing:
            return "generation_missing";
        case InfraredReplayRefusal::Truncated: return "truncated";
        case InfraredReplayRefusal::UnsupportedProtocol:
            return "unsupported_protocol";
        case InfraredReplayRefusal::IntegrityInvalid:
            return "integrity_invalid";
        case InfraredReplayRefusal::CodeInvalid: return "code_invalid";
    }
    return "unknown";
}

const char* infraredReplayStateName(InfraredReplayState state) {
    switch (state) {
        case InfraredReplayState::Idle: return "idle";
        case InfraredReplayState::Preview: return "preview";
        case InfraredReplayState::Confirmation: return "confirmation";
        case InfraredReplayState::Running: return "running";
        case InfraredReplayState::Complete: return "complete";
        case InfraredReplayState::Stopped: return "stopped";
        case InfraredReplayState::TimedOut: return "timed_out";
        case InfraredReplayState::Refused: return "refused";
        case InfraredReplayState::Fault: return "fault";
    }
    return "unknown";
}

bool InfraredReplayController::refuse(InfraredReplayRefusal refusal) {
    plan_ = {};
    report_ = {};
    report_.state = InfraredReplayState::Refused;
    report_.refusal = refusal;
    return false;
}

bool InfraredReplayController::prepare(const InfraredReplaySource& source) {
    if (report_.state == InfraredReplayState::Running) return false;
    const InfraredReplayRefusal refusal = sourceRefusal(source);
    if (refusal != InfraredReplayRefusal::None) return refuse(refusal);
    InfraredReplayPlan plan{};
    if (!buildInfraredReplayPlan(source.decode, &plan)) {
        return refuse(InfraredReplayRefusal::CodeInvalid);
    }
    plan_ = plan;
    report_ = {};
    report_.state = InfraredReplayState::Preview;
    report_.sourceGeneration = source.generation;
    return true;
}

bool InfraredReplayController::requestConfirmation() {
    if (report_.state != InfraredReplayState::Preview) return false;
    report_.state = InfraredReplayState::Confirmation;
    return true;
}

bool InfraredReplayController::cancelConfirmation() {
    if (report_.state != InfraredReplayState::Confirmation) return false;
    report_.state = InfraredReplayState::Preview;
    return true;
}

bool InfraredReplayController::confirmAndStart(
    InfraredReplayOutput& output, std::uint64_t startedUs) {
    if (report_.state != InfraredReplayState::Confirmation || startedUs == 0U ||
        !output.inactive()) {
        return false;
    }
    ++report_.startAttempts;
    if (!output.begin(plan_, startedUs)) {
        ++report_.stopAttempts;
        const bool stopped = output.stop();
        report_.outputInactive = stopped && output.inactive();
        report_.state = InfraredReplayState::Fault;
        report_.endedUs = startedUs;
        return false;
    }
    report_.state = InfraredReplayState::Running;
    report_.startedUs = startedUs;
    report_.outputInactive = false;
    ++report_.emissions;
    return true;
}

bool InfraredReplayController::finish(
    InfraredReplayOutput& output, std::uint64_t nowUs,
    InfraredReplayState state) {
    ++report_.stopAttempts;
    const bool stopped = output.stop();
    report_.outputInactive = stopped && output.inactive();
    report_.endedUs = nowUs;
    report_.state = report_.outputInactive ? state : InfraredReplayState::Fault;
    return report_.outputInactive;
}

bool InfraredReplayController::service(InfraredReplayOutput& output,
                                       std::uint64_t nowUs) {
    if (report_.state != InfraredReplayState::Running ||
        nowUs < report_.startedUs) {
        return false;
    }
    if (nowUs - report_.startedUs >= kInfraredReplayMaximumEmissionUs) {
        report_.deadlineExpired = true;
        return finish(output, nowUs, InfraredReplayState::TimedOut);
    }
    const InfraredReplayOutputState state = output.service(nowUs);
    if (state == InfraredReplayOutputState::Running) return false;
    return finish(output, nowUs,
                  state == InfraredReplayOutputState::Complete
                      ? InfraredReplayState::Complete
                      : InfraredReplayState::Fault);
}

bool InfraredReplayController::stop(InfraredReplayOutput& output,
                                    std::uint64_t nowUs) {
    if (report_.state != InfraredReplayState::Running) return false;
    if (nowUs < report_.startedUs) nowUs = report_.startedUs;
    return finish(output, nowUs, InfraredReplayState::Stopped);
}

void InfraredReplayController::reset() {
    if (report_.state == InfraredReplayState::Running) return;
    plan_ = {};
    report_ = {};
}

}  // namespace leshy1::apps::lab
