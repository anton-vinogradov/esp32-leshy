#pragma once

#include <cstddef>
#include <cstdint>

#include "platform/arduino/DisposableOtaLittleFs.h"
#include "storage/SessionStore.h"
#include "storage/StorageGuard.h"

namespace leshy1::platform::arduino {

// Common SessionStore adapter over a mounted disposable LittleFS target. One
// successful file fsync is also the LittleFS metadata/directory durability
// boundary; syncDirectory consumes that already-proven barrier.
class ArduinoLittleFsSessionStoreIo final : public storage::SessionStoreIo {
public:
    explicit ArduinoLittleFsSessionStoreIo(DisposableOtaLittleFs& filesystem)
        : filesystem_(filesystem) {}
    ~ArduinoLittleFsSessionStoreIo() override { end(); }

    bool prepare(const storage::WritePermit& permit);
    bool openExistingReadOnly(const storage::WritePermit& permit);
    bool openExistingReadOnly(const storage::ReadPermit& permit);
    void end();

    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override;
    ReadStatus readFile(const char* path, std::uint8_t* output,
                        std::size_t capacity,
                        std::size_t* outputSize) override;
    bool syncFile(const char* path) override;
    bool syncDirectory() override;

    std::uint64_t bytesWritten() const { return bytesWritten_; }
    std::uint32_t fileSyncs() const { return fileSyncs_; }
    std::uint32_t directorySyncs() const { return directorySyncs_; }
    bool fileSyncCoversDirectory() const { return true; }
    const char* lastFailure() const { return lastFailure_; }
    int lastErrno() const { return lastErrno_; }
    bool ready() const { return ready_; }
    bool writable() const { return writable_; }

private:
    static constexpr std::size_t kFullPathCapacity = 192;

    bool safeRelativePath(const char* path) const;
    bool formatFullPath(const char* path, char* output,
                        std::size_t capacity) const;
    bool directoryExists(const char* path) const;
    bool ensureDirectory(const char* path);
    void resetCounters();
    void recordFailure(const char* stage);
    bool openExistingReadOnlyPath(const char* path);

    DisposableOtaLittleFs& filesystem_;
    char rootPath_[storage::kScratchPathMax] = {};
    char pendingRelative_[storage::kSessionStorePathMax] = {};
    std::size_t pendingSize_ = 0;
    std::uint64_t byteLimit_ = 0;
    std::uint64_t bytesWritten_ = 0;
    std::uint32_t fileSyncs_ = 0;
    std::uint32_t directorySyncs_ = 0;
    int pendingDescriptor_ = -1;
    int lastErrno_ = 0;
    bool ready_ = false;
    bool writable_ = false;
    bool fileBarrierComplete_ = false;
    const char* lastFailure_ = "none";
};

}  // namespace leshy1::platform::arduino
