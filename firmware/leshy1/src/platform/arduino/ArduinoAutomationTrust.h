#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/automation/AutomationPackage.h"
#include "apps/automation/AutomationTrustStore.h"

namespace leshy1::platform::arduino {

class NvsAutomationTrustStore final
    : public apps::automation::AutomationTrustStoreBackend {
public:
    apps::automation::AutomationTrustLoadStatus load(
        apps::automation::AutomationTrustSnapshot* output) override;
    bool save(
        const apps::automation::AutomationTrustSnapshot& snapshot) override;
};

bool deriveAutomationP256KeyId(
    const std::array<std::uint8_t,
                     apps::automation::kAutomationP256PublicKeyBytes>& publicKey,
    std::array<std::uint8_t,
               apps::automation::kAutomationKeyIdBytes>* output);

bool validateAutomationP256PublicKey(
    const std::array<std::uint8_t,
                     apps::automation::kAutomationP256PublicKeyBytes>& publicKey);

class MbedTlsAutomationSignatureVerifier final
    : public apps::automation::AutomationSignatureVerifier {
public:
    explicit MbedTlsAutomationSignatureVerifier(
        const apps::automation::AutomationTrustStore& trustStore)
        : trustStore_(trustStore) {}

    apps::automation::AutomationTrustStatus verify(
        const std::uint8_t* signedBytes, std::size_t signedSize,
        const std::array<std::uint8_t,
                         apps::automation::kAutomationKeyIdBytes>& keyId,
        const std::array<std::uint8_t,
                         apps::automation::kAutomationSignatureBytes>& signature)
        override;

private:
    const apps::automation::AutomationTrustStore& trustStore_;
};

}  // namespace leshy1::platform::arduino
