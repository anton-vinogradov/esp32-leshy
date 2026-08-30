#pragma once

#include "services/security/DeviceLock.h"

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
};

class NvsDeviceLockStore final
    : public services::security::DeviceLockStore {
public:
    services::security::DeviceLockLoadStatus load(
        services::security::DeviceLockCredential* output) override;
    bool save(const services::security::DeviceLockCredential& credential)
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
