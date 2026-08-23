#pragma once

#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::apps::ble {

enum class BleDeviceKind : std::uint8_t {
    Unknown,
    Phone,
    Computer,
    Watch,
    Audio,
    Keyboard,
    Mouse,
    Input,
    Heart,
    Thermometer,
    Tag,
    Display,
    Fitness,
};

enum class BleSubtype : std::uint8_t {
    None,
    IBeacon,
    AirDrop,
    AirPods,
    AirPlay,
    Handoff,
    Hotspot,
    FindMy,
    Eddystone,
    Xiaomi,
    SmartTag,
    Tile,
    FastPair,
    ExposureNotification,
};

enum class BleTrackerKind : std::uint8_t {
    None,
    FindMy,
    SmartTag,
    Tile,
};

BleDeviceKind classifyBleDevice(
    const domain::observations::Observation& observation);
BleSubtype classifyBleSubtype(
    const domain::observations::Observation& observation);
BleTrackerKind classifyBleTracker(
    const domain::observations::Observation& observation);
const char* bleSubtypeName(BleSubtype subtype);
const char* bleServiceName(std::uint16_t knownServiceMask);

}  // namespace leshy1::apps::ble
