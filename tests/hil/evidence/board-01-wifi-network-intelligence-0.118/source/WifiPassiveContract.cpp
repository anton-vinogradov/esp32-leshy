#include "WifiPassiveContract.h"

#include <algorithm>
#include <cstring>

namespace leshy1::drivers::wifi {

WifiScanPlan defaultPassivePlan() {
    return {};
}

bool validatePassivePlan(const WifiScanPlan& plan) {
    const bool directed = plan.directedSsid != nullptr && plan.directedSsid[0] != '\0';
    return plan.passive && !kActiveProbeAllowed && !directed && plan.channel <= 14 &&
           plan.maxMsPerChannel >= kMinimumDwellMs &&
           plan.maxMsPerChannel <= kMaximumDwellMs;
}

std::uint32_t channelFrequencyKhz(std::uint8_t channel) {
    if (channel >= 1 && channel <= 13) {
        return 2407000U + static_cast<std::uint32_t>(channel) * 5000U;
    }
    return channel == 14 ? 2484000U : 0U;
}

bool normalizePassiveRecord(const WifiScanRecord& record, std::uint64_t monotonicUs,
                            domain::observations::Observation* output) {
    if (output == nullptr || monotonicUs == 0 || channelFrequencyKhz(record.channel) == 0 ||
        record.rssiDbm < -127 || record.rssiDbm > 0 ||
        record.ssidLength > domain::observations::Observation::kLabelCapacity ||
        (record.ssidLength > 0 && record.ssid == nullptr)) {
        return false;
    }
    const bool emptyBssid =
        std::all_of(record.bssid.begin(), record.bssid.end(), [](std::uint8_t value) {
            return value == 0;
        });
    if (emptyBssid) return false;

    domain::observations::Observation normalized;
    normalized.monotonicUs = monotonicUs;
    normalized.radio = domain::observations::RadioKind::Wifi;
    normalized.frequencyKhz = channelFrequencyKhz(record.channel);
    normalized.channel = record.channel;
    normalized.rssiDbm = record.rssiDbm;
    normalized.identity = record.bssid;
    normalized.identityLength = static_cast<std::uint8_t>(record.bssid.size());
    normalized.labelLength = static_cast<std::uint8_t>(record.ssidLength);
    if (record.ssidLength > 0) {
        std::memcpy(normalized.label.data(), record.ssid, record.ssidLength);
    }
    normalized.label[record.ssidLength] = '\0';
    normalized.wifiNetwork = record.network;
    *output = normalized;
    return true;
}

const char* wifiAuthenticationName(
    domain::observations::WifiAuthentication authentication) {
    using Authentication = domain::observations::WifiAuthentication;
    switch (authentication) {
        case Authentication::Open: return "OPEN";
        case Authentication::Wep: return "WEP";
        case Authentication::WpaPsk: return "WPA-PSK";
        case Authentication::Wpa2Psk: return "WPA2-PSK";
        case Authentication::WpaWpa2Psk: return "WPA/WPA2-PSK";
        case Authentication::Wpa2Enterprise: return "WPA2-EAP";
        case Authentication::Wpa3Psk: return "WPA3-SAE";
        case Authentication::Wpa2Wpa3Psk: return "WPA2/WPA3";
        case Authentication::WapiPsk: return "WAPI-PSK";
        case Authentication::Owe: return "OWE";
        case Authentication::Wpa3Enterprise192: return "WPA3-EAP-192";
        case Authentication::Dpp: return "DPP";
        case Authentication::Wpa3Enterprise: return "WPA3-EAP";
        case Authentication::Wpa2Wpa3Enterprise: return "WPA2/WPA3-EAP";
        case Authentication::WpaEnterprise: return "WPA-EAP";
        case Authentication::Unknown:
        default: return "UNKNOWN";
    }
}

const char* wifiCipherName(domain::observations::WifiCipher cipher) {
    using Cipher = domain::observations::WifiCipher;
    switch (cipher) {
        case Cipher::None: return "NONE";
        case Cipher::Wep40: return "WEP40";
        case Cipher::Wep104: return "WEP104";
        case Cipher::Tkip: return "TKIP";
        case Cipher::Ccmp: return "CCMP";
        case Cipher::TkipCcmp: return "TKIP+CCMP";
        case Cipher::AesCmac128: return "AES-CMAC";
        case Cipher::Sms4: return "SMS4";
        case Cipher::Gcmp: return "GCMP";
        case Cipher::Gcmp256: return "GCMP-256";
        case Cipher::AesGmac128: return "AES-GMAC";
        case Cipher::AesGmac256: return "AES-GMAC-256";
        case Cipher::Unknown:
        default: return "UNKNOWN";
    }
}

const char* wifiChannelWidthName(
    domain::observations::WifiChannelWidth width) {
    using Width = domain::observations::WifiChannelWidth;
    switch (width) {
        case Width::Mhz20: return "20 MHZ";
        case Width::Mhz40: return "40 MHZ";
        case Width::Mhz80: return "80 MHZ";
        case Width::Mhz160: return "160 MHZ";
        case Width::Mhz80Plus80: return "80+80 MHZ";
        case Width::Unknown:
        default: return "WIDTH ?";
    }
}

bool formatWifiPhyMask(std::uint16_t phyMask, char* output,
                       std::size_t capacity) {
    using Facts = domain::observations::WifiNetworkFacts;
    if (output == nullptr || capacity == 0U) return false;
    output[0] = '\0';
    struct PhyName final {
        std::uint16_t bit;
        const char* name;
    };
    static constexpr PhyName kNames[] = {
        {Facts::kPhy11b, "B"}, {Facts::kPhy11g, "G"},
        {Facts::kPhy11n, "N"}, {Facts::kPhy11a, "A"},
        {Facts::kPhy11ac, "AC"}, {Facts::kPhy11ax, "AX"},
        {Facts::kPhyLowRate, "LR"},
    };
    std::size_t used = 0U;
    for (const auto& entry : kNames) {
        if ((phyMask & entry.bit) == 0U) continue;
        const std::size_t nameLength = std::strlen(entry.name);
        const std::size_t separator = used == 0U ? 0U : 1U;
        if (used + separator + nameLength >= capacity) return false;
        if (separator != 0U) output[used++] = '/';
        std::memcpy(output + used, entry.name, nameLength);
        used += nameLength;
        output[used] = '\0';
    }
    return used != 0U;
}

}  // namespace leshy1::drivers::wifi
