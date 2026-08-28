#include <array>
#include <cstdio>
#include <cstdlib>
#include <type_traits>

#include "apps/auth/WifiAuthenticationArtifactPolicy.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using namespace leshy1::apps::auth;
using namespace leshy1::services::auth;
using leshy1::storage::AuthenticationCaptureProvenance;
using leshy1::storage::AuthenticationCapturePurpose;

constexpr std::array<std::uint8_t, 6> kAccessPoint{
    0x02U, 0x11U, 0x22U, 0x33U, 0x44U, 0x55U};
constexpr std::array<std::uint8_t, 6> kOtherAccessPoint{
    0x02U, 0xaaU, 0xbbU, 0xccU, 0xddU, 0xeeU};
constexpr std::array<std::uint8_t, 6> kStation{
    0x06U, 0x10U, 0x20U, 0x30U, 0x40U, 0x50U};
constexpr std::uint16_t kMessage1KeyInfo =
    (1U << 3U) | (1U << 7U) | 2U;
constexpr std::uint16_t kMessage2KeyInfo =
    (1U << 3U) | (1U << 8U) | 2U;
constexpr std::uint16_t kMessage3KeyInfo =
    (1U << 3U) | (1U << 6U) | (1U << 7U) | (1U << 8U) |
    (1U << 9U) | 2U;
constexpr std::uint16_t kMessage4KeyInfo =
    (1U << 3U) | (1U << 8U) | (1U << 9U) | 2U;

AuthenticationCaptureProvenance provenanceFixture(
    std::uint32_t accepted = 2U, std::uint32_t droppedCapacity = 0U,
    std::uint32_t droppedInvalid = 0U) {
    AuthenticationCaptureProvenance provenance{};
    provenance.purpose = AuthenticationCapturePurpose::Authentication;
    provenance.targetBssid = kAccessPoint;
    provenance.ssidKnown = true;
    provenance.ssidLength = 4U;
    provenance.ssid[0] = 'A';
    provenance.ssid[1] = 0U;
    provenance.ssid[2] = 'P';
    provenance.ssid[3] = '1';
    provenance.framesAccepted = accepted;
    provenance.framesDroppedCapacity = droppedCapacity;
    provenance.framesDroppedInvalid = droppedInvalid;
    provenance.framesReported = accepted + droppedCapacity + droppedInvalid;
    return provenance;
}

void setAccounting(WifiAuthenticationCaptureReport* report,
                   const AuthenticationCaptureProvenance& provenance) {
    CHECK(report != nullptr);
    report->counters.sourceFrames = provenance.framesAccepted;
    report->counters.captureFramesReported = provenance.framesReported;
    report->counters.captureFramesAccepted = provenance.framesAccepted;
    report->counters.captureFramesDroppedCapacity =
        provenance.framesDroppedCapacity;
    report->counters.captureFramesDroppedInvalid =
        provenance.framesDroppedInvalid;
}

void setAuthenticationCounters(WifiAuthenticationCaptureReport* report,
                               std::uint32_t classifiedKeyFrames) {
    CHECK(report != nullptr);
    report->counters.framesRead = report->counters.sourceFrames;
    report->counters.dataFrames = classifiedKeyFrames;
    report->counters.eapolFrames = classifiedKeyFrames;
    report->counters.eapolKeyFrames = classifiedKeyFrames;
    report->counters.classifiedKeyFrames = classifiedKeyFrames;
}

WifiAuthenticationEvidence evidenceFixture(
    WifiEapolKeyMessage message, std::uint8_t sourceFrameIndex,
    std::uint64_t monotonicUs, std::uint64_t replayCounter) {
    WifiAuthenticationEvidence evidence{};
    evidence.monotonicUs = monotonicUs;
    evidence.replayCounter = replayCounter;
    evidence.sourceFrameIndex = sourceFrameIndex;
    evidence.rssiDbm = -42;
    switch (message) {
        case WifiEapolKeyMessage::Message1:
            evidence.keyInfo = kMessage1KeyInfo;
            break;
        case WifiEapolKeyMessage::Message2:
            evidence.keyInfo = kMessage2KeyInfo;
            break;
        case WifiEapolKeyMessage::Message3:
            evidence.keyInfo = kMessage3KeyInfo;
            break;
        case WifiEapolKeyMessage::Message4:
            evidence.keyInfo = kMessage4KeyInfo;
            break;
        case WifiEapolKeyMessage::Unknown:
            break;
    }
    evidence.channel = 6U;
    evidence.message = message;
    evidence.eapolVersion = 2U;
    evidence.descriptorType = kWifiAuthenticationSupportedDescriptorType;
    evidence.descriptorVersion =
        kWifiAuthenticationSupportedDescriptorVersion2;
    evidence.profile = WifiAuthenticationKeyProfile::RsnWpa2;
    evidence.keyMicNonzero =
        message == WifiEapolKeyMessage::Message2 ||
        message == WifiEapolKeyMessage::Message3 ||
        message == WifiEapolKeyMessage::Message4;
    evidence.accessPoint = kAccessPoint;
    evidence.station = kStation;
    return evidence;
}

WifiAuthenticationCaptureReport strictPairReport() {
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Incomplete;
    const AuthenticationCaptureProvenance provenance = provenanceFixture();
    setAccounting(&report, provenance);
    setAuthenticationCounters(&report, 2U);
    report.evidenceCount = 2U;
    report.evidence[0] = evidenceFixture(
        WifiEapolKeyMessage::Message1, 0U, 1000U, 7U);
    report.evidence[1] = evidenceFixture(
        WifiEapolKeyMessage::Message2, 1U, 2000U, 7U);
    report.peerCount = 1U;
    WifiAuthenticationPeer& peer = report.peers[0];
    peer.accessPoint = kAccessPoint;
    peer.station = kStation;
    peer.messageMask = 0x03U;
    peer.replayCounters[0] = 7U;
    peer.replayCounters[1] = 7U;
    peer.descriptorVersions[0] =
        kWifiAuthenticationSupportedDescriptorVersion2;
    peer.descriptorVersions[1] =
        kWifiAuthenticationSupportedDescriptorVersion2;
    peer.evidenceIndices[0] = 0U;
    peer.evidenceIndices[1] = 1U;
    peer.descriptorType = kWifiAuthenticationSupportedDescriptorType;
    peer.authenticatorNonceSet = true;
    peer.sequenceConsistent = true;
    peer.authenticatorNonce[0] = 0x11U;
    peer.stationNonce[0] = 0x22U;
    return report;
}

WifiAuthenticationCaptureReport pmkidReport() {
    const AuthenticationCaptureProvenance provenance = provenanceFixture(1U);
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Incomplete;
    setAccounting(&report, provenance);
    setAuthenticationCounters(&report, 1U);
    report.evidenceCount = 1U;
    report.evidence[0] = evidenceFixture(
        WifiEapolKeyMessage::Message1, 0U, 1000U, 9U);
    report.pmkidCount = 1U;
    report.pmkids[0].sourceFrameIndex = 0U;
    report.pmkids[0].monotonicUs = 1000U;
    report.pmkids[0].accessPoint = kAccessPoint;
    report.pmkids[0].station = kStation;
    report.pmkids[0].pmkid[0] = 0x5aU;
    return report;
}

WifiAuthenticationCaptureReport completeReport() {
    WifiAuthenticationCaptureReport report = strictPairReport();
    const AuthenticationCaptureProvenance provenance = provenanceFixture(4U);
    setAccounting(&report, provenance);
    setAuthenticationCounters(&report, 4U);
    report.outcome = WifiAuthenticationCaptureOutcome::Complete;
    report.evidenceCount = 4U;
    report.evidence[2] = evidenceFixture(
        WifiEapolKeyMessage::Message3, 2U, 3000U, 8U);
    report.evidence[3] = evidenceFixture(
        WifiEapolKeyMessage::Message4, 3U, 4000U, 8U);
    WifiAuthenticationPeer& peer = report.peers[0];
    peer.messageMask = 0x0fU;
    peer.replayCounters[2] = 8U;
    peer.replayCounters[3] = 8U;
    peer.descriptorVersions[2] =
        kWifiAuthenticationSupportedDescriptorVersion2;
    peer.descriptorVersions[3] =
        kWifiAuthenticationSupportedDescriptorVersion2;
    peer.evidenceIndices[2] = 2U;
    peer.evidenceIndices[3] = 3U;
    peer.replayCountersConsistent = true;
    peer.keyMaterialConsistent = true;
    peer.complete = true;
    return report;
}

void expectRejectedPair(
    const WifiAuthenticationCaptureReport& report,
    WifiAuthenticationStandardArtifactReason expectedReason =
        WifiAuthenticationStandardArtifactReason::NoValidatedEvidence) {
    const AuthenticationCaptureProvenance provenance = provenanceFixture();
    const auto result = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(result.pcap.available);
    CHECK(!result.standard.ready);
    CHECK(result.standard.reason == expectedReason);
}

void testPcapNeedsCleanNonemptyPersistedAccounting() {
    AuthenticationCaptureProvenance provenance = provenanceFixture(1U);
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Inconclusive;
    report.uncertainty = static_cast<std::uint16_t>(
        WifiAuthenticationUncertaintyNoEvidence);
    setAccounting(&report, provenance);

    auto result = evaluateWifiAuthenticationArtifacts(report, provenance, 1U);
    CHECK(result.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(result.pcap.available);
    CHECK(result.pcap.reason ==
          WifiAuthenticationPcapAvailabilityReason::Available);
    CHECK(!result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::CaptureUncertain);

    provenance = provenanceFixture(0U);
    report = {};
    setAccounting(&report, provenance);
    result = evaluateWifiAuthenticationArtifacts(report, provenance, 0U);
    CHECK(!result.pcap.available);
    CHECK(result.pcap.reason ==
          WifiAuthenticationPcapAvailabilityReason::NoPersistedFrames);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::PcapUnavailable);

    provenance = provenanceFixture(1U);
    report = {};
    setAccounting(&report, provenance);
    result = evaluateWifiAuthenticationArtifacts(report, provenance, 2U);
    CHECK(!result.pcap.available);
    CHECK(result.pcap.reason ==
          WifiAuthenticationPcapAvailabilityReason::AccountingMismatch);

    report = {};
    setAccounting(&report, provenance);
    ++report.counters.captureFramesReported;
    result = evaluateWifiAuthenticationArtifacts(report, provenance, 1U);
    CHECK(!result.pcap.available);
    CHECK(result.pcap.reason ==
          WifiAuthenticationPcapAvailabilityReason::AccountingMismatch);

    report = {};
    setAccounting(&report, provenance);
    provenance.framesReported = 2U;
    result = evaluateWifiAuthenticationArtifacts(report, provenance, 1U);
    CHECK(!result.pcap.available);
    CHECK(result.pcap.reason ==
          WifiAuthenticationPcapAvailabilityReason::AccountingMismatch);
}

void testPcapMayPreserveHonestLossWhileStandardFailsClosed() {
    const AuthenticationCaptureProvenance provenance =
        provenanceFixture(2U, 1U, 1U);
    WifiAuthenticationCaptureReport report = strictPairReport();
    setAccounting(&report, provenance);
    report.outcome = WifiAuthenticationCaptureOutcome::Inconclusive;
    report.uncertainty = static_cast<std::uint16_t>(
        WifiAuthenticationUncertaintyCaptureLoss);
    const auto result = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(result.pcap.available);
    CHECK(!result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::CaptureUncertain);
}

void testValidatedPmkidIsReadyWithoutChangingIncompleteOutcome() {
    const AuthenticationCaptureProvenance provenance = provenanceFixture(1U);
    const WifiAuthenticationCaptureReport report = pmkidReport();
    const auto result = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(result.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(result.pcap.available);
    CHECK(result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::ReadyPmkid);

    WifiAuthenticationCaptureReport invalid = report;
    invalid.pmkids[0].pmkid.fill(0U);
    auto rejected = evaluateWifiAuthenticationArtifacts(
        invalid, provenance, provenance.framesAccepted);
    CHECK(!rejected.standard.ready);
    CHECK(rejected.standard.reason ==
          WifiAuthenticationStandardArtifactReason::NoValidatedEvidence);

    invalid = report;
    ++invalid.pmkids[0].monotonicUs;
    rejected = evaluateWifiAuthenticationArtifacts(
        invalid, provenance, provenance.framesAccepted);
    CHECK(!rejected.standard.ready);
    CHECK(rejected.standard.reason ==
          WifiAuthenticationStandardArtifactReason::NoValidatedEvidence);

    invalid = report;
    invalid.evidence[0].profile = WifiAuthenticationKeyProfile::Unsupported;
    rejected = evaluateWifiAuthenticationArtifacts(
        invalid, provenance, provenance.framesAccepted);
    CHECK(!rejected.standard.ready);
    CHECK(rejected.standard.reason ==
          WifiAuthenticationStandardArtifactReason::NoValidatedEvidence);
}

void testStrictM1M2PairIsReadyForCoherentIncompleteOutcome() {
    const AuthenticationCaptureProvenance provenance = provenanceFixture();
    WifiAuthenticationCaptureReport report = strictPairReport();
    auto result = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(result.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::ReadyMessagePair);

    report.outcome = WifiAuthenticationCaptureOutcome::Inconclusive;
    result = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(result.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(!result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::InvalidReport);
}

void testCompleteOutcomeAndPeerFlagsMustBeCoherent() {
    const AuthenticationCaptureProvenance provenance = provenanceFixture(4U);
    const WifiAuthenticationCaptureReport report = completeReport();
    auto result = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(result.outcome == WifiAuthenticationCaptureOutcome::Complete);
    CHECK(result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::ReadyMessagePair);

    WifiAuthenticationCaptureReport invalid = report;
    invalid.peers[0].complete = false;
    result = evaluateWifiAuthenticationArtifacts(
        invalid, provenance, provenance.framesAccepted);
    CHECK(!result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::InvalidReport);

    invalid = report;
    invalid.outcome = WifiAuthenticationCaptureOutcome::Incomplete;
    result = evaluateWifiAuthenticationArtifacts(
        invalid, provenance, provenance.framesAccepted);
    CHECK(!result.standard.ready);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::InvalidReport);
}

void testStrictPairRejectsEveryRequiredInvariant() {
    WifiAuthenticationCaptureReport report = strictPairReport();
    report.peers[0].messageMask = 0x01U;
    report.peers[0].evidenceIndices[1] =
        WifiAuthenticationPeer::kMissingEvidence;
    expectRejectedPair(report);

    report = strictPairReport();
    report.peers[0].sequenceConsistent = false;
    expectRejectedPair(
        report, WifiAuthenticationStandardArtifactReason::InvalidReport);

    report = strictPairReport();
    ++report.peers[0].replayCounters[1];
    expectRejectedPair(
        report, WifiAuthenticationStandardArtifactReason::InvalidReport);

    report = strictPairReport();
    report.evidence[1].monotonicUs = report.evidence[0].monotonicUs;
    expectRejectedPair(report);

    report = strictPairReport();
    report.evidence[1].profile = WifiAuthenticationKeyProfile::Unsupported;
    expectRejectedPair(
        report, WifiAuthenticationStandardArtifactReason::InvalidReport);

    report = strictPairReport();
    report.peers[0].stationNonce.fill(0U);
    expectRejectedPair(report);

    report = strictPairReport();
    report.peers[0].descriptorVersions[1] =
        kWifiAuthenticationSupportedDescriptorVersion3;
    expectRejectedPair(
        report, WifiAuthenticationStandardArtifactReason::InvalidReport);

    report = strictPairReport();
    report.evidence[0].keyInfo = kMessage2KeyInfo;
    expectRejectedPair(report);

    report = strictPairReport();
    report.evidence[1].keyMicNonzero = false;
    expectRejectedPair(
        report, WifiAuthenticationStandardArtifactReason::InvalidReport);

    report = strictPairReport();
    report.peers[0].authenticatorNonceMismatch = true;
    expectRejectedPair(report);
}

void testPurposeSsidTargetAndReportFailuresAreExplicit() {
    AuthenticationCaptureProvenance provenance = provenanceFixture();
    const WifiAuthenticationCaptureReport valid = strictPairReport();

    provenance.purpose = AuthenticationCapturePurpose::Generic;
    auto result = evaluateWifiAuthenticationArtifacts(valid, provenance, 2U);
    CHECK(result.pcap.available);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::PurposeNotAuthentication);

    provenance = provenanceFixture();
    provenance.ssidKnown = false;
    provenance.ssidLength = 0U;
    result = evaluateWifiAuthenticationArtifacts(valid, provenance, 2U);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::SsidUnavailable);

    provenance = provenanceFixture();
    provenance.ssidLength = 0U;
    result = evaluateWifiAuthenticationArtifacts(valid, provenance, 2U);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::SsidInvalid);

    provenance = provenanceFixture();
    provenance.targetBssid = kOtherAccessPoint;
    result = evaluateWifiAuthenticationArtifacts(valid, provenance, 2U);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::TargetMismatch);

    WifiAuthenticationCaptureReport invalid = valid;
    invalid.evidenceCount = invalid.evidence.size() + 1U;
    provenance = provenanceFixture();
    result = evaluateWifiAuthenticationArtifacts(invalid, provenance, 2U);
    CHECK(result.pcap.available);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::InvalidReport);

    const AuthenticationCaptureProvenance lossy =
        provenanceFixture(2U, 1U, 0U);
    invalid = strictPairReport();
    setAccounting(&invalid, lossy);
    result = evaluateWifiAuthenticationArtifacts(invalid, lossy, 2U);
    CHECK(result.pcap.available);
    CHECK(result.standard.reason ==
          WifiAuthenticationStandardArtifactReason::InvalidReport);
}

static_assert(
    std::is_trivially_copyable_v<WifiAuthenticationArtifactPolicyResult>);
static_assert(sizeof(WifiAuthenticationArtifactPolicyResult) <= 8U);

}  // namespace

int main() {
    testPcapNeedsCleanNonemptyPersistedAccounting();
    testPcapMayPreserveHonestLossWhileStandardFailsClosed();
    testValidatedPmkidIsReadyWithoutChangingIncompleteOutcome();
    testStrictM1M2PairIsReadyForCoherentIncompleteOutcome();
    testCompleteOutcomeAndPeerFlagsMustBeCoherent();
    testStrictPairRejectsEveryRequiredInvariant();
    testPurposeSsidTargetAndReportFailuresAreExplicit();
    std::puts("Wi-Fi authentication artifact policy tests passed");
    return 0;
}
