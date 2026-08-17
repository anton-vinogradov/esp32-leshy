#include "SessionStoreIoRouter.h"

namespace leshy1::storage {

bool SessionStoreIoRouter::writeFile(const char* path,
                                     const std::uint8_t* data,
                                     std::size_t size) {
    return backend_ != nullptr && backend_->writeFile(path, data, size);
}

SessionStoreIo::ReadStatus SessionStoreIoRouter::readFile(
    const char* path, std::uint8_t* output, std::size_t capacity,
    std::size_t* outputSize) {
    return backend_ == nullptr
               ? ReadStatus::IoError
               : backend_->readFile(path, output, capacity, outputSize);
}

bool SessionStoreIoRouter::syncFile(const char* path) {
    return backend_ != nullptr && backend_->syncFile(path);
}

bool SessionStoreIoRouter::syncDirectory() {
    return backend_ != nullptr && backend_->syncDirectory();
}

}  // namespace leshy1::storage
