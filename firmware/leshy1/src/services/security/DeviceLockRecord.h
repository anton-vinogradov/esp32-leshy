#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/security/DeviceLock.h"

namespace leshy1::services::security {

constexpr std::size_t kDeviceLockRecordBytes = 68;
using DeviceLockRecord = std::array<std::uint8_t, kDeviceLockRecordBytes>;

// Stable little-endian NVS blob. CRC detects torn/corrupt records; PIN
// authenticity comes from the PBKDF2 verifier, not from this transport checksum.
bool encodeDeviceLockRecord(const DeviceLockCredential& credential,
                            DeviceLockRecord* output);
bool decodeDeviceLockRecord(const DeviceLockRecord& input,
                            DeviceLockCredential* output);

}  // namespace leshy1::services::security
