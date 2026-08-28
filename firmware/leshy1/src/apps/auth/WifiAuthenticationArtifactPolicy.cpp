#include "WifiAuthenticationArtifactPolicy.h"

#include <array>
#include <limits>
#include <type_traits>

namespace leshy1::apps::auth {
namespace {

using namespace services::auth;

constexpr std::uint8_t kMessage1Mask = 1U << 0U;
constexpr std::uint8_t kMessage2Mask = 1U << 1U;
constexpr std::uint8_t kPairMask = kMessage1Mask | kMessage2Mask;
constexpr std::uint16_t kKeyInfoPairwise = 1U << 3U;
constexpr std::uint16_t kKeyInfoInstall = 1U << 6U;
constexpr std::uint16_t kKeyInfoAck = 1U << 7U;
constexpr std::uint16_t kKeyInfoMic = 1U << 8U;
constexpr std::uint16_t kKeyInfoSecure = 1U << 9U;
constexpr std::uint16_t kKeyInfoError = 1U << 10U;
constexpr std::uint16_t kKeyInfoRequest = 1U << 11U;
constexpr std::uint16_t kKeyInfoSmk = 1U << 13U;
constexpr std::uint16_t kKeyInfoReserved = 3U << 14U;
constexpr std::uint16_t kKeyInfoRsnKeyIndex = 3U << 4U;

static_assert(
    std::is_trivially_copyable_v<WifiAuthenticationArtifactPolicyResult>,
    "authentication artifact policy result must remain allocation-free");
static_assert(sizeof(WifiAuthenticationArtifactPolicyResult) <= 8U,
              "authentication artifact policy result exceeded its bound");

bool cleanCaptureAccounting(
    const WifiAuthenticationCaptureReport& report,
    const storage::AuthenticationCaptureProvenance& provenance,
    std::size_t persistedFrameCount) {
    if (persistedFrameCount >
        static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max())) {
        return false;
    }
    const std::uint64_t accounted =
        static_cast<std::uint64_t>(provenance.framesAccepted) +
        provenance.framesDroppedCapacity + provenance.framesDroppedInvalid;
    if (accounted != provenance.framesReported ||
        static_cast<std::size_t>(provenance.framesAccepted) !=
            persistedFrameCount) {
        return false;
    }
    const WifiAuthenticationCaptureCounters& counters = report.counters;
    return counters.captureFramesReported == provenance.framesReported &&
        counters.captureFramesAccepted == provenance.framesAccepted &&
        counters.captureFramesDroppedCapacity ==
            provenance.framesDroppedCapacity &&
        counters.captureFramesDroppedInvalid ==
            provenance.framesDroppedInvalid &&
        static_cast<std::size_t>(counters.sourceFrames) ==
            persistedFrameCount;
}

bool anyNonzero(const std::array<std::uint8_t, 16>& value) {
    for (std::uint8_t octet : value) {
        if (octet != 0U) return true;
    }
    return false;
}

bool anyNonzero(const std::array<std::uint8_t, 32>& value) {
    for (std::uint8_t octet : value) {
        if (octet != 0U) return true;
    }
    return false;
}

bool supportedDescriptorVersion(std::uint8_t version) {
    return version == kWifiAuthenticationSupportedDescriptorVersion2 ||
        version == kWifiAuthenticationSupportedDescriptorVersion3;
}

bool validMessageMask(std::uint8_t mask) {
    return mask == 0U || mask == 0x01U || mask == 0x03U ||
        mask == 0x07U || mask == 0x0fU;
}

bool validMessage(WifiEapolKeyMessage message) {
    return static_cast<std::uint8_t>(message) <=
        static_cast<std::uint8_t>(WifiEapolKeyMessage::Message4);
}

bool validProfile(WifiAuthenticationKeyProfile profile) {
    return static_cast<std::uint8_t>(profile) <=
        static_cast<std::uint8_t>(WifiAuthenticationKeyProfile::RsnWpa2);
}

bool validOutcome(WifiAuthenticationCaptureOutcome outcome) {
    return static_cast<std::uint8_t>(outcome) <=
        static_cast<std::uint8_t>(WifiAuthenticationCaptureOutcome::Complete);
}

bool validPeerIdentity(const std::array<std::uint8_t, 6>& accessPoint,
                       const std::array<std::uint8_t, 6>& station) {
    return validWifiAuthenticationUnicastMac(accessPoint) &&
        validWifiAuthenticationUnicastMac(station) &&
        accessPoint != station;
}

bool peerCompletionIsCoherent(const WifiAuthenticationPeer& peer) {
    if ((peer.messageMask == 0U && peer.sequenceConsistent) ||
        (peer.messageMask != 0U && !peer.sequenceConsistent)) {
        return false;
    }
    const bool full = peer.messageMask == 0x0fU;
    const bool replayCountersConsistent = full &&
        peer.replayCounters[0] == peer.replayCounters[1] &&
        peer.replayCounters[2] == peer.replayCounters[3] &&
        peer.replayCounters[2] > peer.replayCounters[0];
    const bool keyMaterialConsistent = full &&
        peer.authenticatorNonceSet && !peer.authenticatorNonceMismatch &&
        anyNonzero(peer.authenticatorNonce) && anyNonzero(peer.stationNonce) &&
        peer.descriptorType == kWifiAuthenticationSupportedDescriptorType &&
        peer.descriptorVersions[0] == peer.descriptorVersions[1] &&
        peer.descriptorVersions[0] == peer.descriptorVersions[2] &&
        peer.descriptorVersions[0] == peer.descriptorVersions[3];
    const bool complete = peer.sequenceConsistent &&
        replayCountersConsistent && keyMaterialConsistent;
    return peer.replayCountersConsistent == replayCountersConsistent &&
        peer.keyMaterialConsistent == keyMaterialConsistent &&
        peer.complete == complete;
}

bool reportOutcomeIsCoherent(const WifiAuthenticationCaptureReport& report) {
    if (report.uncertainty != WifiAuthenticationUncertaintyNone) {
        return report.outcome ==
            WifiAuthenticationCaptureOutcome::Inconclusive;
    }
    if (report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive) {
        return false;
    }
    bool anyCompletePeer = false;
    for (std::size_t index = 0U; index < report.peerCount; ++index) {
        anyCompletePeer = anyCompletePeer || report.peers[index].complete;
    }
    const bool hasEvidence = report.counters.classifiedKeyFrames != 0U ||
        report.counters.unclassifiedKeyFrames != 0U ||
        report.counters.unsupportedKeyFrames != 0U ||
        report.pmkidCount != 0U;
    if (!hasEvidence) return false;
    return report.outcome ==
        (anyCompletePeer ? WifiAuthenticationCaptureOutcome::Complete
                         : WifiAuthenticationCaptureOutcome::Incomplete);
}

bool reportShapeValid(const WifiAuthenticationCaptureReport& report,
                      std::size_t persistedFrameCount) {
    if (!validOutcome(report.outcome) ||
        report.evidenceCount > report.evidence.size() ||
        report.peerCount > report.peers.size() ||
        report.pmkidCount > report.pmkids.size() ||
        report.evidenceCount > persistedFrameCount) {
        return false;
    }
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        const WifiAuthenticationEvidence& evidence = report.evidence[index];
        if (evidence.sourceFrameIndex >= persistedFrameCount ||
            evidence.monotonicUs == 0U || evidence.channel < 1U ||
            evidence.channel > 14U || !validMessage(evidence.message) ||
            !validProfile(evidence.profile) ||
            !validPeerIdentity(evidence.accessPoint, evidence.station)) {
            return false;
        }
    }
    for (std::size_t index = 0U; index < report.peerCount; ++index) {
        const WifiAuthenticationPeer& peer = report.peers[index];
        if (!validMessageMask(peer.messageMask) ||
            !validPeerIdentity(peer.accessPoint, peer.station) ||
            !peerCompletionIsCoherent(peer) ||
            (peer.messageMask != 0U &&
             peer.descriptorType !=
                 kWifiAuthenticationSupportedDescriptorType)) {
            return false;
        }
        for (std::size_t messageIndex = 0U; messageIndex < 4U;
             ++messageIndex) {
            const bool retained =
                (peer.messageMask & (1U << messageIndex)) != 0U;
            const std::uint8_t evidenceIndex =
                peer.evidenceIndices[messageIndex];
            if (retained) {
                if (evidenceIndex >= report.evidenceCount) return false;
                const WifiAuthenticationEvidence& evidence =
                    report.evidence[evidenceIndex];
                const auto expectedMessage =
                    static_cast<WifiEapolKeyMessage>(messageIndex + 1U);
                if (evidence.message != expectedMessage ||
                    evidence.accessPoint != peer.accessPoint ||
                    evidence.station != peer.station ||
                    evidence.profile !=
                        WifiAuthenticationKeyProfile::RsnWpa2 ||
                    evidence.replayCounter !=
                        peer.replayCounters[messageIndex] ||
                    evidence.descriptorType != peer.descriptorType ||
                    evidence.descriptorVersion !=
                        peer.descriptorVersions[messageIndex] ||
                    !supportedDescriptorVersion(
                        peer.descriptorVersions[messageIndex])) {
                    return false;
                }
                for (std::size_t previous = 0U; previous < messageIndex;
                     ++previous) {
                    if ((peer.messageMask & (1U << previous)) != 0U &&
                        peer.evidenceIndices[previous] == evidenceIndex) {
                        return false;
                    }
                }
            } else if (evidenceIndex !=
                       WifiAuthenticationPeer::kMissingEvidence) {
                return false;
            }
        }
    }
    for (std::size_t index = 0U; index < report.pmkidCount; ++index) {
        const WifiPmkidEvidence& pmkid = report.pmkids[index];
        if (pmkid.sourceFrameIndex >= persistedFrameCount ||
            pmkid.monotonicUs == 0U ||
            !validPeerIdentity(pmkid.accessPoint, pmkid.station)) {
            return false;
        }
    }
    return reportOutcomeIsCoherent(report);
}

bool uncertaintyFreeReportIsConsistent(
    const WifiAuthenticationCaptureReport& report) {
    const WifiAuthenticationCaptureCounters& counters = report.counters;
    const std::uint64_t classified =
        static_cast<std::uint64_t>(counters.classifiedKeyFrames) +
        counters.unclassifiedKeyFrames + counters.unsupportedKeyFrames;
    return counters.captureFramesDroppedCapacity == 0U &&
        counters.captureFramesDroppedInvalid == 0U &&
        counters.sourceReadFailures == 0U &&
        counters.malformedFrames == 0U && counters.truncatedFrames == 0U &&
        counters.evidenceDropped == 0U && counters.peersDropped == 0U &&
        counters.pmkidsDropped == 0U &&
        counters.unsupportedKeyFrames == 0U &&
        counters.unclassifiedKeyFrames == 0U &&
        counters.framesRead == counters.sourceFrames &&
        counters.dataFrames <= counters.framesRead &&
        counters.eapolFrames <= counters.dataFrames &&
        counters.eapolKeyFrames <= counters.eapolFrames &&
        classified == counters.eapolKeyFrames &&
        classified == report.evidenceCount &&
        report.pmkidCount <= counters.classifiedKeyFrames;
}

bool evidenceTargetsMatch(
    const WifiAuthenticationCaptureReport& report,
    const std::array<std::uint8_t, 6>& target) {
    if (!validWifiAuthenticationUnicastMac(target)) return false;
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        if (report.evidence[index].accessPoint != target) return false;
    }
    for (std::size_t index = 0U; index < report.peerCount; ++index) {
        if (report.peers[index].accessPoint != target) return false;
    }
    for (std::size_t index = 0U; index < report.pmkidCount; ++index) {
        if (report.pmkids[index].accessPoint != target) return false;
    }
    return true;
}

bool keyInfoMatches(WifiEapolKeyMessage message, std::uint16_t keyInfo) {
    if ((keyInfo & kKeyInfoPairwise) == 0U ||
        (keyInfo & (kKeyInfoError | kKeyInfoRequest | kKeyInfoSmk |
                    kKeyInfoReserved | kKeyInfoRsnKeyIndex)) != 0U) {
        return false;
    }
    const bool install = (keyInfo & kKeyInfoInstall) != 0U;
    const bool ack = (keyInfo & kKeyInfoAck) != 0U;
    const bool mic = (keyInfo & kKeyInfoMic) != 0U;
    const bool secure = (keyInfo & kKeyInfoSecure) != 0U;
    if (message == WifiEapolKeyMessage::Message1) {
        return ack && !mic && !install && !secure;
    }
    if (message == WifiEapolKeyMessage::Message2) {
        return !ack && mic && !install && !secure;
    }
    return false;
}

bool evidenceMatchesPmkid(const WifiAuthenticationEvidence& evidence,
                          const WifiPmkidEvidence& pmkid) {
    return evidence.sourceFrameIndex == pmkid.sourceFrameIndex &&
        evidence.monotonicUs == pmkid.monotonicUs &&
        evidence.accessPoint == pmkid.accessPoint &&
        evidence.station == pmkid.station &&
        evidence.message == WifiEapolKeyMessage::Message1 &&
        evidence.profile == WifiAuthenticationKeyProfile::RsnWpa2 &&
        evidence.descriptorType ==
            kWifiAuthenticationSupportedDescriptorType &&
        supportedDescriptorVersion(evidence.descriptorVersion) &&
        keyInfoMatches(evidence.message, evidence.keyInfo);
}

bool hasValidatedPmkid(const WifiAuthenticationCaptureReport& report) {
    for (std::size_t pmkidIndex = 0U; pmkidIndex < report.pmkidCount;
         ++pmkidIndex) {
        const WifiPmkidEvidence& pmkid = report.pmkids[pmkidIndex];
        if (!anyNonzero(pmkid.pmkid)) continue;
        for (std::size_t evidenceIndex = 0U;
             evidenceIndex < report.evidenceCount; ++evidenceIndex) {
            if (evidenceMatchesPmkid(report.evidence[evidenceIndex], pmkid)) {
                return true;
            }
        }
    }
    return false;
}

bool evidenceMatchesPairMember(
    const WifiAuthenticationEvidence& evidence,
    const WifiAuthenticationPeer& peer, WifiEapolKeyMessage message,
    std::uint64_t replayCounter, std::uint8_t descriptorVersion) {
    return evidence.accessPoint == peer.accessPoint &&
        evidence.station == peer.station && evidence.message == message &&
        evidence.profile == WifiAuthenticationKeyProfile::RsnWpa2 &&
        evidence.replayCounter == replayCounter &&
        evidence.descriptorType == peer.descriptorType &&
        evidence.descriptorVersion == descriptorVersion &&
        keyInfoMatches(message, evidence.keyInfo);
}

bool hasStrictMessagePair(const WifiAuthenticationCaptureReport& report) {
    for (std::size_t peerIndex = 0U; peerIndex < report.peerCount;
         ++peerIndex) {
        const WifiAuthenticationPeer& peer = report.peers[peerIndex];
        if ((peer.messageMask & kPairMask) != kPairMask ||
            !peer.sequenceConsistent || !peer.authenticatorNonceSet ||
            peer.authenticatorNonceMismatch ||
            !anyNonzero(peer.authenticatorNonce) ||
            !anyNonzero(peer.stationNonce) ||
            peer.descriptorType !=
                kWifiAuthenticationSupportedDescriptorType ||
            peer.descriptorVersions[0] != peer.descriptorVersions[1] ||
            !supportedDescriptorVersion(peer.descriptorVersions[0]) ||
            peer.replayCounters[0] != peer.replayCounters[1]) {
            continue;
        }
        const std::uint8_t message1Index = peer.evidenceIndices[0];
        const std::uint8_t message2Index = peer.evidenceIndices[1];
        if (message1Index == message2Index ||
            message1Index >= report.evidenceCount ||
            message2Index >= report.evidenceCount) {
            continue;
        }
        const WifiAuthenticationEvidence& message1 =
            report.evidence[message1Index];
        const WifiAuthenticationEvidence& message2 =
            report.evidence[message2Index];
        if (message2.monotonicUs <= message1.monotonicUs ||
            !evidenceMatchesPairMember(
                message1, peer, WifiEapolKeyMessage::Message1,
                peer.replayCounters[0], peer.descriptorVersions[0]) ||
            !evidenceMatchesPairMember(
                message2, peer, WifiEapolKeyMessage::Message2,
                peer.replayCounters[1], peer.descriptorVersions[1])) {
            continue;
        }
        // The analyzer only places an evidence index into an attempt after its
        // AP/station direction and strict M1 -> M2 sequence have passed.
        return true;
    }
    return false;
}

}  // namespace

WifiAuthenticationArtifactPolicyResult evaluateWifiAuthenticationArtifacts(
    const WifiAuthenticationCaptureReport& report,
    const storage::AuthenticationCaptureProvenance& provenance,
    std::size_t persistedFrameCount) {
    using PcapReason = WifiAuthenticationPcapAvailabilityReason;
    using StandardReason = WifiAuthenticationStandardArtifactReason;
    WifiAuthenticationArtifactPolicyResult result{};
    result.outcome = report.outcome;

    if (!cleanCaptureAccounting(report, provenance, persistedFrameCount)) {
        result.pcap.reason = PcapReason::AccountingMismatch;
    } else if (persistedFrameCount == 0U) {
        result.pcap.reason = PcapReason::NoPersistedFrames;
    } else {
        result.pcap.available = true;
        result.pcap.reason = PcapReason::Available;
    }

    if (!result.pcap.available) {
        result.standard.reason = StandardReason::PcapUnavailable;
        return result;
    }
    if (!reportShapeValid(report, persistedFrameCount)) {
        result.standard.reason = StandardReason::InvalidReport;
        return result;
    }
    if (report.uncertainty != WifiAuthenticationUncertaintyNone) {
        result.standard.reason = StandardReason::CaptureUncertain;
        return result;
    }
    if (!uncertaintyFreeReportIsConsistent(report)) {
        result.standard.reason = StandardReason::InvalidReport;
        return result;
    }
    if (provenance.purpose !=
        storage::AuthenticationCapturePurpose::Authentication) {
        result.standard.reason = StandardReason::PurposeNotAuthentication;
        return result;
    }
    if (!provenance.ssidKnown) {
        result.standard.reason = StandardReason::SsidUnavailable;
        return result;
    }
    if (provenance.ssidLength == 0U ||
        provenance.ssidLength > provenance.ssid.size()) {
        result.standard.reason = StandardReason::SsidInvalid;
        return result;
    }
    if (!evidenceTargetsMatch(report, provenance.targetBssid)) {
        result.standard.reason = StandardReason::TargetMismatch;
        return result;
    }
    if (hasValidatedPmkid(report)) {
        result.standard.ready = true;
        result.standard.reason = StandardReason::ReadyPmkid;
        return result;
    }
    if (hasStrictMessagePair(report)) {
        result.standard.ready = true;
        result.standard.reason = StandardReason::ReadyMessagePair;
        return result;
    }
    result.standard.reason = StandardReason::NoValidatedEvidence;
    return result;
}

}  // namespace leshy1::apps::auth
