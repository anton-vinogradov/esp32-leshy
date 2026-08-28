#include "WifiAuthenticationCapture.h"

#include <algorithm>
#include <cstring>
#include <type_traits>

namespace leshy1::services::auth {
namespace {

using domain::captures::WifiFrameKind;
using domain::captures::WifiFrameView;

static_assert(std::is_trivially_copyable_v<WifiAuthenticationCaptureReport>,
              "authentication report must remain byte-resettable");

constexpr std::size_t kMacBytes = 6;
constexpr std::size_t kDataHeaderBytes = 24;
constexpr std::size_t kFourAddressHeaderBytes = 30;
constexpr std::size_t kLlcSnapBytes = 8;
constexpr std::size_t kEapolHeaderBytes = 4;
constexpr std::size_t kEapolKeyFixedBytes = 95;
constexpr std::size_t kKeyDataLengthOffset = 93;
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
constexpr std::uint8_t kSupportedDescriptorType = 2U;
constexpr std::uint8_t kSupportedDescriptorVersion2 = 2U;
constexpr std::uint8_t kSupportedDescriptorVersion3 = 3U;

enum class DecodeStatus : std::uint8_t {
    Ignored,
    EapolNonKey,
    UnclassifiedKey,
    UnsupportedKey,
    ClassifiedKey,
    Malformed,
    Truncated,
};

struct DecodedKey final {
    WifiEapolKeyMessage message = WifiEapolKeyMessage::Unknown;
    std::array<std::uint8_t, kMacBytes> accessPoint{};
    std::array<std::uint8_t, kMacBytes> station{};
    std::uint64_t replayCounter = 0;
    std::uint16_t keyInfo = 0;
    std::uint8_t eapolVersion = 0;
    std::uint8_t descriptorType = 0;
    std::uint8_t descriptorVersion = 0;
    std::array<std::uint8_t, 32> nonce{};
    std::array<std::uint8_t, 16> pmkid{};
    bool hasPmkid = false;
    bool fromAccessPoint = false;
};

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

bool sameMac(const std::array<std::uint8_t, kMacBytes>& left,
             const std::array<std::uint8_t, kMacBytes>& right) {
    return left == right;
}

bool validUnicastMac(const std::array<std::uint8_t, kMacBytes>& address) {
    if ((address[0] & 1U) != 0U) return false;
    bool any = false;
    bool allOnes = true;
    for (std::uint8_t octet : address) {
        any = any || octet != 0U;
        allOnes = allOnes && octet == 0xffU;
    }
    return any && !allOnes;
}

std::array<std::uint8_t, kMacBytes> readMac(const std::uint8_t* value) {
    std::array<std::uint8_t, kMacBytes> result{};
    std::memcpy(result.data(), value, result.size());
    return result;
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

DecodeStatus decodeKey(const WifiFrameView& frame, DecodedKey* output) {
    if (output == nullptr || frame.payload == nullptr ||
        frame.capturedLength == 0U || frame.originalLength == 0U ||
        frame.capturedLength > frame.originalLength || frame.monotonicUs == 0U ||
        frame.channel < 1U || frame.channel > 14U) {
        return DecodeStatus::Malformed;
    }
    if (frame.kind != WifiFrameKind::Data) return DecodeStatus::Ignored;
    std::size_t payloadLength = frame.capturedLength;
    if (frame.fcsIncluded) {
        if (payloadLength < 4U) return DecodeStatus::Malformed;
        payloadLength -= 4U;
    }
    if (payloadLength < kDataHeaderBytes) {
        return frame.originalLength > frame.capturedLength
                   ? DecodeStatus::Truncated
                   : DecodeStatus::Malformed;
    }

    const std::uint16_t frameControl = static_cast<std::uint16_t>(
        frame.payload[0] | (static_cast<std::uint16_t>(frame.payload[1]) << 8U));
    const std::uint8_t type = static_cast<std::uint8_t>(
        (frameControl >> 2U) & 0x03U);
    if (type != 2U) return DecodeStatus::Malformed;
    const std::uint8_t subtype = static_cast<std::uint8_t>(
        (frameControl >> 4U) & 0x0fU);
    const bool toDistribution = (frameControl & (1U << 8U)) != 0U;
    const bool fromDistribution = (frameControl & (1U << 9U)) != 0U;
    const bool protectedPayload = (frameControl & (1U << 14U)) != 0U;
    const bool ordered = (frameControl & (1U << 15U)) != 0U;
    const bool qos = (subtype & 0x08U) != 0U;
    std::size_t headerLength =
        toDistribution && fromDistribution ? kFourAddressHeaderBytes
                                           : kDataHeaderBytes;
    if (qos) headerLength += 2U;
    if (qos && ordered) headerLength += 4U;
    if (payloadLength < headerLength + kLlcSnapBytes) {
        return frame.originalLength > frame.capturedLength
                   ? DecodeStatus::Truncated
                   : DecodeStatus::Malformed;
    }
    if (protectedPayload) return DecodeStatus::Ignored;

    const std::uint8_t* llc = frame.payload + headerLength;
    if (llc[0] != 0xaaU || llc[1] != 0xaaU || llc[2] != 0x03U ||
        llc[3] != 0x00U || llc[4] != 0x00U || llc[5] != 0x00U ||
        readBig16(llc + 6U) != kEapolEtherType) {
        return DecodeStatus::Ignored;
    }
    if (toDistribution == fromDistribution) return DecodeStatus::Malformed;
    if (frame.originalLength > frame.capturedLength) {
        return DecodeStatus::Truncated;
    }

    const std::uint8_t* eapol = llc + kLlcSnapBytes;
    const std::size_t eapolAvailable = payloadLength -
        headerLength - kLlcSnapBytes;
    if (eapolAvailable < kEapolHeaderBytes) {
        return DecodeStatus::Truncated;
    }
    output->eapolVersion = eapol[0];
    if (output->eapolVersion == 0U || output->eapolVersion > 3U) {
        return DecodeStatus::Malformed;
    }
    const std::size_t bodyLength = readBig16(eapol + 2U);
    if (bodyLength > eapolAvailable - kEapolHeaderBytes) {
        return DecodeStatus::Truncated;
    }
    if (bodyLength != eapolAvailable - kEapolHeaderBytes) {
        return DecodeStatus::Malformed;
    }
    if (eapol[1] != kEapolKeyPacketType) {
        return DecodeStatus::EapolNonKey;
    }
    if (bodyLength < 1U) return DecodeStatus::Malformed;

    const std::uint8_t* key = eapol + kEapolHeaderBytes;
    output->descriptorType = key[0];
    if (toDistribution) {
        output->accessPoint = readMac(frame.payload + 4U);
        output->station = readMac(frame.payload + 10U);
    } else {
        output->station = readMac(frame.payload + 4U);
        output->accessPoint = readMac(frame.payload + 10U);
    }
    if (!validUnicastMac(output->accessPoint) ||
        !validUnicastMac(output->station) ||
        sameMac(output->accessPoint, output->station)) {
        return DecodeStatus::Malformed;
    }
    output->fromAccessPoint = fromDistribution;

    // Only the RSN descriptor has the common prefix parsed below. RC4,
    // legacy WPA and unknown descriptor layouts are retained as unsupported
    // evidence without guessing their fields.
    if (output->descriptorType != kSupportedDescriptorType) {
        return DecodeStatus::UnsupportedKey;
    }
    constexpr std::size_t kRsnCommonPrefixBytes = 45U;
    if (bodyLength < kRsnCommonPrefixBytes) return DecodeStatus::Malformed;
    output->keyInfo = readBig16(key + 1U);
    output->descriptorVersion =
        static_cast<std::uint8_t>(output->keyInfo & 0x07U);
    output->message = classifyKey(output->keyInfo);
    output->replayCounter = readBig64(key + 5U);
    std::memcpy(output->nonce.data(), key + 13U, output->nonce.size());
    if (output->descriptorVersion != kSupportedDescriptorVersion2 &&
        output->descriptorVersion != kSupportedDescriptorVersion3) {
        return DecodeStatus::UnsupportedKey;
    }
    if (bodyLength < kEapolKeyFixedBytes) return DecodeStatus::Malformed;

    const std::size_t keyDataLength = readBig16(key + kKeyDataLengthOffset);
    if (keyDataLength != bodyLength - kEapolKeyFixedBytes) {
        return DecodeStatus::Malformed;
    }
    if ((output->keyInfo & kKeyInfoEncrypted) == 0U && keyDataLength > 0U) {
        bool malformed = false;
        output->hasPmkid = findPmkidKde(
            key + kEapolKeyFixedBytes, keyDataLength, &output->pmkid,
            &malformed);
        if (malformed) return DecodeStatus::Malformed;
    }
    return output->message == WifiEapolKeyMessage::Unknown
               ? DecodeStatus::UnclassifiedKey
               : DecodeStatus::ClassifiedKey;
}

WifiAuthenticationPeer* findLatestAttempt(
    const DecodedKey& decoded, WifiAuthenticationCaptureReport* report) {
    for (std::size_t index = report->peerCount; index > 0U; --index) {
        WifiAuthenticationPeer& peer = report->peers[index - 1U];
        if (sameMac(peer.accessPoint, decoded.accessPoint) &&
            sameMac(peer.station, decoded.station)) {
            return &peer;
        }
    }
    return nullptr;
}

WifiAuthenticationPeer* addAttempt(
    const DecodedKey& decoded, WifiAuthenticationCaptureReport* report) {
    if (report->peerCount >= report->peers.size()) {
        ++report->counters.peersDropped;
        return nullptr;
    }
    WifiAuthenticationPeer& peer = report->peers[report->peerCount++];
    peer = {};
    peer.evidenceIndices.fill(WifiAuthenticationPeer::kMissingEvidence);
    peer.accessPoint = decoded.accessPoint;
    peer.station = decoded.station;
    return &peer;
}

void resetAttempt(WifiAuthenticationPeer* peer) {
    if (peer == nullptr) return;
    const std::array<std::uint8_t, kMacBytes> accessPoint = peer->accessPoint;
    const std::array<std::uint8_t, kMacBytes> station = peer->station;
    *peer = {};
    peer->evidenceIndices.fill(WifiAuthenticationPeer::kMissingEvidence);
    peer->accessPoint = accessPoint;
    peer->station = station;
}

bool anyNonzero(const std::array<std::uint8_t, 32>& value) {
    for (std::uint8_t octet : value) {
        if (octet != 0U) return true;
    }
    return false;
}

bool messageDirectionIsValid(const DecodedKey& decoded) {
    const bool expectedFromAccessPoint =
        decoded.message == WifiEapolKeyMessage::Message1 ||
        decoded.message == WifiEapolKeyMessage::Message3;
    return decoded.fromAccessPoint == expectedFromAccessPoint;
}

bool timeFollows(const WifiAuthenticationPeer& peer,
                 std::size_t previousMessageIndex,
                 std::uint64_t monotonicUs,
                 const WifiAuthenticationCaptureReport& report) {
    const std::uint8_t evidenceIndex =
        peer.evidenceIndices[previousMessageIndex];
    return evidenceIndex != WifiAuthenticationPeer::kMissingEvidence &&
        evidenceIndex < report.evidenceCount &&
        monotonicUs > report.evidence[evidenceIndex].monotonicUs;
}

void retainAttemptMessage(WifiAuthenticationPeer* peer,
                          const DecodedKey& decoded,
                          std::size_t keyMessageIndex,
                          std::uint8_t evidenceIndex) {
    peer->messageMask = static_cast<std::uint8_t>(
        peer->messageMask | (1U << keyMessageIndex));
    peer->replayCounters[keyMessageIndex] = decoded.replayCounter;
    peer->descriptorVersions[keyMessageIndex] = decoded.descriptorVersion;
    peer->evidenceIndices[keyMessageIndex] = evidenceIndex;
    if (decoded.message == WifiEapolKeyMessage::Message1) {
        peer->descriptorType = decoded.descriptorType;
        peer->authenticatorNonce = decoded.nonce;
        peer->authenticatorNonceSet = true;
    } else if (decoded.message == WifiEapolKeyMessage::Message2) {
        peer->stationNonce = decoded.nonce;
    }
}

bool applyAttemptMessage(const DecodedKey& decoded,
                         std::uint64_t monotonicUs,
                         std::uint8_t evidenceIndex,
                         WifiAuthenticationCaptureReport* report) {
    if (evidenceIndex == WifiAuthenticationPeer::kMissingEvidence ||
        !messageDirectionIsValid(decoded)) {
        return false;
    }
    WifiAuthenticationPeer* peer = findLatestAttempt(decoded, report);
    if (decoded.message == WifiEapolKeyMessage::Message1) {
        if (!anyNonzero(decoded.nonce)) return false;
        if (peer == nullptr || peer->messageMask == 0x0fU) {
            peer = addAttempt(decoded, report);
        } else {
            resetAttempt(peer);
        }
        if (peer == nullptr) return false;
        peer->sequenceConsistent = true;
        retainAttemptMessage(peer, decoded, 0U, evidenceIndex);
        return true;
    }
    if (peer == nullptr) {
        // Keep a bounded peer identity for the incomplete result, but do not
        // seed an attempt from a mid-handshake frame.
        (void)addAttempt(decoded, report);
        return false;
    }
    if (!peer->sequenceConsistent ||
        peer->descriptorType != decoded.descriptorType ||
        peer->descriptorVersions[0] != decoded.descriptorVersion) {
        return false;
    }

    switch (decoded.message) {
        case WifiEapolKeyMessage::Message2:
            if (peer->messageMask != 0x01U || !anyNonzero(decoded.nonce) ||
                decoded.replayCounter != peer->replayCounters[0] ||
                !timeFollows(*peer, 0U, monotonicUs, *report)) {
                return false;
            }
            retainAttemptMessage(peer, decoded, 1U, evidenceIndex);
            return true;
        case WifiEapolKeyMessage::Message3:
            if (peer->messageMask != 0x03U || !anyNonzero(decoded.nonce) ||
                decoded.nonce != peer->authenticatorNonce ||
                decoded.replayCounter <= peer->replayCounters[0] ||
                !timeFollows(*peer, 1U, monotonicUs, *report)) {
                if (decoded.nonce != peer->authenticatorNonce) {
                    peer->authenticatorNonceMismatch = true;
                }
                return false;
            }
            retainAttemptMessage(peer, decoded, 2U, evidenceIndex);
            return true;
        case WifiEapolKeyMessage::Message4:
            if (peer->messageMask != 0x07U ||
                decoded.replayCounter != peer->replayCounters[2] ||
                !timeFollows(*peer, 2U, monotonicUs, *report)) {
                return false;
            }
            retainAttemptMessage(peer, decoded, 3U, evidenceIndex);
            return true;
        case WifiEapolKeyMessage::Message1:
        case WifiEapolKeyMessage::Unknown:
            break;
    }
    return false;
}

std::uint8_t retainEvidence(
    const DecodedKey& decoded, const WifiFrameView& frame,
    std::size_t sourceIndex, WifiAuthenticationKeyProfile profile,
    WifiAuthenticationCaptureReport* report) {
    if (report->evidenceCount >= report->evidence.size()) {
        ++report->counters.evidenceDropped;
        return WifiAuthenticationPeer::kMissingEvidence;
    }
    const std::uint8_t evidenceIndex =
        static_cast<std::uint8_t>(report->evidenceCount);
    WifiAuthenticationEvidence& evidence =
        report->evidence[report->evidenceCount++];
    evidence.sourceFrameIndex = static_cast<std::uint16_t>(sourceIndex);
    evidence.monotonicUs = frame.monotonicUs;
    evidence.replayCounter = decoded.replayCounter;
    evidence.rssiDbm = frame.rssiDbm;
    evidence.keyInfo = decoded.keyInfo;
    evidence.channel = frame.channel;
    evidence.message = decoded.message;
    evidence.eapolVersion = decoded.eapolVersion;
    evidence.descriptorType = decoded.descriptorType;
    evidence.descriptorVersion = decoded.descriptorVersion;
    evidence.profile = profile;
    evidence.accessPoint = decoded.accessPoint;
    evidence.station = decoded.station;
    return evidenceIndex;
}

void retainPmkid(const DecodedKey& decoded, std::size_t sourceIndex,
                 std::uint64_t monotonicUs,
                 WifiAuthenticationCaptureReport* report) {
    if (!decoded.hasPmkid) return;
    for (std::size_t index = 0; index < report->pmkidCount; ++index) {
        const WifiPmkidEvidence& retained = report->pmkids[index];
        if (sameMac(retained.accessPoint, decoded.accessPoint) &&
            sameMac(retained.station, decoded.station) &&
            retained.pmkid == decoded.pmkid) {
            return;
        }
    }
    if (report->pmkidCount >= report->pmkids.size()) {
        ++report->counters.pmkidsDropped;
        return;
    }
    WifiPmkidEvidence& retained = report->pmkids[report->pmkidCount++];
    retained.sourceFrameIndex = static_cast<std::uint16_t>(sourceIndex);
    retained.monotonicUs = monotonicUs;
    retained.accessPoint = decoded.accessPoint;
    retained.station = decoded.station;
    retained.pmkid = decoded.pmkid;
}

void finalizePeers(WifiAuthenticationCaptureReport* report) {
    for (std::size_t index = 0; index < report->peerCount; ++index) {
        WifiAuthenticationPeer& peer = report->peers[index];
        if (peer.messageMask != 0x0fU) continue;
        peer.replayCountersConsistent =
            peer.replayCounters[0] == peer.replayCounters[1] &&
            peer.replayCounters[2] == peer.replayCounters[3] &&
            peer.replayCounters[2] > peer.replayCounters[0];
        peer.keyMaterialConsistent = peer.authenticatorNonceSet &&
            !peer.authenticatorNonceMismatch &&
            anyNonzero(peer.authenticatorNonce) &&
            anyNonzero(peer.stationNonce) &&
            peer.descriptorType == kSupportedDescriptorType &&
            peer.descriptorVersions[0] == peer.descriptorVersions[1] &&
            peer.descriptorVersions[0] == peer.descriptorVersions[2] &&
            peer.descriptorVersions[0] == peer.descriptorVersions[3];
        peer.complete = peer.sequenceConsistent &&
            peer.replayCountersConsistent && peer.keyMaterialConsistent;
    }
}

bool anyCompletePeer(const WifiAuthenticationCaptureReport& report) {
    for (std::size_t index = 0; index < report.peerCount; ++index) {
        if (report.peers[index].complete) return true;
    }
    return false;
}

void addUncertainty(WifiAuthenticationCaptureReport* report,
                    WifiAuthenticationUncertainty uncertainty) {
    report->uncertainty = static_cast<std::uint16_t>(
        report->uncertainty | static_cast<std::uint16_t>(uncertainty));
}

}  // namespace

const char* wifiAuthenticationCaptureOutcomeName(
    WifiAuthenticationCaptureOutcome outcome) {
    switch (outcome) {
        case WifiAuthenticationCaptureOutcome::Inconclusive:
            return "inconclusive";
        case WifiAuthenticationCaptureOutcome::Incomplete:
            return "incomplete";
        case WifiAuthenticationCaptureOutcome::Complete:
            return "complete";
    }
    return "unknown";
}

const char* wifiEapolKeyMessageName(WifiEapolKeyMessage message) {
    switch (message) {
        case WifiEapolKeyMessage::Unknown: return "unknown";
        case WifiEapolKeyMessage::Message1: return "message_1";
        case WifiEapolKeyMessage::Message2: return "message_2";
        case WifiEapolKeyMessage::Message3: return "message_3";
        case WifiEapolKeyMessage::Message4: return "message_4";
    }
    return "unknown";
}

bool analyzeWifiAuthenticationCapture(
    const WifiAuthenticationCaptureInput& input,
    WifiAuthenticationCaptureReport* output) {
    if (output == nullptr) return false;
    std::memset(output, 0, sizeof(*output));
    output->counters.captureFramesReported = input.framesReported;
    output->counters.captureFramesAccepted = input.framesAccepted;
    output->counters.captureFramesDroppedCapacity =
        input.framesDroppedCapacity;
    output->counters.captureFramesDroppedInvalid = input.framesDroppedInvalid;
    if (input.source == nullptr) {
        addUncertainty(output, WifiAuthenticationUncertaintyInvalidInput);
        return true;
    }

    const std::size_t sourceFrames = input.source->frameCount();
    output->counters.sourceFrames = static_cast<std::uint32_t>(
        std::min(sourceFrames, static_cast<std::size_t>(UINT32_MAX)));
    if (!input.captureComplete) {
        addUncertainty(output, WifiAuthenticationUncertaintyCaptureIncomplete);
    }
    const std::uint64_t accounted =
        static_cast<std::uint64_t>(input.framesAccepted) +
        input.framesDroppedCapacity + input.framesDroppedInvalid;
    if (input.framesAccepted != sourceFrames ||
        input.framesReported != accounted) {
        addUncertainty(output, WifiAuthenticationUncertaintyInvalidInput);
    }
    if (input.framesDroppedCapacity != 0U ||
        input.framesDroppedInvalid != 0U) {
        addUncertainty(output, WifiAuthenticationUncertaintyCaptureLoss);
    }
    const std::size_t inspectCount = std::min(
        sourceFrames,
        WifiAuthenticationCaptureReport::kSourceFrameInspectionCapacity);
    if (sourceFrames > inspectCount) {
        addUncertainty(output, WifiAuthenticationUncertaintyCapacity);
    }

    for (std::size_t sourceIndex = 0; sourceIndex < inspectCount;
         ++sourceIndex) {
        WifiFrameView frame{};
        if (!input.source->frameView(sourceIndex, &frame)) {
            ++output->counters.sourceReadFailures;
            addUncertainty(output, WifiAuthenticationUncertaintySourceRead);
            continue;
        }
        ++output->counters.framesRead;
        if (frame.kind == WifiFrameKind::Data) {
            ++output->counters.dataFrames;
        }
        DecodedKey decoded{};
        const DecodeStatus status = decodeKey(frame, &decoded);
        WifiAuthenticationKeyProfile profile =
            WifiAuthenticationKeyProfile::RsnWpa2;
        switch (status) {
            case DecodeStatus::Ignored:
                ++output->counters.framesIgnored;
                continue;
            case DecodeStatus::EapolNonKey:
                ++output->counters.eapolFrames;
                ++output->counters.framesIgnored;
                continue;
            case DecodeStatus::Malformed:
                ++output->counters.malformedFrames;
                addUncertainty(output,
                               WifiAuthenticationUncertaintyMalformed);
                continue;
            case DecodeStatus::Truncated:
                ++output->counters.truncatedFrames;
                addUncertainty(output,
                               WifiAuthenticationUncertaintyTruncated);
                continue;
            case DecodeStatus::UnclassifiedKey:
                ++output->counters.eapolFrames;
                ++output->counters.eapolKeyFrames;
                ++output->counters.unclassifiedKeyFrames;
                profile = WifiAuthenticationKeyProfile::Unsupported;
                addUncertainty(output,
                               WifiAuthenticationUncertaintyUnsupported);
                break;
            case DecodeStatus::UnsupportedKey:
                ++output->counters.eapolFrames;
                ++output->counters.eapolKeyFrames;
                ++output->counters.unsupportedKeyFrames;
                profile = WifiAuthenticationKeyProfile::Unsupported;
                addUncertainty(output,
                               WifiAuthenticationUncertaintyUnsupported);
                break;
            case DecodeStatus::ClassifiedKey:
                ++output->counters.eapolFrames;
                ++output->counters.eapolKeyFrames;
                ++output->counters.classifiedKeyFrames;
                break;
        }

        const std::uint8_t evidenceIndex = retainEvidence(
            decoded, frame, sourceIndex, profile, output);
        if (evidenceIndex == WifiAuthenticationPeer::kMissingEvidence) {
            addUncertainty(output, WifiAuthenticationUncertaintyCapacity);
        }
        if (status != DecodeStatus::ClassifiedKey) {
            continue;
        }
        if (!applyAttemptMessage(decoded, frame.monotonicUs, evidenceIndex,
                                 output)) {
            ++output->counters.sequenceRejected;
        }
        retainPmkid(decoded, sourceIndex, frame.monotonicUs, output);
        if (decoded.hasPmkid && output->pmkidCount == 0U) {
            addUncertainty(output, WifiAuthenticationUncertaintyCapacity);
        }
    }

    if (output->counters.peersDropped != 0U ||
        output->counters.pmkidsDropped != 0U ||
        output->counters.evidenceDropped != 0U) {
        addUncertainty(output, WifiAuthenticationUncertaintyCapacity);
    }
    finalizePeers(output);
    const bool hasEvidence = output->counters.classifiedKeyFrames != 0U ||
        output->counters.unclassifiedKeyFrames != 0U ||
        output->counters.unsupportedKeyFrames != 0U ||
        output->pmkidCount != 0U;
    if (!hasEvidence) {
        addUncertainty(output, WifiAuthenticationUncertaintyNoEvidence);
    }
    if (output->uncertainty != WifiAuthenticationUncertaintyNone) {
        output->outcome = WifiAuthenticationCaptureOutcome::Inconclusive;
    } else if (anyCompletePeer(*output)) {
        output->outcome = WifiAuthenticationCaptureOutcome::Complete;
    } else {
        output->outcome = WifiAuthenticationCaptureOutcome::Incomplete;
    }
    return true;
}

}  // namespace leshy1::services::auth
