#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "storage/SessionStore.h"

namespace leshy1::platform::arduino {

class RamSessionStoreIo final : public storage::SessionStoreIo {
public:
    void reset();

    bool writeFile(const char* path, const std::uint8_t* data, std::size_t size) override;
    ReadStatus readFile(const char* path, std::uint8_t* output, std::size_t capacity,
                        std::size_t* outputSize) override;
    bool syncFile(const char* path) override;
    bool syncDirectory() override;

    bool flipSegmentByte(std::uint32_t generation, std::size_t offset,
                         std::uint8_t mask = 1U);
    std::size_t fileSyncs() const { return fileSyncs_; }
    std::size_t directorySyncs() const { return directorySyncs_; }

private:
    struct GenerationFiles final {
        bool used = false;
        std::uint32_t generation = 0;
        std::array<std::uint8_t, storage::kSessionSegmentMaxBytes> segment{};
        std::size_t segmentSize = 0;
        bool segmentPresent = false;
        std::array<std::uint8_t, storage::kSessionManifestMaxBytes> manifest{};
        std::size_t manifestSize = 0;
        bool manifestPresent = false;
    };

    GenerationFiles* findGeneration(std::uint32_t generation, bool create);
    const GenerationFiles* findGeneration(std::uint32_t generation) const;

    std::array<GenerationFiles, 2> generations_{};
    std::array<std::uint8_t, storage::kHeadWireSize> headA_{};
    std::array<std::uint8_t, storage::kHeadWireSize> headB_{};
    std::size_t headASize_ = 0;
    std::size_t headBSize_ = 0;
    bool headAPresent_ = false;
    bool headBPresent_ = false;
    std::size_t fileSyncs_ = 0;
    std::size_t directorySyncs_ = 0;
};

}  // namespace leshy1::platform::arduino
