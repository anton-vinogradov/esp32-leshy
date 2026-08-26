#include "ArduinoFsSessionStoreIo.h"

#include <cstdio>
#include <cstring>

namespace leshy1::platform::arduino {
namespace {

constexpr const char* kScratchParent = "/leshy-hil";
constexpr const char* kProductParent = "/leshy";
constexpr const char* kProductSessionsParent = "/leshy/sessions";

const char* fresultName(FRESULT result) {
    switch (result) {
        case FR_OK: return "ok";
        case FR_DISK_ERR: return "disk_error";
        case FR_INT_ERR: return "internal_error";
        case FR_NOT_READY: return "not_ready";
        case FR_NO_FILE: return "no_file";
        case FR_NO_PATH: return "no_path";
        case FR_INVALID_NAME: return "invalid_name";
        case FR_DENIED: return "denied";
        case FR_EXIST: return "exists";
        case FR_INVALID_OBJECT: return "invalid_object";
        case FR_WRITE_PROTECTED: return "write_protected";
        case FR_INVALID_DRIVE: return "invalid_drive";
        case FR_NOT_ENABLED: return "not_enabled";
        case FR_NO_FILESYSTEM: return "no_filesystem";
        case FR_MKFS_ABORTED: return "mkfs_aborted";
        case FR_TIMEOUT: return "timeout";
        case FR_LOCKED: return "locked";
        case FR_NOT_ENOUGH_CORE: return "not_enough_core";
        case FR_TOO_MANY_OPEN_FILES: return "too_many_open_files";
        case FR_INVALID_PARAMETER: return "invalid_parameter";
    }
    return "unknown";
}

}  // namespace

const char* ArduinoFsSessionStoreIo::lastFresultName() const {
    return fresultName(lastFresult_);
}

void ArduinoFsSessionStoreIo::recordFailure(const char* stage, FRESULT result) {
    lastFailure_ = stage;
    lastFresult_ = result;
}

bool ArduinoFsSessionStoreIo::progress(const char* stage) {
    if (progressCallback_ == nullptr || progressCallback_()) return true;
    recordFailure(stage, FR_TIMEOUT);
    return false;
}

bool ArduinoFsSessionStoreIo::safeRelativePath(const char* path) const {
    if (path == nullptr || path[0] == '\0') return false;
    for (std::size_t index = 0; index < storage::kSessionStorePathMax; ++index) {
        const char value = path[index];
        if (value == '\0') return index != 0;
        const bool alphanumeric =
            (value >= 'a' && value <= 'z') ||
            (value >= 'A' && value <= 'Z') ||
            (value >= '0' && value <= '9');
        if (!alphanumeric && value != '-' && value != '_' && value != '.') {
            return false;
        }
    }
    return false;
}

bool ArduinoFsSessionStoreIo::formatVolumePath(
    const char* path, char* output, std::size_t capacity) const {
    if (path == nullptr || path[0] != '/' || output == nullptr || capacity == 0 ||
        driveNumber_ >= FF_VOLUMES || driveNumber_ > 9) {
        return false;
    }
    const int written = std::snprintf(output, capacity, "%u:%s",
                                      static_cast<unsigned>(driveNumber_), path);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool ArduinoFsSessionStoreIo::formatFullPath(
    const char* path, char* output, std::size_t capacity) const {
    if (!ready_ || !safeRelativePath(path) || output == nullptr || capacity == 0 ||
        driveNumber_ >= FF_VOLUMES || driveNumber_ > 9) {
        return false;
    }
    const int written = std::snprintf(output, capacity, "%u:%s/%s",
                                      static_cast<unsigned>(driveNumber_),
                                      rootPath_, path);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool ArduinoFsSessionStoreIo::directoryExists(const char* path) const {
    char fullPath[kFullPathCapacity] = {};
    if (!formatVolumePath(path, fullPath, sizeof(fullPath))) return false;
    workspace_.information = {};
    return f_stat(fullPath, &workspace_.information) == FR_OK &&
           (workspace_.information.fattrib & AM_DIR) != 0;
}

bool ArduinoFsSessionStoreIo::ensureDirectory(const char* path) {
    if (directoryExists(path)) return true;
    char fullPath[kFullPathCapacity] = {};
    if (!formatVolumePath(path, fullPath, sizeof(fullPath))) {
        recordFailure("directory_path", FR_INVALID_NAME);
        return false;
    }
    const FRESULT created = f_mkdir(fullPath);
    if (created != FR_OK && created != FR_EXIST) {
        recordFailure("directory_create", created);
        return false;
    }
    if (!directoryExists(path)) {
        recordFailure("directory_verify", created);
        return false;
    }
    return true;
}

bool ArduinoFsSessionStoreIo::prepare(const storage::WritePermit& permit) {
    lastFailure_ = "none";
    lastFresult_ = FR_OK;
    if (ready_ || driveNumber_ >= FF_VOLUMES || !permit.allowed() ||
        permit.byteLimit == 0 ||
        std::strncmp(permit.scratchPath, storage::kScratchRoot,
                     std::strlen(storage::kScratchRoot)) != 0 ||
        std::strlen(permit.scratchPath) >= sizeof(rootPath_) ||
        directoryExists(permit.scratchPath)) {
        recordFailure("prepare_precondition", FR_INVALID_PARAMETER);
        return false;
    }
    if (!ensureDirectory(kScratchParent)) {
        if (std::strcmp(lastFailure_, "none") == 0) {
            recordFailure("parent_directory", FR_INT_ERR);
        }
        return false;
    }
    if (!ensureDirectory(permit.scratchPath)) {
        if (std::strcmp(lastFailure_, "none") == 0) {
            recordFailure("scratch_directory", FR_INT_ERR);
        }
        return false;
    }
    std::strcpy(rootPath_, permit.scratchPath);
    byteLimit_ = permit.byteLimit;
    ready_ = true;
    writable_ = true;
    return true;
}

bool ArduinoFsSessionStoreIo::prepare(
    const storage::ProductStorePermit& permit) {
    lastFailure_ = "none";
    lastFresult_ = FR_OK;
    if (ready_ || driveNumber_ >= FF_VOLUMES || !permit.allowed() ||
        !permit.writable || permit.byteLimit == 0 ||
        permit.operation != storage::ProductStoreOperation::InitializeStore ||
        permit.rootPath == nullptr ||
        std::strcmp(permit.rootPath, storage::kProductSessionStoreRoot) != 0 ||
        directoryExists(permit.rootPath)) {
        recordFailure("product_prepare_precondition", FR_INVALID_PARAMETER);
        return false;
    }
    if (!ensureDirectory(kProductParent) ||
        !ensureDirectory(kProductSessionsParent) ||
        !ensureDirectory(permit.rootPath)) {
        if (std::strcmp(lastFailure_, "none") == 0) {
            recordFailure("product_directory", FR_INT_ERR);
        }
        return false;
    }
    std::strcpy(rootPath_, permit.rootPath);
    byteLimit_ = permit.byteLimit;
    ready_ = true;
    writable_ = true;
    return true;
}

bool ArduinoFsSessionStoreIo::openExistingWritable(
    const storage::ProductStorePermit& permit) {
    return permit.allowed() && permit.writable && permit.byteLimit != 0 &&
           permit.operation == storage::ProductStoreOperation::CommitSession &&
           openExistingPath(permit.rootPath, permit.byteLimit, true, true);
}

bool ArduinoFsSessionStoreIo::openExistingReadOnly(
    const storage::WritePermit& permit) {
    return permit.allowed() && permit.byteLimit != 0 &&
           openExistingPath(permit.scratchPath, permit.byteLimit, false, false);
}

bool ArduinoFsSessionStoreIo::openExistingReadOnly(
    const storage::ReadPermit& permit) {
    return permit.allowed() &&
           openExistingPath(permit.scratchPath, 0, false, false);
}

bool ArduinoFsSessionStoreIo::openExistingReadOnly(
    const storage::ProductStorePermit& permit) {
    return permit.allowed() && !permit.writable &&
           permit.operation == storage::ProductStoreOperation::RecoverCatalog &&
           openExistingPath(permit.rootPath, 0, false, true);
}

bool ArduinoFsSessionStoreIo::removeScratch(
    const storage::ScratchCleanupPermit& permit) {
    static constexpr std::size_t kMaximumFiles = 8;
    char names[kMaximumFiles][storage::kSessionStorePathMax] = {};
    std::size_t count = 0;
    filesRemoved_ = 0;
    scratchRemoved_ = false;
    lastFailure_ = "none";
    lastFresult_ = FR_OK;
    if (ready_ || pendingOpen_ || driveNumber_ >= FF_VOLUMES ||
        !permit.allowed() ||
        std::strncmp(permit.scratchPath, storage::kScratchRoot,
                     std::strlen(storage::kScratchRoot)) != 0) {
        recordFailure("cleanup_precondition", FR_INVALID_PARAMETER);
        return false;
    }

    char root[kFullPathCapacity] = {};
    if (!formatVolumePath(permit.scratchPath, root, sizeof(root))) {
        recordFailure("cleanup_path", FR_INVALID_NAME);
        return false;
    }
    FF_DIR directory{};
    FRESULT result = f_opendir(&directory, root);
    if (result != FR_OK) {
        recordFailure("cleanup_open", result);
        return false;
    }
    bool safe = true;
    for (;;) {
        workspace_.information = {};
        result = f_readdir(&directory, &workspace_.information);
        if (result != FR_OK) {
            safe = false;
            recordFailure("cleanup_scan", result);
            break;
        }
        const char* name = workspace_.information.fname;
        if (name[0] == '\0') break;
        if ((workspace_.information.fattrib & AM_DIR) != 0 ||
            !storage::isSessionStoreScratchFileName(name) ||
            count >= kMaximumFiles ||
            std::strlen(name) >= storage::kSessionStorePathMax) {
            safe = false;
            recordFailure("cleanup_unknown_entry", FR_DENIED);
            break;
        }
        std::strcpy(names[count++], name);
    }
    const FRESULT closeResult = f_closedir(&directory);
    if (closeResult != FR_OK && safe) {
        safe = false;
        recordFailure("cleanup_close", closeResult);
    }
    if (!safe) return false;

    for (std::size_t index = 0; index < count; ++index) {
        char child[kFullPathCapacity] = {};
        const int written = std::snprintf(child, sizeof(child), "%s/%s",
                                          root, names[index]);
        if (written <= 0 ||
            static_cast<std::size_t>(written) >= sizeof(child)) {
            recordFailure("cleanup_child_path", FR_INVALID_NAME);
            return false;
        }
        result = f_unlink(child);
        if (result != FR_OK) {
            recordFailure("cleanup_file", result);
            return false;
        }
        ++filesRemoved_;
    }
    result = f_unlink(root);
    if (result != FR_OK) {
        recordFailure("cleanup_directory", result);
        return false;
    }
    workspace_.information = {};
    result = f_stat(root, &workspace_.information);
    scratchRemoved_ = result == FR_NO_FILE || result == FR_NO_PATH;
    if (!scratchRemoved_) {
        recordFailure("cleanup_verify", result == FR_OK ? FR_EXIST : result);
    }
    return scratchRemoved_;
}

bool ArduinoFsSessionStoreIo::selectDrive(std::uint8_t driveNumber) {
    if (ready_ || pendingOpen_ || driveNumber >= FF_VOLUMES) return false;
    driveNumber_ = driveNumber;
    return true;
}

bool ArduinoFsSessionStoreIo::openExistingPath(
    const char* path, std::uint64_t byteLimit, bool writable,
    bool productRoot) {
    const bool approvedRoot = productRoot
        ? path != nullptr &&
              std::strcmp(path, storage::kProductSessionStoreRoot) == 0
        : path != nullptr &&
              std::strncmp(path, storage::kScratchRoot,
                           std::strlen(storage::kScratchRoot)) == 0;
    if (ready_ || driveNumber_ >= FF_VOLUMES || path == nullptr ||
        !approvedRoot ||
        std::strlen(path) >= sizeof(rootPath_) || !directoryExists(path)) {
        return false;
    }
    std::strcpy(rootPath_, path);
    byteLimit_ = byteLimit;
    ready_ = true;
    writable_ = writable;
    return true;
}

void ArduinoFsSessionStoreIo::end() {
    if (pendingOpen_) f_close(&workspace_.file);
    pendingOpen_ = false;
    pendingRelative_[0] = '\0';
    pendingSize_ = 0;
    fileBarrierComplete_ = false;
    ready_ = false;
    writable_ = false;
}

bool ArduinoFsSessionStoreIo::writeFile(
    const char* path, const std::uint8_t* data, std::size_t size) {
    if (!ready_ || !writable_ || pendingOpen_ || data == nullptr || size == 0 ||
        size > UINT_MAX || bytesWritten_ > byteLimit_ ||
        size > byteLimit_ - bytesWritten_) {
        recordFailure("write_precondition", FR_INVALID_PARAMETER);
        return false;
    }
    char fullPath[kFullPathCapacity] = {};
    if (!formatFullPath(path, fullPath, sizeof(fullPath))) {
        recordFailure("write_path", FR_INVALID_NAME);
        return false;
    }
    if (!progress("write_open_progress")) return false;
    workspace_.file = {};
    FRESULT result = f_open(&workspace_.file, fullPath,
                            FA_WRITE | FA_CREATE_ALWAYS);
    if (result != FR_OK) {
        recordFailure("write_open", result);
        return false;
    }
    pendingOpen_ = true;
    ++writeCalls_;
    if (!progress("write_opened_progress")) {
        f_close(&workspace_.file);
        pendingOpen_ = false;
        return false;
    }
    UINT written = 0;
    result = f_write(&workspace_.file, data, static_cast<UINT>(size), &written);
    bytesWritten_ += written;
    if (result != FR_OK || written != size) {
        const FRESULT closeResult = f_close(&workspace_.file);
        pendingOpen_ = false;
        recordFailure("write_data", result != FR_OK ? result : closeResult);
        return false;
    }
    if (!progress("write_data_progress")) {
        f_close(&workspace_.file);
        pendingOpen_ = false;
        return false;
    }
    std::strcpy(pendingRelative_, path);
    pendingSize_ = size;
    fileBarrierComplete_ = false;
    return true;
}

ArduinoFsSessionStoreIo::ReadStatus ArduinoFsSessionStoreIo::readFile(
    const char* path, std::uint8_t* output, std::size_t capacity,
    std::size_t* outputSize) {
    if (!ready_ || pendingOpen_ || output == nullptr || outputSize == nullptr) {
        return ReadStatus::IoError;
    }
    char fullPath[kFullPathCapacity] = {};
    if (!formatFullPath(path, fullPath, sizeof(fullPath))) {
        return ReadStatus::IoError;
    }
    if (!progress("read_open_progress")) return ReadStatus::IoError;
    workspace_.file = {};
    FRESULT result = f_open(&workspace_.file, fullPath, FA_READ);
    if (result == FR_NO_FILE || result == FR_NO_PATH) return ReadStatus::NotFound;
    if (result != FR_OK) {
        recordFailure("read_open", result);
        return ReadStatus::IoError;
    }
    const FSIZE_t fileSize = f_size(&workspace_.file);
    if (fileSize > capacity || fileSize > UINT_MAX) {
        f_close(&workspace_.file);
        return ReadStatus::TooLarge;
    }
    if (!progress("read_data_progress")) {
        f_close(&workspace_.file);
        return ReadStatus::IoError;
    }
    UINT read = 0;
    result = f_read(&workspace_.file, output, static_cast<UINT>(fileSize), &read);
    const FRESULT closeResult = f_close(&workspace_.file);
    if (result != FR_OK || closeResult != FR_OK || read != fileSize) {
        recordFailure("read_data", result != FR_OK ? result : closeResult);
        return ReadStatus::IoError;
    }
    if (!progress("read_close_progress")) return ReadStatus::IoError;
    *outputSize = static_cast<std::size_t>(fileSize);
    return ReadStatus::Ok;
}

bool ArduinoFsSessionStoreIo::syncFile(const char* path) {
    if (!ready_ || !pendingOpen_ || !safeRelativePath(path) ||
        std::strcmp(path, pendingRelative_) != 0) {
        recordFailure("sync_precondition", FR_INVALID_PARAMETER);
        return false;
    }
    if (!progress("sync_file_progress")) {
        f_close(&workspace_.file);
        pendingOpen_ = false;
        return false;
    }
    FRESULT result = f_sync(&workspace_.file);
    if (result != FR_OK) {
        f_close(&workspace_.file);
        pendingOpen_ = false;
        recordFailure("sync_file", result);
        return false;
    }
    if (!progress("sync_file_complete_progress")) {
        f_close(&workspace_.file);
        pendingOpen_ = false;
        return false;
    }
    result = f_close(&workspace_.file);
    pendingOpen_ = false;
    if (result != FR_OK) {
        recordFailure("sync_close", result);
        return false;
    }
    if (!progress("sync_close_progress")) return false;
    char fullPath[kFullPathCapacity] = {};
    if (!formatFullPath(path, fullPath, sizeof(fullPath))) {
        recordFailure("sync_path", FR_INVALID_NAME);
        return false;
    }
    workspace_.information = {};
    result = f_stat(fullPath, &workspace_.information);
    if (!progress("sync_verify_progress")) return false;
    const bool valid = result == FR_OK &&
                       (workspace_.information.fattrib & AM_DIR) == 0 &&
                       workspace_.information.fsize == pendingSize_;
    pendingRelative_[0] = '\0';
    pendingSize_ = 0;
    fileBarrierComplete_ = valid;
    if (valid) {
        ++fileSyncs_;
    } else {
        recordFailure("sync_verify", result != FR_OK ? result : FR_INT_ERR);
    }
    return valid;
}

bool ArduinoFsSessionStoreIo::syncDirectory() {
    if (!ready_ || pendingOpen_ || !fileBarrierComplete_) return false;
    if (!progress("directory_sync_progress")) return false;
    // FatFs f_sync persists the file, allocation metadata, and directory entry
    // together; this VFS has no independent directory-fd barrier.
    fileBarrierComplete_ = false;
    ++directorySyncs_;
    return progress("directory_sync_complete_progress");
}

}  // namespace leshy1::platform::arduino
