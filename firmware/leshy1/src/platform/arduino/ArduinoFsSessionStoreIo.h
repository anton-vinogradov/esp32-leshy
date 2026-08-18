#pragma once

#include <cstddef>
#include <cstdint>

#include <ff.h>

#include "storage/ProductStorePolicy.h"
#include "storage/SessionStore.h"
#include "storage/StorageGuard.h"

namespace leshy1::platform::arduino {

struct ArduinoFsSessionStoreWorkspace final {
    FIL file{};
    FILINFO information{};
};

// Confines SessionStore paths to one newly authorized /leshy-hil/<run-id>
// directory. It uses FatFs directly so every open/write/sync/close result is
// observable; Arduino FS::File hides the result of its flush barrier.
class ArduinoFsSessionStoreIo final : public storage::SessionStoreIo {
public:
    explicit ArduinoFsSessionStoreIo(ArduinoFsSessionStoreWorkspace& workspace)
        : workspace_(workspace) {}
    ArduinoFsSessionStoreIo(std::uint8_t driveNumber,
                            ArduinoFsSessionStoreWorkspace& workspace)
        : workspace_(workspace), driveNumber_(driveNumber) {}
    ~ArduinoFsSessionStoreIo() override { end(); }

    bool prepare(const storage::WritePermit& permit);
    bool prepare(const storage::ProductStorePermit& permit);
    bool openExistingWritable(const storage::ProductStorePermit& permit);
    bool openExistingReadOnly(const storage::WritePermit& permit);
    bool openExistingReadOnly(const storage::ReadPermit& permit);
    bool openExistingReadOnly(const storage::ProductStorePermit& permit);
    bool removeScratch(const storage::ScratchCleanupPermit& permit);
    bool selectDrive(std::uint8_t driveNumber);
    void end();

    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override;
    ReadStatus readFile(const char* path, std::uint8_t* output,
                        std::size_t capacity,
                        std::size_t* outputSize) override;
    bool syncFile(const char* path) override;
    bool syncDirectory() override;

    bool ready() const { return ready_; }
    bool writable() const { return writable_; }
    bool pendingWrite() const { return pendingOpen_; }
    std::uint64_t bytesWritten() const { return bytesWritten_; }
    std::uint32_t fileSyncs() const { return fileSyncs_; }
    std::uint32_t directorySyncs() const { return directorySyncs_; }
    std::uint16_t filesRemoved() const { return filesRemoved_; }
    bool scratchRemoved() const { return scratchRemoved_; }
    bool fatFileSyncCoversDirectory() const {
        return fatFileSyncCoversDirectory_;
    }
    const char* rootPath() const { return rootPath_; }
    const char* lastFailure() const { return lastFailure_; }
    int lastErrno() const { return 0; }
    unsigned lastFresult() const { return static_cast<unsigned>(lastFresult_); }
    const char* lastFresultName() const;

private:
    static constexpr std::size_t kFullPathCapacity = 128;

    bool safeRelativePath(const char* path) const;
    bool directoryExists(const char* path) const;
    bool ensureDirectory(const char* path);
    bool formatVolumePath(const char* path, char* output,
                          std::size_t capacity) const;
    bool formatFullPath(const char* path, char* output,
                        std::size_t capacity) const;
    bool openExistingPath(const char* path, std::uint64_t byteLimit,
                          bool writable, bool productRoot);
    void recordFailure(const char* stage, FRESULT result);

    ArduinoFsSessionStoreWorkspace& workspace_;
    std::uint8_t driveNumber_ = 0xFF;
    char rootPath_[storage::kScratchPathMax] = {};
    char pendingRelative_[storage::kSessionStorePathMax] = {};
    std::size_t pendingSize_ = 0;
    std::uint64_t byteLimit_ = 0;
    std::uint64_t bytesWritten_ = 0;
    std::uint32_t fileSyncs_ = 0;
    std::uint32_t directorySyncs_ = 0;
    std::uint16_t filesRemoved_ = 0;
    bool scratchRemoved_ = false;
    bool ready_ = false;
    bool writable_ = false;
    bool pendingOpen_ = false;
    bool fileBarrierComplete_ = false;
    bool fatFileSyncCoversDirectory_ = true;
    const char* lastFailure_ = "none";
    FRESULT lastFresult_ = FR_OK;
};

}  // namespace leshy1::platform::arduino
