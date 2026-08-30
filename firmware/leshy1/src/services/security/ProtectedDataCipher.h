#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/security/DeviceLock.h"

namespace leshy1::services::security {

class ProtectedDataCipher {
public:
    virtual ~ProtectedDataCipher() = default;
    virtual bool fillNonce(
        std::array<std::uint8_t, kDeviceLockWrapNonceBytes>* nonce) = 0;
    virtual bool seal(
        const std::array<std::uint8_t, kDeviceLockDataKeyBytes>& key,
        const std::array<std::uint8_t, kDeviceLockWrapNonceBytes>& nonce,
        const std::uint8_t* aad, std::size_t aadSize,
        const std::uint8_t* plaintext, std::size_t size,
        std::uint8_t* ciphertext,
        std::array<std::uint8_t, kDeviceLockAuthTagBytes>* tag) = 0;
    virtual bool open(
        const std::array<std::uint8_t, kDeviceLockDataKeyBytes>& key,
        const std::array<std::uint8_t, kDeviceLockWrapNonceBytes>& nonce,
        const std::uint8_t* aad, std::size_t aadSize,
        const std::uint8_t* ciphertext, std::size_t size,
        const std::array<std::uint8_t, kDeviceLockAuthTagBytes>& tag,
        std::uint8_t* plaintext) = 0;
};

}  // namespace leshy1::services::security
