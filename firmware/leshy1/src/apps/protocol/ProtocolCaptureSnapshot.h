#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "ProtocolWorkbench.h"

namespace leshy1::apps::protocol {

enum class ProtocolCaptureSnapshotStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    SourceReadFailed,
};

// A short-lived bounded foreground copy used only while the shared Session
// codec buffer is reopened on another exact generation. It is never persisted
// and the comparison/derived records still own no raw Capture pulses.
class ProtocolCaptureSnapshot final
    : public domain::captures::InfraredRawSource {
public:
    ProtocolCaptureSnapshotStatus copyFrom(
        const domain::captures::InfraredRawSource& source);
    void clear();

    std::size_t pulseCount() const override { return count_; }
    bool pulseView(std::size_t index,
                   domain::captures::InfraredRawPulseView* output) const override;

private:
    std::array<std::uint16_t,
               ProtocolWorkbenchWorkspace::kMaximumPulses> durations_{};
    std::size_t count_ = 0U;
};

}  // namespace leshy1::apps::protocol
