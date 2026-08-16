#include "RamSessionStoreIo.h"

#include <cstring>

namespace leshy1::platform::arduino {
namespace {

enum class ParsedKind : std::uint8_t {
    Invalid,
    Segment,
    Manifest,
    HeadA,
    HeadB,
};

struct ParsedPath final {
    ParsedKind kind = ParsedKind::Invalid;
    std::uint32_t generation = 0;
};

bool parseGeneration(const char* path, const char* prefix, std::uint32_t* generation) {
    if (path == nullptr || prefix == nullptr || generation == nullptr) return false;
    const std::size_t prefixLength = std::strlen(prefix);
    if (std::strncmp(path, prefix, prefixLength) != 0) return false;
    const char* cursor = path + prefixLength;
    std::uint64_t value = 0;
    std::size_t digits = 0;
    while (*cursor >= '0' && *cursor <= '9') {
        value = value * 10U + static_cast<std::uint8_t>(*cursor - '0');
        if (value > UINT32_MAX) return false;
        ++cursor;
        ++digits;
    }
    if (digits < 8 || std::strcmp(cursor, ".bin") != 0) return false;
    *generation = static_cast<std::uint32_t>(value);
    return true;
}

ParsedPath parsePath(const char* path) {
    ParsedPath parsed;
    if (path == nullptr) return parsed;
    if (std::strcmp(path, "head-a.bin") == 0) {
        parsed.kind = ParsedKind::HeadA;
    } else if (std::strcmp(path, "head-b.bin") == 0) {
        parsed.kind = ParsedKind::HeadB;
    } else if (parseGeneration(path, "segment-", &parsed.generation)) {
        parsed.kind = ParsedKind::Segment;
    } else if (parseGeneration(path, "manifest-", &parsed.generation)) {
        parsed.kind = ParsedKind::Manifest;
    }
    return parsed;
}

bool copyOut(const std::uint8_t* data, std::size_t size, std::uint8_t* output,
             std::size_t capacity, std::size_t* outputSize) {
    if (data == nullptr || output == nullptr || outputSize == nullptr || size > capacity) {
        return false;
    }
    std::memcpy(output, data, size);
    *outputSize = size;
    return true;
}

}  // namespace

void RamSessionStoreIo::reset() {
    for (GenerationFiles& files : generations_) {
        files.used = false;
        files.generation = 0;
        files.segmentSize = 0;
        files.segmentPresent = false;
        files.manifestSize = 0;
        files.manifestPresent = false;
    }
    headA_.fill(0);
    headB_.fill(0);
    headASize_ = 0;
    headBSize_ = 0;
    headAPresent_ = false;
    headBPresent_ = false;
    fileSyncs_ = 0;
    directorySyncs_ = 0;
}

RamSessionStoreIo::GenerationFiles* RamSessionStoreIo::findGeneration(
    std::uint32_t generation, bool create) {
    for (GenerationFiles& files : generations_) {
        if (files.used && files.generation == generation) return &files;
    }
    if (!create) return nullptr;
    for (GenerationFiles& files : generations_) {
        if (!files.used) {
            files.used = true;
            files.generation = generation;
            return &files;
        }
    }
    return nullptr;
}

const RamSessionStoreIo::GenerationFiles* RamSessionStoreIo::findGeneration(
    std::uint32_t generation) const {
    for (const GenerationFiles& files : generations_) {
        if (files.used && files.generation == generation) return &files;
    }
    return nullptr;
}

bool RamSessionStoreIo::writeFile(const char* path, const std::uint8_t* data,
                                  std::size_t size) {
    if (data == nullptr && size != 0) return false;
    const ParsedPath parsed = parsePath(path);
    if (parsed.kind == ParsedKind::HeadA || parsed.kind == ParsedKind::HeadB) {
        if (size > storage::kHeadWireSize) return false;
        std::array<std::uint8_t, storage::kHeadWireSize>& target =
            parsed.kind == ParsedKind::HeadA ? headA_ : headB_;
        std::size_t& targetSize = parsed.kind == ParsedKind::HeadA ? headASize_ : headBSize_;
        bool& present = parsed.kind == ParsedKind::HeadA ? headAPresent_ : headBPresent_;
        std::memcpy(target.data(), data, size);
        targetSize = size;
        present = true;
        return true;
    }
    if (parsed.kind != ParsedKind::Segment && parsed.kind != ParsedKind::Manifest) {
        return false;
    }
    GenerationFiles* files = findGeneration(parsed.generation, true);
    if (files == nullptr) return false;
    if (parsed.kind == ParsedKind::Segment) {
        if (size > files->segment.size()) return false;
        std::memcpy(files->segment.data(), data, size);
        files->segmentSize = size;
        files->segmentPresent = true;
    } else {
        if (size > files->manifest.size()) return false;
        std::memcpy(files->manifest.data(), data, size);
        files->manifestSize = size;
        files->manifestPresent = true;
    }
    return true;
}

RamSessionStoreIo::ReadStatus RamSessionStoreIo::readFile(const char* path,
                                                          std::uint8_t* output,
                                                          std::size_t capacity,
                                                          std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr) return ReadStatus::IoError;
    const ParsedPath parsed = parsePath(path);
    if (parsed.kind == ParsedKind::HeadA || parsed.kind == ParsedKind::HeadB) {
        const bool present = parsed.kind == ParsedKind::HeadA ? headAPresent_ : headBPresent_;
        if (!present) return ReadStatus::NotFound;
        const auto& source = parsed.kind == ParsedKind::HeadA ? headA_ : headB_;
        const std::size_t size = parsed.kind == ParsedKind::HeadA ? headASize_ : headBSize_;
        return copyOut(source.data(), size, output, capacity, outputSize)
                   ? ReadStatus::Ok
                   : ReadStatus::TooLarge;
    }
    if (parsed.kind != ParsedKind::Segment && parsed.kind != ParsedKind::Manifest) {
        return ReadStatus::IoError;
    }
    const GenerationFiles* files = findGeneration(parsed.generation);
    if (files == nullptr) return ReadStatus::NotFound;
    if (parsed.kind == ParsedKind::Segment) {
        if (!files->segmentPresent) return ReadStatus::NotFound;
        return copyOut(files->segment.data(), files->segmentSize, output, capacity, outputSize)
                   ? ReadStatus::Ok
                   : ReadStatus::TooLarge;
    }
    if (!files->manifestPresent) return ReadStatus::NotFound;
    return copyOut(files->manifest.data(), files->manifestSize, output, capacity, outputSize)
               ? ReadStatus::Ok
               : ReadStatus::TooLarge;
}

bool RamSessionStoreIo::syncFile(const char* path) {
    const ParsedPath parsed = parsePath(path);
    if (parsed.kind == ParsedKind::Invalid) return false;
    ++fileSyncs_;
    return true;
}

bool RamSessionStoreIo::syncDirectory() {
    ++directorySyncs_;
    return true;
}

bool RamSessionStoreIo::flipSegmentByte(std::uint32_t generation, std::size_t offset,
                                        std::uint8_t mask) {
    GenerationFiles* files = findGeneration(generation, false);
    if (files == nullptr || !files->segmentPresent || offset >= files->segmentSize || mask == 0) {
        return false;
    }
    files->segment[offset] ^= mask;
    return true;
}

}  // namespace leshy1::platform::arduino
