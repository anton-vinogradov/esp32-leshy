#pragma once

#include <cstddef>

#include "services/ble/BleInspector.h"

namespace leshy1::services::ble {

enum class BleInspectorExportStatus : std::uint8_t {
    Formatted,
    InvalidArgument,
    NotFrozen,
    InvalidCapture,
    BufferTooSmall,
};

// Versioned, line-oriented local export. The caller freezes the capture first,
// then writes one header, each record, and one terminal line. This keeps the
// formatter allocation-free and lets USB/Web adapters stream without holding a
// second copy of the bounded packet set.
BleInspectorExportStatus formatBleInspectorExportHeader(
    const BleInspectorCapture& capture, char* output, std::size_t capacity,
    std::size_t* outputSize);
BleInspectorExportStatus formatBleInspectorExportRecord(
    const BleInspectorCapture& capture, std::size_t index,
    char* output, std::size_t capacity, std::size_t* outputSize);
BleInspectorExportStatus formatBleInspectorExportEnd(
    const BleInspectorCapture& capture, char* output, std::size_t capacity,
    std::size_t* outputSize);

const char* bleInspectorExportStatusName(BleInspectorExportStatus status);

}  // namespace leshy1::services::ble
