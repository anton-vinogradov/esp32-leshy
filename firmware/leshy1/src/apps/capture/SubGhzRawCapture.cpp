#include "SubGhzRawCapture.h"

#include <limits>

namespace leshy1::apps::capture {

const char* subGhzRawCaptureStateName(SubGhzRawCaptureState state) {
    switch (state) {
        case SubGhzRawCaptureState::Idle: return "idle";
        case SubGhzRawCaptureState::Waiting: return "waiting";
        case SubGhzRawCaptureState::Capturing: return "capturing";
        case SubGhzRawCaptureState::Complete: return "complete";
        case SubGhzRawCaptureState::TimedOut: return "timed_out";
        case SubGhzRawCaptureState::SignalTooLong: return "signal_too_long";
        case SubGhzRawCaptureState::Cancelled: return "cancelled";
        case SubGhzRawCaptureState::Failed: return "failed";
    }
    return "unknown";
}

bool validateSubGhzRawCapturePlan(const SubGhzRawCapturePlan& plan) {
    const bool tunable =
        (plan.frequencyKHz >= 300000U && plan.frequencyKHz <= 348000U) ||
        (plan.frequencyKHz >= 387000U && plan.frequencyKHz <= 464000U) ||
        (plan.frequencyKHz >= 779000U && plan.frequencyKHz <= 928000U);
    return tunable && plan.thresholdDbm >= -110 && plan.thresholdDbm <= -30 &&
           plan.waitTimeoutMs >= 1000U && plan.waitTimeoutMs <= 300000U &&
           plan.maximumCaptureMs >= 100U &&
           plan.maximumCaptureMs <= 60000U &&
           plan.debounceUs >= 20U && plan.debounceUs <= 1000U &&
           plan.minimumFskPulseUs >= 1U &&
           plan.minimumFskPulseUs <= 1000U &&
           plan.endGapUs >= 5000U && plan.endGapUs <= 60000U &&
           plan.maximumPulses >= 2U &&
           plan.maximumPulses <= SubGhzRawCapture::kPulseCapacity &&
           (plan.modulation ==
                domain::captures::SubGhzRawModulation::OokEnvelope ||
            plan.modulation ==
                domain::captures::SubGhzRawModulation::FskAsync);
}

bool SubGhzRawCapture::begin(const SubGhzRawCapturePlan& plan,
                             std::uint64_t startedUs) {
    if (stats_.state != SubGhzRawCaptureState::Idle || startedUs == 0U ||
        !validateSubGhzRawCapturePlan(plan)) {
        return false;
    }
    plan_ = plan;
    stats_ = {};
    stats_.state = SubGhzRawCaptureState::Waiting;
    stats_.startedUs = startedUs;
    size_ = 0;
    candidateValid_ = false;
    candidateSinceUs_ = 0;
    stableSinceUs_ = 0;
    lastSampleUs_ = 0;
    fskLevel_ = false;
    fskLevelValid_ = false;
    return true;
}

bool SubGhzRawCapture::acceptStableLevel(bool level,
                                         std::uint64_t monotonicUs) {
    if (stats_.state == SubGhzRawCaptureState::Waiting) {
        if (!level) return false;
        stats_.state = SubGhzRawCaptureState::Capturing;
        stats_.signalStartedUs = candidateSinceUs_;
        stats_.startLevel = true;
        stableLevel_ = true;
        stableSinceUs_ = candidateSinceUs_;
        return true;
    }
    if (stats_.state != SubGhzRawCaptureState::Capturing ||
        level == stableLevel_ || monotonicUs < stableSinceUs_) {
        return false;
    }
    if (plan_.modulation ==
        domain::captures::SubGhzRawModulation::FskAsync) {
        stableLevel_ = level;
        stableSinceUs_ = candidateSinceUs_;
        return true;
    }
    const std::uint64_t duration = candidateSinceUs_ - stableSinceUs_;
    if (duration == 0U) return false;
    if (size_ >= plan_.maximumPulses || size_ >= pulses_.size()) {
        return finish(candidateSinceUs_, true);
    }
    if (duration > std::numeric_limits<std::uint16_t>::max()) {
        stats_.truncated = true;
    }
    pulses_[size_++] = static_cast<std::uint16_t>(
        duration > std::numeric_limits<std::uint16_t>::max()
            ? std::numeric_limits<std::uint16_t>::max() : duration);
    stats_.pulsesAccepted = static_cast<std::uint32_t>(size_);
    stableLevel_ = level;
    stableSinceUs_ = candidateSinceUs_;
    if (size_ >= plan_.maximumPulses || size_ >= pulses_.size()) {
        return finish(candidateSinceUs_, true);
    }
    return true;
}

bool SubGhzRawCapture::ingest(const SubGhzRawRssiSample& sample) {
    if (stats_.state != SubGhzRawCaptureState::Waiting &&
        stats_.state != SubGhzRawCaptureState::Capturing) {
        return false;
    }
    ++stats_.samples;
    if (sample.monotonicUs == 0U ||
        sample.monotonicUs < stats_.startedUs ||
        sample.monotonicUs < lastSampleUs_ || sample.rssiDbm < -127 ||
        sample.rssiDbm > 0) {
        ++stats_.invalidSamples;
        return false;
    }
    lastSampleUs_ = sample.monotonicUs;
    const bool level = sample.rssiDbm > plan_.thresholdDbm;
    if (!candidateValid_ || level != candidateLevel_) {
        if (candidateValid_ && sample.monotonicUs - candidateSinceUs_ <
                                   plan_.debounceUs) {
            ++stats_.shortTransitionsRejected;
        }
        candidateValid_ = true;
        candidateLevel_ = level;
        candidateSinceUs_ = sample.monotonicUs;
        return service(sample.monotonicUs);
    }
    bool changed = false;
    if (sample.monotonicUs - candidateSinceUs_ >= plan_.debounceUs &&
        (stats_.state == SubGhzRawCaptureState::Waiting ||
         candidateLevel_ != stableLevel_)) {
        changed = acceptStableLevel(candidateLevel_, sample.monotonicUs);
    }
    return service(sample.monotonicUs) || changed;
}

bool SubGhzRawCapture::armFskEdges(bool startLevel,
                                   std::uint64_t monotonicUs) {
    if (plan_.modulation !=
            domain::captures::SubGhzRawModulation::FskAsync ||
        stats_.state != SubGhzRawCaptureState::Capturing ||
        monotonicUs < stats_.signalStartedUs) {
        return false;
    }
    if (!fskLevelValid_) stats_.startLevel = startLevel;
    fskLevel_ = startLevel;
    fskLevelValid_ = true;
    return true;
}

bool SubGhzRawCapture::ingestFskEdge(
    std::uint32_t durationUs, bool newLevel, bool transportClipped,
    std::uint64_t monotonicUs) {
    if (plan_.modulation !=
            domain::captures::SubGhzRawModulation::FskAsync ||
        stats_.state != SubGhzRawCaptureState::Capturing ||
        !fskLevelValid_ || monotonicUs < stats_.signalStartedUs ||
        durationUs == 0U) {
        ++stats_.invalidSamples;
        return false;
    }
    if (newLevel == fskLevel_) return false;
    if (durationUs < plan_.minimumFskPulseUs) {
        ++stats_.shortTransitionsRejected;
        return false;
    }
    if (size_ >= plan_.maximumPulses || size_ >= pulses_.size()) {
        return finish(monotonicUs, true);
    }
    const bool clipped = transportClipped ||
        durationUs > std::numeric_limits<std::uint16_t>::max();
    pulses_[size_++] = static_cast<std::uint16_t>(
        clipped ? std::numeric_limits<std::uint16_t>::max() : durationUs);
    stats_.truncated = stats_.truncated || clipped;
    stats_.pulsesAccepted = static_cast<std::uint32_t>(size_);
    fskLevel_ = newLevel;
    if (size_ >= plan_.maximumPulses || size_ >= pulses_.size()) {
        return finish(monotonicUs, true);
    }
    return true;
}

bool SubGhzRawCapture::finishFskTransport(
    std::uint64_t monotonicUs, bool overflowed) {
    if (plan_.modulation !=
            domain::captures::SubGhzRawModulation::FskAsync ||
        stats_.state != SubGhzRawCaptureState::Capturing ||
        monotonicUs < stats_.signalStartedUs) {
        return false;
    }
    if (overflowed) return finish(monotonicUs, true);
    return false;
}

bool SubGhzRawCapture::service(std::uint64_t monotonicUs) {
    if (monotonicUs == 0U || monotonicUs < stats_.startedUs) return false;
    if (stats_.state == SubGhzRawCaptureState::Waiting &&
        monotonicUs - stats_.startedUs >=
            static_cast<std::uint64_t>(plan_.waitTimeoutMs) * 1000U) {
        stats_.state = SubGhzRawCaptureState::TimedOut;
        stats_.endedUs = monotonicUs;
        return true;
    }
    if (stats_.state == SubGhzRawCaptureState::Capturing &&
        !stableLevel_ && monotonicUs - stableSinceUs_ >= plan_.endGapUs) {
        if (plan_.modulation ==
                domain::captures::SubGhzRawModulation::FskAsync &&
            size_ == 0U) {
            stats_.state = SubGhzRawCaptureState::TimedOut;
            stats_.endedUs = monotonicUs;
            return true;
        }
        return finish(monotonicUs, false);
    }
    if (stats_.state == SubGhzRawCaptureState::Capturing &&
        monotonicUs - stats_.signalStartedUs >=
            static_cast<std::uint64_t>(plan_.maximumCaptureMs) * 1000U) {
        stats_.state = SubGhzRawCaptureState::SignalTooLong;
        stats_.endedUs = monotonicUs;
        return true;
    }
    return false;
}

bool SubGhzRawCapture::finish(std::uint64_t endedUs, bool truncated) {
    if (stats_.state != SubGhzRawCaptureState::Capturing ||
        endedUs < stats_.signalStartedUs) {
        return false;
    }
    stats_.state = SubGhzRawCaptureState::Complete;
    stats_.endedUs = endedUs;
    stats_.truncated = stats_.truncated || truncated;
    return true;
}

bool SubGhzRawCapture::cancel(std::uint64_t endedUs) {
    if ((stats_.state != SubGhzRawCaptureState::Waiting &&
         stats_.state != SubGhzRawCaptureState::Capturing) ||
        endedUs < stats_.startedUs) {
        return false;
    }
    stats_.state = SubGhzRawCaptureState::Cancelled;
    stats_.endedUs = endedUs;
    return true;
}

bool SubGhzRawCapture::fail(std::int32_t driverError,
                            std::uint64_t endedUs) {
    if ((stats_.state != SubGhzRawCaptureState::Waiting &&
         stats_.state != SubGhzRawCaptureState::Capturing) ||
        endedUs < stats_.startedUs) {
        return false;
    }
    stats_.state = SubGhzRawCaptureState::Failed;
    stats_.endedUs = endedUs;
    stats_.driverError = driverError;
    return true;
}

void SubGhzRawCapture::reset() {
    pulses_.fill(0);
    plan_ = {};
    stats_ = {};
    size_ = 0;
    candidateLevel_ = false;
    stableLevel_ = false;
    candidateValid_ = false;
    candidateSinceUs_ = 0;
    stableSinceUs_ = 0;
    lastSampleUs_ = 0;
    fskLevel_ = false;
    fskLevelValid_ = false;
}

bool SubGhzRawCapture::pulseView(
    std::size_t index, domain::captures::SubGhzRawPulseView* output) const {
    if (output == nullptr || index >= size_) return false;
    output->durationUs = pulses_[index];
    return true;
}

}  // namespace leshy1::apps::capture
