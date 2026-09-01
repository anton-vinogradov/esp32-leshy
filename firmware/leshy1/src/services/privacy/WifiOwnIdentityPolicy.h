#pragma once

#include <array>
#include <cstdint>

namespace leshy1::services::privacy {

enum class WifiOwnIdentityMode : std::uint8_t {
    PrivatePerSession = 0U,
    Hardware = 1U,
};

enum class WifiOwnInterface : std::uint8_t {
    Station = 0U,
    AccessPoint = 1U,
};

using WifiMacAddress = std::array<std::uint8_t, 6>;

struct WifiPrivateIdentityResult final {
    WifiMacAddress address{};
    bool localAdmin = false;
    bool unicast = false;
    bool differsFromHardware = false;

    bool valid() const {
        return localAdmin && unicast && differsFromHardware;
    }
};

// Converts CSPRNG bytes into an IEEE 802 locally administered unicast
// address. The interface and generation are mixed only to make accidental
// STA/AP or consecutive-session reuse deterministically avoidable; entropy is
// supplied by the platform and the result is never persisted by this policy.
WifiPrivateIdentityResult makePrivateWifiIdentity(
    const WifiMacAddress& entropy, const WifiMacAddress& hardware,
    WifiOwnInterface interface, std::uint32_t generation);

const char* wifiOwnIdentityModeName(WifiOwnIdentityMode mode);

}  // namespace leshy1::services::privacy
