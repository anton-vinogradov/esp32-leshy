#include "WifiAuthenticationSyntheticHilFixture.h"

#include <array>

namespace leshy1::apps::auth {
namespace {

using services::auth::WifiAuthenticationCaptureOutcome;
using services::auth::WifiAuthenticationCaptureReport;
using services::auth::WifiAuthenticationEvidence;
using services::auth::WifiAuthenticationKeyProfile;
using services::auth::WifiAuthenticationPeer;
using services::auth::WifiEapolKeyMessage;

constexpr std::array<std::uint8_t, 6> kSyntheticAccessPoint{
    0x02U, 0x00U, 0x00U, 0x00U, 0x00U, 0x01U};
constexpr std::array<std::uint8_t, 6> kSyntheticStationOne{
    0x02U, 0x00U, 0x00U, 0x00U, 0x01U, 0x01U};
constexpr std::array<std::uint8_t, 6> kSyntheticStationTwo{
    0x02U, 0x00U, 0x00U, 0x00U, 0x02U, 0x01U};
constexpr std::uint16_t kMessage1KeyInfo =
    (1U << 3U) | (1U << 7U) | 2U;
constexpr std::uint16_t kMessage2KeyInfo =
    (1U << 3U) | (1U << 8U) | 2U;
constexpr std::uint16_t kMessage3KeyInfo =
    (1U << 3U) | (1U << 6U) | (1U << 7U) | (1U << 8U) |
    (1U << 9U) | 2U;
constexpr std::uint16_t kMessage4KeyInfo =
    (1U << 3U) | (1U << 8U) | (1U << 9U) | 2U;
constexpr std::array<std::uint16_t, 6> kKeyInfo{
    kMessage1KeyInfo, kMessage2KeyInfo, kMessage3KeyInfo,
    kMessage4KeyInfo, kMessage1KeyInfo, kMessage2KeyInfo};
constexpr std::array<std::uint64_t, 6> kReplayCounters{
    40ULL, 40ULL, 41ULL, 41ULL, 50ULL, 50ULL};

}  // namespace

const char* wifiAuthenticationSyntheticHilStatusName(
    WifiAuthenticationSyntheticHilStatus status) {
    switch (status) {
        case WifiAuthenticationSyntheticHilStatus::Loaded: return "loaded";
        case WifiAuthenticationSyntheticHilStatus::HilInactive:
            return "hil_inactive";
        case WifiAuthenticationSyntheticHilStatus::UnsafeState:
            return "unsafe_state";
        case WifiAuthenticationSyntheticHilStatus::ReplayRejected:
            return "replay_rejected";
        case WifiAuthenticationSyntheticHilStatus::ReportRejected:
            return "report_rejected";
    }
    return "unsafe_state";
}

WifiAuthenticationSyntheticHilStatus
WifiAuthenticationSyntheticHilFixture::loadOnce(
    const WifiAuthenticationSyntheticHilContext& context,
    WifiAuthenticationCaptureReport* report,
    WifiAuthenticationCaptureController* controller) {
    if (!context.hilActive) {
        return WifiAuthenticationSyntheticHilStatus::HilInactive;
    }
    if (loaded_) {
        return WifiAuthenticationSyntheticHilStatus::ReplayRejected;
    }
    if (!context.authenticationViewActive || !context.resultActive ||
        !context.cleanupComplete || !context.captureInactive ||
        !context.foregroundWifiOwnsRf || context.channel < 1U ||
        context.channel > 14U || report == nullptr || controller == nullptr) {
        return WifiAuthenticationSyntheticHilStatus::UnsafeState;
    }

    buildFullReport(report, context.channel);
    if (controller->load(*report, false) !=
        WifiAuthenticationCaptureLoadStatus::Ready) {
        *report = {};
        controller->reset();
        return WifiAuthenticationSyntheticHilStatus::ReportRejected;
    }
    loaded_ = true;
    loadedAtMs_ = context.nowMs;
    return WifiAuthenticationSyntheticHilStatus::Loaded;
}

void WifiAuthenticationSyntheticHilFixture::buildFullReport(
    WifiAuthenticationCaptureReport* report, std::uint8_t channel) {
    *report = {};
    report->outcome = WifiAuthenticationCaptureOutcome::Complete;
    report->counters.sourceFrames = 6U;
    report->counters.framesRead = 6U;
    report->counters.dataFrames = 6U;
    report->counters.eapolFrames = 6U;
    report->counters.eapolKeyFrames = 6U;
    report->counters.classifiedKeyFrames = 6U;
    report->counters.captureFramesReported = 6U;
    report->counters.captureFramesAccepted = 6U;
    report->evidenceCount = 6U;
    report->peerCount = 2U;
    report->pmkidCount = 1U;

    constexpr std::array<std::uint8_t, 6> kMessages{1U, 2U, 3U, 4U, 1U, 2U};
    for (std::size_t index = 0U; index < report->evidenceCount; ++index) {
        WifiAuthenticationEvidence& evidence = report->evidence[index];
        evidence.monotonicUs = 1000000ULL +
            static_cast<std::uint64_t>(index) * 100000ULL;
        evidence.replayCounter = kReplayCounters[index];
        evidence.sourceFrameIndex = static_cast<std::uint8_t>(index);
        evidence.keyMicNonzero = kMessages[index] != 1U;
        evidence.rssiDbm = static_cast<std::int16_t>(-42 -
            static_cast<std::int16_t>(index));
        evidence.keyInfo = kKeyInfo[index];
        evidence.channel = channel;
        evidence.message = static_cast<WifiEapolKeyMessage>(kMessages[index]);
        evidence.eapolVersion = 2U;
        evidence.descriptorType = 2U;
        evidence.descriptorVersion = 2U;
        evidence.profile = WifiAuthenticationKeyProfile::RsnWpa2;
        evidence.accessPoint = kSyntheticAccessPoint;
        evidence.station = index < 4U
            ? kSyntheticStationOne : kSyntheticStationTwo;
    }

    WifiAuthenticationPeer& complete = report->peers[0];
    complete.accessPoint = kSyntheticAccessPoint;
    complete.station = kSyntheticStationOne;
    complete.replayCounters = {40ULL, 40ULL, 41ULL, 41ULL};
    complete.descriptorVersions = {2U, 2U, 2U, 2U};
    complete.evidenceIndices = {0U, 1U, 2U, 3U};
    complete.authenticatorNonce.fill(0x11U);
    complete.stationNonce.fill(0x22U);
    complete.messageMask = 0x0fU;
    complete.descriptorType = 2U;
    complete.authenticatorNonceSet = true;
    complete.sequenceConsistent = true;
    complete.replayCountersConsistent = true;
    complete.keyMaterialConsistent = true;
    complete.complete = true;

    WifiAuthenticationPeer& partial = report->peers[1];
    partial.accessPoint = kSyntheticAccessPoint;
    partial.station = kSyntheticStationTwo;
    partial.replayCounters[0] = 50ULL;
    partial.replayCounters[1] = 50ULL;
    partial.descriptorVersions[0] = 2U;
    partial.descriptorVersions[1] = 2U;
    partial.evidenceIndices[0] = 4U;
    partial.evidenceIndices[1] = 5U;
    partial.authenticatorNonce.fill(0x33U);
    partial.stationNonce.fill(0x55U);
    partial.messageMask = 0x03U;
    partial.descriptorType = 2U;
    partial.authenticatorNonceSet = true;
    partial.sequenceConsistent = true;

    report->pmkids[0].monotonicUs = 1000000ULL;
    report->pmkids[0].sourceFrameIndex = 0U;
    report->pmkids[0].accessPoint = kSyntheticAccessPoint;
    report->pmkids[0].station = kSyntheticStationOne;
    report->pmkids[0].pmkid.fill(0x44U);
}

}  // namespace leshy1::apps::auth
