#include "BleInspectorExport.h"

#include <cstdio>

namespace leshy1::services::ble {
namespace {

constexpr const char* kSchema = "leshy.ble.inspector.capture.v1";

bool validCapture(const BleInspectorCapture& capture) {
    if (capture.state() != BleInspectorCaptureState::Frozen ||
        !validBleInspectorTarget(capture.target()) ||
        capture.size() > BleInspectorCapture::kRecordCapacity ||
        capture.counters().accepted != capture.size()) {
        return false;
    }
    std::uint64_t previousUs = capture.target().observedMonotonicUs;
    for (std::size_t index = 0U; index < capture.size(); ++index) {
        const BleInspectorRawAdvertisement* record = capture.at(index);
        if (record == nullptr || record->address != capture.target().address ||
            record->addressType != capture.target().addressType ||
            record->payloadLength > record->payload.size() ||
            record->monotonicUs < previousUs || record->rssiDbm < -127 ||
            record->rssiDbm > 20) {
            return false;
        }
        previousUs = record->monotonicUs;
    }
    return true;
}

BleInspectorExportStatus finishFormat(int written, std::size_t capacity,
                                      std::size_t* outputSize) {
    if (written < 0) return BleInspectorExportStatus::InvalidCapture;
    if (static_cast<std::size_t>(written) >= capacity) {
        return BleInspectorExportStatus::BufferTooSmall;
    }
    *outputSize = static_cast<std::size_t>(written);
    return BleInspectorExportStatus::Formatted;
}

BleInspectorExportStatus validateArguments(
        const BleInspectorCapture& capture, const char* output,
        std::size_t capacity, const std::size_t* outputSize) {
    if (output == nullptr || capacity == 0U || outputSize == nullptr) {
        return BleInspectorExportStatus::InvalidArgument;
    }
    if (capture.state() != BleInspectorCaptureState::Frozen) {
        return BleInspectorExportStatus::NotFrozen;
    }
    return validCapture(capture) ? BleInspectorExportStatus::Formatted
                                 : BleInspectorExportStatus::InvalidCapture;
}

}  // namespace

BleInspectorExportStatus formatBleInspectorExportHeader(
    const BleInspectorCapture& capture, char* output, std::size_t capacity,
    std::size_t* outputSize) {
    const BleInspectorExportStatus valid =
        validateArguments(capture, output, capacity, outputSize);
    if (valid != BleInspectorExportStatus::Formatted) return valid;
    const BleInspectorTarget& target = capture.target();
    const BleInspectorCaptureCounters& counters = capture.counters();
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"%s\",\"kind\":\"header\",\"version\":1,"
        "\"complete\":false,\"target\":\"%02X:%02X:%02X:%02X:%02X:%02X\","
        "\"address_type\":%u,\"selected_monotonic_us\":%llu,"
        "\"records\":%u,\"observed\":%lu,\"accepted\":%lu,"
        "\"different_target\":%lu,\"invalid\":%lu,\"dropped\":%lu}",
        kSchema, target.address[0], target.address[1], target.address[2],
        target.address[3], target.address[4], target.address[5],
        static_cast<unsigned>(target.addressType),
        static_cast<unsigned long long>(target.observedMonotonicUs),
        static_cast<unsigned>(capture.size()),
        static_cast<unsigned long>(counters.observed),
        static_cast<unsigned long>(counters.accepted),
        static_cast<unsigned long>(counters.differentTarget),
        static_cast<unsigned long>(counters.invalid),
        static_cast<unsigned long>(counters.dropped));
    return finishFormat(written, capacity, outputSize);
}

BleInspectorExportStatus formatBleInspectorExportRecord(
    const BleInspectorCapture& capture, std::size_t index,
    char* output, std::size_t capacity, std::size_t* outputSize) {
    const BleInspectorExportStatus valid =
        validateArguments(capture, output, capacity, outputSize);
    if (valid != BleInspectorExportStatus::Formatted) return valid;
    const BleInspectorRawAdvertisement* record = capture.at(index);
    if (record == nullptr) return BleInspectorExportStatus::InvalidArgument;
    constexpr char kHex[] = "0123456789ABCDEF";
    char payloadHex[drivers::ble::kLegacyAdvertisementPayloadCapacity * 2U + 1U]
        = {};
    for (std::size_t byte = 0U; byte < record->payloadLength; ++byte) {
        payloadHex[byte * 2U] = kHex[record->payload[byte] >> 4U];
        payloadHex[byte * 2U + 1U] = kHex[record->payload[byte] & 0x0fU];
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"%s\",\"kind\":\"record\",\"index\":%u,"
        "\"monotonic_us\":%llu,\"rssi_dbm\":%d,\"event_type\":%u,"
        "\"address_type\":%u,\"payload_length\":%u,"
        "\"payload_hex\":\"%s\"}",
        kSchema, static_cast<unsigned>(index),
        static_cast<unsigned long long>(record->monotonicUs),
        static_cast<int>(record->rssiDbm),
        static_cast<unsigned>(record->eventType),
        static_cast<unsigned>(record->addressType),
        static_cast<unsigned>(record->payloadLength), payloadHex);
    return finishFormat(written, capacity, outputSize);
}

BleInspectorExportStatus formatBleInspectorExportEnd(
    const BleInspectorCapture& capture, char* output, std::size_t capacity,
    std::size_t* outputSize) {
    const BleInspectorExportStatus valid =
        validateArguments(capture, output, capacity, outputSize);
    if (valid != BleInspectorExportStatus::Formatted) return valid;
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"%s\",\"kind\":\"end\",\"records\":%u,"
        "\"complete\":true}",
        kSchema, static_cast<unsigned>(capture.size()));
    return finishFormat(written, capacity, outputSize);
}

const char* bleInspectorExportStatusName(BleInspectorExportStatus status) {
    switch (status) {
        case BleInspectorExportStatus::Formatted: return "formatted";
        case BleInspectorExportStatus::InvalidArgument:
            return "invalid_argument";
        case BleInspectorExportStatus::NotFrozen: return "not_frozen";
        case BleInspectorExportStatus::InvalidCapture:
            return "invalid_capture";
        case BleInspectorExportStatus::BufferTooSmall:
            return "buffer_too_small";
    }
    return "invalid_capture";
}

}  // namespace leshy1::services::ble
