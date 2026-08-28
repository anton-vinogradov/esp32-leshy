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
constexpr std::size_t kLlcSnapBytes = 8;
constexpr std::uint8_t kNullDataSubtype = 4U;
constexpr std::uint8_t kQosNullDataSubtype = 12U;
constexpr std::array<std::uint8_t, kLlcSnapBytes> kEapolLlcSnap{
    0xaaU, 0xaaU, 0x03U, 0x00U, 0x00U, 0x00U, 0x88U, 0x8eU};

using DecodeStatus = WifiAuthenticationFrameDecodeStatus;
using DecodedKey = WifiAuthenticationDecodedKeyFrame;

bool sameMac(const std::array<std::uint8_t, kMacBytes>& left,
             const std::array<std::uint8_t, kMacBytes>& right) {
    return left == right;
}

bool bytesMatchPrefix(const std::uint8_t* value, std::size_t valueLength,
                      const std::array<std::uint8_t, kLlcSnapBytes>& expected) {
    if (value == nullptr || valueLength > expected.size()) return false;
    for (std::size_t index = 0; index < valueLength; ++index) {
        if (value[index] != expected[index]) return false;
    }
    return true;
}

std::array<std::uint8_t, kMacBytes> readMac(const std::uint8_t* value) {
    std::array<std::uint8_t, kMacBytes> result{};
    std::memcpy(result.data(), value, result.size());
    return result;
}

DecodeStatus decodeKey(const WifiFrameView& frame, DecodedKey* output) {
    return decodeWifiAuthenticationKeyFrame(frame, output);
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
            peer.descriptorType ==
                kWifiAuthenticationSupportedDescriptorType &&
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

WifiAuthenticationIngressDisposition classifyWifiAuthenticationIngress(
    const WifiFrameView& frame,
    const std::array<std::uint8_t, 6>& targetAccessPoint) {
    using Disposition = WifiAuthenticationIngressDisposition;
    if (!validWifiAuthenticationUnicastMac(targetAccessPoint) ||
        frame.payload == nullptr ||
        frame.capturedLength == 0U) {
        return Disposition::Invalid;
    }
    if (frame.kind != WifiFrameKind::Data) return Disposition::Ignore;

    std::size_t payloadLength = frame.capturedLength;
    if (frame.fcsIncluded) {
        if (payloadLength < 4U) return Disposition::Invalid;
        payloadLength -= 4U;
    }
    if (payloadLength < kDataHeaderBytes) return Disposition::Invalid;

    const std::uint16_t frameControl = static_cast<std::uint16_t>(
        frame.payload[0] |
        (static_cast<std::uint16_t>(frame.payload[1]) << 8U));
    const std::uint8_t type = static_cast<std::uint8_t>(
        (frameControl >> 2U) & 0x03U);
    if (type != 2U) return Disposition::Invalid;
    const bool toDistribution = (frameControl & (1U << 8U)) != 0U;
    const bool fromDistribution = (frameControl & (1U << 9U)) != 0U;
    if (toDistribution == fromDistribution) return Disposition::Ignore;

    const std::array<std::uint8_t, kMacBytes> frameAccessPoint = readMac(
        frame.payload + (toDistribution ? 4U : 10U));
    if (!sameMac(frameAccessPoint, targetAccessPoint)) {
        return Disposition::Ignore;
    }

    // Once the target AP is proven, preserve malformed metadata and a partial
    // matching EAPOL envelope for the terminal analyzer. Dropping it here could
    // turn capture loss into a false clean/no-evidence result.
    if (frame.originalLength == 0U ||
        frame.capturedLength > frame.originalLength ||
        frame.monotonicUs == 0U || frame.channel < 1U || frame.channel > 14U) {
        return Disposition::Retain;
    }
    const bool protectedPayload = (frameControl & (1U << 14U)) != 0U;
    if (protectedPayload) return Disposition::Ignore;

    const std::uint8_t subtype = static_cast<std::uint8_t>(
        (frameControl >> 4U) & 0x0fU);
    const bool qos = (subtype & 0x08U) != 0U;
    const bool ordered = (frameControl & (1U << 15U)) != 0U;
    std::size_t headerLength = kDataHeaderBytes;
    if (qos) headerLength += 2U;
    if (qos && ordered) headerLength += 4U;

    const bool noDataSubtype = subtype == kNullDataSubtype ||
        subtype == kQosNullDataSubtype;
    if (noDataSubtype) {
        const bool complete = frame.originalLength == frame.capturedLength &&
            payloadLength == headerLength;
        return complete ? Disposition::Ignore : Disposition::Retain;
    }
    if (payloadLength < headerLength) return Disposition::Retain;

    const std::size_t llcAvailable = std::min(
        payloadLength - headerLength, kEapolLlcSnap.size());
    const std::uint8_t* llc = frame.payload + headerLength;
    if (!bytesMatchPrefix(llc, llcAvailable, kEapolLlcSnap)) {
        return Disposition::Ignore;
    }
    return Disposition::Retain;
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
