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
constexpr std::uint8_t kSubGhzRawCaptureWireVersion = 3;
constexpr std::size_t kSubGhzRawCaptureRecordBytes = 88;
constexpr std::uint8_t kInfraredRawCaptureWireVersion = 4;
constexpr std::size_t kInfraredRawCaptureRecordBytes = 96;
constexpr std::uint8_t kAuthenticationCaptureWireVersion = 5;
constexpr std::size_t kAuthenticationCaptureRecordBytes = 132;
constexpr std::uint8_t kWifiFrameMagic[4] = {'L', 'W', 'F', 'C'};
constexpr std::uint8_t kWifiFrameWireVersion = 1;
constexpr std::size_t kWifiFrameHeaderBytes = 16;
constexpr std::size_t kWifiFrameRecordHeaderBytes = 20;
constexpr std::uint8_t kSubGhzRawMagic[4] = {'L', 'S', 'G', 'R'};
constexpr std::uint8_t kSubGhzRawWireVersion = 1;
constexpr std::size_t kSubGhzRawHeaderBytes = 16;
constexpr std::uint8_t kInfraredRawMagic[4] = {'L', 'I', 'R', 'R'};
constexpr std::uint8_t kInfraredRawWireVersion = 1;
constexpr std::size_t kInfraredRawHeaderBytes = 16;
constexpr std::uint8_t kCaptureFlagPassive = 1U << 0U;
constexpr std::uint8_t kCaptureFlagWifiShowHidden = 1U << 1U;
constexpr std::uint8_t kCaptureFlagLocation = 1U << 2U;
constexpr std::uint8_t kCaptureFlagFramePayload = 1U << 3U;
constexpr std::uint8_t kCaptureFlagSubGhzRaw = 1U << 4U;
constexpr std::uint8_t kCaptureFlagInfraredRaw = 1U << 5U;
constexpr std::uint8_t kCaptureKnownFlags =
    kCaptureFlagPassive | kCaptureFlagWifiShowHidden |
    kCaptureFlagLocation | kCaptureFlagFramePayload |
    kCaptureFlagSubGhzRaw | kCaptureFlagInfraredRaw;
constexpr std::uint8_t kObservationFactsWireVersion = 2;
constexpr std::uint8_t kLegacyObservationFactsWireVersion = 1;
constexpr std::size_t kWifiObservationFactsBytes = 19;
constexpr std::size_t kBleObservationFactsBytes = 29;

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

SessionCodecStatus encodeObservation(
    const domain::observations::Observation& observation, bool enriched,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
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
    writer.map(enriched ? 9 : 8);
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
    if (enriched) {
        std::uint8_t facts[kBleObservationFactsBytes] = {};
        std::size_t factsSize = 0;
        facts[0] = kObservationFactsWireVersion;
        if (wifi) {
            const auto& source = observation.wifiNetwork;
            facts[1] = static_cast<std::uint8_t>(
                (source.present ? 1U : 0U) |
                (source.wps ? 1U << 1U : 0U) |
                (source.ftmResponder ? 1U << 2U : 0U) |
                (source.ftmInitiator ? 1U << 3U : 0U) |
                (source.bssColorKnown ? 1U << 4U : 0U) |
                (observation.wifiKind ==
                         domain::observations::WifiObservationKind::Station
                     ? 1U << 5U : 0U));
            facts[2] = static_cast<std::uint8_t>(source.authentication);
            facts[3] = static_cast<std::uint8_t>(source.pairwiseCipher);
            facts[4] = static_cast<std::uint8_t>(source.groupCipher);
            facts[5] = static_cast<std::uint8_t>(source.channelWidth);
            put16(facts + 6, source.phyMask);
            facts[8] = source.secondaryChannelDirection;
            facts[9] = source.receiveAntenna;
            std::memcpy(facts + 10, source.countryCode.data(),
                        source.countryCode.size());
            facts[13] = source.countryStartChannel;
            facts[14] = source.countryChannelCount;
            facts[15] = static_cast<std::uint8_t>(
                source.countryMaximumTxPowerDbm);
            facts[16] = source.bssColor;
            facts[17] = source.vhtCenterChannel1;
            facts[18] = source.vhtCenterChannel2;
            factsSize = kWifiObservationFactsBytes;
        } else {
            const auto& source = observation.bleAdvertisement;
            if (source.firstServiceUuidLength >
                    domain::observations::BleAdvertisementFacts::
                        kServiceUuidCapacity ||
                source.addressType > 3U) {
                return SessionCodecStatus::InvalidArgument;
            }
            facts[1] = static_cast<std::uint8_t>(
                (source.present ? 1U : 0U) |
                (source.legacy ? 1U << 1U : 0U) |
                (source.scannable ? 1U << 2U : 0U) |
                (source.connectable ? 1U << 3U : 0U) |
                (source.txPowerKnown ? 1U << 4U : 0U) |
                (source.appearanceKnown ? 1U << 5U : 0U) |
                (source.companyKnown ? 1U << 6U : 0U));
            facts[2] = source.addressType;
            facts[3] = source.advertisementType;
            facts[4] = static_cast<std::uint8_t>(source.txPowerDbm);
            put16(facts + 5, source.appearance);
            put16(facts + 7, source.companyId);
            facts[9] = source.appleContinuityType;
            put16(facts + 10, source.knownServiceMask);
            facts[12] = source.firstServiceUuidLength;
            std::memcpy(facts + 13, source.firstServiceUuid.data(),
                        domain::observations::BleAdvertisementFacts::
                            kServiceUuidCapacity);
            put32(facts + 21, source.firstServiceUuidHash);
            facts[25] = source.serviceUuidCount;
            facts[26] = source.serviceDataCount;
            facts[27] = source.manufacturerDataLength;
            facts[28] = source.payloadLength;
            factsSize = kBleObservationFactsBytes;
        }
        writer.unsignedValue(8);
        writer.bytes(facts, factsSize);
    }
    if (!writer.ok()) return SessionCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeObservation(
    const std::uint8_t* input, std::size_t size, bool factsRequired,
    domain::observations::Observation* output) {
    if (input == nullptr || output == nullptr) return SessionCodecStatus::InvalidArgument;
    CborReader reader(input, size);
    std::uint64_t count = 0;
    if (!reader.map(&count) || (count != 8 && count != 9) ||
        (factsRequired && count != 9)) {
        return SessionCodecStatus::Malformed;
    }
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
    if (count == 9) {
        if (!key(reader, 8) || !reader.bytes(&bytes, &length)) {
            return SessionCodecStatus::Malformed;
        }
        if (observation.radio == domain::observations::RadioKind::Wifi) {
            if (length != kWifiObservationFactsBytes) {
                return SessionCodecStatus::Malformed;
            }
            const bool legacyFacts =
                bytes[0] == kLegacyObservationFactsWireVersion;
            if ((!legacyFacts &&
                 bytes[0] != kObservationFactsWireVersion) ||
                (bytes[1] & (legacyFacts ? 0xe0U : 0xc0U)) != 0 ||
                bytes[2] > static_cast<std::uint8_t>(
                    domain::observations::WifiAuthentication::WpaEnterprise) ||
                bytes[3] > static_cast<std::uint8_t>(
                    domain::observations::WifiCipher::AesGmac256) ||
                bytes[4] > static_cast<std::uint8_t>(
                    domain::observations::WifiCipher::AesGmac256) ||
                bytes[5] > static_cast<std::uint8_t>(
                    domain::observations::WifiChannelWidth::Mhz80Plus80) ||
                bytes[8] > 2U) {
                return SessionCodecStatus::Malformed;
            }
            auto& facts = observation.wifiNetwork;
            facts.present = (bytes[1] & 1U) != 0;
            facts.wps = (bytes[1] & (1U << 1U)) != 0;
            facts.ftmResponder = (bytes[1] & (1U << 2U)) != 0;
            facts.ftmInitiator = (bytes[1] & (1U << 3U)) != 0;
            facts.bssColorKnown = (bytes[1] & (1U << 4U)) != 0;
            observation.wifiKind = !legacyFacts &&
                    (bytes[1] & (1U << 5U)) != 0
                ? domain::observations::WifiObservationKind::Station
                : domain::observations::WifiObservationKind::AccessPoint;
            facts.authentication =
                static_cast<domain::observations::WifiAuthentication>(bytes[2]);
            facts.pairwiseCipher =
                static_cast<domain::observations::WifiCipher>(bytes[3]);
            facts.groupCipher =
                static_cast<domain::observations::WifiCipher>(bytes[4]);
            facts.channelWidth =
                static_cast<domain::observations::WifiChannelWidth>(bytes[5]);
            facts.phyMask = get16(bytes + 6);
            facts.secondaryChannelDirection = bytes[8];
            facts.receiveAntenna = bytes[9];
            std::memcpy(facts.countryCode.data(), bytes + 10,
                        facts.countryCode.size());
            facts.countryStartChannel = bytes[13];
            facts.countryChannelCount = bytes[14];
            facts.countryMaximumTxPowerDbm =
                static_cast<std::int8_t>(bytes[15]);
            facts.bssColor = bytes[16];
            facts.vhtCenterChannel1 = bytes[17];
            facts.vhtCenterChannel2 = bytes[18];
        } else {
            if (length != kBleObservationFactsBytes ||
                (bytes[0] != kObservationFactsWireVersion &&
                 bytes[0] != kLegacyObservationFactsWireVersion) ||
                (bytes[1] & 0x80U) != 0 || bytes[2] > 3U ||
                bytes[12] > domain::observations::BleAdvertisementFacts::
                    kServiceUuidCapacity) {
                return SessionCodecStatus::Malformed;
            }
            auto& facts = observation.bleAdvertisement;
            facts.present = (bytes[1] & 1U) != 0;
            facts.legacy = (bytes[1] & (1U << 1U)) != 0;
            facts.scannable = (bytes[1] & (1U << 2U)) != 0;
            facts.connectable = (bytes[1] & (1U << 3U)) != 0;
            facts.txPowerKnown = (bytes[1] & (1U << 4U)) != 0;
            facts.appearanceKnown = (bytes[1] & (1U << 5U)) != 0;
            facts.companyKnown = (bytes[1] & (1U << 6U)) != 0;
            facts.addressType = bytes[2];
            facts.advertisementType = bytes[3];
            facts.txPowerDbm = static_cast<std::int8_t>(bytes[4]);
            facts.appearance = get16(bytes + 5);
            facts.companyId = get16(bytes + 7);
            facts.appleContinuityType = bytes[9];
            facts.knownServiceMask = get16(bytes + 10);
            facts.firstServiceUuidLength = bytes[12];
            std::memcpy(facts.firstServiceUuid.data(), bytes + 13,
                        domain::observations::BleAdvertisementFacts::
                            kServiceUuidCapacity);
            facts.firstServiceUuid[facts.firstServiceUuidLength] = '\0';
            facts.firstServiceUuidHash = get32(bytes + 21);
            facts.serviceUuidCount = bytes[25];
            facts.serviceDataCount = bytes[26];
            facts.manufacturerDataLength = bytes[27];
            facts.payloadLength = bytes[28];
        }
    } else if (observation.radio ==
               domain::observations::RadioKind::Ble) {
        // Legacy schemas did not persist BLE facts. Preserve readability and
        // deterministic cross-visit identity with a public-address fallback;
        // every newly written product Session uses the enriched schema.
        observation.bleAdvertisement.present = true;
        observation.bleAdvertisement.addressType = 0;
    }
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
        capacity < (metadata.infraredRawCaptured
                        ? kInfraredRawCaptureRecordBytes
                        : metadata.subGhzRawCaptured
                              ? kSubGhzRawCaptureRecordBytes
                              : kCaptureRecordBytes) ||
        !metadata.present ||
        metadata.appIdentityLength != metadata.appIdentity.size()) {
        return SessionCodecStatus::CaptureInvalid;
    }
    const std::size_t recordBytes = metadata.infraredRawCaptured
        ? kInfraredRawCaptureRecordBytes
        : metadata.subGhzRawCaptured
              ? kSubGhzRawCaptureRecordBytes : kCaptureRecordBytes;
    std::memset(output, 0, recordBytes);
    std::memcpy(output, kCaptureMagic, sizeof(kCaptureMagic));
    output[4] = metadata.infraredRawCaptured
        ? kInfraredRawCaptureWireVersion
        : metadata.subGhzRawCaptured
              ? kSubGhzRawCaptureWireVersion
        : metadata.framePayloadCaptured
              ? kWifiFrameCaptureWireVersion : kCaptureWireVersion;
    output[5] = metadata.selectedSourceMask;
    output[6] = (metadata.passive ? kCaptureFlagPassive : 0) |
        (metadata.wifiShowHidden ? kCaptureFlagWifiShowHidden : 0) |
        (metadata.locationPresent ? kCaptureFlagLocation : 0) |
        (metadata.framePayloadCaptured ? kCaptureFlagFramePayload : 0) |
        (metadata.subGhzRawCaptured ? kCaptureFlagSubGhzRaw : 0) |
        (metadata.infraredRawCaptured ? kCaptureFlagInfraredRaw : 0);
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
    if (metadata.subGhzRawCaptured) {
        put32(output + 72, metadata.subGhzFrequencyKHz);
        put16(output + 76, static_cast<std::uint16_t>(
            metadata.subGhzThresholdDbm));
        output[78] = static_cast<std::uint8_t>(metadata.subGhzModulation);
        output[79] = metadata.subGhzStartLevel ? 1U : 0U;
        put16(output + 80, metadata.subGhzPulseRecords);
        output[82] = metadata.subGhzTruncated ? 1U : 0U;
        put32(output + 84, metadata.subGhzPulseBytes);
    } else if (metadata.infraredRawCaptured) {
        output[72] = static_cast<std::uint8_t>(
            metadata.infraredDecode.protocol);
        output[73] = metadata.infraredStartLevel ? 1U : 0U;
        output[74] = metadata.infraredTruncated ? 1U : 0U;
        output[75] = metadata.infraredDecode.integrityValid ? 1U : 0U;
        put16(output + 76, metadata.infraredPulseRecords);
        put32(output + 80, metadata.infraredPulseBytes);
        put16(output + 84, metadata.infraredDecode.address);
        output[86] = metadata.infraredDecode.command;
        put32(output + 88, metadata.infraredDecode.rawCode);
    }
    *outputSize = recordBytes;
    return SessionCodecStatus::Valid;
}

bool allZero(const std::uint8_t* bytes, std::size_t size) {
    if (bytes == nullptr) return false;
    for (std::size_t index = 0; index < size; ++index) {
        if (bytes[index] != 0) return false;
    }
    return true;
}

bool validAuthenticationCaptureProvenance(
    const AuthenticationCaptureProvenance& provenance,
    std::uint8_t wifiChannel) {
    const auto purpose = static_cast<std::uint8_t>(provenance.purpose);
    if (purpose > static_cast<std::uint8_t>(
                      AuthenticationCapturePurpose::Authentication) ||
        provenance.ssidLength > provenance.ssid.size() ||
        (provenance.ssidKnown && provenance.ssidLength == 0) ||
        (!provenance.ssidKnown && provenance.ssidLength != 0) ||
        !allZero(provenance.ssid.data() + provenance.ssidLength,
                 provenance.ssid.size() - provenance.ssidLength)) {
        return false;
    }
    const std::uint64_t accounted =
        static_cast<std::uint64_t>(provenance.framesAccepted) +
        provenance.framesDroppedCapacity + provenance.framesDroppedInvalid;
    if (accounted != provenance.framesReported) return false;
    const bool targetPresent = !allZero(provenance.targetBssid.data(),
                                        provenance.targetBssid.size());
    if (targetPresent && (provenance.targetBssid[0] & 1U) != 0) return false;
    if (provenance.purpose ==
        AuthenticationCapturePurpose::Authentication) {
        if (wifiChannel == 0 || wifiChannel > 14 ||
            !targetPresent) {
            return false;
        }
    }
    return true;
}

SessionCodecStatus encodeAuthenticationCaptureRecord(
    const services::survey::CaptureMetadata& metadata,
    const AuthenticationCaptureProvenance& provenance,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        capacity < kAuthenticationCaptureRecordBytes ||
        !metadata.framePayloadCaptured || metadata.subGhzRawCaptured ||
        metadata.infraredRawCaptured ||
        !validAuthenticationCaptureProvenance(provenance,
                                              metadata.wifiChannel)) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::size_t baseSize = 0;
    SessionCodecStatus status = encodeCaptureRecord(
        metadata, output, capacity, &baseSize);
    if (status != SessionCodecStatus::Valid || baseSize != kCaptureRecordBytes) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::memset(output + kCaptureRecordBytes, 0,
                kAuthenticationCaptureRecordBytes - kCaptureRecordBytes);
    output[4] = kAuthenticationCaptureWireVersion;
    output[72] = static_cast<std::uint8_t>(provenance.purpose);
    output[73] = provenance.ssidKnown ? 1U : 0U;
    output[74] = provenance.ssidLength;
    std::memcpy(output + 76, provenance.targetBssid.data(),
                provenance.targetBssid.size());
    std::memcpy(output + 82, provenance.ssid.data(), provenance.ssid.size());
    put32(output + 114, provenance.framesReported);
    put32(output + 118, provenance.framesAccepted);
    put32(output + 122, provenance.framesDroppedCapacity);
    put32(output + 126, provenance.framesDroppedInvalid);
    *outputSize = kAuthenticationCaptureRecordBytes;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeAuthenticationCaptureProvenanceRecord(
    const std::uint8_t* input, std::size_t size, std::uint8_t wifiChannel,
    AuthenticationCaptureProvenance* output) {
    if (input == nullptr || size != kAuthenticationCaptureRecordBytes ||
        std::memcmp(input, kCaptureMagic, sizeof(kCaptureMagic)) != 0 ||
        input[4] != kAuthenticationCaptureWireVersion || input[73] > 1U ||
        input[75] != 0 || input[130] != 0 || input[131] != 0) {
        return SessionCodecStatus::CaptureInvalid;
    }
    AuthenticationCaptureProvenance provenance;
    provenance.purpose = static_cast<AuthenticationCapturePurpose>(input[72]);
    provenance.ssidKnown = input[73] != 0;
    provenance.ssidLength = input[74];
    std::memcpy(provenance.targetBssid.data(), input + 76,
                provenance.targetBssid.size());
    std::memcpy(provenance.ssid.data(), input + 82,
                provenance.ssid.size());
    provenance.framesReported = get32(input + 114);
    provenance.framesAccepted = get32(input + 118);
    provenance.framesDroppedCapacity = get32(input + 122);
    provenance.framesDroppedInvalid = get32(input + 126);
    if (!validAuthenticationCaptureProvenance(provenance, wifiChannel)) {
        return SessionCodecStatus::CaptureInvalid;
    }
    if (output != nullptr) *output = provenance;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeCaptureRecord(
    const std::uint8_t* input, std::size_t size,
    services::survey::SurveySession* output,
    AuthenticationCaptureProvenance* provenance = nullptr) {
    if (input == nullptr || output == nullptr ||
        (size != kCaptureRecordBytes &&
         size != kSubGhzRawCaptureRecordBytes &&
         size != kInfraredRawCaptureRecordBytes &&
         size != kAuthenticationCaptureRecordBytes) ||
        std::memcmp(input, kCaptureMagic, sizeof(kCaptureMagic)) != 0 ||
        (input[4] != kCaptureWireVersion &&
         input[4] != kWifiFrameCaptureWireVersion &&
         input[4] != kSubGhzRawCaptureWireVersion &&
         input[4] != kInfraredRawCaptureWireVersion &&
         input[4] != kAuthenticationCaptureWireVersion) || input[7] != 32 ||
        (input[6] & static_cast<std::uint8_t>(~kCaptureKnownFlags)) != 0 ||
        input[13] != 0 || input[14] != 0 || input[15] != 0 ||
        input[31] != 0) {
        return SessionCodecStatus::CaptureInvalid;
    }
    const bool authenticationWire =
        input[4] == kAuthenticationCaptureWireVersion;
    const bool payloadWire = input[4] == kWifiFrameCaptureWireVersion ||
                             authenticationWire;
    const bool subGhzWire = input[4] == kSubGhzRawCaptureWireVersion;
    const bool infraredWire =
        input[4] == kInfraredRawCaptureWireVersion;
    if ((subGhzWire && size != kSubGhzRawCaptureRecordBytes) ||
        (infraredWire && size != kInfraredRawCaptureRecordBytes) ||
        (authenticationWire && size != kAuthenticationCaptureRecordBytes) ||
        (!subGhzWire && !infraredWire && !authenticationWire &&
         size != kCaptureRecordBytes)) {
        return SessionCodecStatus::CaptureInvalid;
    }
    if ((!payloadWire &&
         (input[26] != 0 || input[27] != 0 || input[28] != 0 ||
          input[29] != 0 || input[30] != 0 ||
          (input[6] & kCaptureFlagFramePayload) != 0)) ||
        (payloadWire && (input[6] & kCaptureFlagFramePayload) == 0) ||
        (subGhzWire && (input[6] & kCaptureFlagSubGhzRaw) == 0) ||
        (!subGhzWire && (input[6] & kCaptureFlagSubGhzRaw) != 0) ||
        (infraredWire && (input[6] & kCaptureFlagInfraredRaw) == 0) ||
        (!infraredWire && (input[6] & kCaptureFlagInfraredRaw) != 0) ||
        ((subGhzWire || infraredWire) &&
         (input[6] & kCaptureFlagFramePayload) != 0) ||
        (subGhzWire && infraredWire)) {
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
    metadata.subGhzRawCaptured =
        (input[6] & kCaptureFlagSubGhzRaw) != 0;
    metadata.infraredRawCaptured =
        (input[6] & kCaptureFlagInfraredRaw) != 0;
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
    AuthenticationCaptureProvenance decodedProvenance;
    if (authenticationWire) {
        const SessionCodecStatus provenanceStatus =
            decodeAuthenticationCaptureProvenanceRecord(
                input, size, metadata.wifiChannel, &decodedProvenance);
        if (provenanceStatus != SessionCodecStatus::Valid) {
            return provenanceStatus;
        }
    }
    if (subGhzWire) {
        if (input[83] != 0 || input[78] > static_cast<std::uint8_t>(
                domain::captures::SubGhzRawModulation::FskAsync) ||
            input[79] > 1U || input[82] > 1U) {
            return SessionCodecStatus::CaptureInvalid;
        }
        metadata.subGhzFrequencyKHz = get32(input + 72);
        metadata.subGhzThresholdDbm = static_cast<std::int16_t>(
            get16(input + 76));
        metadata.subGhzModulation = static_cast<
            domain::captures::SubGhzRawModulation>(input[78]);
        metadata.subGhzStartLevel = input[79] != 0;
        metadata.subGhzPulseRecords = get16(input + 80);
        metadata.subGhzTruncated = input[82] != 0;
        metadata.subGhzPulseBytes = get32(input + 84);
    } else if (infraredWire) {
        if (input[72] > static_cast<std::uint8_t>(
                domain::captures::InfraredProtocol::NecRepeat) ||
            input[73] > 1U || input[74] > 1U || input[75] > 1U ||
            input[78] != 0 || input[79] != 0 || input[87] != 0 ||
            input[92] != 0 || input[93] != 0 || input[94] != 0 ||
            input[95] != 0) {
            return SessionCodecStatus::CaptureInvalid;
        }
        metadata.infraredDecode.protocol = static_cast<
            domain::captures::InfraredProtocol>(input[72]);
        metadata.infraredStartLevel = input[73] != 0;
        metadata.infraredTruncated = input[74] != 0;
        metadata.infraredDecode.integrityValid = input[75] != 0;
        metadata.infraredPulseRecords = get16(input + 76);
        metadata.infraredPulseBytes = get32(input + 80);
        metadata.infraredDecode.address = get16(input + 84);
        metadata.infraredDecode.command = input[86];
        metadata.infraredDecode.rawCode = get32(input + 88);
    }
    if (output->configureCaptureMetadata(metadata) !=
        services::survey::CaptureMetadataStatus::Configured) {
        return SessionCodecStatus::CaptureInvalid;
    }
    if (authenticationWire && provenance != nullptr) {
        *provenance = decodedProvenance;
    }
    return SessionCodecStatus::Valid;
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

SessionCodecStatus encodeSubGhzRawBlock(
    const services::survey::SurveySession& session,
    const domain::captures::SubGhzRawSource& pulses,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        pulses.pulseCount() == 0 ||
        pulses.pulseCount() > PersistedSubGhzRawCaptureView::kPulseCapacity ||
        capacity < kSubGhzRawHeaderBytes + pulses.pulseCount() * 2U) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::memset(output, 0, kSubGhzRawHeaderBytes);
    std::memcpy(output, kSubGhzRawMagic, sizeof(kSubGhzRawMagic));
    output[4] = kSubGhzRawWireVersion;
    put16(output + 6, static_cast<std::uint16_t>(pulses.pulseCount()));
    std::uint64_t totalDurationUs = 0;
    std::size_t position = kSubGhzRawHeaderBytes;
    for (std::size_t index = 0; index < pulses.pulseCount(); ++index) {
        domain::captures::SubGhzRawPulseView pulse;
        if (!pulses.pulseView(index, &pulse) || pulse.durationUs == 0) {
            return SessionCodecStatus::CaptureInvalid;
        }
        put16(output + position, pulse.durationUs);
        position += 2;
        totalDurationUs += pulse.durationUs;
    }
    if (totalDurationUs > std::numeric_limits<std::uint32_t>::max()) {
        return SessionCodecStatus::BoundsExceeded;
    }
    put32(output + 8, static_cast<std::uint32_t>(totalDurationUs));
    const auto& metadata = session.captureMetadata();
    if (!metadata.subGhzRawCaptured ||
        metadata.subGhzPulseRecords != pulses.pulseCount() ||
        metadata.subGhzPulseBytes != pulses.pulseCount() * 2U) {
        return SessionCodecStatus::CaptureInvalid;
    }
    *outputSize = position;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeSubGhzRawBlock(
    const services::survey::SurveySession& session,
    const std::uint8_t* input, std::size_t size, std::size_t* decodedCount) {
    if (input == nullptr || size < kSubGhzRawHeaderBytes ||
        std::memcmp(input, kSubGhzRawMagic, sizeof(kSubGhzRawMagic)) != 0 ||
        input[4] != kSubGhzRawWireVersion || input[5] != 0 ||
        input[12] != 0 || input[13] != 0 || input[14] != 0 ||
        input[15] != 0) {
        return SessionCodecStatus::CaptureInvalid;
    }
    const std::size_t count = get16(input + 6);
    if (count == 0 || count > PersistedSubGhzRawCaptureView::kPulseCapacity ||
        size != kSubGhzRawHeaderBytes + count * 2U) {
        return SessionCodecStatus::BoundsExceeded;
    }
    std::uint64_t totalDurationUs = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const std::uint16_t duration =
            get16(input + kSubGhzRawHeaderBytes + index * 2U);
        if (duration == 0) return SessionCodecStatus::CaptureInvalid;
        totalDurationUs += duration;
    }
    const auto& metadata = session.captureMetadata();
    if (totalDurationUs != get32(input + 8) ||
        !metadata.subGhzRawCaptured ||
        metadata.subGhzPulseRecords != count ||
        metadata.subGhzPulseBytes != count * 2U) {
        return SessionCodecStatus::CaptureInvalid;
    }
    if (decodedCount != nullptr) *decodedCount = count;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus encodeInfraredRawBlock(
    const services::survey::SurveySession& session,
    const domain::captures::InfraredRawSource& pulses,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        pulses.pulseCount() == 0 ||
        pulses.pulseCount() > PersistedInfraredRawCaptureView::kPulseCapacity ||
        capacity < kInfraredRawHeaderBytes + pulses.pulseCount() * 2U) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::memset(output, 0, kInfraredRawHeaderBytes);
    std::memcpy(output, kInfraredRawMagic, sizeof(kInfraredRawMagic));
    output[4] = kInfraredRawWireVersion;
    put16(output + 6, static_cast<std::uint16_t>(pulses.pulseCount()));
    std::uint64_t totalDurationUs = 0;
    std::size_t position = kInfraredRawHeaderBytes;
    for (std::size_t index = 0; index < pulses.pulseCount(); ++index) {
        domain::captures::InfraredRawPulseView pulse;
        if (!pulses.pulseView(index, &pulse) || pulse.durationUs == 0) {
            return SessionCodecStatus::CaptureInvalid;
        }
        put16(output + position, pulse.durationUs);
        position += 2;
        totalDurationUs += pulse.durationUs;
    }
    if (totalDurationUs > std::numeric_limits<std::uint32_t>::max()) {
        return SessionCodecStatus::BoundsExceeded;
    }
    put32(output + 8, static_cast<std::uint32_t>(totalDurationUs));
    const auto& metadata = session.captureMetadata();
    if (!metadata.infraredRawCaptured ||
        metadata.infraredPulseRecords != pulses.pulseCount() ||
        metadata.infraredPulseBytes != pulses.pulseCount() * 2U) {
        return SessionCodecStatus::CaptureInvalid;
    }
    *outputSize = position;
    return SessionCodecStatus::Valid;
}

SessionCodecStatus decodeInfraredRawBlock(
    const services::survey::SurveySession& session,
    const std::uint8_t* input, std::size_t size, std::size_t* decodedCount) {
    if (input == nullptr || size < kInfraredRawHeaderBytes ||
        std::memcmp(input, kInfraredRawMagic, sizeof(kInfraredRawMagic)) != 0 ||
        input[4] != kInfraredRawWireVersion || input[5] != 0 ||
        input[12] != 0 || input[13] != 0 || input[14] != 0 ||
        input[15] != 0) {
        return SessionCodecStatus::CaptureInvalid;
    }
    const std::size_t count = get16(input + 6);
    if (count == 0 ||
        count > PersistedInfraredRawCaptureView::kPulseCapacity ||
        size != kInfraredRawHeaderBytes + count * 2U) {
        return SessionCodecStatus::BoundsExceeded;
    }
    std::uint64_t totalDurationUs = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const std::uint16_t duration =
            get16(input + kInfraredRawHeaderBytes + index * 2U);
        if (duration == 0) return SessionCodecStatus::CaptureInvalid;
        totalDurationUs += duration;
    }
    const auto& metadata = session.captureMetadata();
    if (totalDurationUs != get32(input + 8) ||
        !metadata.infraredRawCaptured ||
        metadata.infraredPulseRecords != count ||
        metadata.infraredPulseBytes != count * 2U) {
        return SessionCodecStatus::CaptureInvalid;
    }
    if (decodedCount != nullptr) *decodedCount = count;
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
        version != kWifiFrameSegmentSchemaVersion &&
        version != kSubGhzRawSegmentSchemaVersion &&
        version != kInfraredRawSegmentSchemaVersion &&
        version != kEnrichedSegmentSchemaVersion &&
        version != kAuthenticationCaptureSegmentSchemaVersion) {
        return SessionCodecStatus::UnsupportedSchema;
    }
    if ((version == kLegacySegmentSchemaVersion &&
         decodedAdditionalRecords != 0) ||
        (version == kTimelineSegmentSchemaVersion &&
         decodedAdditionalRecords != 1) ||
        (version == kSegmentSchemaVersion && decodedAdditionalRecords != 2) ||
        (version == kWifiFrameSegmentSchemaVersion &&
         decodedAdditionalRecords != 2) ||
        (version == kSubGhzRawSegmentSchemaVersion &&
         decodedAdditionalRecords != 2) ||
        (version == kInfraredRawSegmentSchemaVersion &&
         decodedAdditionalRecords != 2) ||
        (version == kEnrichedSegmentSchemaVersion &&
         decodedAdditionalRecords != 2) ||
        (version == kAuthenticationCaptureSegmentSchemaVersion &&
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
    if ((schemaVersion != kWifiFrameSegmentSchemaVersion &&
         schemaVersion != kAuthenticationCaptureSegmentSchemaVersion) ||
        recordCount != 0 ||
        additionalRecords != 2 || bodyLength < 16) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::size_t position = 0;
    const std::uint32_t captureLength = get32(segment + position);
    const std::uint32_t captureCrc = get32(segment + position + 4);
    position += 8;
    const std::size_t expectedCaptureLength =
        schemaVersion == kAuthenticationCaptureSegmentSchemaVersion
            ? kAuthenticationCaptureRecordBytes : kCaptureRecordBytes;
    if (captureLength != expectedCaptureLength ||
        captureLength > bodyLength - position ||
        captureCrc != crc32c(segment + position, captureLength)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    AuthenticationCaptureProvenance authenticationProvenance;
    if (schemaVersion == kAuthenticationCaptureSegmentSchemaVersion) {
        status = decodeAuthenticationCaptureProvenanceRecord(
            segment + position, captureLength,
            session.captureMetadata().wifiChannel,
            &authenticationProvenance);
        if (status != SessionCodecStatus::Valid) return status;
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
    if (status == SessionCodecStatus::Valid &&
        schemaVersion == kAuthenticationCaptureSegmentSchemaVersion &&
        authenticationProvenance.framesAccepted != output->count_) {
        status = SessionCodecStatus::CaptureInvalid;
    }
    if (status != SessionCodecStatus::Valid) output->reset();
    return status;
}

SessionCodecStatus openPersistedAuthenticationCapture(
    const services::survey::SurveySession& session,
    const std::uint8_t* segment, std::size_t segmentSize,
    AuthenticationCaptureProvenance* provenance,
    PersistedWifiFrameCaptureView* output) {
    if (provenance == nullptr || output == nullptr || segment == nullptr ||
        session.state() != services::survey::SessionState::Stopped) {
        return SessionCodecStatus::InvalidArgument;
    }
    output->reset();
    std::uint16_t schemaVersion = 0;
    SessionCodecStatus status = validateSegmentFooter(
        segment, segmentSize, nullptr, nullptr, &schemaVersion, nullptr);
    if (status != SessionCodecStatus::Valid) return status;
    if (schemaVersion != kAuthenticationCaptureSegmentSchemaVersion ||
        segmentSize < 8 + kAuthenticationCaptureRecordBytes +
                          kSegmentFooterBytes) {
        return SessionCodecStatus::UnsupportedSchema;
    }
    status = openPersistedWifiFrameCapture(session, segment, segmentSize,
                                           output);
    if (status != SessionCodecStatus::Valid) return status;
    const std::uint32_t captureLength = get32(segment);
    AuthenticationCaptureProvenance decodedProvenance;
    status = decodeAuthenticationCaptureProvenanceRecord(
        segment + 8, captureLength, session.captureMetadata().wifiChannel,
        &decodedProvenance);
    if (status != SessionCodecStatus::Valid ||
        decodedProvenance.framesAccepted != output->frameCount()) {
        output->reset();
        return SessionCodecStatus::CaptureInvalid;
    }
    *provenance = decodedProvenance;
    return SessionCodecStatus::Valid;
}

void PersistedSubGhzRawCaptureView::reset() {
    block_ = nullptr;
    blockSize_ = 0;
    count_ = 0;
}

bool PersistedSubGhzRawCaptureView::pulseView(
    std::size_t index, domain::captures::SubGhzRawPulseView* output) const {
    if (output == nullptr || block_ == nullptr || index >= count_ ||
        blockSize_ < kSubGhzRawHeaderBytes + (index + 1U) * 2U) {
        return false;
    }
    output->durationUs = get16(
        block_ + kSubGhzRawHeaderBytes + index * 2U);
    return output->durationUs != 0;
}

SessionCodecStatus openPersistedSubGhzRawCapture(
    const services::survey::SurveySession& session,
    const std::uint8_t* segment, std::size_t segmentSize,
    PersistedSubGhzRawCaptureView* output) {
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
    if (schemaVersion != kSubGhzRawSegmentSchemaVersion ||
        recordCount != 0 || additionalRecords != 2 || bodyLength < 16) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::size_t position = 0;
    const std::uint32_t captureLength = get32(segment + position);
    const std::uint32_t captureCrc = get32(segment + position + 4);
    position += 8;
    if (captureLength != kSubGhzRawCaptureRecordBytes ||
        captureLength > bodyLength - position ||
        captureCrc != crc32c(segment + position, captureLength)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    position += captureLength;
    if (bodyLength - position < 8) return SessionCodecStatus::BoundsExceeded;
    const std::uint32_t blockLength = get32(segment + position);
    const std::uint32_t blockCrc = get32(segment + position + 4);
    position += 8;
    if (blockLength < kSubGhzRawHeaderBytes ||
        blockLength != bodyLength - position ||
        blockCrc != crc32c(segment + position, blockLength)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    output->block_ = segment + position;
    output->blockSize_ = blockLength;
    status = decodeSubGhzRawBlock(
        session, output->block_, output->blockSize_, &output->count_);
    if (status != SessionCodecStatus::Valid) output->reset();
    return status;
}

void PersistedInfraredRawCaptureView::reset() {
    block_ = nullptr;
    blockSize_ = 0;
    count_ = 0;
}

bool PersistedInfraredRawCaptureView::pulseView(
    std::size_t index,
    domain::captures::InfraredRawPulseView* output) const {
    if (output == nullptr || block_ == nullptr || index >= count_ ||
        blockSize_ < kInfraredRawHeaderBytes + (index + 1U) * 2U) {
        return false;
    }
    output->durationUs = get16(
        block_ + kInfraredRawHeaderBytes + index * 2U);
    return output->durationUs != 0;
}

SessionCodecStatus openPersistedInfraredRawCapture(
    const services::survey::SurveySession& session,
    const std::uint8_t* segment, std::size_t segmentSize,
    PersistedInfraredRawCaptureView* output) {
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
    if (schemaVersion != kInfraredRawSegmentSchemaVersion ||
        recordCount != 0 || additionalRecords != 2 || bodyLength < 16) {
        return SessionCodecStatus::CaptureInvalid;
    }
    std::size_t position = 0;
    const std::uint32_t captureLength = get32(segment + position);
    const std::uint32_t captureCrc = get32(segment + position + 4);
    position += 8;
    if (captureLength != kInfraredRawCaptureRecordBytes ||
        captureLength > bodyLength - position ||
        captureCrc != crc32c(segment + position, captureLength)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    position += captureLength;
    if (bodyLength - position < 8) return SessionCodecStatus::BoundsExceeded;
    const std::uint32_t blockLength = get32(segment + position);
    const std::uint32_t blockCrc = get32(segment + position + 4);
    position += 8;
    if (blockLength < kInfraredRawHeaderBytes ||
        blockLength != bodyLength - position ||
        blockCrc != crc32c(segment + position, blockLength)) {
        return SessionCodecStatus::ChecksumMismatch;
    }
    output->block_ = segment + position;
    output->blockSize_ = blockLength;
    status = decodeInfraredRawBlock(
        session, output->block_, output->blockSize_, &output->count_);
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
            encodeObservation(*observation, hasCapture, record,
                              sizeof(record), &recordSize);
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
    put16(footer + 4, hasCapture ? kEnrichedSegmentSchemaVersion
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

SessionCodecStatus encodeAuthenticationCaptureSegment(
    const services::survey::SurveySession& session,
    const AuthenticationCaptureProvenance& provenance,
    const domain::captures::WifiFrameSource& frames,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        session.state() != services::survey::SessionState::Stopped ||
        capacity > kSessionSegmentMaxBytes || session.size() != 0 ||
        session.timeline().present ||
        !session.captureMetadata().present ||
        !session.captureMetadata().framePayloadCaptured ||
        provenance.framesAccepted != frames.frameCount()) {
        return SessionCodecStatus::CaptureInvalid;
    }
    CborWriter writer(output, capacity);
    std::uint8_t captureRecord[kAuthenticationCaptureRecordBytes] = {};
    std::size_t captureRecordSize = 0;
    SessionCodecStatus status = encodeAuthenticationCaptureRecord(
        session.captureMetadata(), provenance, captureRecord,
        sizeof(captureRecord), &captureRecordSize);
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
    put16(footer + 4, kAuthenticationCaptureSegmentSchemaVersion);
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

SessionCodecStatus encodeSubGhzRawCaptureSegment(
    const services::survey::SurveySession& session,
    const domain::captures::SubGhzRawSource& pulses,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        session.state() != services::survey::SessionState::Stopped ||
        capacity > kSessionSegmentMaxBytes || session.size() != 0 ||
        session.timeline().present || !session.captureMetadata().present ||
        !session.captureMetadata().subGhzRawCaptured ||
        session.captureMetadata().framePayloadCaptured) {
        return SessionCodecStatus::CaptureInvalid;
    }
    CborWriter writer(output, capacity);
    std::uint8_t captureRecord[kSubGhzRawCaptureRecordBytes] = {};
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
    std::size_t pulseBlockSize = 0;
    std::uint8_t* pulseBlock = output + writer.size() + 8;
    status = encodeSubGhzRawBlock(
        session, pulses, pulseBlock, capacity - writer.size() - 8,
        &pulseBlockSize);
    if (status != SessionCodecStatus::Valid) return status;
    writer.be32(static_cast<std::uint32_t>(pulseBlockSize));
    writer.be32(crc32c(pulseBlock, pulseBlockSize));
    writer.raw(pulseBlock, pulseBlockSize);
    if (!writer.ok() || kSegmentFooterBytes > capacity - writer.size()) {
        return SessionCodecStatus::BufferTooSmall;
    }
    const std::size_t bodySize = writer.size();
    std::uint8_t footer[kSegmentFooterBytes] = {};
    std::memcpy(footer, kSegmentMagic, sizeof(kSegmentMagic));
    put16(footer + 4, kSubGhzRawSegmentSchemaVersion);
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

SessionCodecStatus encodeInfraredRawCaptureSegment(
    const services::survey::SurveySession& session,
    const domain::captures::InfraredRawSource& pulses,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr ||
        session.state() != services::survey::SessionState::Stopped ||
        capacity > kSessionSegmentMaxBytes || session.size() != 0 ||
        session.timeline().present || !session.captureMetadata().present ||
        !session.captureMetadata().infraredRawCaptured ||
        session.captureMetadata().subGhzRawCaptured ||
        session.captureMetadata().framePayloadCaptured) {
        return SessionCodecStatus::CaptureInvalid;
    }
    CborWriter writer(output, capacity);
    std::uint8_t captureRecord[kInfraredRawCaptureRecordBytes] = {};
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
    std::size_t pulseBlockSize = 0;
    std::uint8_t* pulseBlock = output + writer.size() + 8;
    status = encodeInfraredRawBlock(
        session, pulses, pulseBlock, capacity - writer.size() - 8,
        &pulseBlockSize);
    if (status != SessionCodecStatus::Valid) return status;
    writer.be32(static_cast<std::uint32_t>(pulseBlockSize));
    writer.be32(crc32c(pulseBlock, pulseBlockSize));
    writer.raw(pulseBlock, pulseBlockSize);
    if (!writer.ok() || kSegmentFooterBytes > capacity - writer.size()) {
        return SessionCodecStatus::BufferTooSmall;
    }
    const std::size_t bodySize = writer.size();
    std::uint8_t footer[kSegmentFooterBytes] = {};
    std::memcpy(footer, kSegmentMagic, sizeof(kSegmentMagic));
    put16(footer + 4, kInfraredRawSegmentSchemaVersion);
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
    writer.unsignedValue(
                         segmentVersion ==
                                 kAuthenticationCaptureSegmentSchemaVersion
                             ? kAuthenticationCaptureSessionSchemaVersion
                         : segmentVersion == kEnrichedSegmentSchemaVersion
                             ? kEnrichedSessionSchemaVersion
                         : segmentVersion == kInfraredRawSegmentSchemaVersion
                             ? kInfraredRawSessionSchemaVersion
                         : segmentVersion == kSubGhzRawSegmentSchemaVersion
                             ? kSubGhzRawSessionSchemaVersion
                         : segmentVersion == kWifiFrameSegmentSchemaVersion
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
        value != kWifiFrameSessionSchemaVersion &&
        value != kSubGhzRawSessionSchemaVersion &&
        value != kInfraredRawSessionSchemaVersion &&
        value != kEnrichedSessionSchemaVersion &&
        value != kAuthenticationCaptureSessionSchemaVersion) {
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
        manifest.schemaVersion == kAuthenticationCaptureSessionSchemaVersion
            ? kAuthenticationCaptureSegmentSchemaVersion
        : manifest.schemaVersion == kEnrichedSessionSchemaVersion
            ? kEnrichedSegmentSchemaVersion
        : manifest.schemaVersion == kInfraredRawSessionSchemaVersion
            ? kInfraredRawSegmentSchemaVersion
        : manifest.schemaVersion == kSubGhzRawSessionSchemaVersion
            ? kSubGhzRawSegmentSchemaVersion
        : manifest.schemaVersion == kWifiFrameSessionSchemaVersion
            ? kWifiFrameSegmentSchemaVersion
            : manifest.schemaVersion == kSessionSchemaVersion
            ? kSegmentSchemaVersion : kLegacySegmentSchemaVersion;
    const std::uint16_t compatibleSegmentVersion =
        manifest.schemaVersion == kTimelineSessionSchemaVersion
            ? kTimelineSegmentSchemaVersion : expectedSegmentVersion;
    const std::uint16_t expectedAdditionalRecords =
        manifest.schemaVersion == kAuthenticationCaptureSessionSchemaVersion
            ? 2
        : manifest.schemaVersion == kEnrichedSessionSchemaVersion
            ? 2
        : manifest.schemaVersion == kInfraredRawSessionSchemaVersion
            ? 2
        : manifest.schemaVersion == kSubGhzRawSessionSchemaVersion
            ? 2
        : manifest.schemaVersion == kWifiFrameSessionSchemaVersion
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
    AuthenticationCaptureProvenance authenticationProvenance;
    if (manifest.schemaVersion == kAuthenticationCaptureSessionSchemaVersion ||
        manifest.schemaVersion == kEnrichedSessionSchemaVersion ||
        manifest.schemaVersion == kSessionSchemaVersion ||
        manifest.schemaVersion == kInfraredRawSessionSchemaVersion ||
        manifest.schemaVersion == kSubGhzRawSessionSchemaVersion ||
        manifest.schemaVersion == kWifiFrameSessionSchemaVersion) {
        if (bodyLength - position < 8) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        const std::uint32_t recordLength = get32(segment + position);
        const std::uint32_t recordCrc = get32(segment + position + 4);
        position += 8;
        const std::size_t expectedCaptureBytes =
            manifest.schemaVersion ==
                    kAuthenticationCaptureSessionSchemaVersion
                ? kAuthenticationCaptureRecordBytes
            : manifest.schemaVersion == kInfraredRawSessionSchemaVersion
                ? kInfraredRawCaptureRecordBytes
            : manifest.schemaVersion == kSubGhzRawSessionSchemaVersion
                ? kSubGhzRawCaptureRecordBytes : kCaptureRecordBytes;
        if (recordLength != expectedCaptureBytes ||
            recordLength > bodyLength - position) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        if (recordCrc != crc32c(segment + position, recordLength)) {
            output->reset();
            return SessionCodecStatus::ChecksumMismatch;
        }
        status = decodeCaptureRecord(
            segment + position, recordLength, output,
            manifest.schemaVersion ==
                    kAuthenticationCaptureSessionSchemaVersion
                ? &authenticationProvenance : nullptr);
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
        status = decodeObservation(
            segment + position, recordLength,
            manifest.schemaVersion == kEnrichedSessionSchemaVersion,
            &observation);
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
    if (manifest.schemaVersion == kAuthenticationCaptureSessionSchemaVersion ||
        manifest.schemaVersion == kInfraredRawSessionSchemaVersion ||
        manifest.schemaVersion == kWifiFrameSessionSchemaVersion ||
        manifest.schemaVersion == kSubGhzRawSessionSchemaVersion) {
        if (bodyLength - position < 8) {
            output->reset();
            return SessionCodecStatus::BoundsExceeded;
        }
        const std::uint32_t recordLength = get32(segment + position);
        const std::uint32_t recordCrc = get32(segment + position + 4);
        position += 8;
        const std::size_t minimumBlockBytes =
            manifest.schemaVersion == kInfraredRawSessionSchemaVersion
                ? kInfraredRawHeaderBytes
            : manifest.schemaVersion == kSubGhzRawSessionSchemaVersion
                ? kSubGhzRawHeaderBytes : kWifiFrameHeaderBytes;
        if (recordLength < minimumBlockBytes ||
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
        std::size_t decodedCaptureCount = 0;
        status = manifest.schemaVersion == kInfraredRawSessionSchemaVersion
            ? decodeInfraredRawBlock(*output, segment + position,
                                     recordLength, nullptr)
            : manifest.schemaVersion == kSubGhzRawSessionSchemaVersion
                  ? decodeSubGhzRawBlock(*output, segment + position,
                                         recordLength, nullptr)
                  : decodeWifiFrameBlock(*output, segment + position,
                                         recordLength, nullptr, 0,
                                         &decodedCaptureCount, nullptr);
        if (status == SessionCodecStatus::Valid &&
            manifest.schemaVersion ==
                kAuthenticationCaptureSessionSchemaVersion &&
            authenticationProvenance.framesAccepted != decodedCaptureCount) {
            status = SessionCodecStatus::CaptureInvalid;
        }
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
    if ((manifest.schemaVersion == kSessionSchemaVersion ||
         manifest.schemaVersion == kEnrichedSessionSchemaVersion) &&
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
    if (manifest.schemaVersion != kAuthenticationCaptureSessionSchemaVersion &&
        manifest.schemaVersion != kWifiFrameSessionSchemaVersion &&
        manifest.schemaVersion != kSubGhzRawSessionSchemaVersion &&
        manifest.schemaVersion != kInfraredRawSessionSchemaVersion &&
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
    if (session.captureMetadata().infraredRawCaptured) {
        const auto& capture = session.captureMetadata();
        written = std::snprintf(
            output, capacity,
            "{\"schema\":\"leshy.capture.infrared_raw.v1\",\"id\":\"%s\","
            "\"started_us\":%llu,\"stopped_us\":%llu,"
            "\"protocol\":\"%s\",\"raw_code\":%lu,"
            "\"address\":%u,\"command\":%u,\"integrity_valid\":%s,"
            "\"pulses\":%u,\"pulse_bytes\":%lu,\"start_level\":%s,"
            "\"truncated\":%s,\"passive\":true,\"rx_only\":true}",
            session.id(),
            static_cast<unsigned long long>(session.startedUs()),
            static_cast<unsigned long long>(session.stoppedUs()),
            domain::captures::infraredProtocolName(
                capture.infraredDecode.protocol),
            static_cast<unsigned long>(capture.infraredDecode.rawCode),
            static_cast<unsigned>(capture.infraredDecode.address),
            static_cast<unsigned>(capture.infraredDecode.command),
            capture.infraredDecode.integrityValid ? "true" : "false",
            static_cast<unsigned>(capture.infraredPulseRecords),
            static_cast<unsigned long>(capture.infraredPulseBytes),
            capture.infraredStartLevel ? "true" : "false",
            capture.infraredTruncated ? "true" : "false");
    } else if (session.captureMetadata().subGhzRawCaptured) {
        const auto& capture = session.captureMetadata();
        written = std::snprintf(
            output, capacity,
            "{\"schema\":\"leshy.capture.subghz_raw.v1\",\"id\":\"%s\","
            "\"started_us\":%llu,\"stopped_us\":%llu,"
            "\"frequency_khz\":%lu,\"threshold_dbm\":%d,"
            "\"modulation\":\"%s\",\"pulses\":%u,"
            "\"pulse_bytes\":%lu,\"start_level\":%s,"
            "\"truncated\":%s,\"passive\":true,\"rx_only\":true}",
            session.id(),
            static_cast<unsigned long long>(session.startedUs()),
            static_cast<unsigned long long>(session.stoppedUs()),
            static_cast<unsigned long>(capture.subGhzFrequencyKHz),
            static_cast<int>(capture.subGhzThresholdDbm),
            domain::captures::subGhzRawModulationName(
                capture.subGhzModulation),
            static_cast<unsigned>(capture.subGhzPulseRecords),
            static_cast<unsigned long>(capture.subGhzPulseBytes),
            capture.subGhzStartLevel ? "true" : "false",
            capture.subGhzTruncated ? "true" : "false");
    } else if (session.captureMetadata().framePayloadCaptured) {
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
