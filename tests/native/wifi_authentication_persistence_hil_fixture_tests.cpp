#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <type_traits>

#include "apps/auth/WifiAuthenticationArtifactPolicy.h"
#include "apps/auth/WifiAuthenticationHc22000.h"
#include "apps/auth/WifiAuthenticationPersistenceHilFixture.h"

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
using namespace leshy1::apps::capture;
using namespace leshy1::services::auth;
using leshy1::storage::AuthenticationCaptureProvenance;
using leshy1::storage::AuthenticationCapturePurpose;

WifiAuthenticationPersistenceHilContext safeContext() {
    WifiAuthenticationPersistenceHilContext context{};
    context.hilActive = true;
    context.authenticationViewActive = true;
    context.resultActive = true;
    context.cleanupComplete = true;
    context.captureInactive = true;
    context.foregroundWifiOwnsRf = true;
    context.nowMs = 100U;
    context.nowUs = 1000000ULL;
    return context;
}

AuthenticationCaptureProvenance provenance() {
    AuthenticationCaptureProvenance facts{};
    facts.purpose = AuthenticationCapturePurpose::Authentication;
    facts.targetBssid = WifiAuthenticationPersistenceHilFixture::kAccessPoint;
    std::copy(WifiAuthenticationPersistenceHilFixture::kSsid.begin(),
              WifiAuthenticationPersistenceHilFixture::kSsid.end(),
              facts.ssid.begin());
    facts.ssidLength = static_cast<std::uint8_t>(
        WifiAuthenticationPersistenceHilFixture::kSsid.size());
    facts.ssidKnown = true;
    facts.framesReported = 2U;
    facts.framesAccepted = 2U;
    return facts;
}

bool appendBytes(const std::uint8_t* data, std::size_t size, void* context) {
    if (data == nullptr || context == nullptr) return false;
    *static_cast<std::size_t*>(context) += size;
    return true;
}

void testFailsClosedOutsideExactHilState() {
    WifiAuthenticationPersistenceHilFixture fixture;
    WifiFrameCapture capture;
    WifiAuthenticationCaptureReport report{};
    WifiAuthenticationCaptureController controller;
    auto context = safeContext();
    context.hilActive = false;
    CHECK(fixture.loadOnce(context, &capture, &report, &controller) ==
          WifiAuthenticationPersistenceHilStatus::HilInactive);
    CHECK(capture.stats().state == WifiFrameCaptureState::Idle);

    context = safeContext();
    context.foregroundWifiOwnsRf = false;
    CHECK(fixture.loadOnce(context, &capture, &report, &controller) ==
          WifiAuthenticationPersistenceHilStatus::UnsafeState);
    CHECK(!fixture.loaded());
    CHECK(!controller.ready());
}

void testBuildsRealStrictM1M2CaptureOnce() {
    WifiAuthenticationPersistenceHilFixture fixture;
    WifiFrameCapture capture;
    WifiAuthenticationCaptureReport report{};
    WifiAuthenticationCaptureController controller;
    const auto context = safeContext();
    CHECK(fixture.loadOnce(context, &capture, &report, &controller) ==
          WifiAuthenticationPersistenceHilStatus::Loaded);
    CHECK(fixture.loaded());
    CHECK(capture.stats().state == WifiFrameCaptureState::Complete);
    CHECK(capture.size() == 2U);
    CHECK(capture.stats().framesReported == 2U);
    CHECK(capture.stats().framesAccepted == 2U);
    CHECK(report.peerCount == 1U);
    CHECK(report.evidenceCount == 2U);
    CHECK(report.peers[0].messageMask == 0x03U);
    CHECK(report.counters.sourceFrames == 2U);
    CHECK(controller.ready());
    CHECK(controller.saveAvailable());

    const auto policy = evaluateWifiAuthenticationArtifacts(
        report, provenance(), capture.frameCount());
    CHECK(policy.pcap.available);
    CHECK(policy.standard.ready);
    CHECK(policy.standard.reason ==
          WifiAuthenticationStandardArtifactReason::ReadyMessagePair);
    const std::size_t expected = wifiAuthenticationHc22000Size(
        report, provenance(), capture);
    CHECK(expected != 0U);
    std::size_t written = 0U;
    const auto result = writeWifiAuthenticationHc22000(
        report, provenance(), capture, appendBytes, &written);
    CHECK(result.valid());
    CHECK(result.recordsWritten == 1U);
    CHECK(result.eapolRecordsWritten == 1U);
    CHECK(result.pmkidRecordsWritten == 0U);
    CHECK(result.bytesWritten == expected);
    CHECK(written == expected);

    CHECK(fixture.loadOnce(context, &capture, &report, &controller) ==
          WifiAuthenticationPersistenceHilStatus::ReplayRejected);
}

void testExpiryAndResetAreBounded() {
    WifiAuthenticationPersistenceHilFixture fixture;
    WifiFrameCapture capture;
    WifiAuthenticationCaptureReport report{};
    WifiAuthenticationCaptureController controller;
    auto context = safeContext();
    context.nowMs = 0xffff0000U;
    CHECK(fixture.loadOnce(context, &capture, &report, &controller) ==
          WifiAuthenticationPersistenceHilStatus::Loaded);
    CHECK(!fixture.expired(context.nowMs +
                           WifiAuthenticationPersistenceHilFixture::kLifetimeMs -
                           1U));
    CHECK(fixture.expired(context.nowMs +
                          WifiAuthenticationPersistenceHilFixture::kLifetimeMs));
    fixture.resetForSession();
    CHECK(!fixture.loaded());
}

static_assert(std::is_trivially_copyable_v<
              WifiAuthenticationPersistenceHilFixture>);
static_assert(sizeof(WifiAuthenticationPersistenceHilFixture) <= 8U);

}  // namespace

int main() {
    testFailsClosedOutsideExactHilState();
    testBuildsRealStrictM1M2CaptureOnce();
    testExpiryAndResetAreBounded();
    std::puts("Wi-Fi authentication persistence HIL fixture tests passed");
    return 0;
}
