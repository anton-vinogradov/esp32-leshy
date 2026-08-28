#include "WifiAuthenticationFrameDecoder.h"

#include <cstring>
#include <type_traits>

namespace leshy1::services::auth {
namespace {

using domain::captures::WifiFrameKind;
using domain::captures::WifiFrameView;

static_assert(
    std::is_trivially_copyable_v<WifiAuthenticationDecodedKeyFrame>,
    "authentication frame decode result must remain allocation-free");
static_assert(sizeof(WifiAuthenticationDecodedKeyFrame) <= 128U,
              "authentication frame decode result exceeded its bound");

constexpr std::size_t kDataHeaderBytes = 24U;
constexpr std::size_t kFourAddressHeaderBytes = 30U;
constexpr std::size_t kLlcSnapBytes = 8U;
constexpr std::size_t kEapolHeaderBytes = 4U;
constexpr std::size_t kEapolKeyFixedBytes = 95U;
constexpr std::size_t kKeyDataLengthOffset = 93U;
constexpr std::size_t kKeyMicOffset = 77U;
constexpr std::size_t kKeyMicBytes = 16U;
constexpr std::uint16_t kEapolEtherType = 0x888eU;
constexpr std::uint8_t kEapolKeyPacketType = 3U;
constexpr std::uint16_t kKeyInfoPairwise = 1U << 3U;
constexpr std::uint16_t kKeyInfoInstall = 1U << 6U;
constexpr std::uint16_t kKeyInfoAck = 1U << 7U;
constexpr std::uint16_t kKeyInfoMic = 1U << 8U;
constexpr std::uint16_t kKeyInfoSecure = 1U << 9U;
constexpr std::uint16_t kKeyInfoError = 1U << 10U;
constexpr std::uint16_t kKeyInfoRequest = 1U << 11U;
constexpr std::uint16_t kKeyInfoEncrypted = 1U << 12U;
constexpr std::uint16_t kKeyInfoSmk = 1U << 13U;
constexpr std::uint16_t kKeyInfoReserved = 3U << 14U;
constexpr std::uint16_t kKeyInfoRsnKeyIndex = 3U << 4U;

std::uint16_t readBig16(const std::uint8_t* value) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(value[0]) << 8U) |
        static_cast<std::uint16_t>(value[1]));
}

std::uint64_t readBig64(const std::uint8_t* value) {
    std::uint64_t result = 0;
    for (std::size_t index = 0; index < 8U; ++index) {
        result = (result << 8U) | value[index];
    }
    return result;
}

std::array<std::uint8_t, 6> readMac(const std::uint8_t* value) {
    std::array<std::uint8_t, 6> result{};
    std::memcpy(result.data(), value, result.size());
    return result;
}

bool anyNonzero(const std::uint8_t* value, std::size_t size) {
    if (value == nullptr) return false;
    for (std::size_t index = 0U; index < size; ++index) {
        if (value[index] != 0U) return true;
    }
    return false;
}

WifiEapolKeyMessage classifyKey(std::uint16_t keyInfo) {
    if ((keyInfo & kKeyInfoPairwise) == 0U ||
        (keyInfo & (kKeyInfoError | kKeyInfoRequest | kKeyInfoSmk |
                    kKeyInfoReserved | kKeyInfoRsnKeyIndex)) != 0U) {
        return WifiEapolKeyMessage::Unknown;
    }
    const bool install = (keyInfo & kKeyInfoInstall) != 0U;
    const bool ack = (keyInfo & kKeyInfoAck) != 0U;
    const bool mic = (keyInfo & kKeyInfoMic) != 0U;
    const bool secure = (keyInfo & kKeyInfoSecure) != 0U;
    if (ack && !mic && !install && !secure) {
        return WifiEapolKeyMessage::Message1;
    }
    if (!ack && mic && !install && !secure) {
        return WifiEapolKeyMessage::Message2;
    }
    if (ack && mic && install && secure) {
        return WifiEapolKeyMessage::Message3;
    }
    if (!ack && mic && !install && secure) {
        return WifiEapolKeyMessage::Message4;
    }
    return WifiEapolKeyMessage::Unknown;
}

bool findPmkidKde(const std::uint8_t* keyData, std::size_t keyDataLength,
                  std::array<std::uint8_t, 16>* output, bool* malformed) {
    if (output == nullptr || malformed == nullptr) return false;
    std::size_t offset = 0;
    bool found = false;
    while (offset < keyDataLength) {
        if (keyDataLength - offset < 2U) {
            *malformed = true;
            return false;
        }
        const std::uint8_t elementId = keyData[offset];
        const std::size_t elementLength = keyData[offset + 1U];
        offset += 2U;
        if (elementLength > keyDataLength - offset) {
            *malformed = true;
            return false;
        }
        const std::uint8_t* element = keyData + offset;
        if (elementId == 0xddU && elementLength == 20U &&
            element[0] == 0x00U && element[1] == 0x0fU &&
            element[2] == 0xacU && element[3] == 0x04U) {
            std::array<std::uint8_t, 16> candidate{};
            std::memcpy(candidate.data(), element + 4U, candidate.size());
            bool any = false;
            for (std::uint8_t octet : candidate) any = any || octet != 0U;
            if (!any) {
                *malformed = true;
                return false;
            }
            if (found && *output != candidate) {
                *malformed = true;
                return false;
            }
            *output = candidate;
            found = true;
        }
        offset += elementLength;
    }
    return found;
}

}  // namespace

bool validWifiAuthenticationUnicastMac(
    const std::array<std::uint8_t, 6>& address) {
    if ((address[0] & 1U) != 0U) return false;
    bool any = false;
    bool allOnes = true;
    for (std::uint8_t octet : address) {
        any = any || octet != 0U;
        allOnes = allOnes && octet == 0xffU;
    }
    return any && !allOnes;
}

WifiAuthenticationFrameDecodeStatus decodeWifiAuthenticationKeyFrame(
    const WifiFrameView& frame,
    WifiAuthenticationDecodedKeyFrame* output) {
    using Status = WifiAuthenticationFrameDecodeStatus;
    if (output == nullptr) return Status::Malformed;
    *output = {};
    if (frame.payload == nullptr || frame.capturedLength == 0U ||
        frame.originalLength == 0U ||
        frame.capturedLength > frame.originalLength ||
        frame.monotonicUs == 0U || frame.channel < 1U ||
        frame.channel > 14U) {
        return Status::Malformed;
    }
    if (frame.kind != WifiFrameKind::Data) return Status::Ignored;
    std::size_t payloadLength = frame.capturedLength;
    if (frame.fcsIncluded) {
        if (payloadLength < 4U) return Status::Malformed;
        payloadLength -= 4U;
    }
    if (payloadLength < kDataHeaderBytes) {
        return frame.originalLength > frame.capturedLength
                   ? Status::Truncated
                   : Status::Malformed;
    }

    const std::uint16_t frameControl = static_cast<std::uint16_t>(
        frame.payload[0] |
        (static_cast<std::uint16_t>(frame.payload[1]) << 8U));
    const std::uint8_t type = static_cast<std::uint8_t>(
        (frameControl >> 2U) & 0x03U);
    if (type != 2U) return Status::Malformed;
    const std::uint8_t subtype = static_cast<std::uint8_t>(
        (frameControl >> 4U) & 0x0fU);
    const bool toDistribution = (frameControl & (1U << 8U)) != 0U;
    const bool fromDistribution = (frameControl & (1U << 9U)) != 0U;
    const bool protectedPayload = (frameControl & (1U << 14U)) != 0U;
    const bool ordered = (frameControl & (1U << 15U)) != 0U;
    const bool qos = (subtype & 0x08U) != 0U;
    std::size_t headerLength = toDistribution && fromDistribution
        ? kFourAddressHeaderBytes : kDataHeaderBytes;
    if (qos) headerLength += 2U;
    if (qos && ordered) headerLength += 4U;
    if (payloadLength < headerLength + kLlcSnapBytes) {
        return frame.originalLength > frame.capturedLength
                   ? Status::Truncated
                   : Status::Malformed;
    }
    if (protectedPayload) return Status::Ignored;

    const std::uint8_t* llc = frame.payload + headerLength;
    if (llc[0] != 0xaaU || llc[1] != 0xaaU || llc[2] != 0x03U ||
        llc[3] != 0x00U || llc[4] != 0x00U || llc[5] != 0x00U ||
        readBig16(llc + 6U) != kEapolEtherType) {
        return Status::Ignored;
    }
    if (toDistribution == fromDistribution) return Status::Malformed;
    if (frame.originalLength > frame.capturedLength) {
        return Status::Truncated;
    }

    const std::uint8_t* eapol = llc + kLlcSnapBytes;
    const std::size_t eapolAvailable =
        payloadLength - headerLength - kLlcSnapBytes;
    if (eapolAvailable < kEapolHeaderBytes) return Status::Truncated;
    output->eapolVersion = eapol[0];
    if (output->eapolVersion == 0U || output->eapolVersion > 3U) {
        return Status::Malformed;
    }
    const std::size_t bodyLength = readBig16(eapol + 2U);
    if (bodyLength > eapolAvailable - kEapolHeaderBytes) {
        return Status::Truncated;
    }
    if (bodyLength != eapolAvailable - kEapolHeaderBytes) {
        return Status::Malformed;
    }
    if (eapol[1] != kEapolKeyPacketType) return Status::EapolNonKey;
    if (bodyLength < 1U) return Status::Malformed;

    const std::uint8_t* key = eapol + kEapolHeaderBytes;
    output->descriptorType = key[0];
    if (toDistribution) {
        output->accessPoint = readMac(frame.payload + 4U);
        output->station = readMac(frame.payload + 10U);
    } else {
        output->station = readMac(frame.payload + 4U);
        output->accessPoint = readMac(frame.payload + 10U);
    }
    if (!validWifiAuthenticationUnicastMac(output->accessPoint) ||
        !validWifiAuthenticationUnicastMac(output->station) ||
        output->accessPoint == output->station) {
        return Status::Malformed;
    }
    output->fromAccessPoint = fromDistribution;

    if (output->descriptorType !=
        kWifiAuthenticationSupportedDescriptorType) {
        return Status::UnsupportedKey;
    }
    constexpr std::size_t kRsnCommonPrefixBytes = 45U;
    if (bodyLength < kRsnCommonPrefixBytes) return Status::Malformed;
    output->keyInfo = readBig16(key + 1U);
    output->descriptorVersion = static_cast<std::uint8_t>(
        output->keyInfo & 0x07U);
    output->message = classifyKey(output->keyInfo);
    output->replayCounter = readBig64(key + 5U);
    std::memcpy(output->nonce.data(), key + 13U, output->nonce.size());
    if (output->descriptorVersion !=
            kWifiAuthenticationSupportedDescriptorVersion2 &&
        output->descriptorVersion !=
            kWifiAuthenticationSupportedDescriptorVersion3) {
        return Status::UnsupportedKey;
    }
    if (bodyLength < kEapolKeyFixedBytes) return Status::Malformed;
    output->keyMicNonzero = anyNonzero(key + kKeyMicOffset, kKeyMicBytes);
    const bool classifiedMicBearingMessage =
        output->message == WifiEapolKeyMessage::Message2 ||
        output->message == WifiEapolKeyMessage::Message3 ||
        output->message == WifiEapolKeyMessage::Message4;
    if (classifiedMicBearingMessage && !output->keyMicNonzero) {
        return Status::Malformed;
    }
    const std::size_t keyDataLength =
        readBig16(key + kKeyDataLengthOffset);
    if (keyDataLength != bodyLength - kEapolKeyFixedBytes) {
        return Status::Malformed;
    }
    if ((output->keyInfo & kKeyInfoEncrypted) == 0U &&
        keyDataLength > 0U) {
        bool malformed = false;
        output->hasPmkid = findPmkidKde(
            key + kEapolKeyFixedBytes, keyDataLength, &output->pmkid,
            &malformed);
        if (malformed) return Status::Malformed;
    }
    return output->message == WifiEapolKeyMessage::Unknown
        ? Status::UnclassifiedKey : Status::ClassifiedKey;
}

}  // namespace leshy1::services::auth
