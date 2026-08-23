#include "InfraredCapture.h"

#include <limits>

namespace leshy1::apps::capture {
namespace {

bool nearDuration(std::uint16_t actual, std::uint16_t expected,
                  std::uint8_t tolerancePercent = 30) {
    const std::uint32_t delta =
        static_cast<std::uint32_t>(expected) * tolerancePercent / 100U;
    return actual >= expected - delta && actual <= expected + delta;
}

// A demodulating IR receiver reports the envelope, not the electrical LED
// drive time. Its recovery delay can shorten every carrier mark and lengthen
// the following space by a few hundred microseconds. Keep disjoint,
// protocol-specific windows here: real NEC zero/one spaces remain
// unambiguous, while the byte-complement checks below still reject noise.
bool validNecBitMark(std::uint16_t actual) {
    // The capture plan has already rejected pulses shorter than 80 us. Real
    // ESP32-DIV receiver envelopes observed across repeated fixed-vector runs
    // can compress isolated 560 us carrier marks to 110 us while preserving
    // an unambiguous following zero/one space. Keep the decoder aligned with
    // that acquisition floor; header, exact pulse structure, disjoint spaces
    // and NEC complement bytes remain independent fail-closed checks.
    return actual >= 80U && actual <= 900U;
}

int classifyNecBitSpace(std::uint16_t actual) {
    if (actual >= 300U && actual <= 1050U) return 0;
    if (actual >= 1200U && actual <= 2500U) return 1;
    return -1;
}

}  // namespace

const char* infraredCaptureStateName(InfraredCaptureState state) {
    switch (state) {
        case InfraredCaptureState::Idle: return "idle";
        case InfraredCaptureState::Waiting: return "waiting";
        case InfraredCaptureState::Capturing: return "capturing";
        case InfraredCaptureState::Complete: return "complete";
        case InfraredCaptureState::TimedOut: return "timed_out";
        case InfraredCaptureState::SignalTooLong: return "signal_too_long";
        case InfraredCaptureState::Unreliable: return "unreliable";
        case InfraredCaptureState::Cancelled: return "cancelled";
        case InfraredCaptureState::Failed: return "failed";
    }
    return "unknown";
}

bool validateInfraredCapturePlan(const InfraredCapturePlan& plan) {
    return plan.waitTimeoutMs >= 1000U && plan.waitTimeoutMs <= 300000U &&
           plan.maximumCaptureMs >= 100U &&
           plan.maximumCaptureMs <= 10000U &&
           plan.minimumPulseUs >= 20U && plan.minimumPulseUs <= 1000U &&
           plan.endGapUs >= 5000U && plan.endGapUs <= 60000U &&
           plan.maximumSampleGapUs >= 50U &&
           plan.maximumSampleGapUs <= 2000U &&
           plan.maximumPulses >= 4U &&
           plan.maximumPulses <= InfraredCapture::kPulseCapacity;
}

bool InfraredCapture::begin(const InfraredCapturePlan& plan,
                            std::uint64_t startedUs, bool initialLevel) {
    if (stats_.state != InfraredCaptureState::Idle || startedUs == 0U ||
        !validateInfraredCapturePlan(plan)) {
        return false;
    }
    plan_ = plan;
    stats_ = {};
    stats_.state = InfraredCaptureState::Waiting;
    stats_.startedUs = startedUs;
    currentLevel_ = initialLevel;
    currentLevelSinceUs_ = startedUs;
    lastSampleUs_ = startedUs;
    size_ = 0;
    decode_ = {};
    return true;
}

bool InfraredCapture::acceptTransition(bool level,
                                       std::uint64_t monotonicUs) {
    const std::uint64_t duration = monotonicUs - currentLevelSinceUs_;
    if (stats_.state == InfraredCaptureState::Waiting) {
        currentLevel_ = level;
        currentLevelSinceUs_ = monotonicUs;
        if (level == plan_.idleLevel) return false;
        stats_.state = InfraredCaptureState::Capturing;
        stats_.signalStartedUs = monotonicUs;
        stats_.startLevel = level;
        // Waiting UI/console work is outside the measured waveform. From the
        // first observed edge onward every sampling gap is fail-closed.
        stats_.maximumObservedSampleGapUs = 0;
        return true;
    }
    if (stats_.state != InfraredCaptureState::Capturing) return false;
    if (duration < plan_.minimumPulseUs) {
        ++stats_.shortPulsesRejected;
        currentLevel_ = level;
        currentLevelSinceUs_ = monotonicUs;
        return false;
    }
    if (size_ >= plan_.maximumPulses || size_ >= pulses_.size()) {
        return finish(monotonicUs, true);
    }
    pulses_[size_++] = static_cast<std::uint16_t>(
        duration > std::numeric_limits<std::uint16_t>::max()
            ? std::numeric_limits<std::uint16_t>::max() : duration);
    stats_.truncated = stats_.truncated ||
        duration > std::numeric_limits<std::uint16_t>::max();
    stats_.pulsesAccepted = static_cast<std::uint32_t>(size_);
    currentLevel_ = level;
    currentLevelSinceUs_ = monotonicUs;
    if (size_ >= plan_.maximumPulses || size_ >= pulses_.size()) {
        return finish(monotonicUs, true);
    }
    return true;
}

bool InfraredCapture::ingest(const InfraredLevelSample& sample) {
    if (stats_.state != InfraredCaptureState::Waiting &&
        stats_.state != InfraredCaptureState::Capturing) {
        return false;
    }
    ++stats_.samples;
    if (sample.monotonicUs < stats_.startedUs ||
        sample.monotonicUs < lastSampleUs_) {
        ++stats_.invalidSamples;
        return false;
    }
    const std::uint64_t gap = sample.monotonicUs - lastSampleUs_;
    if (gap > stats_.maximumObservedSampleGapUs) {
        stats_.maximumObservedSampleGapUs = static_cast<std::uint32_t>(
            gap > std::numeric_limits<std::uint32_t>::max()
                ? std::numeric_limits<std::uint32_t>::max() : gap);
    }
    lastSampleUs_ = sample.monotonicUs;
    if (stats_.state == InfraredCaptureState::Capturing &&
        gap > plan_.maximumSampleGapUs) {
        stats_.state = InfraredCaptureState::Unreliable;
        stats_.endedUs = sample.monotonicUs;
        return true;
    }
    bool changed = false;
    if (sample.level != currentLevel_) {
        changed = acceptTransition(sample.level, sample.monotonicUs);
    }
    return service(sample.monotonicUs) || changed;
}

bool InfraredCapture::service(std::uint64_t monotonicUs) {
    if (monotonicUs < stats_.startedUs) return false;
    if (stats_.state == InfraredCaptureState::Waiting &&
        monotonicUs - stats_.startedUs >=
            static_cast<std::uint64_t>(plan_.waitTimeoutMs) * 1000U) {
        stats_.state = InfraredCaptureState::TimedOut;
        stats_.endedUs = monotonicUs;
        return true;
    }
    if (stats_.state == InfraredCaptureState::Capturing &&
        currentLevel_ == plan_.idleLevel &&
        monotonicUs - currentLevelSinceUs_ >= plan_.endGapUs) {
        return finish(monotonicUs, false);
    }
    if (stats_.state == InfraredCaptureState::Capturing &&
        monotonicUs - stats_.signalStartedUs >=
            static_cast<std::uint64_t>(plan_.maximumCaptureMs) * 1000U) {
        stats_.state = InfraredCaptureState::SignalTooLong;
        stats_.endedUs = monotonicUs;
        return true;
    }
    return false;
}

bool InfraredCapture::finish(std::uint64_t endedUs, bool truncated) {
    if (stats_.state != InfraredCaptureState::Capturing ||
        endedUs < stats_.signalStartedUs || size_ < 2U) {
        return false;
    }
    stats_.state = InfraredCaptureState::Complete;
    stats_.endedUs = endedUs;
    stats_.truncated = stats_.truncated || truncated;
    decodeCapturedSignal();
    return true;
}

void InfraredCapture::decodeCapturedSignal() {
    decode_ = {};
    if (stats_.startLevel || size_ < 3U ||
        !nearDuration(pulses_[0], 9000U)) {
        return;
    }
    if (nearDuration(pulses_[1], 2250U) && validNecBitMark(pulses_[2])) {
        decode_.protocol = domain::captures::InfraredProtocol::NecRepeat;
        decode_.integrityValid = true;
        return;
    }
    if (size_ < 66U || !nearDuration(pulses_[1], 4500U)) return;
    std::uint32_t code = 0;
    for (std::size_t bit = 0; bit < 32U; ++bit) {
        const std::size_t mark = 2U + bit * 2U;
        const std::size_t space = mark + 1U;
        if (!validNecBitMark(pulses_[mark])) return;
        const int bitValue = classifyNecBitSpace(pulses_[space]);
        if (bitValue == 1) {
            code |= static_cast<std::uint32_t>(1U << bit);
        } else if (bitValue != 0) {
            return;
        }
    }
    const std::uint8_t first = static_cast<std::uint8_t>(code);
    const std::uint8_t second = static_cast<std::uint8_t>(code >> 8U);
    const std::uint8_t command = static_cast<std::uint8_t>(code >> 16U);
    const std::uint8_t commandInverse = static_cast<std::uint8_t>(code >> 24U);
    if (static_cast<std::uint8_t>(command ^ commandInverse) != 0xFFU) return;
    const bool standard = static_cast<std::uint8_t>(first ^ second) == 0xFFU;
    decode_.protocol = standard
        ? domain::captures::InfraredProtocol::Nec
        : domain::captures::InfraredProtocol::NecExtended;
    decode_.rawCode = code;
    decode_.address = standard
        ? first
        : static_cast<std::uint16_t>(first |
              (static_cast<std::uint16_t>(second) << 8U));
    decode_.command = command;
    decode_.integrityValid = true;
}

bool InfraredCapture::cancel(std::uint64_t endedUs) {
    if ((stats_.state != InfraredCaptureState::Waiting &&
         stats_.state != InfraredCaptureState::Capturing) ||
        endedUs < stats_.startedUs) {
        return false;
    }
    stats_.state = InfraredCaptureState::Cancelled;
    stats_.endedUs = endedUs;
    return true;
}

bool InfraredCapture::fail(std::int32_t driverError,
                           std::uint64_t endedUs) {
    if ((stats_.state != InfraredCaptureState::Waiting &&
         stats_.state != InfraredCaptureState::Capturing) ||
        endedUs < stats_.startedUs) {
        return false;
    }
    stats_.state = InfraredCaptureState::Failed;
    stats_.endedUs = endedUs;
    stats_.driverError = driverError;
    return true;
}

void InfraredCapture::reset() {
    pulses_.fill(0);
    plan_ = {};
    stats_ = {};
    decode_ = {};
    size_ = 0;
    currentLevel_ = true;
    currentLevelSinceUs_ = 0;
    lastSampleUs_ = 0;
}

bool InfraredCapture::pulseView(
    std::size_t index,
    domain::captures::InfraredRawPulseView* output) const {
    if (output == nullptr || index >= size_) return false;
    output->durationUs = pulses_[index];
    return output->durationUs != 0;
}

}  // namespace leshy1::apps::capture
