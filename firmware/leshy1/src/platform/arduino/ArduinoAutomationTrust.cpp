#include "ArduinoAutomationTrust.h"

#include <algorithm>
#include <cstring>

#include <mbedtls/bignum.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/ecp.h>
#include <mbedtls/sha256.h>
#include <nvs.h>

namespace leshy1::platform::arduino {
namespace {

using apps::automation::AutomationTrustLoadStatus;
using apps::automation::AutomationTrustRecord;
using apps::automation::AutomationTrustSnapshot;
using apps::automation::AutomationTrustStatus;

constexpr const char* kNamespace = "leshy1-auto";
constexpr const char* kTrustRecordKey = "trust.v1";

class ScopedNvsHandle final {
public:
    ~ScopedNvsHandle() {
        if (open_) nvs_close(handle_);
    }

    bool open(nvs_open_mode_t mode, esp_err_t* status) {
        if (status == nullptr || open_) return false;
        *status = nvs_open(kNamespace, mode, &handle_);
        open_ = *status == ESP_OK;
        return open_;
    }

    nvs_handle_t get() const { return handle_; }

private:
    nvs_handle_t handle_ = 0;
    bool open_ = false;
};

bool constantTimeEqual(
    const std::array<std::uint8_t,
                     apps::automation::kAutomationKeyIdBytes>& left,
    const std::array<std::uint8_t,
                     apps::automation::kAutomationKeyIdBytes>& right) {
    std::uint8_t difference = 0U;
    for (std::size_t index = 0U; index < left.size(); ++index) {
        difference = static_cast<std::uint8_t>(
            difference | static_cast<std::uint8_t>(left[index] ^ right[index]));
    }
    return difference == 0U;
}

bool sha256(const std::uint8_t* bytes, std::size_t size,
            std::array<std::uint8_t, 32U>* output) {
    if (bytes == nullptr || size == 0U || output == nullptr) return false;
    output->fill(0U);
    mbedtls_sha256_context context;
    mbedtls_sha256_init(&context);
    const bool valid = mbedtls_sha256_starts(&context, 0) == 0 &&
        mbedtls_sha256_update(&context, bytes, size) == 0 &&
        mbedtls_sha256_finish(&context, output->data()) == 0;
    mbedtls_sha256_free(&context);
    if (!valid) output->fill(0U);
    return valid;
}

}  // namespace

AutomationTrustLoadStatus NvsAutomationTrustStore::load(
    AutomationTrustSnapshot* output) {
    if (output == nullptr) return AutomationTrustLoadStatus::Error;
    *output = {};
    ScopedNvsHandle storage;
    esp_err_t openStatus = ESP_FAIL;
    if (!storage.open(NVS_READONLY, &openStatus)) {
        return openStatus == ESP_ERR_NVS_NOT_FOUND
            ? AutomationTrustLoadStatus::Missing
            : AutomationTrustLoadStatus::Error;
    }
    std::size_t stored = 0U;
    const esp_err_t sizeStatus =
        nvs_get_blob(storage.get(), kTrustRecordKey, nullptr, &stored);
    if (sizeStatus == ESP_ERR_NVS_NOT_FOUND) {
        return AutomationTrustLoadStatus::Missing;
    }
    if (sizeStatus != ESP_OK) return AutomationTrustLoadStatus::Error;
    if (stored != apps::automation::kAutomationTrustRecordBytes) {
        return AutomationTrustLoadStatus::Corrupt;
    }
    AutomationTrustRecord record{};
    if (nvs_get_blob(storage.get(), kTrustRecordKey, record.data(), &stored) !=
            ESP_OK ||
        stored != record.size() ||
        !apps::automation::decodeAutomationTrustRecord(record, output)) {
        *output = {};
        return AutomationTrustLoadStatus::Corrupt;
    }
    return AutomationTrustLoadStatus::Loaded;
}

bool NvsAutomationTrustStore::save(const AutomationTrustSnapshot& snapshot) {
    AutomationTrustRecord record{};
    if (!apps::automation::encodeAutomationTrustRecord(snapshot, &record)) {
        return false;
    }
    ScopedNvsHandle storage;
    esp_err_t openStatus = ESP_FAIL;
    if (!storage.open(NVS_READWRITE, &openStatus) ||
        nvs_set_blob(storage.get(), kTrustRecordKey, record.data(),
                     record.size()) != ESP_OK ||
        nvs_commit(storage.get()) != ESP_OK) {
        return false;
    }
    AutomationTrustSnapshot verified{};
    AutomationTrustRecord verifiedRecord{};
    return load(&verified) == AutomationTrustLoadStatus::Loaded &&
        apps::automation::encodeAutomationTrustRecord(
            verified, &verifiedRecord) &&
        verifiedRecord == record;
}

bool deriveAutomationP256KeyId(
    const std::array<std::uint8_t,
                     apps::automation::kAutomationP256PublicKeyBytes>& publicKey,
    std::array<std::uint8_t,
               apps::automation::kAutomationKeyIdBytes>* output) {
    if (output == nullptr || publicKey[0] != 0x04U) return false;
    std::array<std::uint8_t, 32U> digest{};
    const bool hashed = sha256(publicKey.data(), publicKey.size(), &digest);
    if (hashed) {
        std::copy_n(digest.begin(), output->size(), output->begin());
    } else {
        output->fill(0U);
    }
    volatile std::uint8_t* cursor = digest.data();
    for (std::size_t index = 0U; index < digest.size(); ++index) {
        cursor[index] = 0U;
    }
    return hashed;
}

bool validateAutomationP256PublicKey(
    const std::array<std::uint8_t,
                     apps::automation::kAutomationP256PublicKeyBytes>& publicKey) {
    if (publicKey[0] != 0x04U) return false;
    mbedtls_ecp_group group;
    mbedtls_ecp_point point;
    mbedtls_ecp_group_init(&group);
    mbedtls_ecp_point_init(&point);
    int status = mbedtls_ecp_group_load(
        &group, MBEDTLS_ECP_DP_SECP256R1);
    if (status == 0) {
        status = mbedtls_ecp_point_read_binary(
            &group, &point, publicKey.data(), publicKey.size());
    }
    if (status == 0) status = mbedtls_ecp_check_pubkey(&group, &point);
    mbedtls_ecp_point_free(&point);
    mbedtls_ecp_group_free(&group);
    return status == 0;
}

AutomationTrustStatus MbedTlsAutomationSignatureVerifier::verify(
    const std::uint8_t* signedBytes, std::size_t signedSize,
    const std::array<std::uint8_t,
                     apps::automation::kAutomationKeyIdBytes>& keyId,
    const std::array<std::uint8_t,
                     apps::automation::kAutomationSignatureBytes>& signature) {
    if (signedBytes == nullptr || signedSize == 0U || !trustStore_.ready()) {
        return AutomationTrustStatus::VerifierUnavailable;
    }
    const apps::automation::AutomationTrustedKey* key =
        apps::automation::findAutomationTrustedKey(
            trustStore_.snapshot(), keyId);
    if (key == nullptr) return AutomationTrustStatus::UnknownSigner;
    std::array<std::uint8_t, apps::automation::kAutomationKeyIdBytes>
        derivedKeyId{};
    if (!validateAutomationP256PublicKey(key->publicKey) ||
        !deriveAutomationP256KeyId(key->publicKey, &derivedKeyId) ||
        !constantTimeEqual(derivedKeyId, keyId)) {
        return AutomationTrustStatus::InvalidSignature;
    }

    std::array<std::uint8_t, 32U> digest{};
    mbedtls_ecp_group group;
    mbedtls_ecp_point point;
    mbedtls_mpi r;
    mbedtls_mpi s;
    mbedtls_ecp_group_init(&group);
    mbedtls_ecp_point_init(&point);
    mbedtls_mpi_init(&r);
    mbedtls_mpi_init(&s);
    int status = sha256(signedBytes, signedSize, &digest) ? 0 : -1;
    if (status == 0) {
        status = mbedtls_ecp_group_load(
            &group, MBEDTLS_ECP_DP_SECP256R1);
    }
    if (status == 0) {
        status = mbedtls_ecp_point_read_binary(
            &group, &point, key->publicKey.data(), key->publicKey.size());
    }
    if (status == 0) status = mbedtls_ecp_check_pubkey(&group, &point);
    if (status == 0) {
        status = mbedtls_mpi_read_binary(
            &r, signature.data(), signature.size() / 2U);
    }
    if (status == 0) {
        status = mbedtls_mpi_read_binary(
            &s, signature.data() + signature.size() / 2U,
            signature.size() / 2U);
    }
    if (status == 0) {
        status = mbedtls_ecdsa_verify(
            &group, digest.data(), digest.size(), &point, &r, &s);
    }
    mbedtls_mpi_free(&s);
    mbedtls_mpi_free(&r);
    mbedtls_ecp_point_free(&point);
    mbedtls_ecp_group_free(&group);
    volatile std::uint8_t* cursor = digest.data();
    for (std::size_t index = 0U; index < digest.size(); ++index) {
        cursor[index] = 0U;
    }
    return status == 0 ? AutomationTrustStatus::VerifiedTrusted
                       : AutomationTrustStatus::InvalidSignature;
}

}  // namespace leshy1::platform::arduino
