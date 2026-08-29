#include "WifiAuthenticationPersistenceHilFixture.h"

#include <algorithm>
#include <array>
#include <cstring>

#include "services/auth/WifiAuthenticationCapture.h"

namespace leshy1::apps::auth {
namespace {

constexpr std::array<std::uint8_t, 32> kAuthenticatorNonce{
    0x10U, 0xe3U, 0xbeU, 0x3bU, 0x00U, 0x5aU, 0x62U, 0x9eU,
    0x89U, 0xdeU, 0x08U, 0x8dU, 0x6aU, 0x2fU, 0xdcU, 0x48U,
    0x9dU, 0xb8U, 0x3aU, 0xd4U, 0x76U, 0x4fU, 0x2dU, 0x18U,
    0x6bU, 0x9cU, 0xdeU, 0x15U, 0x44U, 0x6eU, 0x97U, 0x2eU};
constexpr std::array<std::uint8_t, 32> kStationNonce{
    0x48U, 0xceU, 0x2cU, 0xcbU, 0xa9U, 0xc1U, 0xfdU, 0xa1U,
    0x30U, 0xffU, 0x2fU, 0xbbU, 0xfbU, 0x4fU, 0xd3U, 0xb0U,
    0x63U, 0xd1U, 0xa9U, 0x39U, 0x20U, 0xb0U, 0xf7U, 0xdfU,
    0x54U, 0xa5U, 0xcbU, 0xf7U, 0x87U, 0xb1U, 0x61U, 0x71U};
constexpr std::array<std::uint8_t, 16> kMic{
    0x02U, 0x40U, 0x22U, 0x79U, 0x52U, 0x24U, 0xbfU, 0xfcU,
    0xa5U, 0x45U, 0x27U, 0x6cU, 0x37U, 0x62U, 0x68U, 0x6fU};

std::array<std::uint8_t, 99> message1() {
    std::array<std::uint8_t, 99> eapol{};
    eapol[0] = 1U;
    eapol[1] = 3U;
    eapol[2] = 0U;
    eapol[3] = 95U;
    eapol[4] = 2U;
    eapol[5] = 0U;
    eapol[6] = 0x8aU;
    eapol[8] = 16U;
    eapol[16] = 1U;
    std::memcpy(eapol.data() + 17U, kAuthenticatorNonce.data(),
                kAuthenticatorNonce.size());
    return eapol;
}

std::array<std::uint8_t, 121> message2() {
    std::array<std::uint8_t, 121> eapol{};
    eapol[0] = 1U;
    eapol[1] = 3U;
    eapol[2] = 0U;
    eapol[3] = 117U;
    eapol[4] = 2U;
    eapol[5] = 0x01U;
    eapol[6] = 0x0aU;
    eapol[16] = 1U;
    std::memcpy(eapol.data() + 17U, kStationNonce.data(),
                kStationNonce.size());
    std::memcpy(eapol.data() + 81U, kMic.data(), kMic.size());
    eapol[97] = 0U;
    eapol[98] = 22U;
    constexpr std::array<std::uint8_t, 22> kRsnIe{
        0x30U, 0x14U, 0x01U, 0x00U, 0x00U, 0x0fU, 0xacU, 0x04U,
        0x01U, 0x00U, 0x00U, 0x0fU, 0xacU, 0x04U, 0x01U, 0x00U,
        0x00U, 0x0fU, 0xacU, 0x02U, 0x80U, 0x00U};
    std::memcpy(eapol.data() + 99U, kRsnIe.data(), kRsnIe.size());
    return eapol;
}

}  // namespace

const char* wifiAuthenticationPersistenceHilStatusName(
    WifiAuthenticationPersistenceHilStatus status) {
    switch (status) {
        case WifiAuthenticationPersistenceHilStatus::Loaded: return "loaded";
        case WifiAuthenticationPersistenceHilStatus::HilInactive:
            return "hil_inactive";
        case WifiAuthenticationPersistenceHilStatus::UnsafeState:
            return "unsafe_state";
        case WifiAuthenticationPersistenceHilStatus::ReplayRejected:
            return "replay_rejected";
        case WifiAuthenticationPersistenceHilStatus::CaptureRejected:
            return "capture_rejected";
        case WifiAuthenticationPersistenceHilStatus::AnalysisRejected:
            return "analysis_rejected";
        case WifiAuthenticationPersistenceHilStatus::ReportRejected:
            return "report_rejected";
    }
    return "unsafe_state";
}

bool WifiAuthenticationPersistenceHilFixture::buildFrame(
    bool fromAccessPoint, const std::uint8_t* eapol,
    std::size_t eapolLength, std::array<std::uint8_t, 256>* frame,
    std::uint16_t* frameLength) {
    if (eapol == nullptr || frame == nullptr || frameLength == nullptr ||
        eapolLength + 32U > frame->size()) {
        return false;
    }
    frame->fill(0U);
    (*frame)[0] = 0x08U;
    (*frame)[1] = fromAccessPoint ? 0x02U : 0x01U;
    if (fromAccessPoint) {
        std::copy(kStation.begin(), kStation.end(), frame->begin() + 4U);
        std::copy(kAccessPoint.begin(), kAccessPoint.end(),
                  frame->begin() + 10U);
    } else {
        std::copy(kAccessPoint.begin(), kAccessPoint.end(),
                  frame->begin() + 4U);
        std::copy(kStation.begin(), kStation.end(), frame->begin() + 10U);
    }
    std::copy(kAccessPoint.begin(), kAccessPoint.end(),
              frame->begin() + 16U);
    constexpr std::array<std::uint8_t, 8> kLlc{
        0xaaU, 0xaaU, 0x03U, 0x00U, 0x00U, 0x00U, 0x88U, 0x8eU};
    std::copy(kLlc.begin(), kLlc.end(), frame->begin() + 24U);
    std::copy_n(eapol, eapolLength, frame->begin() + 32U);
    *frameLength = static_cast<std::uint16_t>(eapolLength + 32U);
    return true;
}

WifiAuthenticationPersistenceHilStatus
WifiAuthenticationPersistenceHilFixture::loadOnce(
    const WifiAuthenticationPersistenceHilContext& context,
    apps::capture::WifiFrameCapture* capture,
    services::auth::WifiAuthenticationCaptureReport* report,
    WifiAuthenticationCaptureController* controller) {
    if (!context.hilActive) {
        return WifiAuthenticationPersistenceHilStatus::HilInactive;
    }
    if (loaded_) {
        return WifiAuthenticationPersistenceHilStatus::ReplayRejected;
    }
    if (!context.authenticationViewActive || !context.resultActive ||
        !context.cleanupComplete || !context.captureInactive ||
        !context.foregroundWifiOwnsRf || context.nowUs == 0U ||
        capture == nullptr || report == nullptr || controller == nullptr) {
        return WifiAuthenticationPersistenceHilStatus::UnsafeState;
    }

    capture->reset();
    apps::capture::WifiFrameCapturePlan plan{};
    plan.channel = kChannel;
    plan.durationMs = 500U;
    plan.channelDwellMs = 120U;
    plan.snapLength = 256U;
    plan.maximumFrames = 2U;
    if (!capture->begin(plan, context.nowUs)) {
        return WifiAuthenticationPersistenceHilStatus::CaptureRejected;
    }
    const auto m1 = message1();
    const auto m2 = message2();
    std::array<std::uint8_t, 256> frame{};
    std::uint16_t length = 0U;
    const bool accepted =
        buildFrame(true, m1.data(), m1.size(), &frame, &length) &&
        capture->append(frame.data(), length, context.nowUs + 1000U, -42,
                        kChannel, apps::capture::WifiFrameKind::Data, false) &&
        buildFrame(false, m2.data(), m2.size(), &frame, &length) &&
        capture->append(frame.data(), length, context.nowUs + 2000U, -43,
                        kChannel, apps::capture::WifiFrameKind::Data, false) &&
        capture->complete(context.nowUs + 3000U);
    if (!accepted) {
        capture->reset();
        return WifiAuthenticationPersistenceHilStatus::CaptureRejected;
    }

    services::auth::WifiAuthenticationCaptureInput input{};
    input.source = capture;
    input.captureComplete = true;
    input.framesReported = 2U;
    input.framesAccepted = 2U;
    *report = {};
    if (!services::auth::analyzeWifiAuthenticationCapture(input, report)) {
        capture->reset();
        *report = {};
        return WifiAuthenticationPersistenceHilStatus::AnalysisRejected;
    }
    controller->reset();
    if (controller->load(*report, true) !=
        WifiAuthenticationCaptureLoadStatus::Ready) {
        capture->reset();
        *report = {};
        controller->reset();
        return WifiAuthenticationPersistenceHilStatus::ReportRejected;
    }
    loaded_ = true;
    loadedAtMs_ = context.nowMs;
    return WifiAuthenticationPersistenceHilStatus::Loaded;
}

}  // namespace leshy1::apps::auth
