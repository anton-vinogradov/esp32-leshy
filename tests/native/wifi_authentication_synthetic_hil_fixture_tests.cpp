#include <cstdio>
#include <cstdlib>
#include <type_traits>

#include "apps/auth/WifiAuthenticationArtifactPolicy.h"
#include "apps/auth/WifiAuthenticationSyntheticHilFixture.h"

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

WifiAuthenticationSyntheticHilContext safeContext() {
    WifiAuthenticationSyntheticHilContext context{};
    context.hilActive = true;
    context.authenticationViewActive = true;
    context.resultActive = true;
    context.cleanupComplete = true;
    context.captureInactive = true;
    context.foregroundWifiOwnsRf = true;
    context.channel = 11U;
    context.nowMs = 100U;
    return context;
}

void testFixtureFailsClosedOutsideExactHilResultState() {
    WifiAuthenticationSyntheticHilFixture fixture;
    WifiAuthenticationCaptureReport report{};
    WifiAuthenticationCaptureController controller;
    auto context = safeContext();
    context.hilActive = false;
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::HilInactive);
    CHECK(!fixture.loaded());
    CHECK(!controller.ready());

    context = safeContext();
    context.cleanupComplete = false;
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::UnsafeState);
    CHECK(!fixture.loaded());
    CHECK(!controller.ready());

    context = safeContext();
    context.captureInactive = false;
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::UnsafeState);
    CHECK(!fixture.loaded());
    CHECK(!controller.ready());

    context = safeContext();
    context.channel = 0U;
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::UnsafeState);
    context.channel = 15U;
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::UnsafeState);
    CHECK(!fixture.loaded());
    CHECK(!controller.ready());
}

void testFixtureBuildsDeterministicFullUiReportOnce() {
    WifiAuthenticationSyntheticHilFixture fixture;
    WifiAuthenticationCaptureReport report{};
    WifiAuthenticationCaptureController controller;
    const auto context = safeContext();
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::Loaded);
    CHECK(fixture.loaded());
    CHECK(controller.ready());
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Complete);
    CHECK(report.uncertainty == 0U);
    CHECK(report.peerCount == 2U);
    CHECK(report.evidenceCount == 6U);
    CHECK(report.pmkidCount == 1U);
    CHECK(controller.peerCount() == 2U);
    CHECK(controller.selectedPeer() != nullptr);
    CHECK(controller.selectedPeer()->complete);
    CHECK(controller.selectedPeer()->messageMask == 0x0fU);
    CHECK(controller.evidenceCount() == 6U);
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        CHECK(report.evidence[index].channel == context.channel);
    }
    CHECK(report.evidence[0].replayCounter == 40U);
    CHECK(report.evidence[1].replayCounter == 40U);
    CHECK(report.evidence[2].replayCounter == 41U);
    CHECK(report.evidence[3].replayCounter == 41U);
    CHECK(report.evidence[0].keyInfo == 0x008aU);
    CHECK(report.evidence[1].keyInfo == 0x010aU);
    CHECK(report.evidence[2].keyInfo == 0x03caU);
    CHECK(report.evidence[3].keyInfo == 0x030aU);
    CHECK(!report.evidence[0].keyMicNonzero);
    CHECK(report.evidence[1].keyMicNonzero);
    CHECK(report.evidence[2].keyMicNonzero);
    CHECK(report.evidence[3].keyMicNonzero);
    CHECK(!report.evidence[4].keyMicNonzero);
    CHECK(report.evidence[5].keyMicNonzero);
    CHECK(report.peers[0].replayCounters[0] ==
          report.peers[0].replayCounters[1]);
    CHECK(report.peers[0].replayCounters[2] ==
          report.peers[0].replayCounters[3]);
    CHECK(report.peers[0].replayCounters[2] >
          report.peers[0].replayCounters[0]);
    CHECK(report.peers[1].messageMask == 0x03U);
    CHECK(report.peers[1].replayCounters[0] ==
          report.peers[1].replayCounters[1]);
    CHECK(report.peers[1].authenticatorNonceSet);
    CHECK(report.peers[1].sequenceConsistent);

    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::ReplayRejected);
    CHECK(controller.ready());

    fixture.resetForSession();
    CHECK(!fixture.loaded());
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::Loaded);
}

void testFixtureMatchesPersistedArtifactPolicyInvariants() {
    WifiAuthenticationSyntheticHilFixture fixture;
    WifiAuthenticationCaptureReport report{};
    WifiAuthenticationCaptureController controller;
    const auto context = safeContext();
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::Loaded);

    AuthenticationCaptureProvenance provenance{};
    provenance.purpose = AuthenticationCapturePurpose::Authentication;
    provenance.targetBssid = report.evidence[0].accessPoint;
    provenance.ssidKnown = true;
    provenance.ssidLength = 4U;
    provenance.ssid[0] = 'T';
    provenance.ssid[1] = 'E';
    provenance.ssid[2] = 'S';
    provenance.ssid[3] = 'T';
    provenance.framesReported = 6U;
    provenance.framesAccepted = 6U;
    auto policy = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(policy.outcome == WifiAuthenticationCaptureOutcome::Complete);
    CHECK(policy.pcap.available);
    CHECK(policy.standard.ready);
    CHECK(policy.standard.reason ==
          WifiAuthenticationStandardArtifactReason::ReadyPmkid);

    report.pmkidCount = 0U;
    policy = evaluateWifiAuthenticationArtifacts(
        report, provenance, provenance.framesAccepted);
    CHECK(policy.standard.ready);
    CHECK(policy.standard.reason ==
          WifiAuthenticationStandardArtifactReason::ReadyMessagePair);
}

void testFixtureExpiryIsBoundedAndWrapSafe() {
    WifiAuthenticationSyntheticHilFixture fixture;
    WifiAuthenticationCaptureReport report{};
    WifiAuthenticationCaptureController controller;
    auto context = safeContext();
    context.nowMs = 0xffff0000U;
    CHECK(fixture.loadOnce(context, &report, &controller) ==
          WifiAuthenticationSyntheticHilStatus::Loaded);
    CHECK(!fixture.expired(context.nowMs +
                           WifiAuthenticationSyntheticHilFixture::kLifetimeMs -
                           1U));
    CHECK(fixture.expired(context.nowMs +
                          WifiAuthenticationSyntheticHilFixture::kLifetimeMs));
    fixture.resetForSession();
    CHECK(!fixture.expired(0U));
}

static_assert(std::is_trivially_copyable_v<
              WifiAuthenticationSyntheticHilFixture>);
static_assert(sizeof(WifiAuthenticationSyntheticHilFixture) <= 8U);

}  // namespace

int main() {
    testFixtureFailsClosedOutsideExactHilResultState();
    testFixtureBuildsDeterministicFullUiReportOnce();
    testFixtureMatchesPersistedArtifactPolicyInvariants();
    testFixtureExpiryIsBoundedAndWrapSafe();
    std::puts("Wi-Fi authentication synthetic HIL fixture tests passed");
    return 0;
}
