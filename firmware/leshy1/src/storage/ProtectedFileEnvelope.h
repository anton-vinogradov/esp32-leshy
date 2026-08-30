#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/security/DeviceLock.h"
#include "storage/SessionStore.h"

namespace leshy1::storage {

constexpr std::size_t kProtectedFileHeaderBytes = 32;
constexpr std::size_t kProtectedFileChunkBytes = 256;
constexpr std::size_t kProtectedFileAadBytes =
    kProtectedFileHeaderBytes + 4U + kSessionStorePathMax;

using ProtectedFileHeader =
    std::array<std::uint8_t, kProtectedFileHeaderBytes>;
using ProtectedFileAad =
    std::array<std::uint8_t, kProtectedFileAadBytes>;

struct ProtectedFileDescription final {
    std::uint32_t plaintextSize = 0;
    std::array<std::uint8_t,
               services::security::kDeviceLockWrapNonceBytes> nonceSeed{};
};

std::size_t protectedFileChunkCount(std::size_t plaintextSize);
std::size_t protectedFileChunkSize(std::size_t plaintextSize,
                                   std::size_t chunkIndex);
std::size_t protectedFilePhysicalSize(std::size_t plaintextSize);
bool encodeProtectedFileHeader(const ProtectedFileDescription& description,
                               ProtectedFileHeader* output);
bool decodeProtectedFileHeader(const ProtectedFileHeader& input,
                               ProtectedFileDescription* output);
bool buildProtectedFileChunkNonce(
    const ProtectedFileDescription& description, std::size_t chunkIndex,
    std::array<std::uint8_t,
               services::security::kDeviceLockWrapNonceBytes>* output);
bool buildProtectedFileChunkAad(const ProtectedFileHeader& header,
                                const char* relativePath,
                                std::size_t chunkIndex,
                                ProtectedFileAad* output,
                                std::size_t* outputSize);

}  // namespace leshy1::storage
