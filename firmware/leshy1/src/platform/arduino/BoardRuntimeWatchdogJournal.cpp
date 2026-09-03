#include "platform/arduino/BoardRuntimeWatchdogJournal.h"

#include <cstdio>
#include <cstring>

#include <ff.h>
#include <nvs.h>

namespace leshy1::platform::arduino {
namespace {

constexpr const char* kNamespace = "leshy1-crash";
constexpr const char* kRecordKey = "watchdog.v1";
constexpr const char* kSdSequenceKey = "sd.seq.v1";
constexpr const char* kRoot = "/leshy";
constexpr const char* kDiagnostics = "/leshy/diagnostics";
constexpr const char* kDiagnosticsV1 = "/leshy/diagnostics/v1";
constexpr std::size_t kMaximumJsonBytes = 512U;

class ScopedNvsHandle final {
public:
    ~ScopedNvsHandle() {
        if (open_) nvs_close(handle_);
    }

    esp_err_t open(const char* name, nvs_open_mode_t mode) {
        if (name == nullptr || open_) return ESP_ERR_INVALID_STATE;
        const esp_err_t status = nvs_open(name, mode, &handle_);
        open_ = status == ESP_OK;
        return status;
    }

    nvs_handle_t get() const { return handle_; }

private:
    nvs_handle_t handle_ = 0;
    bool open_ = false;
};

bool formatVolumePath(std::uint8_t driveNumber, const char* path,
                      char* output, std::size_t capacity) {
    if (driveNumber >= FF_VOLUMES || driveNumber > 9U || path == nullptr ||
        path[0] != '/' || output == nullptr || capacity == 0U) {
        return false;
    }
    const int written = std::snprintf(
        output, capacity, "%u:%s", static_cast<unsigned>(driveNumber), path);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool ensureDirectory(std::uint8_t driveNumber, const char* path) {
    char fullPath[96] = {};
    if (!formatVolumePath(driveNumber, path, fullPath, sizeof(fullPath))) {
        return false;
    }
    FILINFO information{};
    const FRESULT stat = f_stat(fullPath, &information);
    if (stat == FR_OK) return (information.fattrib & AM_DIR) != 0U;
    if (stat != FR_NO_FILE && stat != FR_NO_PATH) return false;
    const FRESULT created = f_mkdir(fullPath);
    if (created != FR_OK && created != FR_EXIST) return false;
    information = {};
    return f_stat(fullPath, &information) == FR_OK &&
        (information.fattrib & AM_DIR) != 0U;
}

bool exactFile(std::uint8_t driveNumber, const char* path,
               const char* expected, std::size_t size) {
    char fullPath[96] = {};
    if (!formatVolumePath(driveNumber, path, fullPath, sizeof(fullPath))) {
        return false;
    }
    FIL file{};
    if (f_open(&file, fullPath, FA_READ) != FR_OK) return false;
    const bool exactSize =
        static_cast<std::size_t>(f_size(&file)) == size;
    char buffer[kMaximumJsonBytes] = {};
    UINT read = 0;
    const FRESULT readStatus = exactSize
        ? f_read(&file, buffer, static_cast<UINT>(size), &read)
        : FR_INVALID_OBJECT;
    const FRESULT closeStatus = f_close(&file);
    return exactSize && readStatus == FR_OK && closeStatus == FR_OK &&
        static_cast<std::size_t>(read) == size &&
        std::memcmp(buffer, expected, size) == 0;
}

}  // namespace

const char* runtimeWatchdogJournalLoadStatusName(
    RuntimeWatchdogJournalLoadStatus status) {
    switch (status) {
        case RuntimeWatchdogJournalLoadStatus::Missing: return "missing";
        case RuntimeWatchdogJournalLoadStatus::Valid: return "valid";
        case RuntimeWatchdogJournalLoadStatus::Invalid: return "invalid";
        case RuntimeWatchdogJournalLoadStatus::IoError: return "io_error";
    }
    return "io_error";
}

const char* runtimeWatchdogJournalSdWriteStatusName(
    RuntimeWatchdogJournalSdWriteStatus status) {
    switch (status) {
        case RuntimeWatchdogJournalSdWriteStatus::Written: return "written";
        case RuntimeWatchdogJournalSdWriteStatus::AlreadyPresent:
            return "already_present";
        case RuntimeWatchdogJournalSdWriteStatus::InvalidInput:
            return "invalid_input";
        case RuntimeWatchdogJournalSdWriteStatus::DirectoryFailed:
            return "directory_failed";
        case RuntimeWatchdogJournalSdWriteStatus::OpenFailed:
            return "open_failed";
        case RuntimeWatchdogJournalSdWriteStatus::WriteFailed:
            return "write_failed";
        case RuntimeWatchdogJournalSdWriteStatus::SyncFailed:
            return "sync_failed";
        case RuntimeWatchdogJournalSdWriteStatus::VerifyFailed:
            return "verify_failed";
        case RuntimeWatchdogJournalSdWriteStatus::RenameFailed:
            return "rename_failed";
    }
    return "invalid_input";
}

RuntimeWatchdogJournalLoadStatus BoardRuntimeWatchdogJournal::load(
    kernel::safety::RuntimeWatchdogJournalRecord* output) const {
    if (output == nullptr) return RuntimeWatchdogJournalLoadStatus::Invalid;
    *output = {};
    ScopedNvsHandle storage;
    const esp_err_t openStatus = storage.open(kNamespace, NVS_READONLY);
    if (openStatus != ESP_OK) {
        return openStatus == ESP_ERR_NVS_NOT_FOUND
            ? RuntimeWatchdogJournalLoadStatus::Missing
            : RuntimeWatchdogJournalLoadStatus::IoError;
    }
    std::size_t stored = 0U;
    const esp_err_t sizeStatus =
        nvs_get_blob(storage.get(), kRecordKey, nullptr, &stored);
    if (sizeStatus == ESP_ERR_NVS_NOT_FOUND) {
        return RuntimeWatchdogJournalLoadStatus::Missing;
    }
    if (sizeStatus != ESP_OK) return RuntimeWatchdogJournalLoadStatus::IoError;
    if (stored != sizeof(*output)) {
        return RuntimeWatchdogJournalLoadStatus::Invalid;
    }
    return nvs_get_blob(storage.get(), kRecordKey, output, &stored) == ESP_OK &&
            stored == sizeof(*output)
        ? RuntimeWatchdogJournalLoadStatus::Valid
        : RuntimeWatchdogJournalLoadStatus::IoError;
}

bool BoardRuntimeWatchdogJournal::save(
    const kernel::safety::RuntimeWatchdogJournalRecord& record) const {
    ScopedNvsHandle storage;
    if (storage.open(kNamespace, NVS_READWRITE) != ESP_OK ||
        nvs_set_blob(storage.get(), kRecordKey, &record, sizeof(record)) !=
            ESP_OK ||
        nvs_commit(storage.get()) != ESP_OK) {
        return false;
    }
    kernel::safety::RuntimeWatchdogJournalRecord verified{};
    return load(&verified) == RuntimeWatchdogJournalLoadStatus::Valid &&
        std::memcmp(&verified, &record, sizeof(record)) == 0;
}

std::uint32_t BoardRuntimeWatchdogJournal::loadSdMirroredSequence() const {
    ScopedNvsHandle storage;
    if (storage.open(kNamespace, NVS_READONLY) != ESP_OK) return 0U;
    std::uint32_t sequence = 0U;
    return nvs_get_u32(storage.get(), kSdSequenceKey, &sequence) == ESP_OK
        ? sequence : 0U;
}

bool BoardRuntimeWatchdogJournal::saveSdMirroredSequence(
    std::uint32_t sequence) const {
    if (sequence == 0U) return false;
    ScopedNvsHandle storage;
    return storage.open(kNamespace, NVS_READWRITE) == ESP_OK &&
        nvs_set_u32(storage.get(), kSdSequenceKey, sequence) == ESP_OK &&
        nvs_commit(storage.get()) == ESP_OK &&
        loadSdMirroredSequence() == sequence;
}

RuntimeWatchdogJournalSdWriteStatus BoardRuntimeWatchdogJournal::writeSd(
    std::uint8_t driveNumber, std::uint32_t sequence,
    const char* json, std::size_t size) const {
    if (driveNumber >= FF_VOLUMES || driveNumber > 9U || sequence == 0U ||
        json == nullptr || size == 0U || size > kMaximumJsonBytes) {
        return RuntimeWatchdogJournalSdWriteStatus::InvalidInput;
    }
    if (!ensureDirectory(driveNumber, kRoot) ||
        !ensureDirectory(driveNumber, kDiagnostics) ||
        !ensureDirectory(driveNumber, kDiagnosticsV1)) {
        return RuntimeWatchdogJournalSdWriteStatus::DirectoryFailed;
    }

    char relativeFinal[64] = {};
    char relativeTemporary[64] = {};
    const int finalLength = std::snprintf(
        relativeFinal, sizeof(relativeFinal),
        "/leshy/diagnostics/v1/watchdog-%08lx.json",
        static_cast<unsigned long>(sequence));
    const int temporaryLength = std::snprintf(
        relativeTemporary, sizeof(relativeTemporary),
        "/leshy/diagnostics/v1/watchdog-%08lx.tmp",
        static_cast<unsigned long>(sequence));
    if (finalLength <= 0 || temporaryLength <= 0 ||
        static_cast<std::size_t>(finalLength) >= sizeof(relativeFinal) ||
        static_cast<std::size_t>(temporaryLength) >= sizeof(relativeTemporary)) {
        return RuntimeWatchdogJournalSdWriteStatus::InvalidInput;
    }
    if (exactFile(driveNumber, relativeFinal, json, size)) {
        return RuntimeWatchdogJournalSdWriteStatus::AlreadyPresent;
    }

    char fullTemporary[96] = {};
    char fullFinal[96] = {};
    if (!formatVolumePath(driveNumber, relativeTemporary, fullTemporary,
                          sizeof(fullTemporary)) ||
        !formatVolumePath(driveNumber, relativeFinal, fullFinal,
                          sizeof(fullFinal))) {
        return RuntimeWatchdogJournalSdWriteStatus::InvalidInput;
    }
    (void)f_unlink(fullTemporary);
    FIL file{};
    if (f_open(&file, fullTemporary, FA_WRITE | FA_CREATE_ALWAYS) != FR_OK) {
        return RuntimeWatchdogJournalSdWriteStatus::OpenFailed;
    }
    UINT written = 0U;
    const FRESULT writeStatus = f_write(
        &file, json, static_cast<UINT>(size), &written);
    if (writeStatus != FR_OK ||
        static_cast<std::size_t>(written) != size) {
        (void)f_close(&file);
        (void)f_unlink(fullTemporary);
        return RuntimeWatchdogJournalSdWriteStatus::WriteFailed;
    }
    const FRESULT syncStatus = f_sync(&file);
    const FRESULT closeStatus = f_close(&file);
    if (syncStatus != FR_OK || closeStatus != FR_OK) {
        (void)f_unlink(fullTemporary);
        return RuntimeWatchdogJournalSdWriteStatus::SyncFailed;
    }
    if (!exactFile(driveNumber, relativeTemporary, json, size)) {
        (void)f_unlink(fullTemporary);
        return RuntimeWatchdogJournalSdWriteStatus::VerifyFailed;
    }
    if (f_rename(fullTemporary, fullFinal) != FR_OK) {
        (void)f_unlink(fullTemporary);
        return exactFile(driveNumber, relativeFinal, json, size)
            ? RuntimeWatchdogJournalSdWriteStatus::AlreadyPresent
            : RuntimeWatchdogJournalSdWriteStatus::RenameFailed;
    }
    return exactFile(driveNumber, relativeFinal, json, size)
        ? RuntimeWatchdogJournalSdWriteStatus::Written
        : RuntimeWatchdogJournalSdWriteStatus::VerifyFailed;
}

}  // namespace leshy1::platform::arduino
