#include "DeviceLockRecord.h"

#include <algorithm>

namespace leshy1::services::security {
namespace {

constexpr std::array<std::uint8_t, 4> kMagic = {'L', 'D', 'L', 'K'};

void putU32(std::uint8_t* output, std::uint32_t value) {
    output[0] = static_cast<std::uint8_t>(value);
    output[1] = static_cast<std::uint8_t>(value >> 8U);
    output[2] = static_cast<std::uint8_t>(value >> 16U);
    output[3] = static_cast<std::uint8_t>(value >> 24U);
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

}  // namespace

bool encodeDeviceLockRecord(const DeviceLockCredential& credential,
                            DeviceLockRecord* output) {
    if (output == nullptr || !credential.valid()) return false;
    output->fill(0);
    std::copy(kMagic.begin(), kMagic.end(), output->begin());
    (*output)[4] = credential.schemaVersion;
    (*output)[5] = credential.failedAttempts;
    putU32(output->data() + 8U, credential.iterations);
    putU32(output->data() + 12U, credential.generation);
    std::copy(credential.salt.begin(), credential.salt.end(),
              output->begin() + 16U);
    std::copy(credential.verifier.begin(), credential.verifier.end(),
              output->begin() + 32U);
    std::copy(credential.wrapNonce.begin(), credential.wrapNonce.end(),
              output->begin() + 64U);
    std::copy(credential.wrappedDataKey.begin(),
              credential.wrappedDataKey.end(), output->begin() + 76U);
    std::copy(credential.wrapTag.begin(), credential.wrapTag.end(),
              output->begin() + 108U);
    putU32(output->data() + 124U, crc32(output->data(), 124U));
    return true;
}

bool decodeDeviceLockRecord(const DeviceLockRecord& input,
                            DeviceLockCredential* output) {
    if (output == nullptr ||
        !std::equal(kMagic.begin(), kMagic.end(), input.begin()) ||
        getU32(input.data() + 124U) != crc32(input.data(), 124U) ||
        input[6] != 0 || input[7] != 0) {
        return false;
    }
    DeviceLockCredential candidate{};
    candidate.schemaVersion = input[4];
    candidate.failedAttempts = input[5];
    candidate.iterations = getU32(input.data() + 8U);
    candidate.generation = getU32(input.data() + 12U);
    std::copy_n(input.begin() + 16U, candidate.salt.size(),
                candidate.salt.begin());
    std::copy_n(input.begin() + 32U, candidate.verifier.size(),
                candidate.verifier.begin());
    std::copy_n(input.begin() + 64U, candidate.wrapNonce.size(),
                candidate.wrapNonce.begin());
    std::copy_n(input.begin() + 76U, candidate.wrappedDataKey.size(),
                candidate.wrappedDataKey.begin());
    std::copy_n(input.begin() + 108U, candidate.wrapTag.size(),
                candidate.wrapTag.begin());
    if (!candidate.valid()) {
        candidate.clear();
        return false;
    }
    *output = candidate;
    candidate.clear();
    return true;
}

}  // namespace leshy1::services::security
