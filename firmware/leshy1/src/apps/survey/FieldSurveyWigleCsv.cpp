#include "apps/survey/FieldSurveyWigleCsv.h"

#include <array>
#include <cstdio>
#include <cstring>

namespace leshy1::apps::survey {
namespace {

using domain::observations::WifiAuthentication;
using domain::observations::WifiCipher;

FieldSurveyWigleResult result(FieldSurveyWigleStatus status,
                              FieldSurveyWigleReadiness readiness,
                              char* output, std::size_t capacity,
                              int written) {
    if (written < 0 || static_cast<std::size_t>(written) >= capacity) {
        if (output != nullptr && capacity != 0U) output[0] = '\0';
        return {FieldSurveyWigleStatus::BufferTooSmall, readiness, 0, false};
    }
    return {status, readiness, static_cast<std::size_t>(written),
            status == FieldSurveyWigleStatus::Valid &&
                readiness == FieldSurveyWigleReadiness::Located};
}

bool safeVersion(const char* version) {
    if (version == nullptr || version[0] == '\0') return false;
    std::size_t length = 0;
    for (; version[length] != '\0'; ++length) {
        const char value = version[length];
        const bool safe = (value >= 'A' && value <= 'Z') ||
            (value >= 'a' && value <= 'z') ||
            (value >= '0' && value <= '9') || value == '.' ||
            value == '-' || value == '_';
        if (!safe || length >= 31U) return false;
    }
    return length != 0U;
}

bool validTimestamp(const char* timestamp) {
    if (timestamp == nullptr || timestamp[0] == '\0') return true;
    if (std::strlen(timestamp) != 19U) return false;
    for (std::size_t index = 0; index < 19U; ++index) {
        if (index == 4U || index == 7U) {
            if (timestamp[index] != '-') return false;
        } else if (index == 10U) {
            if (timestamp[index] != ' ') return false;
        } else if (index == 13U || index == 16U) {
            if (timestamp[index] != ':') return false;
        } else if (timestamp[index] < '0' || timestamp[index] > '9') {
            return false;
        }
    }
    return true;
}

bool validLocation(const FieldSurveyLocation& location) {
    if (!location.present) {
        return location.latitudeE7 == 0 && location.longitudeE7 == 0 &&
            location.altitudeCentimeters == 0 &&
            location.accuracyCentimeters == 0U;
    }
    return location.latitudeE7 >= -900000000 &&
        location.latitudeE7 <= 900000000 &&
        location.longitudeE7 >= -1800000000 &&
        location.longitudeE7 <= 1800000000 &&
        location.accuracyCentimeters <= 10000000U;
}

FieldSurveyWigleReadiness readiness(
    const FieldSurveyWigleContext& context) {
    const bool timed = context.firstSeenUtc != nullptr &&
        context.firstSeenUtc[0] != '\0';
    if (timed && context.location.present) {
        return FieldSurveyWigleReadiness::Located;
    }
    if (timed) return FieldSurveyWigleReadiness::Unlocated;
    return context.location.present
        ? FieldSurveyWigleReadiness::UntimedLocated
        : FieldSurveyWigleReadiness::UntimedUnlocated;
}

void formatMac(const FieldSurveyRecord& record,
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

bool quoteCsv(const char* input, std::size_t length,
              char* output, std::size_t capacity) {
    if (input == nullptr || output == nullptr || capacity < 3U) return false;
    std::size_t position = 0;
    output[position++] = '"';
    for (std::size_t index = 0; index < length; ++index) {
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

const char* cipherName(WifiCipher cipher) {
    switch (cipher) {
        case WifiCipher::Wep40: return "WEP40";
        case WifiCipher::Wep104: return "WEP104";
        case WifiCipher::Tkip: return "TKIP";
        case WifiCipher::Ccmp: return "CCMP";
        case WifiCipher::TkipCcmp: return "TKIP+CCMP";
        case WifiCipher::Gcmp: return "GCMP";
        case WifiCipher::Gcmp256: return "GCMP-256";
        case WifiCipher::None: return "NONE";
        case WifiCipher::Unknown:
        case WifiCipher::AesCmac128:
        case WifiCipher::Sms4:
        case WifiCipher::AesGmac128:
        case WifiCipher::AesGmac256:
            return "UNKNOWN";
    }
    return "UNKNOWN";
}

void formatAuthentication(const FieldSurveyRecord& record,
                          char* output, std::size_t capacity) {
    const char* family = "";
    switch (record.wifiAuthentication) {
        case WifiAuthentication::Open:
            std::snprintf(output, capacity, "[ESS]");
            return;
        case WifiAuthentication::Wep: family = "WEP"; break;
        case WifiAuthentication::WpaPsk: family = "WPA-PSK"; break;
        case WifiAuthentication::Wpa2Psk: family = "WPA2-PSK"; break;
        case WifiAuthentication::WpaWpa2Psk:
            family = "WPA-WPA2-PSK";
            break;
        case WifiAuthentication::Wpa2Enterprise:
            family = "WPA2-EAP";
            break;
        case WifiAuthentication::Wpa3Psk: family = "WPA3-SAE"; break;
        case WifiAuthentication::Wpa2Wpa3Psk:
            family = "WPA2-WPA3-PSK";
            break;
        case WifiAuthentication::WapiPsk: family = "WAPI-PSK"; break;
        case WifiAuthentication::Owe: family = "OWE"; break;
        case WifiAuthentication::Wpa3Enterprise192:
            family = "WPA3-EAP-192";
            break;
        case WifiAuthentication::Dpp: family = "DPP"; break;
        case WifiAuthentication::Wpa3Enterprise:
            family = "WPA3-EAP";
            break;
        case WifiAuthentication::Wpa2Wpa3Enterprise:
            family = "WPA2-WPA3-EAP";
            break;
        case WifiAuthentication::WpaEnterprise:
            family = "WPA-EAP";
            break;
        case WifiAuthentication::Unknown: family = "UNKNOWN"; break;
    }
    std::snprintf(output, capacity, "[%s-%s][ESS]", family,
                  cipherName(record.wifiPairwiseCipher));
}

bool formatFixed(std::int32_t value, std::uint32_t scale,
                 unsigned digits, char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U || scale == 0U) return false;
    const bool negative = value < 0;
    const std::int64_t magnitude = negative
        ? -static_cast<std::int64_t>(value)
        : static_cast<std::int64_t>(value);
    const std::int64_t whole = magnitude / scale;
    const std::int64_t fraction = magnitude % scale;
    const int written = std::snprintf(
        output, capacity, "%s%lld.%0*lld", negative ? "-" : "",
        static_cast<long long>(whole), static_cast<int>(digits),
        static_cast<long long>(fraction));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace

const char* fieldSurveyWigleStatusName(FieldSurveyWigleStatus status) {
    switch (status) {
        case FieldSurveyWigleStatus::Valid: return "valid";
        case FieldSurveyWigleStatus::InvalidArgument:
            return "invalid_argument";
        case FieldSurveyWigleStatus::BufferTooSmall:
            return "buffer_too_small";
        case FieldSurveyWigleStatus::InvalidTimestamp:
            return "invalid_timestamp";
        case FieldSurveyWigleStatus::InvalidLocation:
            return "invalid_location";
        case FieldSurveyWigleStatus::UnsupportedEntity:
            return "unsupported_entity";
    }
    return "invalid_argument";
}

const char* fieldSurveyWigleReadinessName(
    FieldSurveyWigleReadiness value) {
    switch (value) {
        case FieldSurveyWigleReadiness::Located: return "located";
        case FieldSurveyWigleReadiness::Unlocated: return "unlocated";
        case FieldSurveyWigleReadiness::UntimedLocated:
            return "untimed_located";
        case FieldSurveyWigleReadiness::UntimedUnlocated:
            return "untimed_unlocated";
    }
    return "untimed_unlocated";
}

FieldSurveyWigleResult formatFieldSurveyWigleMetadata(
    const char* firmwareVersion, char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U || !safeVersion(firmwareVersion)) {
        if (output != nullptr && capacity != 0U) output[0] = '\0';
        return {};
    }
    const int written = std::snprintf(
        output, capacity,
        "WigleWifi-1.6,appRelease=ESP32-Leshy-%s,model=ESP32-DIV,"
        "release=1.x,device=ESP32-DIV,display=ILI9341,"
        "board=esp32-div-v2\r\n",
        firmwareVersion);
    return result(FieldSurveyWigleStatus::Valid,
                  FieldSurveyWigleReadiness::UntimedUnlocated,
                  output, capacity, written);
}

FieldSurveyWigleResult formatFieldSurveyWigleColumns(
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U) return {};
    const int written = std::snprintf(
        output, capacity,
        "MAC,SSID,AuthMode,FirstSeen,Channel,Frequency,RSSI,"
        "CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,"
        "RCOIs,MfgrId,Type\r\n");
    return result(FieldSurveyWigleStatus::Valid,
                  FieldSurveyWigleReadiness::UntimedUnlocated,
                  output, capacity, written);
}

FieldSurveyWigleResult formatFieldSurveyWigleRow(
    const FieldSurveyRecord& record,
    const FieldSurveyWigleContext& context,
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U ||
        record.identityLength != record.identity.size() ||
        record.labelLength > domain::observations::Observation::kLabelCapacity) {
        if (output != nullptr && capacity != 0U) output[0] = '\0';
        return {};
    }
    if (record.kind == FieldSurveyEntityKind::WifiStation) {
        output[0] = '\0';
        return {FieldSurveyWigleStatus::UnsupportedEntity,
                readiness(context), 0, false};
    }
    if (!validTimestamp(context.firstSeenUtc)) {
        output[0] = '\0';
        return {FieldSurveyWigleStatus::InvalidTimestamp,
                readiness(context), 0, false};
    }
    if (!validLocation(context.location)) {
        output[0] = '\0';
        return {FieldSurveyWigleStatus::InvalidLocation,
                readiness(context), 0, false};
    }

    std::array<char, 18> mac{};
    std::array<char, 70> label{};
    std::array<char, 48> authentication{};
    std::array<char, 24> latitude{};
    std::array<char, 24> longitude{};
    std::array<char, 24> altitude{};
    std::array<char, 24> accuracy{};
    std::array<char, 12> manufacturer{};
    std::array<char, 12> frequency{};
    formatMac(record, mac);
    if (!quoteCsv(record.label.data(), record.labelLength,
                  label.data(), label.size())) {
        output[0] = '\0';
        return {};
    }
    const bool wifi = record.kind == FieldSurveyEntityKind::WifiAccessPoint;
    if (wifi) {
        formatAuthentication(record, authentication.data(),
                             authentication.size());
    } else {
        std::snprintf(authentication.data(), authentication.size(),
                      "Misc [LE]");
        if (record.bleCompanyKnown) {
            std::snprintf(manufacturer.data(), manufacturer.size(), "0x%04X",
                          static_cast<unsigned>(record.bleCompanyId));
        }
    }
    if (context.location.present &&
        (!formatFixed(context.location.latitudeE7, 10000000U, 7U,
                      latitude.data(), latitude.size()) ||
         !formatFixed(context.location.longitudeE7, 10000000U, 7U,
                      longitude.data(), longitude.size()) ||
         !formatFixed(context.location.altitudeCentimeters, 100U, 2U,
                      altitude.data(), altitude.size()) ||
         !formatFixed(static_cast<std::int32_t>(
                          context.location.accuracyCentimeters),
                      100U, 2U, accuracy.data(), accuracy.size()))) {
        output[0] = '\0';
        return {FieldSurveyWigleStatus::InvalidLocation,
                readiness(context), 0, false};
    }
    const char* timestamp = context.firstSeenUtc == nullptr
        ? "" : context.firstSeenUtc;
    const std::uint32_t frequencyMhz = wifi
        ? record.strongestFrequencyKhz / 1000U : 0U;
    if (wifi) {
        std::snprintf(frequency.data(), frequency.size(), "%lu",
                      static_cast<unsigned long>(frequencyMhz));
    }
    const int written = std::snprintf(
        output, capacity,
        "%s,%s,\"%s\",%s,%u,%s,%d,%s,%s,%s,%s,,%s,%s\r\n",
        mac.data(), label.data(), authentication.data(), timestamp,
        static_cast<unsigned>(wifi ? record.strongestChannel : 0U),
        frequency.data(),
        static_cast<int>(record.strongestRssiDbm), latitude.data(),
        longitude.data(), altitude.data(), accuracy.data(),
        manufacturer.data(), wifi ? "WIFI" : "BLE");
    return result(FieldSurveyWigleStatus::Valid, readiness(context),
                  output, capacity, written);
}

}  // namespace leshy1::apps::survey
