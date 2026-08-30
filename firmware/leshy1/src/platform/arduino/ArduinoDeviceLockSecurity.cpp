#include "ArduinoDeviceLockSecurity.h"

#include <algorithm>
#include <array>
#include <cstring>

#include <esp_random.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <mbedtls/md.h>
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
constexpr std::uint32_t kDeviceLockKdfYieldInterval = 256U;

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
    const mbedtls_md_info_t* info =
        mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (info == nullptr || output->size() != 32U) return false;

    mbedtls_md_context_t context;
    mbedtls_md_init(&context);
    std::array<std::uint8_t, 32> u{};
    std::array<std::uint8_t, 32> block{};
    constexpr std::array<std::uint8_t, 4> blockIndex{{0U, 0U, 0U, 1U}};
    int status = mbedtls_md_setup(&context, info, 1);
    if (status == 0) {
        status = mbedtls_md_hmac_starts(
            &context, reinterpret_cast<const unsigned char*>(pin),
            pinLength);
    }
    if (status == 0) {
        status = mbedtls_md_hmac_update(
            &context, salt.data(), salt.size());
    }
    if (status == 0) {
        status = mbedtls_md_hmac_update(
            &context, blockIndex.data(), blockIndex.size());
    }
    if (status == 0) {
        status = mbedtls_md_hmac_finish(&context, u.data());
        block = u;
    }
    for (std::uint32_t iteration = 1U;
         status == 0 && iteration < iterations; ++iteration) {
        status = mbedtls_md_hmac_reset(&context);
        if (status == 0) {
            status = mbedtls_md_hmac_update(
                &context, u.data(), u.size());
        }
        if (status == 0) {
            status = mbedtls_md_hmac_finish(&context, u.data());
        }
        if (status == 0) {
            for (std::size_t index = 0; index < block.size(); ++index) {
                block[index] = static_cast<std::uint8_t>(
                    block[index] ^ u[index]);
            }
        }
        // The ESP-IDF Task WDT supervises each core's idle task. A monolithic
        // PBKDF2 call can starve idle0 even though loopTask on the other core
        // remains conceptually responsive. Blocking for one tick makes the
        // KDF cooperative without weakening the five-second safety watchdog.
        if (iteration % kDeviceLockKdfYieldInterval == 0U) {
            vTaskDelay(1);
        }
    }
    if (status == 0) *output = block;
    mbedtls_md_free(&context);
    volatile std::uint8_t* uBytes = u.data();
    volatile std::uint8_t* blockBytes = block.data();
    for (std::size_t index = 0; index < u.size(); ++index) {
        uBytes[index] = 0U;
        blockBytes[index] = 0U;
    }
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
