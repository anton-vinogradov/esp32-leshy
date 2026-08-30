#include "ProtectedFileEnvelope.h"

#include <algorithm>
#include <cstring>
#include <limits>

namespace leshy1::storage {
namespace {

constexpr std::array<std::uint8_t, 4> kMagic{{'L', 'E', 'N', 'C'}};
constexpr std::uint8_t kSchemaVersion = 1;

void putU16(std::uint8_t* output, std::uint16_t value) {
    output[0] = static_cast<std::uint8_t>(value);
    output[1] = static_cast<std::uint8_t>(value >> 8U);
}

void putU32(std::uint8_t* output, std::uint32_t value) {
    output[0] = static_cast<std::uint8_t>(value);
    output[1] = static_cast<std::uint8_t>(value >> 8U);
    output[2] = static_cast<std::uint8_t>(value >> 16U);
    output[3] = static_cast<std::uint8_t>(value >> 24U);
}

std::uint16_t getU16(const std::uint8_t* input) {
    return static_cast<std::uint16_t>(input[0]) |
        static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(input[1]) << 8U);
}

std::uint32_t getU32(const std::uint8_t* input) {
    return static_cast<std::uint32_t>(input[0]) |
        (static_cast<std::uint32_t>(input[1]) << 8U) |
        (static_cast<std::uint32_t>(input[2]) << 16U) |
        (static_cast<std::uint32_t>(input[3]) << 24U);
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) {
    std::uint32_t crc = 0xffffffffU;
    for (std::size_t index = 0; index < size; ++index) {
        crc ^= data[index];
        for (unsigned bit = 0; bit < 8U; ++bit) {
            const std::uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1U) ^ (0xedb88320U & mask);
        }
    }
    return ~crc;
}

bool nonceSeedValid(
    const std::array<std::uint8_t,
                     services::security::kDeviceLockWrapNonceBytes>& seed) {
    std::uint8_t combined = 0;
    for (std::size_t index = 0; index < 8U; ++index) {
        combined = static_cast<std::uint8_t>(combined | seed[index]);
    }
    return combined != 0U && seed[8] == 0U && seed[9] == 0U &&
        seed[10] == 0U && seed[11] == 0U;
}

}  // namespace

std::size_t protectedFileChunkCount(std::size_t plaintextSize) {
    return plaintextSize == 0U ? 0U :
        1U + (plaintextSize - 1U) / kProtectedFileChunkBytes;
}

std::size_t protectedFileChunkSize(std::size_t plaintextSize,
                                   std::size_t chunkIndex) {
    const std::size_t count = protectedFileChunkCount(plaintextSize);
    if (chunkIndex >= count) return 0U;
    const std::size_t offset = chunkIndex * kProtectedFileChunkBytes;
    return std::min(kProtectedFileChunkBytes, plaintextSize - offset);
}

std::size_t protectedFilePhysicalSize(std::size_t plaintextSize) {
    const std::size_t chunks = protectedFileChunkCount(plaintextSize);
    const std::size_t tagBytes =
        services::security::kDeviceLockAuthTagBytes;
    if (plaintextSize == 0U ||
        chunks > (std::numeric_limits<std::size_t>::max() -
                  kProtectedFileHeaderBytes - plaintextSize) / tagBytes) {
        return 0U;
    }
    return kProtectedFileHeaderBytes + plaintextSize + chunks * tagBytes;
}

bool encodeProtectedFileHeader(const ProtectedFileDescription& description,
                               ProtectedFileHeader* output) {
    if (output == nullptr || description.plaintextSize == 0U ||
        protectedFilePhysicalSize(description.plaintextSize) == 0U ||
        !nonceSeedValid(description.nonceSeed)) {
        return false;
    }
    output->fill(0);
    std::copy(kMagic.begin(), kMagic.end(), output->begin());
    (*output)[4] = kSchemaVersion;
    (*output)[5] = static_cast<std::uint8_t>(kProtectedFileHeaderBytes);
    putU16(output->data() + 6U,
           static_cast<std::uint16_t>(kProtectedFileChunkBytes));
    putU32(output->data() + 8U, description.plaintextSize);
    std::copy(description.nonceSeed.begin(), description.nonceSeed.end(),
              output->begin() + 12U);
    putU32(output->data() + 28U, crc32(output->data(), 28U));
    return true;
}

bool decodeProtectedFileHeader(const ProtectedFileHeader& input,
                               ProtectedFileDescription* output) {
    if (output == nullptr ||
        !std::equal(kMagic.begin(), kMagic.end(), input.begin()) ||
        input[4] != kSchemaVersion ||
        input[5] != kProtectedFileHeaderBytes ||
        getU16(input.data() + 6U) != kProtectedFileChunkBytes ||
        input[24] != 0U || input[25] != 0U || input[26] != 0U ||
        input[27] != 0U ||
        getU32(input.data() + 28U) != crc32(input.data(), 28U)) {
        return false;
    }
    ProtectedFileDescription candidate{};
    candidate.plaintextSize = getU32(input.data() + 8U);
    std::copy_n(input.begin() + 12U, candidate.nonceSeed.size(),
                candidate.nonceSeed.begin());
    if (candidate.plaintextSize == 0U ||
        protectedFilePhysicalSize(candidate.plaintextSize) == 0U ||
        !nonceSeedValid(candidate.nonceSeed)) {
        return false;
    }
    *output = candidate;
    return true;
}

bool buildProtectedFileChunkNonce(
    const ProtectedFileDescription& description, std::size_t chunkIndex,
    std::array<std::uint8_t,
               services::security::kDeviceLockWrapNonceBytes>* output) {
    if (output == nullptr || !nonceSeedValid(description.nonceSeed) ||
        chunkIndex >= protectedFileChunkCount(description.plaintextSize) ||
        chunkIndex > std::numeric_limits<std::uint32_t>::max()) {
        return false;
    }
    *output = description.nonceSeed;
    putU32(output->data() + 8U, static_cast<std::uint32_t>(chunkIndex));
    return true;
}

bool buildProtectedFileChunkAad(const ProtectedFileHeader& header,
                                const char* relativePath,
                                std::size_t chunkIndex,
                                ProtectedFileAad* output,
                                std::size_t* outputSize) {
    if (relativePath == nullptr || output == nullptr || outputSize == nullptr ||
        chunkIndex > std::numeric_limits<std::uint32_t>::max()) {
        return false;
    }
    const std::size_t pathSize = std::strlen(relativePath);
    if (pathSize == 0U || pathSize >= kSessionStorePathMax) return false;
    output->fill(0);
    std::copy(header.begin(), header.end(), output->begin());
    putU32(output->data() + kProtectedFileHeaderBytes,
           static_cast<std::uint32_t>(chunkIndex));
    std::copy_n(reinterpret_cast<const std::uint8_t*>(relativePath), pathSize,
                output->begin() + kProtectedFileHeaderBytes + 4U);
    *outputSize = kProtectedFileHeaderBytes + 4U + pathSize;
    return true;
}

}  // namespace leshy1::storage
