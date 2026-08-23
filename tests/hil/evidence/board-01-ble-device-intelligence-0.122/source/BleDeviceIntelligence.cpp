#include "BleDeviceIntelligence.h"

#include <cctype>
#include <cstring>

namespace leshy1::apps::ble {

namespace {

bool containsAsciiIgnoreCase(const char* value, const char* needle) {
    if (value == nullptr || needle == nullptr || *needle == '\0') return false;
    const std::size_t valueLength = std::strlen(value);
    const std::size_t needleLength = std::strlen(needle);
    if (needleLength > valueLength) return false;
    for (std::size_t offset = 0; offset + needleLength <= valueLength; ++offset) {
        bool matches = true;
        for (std::size_t index = 0; index < needleLength; ++index) {
            const auto left = static_cast<unsigned char>(value[offset + index]);
            const auto right = static_cast<unsigned char>(needle[index]);
            if (std::tolower(left) != std::tolower(right)) {
                matches = false;
                break;
            }
        }
        if (matches) return true;
    }
    return false;
}

}  // namespace

BleDeviceKind classifyBleDevice(
        const domain::observations::Observation& observation) {
    using Facts = domain::observations::BleAdvertisementFacts;
    const Facts& facts = observation.bleAdvertisement;
    if (facts.appearanceKnown) {
        switch (facts.appearance >> 6U) {
            case 0x01: return BleDeviceKind::Phone;
            case 0x02: return BleDeviceKind::Computer;
            case 0x03: return BleDeviceKind::Watch;
            case 0x05: return BleDeviceKind::Display;
            case 0x08: return BleDeviceKind::Tag;
            case 0x0c: return BleDeviceKind::Thermometer;
            case 0x0d: return BleDeviceKind::Heart;
            case 0x0f:
                if ((facts.appearance & 0x3fU) == 1U) {
                    return BleDeviceKind::Keyboard;
                }
                if ((facts.appearance & 0x3fU) == 2U) {
                    return BleDeviceKind::Mouse;
                }
                return BleDeviceKind::Input;
            case 0x11:
            case 0x12: return BleDeviceKind::Fitness;
            case 0x25: return BleDeviceKind::Audio;
            default: break;
        }
    }
    if ((facts.knownServiceMask & Facts::kServiceHid) != 0U) {
        return BleDeviceKind::Input;
    }
    if ((facts.knownServiceMask & Facts::kServiceHeartRate) != 0U) {
        return BleDeviceKind::Heart;
    }
    if ((facts.knownServiceMask & Facts::kServiceThermometer) != 0U) {
        return BleDeviceKind::Thermometer;
    }
    if ((facts.knownServiceMask & Facts::kServiceFitness) != 0U) {
        return BleDeviceKind::Fitness;
    }
    const char* name = observation.label.data();
    if (containsAsciiIgnoreCase(name, "airpod") ||
        containsAsciiIgnoreCase(name, "buds") ||
        containsAsciiIgnoreCase(name, "headphone") ||
        containsAsciiIgnoreCase(name, "headset") ||
        containsAsciiIgnoreCase(name, "beats")) {
        return BleDeviceKind::Audio;
    }
    if (containsAsciiIgnoreCase(name, "watch") ||
        containsAsciiIgnoreCase(name, "band") ||
        containsAsciiIgnoreCase(name, "amazfit") ||
        containsAsciiIgnoreCase(name, "fitbit")) {
        return BleDeviceKind::Watch;
    }
    if (containsAsciiIgnoreCase(name, "keyboard")) {
        return BleDeviceKind::Keyboard;
    }
    if (containsAsciiIgnoreCase(name, "mouse")) return BleDeviceKind::Mouse;
    if (containsAsciiIgnoreCase(name, "thermo") ||
        containsAsciiIgnoreCase(name, "lywsd") ||
        containsAsciiIgnoreCase(name, "atc_")) {
        return BleDeviceKind::Thermometer;
    }
    if (containsAsciiIgnoreCase(name, "iphone") ||
        containsAsciiIgnoreCase(name, "galaxy") ||
        containsAsciiIgnoreCase(name, "phone") ||
        containsAsciiIgnoreCase(name, "pixel") ||
        containsAsciiIgnoreCase(name, "redmi") ||
        containsAsciiIgnoreCase(name, "poco")) {
        return BleDeviceKind::Phone;
    }
    return BleDeviceKind::Unknown;
}

BleSubtype classifyBleSubtype(
        const domain::observations::Observation& observation) {
    using Facts = domain::observations::BleAdvertisementFacts;
    const Facts& facts = observation.bleAdvertisement;
    if (facts.companyKnown && facts.companyId == 0x004cU) {
        switch (facts.appleContinuityType) {
            case 0x02: return BleSubtype::IBeacon;
            case 0x05: return BleSubtype::AirDrop;
            case 0x07: return BleSubtype::AirPods;
            case 0x09:
            case 0x0a: return BleSubtype::AirPlay;
            case 0x0c: return BleSubtype::Handoff;
            case 0x0d:
            case 0x0e: return BleSubtype::Hotspot;
            case 0x12: return BleSubtype::FindMy;
            default: break;
        }
    }
    if ((facts.knownServiceMask & Facts::kServiceEddystone) != 0U) {
        return BleSubtype::Eddystone;
    }
    if ((facts.knownServiceMask & Facts::kServiceXiaomi) != 0U) {
        return BleSubtype::Xiaomi;
    }
    if ((facts.knownServiceMask & Facts::kServiceSmartTag) != 0U) {
        return BleSubtype::SmartTag;
    }
    if ((facts.knownServiceMask & Facts::kServiceTile) != 0U) {
        return BleSubtype::Tile;
    }
    if ((facts.knownServiceMask & Facts::kServiceFastPair) != 0U) {
        return BleSubtype::FastPair;
    }
    if ((facts.knownServiceMask & Facts::kServiceExposure) != 0U) {
        return BleSubtype::ExposureNotification;
    }
    return BleSubtype::None;
}

BleTrackerKind classifyBleTracker(
        const domain::observations::Observation& observation) {
    switch (classifyBleSubtype(observation)) {
        case BleSubtype::FindMy: return BleTrackerKind::FindMy;
        case BleSubtype::SmartTag: return BleTrackerKind::SmartTag;
        case BleSubtype::Tile: return BleTrackerKind::Tile;
        default: return BleTrackerKind::None;
    }
}

const char* bleSubtypeName(BleSubtype subtype) {
    switch (subtype) {
        case BleSubtype::IBeacon: return "iBeacon";
        case BleSubtype::AirDrop: return "AirDrop";
        case BleSubtype::AirPods: return "AirPods";
        case BleSubtype::AirPlay: return "AirPlay";
        case BleSubtype::Handoff: return "Handoff";
        case BleSubtype::Hotspot: return "Hotspot";
        case BleSubtype::FindMy: return "Find My";
        case BleSubtype::Eddystone: return "Eddystone";
        case BleSubtype::Xiaomi: return "Xiaomi";
        case BleSubtype::SmartTag: return "SmartTag";
        case BleSubtype::Tile: return "Tile";
        case BleSubtype::FastPair: return "Fast Pair";
        case BleSubtype::ExposureNotification: return "Exposure";
        case BleSubtype::None:
        default: return "";
    }
}

const char* bleServiceName(std::uint16_t mask) {
    using Facts = domain::observations::BleAdvertisementFacts;
    if ((mask & Facts::kServiceHid) != 0U) return "HID";
    if ((mask & Facts::kServiceBattery) != 0U) return "Battery";
    if ((mask & Facts::kServiceHeartRate) != 0U) return "Heart Rate";
    if ((mask & Facts::kServiceThermometer) != 0U) return "Thermometer";
    if ((mask & Facts::kServiceFitness) != 0U) return "Fitness";
    const BleSubtype subtype = (mask & Facts::kServiceEddystone) != 0U
        ? BleSubtype::Eddystone : (mask & Facts::kServiceXiaomi
            ? BleSubtype::Xiaomi : (mask & Facts::kServiceSmartTag
                ? BleSubtype::SmartTag : (mask & Facts::kServiceTile
                    ? BleSubtype::Tile : (mask & Facts::kServiceFastPair
                        ? BleSubtype::FastPair : (mask & Facts::kServiceExposure
                            ? BleSubtype::ExposureNotification
                            : BleSubtype::None)))));
    return bleSubtypeName(subtype);
}

}  // namespace leshy1::apps::ble
