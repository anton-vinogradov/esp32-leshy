#include "SessionCodec.h"

#include <cstdio>
#include <cstring>
#include <limits>

#include "AtomicHead.h"

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kSegmentMagic[4] = {'L', 'S', 'H', 'S'};

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
    if (output == nullptr || outputSize == nullptr || observation.identityLength == 0 ||
        observation.identityLength > observation.identity.size() ||
        observation.labelLength > domain::observations::Observation::kLabelCapacity ||
        observation.channel == 0 || observation.channel > 14 || observation.rssiDbm < -127 ||
        observation.rssiDbm > 0 || observation.frequencyKhz == 0) {
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
        unsignedValue != static_cast<std::uint8_t>(domain::observations::RadioKind::Wifi)) {
        return SessionCodecStatus::Malformed;
    }
    observation.radio = domain::observations::RadioKind::Wifi;
    if (!key(reader, 3) || !reader.unsignedValue(&unsignedValue) ||
        unsignedValue > std::numeric_limits<std::uint32_t>::max()) {
        return SessionCodecStatus::Malformed;
    }
    observation.frequencyKhz = static_cast<std::uint32_t>(unsignedValue);
    if (!key(reader, 4) || !reader.unsignedValue(&unsignedValue) || unsignedValue > 14) {
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
    if (observation.sequence == 0 || observation.monotonicUs == 0 ||
        observation.channel == 0 || observation.frequencyKhz == 0) {
        return SessionCodecStatus::Malformed;
    }
    *output = observation;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus validateSegmentFooter(const std::uint8_t* segment, std::size_t size,
                                         std::uint32_t* recordCount,
                                         std::uint32_t* bodyLength) {
    if (segment == nullptr || size < kSegmentFooterBytes || size > kSessionSegmentMaxBytes) {
        return SessionCodecStatus::BoundsExceeded;
    }
    const std::uint8_t* footer = segment + size - kSegmentFooterBytes;
    if (std::memcmp(footer, kSegmentMagic, sizeof(kSegmentMagic)) != 0 ||
        get16(footer + 6) != 0) {
        return SessionCodecStatus::Malformed;
    }
    if (get16(footer + 4) != kSegmentSchemaVersion) {
        return SessionCodecStatus::UnsupportedSchema;
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
    return SessionCodecStatus::Valid;
}

}  // namespace

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
    CborWriter writer(output, capacity);
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
    if (!writer.ok() || kSegmentFooterBytes > capacity - writer.size()) {
        return SessionCodecStatus::BufferTooSmall;
    }
    const std::size_t bodySize = writer.size();
    std::uint8_t footer[kSegmentFooterBytes] = {};
    std::memcpy(footer, kSegmentMagic, sizeof(kSegmentMagic));
    put16(footer + 4, kSegmentSchemaVersion);
    put16(footer + 6, 0);
    put32(footer + 8, static_cast<std::uint32_t>(session.size()));
    put32(footer + 12, static_cast<std::uint32_t>(bodySize));
    put32(footer + 16, crc32c(output, bodySize));
    put32(footer + 20, crc32c(footer, 20));
    if (!writer.raw(footer, sizeof(footer))) return SessionCodecStatus::BufferTooSmall;
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
    const SessionCodecStatus footerStatus =
        validateSegmentFooter(segment, segmentSize, &recordCount, nullptr);
    if (footerStatus != SessionCodecStatus::Valid) return footerStatus;
    if (recordCount != session.size()) return SessionCodecStatus::Malformed;

    CborWriter writer(output, capacity);
    writer.map(8);
    writer.unsignedValue(0);
    writer.unsignedValue(kSessionSchemaVersion);
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
    if (value != kSessionSchemaVersion) return SessionCodecStatus::UnsupportedSchema;
    if (!key(reader, 1) || !reader.unsignedValue(&value) || value != 1 || !key(reader, 2)) {
        return SessionCodecStatus::Malformed;
    }
    const std::uint8_t* id = nullptr;
    std::size_t idLength = 0;
    if (!reader.text(&id, &idLength) || !validSessionId(id, idLength)) {
        return SessionCodecStatus::BoundsExceeded;
    }
    SessionManifest manifest;
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
    status = validateSegmentFooter(segment, segmentSize, &recordCount, &bodyLength);
    if (status != SessionCodecStatus::Valid) return status;
    if (recordCount != manifest.observationCount) return SessionCodecStatus::Malformed;

    // The maximum Session is several KiB. It must live in caller-owned bounded
    // storage, never as a hidden task-stack copy on the ESP32 loop task.
    output->reset();
    if (output->start(manifest.sessionId.data(), manifest.startedUs) !=
        services::survey::SessionStatus::Started) {
        return SessionCodecStatus::Malformed;
    }
    std::size_t position = 0;
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
    if (position != bodyLength) {
        output->reset();
        return SessionCodecStatus::TrailingData;
    }
    if (output->stop(manifest.stoppedUs) != services::survey::SessionStatus::Stopped) {
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
    for (std::size_t index = 0; index < session.size(); ++index) {
        const domain::observations::Observation* observation = session.get(index);
        if (observation != nullptr &&
            observation->radio == domain::observations::RadioKind::Wifi) {
            ++wifiCount;
        }
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.session.summary.v1\",\"id\":\"%s\","
        "\"started_us\":%llu,\"stopped_us\":%llu,\"observations\":%u,"
        "\"dropped\":%lu,\"sources\":{\"wifi\":%u}}",
        session.id(), static_cast<unsigned long long>(session.startedUs()),
        static_cast<unsigned long long>(session.stoppedUs()),
        static_cast<unsigned>(session.size()), static_cast<unsigned long>(session.dropped()),
        static_cast<unsigned>(wifiCount));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace leshy1::storage
