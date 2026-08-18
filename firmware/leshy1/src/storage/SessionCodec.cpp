#include "SessionCodec.h"

#include <cstdio>
#include <cstring>
#include <limits>

#include "AtomicHead.h"

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kSegmentMagic[4] = {'L', 'S', 'H', 'S'};
constexpr std::uint8_t kTimelineMagic[4] = {'L', 'T', 'L', 'N'};
constexpr std::uint8_t kTimelineWireVersion = 1;
constexpr std::size_t kTimelineHeaderBytes = 40;
constexpr std::size_t kTimelineSummaryBytes = 60;
constexpr std::size_t kTimelineWindowBytes = 36;
constexpr std::uint8_t kCaptureMagic[4] = {'L', 'C', 'A', 'P'};
constexpr std::uint8_t kCaptureWireVersion = 1;
constexpr std::uint8_t kWifiFrameCaptureWireVersion = 2;
constexpr std::size_t kCaptureRecordBytes = 72;
constexpr std::uint8_t kWifiFrameMagic[4] = {'L', 'W', 'F', 'C'};
constexpr std::uint8_t kWifiFrameWireVersion = 1;
constexpr std::size_t kWifiFrameHeaderBytes = 16;
constexpr std::size_t kWifiFrameRecordHeaderBytes = 20;
constexpr std::uint8_t kCaptureFlagPassive = 1U << 0U;
constexpr std::uint8_t kCaptureFlagWifiShowHidden = 1U << 1U;
constexpr std::uint8_t kCaptureFlagLocation = 1U << 2U;
constexpr std::uint8_t kCaptureFlagFramePayload = 1U << 3U;
constexpr std::uint8_t kCaptureKnownFlags =
    kCaptureFlagPassive | kCaptureFlagWifiShowHidden |
    kCaptureFlagLocation | kCaptureFlagFramePayload;

void put16(std::uint8_t* output, std::uint16_t value) {
    output[0] = static_cast<std::uint8_t>(value >> 8U);
    output[1] = static_cast<std::uint8_t>(value);
}

void put32(std::uint8_t* output, std::uint32_t value) {
    output[0] = static_cast<std::uint8_t>(value >> 24U);
    output[1] = static_cast<std::uint8_t>(value >> 16U);
    output[2] = static_cast<std::uint8_t>(value >> 8U);
    output[3] = static_cast<std::uint8_t>(value);
}

void put64(std::uint8_t* output, std::uint64_t value) {
    for (std::size_t index = 0; index < 8; ++index) {
        output[index] = static_cast<std::uint8_t>(
            value >> ((7U - index) * 8U));
    }
}

std::uint16_t get16(const std::uint8_t* input) {
    return static_cast<std::uint16_t>((static_cast<std::uint16_t>(input[0]) << 8U) |
                                      static_cast<std::uint16_t>(input[1]));
}

std::uint32_t get32(const std::uint8_t* input) {
    return (static_cast<std::uint32_t>(input[0]) << 24U) |
           (static_cast<std::uint32_t>(input[1]) << 16U) |
           (static_cast<std::uint32_t>(input[2]) << 8U) |
           static_cast<std::uint32_t>(input[3]);
}

std::uint64_t get64(const std::uint8_t* input) {
    std::uint64_t value = 0;
    for (std::size_t index = 0; index < 8; ++index) {
        value = (value << 8U) | input[index];
    }
    return value;
}

class CborWriter final {
public:
    CborWriter(std::uint8_t* output, std::size_t capacity)
        : output_(output), capacity_(capacity) {}

    bool unsignedValue(std::uint64_t value) { return typeValue(0, value); }
    bool signedValue(std::int64_t value) {
        return value >= 0 ? typeValue(0, static_cast<std::uint64_t>(value))
                          : typeValue(1, static_cast<std::uint64_t>(-1 - value));
    }
    bool map(std::uint64_t size) { return typeValue(5, size); }
    bool array(std::uint64_t size) { return typeValue(4, size); }
    bool text(const char* value, std::size_t size) {
        return value != nullptr && typeValue(3, size) && raw(value, size);
    }
    bool bytes(const std::uint8_t* value, std::size_t size) {
        return (value != nullptr || size == 0) && typeValue(2, size) && raw(value, size);
    }
    bool be32(std::uint32_t value) {
        std::uint8_t wire[4] = {};
        put32(wire, value);
        return raw(wire, sizeof(wire));
    }
    bool raw(const void* value, std::size_t size) {
        if (!ok_ || (value == nullptr && size != 0) || size > capacity_ - position_) {
            ok_ = false;
            return false;
        }
        if (size != 0) std::memcpy(output_ + position_, value, size);
        position_ += size;
        return true;
    }
    bool ok() const { return ok_; }
    std::size_t size() const { return position_; }

private:
    bool typeValue(std::uint8_t major, std::uint64_t value) {
        std::uint8_t wire[9] = {};
        std::size_t size = 1;
        if (value < 24) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | value);
        } else if (value <= 0xFFU) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 24U);
            wire[1] = static_cast<std::uint8_t>(value);
            size = 2;
        } else if (value <= 0xFFFFU) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 25U);
            put16(wire + 1, static_cast<std::uint16_t>(value));
            size = 3;
        } else if (value <= 0xFFFFFFFFU) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 26U);
            put32(wire + 1, static_cast<std::uint32_t>(value));
            size = 5;
        } else {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 27U);
            for (std::size_t index = 0; index < 8; ++index) {
                wire[index + 1] =
                    static_cast<std::uint8_t>(value >> ((7U - index) * 8U));
            }
            size = 9;
        }
        return raw(wire, size);
    }

    std::uint8_t* output_ = nullptr;
    std::size_t capacity_ = 0;
    std::size_t position_ = 0;
    bool ok_ = true;
};

class CborReader final {
public:
    CborReader(const std::uint8_t* input, std::size_t size) : input_(input), size_(size) {}

    bool unsignedValue(std::uint64_t* value) { return typeValue(0, value); }
    bool map(std::uint64_t* value) { return typeValue(5, value); }
    bool array(std::uint64_t* value) { return typeValue(4, value); }
    bool signedValue(std::int64_t* value) {
        if (value == nullptr || position_ >= size_) return false;
        const std::uint8_t major = input_[position_] >> 5U;
        std::uint64_t encoded = 0;
        if (major != 0 && major != 1) return false;
        if (!typeValue(major, &encoded)) return false;
        if (major == 0) {
            if (encoded > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
                return false;
            }
            *value = static_cast<std::int64_t>(encoded);
        } else {
            if (encoded > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
                return false;
            }
            *value = -1 - static_cast<std::int64_t>(encoded);
        }
        return true;
    }
    bool text(const std::uint8_t** value, std::size_t* length) {
        return sizedValue(3, value, length);
    }
    bool bytes(const std::uint8_t** value, std::size_t* length) {
        return sizedValue(2, value, length);
    }
    bool complete() const { return position_ == size_; }

private:
    bool typeValue(std::uint8_t expectedMajor, std::uint64_t* value) {
        if (value == nullptr || position_ >= size_) return false;
        const std::uint8_t initial = input_[position_++];
        if ((initial >> 5U) != expectedMajor) return false;
        const std::uint8_t additional = initial & 0x1FU;
        if (additional < 24) {
            *value = additional;
            return true;
        }
        std::size_t bytes = 0;
        if (additional == 24) bytes = 1;
        else if (additional == 25) bytes = 2;
        else if (additional == 26) bytes = 4;
        else if (additional == 27) bytes = 8;
        else return false;
        if (bytes > size_ - position_) return false;
        std::uint64_t decoded = 0;
        for (std::size_t index = 0; index < bytes; ++index) {
            decoded = (decoded << 8U) | input_[position_++];
        }
        if ((bytes == 1 && decoded < 24) || (bytes == 2 && decoded <= 0xFFU) ||
            (bytes == 4 && decoded <= 0xFFFFU) ||
            (bytes == 8 && decoded <= 0xFFFFFFFFU)) {
            return false;
        }
        *value = decoded;
        return true;
    }

    bool sizedValue(std::uint8_t major, const std::uint8_t** value, std::size_t* length) {
        if (value == nullptr || length == nullptr) return false;
        std::uint64_t decodedLength = 0;
        if (!typeValue(major, &decodedLength) || decodedLength > size_ - position_) return false;
        *value = input_ + position_;
        *length = static_cast<std::size_t>(decodedLength);
        position_ += *length;
        return true;
    }

    const std::uint8_t* input_ = nullptr;
    std::size_t size_ = 0;
    std::size_t position_ = 0;
};

bool key(CborReader& reader, std::uint64_t expected) {
    std::uint64_t actual = 0;
    return reader.unsignedValue(&actual) && actual == expected;
}

bool validSessionId(const std::uint8_t* value, std::size_t size) {
    if (value == nullptr || size == 0 || size > services::survey::SurveySession::kSessionIdCapacity) {
        return false;
    }
    for (std::size_t index = 0; index < size; ++index) {
        const char character = static_cast<char>(value[index]);
        const bool allowed = (character >= 'a' && character <= 'z') ||
                             (character >= 'A' && character <= 'Z') ||
                             (character >= '0' && character <= '9') || character == '-' ||
                             character == '_';
        if (!allowed) return false;
    }
    return true;
}

SessionCodecStatus encodeObservation(const domain::observations::Observation& observation,
                                     std::uint8_t* output, std::size_t capacity,
                                     std::size_t* outputSize) {
    const bool wifi =
        observation.radio == domain::observations::RadioKind::Wifi;
    const bool ble = observation.radio == domain::observations::RadioKind::Ble;
    const bool validRadioFields =
        (wifi && observation.channel > 0 && observation.channel <= 14 &&
         observation.frequencyKhz > 0) ||
        (ble && observation.channel == 0 && observation.frequencyKhz == 0);
    if (output == nullptr || outputSize == nullptr ||
        (!wifi && !ble) || !validRadioFields ||
        observation.identityLength == 0 ||
        observation.identityLength > observation.identity.size() ||
        observation.labelLength > domain::observations::Observation::kLabelCapacity ||
        observation.rssiDbm < -127 || observation.rssiDbm > 0) {
        return SessionCodecStatus::InvalidArgument;
    }
    CborWriter writer(output, capacity);
    writer.map(8);
    writer.unsignedValue(0);
    writer.unsignedValue(observation.sequence);
    writer.unsignedValue(1);
    writer.unsignedValue(observation.monotonicUs);
    writer.unsignedValue(2);
    writer.unsignedValue(static_cast<std::uint8_t>(observation.radio));
    writer.unsignedValue(3);
    writer.unsignedValue(observation.frequencyKhz);
    writer.unsignedValue(4);
    writer.unsignedValue(observation.channel);
    writer.unsignedValue(5);
    writer.signedValue(observation.rssiDbm);
    writer.unsignedValue(6);
    writer.bytes(observation.identity.data(), observation.identityLength);
    writer.unsignedValue(7);
    writer.text(observation.label.data(), observation.labelLength);
    if (!writer.ok()) return SessionCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeObservation(const std::uint8_t* input, std::size_t size,
                                     domain::observations::Observation* output) {
    if (input == nullptr || output == nullptr) return SessionCodecStatus::InvalidArgument;
    CborReader reader(input, size);
    std::uint64_t count = 0;
    if (!reader.map(&count) || count != 8) return SessionCodecStatus::Malformed;
    domain::observations::Observation observation;
    std::uint64_t unsignedValue = 0;
    std::int64_t signedValue = 0;
    if (!key(reader, 0) || !reader.unsignedValue(&observation.sequence) ||
        !key(reader, 1) || !reader.unsignedValue(&observation.monotonicUs) ||
        !key(reader, 2) || !reader.unsignedValue(&unsignedValue) ||
        (unsignedValue != static_cast<std::uint8_t>(
                              domain::observations::RadioKind::Wifi) &&
         unsignedValue != static_cast<std::uint8_t>(
                              domain::observations::RadioKind::Ble))) {
        return SessionCodecStatus::Malformed;
    }
    observation.radio = static_cast<domain::observations::RadioKind>(
        static_cast<std::uint8_t>(unsignedValue));
    if (!key(reader, 3) || !reader.unsignedValue(&unsignedValue) ||
        unsignedValue > std::numeric_limits<std::uint32_t>::max()) {
        return SessionCodecStatus::Malformed;
    }
    observation.frequencyKhz = static_cast<std::uint32_t>(unsignedValue);
    if (!key(reader, 4) || !reader.unsignedValue(&unsignedValue) ||
        unsignedValue > std::numeric_limits<std::uint16_t>::max()) {
        return SessionCodecStatus::Malformed;
    }
    observation.channel = static_cast<std::uint16_t>(unsignedValue);
    if (!key(reader, 5) || !reader.signedValue(&signedValue) || signedValue < -127 ||
        signedValue > 0) {
        return SessionCodecStatus::Malformed;
    }
    observation.rssiDbm = static_cast<std::int16_t>(signedValue);
    const std::uint8_t* bytes = nullptr;
    std::size_t length = 0;
    if (!key(reader, 6) || !reader.bytes(&bytes, &length) || length == 0 ||
        length > observation.identity.size()) {
        return SessionCodecStatus::BoundsExceeded;
    }
    std::memcpy(observation.identity.data(), bytes, length);
    observation.identityLength = static_cast<std::uint8_t>(length);
    if (!key(reader, 7) || !reader.text(&bytes, &length) ||
        length > domain::observations::Observation::kLabelCapacity) {
        return SessionCodecStatus::BoundsExceeded;
    }
    std::memcpy(observation.label.data(), bytes, length);
    observation.label[length] = '\0';
    observation.labelLength = static_cast<std::uint8_t>(length);
    if (!reader.complete()) return SessionCodecStatus::TrailingData;
    const bool validRadioFields =
        (observation.radio == domain::observations::RadioKind::Wifi &&
         observation.channel > 0 && observation.channel <= 14 &&
         observation.frequencyKhz > 0) ||
        (observation.radio == domain::observations::RadioKind::Ble &&
         observation.channel == 0 && observation.frequencyKhz == 0);
    if (observation.sequence == 0 || observation.monotonicUs == 0 ||
        !validRadioFields) {
        return SessionCodecStatus::Malformed;
    }
    *output = observation;
    return SessionCodecStatus::Valid;
}

void encodeTimelineSummary(
    const services::survey::SourceRuntimeSummary& summary,
    std::uint8_t* output) {
    output[0] = summary.selected ? 1 : 0;
    output[1] = static_cast<std::uint8_t>(summary.state);
    output[2] = 0;
    output[3] = 0;
    put64(output + 4, summary.scheduledUs);
    put64(output + 12, summary.activeUs);
    put64(output + 20, summary.unavailableUs);
    put64(output + 28, summary.faultUs);
    put64(output + 36, summary.accepted);
    put64(output + 44, summary.dropped);
    put32(output + 52, summary.windows);
    put32(output + 56, summary.transitions);
}

bool decodeTimelineSummary(
    const std::uint8_t* input,
    services::survey::SourceRuntimeSummary* output) {
    if (input == nullptr || output == nullptr || input[0] > 1 ||
        input[1] > static_cast<std::uint8_t>(
            services::survey::SourceWindowState::Stopped) ||
        input[2] != 0 || input[3] != 0) {
        return false;
    }
    output->selected = input[0] != 0;
    output->state = static_cast<services::survey::SourceWindowState>(input[1]);
    output->scheduledUs = get64(input + 4);
    output->activeUs = get64(input + 12);
    output->unavailableUs = get64(input + 20);
    output->faultUs = get64(input + 28);
    output->accepted = get64(input + 36);
    output->dropped = get64(input + 44);
    output->windows = get32(input + 52);
    output->transitions = get32(input + 56);
    return true;
}

SessionCodecStatus encodeTimelineRecord(
    const services::survey::SurveySession& session, std::uint8_t* output,
    std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr) {
        return SessionCodecStatus::InvalidArgument;
    }
    const services::survey::SessionTimelineSummary& timeline = session.timeline();
    const std::size_t retained = session.timelineWindowCount();
    const std::size_t required = kTimelineHeaderBytes +
        services::survey::SourceTimeline::kSourceCount * kTimelineSummaryBytes +
        retained * kTimelineWindowBytes;
    if (!timeline.present || !timeline.finalized || timeline.selectedMask == 0 ||
        retained > services::survey::SurveySession::kTimelineWindowCapacity ||
        timeline.totalWindows != timeline.evictedWindows + retained ||
        timeline.startedUs < session.startedUs() ||
        timeline.stoppedUs < timeline.startedUs ||
        timeline.stoppedUs > session.stoppedUs()) {
        return SessionCodecStatus::TimelineInvalid;
    }
    if (required > capacity || required > kTimelineRecordMaxBytes) {
        return SessionCodecStatus::BufferTooSmall;
    }
    std::memset(output, 0, required);
    std::memcpy(output, kTimelineMagic, sizeof(kTimelineMagic));
    output[4] = kTimelineWireVersion;
    output[5] = timeline.selectedMask;
    output[6] = static_cast<std::uint8_t>(retained);
    output[7] = 1;  // finalized
    put64(output + 8, timeline.startedUs);
    put64(output + 16, timeline.stoppedUs);
    put32(output + 24, timeline.totalWindows);
    put32(output + 28, timeline.evictedWindows);
    put64(output + 32, timeline.overflowEvents);
    std::size_t position = kTimelineHeaderBytes;
    for (const services::survey::SourceRuntimeSummary& source : timeline.sources) {
        encodeTimelineSummary(source, output + position);
        position += kTimelineSummaryBytes;
    }
    for (std::size_t index = 0; index < retained; ++index) {
        const services::survey::SourceWindow* window =
            session.timelineWindow(index);
        if (window == nullptr) return SessionCodecStatus::TimelineInvalid;
        output[position] = static_cast<std::uint8_t>(window->source);
        output[position + 1] = static_cast<std::uint8_t>(window->state);
        output[position + 2] = static_cast<std::uint8_t>(window->reason);
        output[position + 3] = 0;
        put64(output + position + 4, window->startedUs);
        put64(output + position + 12, window->endedUs);
        put64(output + position + 20, window->accepted);
        put64(output + position + 28, window->dropped);
        position += kTimelineWindowBytes;
    }
    *outputSize = position;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeTimelineRecord(
    const std::uint8_t* input, std::size_t size,
    services::survey::SurveySession* output) {
    if (input == nullptr || output == nullptr || size < kTimelineHeaderBytes +
            services::survey::SourceTimeline::kSourceCount * kTimelineSummaryBytes ||
        size > kTimelineRecordMaxBytes ||
        std::memcmp(input, kTimelineMagic, sizeof(kTimelineMagic)) != 0 ||
        input[4] != kTimelineWireVersion || input[7] != 1) {
        return SessionCodecStatus::Malformed;
    }
    const std::uint8_t selectedMask = input[5];
    const std::size_t retained = input[6];
    const std::size_t expectedSize = kTimelineHeaderBytes +
        services::survey::SourceTimeline::kSourceCount * kTimelineSummaryBytes +
        retained * kTimelineWindowBytes;
    if (retained > services::survey::SurveySession::kTimelineWindowCapacity ||
        expectedSize != size) {
        return SessionCodecStatus::BoundsExceeded;
    }
    const std::uint64_t startedUs = get64(input + 8);
    const std::uint64_t stoppedUs = get64(input + 16);
    const std::uint32_t totalWindows = get32(input + 24);
    const std::uint32_t evictedWindows = get32(input + 28);
    const std::uint64_t overflowEvents = get64(input + 32);
    if (totalWindows != evictedWindows + retained || stoppedUs < startedUs) {
        return SessionCodecStatus::TimelineInvalid;
    }
    std::array<services::survey::SourceRuntimeSummary,
               services::survey::SourceTimeline::kSourceCount> sources{};
    std::size_t position = kTimelineHeaderBytes;
    for (services::survey::SourceRuntimeSummary& source : sources) {
        if (!decodeTimelineSummary(input + position, &source)) {
            return SessionCodecStatus::Malformed;
        }
        position += kTimelineSummaryBytes;
    }
    if (output->startTimeline(selectedMask, startedUs) !=
            services::survey::SessionTimelineStatus::Started ||
        output->restoreTimelineEvictions(evictedWindows) !=
            services::survey::SessionTimelineStatus::Appended) {
        return SessionCodecStatus::TimelineInvalid;
    }
    for (std::size_t index = 0; index < retained; ++index) {
        if (input[position + 3] != 0) return SessionCodecStatus::Malformed;
        services::survey::SourceWindow window;
        window.source = static_cast<domain::observations::RadioKind>(
            input[position]);
        window.state = static_cast<services::survey::SourceWindowState>(
            input[position + 1]);
        window.reason = static_cast<services::survey::SourceWindowReason>(
            input[position + 2]);
        window.startedUs = get64(input + position + 4);
        window.endedUs = get64(input + position + 12);
        window.accepted = get64(input + position + 20);
        window.dropped = get64(input + position + 28);
        if (output->appendTimelineWindow(window) !=
            services::survey::SessionTimelineStatus::Appended) {
            return SessionCodecStatus::TimelineInvalid;
        }
        position += kTimelineWindowBytes;
    }
    return output->finalizeTimeline(stoppedUs, sources[0], sources[1],
                                    overflowEvents) ==
            services::survey::SessionTimelineStatus::Finalized
        ? SessionCodecStatus::Valid : SessionCodecStatus::TimelineInvalid;
}

SessionCodecStatus encodeCaptureRecord(
    const services::survey::CaptureMetadata& metadata,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        capacity < kCaptureRecordBytes || !metadata.present ||
        metadata.appIdentityLength != metadata.appIdentity.size()) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::memset(output, 0, kCaptureRecordBytes);
    std::memcpy(output, kCaptureMagic, sizeof(kCaptureMagic));
    output[4] = metadata.framePayloadCaptured
        ? kWifiFrameCaptureWireVersion : kCaptureWireVersion;
    output[5] = metadata.selectedSourceMask;
    output[6] = (metadata.passive ? kCaptureFlagPassive : 0) |
        (metadata.wifiShowHidden ? kCaptureFlagWifiShowHidden : 0) |
        (metadata.locationPresent ? kCaptureFlagLocation : 0) |
        (metadata.framePayloadCaptured ? kCaptureFlagFramePayload : 0);
    output[7] = metadata.appIdentityLength;
    put32(output + 8, metadata.wifiMaxMsPerChannel);
    output[12] = metadata.wifiChannel;
    put32(output + 16, metadata.bleDurationMs);
    put16(output + 20, metadata.bleIntervalMs);
    put16(output + 22, metadata.bleWindowMs);
    put16(output + 24, metadata.bleMaximumRecords);
    put16(output + 26, metadata.framePayloadRecords);
    put16(output + 28, metadata.framePayloadSnapLength);
    output[30] = static_cast<std::uint8_t>(metadata.framePayloadFormat);
    put64(output + 32, metadata.framePayloadBytes);
    std::memcpy(output + 40, metadata.appIdentity.data(),
                metadata.appIdentity.size());
    *outputSize = kCaptureRecordBytes;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeCaptureRecord(
    const std::uint8_t* input, std::size_t size,
    services::survey::SurveySession* output) {
    if (input == nullptr || output == nullptr || size != kCaptureRecordBytes ||
        std::memcmp(input, kCaptureMagic, sizeof(kCaptureMagic)) != 0 ||
        (input[4] != kCaptureWireVersion &&
         input[4] != kWifiFrameCaptureWireVersion) || input[7] != 32 ||
        (input[6] & static_cast<std::uint8_t>(~kCaptureKnownFlags)) != 0 ||
        input[13] != 0 || input[14] != 0 || input[15] != 0 ||
        input[31] != 0) {
        return SessionCodecStatus::CaptureInvalid;
    }
    const bool payloadWire = input[4] == kWifiFrameCaptureWireVersion;
    if ((!payloadWire &&
         (input[26] != 0 || input[27] != 0 || input[28] != 0 ||
          input[29] != 0 || input[30] != 0 ||
          (input[6] & kCaptureFlagFramePayload) != 0)) ||
        (payloadWire && (input[6] & kCaptureFlagFramePayload) == 0)) {
        return SessionCodecStatus::CaptureInvalid;
    }
    services::survey::CaptureMetadata metadata;
    metadata.present = true;
    metadata.selectedSourceMask = input[5];
    metadata.passive = (input[6] & kCaptureFlagPassive) != 0;
    metadata.wifiShowHidden =
        (input[6] & kCaptureFlagWifiShowHidden) != 0;
    metadata.locationPresent = (input[6] & kCaptureFlagLocation) != 0;
    metadata.framePayloadCaptured =
        (input[6] & kCaptureFlagFramePayload) != 0;
    metadata.appIdentityLength = input[7];
    metadata.wifiMaxMsPerChannel = get32(input + 8);
    metadata.wifiChannel = input[12];
    metadata.bleDurationMs = get32(input + 16);
    metadata.bleIntervalMs = get16(input + 20);
    metadata.bleWindowMs = get16(input + 22);
    metadata.bleMaximumRecords = get16(input + 24);
    metadata.framePayloadRecords = get16(input + 26);
    metadata.framePayloadSnapLength = get16(input + 28);
    metadata.framePayloadFormat = static_cast<services::survey::FramePayloadFormat>(
        input[30]);
    metadata.framePayloadBytes = get64(input + 32);
    std::memcpy(metadata.appIdentity.data(), input + 40,
                metadata.appIdentity.size());
    return output->configureCaptureMetadata(metadata) ==
            services::survey::CaptureMetadataStatus::Configured
        ? SessionCodecStatus::Valid : SessionCodecStatus::CaptureInvalid;
}

SessionCodecStatus encodeWifiFrameBlock(
    const services::survey::SurveySession& session,
    const domain::captures::WifiFrameSource& frames,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr || frames.frameCount() == 0 ||
        frames.frameCount() > PersistedWifiFrameCaptureView::kFrameCapacity ||
        frames.snapLength() < 32 || frames.snapLength() > 256 ||
        capacity < kWifiFrameHeaderBytes) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::memset(output, 0, kWifiFrameHeaderBytes);
    std::memcpy(output, kWifiFrameMagic, sizeof(kWifiFrameMagic));
    output[4] = kWifiFrameWireVersion;
    output[5] = static_cast<std::uint8_t>(frames.frameCount());
    put16(output + 6, frames.snapLength());
    std::size_t position = kWifiFrameHeaderBytes;
    std::uint32_t payloadBytes = 0;
    std::uint64_t previousUs = 0;
    for (std::size_t index = 0; index < frames.frameCount(); ++index) {
        domain::captures::WifiFrameView frame;
        if (!frames.frameView(index, &frame) || frame.payload == nullptr ||
            frame.capturedLength == 0 ||
            frame.capturedLength > frames.snapLength() ||
            frame.capturedLength > frame.originalLength || frame.channel == 0 ||
            frame.channel > 14 || static_cast<std::uint8_t>(frame.kind) > 2 ||
            frame.monotonicUs < session.startedUs() ||
            frame.monotonicUs > session.stoppedUs() ||
            (previousUs != 0 && frame.monotonicUs < previousUs) ||
            kWifiFrameRecordHeaderBytes + frame.capturedLength >
                capacity - position) {
            return SessionCodecStatus::CaptureInvalid;
        }
        std::uint8_t* record = output + position;
        std::memset(record, 0, kWifiFrameRecordHeaderBytes);
        put64(record, frame.monotonicUs);
        put16(record + 8, frame.capturedLength);
        put16(record + 10, frame.originalLength);
        put16(record + 12, static_cast<std::uint16_t>(frame.rssiDbm));
        record[14] = frame.channel;
        record[15] = static_cast<std::uint8_t>(frame.kind);
        record[16] = frame.fcsIncluded ? 1U : 0U;
        std::memcpy(record + kWifiFrameRecordHeaderBytes, frame.payload,
                    frame.capturedLength);
        position += kWifiFrameRecordHeaderBytes + frame.capturedLength;
        payloadBytes += frame.capturedLength;
        previousUs = frame.monotonicUs;
    }
    put32(output + 8, payloadBytes);
    const auto& metadata = session.captureMetadata();
    if (metadata.framePayloadBytes != payloadBytes ||
        metadata.framePayloadRecords != frames.frameCount() ||
        metadata.framePayloadSnapLength != frames.snapLength() ||
        metadata.framePayloadFormat !=
            services::survey::FramePayloadFormat::Ieee80211) {
        return SessionCodecStatus::CaptureInvalid;
    }
    *outputSize = position;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeWifiFrameBlock(
    const services::survey::SurveySession& session,
    const std::uint8_t* input, std::size_t size,
    std::uint16_t* recordOffsets, std::size_t offsetCapacity,
    std::size_t* decodedCount, std::uint16_t* decodedSnapLength) {
    if (input == nullptr || size < kWifiFrameHeaderBytes ||
        std::memcmp(input, kWifiFrameMagic, sizeof(kWifiFrameMagic)) != 0 ||
        input[4] != kWifiFrameWireVersion || input[12] != 0 ||
        input[13] != 0 || input[14] != 0 || input[15] != 0) {
        return SessionCodecStatus::CaptureInvalid;
    }
    const std::size_t count = input[5];
    const std::uint16_t snapLength = get16(input + 6);
    const std::uint32_t expectedPayloadBytes = get32(input + 8);
    if (count == 0 || count > PersistedWifiFrameCaptureView::kFrameCapacity ||
        snapLength < 32 || snapLength > 256 ||
        (recordOffsets != nullptr && offsetCapacity < count)) {
        return SessionCodecStatus::BoundsExceeded;
    }
    std::size_t position = kWifiFrameHeaderBytes;
    std::uint32_t payloadBytes = 0;
    std::uint64_t previousUs = 0;
    for (std::size_t index = 0; index < count; ++index) {
        if (size - position < kWifiFrameRecordHeaderBytes ||
            position > std::numeric_limits<std::uint16_t>::max()) {
            return SessionCodecStatus::BoundsExceeded;
        }
        const std::uint8_t* record = input + position;
        const std::uint64_t monotonicUs = get64(record);
        const std::uint16_t capturedLength = get16(record + 8);
        const std::uint16_t originalLength = get16(record + 10);
        if (capturedLength == 0 || capturedLength > snapLength ||
            capturedLength > originalLength ||
            kWifiFrameRecordHeaderBytes + capturedLength > size - position ||
            record[14] == 0 || record[14] > 14 || record[15] > 2 ||
            (record[16] & static_cast<std::uint8_t>(~1U)) != 0 ||
            record[17] != 0 || record[18] != 0 || record[19] != 0 ||
            monotonicUs < session.startedUs() ||
            monotonicUs > session.stoppedUs() ||
            (previousUs != 0 && monotonicUs < previousUs)) {
            return SessionCodecStatus::CaptureInvalid;
        }
        if (recordOffsets != nullptr) {
            recordOffsets[index] = static_cast<std::uint16_t>(position);
        }
        position += kWifiFrameRecordHeaderBytes + capturedLength;
        payloadBytes += capturedLength;
        previousUs = monotonicUs;
    }
    const auto& metadata = session.captureMetadata();
    if (position != size || payloadBytes != expectedPayloadBytes ||
        !metadata.framePayloadCaptured ||
        metadata.framePayloadBytes != payloadBytes ||
        metadata.framePayloadRecords != count ||
        metadata.framePayloadSnapLength != snapLength ||
        metadata.framePayloadFormat !=
            services::survey::FramePayloadFormat::Ieee80211) {
        return SessionCodecStatus::CaptureInvalid;
    }
    if (decodedCount != nullptr) *decodedCount = count;
    if (decodedSnapLength != nullptr) *decodedSnapLength = snapLength;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus validateSegmentFooter(const std::uint8_t* segment, std::size_t size,
                                         std::uint32_t* recordCount,
                                         std::uint32_t* bodyLength,
                                         std::uint16_t* schemaVersion = nullptr,
                                         std::uint16_t* additionalRecords = nullptr) {
    if (segment == nullptr || size < kSegmentFooterBytes || size > kSessionSegmentMaxBytes) {
        return SessionCodecStatus::BoundsExceeded;
    }
    const std::uint8_t* footer = segment + size - kSegmentFooterBytes;
    if (std::memcmp(footer, kSegmentMagic, sizeof(kSegmentMagic)) != 0) {
        return SessionCodecStatus::Malformed;
    }
    const std::uint16_t version = get16(footer + 4);
    const std::uint16_t decodedAdditionalRecords = get16(footer + 6);
    if (version != kLegacySegmentSchemaVersion &&
        version != kTimelineSegmentSchemaVersion &&
        version != kSegmentSchemaVersion &&
        version != kWifiFrameSegmentSchemaVersion) {
        return SessionCodecStatus::UnsupportedSchema;
    }
    if ((version == kLegacySegmentSchemaVersion &&
         decodedAdditionalRecords != 0) ||
        (version == kTimelineSegmentSchemaVersion &&
         decodedAdditionalRecords != 1) ||
        (version == kSegmentSchemaVersion && decodedAdditionalRecords != 2) ||
        (version == kWifiFrameSegmentSchemaVersion &&
         decodedAdditionalRecords != 2)) {
        return SessionCodecStatus::Malformed;
    }
    const std::uint32_t decodedCount = get32(footer + 8);
    const std::uint32_t decodedBodyLength = get32(footer + 12);
    if (decodedCount > services::survey::SurveySession::kObservationCapacity ||
        decodedBodyLength != size - kSegmentFooterBytes) {
        return SessionCodecStatus::BoundsExceeded;
    }
    if (get32(footer + 16) != crc32c(segment, decodedBodyLength) ||
        get32(footer + 20) != crc32c(footer, 20)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    if (recordCount != nullptr) *recordCount = decodedCount;
    if (bodyLength != nullptr) *bodyLength = decodedBodyLength;
    if (schemaVersion != nullptr) *schemaVersion = version;
    if (additionalRecords != nullptr) {
        *additionalRecords = decodedAdditionalRecords;
    }
    return SessionCodecStatus::Valid;
}

}  // namespace

void PersistedWifiFrameCaptureView::reset() {
    block_ = nullptr;
    blockSize_ = 0;
    recordOffsets_.fill(0);
    count_ = 0;
    snapLength_ = 0;
}

bool PersistedWifiFrameCaptureView::frameView(
    std::size_t index, domain::captures::WifiFrameView* output) const {
    if (output == nullptr || block_ == nullptr || index >= count_) return false;
    const std::size_t offset = recordOffsets_[index];
    if (offset > blockSize_ ||
        blockSize_ - offset < kWifiFrameRecordHeaderBytes) return false;
    const std::uint8_t* record = block_ + offset;
    const std::uint16_t capturedLength = get16(record + 8);
    if (capturedLength > blockSize_ - offset - kWifiFrameRecordHeaderBytes) {
        return false;
    }
    output->monotonicUs = get64(record);
    output->capturedLength = capturedLength;
    output->originalLength = get16(record + 10);
    output->rssiDbm = static_cast<std::int16_t>(get16(record + 12));
    output->channel = record[14];
    output->kind = static_cast<domain::captures::WifiFrameKind>(record[15]);
    output->fcsIncluded = (record[16] & 1U) != 0;
    output->payload = record + kWifiFrameRecordHeaderBytes;
    return true;
}

SessionCodecStatus openPersistedWifiFrameCapture(
    const services::survey::SurveySession& session,
    const std::uint8_t* segment, std::size_t segmentSize,
    PersistedWifiFrameCaptureView* output) {
    if (output == nullptr || segment == nullptr ||
        session.state() != services::survey::SessionState::Stopped) {
        return SessionCodecStatus::InvalidArgument;
    }
    output->reset();
    std::uint32_t recordCount = 0;
    std::uint32_t bodyLength = 0;
    std::uint16_t schemaVersion = 0;
    std::uint16_t additionalRecords = 0;
    SessionCodecStatus status = validateSegmentFooter(
        segment, segmentSize, &recordCount, &bodyLength, &schemaVersion,
        &additionalRecords);
    if (status != SessionCodecStatus::Valid) return status;
    if (schemaVersion != kWifiFrameSegmentSchemaVersion || recordCount != 0 ||
        additionalRecords != 2 || bodyLength < 16) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::size_t position = 0;
    const std::uint32_t captureLength = get32(segment + position);
    const std::uint32_t captureCrc = get32(segment + position + 4);
    position += 8;
    if (captureLength != kCaptureRecordBytes ||
        captureLength > bodyLength - position ||
        captureCrc != crc32c(segment + position, captureLength)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    position += captureLength;
    if (bodyLength - position < 8) return SessionCodecStatus::BoundsExceeded;
    const std::uint32_t blockLength = get32(segment + position);
    const std::uint32_t blockCrc = get32(segment + position + 4);
    position += 8;
    if (blockLength < kWifiFrameHeaderBytes ||
        blockLength != bodyLength - position ||
        blockCrc != crc32c(segment + position, blockLength)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    output->block_ = segment + position;
    output->blockSize_ = blockLength;
    status = decodeWifiFrameBlock(
        session, output->block_, output->blockSize_,
        output->recordOffsets_.data(), output->recordOffsets_.size(),
        &output->count_, &output->snapLength_);
    if (status != SessionCodecStatus::Valid) output->reset();
    return status;
}

const char* sessionCodecStatusName(SessionCodecStatus status) {
    switch (status) {
        case SessionCodecStatus::Valid: return "valid";
        case SessionCodecStatus::InvalidArgument: return "invalid_argument";
        case SessionCodecStatus::BufferTooSmall: return "buffer_too_small";
        case SessionCodecStatus::Malformed: return "malformed";
        case SessionCodecStatus::UnsupportedSchema: return "unsupported_schema";
        case SessionCodecStatus::BoundsExceeded: return "bounds_exceeded";
        case SessionCodecStatus::ChecksumMismatch: return "checksum_mismatch";
        case SessionCodecStatus::TimelineInvalid: return "timeline_invalid";
        case SessionCodecStatus::CaptureInvalid: return "capture_invalid";
        case SessionCodecStatus::TrailingData: return "trailing_data";
    }
    return "malformed";
}

SessionCodecStatus encodeObservationSegment(const services::survey::SurveySession& session,
                                            std::uint8_t* output, std::size_t capacity,
                                            std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        session.state() != services::survey::SessionState::Stopped ||
        capacity > kSessionSegmentMaxBytes) {
        return SessionCodecStatus::InvalidArgument;
    }
    const bool hasTimeline = session.timeline().present;
    const bool hasCapture = session.captureMetadata().present;
    if (hasCapture && session.captureMetadata().framePayloadCaptured) {
        return SessionCodecStatus::CaptureInvalid;
    }
    if (hasCapture && (!hasTimeline ||
        session.captureMetadata().selectedSourceMask !=
            session.timeline().selectedMask)) {
        return SessionCodecStatus::CaptureInvalid;
    }
    CborWriter writer(output, capacity);
    if (hasCapture) {
        std::uint8_t record[kCaptureRecordBytes] = {};
        std::size_t recordSize = 0;
        const SessionCodecStatus status = encodeCaptureRecord(
            session.captureMetadata(), record, sizeof(record), &recordSize);
        if (status != SessionCodecStatus::Valid) return status;
        writer.be32(static_cast<std::uint32_t>(recordSize));
        writer.be32(crc32c(record, recordSize));
        writer.raw(record, recordSize);
    }
    for (std::size_t index = 0; index < session.size(); ++index) {
        const domain::observations::Observation* observation = session.get(index);
        if (observation == nullptr) return SessionCodecStatus::InvalidArgument;
        std::uint8_t record[kObservationRecordMaxBytes] = {};
        std::size_t recordSize = 0;
        const SessionCodecStatus status =
            encodeObservation(*observation, record, sizeof(record), &recordSize);
        if (status != SessionCodecStatus::Valid) return status;
        writer.be32(static_cast<std::uint32_t>(recordSize));
        writer.be32(crc32c(record, recordSize));
        writer.raw(record, recordSize);
    }
    if (hasTimeline) {
        std::array<std::uint8_t, kTimelineRecordMaxBytes> record{};
        std::size_t recordSize = 0;
        const SessionCodecStatus status = encodeTimelineRecord(
            session, record.data(), record.size(), &recordSize);
        if (status != SessionCodecStatus::Valid) return status;
        writer.be32(static_cast<std::uint32_t>(recordSize));
        writer.be32(crc32c(record.data(), recordSize));
        writer.raw(record.data(), recordSize);
    }
    if (!writer.ok() || kSegmentFooterBytes > capacity - writer.size()) {
        return SessionCodecStatus::BufferTooSmall;
    }
    const std::size_t bodySize = writer.size();
    std::uint8_t footer[kSegmentFooterBytes] = {};
    std::memcpy(footer, kSegmentMagic, sizeof(kSegmentMagic));
    put16(footer + 4, hasCapture ? kSegmentSchemaVersion
                                : hasTimeline ? kTimelineSegmentSchemaVersion
                                              : kLegacySegmentSchemaVersion);
    put16(footer + 6, hasCapture ? 2 : hasTimeline ? 1 : 0);
    put32(footer + 8, static_cast<std::uint32_t>(session.size()));
    put32(footer + 12, static_cast<std::uint32_t>(bodySize));
    put32(footer + 16, crc32c(output, bodySize));
    put32(footer + 20, crc32c(footer, 20));
    if (!writer.raw(footer, sizeof(footer))) return SessionCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return SessionCodecStatus::Valid;
}

SessionCodecStatus encodeWifiFrameCaptureSegment(
    const services::survey::SurveySession& session,
    const domain::captures::WifiFrameSource& frames,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        session.state() != services::survey::SessionState::Stopped ||
        capacity > kSessionSegmentMaxBytes || session.size() != 0 ||
        session.timeline().present ||
        !session.captureMetadata().present ||
        !session.captureMetadata().framePayloadCaptured) {
        return SessionCodecStatus::CaptureInvalid;
    }
    CborWriter writer(output, capacity);
    std::uint8_t captureRecord[kCaptureRecordBytes] = {};
    std::size_t captureRecordSize = 0;
    SessionCodecStatus status = encodeCaptureRecord(
        session.captureMetadata(), captureRecord, sizeof(captureRecord),
        &captureRecordSize);
    if (status != SessionCodecStatus::Valid) return status;
    writer.be32(static_cast<std::uint32_t>(captureRecordSize));
    writer.be32(crc32c(captureRecord, captureRecordSize));
    writer.raw(captureRecord, captureRecordSize);
    if (!writer.ok() || writer.size() + 8 > capacity) {
        return SessionCodecStatus::BufferTooSmall;
    }
    std::size_t frameBlockSize = 0;
    std::uint8_t* frameBlock = output + writer.size() + 8;
    status = encodeWifiFrameBlock(
        session, frames, frameBlock, capacity - writer.size() - 8,
        &frameBlockSize);
    if (status != SessionCodecStatus::Valid) return status;
    writer.be32(static_cast<std::uint32_t>(frameBlockSize));
    writer.be32(crc32c(frameBlock, frameBlockSize));
    writer.raw(frameBlock, frameBlockSize);
    if (!writer.ok() || kSegmentFooterBytes > capacity - writer.size()) {
        return SessionCodecStatus::BufferTooSmall;
    }
    const std::size_t bodySize = writer.size();
    std::uint8_t footer[kSegmentFooterBytes] = {};
    std::memcpy(footer, kSegmentMagic, sizeof(kSegmentMagic));
    put16(footer + 4, kWifiFrameSegmentSchemaVersion);
    put16(footer + 6, 2);
    put32(footer + 8, 0);
    put32(footer + 12, static_cast<std::uint32_t>(bodySize));
    put32(footer + 16, crc32c(output, bodySize));
    put32(footer + 20, crc32c(footer, 20));
    if (!writer.raw(footer, sizeof(footer))) {
        return SessionCodecStatus::BufferTooSmall;
    }
    *outputSize = writer.size();
    return SessionCodecStatus::Valid;
}

SessionCodecStatus encodeSessionManifest(const services::survey::SurveySession& session,
                                         const std::uint8_t* segment, std::size_t segmentSize,
                                         std::uint8_t* output, std::size_t capacity,
                                         std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        session.state() != services::survey::SessionState::Stopped ||
        segmentSize > std::numeric_limits<std::uint32_t>::max()) {
        return SessionCodecStatus::InvalidArgument;
    }
    std::uint32_t recordCount = 0;
    std::uint16_t segmentVersion = 0;
    const SessionCodecStatus footerStatus =
        validateSegmentFooter(segment, segmentSize, &recordCount, nullptr,
                              &segmentVersion);
    if (footerStatus != SessionCodecStatus::Valid) return footerStatus;
    if (recordCount != session.size()) return SessionCodecStatus::Malformed;

    CborWriter writer(output, capacity);
    writer.map(8);
    writer.unsignedValue(0);
    writer.unsignedValue(segmentVersion == kWifiFrameSegmentSchemaVersion
                             ? kWifiFrameSessionSchemaVersion
                             : segmentVersion == kSegmentSchemaVersion
                             ? kSessionSchemaVersion
                             : segmentVersion == kTimelineSegmentSchemaVersion
                                   ? kTimelineSessionSchemaVersion
                                   : kLegacySessionSchemaVersion);
    writer.unsignedValue(1);
    writer.unsignedValue(1);  // kind: Session
    writer.unsignedValue(2);
    writer.text(session.id(), std::strlen(session.id()));
    writer.unsignedValue(3);
    writer.unsignedValue(session.startedUs());
    writer.unsignedValue(4);
    writer.unsignedValue(session.stoppedUs());
    writer.unsignedValue(5);
    writer.unsignedValue(session.size());
    writer.unsignedValue(6);
    writer.unsignedValue(segmentSize);
    writer.unsignedValue(7);
    writer.unsignedValue(crc32c(segment, segmentSize));
    if (!writer.ok()) return SessionCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeSessionManifest(const std::uint8_t* input, std::size_t size,
                                         SessionManifest* output) {
    if (input == nullptr || output == nullptr || size == 0 ||
        size > kSessionManifestMaxBytes) {
        return SessionCodecStatus::InvalidArgument;
    }
    CborReader reader(input, size);
    std::uint64_t fieldCount = 0;
    std::uint64_t value = 0;
    if (!reader.map(&fieldCount) || fieldCount != 8 || !key(reader, 0) ||
        !reader.unsignedValue(&value)) {
        return SessionCodecStatus::Malformed;
    }
    if (value != kLegacySessionSchemaVersion &&
        value != kTimelineSessionSchemaVersion &&
        value != kSessionSchemaVersion &&
        value != kWifiFrameSessionSchemaVersion) {
        return SessionCodecStatus::UnsupportedSchema;
    }
    const std::uint16_t decodedSchemaVersion =
        static_cast<std::uint16_t>(value);
    if (!key(reader, 1) || !reader.unsignedValue(&value) || value != 1 || !key(reader, 2)) {
        return SessionCodecStatus::Malformed;
    }
    const std::uint8_t* id = nullptr;
    std::size_t idLength = 0;
    if (!reader.text(&id, &idLength) || !validSessionId(id, idLength)) {
        return SessionCodecStatus::BoundsExceeded;
    }
    SessionManifest manifest;
    manifest.schemaVersion = decodedSchemaVersion;
    std::memcpy(manifest.sessionId.data(), id, idLength);
    manifest.sessionId[idLength] = '\0';
    if (!key(reader, 3) || !reader.unsignedValue(&manifest.startedUs) || !key(reader, 4) ||
        !reader.unsignedValue(&manifest.stoppedUs) || !key(reader, 5) ||
        !reader.unsignedValue(&value) ||
        value > services::survey::SurveySession::kObservationCapacity) {
        return SessionCodecStatus::BoundsExceeded;
    }
    manifest.observationCount = static_cast<std::uint32_t>(value);
    if (!key(reader, 6) || !reader.unsignedValue(&value) ||
        value > kSessionSegmentMaxBytes || value > std::numeric_limits<std::uint32_t>::max()) {
        return SessionCodecStatus::BoundsExceeded;
    }
    manifest.segmentLength = static_cast<std::uint32_t>(value);
    if (!key(reader, 7) || !reader.unsignedValue(&value) ||
        value > std::numeric_limits<std::uint32_t>::max()) {
        return SessionCodecStatus::BoundsExceeded;
    }
    manifest.segmentCrc32c = static_cast<std::uint32_t>(value);
    if (!reader.complete()) return SessionCodecStatus::TrailingData;
    if (manifest.startedUs == 0 || manifest.stoppedUs < manifest.startedUs ||
        manifest.segmentLength < kSegmentFooterBytes) {
        return SessionCodecStatus::TimelineInvalid;
    }
    *output = manifest;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus reopenSession(const std::uint8_t* manifestBytes, std::size_t manifestSize,
                                 const std::uint8_t* segment, std::size_t segmentSize,
                                 services::survey::SurveySession* output) {
    if (output == nullptr || segment == nullptr) return SessionCodecStatus::InvalidArgument;
    SessionManifest manifest;
    SessionCodecStatus status =
        decodeSessionManifest(manifestBytes, manifestSize, &manifest);
    if (status != SessionCodecStatus::Valid) return status;
    if (manifest.segmentLength != segmentSize ||
        manifest.segmentCrc32c != crc32c(segment, segmentSize)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    std::uint32_t recordCount = 0;
    std::uint32_t bodyLength = 0;
    std::uint16_t segmentVersion = 0;
    std::uint16_t additionalRecords = 0;
    status = validateSegmentFooter(segment, segmentSize, &recordCount,
                                   &bodyLength, &segmentVersion,
                                   &additionalRecords);
    if (status != SessionCodecStatus::Valid) return status;
    const std::uint16_t expectedSegmentVersion =
        manifest.schemaVersion == kWifiFrameSessionSchemaVersion
            ? kWifiFrameSegmentSchemaVersion
            : manifest.schemaVersion == kSessionSchemaVersion
            ? kSegmentSchemaVersion : kLegacySegmentSchemaVersion;
    const std::uint16_t compatibleSegmentVersion =
        manifest.schemaVersion == kTimelineSessionSchemaVersion
            ? kTimelineSegmentSchemaVersion : expectedSegmentVersion;
    const std::uint16_t expectedAdditionalRecords =
        manifest.schemaVersion == kWifiFrameSessionSchemaVersion
            ? 2 : manifest.schemaVersion == kSessionSchemaVersion
            ? 2 : manifest.schemaVersion == kTimelineSessionSchemaVersion ? 1 : 0;
    if (recordCount != manifest.observationCount ||
        segmentVersion != compatibleSegmentVersion ||
        additionalRecords != expectedAdditionalRecords) {
        return SessionCodecStatus::Malformed;
    }

    // The maximum Session is several KiB. It must live in caller-owned bounded
    // storage, never as a hidden task-stack copy on the ESP32 loop task.
    output->reset();
    if (output->start(manifest.sessionId.data(), manifest.startedUs) !=
        services::survey::SessionStatus::Started) {
        return SessionCodecStatus::Malformed;
    }
    std::size_t position = 0;
    if (manifest.schemaVersion == kSessionSchemaVersion ||
        manifest.schemaVersion == kWifiFrameSessionSchemaVersion) {
        if (bodyLength - position < 8) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        const std::uint32_t recordLength = get32(segment + position);
        const std::uint32_t recordCrc = get32(segment + position + 4);
        position += 8;
        if (recordLength != kCaptureRecordBytes ||
            recordLength > bodyLength - position) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        if (recordCrc != crc32c(segment + position, recordLength)) {
            output->reset();
            return SessionCodecStatus::ChecksumMismatch;
        }
        status = decodeCaptureRecord(segment + position, recordLength, output);
        if (status != SessionCodecStatus::Valid) {
            output->reset();
            return status;
        }
        position += recordLength;
    }
    for (std::uint32_t index = 0; index < recordCount; ++index) {
        if (bodyLength - position < 8) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        const std::uint32_t recordLength = get32(segment + position);
        const std::uint32_t recordCrc = get32(segment + position + 4);
        position += 8;
        if (recordLength == 0 || recordLength > kObservationRecordMaxBytes ||
            recordLength > bodyLength - position) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        if (recordCrc != crc32c(segment + position, recordLength)) {
            output->reset();
            return SessionCodecStatus::ChecksumMismatch;
        }
        domain::observations::Observation observation;
        status = decodeObservation(segment + position, recordLength, &observation);
        if (status != SessionCodecStatus::Valid) {
            output->reset();
            return status;
        }
        if (observation.sequence != static_cast<std::uint64_t>(index + 1) ||
            output->append(observation) != services::survey::SessionStatus::Appended) {
            output->reset();
            return SessionCodecStatus::TimelineInvalid;
        }
        position += recordLength;
    }
    if (manifest.schemaVersion == kWifiFrameSessionSchemaVersion) {
        if (bodyLength - position < 8) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        const std::uint32_t recordLength = get32(segment + position);
        const std::uint32_t recordCrc = get32(segment + position + 4);
        position += 8;
        if (recordLength < kWifiFrameHeaderBytes ||
            recordLength > bodyLength - position) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        if (recordCrc != crc32c(segment + position, recordLength)) {
            output->reset();
            return SessionCodecStatus::ChecksumMismatch;
        }
        // Stop first so frame timestamps can be checked against both bounds.
        if (output->stop(manifest.stoppedUs) !=
            services::survey::SessionStatus::Stopped) {
            output->reset();
            return SessionCodecStatus::TimelineInvalid;
        }
        status = decodeWifiFrameBlock(*output, segment + position, recordLength,
                                      nullptr, 0, nullptr, nullptr);
        if (status != SessionCodecStatus::Valid) {
            output->reset();
            return status;
        }
        position += recordLength;
    } else if (additionalRecords >= 1) {
        if (bodyLength - position < 8) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        const std::uint32_t recordLength = get32(segment + position);
        const std::uint32_t recordCrc = get32(segment + position + 4);
        position += 8;
        if (recordLength == 0 || recordLength > kTimelineRecordMaxBytes ||
            recordLength > bodyLength - position) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        if (recordCrc != crc32c(segment + position, recordLength)) {
            output->reset();
            return SessionCodecStatus::ChecksumMismatch;
        }
        status = decodeTimelineRecord(segment + position, recordLength, output);
        if (status != SessionCodecStatus::Valid) {
            output->reset();
            return status;
        }
        position += recordLength;
    }
    if (manifest.schemaVersion == kSessionSchemaVersion &&
        (!output->captureMetadata().present || !output->timeline().present ||
         output->captureMetadata().selectedSourceMask !=
             output->timeline().selectedMask)) {
        output->reset();
        return SessionCodecStatus::CaptureInvalid;
    }
    if (position != bodyLength) {
        output->reset();
        return SessionCodecStatus::TrailingData;
    }
    if (manifest.schemaVersion != kWifiFrameSessionSchemaVersion &&
        output->stop(manifest.stoppedUs) != services::survey::SessionStatus::Stopped) {
        output->reset();
        return SessionCodecStatus::TimelineInvalid;
    }
    return SessionCodecStatus::Valid;
}

bool formatSessionJsonSummary(const services::survey::SurveySession& session, char* output,
                              std::size_t capacity) {
    if (output == nullptr || capacity == 0 ||
        session.state() != services::survey::SessionState::Stopped) {
        return false;
    }
    std::size_t wifiCount = 0;
    std::size_t bleCount = 0;
    for (std::size_t index = 0; index < session.size(); ++index) {
        const domain::observations::Observation* observation = session.get(index);
        if (observation != nullptr &&
            observation->radio == domain::observations::RadioKind::Wifi) {
            ++wifiCount;
        } else if (observation != nullptr &&
                   observation->radio ==
                       domain::observations::RadioKind::Ble) {
            ++bleCount;
        }
    }
    const services::survey::SessionTimelineSummary& timeline = session.timeline();
    int written = -1;
    if (session.captureMetadata().framePayloadCaptured) {
        const auto& capture = session.captureMetadata();
        written = std::snprintf(
            output, capacity,
            "{\"schema\":\"leshy.capture.summary.v1\",\"id\":\"%s\","
            "\"started_us\":%llu,\"stopped_us\":%llu,"
            "\"frames\":%u,\"payload_bytes\":%llu,\"snap_length\":%u,"
            "\"format\":\"ieee80211\",\"passive\":true}",
            session.id(),
            static_cast<unsigned long long>(session.startedUs()),
            static_cast<unsigned long long>(session.stoppedUs()),
            static_cast<unsigned>(capture.framePayloadRecords),
            static_cast<unsigned long long>(capture.framePayloadBytes),
            static_cast<unsigned>(capture.framePayloadSnapLength));
    } else if (!timeline.present) {
        written = std::snprintf(
            output, capacity,
            "{\"schema\":\"leshy.session.summary.v1\",\"id\":\"%s\","
            "\"started_us\":%llu,\"stopped_us\":%llu,\"observations\":%u,"
            "\"dropped\":%lu,\"sources\":{\"wifi\":%u}}",
            session.id(), static_cast<unsigned long long>(session.startedUs()),
            static_cast<unsigned long long>(session.stoppedUs()),
            static_cast<unsigned>(session.size()),
            static_cast<unsigned long>(session.dropped()),
            static_cast<unsigned>(wifiCount));
    } else if (timeline.finalized) {
        const std::uint64_t elapsed = timeline.stoppedUs - timeline.startedUs;
        const auto duty = [elapsed](
            const services::survey::SourceRuntimeSummary& source) {
            if (!source.selected || elapsed == 0) return 0U;
            if (source.activeUs >= elapsed) return 1000U;
            return static_cast<unsigned>((source.activeUs * 1000U) / elapsed);
        };
        const auto& wifi = timeline.sources[0];
        const auto& ble = timeline.sources[1];
        written = std::snprintf(
            output, capacity,
            "{\"schema\":\"leshy.session.summary.v2\",\"id\":\"%s\","
            "\"started_us\":%llu,\"stopped_us\":%llu,\"observations\":%u,"
            "\"dropped\":%lu,\"sources\":{\"wifi\":%u,\"ble\":%u},"
            "\"timeline\":{"
            "\"selected_mask\":%u,\"started_us\":%llu,\"stopped_us\":%llu,"
            "\"windows\":%lu,\"retained\":%u,"
            "\"evicted\":%lu,\"overflow\":%llu,"
            "\"wifi\":{\"scheduled_us\":%llu,\"active_us\":%llu,"
            "\"unavailable_us\":%llu,\"fault_us\":%llu,"
            "\"duty_permille\":%u,\"accepted\":%llu,\"dropped\":%llu},"
            "\"ble\":{\"scheduled_us\":%llu,\"active_us\":%llu,"
            "\"unavailable_us\":%llu,\"fault_us\":%llu,"
            "\"duty_permille\":%u,\"accepted\":%llu,\"dropped\":%llu}}}",
            session.id(), static_cast<unsigned long long>(session.startedUs()),
            static_cast<unsigned long long>(session.stoppedUs()),
            static_cast<unsigned>(session.size()),
            static_cast<unsigned long>(session.dropped()),
            static_cast<unsigned>(wifiCount),
            static_cast<unsigned>(bleCount),
            static_cast<unsigned>(timeline.selectedMask),
            static_cast<unsigned long long>(timeline.startedUs),
            static_cast<unsigned long long>(timeline.stoppedUs),
            static_cast<unsigned long>(timeline.totalWindows),
            static_cast<unsigned>(session.timelineWindowCount()),
            static_cast<unsigned long>(timeline.evictedWindows),
            static_cast<unsigned long long>(timeline.overflowEvents),
            static_cast<unsigned long long>(wifi.scheduledUs),
            static_cast<unsigned long long>(wifi.activeUs),
            static_cast<unsigned long long>(wifi.unavailableUs),
            static_cast<unsigned long long>(wifi.faultUs), duty(wifi),
            static_cast<unsigned long long>(wifi.accepted),
            static_cast<unsigned long long>(wifi.dropped),
            static_cast<unsigned long long>(ble.scheduledUs),
            static_cast<unsigned long long>(ble.activeUs),
            static_cast<unsigned long long>(ble.unavailableUs),
            static_cast<unsigned long long>(ble.faultUs), duty(ble),
            static_cast<unsigned long long>(ble.accepted),
            static_cast<unsigned long long>(ble.dropped));
    }
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace leshy1::storage
