#pragma once

#include <cstddef>
#include <cstdint>

#include "SessionStore.h"

namespace leshy1::storage {

// Diagnostic-only wrapper that observes the six durable SessionStore commit
// boundaries without changing the production commit order. The callback is
// invoked only after the wrapped operation succeeds. If it returns, the wrapper
// stops the commit at that boundary; a board callback may instead call
// esp_restart(), which never returns.
using SessionStoreBoundaryHook = void (*)(void* context, CommitStage boundary);

class SessionStoreBoundaryIo final : public SessionStoreIo {
public:
    SessionStoreBoundaryIo(SessionStoreIo& wrapped, CommitStage stopAfter,
                           SessionStoreBoundaryHook hook = nullptr,
                           void* hookContext = nullptr)
        : wrapped_(wrapped), stopAfter_(stopAfter), hook_(hook),
          hookContext_(hookContext) {}

    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override;
    ReadStatus readFile(const char* path, std::uint8_t* output,
                        std::size_t capacity,
                        std::size_t* outputSize) override;
    bool syncFile(const char* path) override;
    bool syncDirectory() override;

    bool armed() const;
    bool stopped() const { return stopped_; }
    bool sequenceValid() const { return sequenceValid_; }
    std::size_t boundariesReached() const { return nextBoundary_; }
    CommitStage lastReached() const { return lastReached_; }

private:
    bool completeBoundary(CommitStage boundary);
    static CommitStage stageAt(std::size_t index);

    SessionStoreIo& wrapped_;
    CommitStage stopAfter_ = CommitStage::Complete;
    SessionStoreBoundaryHook hook_ = nullptr;
    void* hookContext_ = nullptr;
    std::size_t nextBoundary_ = 0;
    CommitStage lastReached_ = CommitStage::Complete;
    bool fileSynced_ = false;
    bool stopped_ = false;
    bool sequenceValid_ = true;
};

const char* sessionStoreBoundaryName(CommitStage boundary);
bool isSessionStoreBoundary(CommitStage boundary);

}  // namespace leshy1::storage
