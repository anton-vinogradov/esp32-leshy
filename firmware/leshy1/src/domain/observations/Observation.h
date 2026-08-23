#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::domain::observations {

enum class RadioKind : std::uint8_t {
    Wifi = 1,
    Ble = 2,
};

// Passive facts reported by the Wi-Fi scan driver for an access point.  They
// are deliberately stored alongside the normalized observation: the survey
// pipeline remains allocation-free and the live network catalog can enrich a
// BSSID without running a second radio parser or issuing active probes.
enum class WifiAuthentication : std::uint8_t {
    Unknown,
    Open,
    Wep,
    WpaPsk,
    Wpa2Psk,
    WpaWpa2Psk,
    Wpa2Enterprise,
    Wpa3Psk,
    Wpa2Wpa3Psk,
    WapiPsk,
    Owe,
    Wpa3Enterprise192,
    Dpp,
    Wpa3Enterprise,
    Wpa2Wpa3Enterprise,
    WpaEnterprise,
};

enum class WifiCipher : std::uint8_t {
    Unknown,
    None,
    Wep40,
    Wep104,
    Tkip,
    Ccmp,
    TkipCcmp,
    AesCmac128,
    Sms4,
    Gcmp,
    Gcmp256,
    AesGmac128,
    AesGmac256,
};

enum class WifiChannelWidth : std::uint8_t {
    Unknown,
    Mhz20,
    Mhz40,
    Mhz80,
    Mhz160,
    Mhz80Plus80,
};

struct WifiNetworkFacts final {
    static constexpr std::uint16_t kPhy11b = 1U << 0U;
    static constexpr std::uint16_t kPhy11g = 1U << 1U;
    static constexpr std::uint16_t kPhy11n = 1U << 2U;
    static constexpr std::uint16_t kPhyLowRate = 1U << 3U;
    static constexpr std::uint16_t kPhy11a = 1U << 4U;
    static constexpr std::uint16_t kPhy11ac = 1U << 5U;
    static constexpr std::uint16_t kPhy11ax = 1U << 6U;

    bool present = false;
    WifiAuthentication authentication = WifiAuthentication::Unknown;
    WifiCipher pairwiseCipher = WifiCipher::Unknown;
    WifiCipher groupCipher = WifiCipher::Unknown;
    WifiChannelWidth channelWidth = WifiChannelWidth::Unknown;
    std::uint16_t phyMask = 0;
    // 0 = none, 1 = above the primary channel, 2 = below it.
    std::uint8_t secondaryChannelDirection = 0;
    std::uint8_t receiveAntenna = 0xffU;
    bool wps = false;
    bool ftmResponder = false;
    bool ftmInitiator = false;
    std::array<char, 3> countryCode{};
    std::uint8_t countryStartChannel = 0;
    std::uint8_t countryChannelCount = 0;
    std::int8_t countryMaximumTxPowerDbm = 0;
    std::uint8_t bssColor = 0;
    bool bssColorKnown = false;
    std::uint8_t vhtCenterChannel1 = 0;
    std::uint8_t vhtCenterChannel2 = 0;
};

inline bool wifiNetworkFactsEqual(const WifiNetworkFacts& left,
                                  const WifiNetworkFacts& right) {
    return left.present == right.present &&
        left.authentication == right.authentication &&
        left.pairwiseCipher == right.pairwiseCipher &&
        left.groupCipher == right.groupCipher &&
        left.channelWidth == right.channelWidth &&
        left.phyMask == right.phyMask &&
        left.secondaryChannelDirection == right.secondaryChannelDirection &&
        left.receiveAntenna == right.receiveAntenna &&
        left.wps == right.wps &&
        left.ftmResponder == right.ftmResponder &&
        left.ftmInitiator == right.ftmInitiator &&
        left.countryCode == right.countryCode &&
        left.countryStartChannel == right.countryStartChannel &&
        left.countryChannelCount == right.countryChannelCount &&
        left.countryMaximumTxPowerDbm == right.countryMaximumTxPowerDbm &&
        left.bssColor == right.bssColor &&
        left.bssColorKnown == right.bssColorKnown &&
        left.vhtCenterChannel1 == right.vhtCenterChannel1 &&
        left.vhtCenterChannel2 == right.vhtCenterChannel2;
}

struct BleAdvertisementFacts final {
    // The 240 px UI displays either a short UUID or the assigned-number slice
    // of a 128-bit UUID. Keep that text plus a hash of the full UUID instead of
    // copying 36 bytes into every bounded survey observation.
    static constexpr std::size_t kServiceUuidCapacity = 8;
    static constexpr std::uint16_t kServiceHid = 1U << 0U;
    static constexpr std::uint16_t kServiceBattery = 1U << 1U;
    static constexpr std::uint16_t kServiceHeartRate = 1U << 2U;
    static constexpr std::uint16_t kServiceThermometer = 1U << 3U;
    static constexpr std::uint16_t kServiceFitness = 1U << 4U;
    static constexpr std::uint16_t kServiceEddystone = 1U << 5U;
    static constexpr std::uint16_t kServiceXiaomi = 1U << 6U;
    static constexpr std::uint16_t kServiceSmartTag = 1U << 7U;
    static constexpr std::uint16_t kServiceTile = 1U << 8U;
    static constexpr std::uint16_t kServiceFastPair = 1U << 9U;
    static constexpr std::uint16_t kServiceExposure = 1U << 10U;

    bool present = false;
    std::uint8_t addressType = 0;
    std::uint8_t advertisementType = 0;
    bool legacy = false;
    bool scannable = false;
    bool connectable = false;
    bool txPowerKnown = false;
    std::int8_t txPowerDbm = 0;
    bool appearanceKnown = false;
    std::uint16_t appearance = 0;
    bool companyKnown = false;
    std::uint16_t companyId = 0;
    std::uint8_t appleContinuityType = 0;
    std::uint16_t knownServiceMask = 0;
    std::array<char, kServiceUuidCapacity + 1U> firstServiceUuid{};
    std::uint32_t firstServiceUuidHash = 0;
    std::uint8_t firstServiceUuidLength = 0;
    std::uint8_t serviceUuidCount = 0;
    std::uint8_t serviceDataCount = 0;
    std::uint8_t manufacturerDataLength = 0;
    std::uint8_t payloadLength = 0;
};

inline bool bleAdvertisementFactsEqual(const BleAdvertisementFacts& left,
                                       const BleAdvertisementFacts& right) {
    return left.present == right.present &&
        left.addressType == right.addressType &&
        left.advertisementType == right.advertisementType &&
        left.legacy == right.legacy &&
        left.scannable == right.scannable &&
        left.connectable == right.connectable &&
        left.txPowerKnown == right.txPowerKnown &&
        left.txPowerDbm == right.txPowerDbm &&
        left.appearanceKnown == right.appearanceKnown &&
        left.appearance == right.appearance &&
        left.companyKnown == right.companyKnown &&
        left.companyId == right.companyId &&
        left.appleContinuityType == right.appleContinuityType &&
        left.knownServiceMask == right.knownServiceMask &&
        left.firstServiceUuidHash == right.firstServiceUuidHash &&
        left.firstServiceUuidLength == right.firstServiceUuidLength &&
        left.firstServiceUuid == right.firstServiceUuid &&
        left.serviceUuidCount == right.serviceUuidCount &&
        left.serviceDataCount == right.serviceDataCount &&
        left.manufacturerDataLength == right.manufacturerDataLength &&
        left.payloadLength == right.payloadLength;
}

struct Observation final {
    static constexpr std::size_t kIdentityCapacity = 6;
    static constexpr std::size_t kLabelCapacity = 32;

    std::uint64_t sequence = 0;
    std::uint64_t monotonicUs = 0;
    RadioKind radio = RadioKind::Wifi;
    std::uint32_t frequencyKhz = 0;
    std::uint16_t channel = 0;
    std::int16_t rssiDbm = 0;
    std::array<std::uint8_t, kIdentityCapacity> identity{};
    std::uint8_t identityLength = 0;
    std::array<char, kLabelCapacity + 1> label{};
    std::uint8_t labelLength = 0;
    WifiNetworkFacts wifiNetwork{};
    BleAdvertisementFacts bleAdvertisement{};
};

}  // namespace leshy1::domain::observations
