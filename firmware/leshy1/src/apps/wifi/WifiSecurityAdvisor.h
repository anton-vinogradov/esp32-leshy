#pragma once

#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::apps::wifi {

enum class WifiSecurityPosture : std::uint8_t {
    Unknown,
    Open,
    Legacy,
    UpgradeRecommended,
    Protected,
};

enum class WifiSecurityNextStep : std::uint8_t {
    ListenForFacts,
    EnableProtection,
    UpgradeRouterSecurity,
    DisableWps,
    RecordOwnedLogin,
    ReviewEnterpriseSettings,
    NoPasswordCheck,
};

// A task-facing interpretation of passive scan facts. The assessment never
// invents RSN capabilities that the managed scan did not expose: in
// particular, PMF remains explicitly unknown until raw management-frame
// evidence is admitted by a later receiver path.
struct WifiSecurityAssessment final {
    WifiSecurityPosture posture = WifiSecurityPosture::Unknown;
    WifiSecurityNextStep nextStep = WifiSecurityNextStep::ListenForFacts;
    bool factsComplete = false;
    bool passwordCheckAvailable = false;
    bool wpsAdvertised = false;
    bool saeAdvertised = false;
    bool transitionMode = false;
    bool enterprise = false;
    bool pmfKnown = false;
    bool legacyCipher = false;
};

WifiSecurityAssessment assessWifiSecurity(
    const domain::observations::WifiNetworkFacts& facts);

}  // namespace leshy1::apps::wifi
