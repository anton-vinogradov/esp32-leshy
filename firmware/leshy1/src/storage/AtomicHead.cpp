#include "AtomicHead.h"

#include <cstring>

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kMagic[4] = {'L', 'S', 'H', 'H'};

void put16(std::uint8_t* output, std::uint16_t value) {
    output[0] = static_cast<std::uint8_t>(value >> 8U);
    output[1] = static_cast<std::uint8_t>(value);
}

void put32(std::uint8_t* output, std::uint32_t value) {
    output[0] = static_cast<std::uint8_t>(value >> 24U);
    output[1] = static_cast<std::uint8_t>(value >> 16U);
    output[2] = static_cast<std::uint8_t>(value >> 8U);
    output[3] = static_cast<std::uint8_t>(value);
}

std::uint16_t get16(const std::uint8_t* input) {
    return static_cast<std::uint16_t>((static_cast<std::uint16_t>(input[0]) << 8U) |
                                      static_cast<std::uint16_t>(input[1]));
}

std::uint32_t get32(const std::uint8_t* input) {
    return (static_cast<std::uint32_t>(input[0]) << 24U) |
           (static_cast<std::uint32_t>(input[1]) << 16U) |
           (static_cast<std::uint32_t>(input[2]) << 8U) |
           static_cast<std::uint32_t>(input[3]);
}

CandidateStatus evaluate(const HeadCandidate& candidate, HeadRecord* record) {
    if (decodeHead(candidate.wire, candidate.wireSize, record) != HeadDecodeStatus::Valid) {
        return CandidateStatus::InvalidHead;
    }
    if (!candidate.manifest.present) return CandidateStatus::MissingManifest;
    if (candidate.manifest.length != record->manifestLength ||
        candidate.manifest.crc32c != record->manifestCrc32c) {
        return CandidateStatus::ManifestMismatch;
    }
    if (!candidate.payloadValid) return CandidateStatus::InvalidPayload;
    return CandidateStatus::Valid;
}

}  // namespace

std::uint32_t crc32c(const std::uint8_t* data, std::size_t size) {
    if (data == nullptr && size != 0) return 0;
    std::uint32_t crc = 0xFFFFFFFFU;
    for (std::size_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            const std::uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1U) ^ (0x82F63B78U & mask);
        }
    }
    return ~crc;
}

bool encodeHead(const HeadRecord& record, std::uint8_t* output, std::size_t size) {
    if (output == nullptr || size < kHeadWireSize) return false;
    std::memset(output, 0, kHeadWireSize);
    std::memcpy(output, kMagic, sizeof(kMagic));
    put16(output + 4, kHeadSchemaVersion);
    put16(output + 6, 0);  // reserved flags must remain zero in schema v1
    put32(output + 8, record.generation);
    put32(output + 12, record.manifestLength);
    put32(output + 16, record.manifestCrc32c);
    put32(output + 20, crc32c(output, 20));
    return true;
}

HeadDecodeStatus decodeHead(const std::uint8_t* wire, std::size_t size, HeadRecord* output) {
    if (wire == nullptr || output == nullptr || size < kHeadWireSize) {
        return HeadDecodeStatus::TooShort;
    }
    if (std::memcmp(wire, kMagic, sizeof(kMagic)) != 0) {
        return HeadDecodeStatus::MagicMismatch;
    }
    if (get16(wire + 4) != kHeadSchemaVersion) {
        return HeadDecodeStatus::UnsupportedSchema;
    }
    if (get16(wire + 6) != 0) return HeadDecodeStatus::InvalidFlags;
    if (get32(wire + 20) != crc32c(wire, 20)) {
        return HeadDecodeStatus::ChecksumMismatch;
    }
    output->generation = get32(wire + 8);
    output->manifestLength = get32(wire + 12);
    output->manifestCrc32c = get32(wire + 16);
    return HeadDecodeStatus::Valid;
}

RecoveryResult recoverHead(const HeadCandidate& a, const HeadCandidate& b) {
    RecoveryResult result;
    HeadRecord aRecord;
    HeadRecord bRecord;
    result.aStatus = evaluate(a, &aRecord);
    result.bStatus = evaluate(b, &bRecord);
    const bool aValid = result.aStatus == CandidateStatus::Valid;
    const bool bValid = result.bStatus == CandidateStatus::Valid;
    if (!aValid && !bValid) return result;
    if (aValid && !bValid) {
        result.choice = RecoveryChoice::A;
        result.selected = aRecord;
        return result;
    }
    if (!aValid && bValid) {
        result.choice = RecoveryChoice::B;
        result.selected = bRecord;
        return result;
    }

    if (aRecord.generation == bRecord.generation) {
        if (aRecord.manifestLength != bRecord.manifestLength ||
            aRecord.manifestCrc32c != bRecord.manifestCrc32c) {
            result.choice = RecoveryChoice::Conflict;
            return result;
        }
        result.choice = RecoveryChoice::A;
        result.selected = aRecord;
        return result;
    }

    const std::uint32_t delta = aRecord.generation - bRecord.generation;
    if (delta == 0x80000000U) {
        result.choice = RecoveryChoice::Conflict;
    } else if (delta < 0x80000000U) {
        result.choice = RecoveryChoice::A;
        result.selected = aRecord;
    } else {
        result.choice = RecoveryChoice::B;
        result.selected = bRecord;
    }
    return result;
}

CommitResult commitGeneration(CommitBackend& backend, const HeadRecord& next) {
    std::uint8_t wire[kHeadWireSize] = {};
    if (!encodeHead(next, wire, sizeof(wire))) return {false, CommitStage::WriteHead};
    if (!backend.writePayloads()) return {false, CommitStage::WritePayloads};
    if (!backend.syncPayloads()) return {false, CommitStage::SyncPayloads};
    if (!backend.writeManifest()) return {false, CommitStage::WriteManifest};
    if (!backend.syncManifest()) return {false, CommitStage::SyncManifest};
    if (!backend.writeOlderHead(wire, sizeof(wire))) return {false, CommitStage::WriteHead};
    if (!backend.syncHead()) return {false, CommitStage::SyncHead};
    return {true, CommitStage::Complete};
}

}  // namespace leshy1::storage
