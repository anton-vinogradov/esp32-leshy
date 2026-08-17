#pragma once

#include "storage/SessionStore.h"

namespace leshy1::storage {

// Allocation-free indirection between the Survey workflow and the selected
// storage backend. Binding is allowed only while no SessionStore call is in
// progress; the board lifecycle owns that invariant and always restores RAM
// after a persistent run is closed.
class SessionStoreIoRouter final : public SessionStoreIo {
public:
    explicit SessionStoreIoRouter(SessionStoreIo& backend)
        : backend_(&backend) {}

    bool bind(SessionStoreIo& backend) {
        backend_ = &backend;
        return true;
    }

    bool boundTo(const SessionStoreIo& backend) const {
        return backend_ == &backend;
    }

    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override;
    ReadStatus readFile(const char* path, std::uint8_t* output,
                        std::size_t capacity,
                        std::size_t* outputSize) override;
    bool syncFile(const char* path) override;
    bool syncDirectory() override;

private:
    SessionStoreIo* backend_ = nullptr;
};

}  // namespace leshy1::storage
