#include "ArduinoDeviceLockSecurity.h"

#include <algorithm>
#include <array>
#include <cstring>

#include <esp_random.h>
#include <mbedtls/md.h>
#include <mbedtls/pkcs5.h>
#include <nvs.h>

#include "services/security/DeviceLockRecord.h"

namespace leshy1::platform::arduino {
namespace {

using services::security::DeviceLockCredential;
using services::security::DeviceLockLoadStatus;

constexpr const char* kNamespace = "leshy1-lock";
constexpr const char* kCredentialKey = "credential.v1";
constexpr const char* kProvisionedLatchKey = "enrolled.v1";
constexpr std::uint32_t kProvisionedLatch = 0x4c4f434bU;

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

bool eraseKeyIfPresent(nvs_handle_t handle, const char* key) {
    const esp_err_t status = nvs_erase_key(handle, key);
    return status == ESP_OK || status == ESP_ERR_NVS_NOT_FOUND;
}

}  // namespace

bool MbedTlsDeviceLockCrypto::fillRandom(std::uint8_t* output,
                                        std::size_t size) {
    if (output == nullptr || size == 0) return false;
    esp_fill_random(output, size);
    std::uint8_t combined = 0;
    for (std::size_t index = 0; index < size; ++index) {
        combined = static_cast<std::uint8_t>(combined | output[index]);
    }
    return combined != 0;
}

bool MbedTlsDeviceLockCrypto::deriveVerifier(
    const char* pin, std::size_t pinLength,
    const std::array<std::uint8_t,
                     services::security::kDeviceLockSaltBytes>& salt,
    std::uint32_t iterations,
    std::array<std::uint8_t,
               services::security::kDeviceLockVerifierBytes>* output) {
    if (pin == nullptr || output == nullptr ||
        iterations != services::security::kDeviceLockPbkdf2Iterations) {
        return false;
    }
    output->fill(0);
    const int status = mbedtls_pkcs5_pbkdf2_hmac_ext(
        MBEDTLS_MD_SHA256,
        reinterpret_cast<const unsigned char*>(pin), pinLength,
        salt.data(), salt.size(), iterations,
        static_cast<std::uint32_t>(output->size()), output->data());
    if (status != 0) output->fill(0);
    return status == 0;
}

DeviceLockLoadStatus NvsDeviceLockStore::load(
    DeviceLockCredential* output) {
    if (output == nullptr) return DeviceLockLoadStatus::Error;
    output->clear();
    ScopedNvsHandle storage;
    esp_err_t openStatus = ESP_FAIL;
    if (!storage.open(NVS_READONLY, &openStatus)) {
        if (openStatus == ESP_ERR_NVS_NOT_FOUND) {
            return DeviceLockLoadStatus::MissingVirgin;
        }
        return DeviceLockLoadStatus::Error;
    }

    std::uint32_t latch = 0;
    const esp_err_t latchStatus =
        nvs_get_u32(storage.get(), kProvisionedLatchKey, &latch);
    const bool latchPresent = latchStatus == ESP_OK;
    if (latchStatus != ESP_OK && latchStatus != ESP_ERR_NVS_NOT_FOUND) {
        return DeviceLockLoadStatus::Error;
    }

    std::size_t stored = 0;
    const esp_err_t lengthStatus =
        nvs_get_blob(storage.get(), kCredentialKey, nullptr, &stored);
    const bool recordPresent = lengthStatus == ESP_OK;
    if (lengthStatus != ESP_OK && lengthStatus != ESP_ERR_NVS_NOT_FOUND) {
        return DeviceLockLoadStatus::Error;
    }
    services::security::DeviceLockRecord record{};
    if (latchPresent && latch != kProvisionedLatch) {
        return DeviceLockLoadStatus::Corrupt;
    }
    if (!recordPresent) {
        return latchPresent ? DeviceLockLoadStatus::MissingExpected
                            : DeviceLockLoadStatus::MissingVirgin;
    }
    // A first-time enrollment interrupted after publishing the verifier but
    // before publishing the independent latch must never unlock the device.
    if (!latchPresent) {
        return DeviceLockLoadStatus::Corrupt;
    }
    if (stored != record.size() ||
        nvs_get_blob(storage.get(), kCredentialKey, record.data(), &stored) !=
            ESP_OK ||
        stored != record.size() ||
        !services::security::decodeDeviceLockRecord(record, output)) {
        return DeviceLockLoadStatus::Corrupt;
    }
    return DeviceLockLoadStatus::Loaded;
}

bool NvsDeviceLockStore::save(
    const DeviceLockCredential& credential) {
    services::security::DeviceLockRecord record{};
    if (!services::security::encodeDeviceLockRecord(credential, &record)) {
        return false;
    }
    ScopedNvsHandle storage;
    esp_err_t openStatus = ESP_FAIL;
    if (!storage.open(NVS_READWRITE, &openStatus)) return false;
    // Commit the credential before the independent provisioned latch. A
    // power cut can therefore produce only virgin, corrupt or fully loaded —
    // never an apparently valid empty credential.
    if (nvs_set_blob(storage.get(), kCredentialKey, record.data(),
                     record.size()) != ESP_OK ||
        nvs_commit(storage.get()) != ESP_OK ||
        nvs_set_u32(storage.get(), kProvisionedLatchKey,
                    kProvisionedLatch) != ESP_OK ||
        nvs_commit(storage.get()) != ESP_OK) {
        return false;
    }
    DeviceLockCredential verified{};
    const bool exact = load(&verified) == DeviceLockLoadStatus::Loaded &&
        verified.schemaVersion == credential.schemaVersion &&
        verified.failedAttempts == credential.failedAttempts &&
        verified.iterations == credential.iterations &&
        verified.generation == credential.generation &&
        verified.salt == credential.salt &&
        verified.verifier == credential.verifier;
    verified.clear();
    return exact;
}

bool NvsDeviceLockStore::clearCredentialAndLatch() {
    ScopedNvsHandle storage;
    esp_err_t openStatus = ESP_FAIL;
    if (!storage.open(NVS_READWRITE, &openStatus)) return false;
    // Keep the latch until protected state and the verifier are durably gone.
    // A reset between these commits is MissingExpected and remains locked.
    if (!eraseKeyIfPresent(storage.get(), kCredentialKey) ||
        nvs_commit(storage.get()) != ESP_OK ||
        !eraseKeyIfPresent(storage.get(), kProvisionedLatchKey) ||
        nvs_commit(storage.get()) != ESP_OK) {
        return false;
    }
    DeviceLockCredential discarded{};
    return load(&discarded) == DeviceLockLoadStatus::MissingVirgin;
}

}  // namespace leshy1::platform::arduino
