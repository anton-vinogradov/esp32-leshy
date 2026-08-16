#include "SessionStoreBoundary.h"

namespace leshy1::storage {
namespace {

constexpr CommitStage kBoundaries[] = {
    CommitStage::WritePayloads,
    CommitStage::SyncPayloads,
    CommitStage::WriteManifest,
    CommitStage::SyncManifest,
    CommitStage::WriteHead,
    CommitStage::SyncHead,
};

}  // namespace

bool isSessionStoreBoundary(CommitStage boundary) {
    for (const CommitStage candidate : kBoundaries) {
        if (candidate == boundary) return true;
    }
    return false;
}

const char* sessionStoreBoundaryName(CommitStage boundary) {
    switch (boundary) {
        case CommitStage::WritePayloads: return "write_payloads";
        case CommitStage::SyncPayloads: return "sync_payloads";
        case CommitStage::WriteManifest: return "write_manifest";
        case CommitStage::SyncManifest: return "sync_manifest";
        case CommitStage::WriteHead: return "write_head";
        case CommitStage::SyncHead: return "sync_head";
        case CommitStage::Complete: return "complete";
    }
    return "unknown";
}

CommitStage SessionStoreBoundaryIo::stageAt(std::size_t index) {
    return index < (sizeof(kBoundaries) / sizeof(kBoundaries[0]))
               ? kBoundaries[index] : CommitStage::Complete;
}

bool SessionStoreBoundaryIo::armed() const {
    return isSessionStoreBoundary(stopAfter_);
}

bool SessionStoreBoundaryIo::completeBoundary(CommitStage boundary) {
    if (stopped_ || nextBoundary_ >= 6 || stageAt(nextBoundary_) != boundary) {
        sequenceValid_ = false;
        return false;
    }
    lastReached_ = boundary;
    ++nextBoundary_;
    if (boundary != stopAfter_) return true;
    stopped_ = true;
    if (hook_ != nullptr) hook_(hookContext_, boundary);
    return false;
}

bool SessionStoreBoundaryIo::writeFile(const char* path,
                                       const std::uint8_t* data,
                                       std::size_t size) {
    const CommitStage stage = stageAt(nextBoundary_);
    if (stopped_ || (stage != CommitStage::WritePayloads &&
                     stage != CommitStage::WriteManifest &&
                     stage != CommitStage::WriteHead)) {
        sequenceValid_ = false;
        return false;
    }
    if (!wrapped_.writeFile(path, data, size)) return false;
    fileSynced_ = false;
    return completeBoundary(stage);
}

SessionStoreIo::ReadStatus SessionStoreBoundaryIo::readFile(
    const char* path, std::uint8_t* output, std::size_t capacity,
    std::size_t* outputSize) {
    return wrapped_.readFile(path, output, capacity, outputSize);
}

bool SessionStoreBoundaryIo::syncFile(const char* path) {
    const CommitStage stage = stageAt(nextBoundary_);
    if (stopped_ || fileSynced_ ||
        (stage != CommitStage::SyncPayloads &&
         stage != CommitStage::SyncManifest &&
         stage != CommitStage::SyncHead)) {
        sequenceValid_ = false;
        return false;
    }
    if (!wrapped_.syncFile(path)) return false;
    fileSynced_ = true;
    return true;
}

bool SessionStoreBoundaryIo::syncDirectory() {
    const CommitStage stage = stageAt(nextBoundary_);
    if (stopped_ || !fileSynced_ ||
        (stage != CommitStage::SyncPayloads &&
         stage != CommitStage::SyncManifest &&
         stage != CommitStage::SyncHead)) {
        sequenceValid_ = false;
        return false;
    }
    if (!wrapped_.syncDirectory()) return false;
    fileSynced_ = false;
    return completeBoundary(stage);
}

}  // namespace leshy1::storage
