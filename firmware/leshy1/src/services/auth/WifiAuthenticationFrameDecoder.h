#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/WifiFrame.h"

namespace leshy1::services::auth {

enum class WifiEapolKeyMessage : std::uint8_t {
    Unknown,
    Message1,
    Message2,
    Message3,
    Message4,
};

enum class WifiAuthenticationFrameDecodeStatus : std::uint8_t {
    Ignored,
    EapolNonKey,
    UnclassifiedKey,
    UnsupportedKey,
    ClassifiedKey,
    Malformed,
    Truncated,
};

// A bounded decode of one immutable 802.11 frame.
struct WifiAuthenticationDecodedKeyFrame final {
    WifiEapolKeyMessage message = WifiEapolKeyMessage::Unknown;
    std::array<std::uint8_t, 6> accessPoint{};
    std::array<std::uint8_t, 6> station{};
    std::uint64_t replayCounter = 0;
    std::uint16_t keyInfo = 0;
    bool keyMicNonzero = false;
    std::uint8_t eapolVersion = 0;
    std::uint8_t descriptorType = 0;
    std::uint8_t descriptorVersion = 0;
    std::array<std::uint8_t, 32> nonce{};
    std::array<std::uint8_t, 16> pmkid{};
    // Byte-exact borrowed ranges inside the source 802.11 payload.  They let
    // standard artifact serializers reuse the decoder's validated framing
    // instead of maintaining a second EAPOL parser.  The full EAPOL packet
    // includes its four-byte header; keyMicOffset is relative to that packet.
    std::uint16_t eapolOffset = 0;
    std::uint16_t eapolLength = 0;
    std::uint16_t keyMicOffset = 0;
    bool hasPmkid = false;
    bool fromAccessPoint = false;
};

constexpr std::uint8_t kWifiAuthenticationSupportedDescriptorType = 2U;
constexpr std::uint8_t kWifiAuthenticationSupportedDescriptorVersion2 = 2U;
constexpr std::uint8_t kWifiAuthenticationSupportedDescriptorVersion3 = 3U;
bool validWifiAuthenticationUnicastMac(
    const std::array<std::uint8_t, 6>& address);

// Parses one borrowed frame without allocation, I/O, radio access, or
// ownership changes. Malformed and truncated are intentionally distinct so
// callers can preserve fail-closed accounting.
WifiAuthenticationFrameDecodeStatus decodeWifiAuthenticationKeyFrame(
    const domain::captures::WifiFrameView& frame,
    WifiAuthenticationDecodedKeyFrame* output);

}  // namespace leshy1::services::auth
