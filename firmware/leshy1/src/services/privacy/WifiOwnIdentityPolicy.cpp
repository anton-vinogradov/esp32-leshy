#include "services/privacy/WifiOwnIdentityPolicy.h"

namespace leshy1::services::privacy {

namespace {

bool sameAddress(const WifiMacAddress& left, const WifiMacAddress& right) {
    for (std::size_t index = 0; index < left.size(); ++index) {
        if (left[index] != right[index]) return false;
    }
    return true;
}

}  // namespace

WifiPrivateIdentityResult makePrivateWifiIdentity(
    const WifiMacAddress& entropy, const WifiMacAddress& hardware,
    WifiOwnInterface interface, std::uint32_t generation) {
    WifiPrivateIdentityResult result;
    result.address = entropy;
    result.address[0] = static_cast<std::uint8_t>(
        (result.address[0] & 0xfcU) | 0x02U);
    result.address[1] ^= static_cast<std::uint8_t>(generation);
    result.address[2] ^=
        static_cast<std::uint8_t>(generation >> 8U);
    result.address[3] ^= interface == WifiOwnInterface::AccessPoint
        ? 0xa5U : 0x5aU;
    result.address[4] ^=
        static_cast<std::uint8_t>(generation >> 16U);
    result.address[5] ^=
        static_cast<std::uint8_t>(generation >> 24U);
    if (sameAddress(result.address, hardware)) {
        result.address[5] ^= 0x80U;
    }
    result.localAdmin = (result.address[0] & 0x02U) != 0U;
    result.unicast = (result.address[0] & 0x01U) == 0U;
    result.differsFromHardware = !sameAddress(result.address, hardware);
    return result;
}

const char* wifiOwnIdentityModeName(WifiOwnIdentityMode mode) {
    switch (mode) {
        case WifiOwnIdentityMode::PrivatePerSession:
            return "private_per_session";
        case WifiOwnIdentityMode::Hardware: return "hardware";
    }
    return "hardware";
}

}  // namespace leshy1::services::privacy
