#pragma once

#include "services/security/DeviceLock.h"
#include "services/security/ProtectedDataCipher.h"

namespace leshy1::platform::arduino {

class MbedTlsDeviceLockCrypto final
    : public services::security::DeviceLockCrypto {
public:
    bool fillRandom(std::uint8_t* output, std::size_t size) override;
    bool deriveVerifier(
        const char* pin, std::size_t pinLength,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockSaltBytes>& salt,
        std::uint32_t iterations,
        std::array<std::uint8_t,
                   services::security::kDeviceLockVerifierBytes>* output)
        override;
    bool deriveCredentialKeys(
        const char* pin, std::size_t pinLength,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockSaltBytes>& salt,
        std::uint32_t iterations,
        std::array<std::uint8_t,
                   services::security::kDeviceLockVerifierBytes>* verifier,
        std::array<std::uint8_t,
                   services::security::kDeviceLockWrappingKeyBytes>*
            wrappingKey) override;
    bool wrapDataKey(
        const std::array<std::uint8_t,
                         services::security::kDeviceLockWrappingKeyBytes>&
            wrappingKey,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockWrapNonceBytes>& nonce,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockDataKeyBytes>& dataKey,
        std::array<std::uint8_t,
                   services::security::kDeviceLockDataKeyBytes>* wrappedDataKey,
        std::array<std::uint8_t,
                   services::security::kDeviceLockAuthTagBytes>* tag) override;
    bool unwrapDataKey(
        const std::array<std::uint8_t,
                         services::security::kDeviceLockWrappingKeyBytes>&
            wrappingKey,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockWrapNonceBytes>& nonce,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockDataKeyBytes>&
            wrappedDataKey,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockAuthTagBytes>& tag,
        std::array<std::uint8_t,
                   services::security::kDeviceLockDataKeyBytes>* dataKey)
        override;
};

class MbedTlsProtectedDataCipher final
    : public services::security::ProtectedDataCipher {
public:
    bool fillNonce(
        std::array<std::uint8_t,
                   services::security::kDeviceLockWrapNonceBytes>* nonce)
        override;
    bool seal(
        const std::array<std::uint8_t,
                         services::security::kDeviceLockDataKeyBytes>& key,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockWrapNonceBytes>& nonce,
        const std::uint8_t* aad, std::size_t aadSize,
        const std::uint8_t* plaintext, std::size_t size,
        std::uint8_t* ciphertext,
        std::array<std::uint8_t,
                   services::security::kDeviceLockAuthTagBytes>* tag) override;
    bool open(
        const std::array<std::uint8_t,
                         services::security::kDeviceLockDataKeyBytes>& key,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockWrapNonceBytes>& nonce,
        const std::uint8_t* aad, std::size_t aadSize,
        const std::uint8_t* ciphertext, std::size_t size,
        const std::array<std::uint8_t,
                         services::security::kDeviceLockAuthTagBytes>& tag,
        std::uint8_t* plaintext) override;
};

class NvsDeviceLockStore final
    : public services::security::DeviceLockStore {
public:
    services::security::DeviceLockLoadStatus load(
        services::security::DeviceLockCredential* output) override;
    bool save(const services::security::DeviceLockCredential& credential)
        override;
    services::security::DeviceLockBootstrapStatus loadBootstrapDataKey(
        std::array<std::uint8_t,
                   services::security::kDeviceLockDataKeyBytes>* output)
        override;
    bool saveBootstrapDataKey(
        const std::array<std::uint8_t,
                         services::security::kDeviceLockDataKeyBytes>& key)
        override;
    bool clearBootstrapDataKey() override;
    bool disableCredential(
        const std::array<std::uint8_t,
                         services::security::kDeviceLockDataKeyBytes>& dataKey)
        override;
    bool clearCredentialAndLatch() override;

    // HIL may exercise the exact production codec and NVS transaction logic
    // in a dedicated namespace. It never reads, copies or erases the product
    // namespace, and every boot returns to the product namespace by default.
    void useHilFixtureNamespace(bool enabled);
    bool hilFixtureNamespaceActive() const {
        return hilFixtureNamespaceActive_;
    }
    bool hilFixtureStatePresent() const;

private:
    bool hilFixtureNamespaceActive_ = false;
};

}  // namespace leshy1::platform::arduino
