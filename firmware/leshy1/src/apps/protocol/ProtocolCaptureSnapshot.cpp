#include "ProtocolCaptureSnapshot.h"

namespace leshy1::apps::protocol {

ProtocolCaptureSnapshotStatus ProtocolCaptureSnapshot::copyFrom(
    const domain::captures::InfraredRawSource& source) {
    clear();
    const std::size_t count = source.pulseCount();
    if (count < 2U || count > durations_.size()) {
        return ProtocolCaptureSnapshotStatus::InvalidArgument;
    }
    for (std::size_t index = 0U; index < count; ++index) {
        domain::captures::InfraredRawPulseView pulse;
        if (!source.pulseView(index, &pulse) || pulse.durationUs == 0U) {
            clear();
            return ProtocolCaptureSnapshotStatus::SourceReadFailed;
        }
        durations_[index] = pulse.durationUs;
    }
    count_ = count;
    return ProtocolCaptureSnapshotStatus::Valid;
}

void ProtocolCaptureSnapshot::clear() {
    durations_.fill(0U);
    count_ = 0U;
}

bool ProtocolCaptureSnapshot::pulseView(
    std::size_t index,
    domain::captures::InfraredRawPulseView* output) const {
    if (output == nullptr || index >= count_) return false;
    output->durationUs = durations_[index];
    return output->durationUs != 0U;
}

}  // namespace leshy1::apps::protocol
