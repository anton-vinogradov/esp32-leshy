#include "WifiFrameCapture.h"

#include <cstring>

namespace leshy1::apps::capture {

const char* wifiFrameKindName(WifiFrameKind kind) {
    switch (kind) {
        case WifiFrameKind::Management: return "management";
        case WifiFrameKind::Control: return "control";
        case WifiFrameKind::Data: return "data";
    }
    return "unknown";
}

const char* wifiFrameCaptureStateName(WifiFrameCaptureState state) {
    switch (state) {
        case WifiFrameCaptureState::Idle: return "idle";
        case WifiFrameCaptureState::Running: return "running";
        case WifiFrameCaptureState::Complete: return "complete";
        case WifiFrameCaptureState::Failed: return "failed";
    }
    return "unknown";
}

bool validateWifiFrameCapturePlan(const WifiFrameCapturePlan& plan) {
    return plan.channel <= 13U && plan.durationMs >= 500U &&
           plan.durationMs <= 30000U && plan.channelDwellMs >= 50U &&
           plan.channelDwellMs <= 1000U && plan.snapLength >= 32U &&
           plan.snapLength <= WifiFrame::kPayloadCapacity &&
           plan.maximumFrames > 0U &&
           plan.maximumFrames <= WifiFrameCapture::kFrameCapacity;
}

bool WifiFrameCapture::begin(const WifiFrameCapturePlan& plan,
                             std::uint64_t startedUs) {
    if (stats_.state != WifiFrameCaptureState::Idle || startedUs == 0U ||
        !validateWifiFrameCapturePlan(plan)) {
        return false;
    }
    plan_ = plan;
    stats_ = {};
    stats_.state = WifiFrameCaptureState::Running;
    stats_.startedUs = startedUs;
    size_ = 0;
    return true;
}

bool WifiFrameCapture::append(const std::uint8_t* payload,
                              std::uint16_t originalLength,
                              std::uint64_t monotonicUs,
                              std::int16_t rssiDbm, std::uint8_t channel,
                              WifiFrameKind kind, bool fcsIncluded) {
    if (stats_.state != WifiFrameCaptureState::Running) return false;
    ++stats_.framesReported;
    if (payload == nullptr || originalLength == 0U || monotonicUs == 0U ||
        monotonicUs < stats_.startedUs || channel == 0U || channel > 14U) {
        ++stats_.framesDroppedInvalid;
        return false;
    }
    if (size_ >= plan_.maximumFrames || size_ >= frames_.size()) {
        ++stats_.framesDroppedCapacity;
        return false;
    }

    WifiFrame& frame = frames_[size_];
    frame = {};
    frame.monotonicUs = monotonicUs;
    frame.originalLength = originalLength;
    frame.capturedLength = originalLength < plan_.snapLength
                               ? originalLength : plan_.snapLength;
    frame.rssiDbm = rssiDbm;
    frame.channel = channel;
    frame.kind = kind;
    frame.fcsIncluded = fcsIncluded;
    std::memcpy(frame.payload.data(), payload, frame.capturedLength);
    ++size_;
    ++stats_.framesAccepted;
    stats_.payloadBytes += frame.capturedLength;
    return true;
}

bool WifiFrameCapture::complete(std::uint64_t endedUs) {
    if (stats_.state != WifiFrameCaptureState::Running ||
        endedUs < stats_.startedUs) {
        return false;
    }
    stats_.state = WifiFrameCaptureState::Complete;
    stats_.endedUs = endedUs;
    return true;
}

bool WifiFrameCapture::fail(std::int32_t driverError,
                            std::uint64_t endedUs) {
    if (stats_.state != WifiFrameCaptureState::Running ||
        endedUs < stats_.startedUs) {
        return false;
    }
    stats_.state = WifiFrameCaptureState::Failed;
    stats_.endedUs = endedUs;
    stats_.driverError = driverError;
    return true;
}

void WifiFrameCapture::reset() {
    frames_.fill(WifiFrame{});
    plan_ = {};
    stats_ = {};
    size_ = 0;
}

const WifiFrame* WifiFrameCapture::frame(std::size_t index) const {
    return index < size_ ? &frames_[index] : nullptr;
}

bool WifiFrameCapture::frameView(
    std::size_t index, domain::captures::WifiFrameView* output) const {
    const WifiFrame* stored = frame(index);
    if (stored == nullptr || output == nullptr) return false;
    output->monotonicUs = stored->monotonicUs;
    output->capturedLength = stored->capturedLength;
    output->originalLength = stored->originalLength;
    output->rssiDbm = stored->rssiDbm;
    output->channel = stored->channel;
    output->kind = stored->kind;
    output->fcsIncluded = stored->fcsIncluded;
    output->payload = stored->payload.data();
    return true;
}

}  // namespace leshy1::apps::capture
