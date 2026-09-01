#include <cstdio>
#include <cstdlib>

#include "apps/wifi/WifiSecurityAdvisor.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using leshy1::apps::wifi::WifiSecurityNextStep;
using leshy1::apps::wifi::WifiSecurityPosture;
using leshy1::apps::wifi::assessWifiSecurity;
using leshy1::domain::observations::WifiAuthentication;
using leshy1::domain::observations::WifiCipher;
using leshy1::domain::observations::WifiNetworkFacts;

WifiNetworkFacts facts(WifiAuthentication authentication,
                       WifiCipher cipher = WifiCipher::Ccmp) {
    WifiNetworkFacts value{};
    value.present = true;
    value.authentication = authentication;
    value.pairwiseCipher = cipher;
    value.groupCipher = cipher;
    return value;
}

void unknownFactsFailClosed() {
    const auto assessment = assessWifiSecurity({});
    CHECK(assessment.posture == WifiSecurityPosture::Unknown);
    CHECK(assessment.nextStep == WifiSecurityNextStep::ListenForFacts);
    CHECK(!assessment.factsComplete);
    CHECK(!assessment.passwordCheckAvailable);
    CHECK(!assessment.pmfKnown);
}

void openAndLegacyNetworksDoNotLookProtected() {
    const auto open = assessWifiSecurity(facts(WifiAuthentication::Open,
                                               WifiCipher::None));
    CHECK(open.posture == WifiSecurityPosture::Open);
    CHECK(open.nextStep == WifiSecurityNextStep::EnableProtection);
    CHECK(!open.passwordCheckAvailable);

    const auto wep = assessWifiSecurity(facts(WifiAuthentication::Wep,
                                              WifiCipher::Wep104));
    CHECK(wep.posture == WifiSecurityPosture::Legacy);
    CHECK(wep.nextStep == WifiSecurityNextStep::UpgradeRouterSecurity);
    CHECK(!wep.passwordCheckAvailable);
}

void wpa2CanEnterOwnedLoginWorkflow() {
    const auto wpa2 = assessWifiSecurity(facts(WifiAuthentication::Wpa2Psk));
    CHECK(wpa2.posture == WifiSecurityPosture::Protected);
    CHECK(wpa2.nextStep == WifiSecurityNextStep::RecordOwnedLogin);
    CHECK(wpa2.passwordCheckAvailable);
    CHECK(!wpa2.saeAdvertised);
    CHECK(!wpa2.pmfKnown);

    auto withWps = facts(WifiAuthentication::Wpa2Psk);
    withWps.wps = true;
    const auto wps = assessWifiSecurity(withWps);
    CHECK(wps.passwordCheckAvailable);
    CHECK(wps.wpsAdvertised);
    CHECK(wps.nextStep == WifiSecurityNextStep::DisableWps);
}

void transitionModeIsVisibleAndStillCheckable() {
    const auto mixed = assessWifiSecurity(
        facts(WifiAuthentication::Wpa2Wpa3Psk));
    CHECK(mixed.posture == WifiSecurityPosture::UpgradeRecommended);
    CHECK(mixed.transitionMode);
    CHECK(mixed.saeAdvertised);
    CHECK(mixed.passwordCheckAvailable);
}

void pureSaeAndEnterpriseStayOutOfWpa2Verifier() {
    const auto sae = assessWifiSecurity(facts(WifiAuthentication::Wpa3Psk,
                                              WifiCipher::Gcmp));
    CHECK(sae.posture == WifiSecurityPosture::Protected);
    CHECK(sae.saeAdvertised);
    CHECK(sae.nextStep == WifiSecurityNextStep::NoPasswordCheck);
    CHECK(!sae.passwordCheckAvailable);

    const auto enterprise = assessWifiSecurity(
        facts(WifiAuthentication::Wpa3Enterprise192, WifiCipher::Gcmp256));
    CHECK(enterprise.posture == WifiSecurityPosture::Protected);
    CHECK(enterprise.enterprise);
    CHECK(enterprise.nextStep ==
          WifiSecurityNextStep::ReviewEnterpriseSettings);
    CHECK(!enterprise.passwordCheckAvailable);
}

void cipherEvidenceCanDowngradeAnOptimisticLabel() {
    const auto tkip = assessWifiSecurity(
        facts(WifiAuthentication::Wpa2Psk, WifiCipher::Tkip));
    CHECK(tkip.posture == WifiSecurityPosture::Legacy);
    CHECK(tkip.legacyCipher);
    CHECK(tkip.passwordCheckAvailable);
    CHECK(tkip.nextStep == WifiSecurityNextStep::UpgradeRouterSecurity);
}

}  // namespace

int main() {
    unknownFactsFailClosed();
    openAndLegacyNetworksDoNotLookProtected();
    wpa2CanEnterOwnedLoginWorkflow();
    transitionModeIsVisibleAndStillCheckable();
    pureSaeAndEnterpriseStayOutOfWpa2Verifier();
    cipherEvidenceCanDowngradeAnOptimisticLabel();
    std::puts("wifi_security_advisor_tests: PASS");
    return 0;
}
