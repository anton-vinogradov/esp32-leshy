#include "WifiAuthenticationHc22000.h"

#include <array>
#include <cstring>
#include <type_traits>

#include "services/auth/WifiAuthenticationFrameDecoder.h"

namespace leshy1::apps::auth {
namespace {

using domain::captures::WifiFrameSource;
using domain::captures::WifiFrameView;
using services::auth::WifiAuthenticationCaptureReport;
using services::auth::WifiAuthenticationDecodedKeyFrame;
using services::auth::WifiAuthenticationEvidence;
using services::auth::WifiAuthenticationFrameDecodeStatus;
using services::auth::WifiAuthenticationPeer;
using services::auth::WifiEapolKeyMessage;
using services::auth::WifiPmkidEvidence;
using storage::AuthenticationCaptureProvenance;

constexpr std::size_t kKeyMicBytes = 16U;
constexpr std::size_t kMaximumHashcatEapolBytes = 256U;
constexpr std::uint8_t kStrictM1M2MessagePair = 0x00U;

struct SerializationPlan final {
    std::array<std::uint8_t, WifiAuthenticationCaptureReport::kPmkidCapacity>
        pmkidIndices{};
    std::array<std::uint8_t, WifiAuthenticationCaptureReport::kPeerCapacity>
        peerIndices{};
    std::size_t pmkidCount = 0U;
    std::size_t peerCount = 0U;
};

static_assert(std::is_trivially_copyable_v<SerializationPlan>);
static_assert(sizeof(SerializationPlan) <= 32U);

bool anyNonzero(const std::uint8_t* value, std::size_t size) {
    if (value == nullptr) return false;
    for (std::size_t index = 0U; index < size; ++index) {
        if (value[index] != 0U) return true;
    }
    return false;
}

bool decodedMatchesEvidence(
    const WifiAuthenticationDecodedKeyFrame& decoded,
    const WifiAuthenticationEvidence& evidence,
    const WifiFrameView& frame) {
    return decoded.message == evidence.message &&
        decoded.accessPoint == evidence.accessPoint &&
        decoded.station == evidence.station &&
        decoded.replayCounter == evidence.replayCounter &&
        decoded.keyInfo == evidence.keyInfo &&
        decoded.keyMicNonzero == evidence.keyMicNonzero &&
        decoded.eapolVersion == evidence.eapolVersion &&
        decoded.descriptorType == evidence.descriptorType &&
        decoded.descriptorVersion == evidence.descriptorVersion &&
        frame.monotonicUs == evidence.monotonicUs &&
        frame.rssiDbm == evidence.rssiDbm &&
        frame.channel == evidence.channel;
}

bool readAndDecode(const WifiFrameSource& source, std::size_t index,
                   WifiFrameView* frame,
                   WifiAuthenticationDecodedKeyFrame* decoded) {
    if (frame == nullptr || decoded == nullptr ||
        !source.frameView(index, frame) || frame->payload == nullptr) {
        return false;
    }
    return services::auth::decodeWifiAuthenticationKeyFrame(
               *frame, decoded) ==
        WifiAuthenticationFrameDecodeStatus::ClassifiedKey;
}

const WifiAuthenticationEvidence* matchingPmkidEvidence(
    const WifiAuthenticationCaptureReport& report,
    const WifiPmkidEvidence& pmkid) {
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        const WifiAuthenticationEvidence& evidence = report.evidence[index];
        if (evidence.sourceFrameIndex == pmkid.sourceFrameIndex &&
            evidence.monotonicUs == pmkid.monotonicUs &&
            evidence.accessPoint == pmkid.accessPoint &&
            evidence.station == pmkid.station &&
            evidence.message == WifiEapolKeyMessage::Message1) {
            return &evidence;
        }
    }
    return nullptr;
}

bool validatePmkidRecord(const WifiAuthenticationCaptureReport& report,
                         const WifiFrameSource& source,
                         std::size_t pmkidIndex) {
    if (pmkidIndex >= report.pmkidCount) return false;
    const WifiPmkidEvidence& pmkid = report.pmkids[pmkidIndex];
    if (!anyNonzero(pmkid.pmkid.data(), pmkid.pmkid.size())) return false;
    const WifiAuthenticationEvidence* evidence =
        matchingPmkidEvidence(report, pmkid);
    if (evidence == nullptr) return false;
    WifiFrameView frame{};
    WifiAuthenticationDecodedKeyFrame decoded{};
    return readAndDecode(source, pmkid.sourceFrameIndex, &frame, &decoded) &&
        decodedMatchesEvidence(decoded, *evidence, frame) &&
        decoded.fromAccessPoint && decoded.hasPmkid &&
        decoded.pmkid == pmkid.pmkid &&
        decoded.accessPoint == pmkid.accessPoint &&
        decoded.station == pmkid.station;
}

bool peerCouldProvideStrictPair(const WifiAuthenticationPeer& peer) {
    return (peer.messageMask & 0x03U) == 0x03U &&
        peer.sequenceConsistent && peer.authenticatorNonceSet &&
        !peer.authenticatorNonceMismatch &&
        anyNonzero(peer.authenticatorNonce.data(),
                   peer.authenticatorNonce.size()) &&
        anyNonzero(peer.stationNonce.data(), peer.stationNonce.size()) &&
        peer.replayCounters[0] == peer.replayCounters[1] &&
        peer.descriptorVersions[0] == peer.descriptorVersions[1] &&
        (peer.descriptorVersions[0] ==
             services::auth::kWifiAuthenticationSupportedDescriptorVersion2 ||
         peer.descriptorVersions[0] ==
             services::auth::kWifiAuthenticationSupportedDescriptorVersion3);
}

bool validatePairRecord(const WifiAuthenticationCaptureReport& report,
                        const WifiFrameSource& source,
                        std::size_t peerIndex) {
    if (peerIndex >= report.peerCount) return false;
    const WifiAuthenticationPeer& peer = report.peers[peerIndex];
    if (!peerCouldProvideStrictPair(peer)) return false;
    const std::uint8_t message1Index = peer.evidenceIndices[0];
    const std::uint8_t message2Index = peer.evidenceIndices[1];
    if (message1Index == message2Index ||
        message1Index >= report.evidenceCount ||
        message2Index >= report.evidenceCount) {
        return false;
    }
    const WifiAuthenticationEvidence& message1 =
        report.evidence[message1Index];
    const WifiAuthenticationEvidence& message2 =
        report.evidence[message2Index];
    WifiFrameView frame1{};
    WifiFrameView frame2{};
    WifiAuthenticationDecodedKeyFrame decoded1{};
    WifiAuthenticationDecodedKeyFrame decoded2{};
    if (!readAndDecode(source, message1.sourceFrameIndex, &frame1, &decoded1) ||
        !readAndDecode(source, message2.sourceFrameIndex, &frame2, &decoded2)) {
        return false;
    }
    const std::size_t micEnd =
        static_cast<std::size_t>(decoded2.keyMicOffset) + kKeyMicBytes;
    return message1.monotonicUs < message2.monotonicUs &&
        decodedMatchesEvidence(decoded1, message1, frame1) &&
        decodedMatchesEvidence(decoded2, message2, frame2) &&
        decoded1.message == WifiEapolKeyMessage::Message1 &&
        decoded2.message == WifiEapolKeyMessage::Message2 &&
        decoded1.fromAccessPoint && !decoded2.fromAccessPoint &&
        decoded1.accessPoint == peer.accessPoint &&
        decoded1.station == peer.station &&
        decoded2.accessPoint == peer.accessPoint &&
        decoded2.station == peer.station &&
        decoded1.replayCounter == decoded2.replayCounter &&
        decoded1.nonce == peer.authenticatorNonce &&
        decoded2.nonce == peer.stationNonce && decoded2.keyMicNonzero &&
        decoded2.eapolLength <= kMaximumHashcatEapolBytes &&
        micEnd <= decoded2.eapolLength &&
        static_cast<std::size_t>(decoded2.eapolOffset) +
                decoded2.eapolLength <=
            frame2.capturedLength &&
        anyNonzero(frame2.payload + decoded2.eapolOffset +
                       decoded2.keyMicOffset,
                   kKeyMicBytes);
}

WifiAuthenticationHc22000Status buildPlan(
    const WifiAuthenticationCaptureReport& report,
    const AuthenticationCaptureProvenance& provenance,
    const WifiFrameSource& source, SerializationPlan* plan) {
    if (plan == nullptr) {
        return WifiAuthenticationHc22000Status::InvalidArgument;
    }
    *plan = {};
    const auto policy = evaluateWifiAuthenticationArtifacts(
        report, provenance, source.frameCount());
    if (!policy.standard.ready) {
        return WifiAuthenticationHc22000Status::PolicyRejected;
    }
    for (std::size_t index = 0U; index < report.pmkidCount; ++index) {
        if (!validatePmkidRecord(report, source, index)) {
            return WifiAuthenticationHc22000Status::EvidenceMismatch;
        }
        plan->pmkidIndices[plan->pmkidCount++] =
            static_cast<std::uint8_t>(index);
    }
    for (std::size_t index = 0U; index < report.peerCount; ++index) {
        if (!peerCouldProvideStrictPair(report.peers[index])) continue;
        if (!validatePairRecord(report, source, index)) {
            return WifiAuthenticationHc22000Status::EvidenceMismatch;
        }
        plan->peerIndices[plan->peerCount++] =
            static_cast<std::uint8_t>(index);
    }
    return plan->pmkidCount == 0U && plan->peerCount == 0U
        ? WifiAuthenticationHc22000Status::NoArtifact
        : WifiAuthenticationHc22000Status::Valid;
}

bool emit(WifiAuthenticationArtifactByteSink sink, void* context,
          const void* data, std::size_t size,
          WifiAuthenticationHc22000Result* result) {
    if (size == 0U) return true;
    if (sink == nullptr || data == nullptr || result == nullptr ||
        !sink(static_cast<const std::uint8_t*>(data), size, context)) {
        return false;
    }
    result->bytesWritten += size;
    return true;
}

bool emitLiteral(WifiAuthenticationArtifactByteSink sink, void* context,
                 const char* text,
                 WifiAuthenticationHc22000Result* result) {
    return text != nullptr &&
        emit(sink, context, text, std::strlen(text), result);
}

bool emitHex(WifiAuthenticationArtifactByteSink sink, void* context,
             const std::uint8_t* bytes, std::size_t size,
             std::size_t zeroOffset, std::size_t zeroLength,
             WifiAuthenticationHc22000Result* result) {
    if (bytes == nullptr && size != 0U) return false;
    constexpr char kHex[] = "0123456789abcdef";
    std::array<std::uint8_t, 64> encoded{};
    std::size_t offset = 0U;
    while (offset < size) {
        const std::size_t remaining = size - offset;
        const std::size_t chunk = remaining < encoded.size() / 2U
            ? remaining : encoded.size() / 2U;
        for (std::size_t index = 0U; index < chunk; ++index) {
            const std::size_t sourceIndex = offset + index;
            const bool zero = sourceIndex >= zeroOffset &&
                sourceIndex - zeroOffset < zeroLength;
            const std::uint8_t value = zero ? 0U : bytes[sourceIndex];
            encoded[index * 2U] = static_cast<std::uint8_t>(
                kHex[value >> 4U]);
            encoded[index * 2U + 1U] = static_cast<std::uint8_t>(
                kHex[value & 0x0fU]);
        }
        if (!emit(sink, context, encoded.data(), chunk * 2U, result)) {
            return false;
        }
        offset += chunk;
    }
    return true;
}

bool emitHex(WifiAuthenticationArtifactByteSink sink, void* context,
             const std::uint8_t* bytes, std::size_t size,
             WifiAuthenticationHc22000Result* result) {
    return emitHex(sink, context, bytes, size, size, 0U, result);
}

bool emitPmkidRecord(
    const WifiPmkidEvidence& pmkid,
    const AuthenticationCaptureProvenance& provenance,
    WifiAuthenticationArtifactByteSink sink, void* context,
    WifiAuthenticationHc22000Result* result) {
    return emitLiteral(sink, context, "WPA*01*", result) &&
        emitHex(sink, context, pmkid.pmkid.data(), pmkid.pmkid.size(),
                result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, pmkid.accessPoint.data(),
                pmkid.accessPoint.size(), result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, pmkid.station.data(), pmkid.station.size(),
                result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, provenance.ssid.data(),
                provenance.ssidLength, result) &&
        emitLiteral(sink, context, "***\n", result);
}

bool emitPairRecord(
    const WifiAuthenticationCaptureReport& report,
    const WifiAuthenticationPeer& peer,
    const AuthenticationCaptureProvenance& provenance,
    const WifiFrameSource& source,
    WifiAuthenticationArtifactByteSink sink, void* context,
    WifiAuthenticationHc22000Result* result) {
    const WifiAuthenticationEvidence& message2 =
        report.evidence[peer.evidenceIndices[1]];
    WifiFrameView frame{};
    WifiAuthenticationDecodedKeyFrame decoded{};
    if (!readAndDecode(source, message2.sourceFrameIndex, &frame, &decoded)) {
        return false;
    }
    const std::uint8_t* eapol = frame.payload + decoded.eapolOffset;
    const std::uint8_t* mic = eapol + decoded.keyMicOffset;
    constexpr std::array<std::uint8_t, 1> kPair{kStrictM1M2MessagePair};
    return emitLiteral(sink, context, "WPA*02*", result) &&
        emitHex(sink, context, mic, kKeyMicBytes, result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, peer.accessPoint.data(),
                peer.accessPoint.size(), result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, peer.station.data(), peer.station.size(),
                result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, provenance.ssid.data(),
                provenance.ssidLength, result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, peer.authenticatorNonce.data(),
                peer.authenticatorNonce.size(), result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, eapol, decoded.eapolLength,
                decoded.keyMicOffset, kKeyMicBytes, result) &&
        emitLiteral(sink, context, "*", result) &&
        emitHex(sink, context, kPair.data(), kPair.size(), result) &&
        emitLiteral(sink, context, "\n", result);
}

bool countBytes(const std::uint8_t*, std::size_t, void*) {
    return true;
}

}  // namespace

const char* wifiAuthenticationHc22000StatusName(
    WifiAuthenticationHc22000Status status) {
    switch (status) {
        case WifiAuthenticationHc22000Status::Valid: return "valid";
        case WifiAuthenticationHc22000Status::InvalidArgument:
            return "invalid_argument";
        case WifiAuthenticationHc22000Status::PolicyRejected:
            return "policy_rejected";
        case WifiAuthenticationHc22000Status::EvidenceMismatch:
            return "evidence_mismatch";
        case WifiAuthenticationHc22000Status::NoArtifact:
            return "no_artifact";
        case WifiAuthenticationHc22000Status::OutputFailed:
            return "output_failed";
    }
    return "invalid_argument";
}

WifiAuthenticationHc22000Result writeWifiAuthenticationHc22000(
    const WifiAuthenticationCaptureReport& report,
    const AuthenticationCaptureProvenance& provenance,
    const WifiFrameSource& source,
    WifiAuthenticationArtifactByteSink sink, void* context) {
    WifiAuthenticationHc22000Result result{};
    if (sink == nullptr) return result;
    SerializationPlan plan{};
    result.status = buildPlan(report, provenance, source, &plan);
    if (result.status != WifiAuthenticationHc22000Status::Valid) {
        return result;
    }
    for (std::size_t index = 0U; index < plan.pmkidCount; ++index) {
        const WifiPmkidEvidence& pmkid =
            report.pmkids[plan.pmkidIndices[index]];
        if (!emitPmkidRecord(pmkid, provenance, sink, context, &result)) {
            result.status = WifiAuthenticationHc22000Status::OutputFailed;
            return result;
        }
        ++result.recordsWritten;
        ++result.pmkidRecordsWritten;
    }
    for (std::size_t index = 0U; index < plan.peerCount; ++index) {
        const WifiAuthenticationPeer& peer =
            report.peers[plan.peerIndices[index]];
        if (!emitPairRecord(report, peer, provenance, source, sink, context,
                            &result)) {
            result.status = WifiAuthenticationHc22000Status::OutputFailed;
            return result;
        }
        ++result.recordsWritten;
        ++result.eapolRecordsWritten;
    }
    result.status = WifiAuthenticationHc22000Status::Valid;
    return result;
}

std::size_t wifiAuthenticationHc22000Size(
    const WifiAuthenticationCaptureReport& report,
    const AuthenticationCaptureProvenance& provenance,
    const WifiFrameSource& source) {
    const WifiAuthenticationHc22000Result result =
        writeWifiAuthenticationHc22000(
            report, provenance, source, countBytes, nullptr);
    return result.valid() ? result.bytesWritten : 0U;
}

}  // namespace leshy1::apps::auth
