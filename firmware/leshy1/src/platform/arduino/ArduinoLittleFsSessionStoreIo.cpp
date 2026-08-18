#include "ArduinoLittleFsSessionStoreIo.h"

#include <cerrno>
#include <cstdio>
#include <cstring>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace leshy1::platform::arduino {
namespace {

constexpr const char* kScratchParent = "/leshy-hil";

}  // namespace

void ArduinoLittleFsSessionStoreIo::recordFailure(const char* stage) {
    lastFailure_ = stage;
    lastErrno_ = errno;
}

void ArduinoLittleFsSessionStoreIo::resetCounters() {
    byteLimit_ = 0;
    bytesWritten_ = 0;
    fileSyncs_ = 0;
    directorySyncs_ = 0;
    pendingSize_ = 0;
    pendingRelative_[0] = '\0';
    fileBarrierComplete_ = false;
    lastFailure_ = "none";
    lastErrno_ = 0;
}

bool ArduinoLittleFsSessionStoreIo::safeRelativePath(const char* path) const {
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

bool ArduinoLittleFsSessionStoreIo::formatFullPath(
    const char* path, char* output, std::size_t capacity) const {
    if (!ready_ || !safeRelativePath(path) || output == nullptr || capacity == 0) {
        return false;
    }
    const int written = std::snprintf(
        output, capacity, "%s%s/%s", DisposableOtaLittleFs::kBasePath,
        rootPath_, path);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool ArduinoLittleFsSessionStoreIo::directoryExists(const char* path) const {
    if (path == nullptr || path[0] != '/') return false;
    char fullPath[kFullPathCapacity] = {};
    const int written = std::snprintf(
        fullPath, sizeof(fullPath), "%s%s",
        DisposableOtaLittleFs::kBasePath, path);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(fullPath)) {
        return false;
    }
    struct stat information {};
    return ::stat(fullPath, &information) == 0 && S_ISDIR(information.st_mode);
}

bool ArduinoLittleFsSessionStoreIo::ensureDirectory(const char* path) {
    if (directoryExists(path)) return true;
    char fullPath[kFullPathCapacity] = {};
    const int written = std::snprintf(
        fullPath, sizeof(fullPath), "%s%s",
        DisposableOtaLittleFs::kBasePath, path);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(fullPath) ||
        ::mkdir(fullPath, 0700) != 0 || !directoryExists(path)) {
        recordFailure("directory_create");
        return false;
    }
    return true;
}

bool ArduinoLittleFsSessionStoreIo::prepare(
    const storage::WritePermit& permit) {
    if (ready_ || !filesystem_.mounted() || filesystem_.readOnly() ||
        !permit.allowed() || permit.byteLimit == 0 ||
        std::strncmp(permit.scratchPath, storage::kScratchRoot,
                     std::strlen(storage::kScratchRoot)) != 0 ||
        std::strlen(permit.scratchPath) >= sizeof(rootPath_) ||
        directoryExists(permit.scratchPath)) {
        recordFailure("prepare_precondition");
        return false;
    }
    resetCounters();
    if (!ensureDirectory(kScratchParent) ||
        !ensureDirectory(permit.scratchPath)) {
        return false;
    }
    std::strcpy(rootPath_, permit.scratchPath);
    byteLimit_ = permit.byteLimit;
    ready_ = true;
    writable_ = true;
    return true;
}

bool ArduinoLittleFsSessionStoreIo::openExistingReadOnly(
    const storage::WritePermit& permit) {
    if (ready_ || !filesystem_.mounted() || !filesystem_.readOnly() ||
        !permit.allowed() ||
        std::strlen(permit.scratchPath) >= sizeof(rootPath_) ||
        !directoryExists(permit.scratchPath)) {
        recordFailure("readonly_precondition");
        return false;
    }
    resetCounters();
    std::strcpy(rootPath_, permit.scratchPath);
    ready_ = true;
    writable_ = false;
    return true;
}

void ArduinoLittleFsSessionStoreIo::end() {
    if (pendingDescriptor_ >= 0) ::close(pendingDescriptor_);
    pendingDescriptor_ = -1;
    pendingRelative_[0] = '\0';
    pendingSize_ = 0;
    fileBarrierComplete_ = false;
    ready_ = false;
    writable_ = false;
}

bool ArduinoLittleFsSessionStoreIo::writeFile(
    const char* path, const std::uint8_t* data, std::size_t size) {
    if (!ready_ || !writable_ || pendingDescriptor_ >= 0 || data == nullptr ||
        size == 0 || bytesWritten_ > byteLimit_ ||
        size > byteLimit_ - bytesWritten_) {
        recordFailure("write_precondition");
        return false;
    }
    char fullPath[kFullPathCapacity] = {};
    if (!formatFullPath(path, fullPath, sizeof(fullPath))) {
        recordFailure("write_path");
        return false;
    }
    pendingDescriptor_ = ::open(
        fullPath, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (pendingDescriptor_ < 0) {
        recordFailure("write_open");
        return false;
    }
    std::size_t offset = 0;
    while (offset < size) {
        const ssize_t written = ::write(
            pendingDescriptor_, data + offset, size - offset);
        if (written <= 0) {
            recordFailure("write_data");
            ::close(pendingDescriptor_);
            pendingDescriptor_ = -1;
            return false;
        }
        offset += static_cast<std::size_t>(written);
        bytesWritten_ += static_cast<std::size_t>(written);
    }
    std::strcpy(pendingRelative_, path);
    pendingSize_ = size;
    fileBarrierComplete_ = false;
    return true;
}

ArduinoLittleFsSessionStoreIo::ReadStatus
ArduinoLittleFsSessionStoreIo::readFile(
    const char* path, std::uint8_t* output, std::size_t capacity,
    std::size_t* outputSize) {
    if (!ready_ || pendingDescriptor_ >= 0 || output == nullptr ||
        outputSize == nullptr) {
        recordFailure("read_precondition");
        return ReadStatus::IoError;
    }
    char fullPath[kFullPathCapacity] = {};
    if (!formatFullPath(path, fullPath, sizeof(fullPath))) {
        recordFailure("read_path");
        return ReadStatus::IoError;
    }
    struct stat information {};
    if (::stat(fullPath, &information) != 0) {
        if (errno == ENOENT) return ReadStatus::NotFound;
        recordFailure("read_stat");
        return ReadStatus::IoError;
    }
    if (information.st_size < 0 ||
        static_cast<std::uint64_t>(information.st_size) > capacity) {
        return ReadStatus::TooLarge;
    }
    const int descriptor = ::open(fullPath, O_RDONLY);
    if (descriptor < 0) {
        recordFailure("read_open");
        return ReadStatus::IoError;
    }
    const std::size_t expected = static_cast<std::size_t>(information.st_size);
    std::size_t offset = 0;
    while (offset < expected) {
        const ssize_t read = ::read(descriptor, output + offset,
                                    expected - offset);
        if (read <= 0) {
            recordFailure("read_data");
            ::close(descriptor);
            return ReadStatus::IoError;
        }
        offset += static_cast<std::size_t>(read);
    }
    if (::close(descriptor) != 0) {
        recordFailure("read_close");
        return ReadStatus::IoError;
    }
    *outputSize = expected;
    return ReadStatus::Ok;
}

bool ArduinoLittleFsSessionStoreIo::syncFile(const char* path) {
    if (!ready_ || pendingDescriptor_ < 0 || !safeRelativePath(path) ||
        std::strcmp(path, pendingRelative_) != 0) {
        recordFailure("sync_precondition");
        return false;
    }
    if (::fsync(pendingDescriptor_) != 0) {
        recordFailure("sync_file");
        ::close(pendingDescriptor_);
        pendingDescriptor_ = -1;
        return false;
    }
    if (::close(pendingDescriptor_) != 0) {
        recordFailure("sync_close");
        pendingDescriptor_ = -1;
        return false;
    }
    pendingDescriptor_ = -1;
    char fullPath[kFullPathCapacity] = {};
    struct stat information {};
    const bool valid = formatFullPath(path, fullPath, sizeof(fullPath)) &&
        ::stat(fullPath, &information) == 0 &&
        information.st_size >= 0 &&
        static_cast<std::size_t>(information.st_size) == pendingSize_;
    pendingRelative_[0] = '\0';
    pendingSize_ = 0;
    fileBarrierComplete_ = valid;
    if (valid) {
        ++fileSyncs_;
    } else {
        recordFailure("sync_verify");
    }
    return valid;
}

bool ArduinoLittleFsSessionStoreIo::syncDirectory() {
    if (!ready_ || pendingDescriptor_ >= 0 || !fileBarrierComplete_) {
        recordFailure("directory_sync_precondition");
        return false;
    }
    // LittleFS lfs_file_sync commits the file's metadata pair, including its
    // directory entry. There is no separate directory fd in esp_littlefs VFS.
    fileBarrierComplete_ = false;
    ++directorySyncs_;
    return true;
}

}  // namespace leshy1::platform::arduino
