#include "apps/survey/FieldSurveyNativeCsv.h"

#include <array>
#include <cstdio>

namespace leshy1::apps::survey {
namespace {

using domain::observations::WifiAuthentication;
using domain::observations::WifiCipher;

FieldSurveyNativeResult result(char* output, std::size_t capacity,
                               int written) {
    if (written < 0 || static_cast<std::size_t>(written) >= capacity) {
        if (output != nullptr && capacity != 0U) output[0] = '\0';
        return {FieldSurveyNativeStatus::BufferTooSmall, 0U};
    }
    return {FieldSurveyNativeStatus::Valid,
            static_cast<std::size_t>(written)};
}

bool quoteCsv(const char* input, std::size_t length,
              char* output, std::size_t capacity) {
    if (input == nullptr || output == nullptr || capacity < 3U) return false;
    std::size_t position = 0U;
    output[position++] = '"';
    for (std::size_t index = 0U; index < length; ++index) {
        const char value = input[index];
        if (value == '\r' || value == '\n' || value == '\0') return false;
        if (value == '"') {
            if (position + 2U >= capacity) return false;
            output[position++] = '"';
        } else if (position + 1U >= capacity) {
            return false;
        }
        output[position++] = value;
    }
    if (position + 2U > capacity) return false;
    output[position++] = '"';
    output[position] = '\0';
    return true;
}

void formatIdentity(const FieldSurveyRecord& record,
                    std::array<char, 18>& output) {
    std::snprintf(
        output.data(), output.size(), "%02X:%02X:%02X:%02X:%02X:%02X",
        static_cast<unsigned>(record.identity[0]),
        static_cast<unsigned>(record.identity[1]),
        static_cast<unsigned>(record.identity[2]),
        static_cast<unsigned>(record.identity[3]),
        static_cast<unsigned>(record.identity[4]),
        static_cast<unsigned>(record.identity[5]));
}

const char* authenticationName(WifiAuthentication value) {
    switch (value) {
        case WifiAuthentication::Unknown: return "unknown";
        case WifiAuthentication::Open: return "open";
        case WifiAuthentication::Wep: return "wep";
        case WifiAuthentication::WpaPsk: return "wpa_psk";
        case WifiAuthentication::Wpa2Psk: return "wpa2_psk";
        case WifiAuthentication::WpaWpa2Psk: return "wpa_wpa2_psk";
        case WifiAuthentication::Wpa2Enterprise: return "wpa2_enterprise";
        case WifiAuthentication::Wpa3Psk: return "wpa3_psk";
        case WifiAuthentication::Wpa2Wpa3Psk: return "wpa2_wpa3_psk";
        case WifiAuthentication::WapiPsk: return "wapi_psk";
        case WifiAuthentication::Owe: return "owe";
        case WifiAuthentication::Wpa3Enterprise192:
            return "wpa3_enterprise_192";
        case WifiAuthentication::Dpp: return "dpp";
        case WifiAuthentication::Wpa3Enterprise: return "wpa3_enterprise";
        case WifiAuthentication::Wpa2Wpa3Enterprise:
            return "wpa2_wpa3_enterprise";
        case WifiAuthentication::WpaEnterprise: return "wpa_enterprise";
    }
    return "unknown";
}

const char* cipherName(WifiCipher value) {
    switch (value) {
        case WifiCipher::Unknown: return "unknown";
        case WifiCipher::None: return "none";
        case WifiCipher::Wep40: return "wep40";
        case WifiCipher::Wep104: return "wep104";
        case WifiCipher::Tkip: return "tkip";
        case WifiCipher::Ccmp: return "ccmp";
        case WifiCipher::TkipCcmp: return "tkip_ccmp";
        case WifiCipher::AesCmac128: return "aes_cmac_128";
        case WifiCipher::Sms4: return "sms4";
        case WifiCipher::Gcmp: return "gcmp";
        case WifiCipher::Gcmp256: return "gcmp_256";
        case WifiCipher::AesGmac128: return "aes_gmac_128";
        case WifiCipher::AesGmac256: return "aes_gmac_256";
    }
    return "unknown";
}

}  // namespace

const char* fieldSurveyNativeStatusName(FieldSurveyNativeStatus status) {
    switch (status) {
        case FieldSurveyNativeStatus::Valid: return "valid";
        case FieldSurveyNativeStatus::InvalidArgument:
            return "invalid_argument";
        case FieldSurveyNativeStatus::BufferTooSmall:
            return "buffer_too_small";
    }
    return "invalid_argument";
}

FieldSurveyNativeResult formatFieldSurveyNativeHeader(
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U) return {};
    const int written = std::snprintf(
        output, capacity,
        "entity_kind,identity,label,first_seen_monotonic_us,"
        "last_seen_monotonic_us,observations,strongest_frequency_khz,"
        "strongest_channel,strongest_rssi_dbm,latest_rssi_dbm,"
        "wifi_authentication,wifi_pairwise_cipher,wifi_group_cipher,"
        "ble_company_id\r\n");
    return result(output, capacity, written);
}

FieldSurveyNativeResult formatFieldSurveyNativeRow(
    const FieldSurveyRecord& record, char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U ||
        record.identityLength != record.identity.size() ||
        record.labelLength > domain::observations::Observation::kLabelCapacity ||
        record.firstSeenUs == 0U || record.lastSeenUs < record.firstSeenUs ||
        record.observations == 0U) {
        if (output != nullptr && capacity != 0U) output[0] = '\0';
        return {};
    }
    std::array<char, 18> identity{};
    std::array<char, 70> label{};
    std::array<char, 8> company{};
    formatIdentity(record, identity);
    if (!quoteCsv(record.label.data(), record.labelLength,
                  label.data(), label.size())) {
        output[0] = '\0';
        return {};
    }
    const bool wifi = record.kind != FieldSurveyEntityKind::BleDevice;
    if (record.kind == FieldSurveyEntityKind::BleDevice &&
        record.bleCompanyKnown) {
        std::snprintf(company.data(), company.size(), "0x%04X",
                      static_cast<unsigned>(record.bleCompanyId));
    }
    const int written = std::snprintf(
        output, capacity,
        "%s,%s,%s,%llu,%llu,%lu,%lu,%u,%d,%d,%s,%s,%s,%s\r\n",
        fieldSurveyEntityKindName(record.kind), identity.data(), label.data(),
        static_cast<unsigned long long>(record.firstSeenUs),
        static_cast<unsigned long long>(record.lastSeenUs),
        static_cast<unsigned long>(record.observations),
        static_cast<unsigned long>(record.strongestFrequencyKhz),
        static_cast<unsigned>(record.strongestChannel),
        static_cast<int>(record.strongestRssiDbm),
        static_cast<int>(record.latestRssiDbm),
        wifi ? authenticationName(record.wifiAuthentication) : "",
        wifi ? cipherName(record.wifiPairwiseCipher) : "",
        wifi ? cipherName(record.wifiGroupCipher) : "",
        company.data());
    return result(output, capacity, written);
}

}  // namespace leshy1::apps::survey
