#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>

#include "storage/ProtectedFileEnvelope.h"

using namespace leshy1::storage;

namespace {

int failures = 0;

#define CHECK(expression)                                                     \
    do {                                                                      \
        if (!(expression)) {                                                  \
            std::cerr << __FILE__ << ':' << __LINE__                          \
                      << ": check failed: " #expression << '\n';             \
            ++failures;                                                       \
        }                                                                     \
    } while (false)

ProtectedFileDescription description(std::uint32_t size) {
    ProtectedFileDescription value{};
    value.plaintextSize = size;
    for (std::size_t index = 0; index < 8U; ++index) {
        value.nonceSeed[index] = static_cast<std::uint8_t>(0x31U + index);
    }
    return value;
}

void testExactChunkAndPhysicalBounds() {
    CHECK(protectedFileChunkCount(0) == 0U);
    CHECK(protectedFileChunkCount(1) == 1U);
    CHECK(protectedFileChunkCount(256) == 1U);
    CHECK(protectedFileChunkCount(257) == 2U);
    CHECK(protectedFileChunkSize(257, 0) == 256U);
    CHECK(protectedFileChunkSize(257, 1) == 1U);
    CHECK(protectedFileChunkSize(257, 2) == 0U);
    CHECK(protectedFilePhysicalSize(1) == 49U);
    CHECK(protectedFilePhysicalSize(256) == 304U);
    CHECK(protectedFilePhysicalSize(257) == 321U);
}

void testHeaderRoundTripAndEveryRegionCorruption() {
    const ProtectedFileDescription source = description(12288U);
    ProtectedFileHeader header{};
    CHECK(encodeProtectedFileHeader(source, &header));
    ProtectedFileDescription decoded{};
    CHECK(decodeProtectedFileHeader(header, &decoded));
    CHECK(decoded.plaintextSize == source.plaintextSize);
    CHECK(decoded.nonceSeed == source.nonceSeed);
    for (const std::size_t index : {0U, 4U, 5U, 6U, 8U, 12U, 24U, 28U}) {
        ProtectedFileHeader corrupt = header;
        corrupt[index] ^= 0x01U;
        ProtectedFileDescription rejected{};
        CHECK(!decodeProtectedFileHeader(corrupt, &rejected));
    }
}

void testNonceAndAadBindChunkPathAndHeader() {
    const ProtectedFileDescription source = description(513U);
    ProtectedFileHeader header{};
    CHECK(encodeProtectedFileHeader(source, &header));
    std::array<std::uint8_t,
               leshy1::services::security::kDeviceLockWrapNonceBytes> first{};
    auto second = first;
    CHECK(buildProtectedFileChunkNonce(source, 0, &first));
    CHECK(buildProtectedFileChunkNonce(source, 1, &second));
    CHECK(first != second);
    CHECK(!buildProtectedFileChunkNonce(source, 3, &second));

    ProtectedFileAad firstAad{};
    ProtectedFileAad secondAad{};
    ProtectedFileAad otherPathAad{};
    std::size_t firstSize = 0;
    std::size_t secondSize = 0;
    std::size_t otherPathSize = 0;
    CHECK(buildProtectedFileChunkAad(header, "segment-1.bin", 0,
                                     &firstAad, &firstSize));
    CHECK(buildProtectedFileChunkAad(header, "segment-1.bin", 1,
                                     &secondAad, &secondSize));
    CHECK(buildProtectedFileChunkAad(header, "segment-2.bin", 0,
                                     &otherPathAad, &otherPathSize));
    CHECK(firstSize == secondSize);
    CHECK(firstSize == otherPathSize);
    CHECK(firstAad != secondAad);
    CHECK(firstAad != otherPathAad);
    CHECK(std::memcmp(firstAad.data(), header.data(), header.size()) == 0);
}

}  // namespace

int main() {
    testExactChunkAndPhysicalBounds();
    testHeaderRoundTripAndEveryRegionCorruption();
    testNonceAndAadBindChunkPathAndHeader();
    if (failures != 0) {
        std::cerr << failures << " protected file envelope checks failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "Protected file envelope tests passed\n";
    return EXIT_SUCCESS;
}
