#include "WifiSecurityAdvisor.h"

namespace leshy1::apps::wifi {
namespace {

using Authentication = domain::observations::WifiAuthentication;
using Cipher = domain::observations::WifiCipher;

bool isLegacyCipher(Cipher cipher) {
    return cipher == Cipher::Wep40 || cipher == Cipher::Wep104 ||
        cipher == Cipher::Tkip;
}

bool isMixedLegacyCipher(Cipher cipher) {
    return cipher == Cipher::TkipCcmp;
}

bool supportsOwnedPasswordCheck(Authentication authentication) {
    return authentication == Authentication::WpaPsk ||
        authentication == Authentication::Wpa2Psk ||
        authentication == Authentication::WpaWpa2Psk ||
        authentication == Authentication::Wpa2Wpa3Psk;
}

bool isEnterprise(Authentication authentication) {
    return authentication == Authentication::WpaEnterprise ||
        authentication == Authentication::Wpa2Enterprise ||
        authentication == Authentication::Wpa3Enterprise ||
        authentication == Authentication::Wpa3Enterprise192 ||
        authentication == Authentication::Wpa2Wpa3Enterprise;
}

}  // namespace

WifiSecurityAssessment assessWifiSecurity(
    const domain::observations::WifiNetworkFacts& facts) {
    WifiSecurityAssessment assessment{};
    // The current managed scan does not expose RSN capabilities, therefore
    // PMF is never inferred from an authentication label alone.
    assessment.pmfKnown = false;
    assessment.factsComplete = facts.present &&
        facts.authentication != Authentication::Unknown;
    assessment.wpsAdvertised = facts.present && facts.wps;
    assessment.enterprise = isEnterprise(facts.authentication);
    assessment.saeAdvertised =
        facts.authentication == Authentication::Wpa3Psk ||
        facts.authentication == Authentication::Wpa2Wpa3Psk;
    assessment.transitionMode =
        facts.authentication == Authentication::WpaWpa2Psk ||
        facts.authentication == Authentication::Wpa2Wpa3Psk ||
        facts.authentication == Authentication::Wpa2Wpa3Enterprise;
    assessment.legacyCipher = isLegacyCipher(facts.pairwiseCipher) ||
        isLegacyCipher(facts.groupCipher);

    if (!assessment.factsComplete) return assessment;

    if (facts.authentication == Authentication::Open) {
        assessment.posture = WifiSecurityPosture::Open;
        assessment.nextStep = WifiSecurityNextStep::EnableProtection;
        return assessment;
    }

    if (facts.authentication == Authentication::Wep ||
        facts.authentication == Authentication::WpaPsk ||
        facts.authentication == Authentication::WpaEnterprise ||
        facts.authentication == Authentication::WapiPsk ||
        assessment.legacyCipher) {
        assessment.posture = WifiSecurityPosture::Legacy;
        assessment.nextStep = WifiSecurityNextStep::UpgradeRouterSecurity;
        assessment.passwordCheckAvailable =
            supportsOwnedPasswordCheck(facts.authentication);
        return assessment;
    }

    if (facts.authentication == Authentication::WpaWpa2Psk ||
        isMixedLegacyCipher(facts.pairwiseCipher) ||
        isMixedLegacyCipher(facts.groupCipher)) {
        assessment.posture = WifiSecurityPosture::UpgradeRecommended;
        assessment.nextStep = WifiSecurityNextStep::UpgradeRouterSecurity;
        assessment.passwordCheckAvailable = true;
        return assessment;
    }

    if (assessment.enterprise) {
        assessment.posture = WifiSecurityPosture::Protected;
        assessment.nextStep = WifiSecurityNextStep::ReviewEnterpriseSettings;
        return assessment;
    }

    if (facts.authentication == Authentication::Owe ||
        facts.authentication == Authentication::Dpp) {
        assessment.posture = WifiSecurityPosture::Protected;
        assessment.nextStep = WifiSecurityNextStep::NoPasswordCheck;
        return assessment;
    }

    if (facts.authentication == Authentication::Wpa3Psk) {
        assessment.posture = WifiSecurityPosture::Protected;
        // The current verifier accepts WPA*01/02 and key descriptor versions
        // 1/2 only. Pure SAE must not be sent into that WPA2 workflow.
        assessment.nextStep = WifiSecurityNextStep::NoPasswordCheck;
        return assessment;
    }

    if (facts.authentication == Authentication::Wpa2Psk ||
        facts.authentication == Authentication::Wpa2Wpa3Psk) {
        assessment.posture = assessment.transitionMode
            ? WifiSecurityPosture::UpgradeRecommended
            : WifiSecurityPosture::Protected;
        assessment.passwordCheckAvailable = true;
        assessment.nextStep = assessment.wpsAdvertised
            ? WifiSecurityNextStep::DisableWps
            : WifiSecurityNextStep::RecordOwnedLogin;
        return assessment;
    }

    assessment.posture = WifiSecurityPosture::Unknown;
    assessment.nextStep = WifiSecurityNextStep::ListenForFacts;
    return assessment;
}

}  // namespace leshy1::apps::wifi
