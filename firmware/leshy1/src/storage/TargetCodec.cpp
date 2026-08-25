#include "TargetCodec.h"

#include <cstring>
#include <limits>

#include "AtomicHead.h"

namespace leshy1::storage {
namespace {

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

class CborWriter final {
public:
    CborWriter(std::uint8_t* output, std::size_t capacity)
        : output_(output), capacity_(capacity) {}

    bool unsignedValue(std::uint64_t value) { return typeValue(0, value); }
    bool map(std::uint64_t size) { return typeValue(5, size); }
    bool array(std::uint64_t size) { return typeValue(4, size); }
    bool text(const char* value, std::size_t size) {
        return value != nullptr && typeValue(3, size) && raw(value, size);
    }
    bool bytes(const std::uint8_t* value, std::size_t size) {
        return (value != nullptr || size == 0) &&
            typeValue(2, size) && raw(value, size);
    }
    bool boolean(bool value) {
        const std::uint8_t wire = value ? 0xf5U : 0xf4U;
        return raw(&wire, 1);
    }
    bool ok() const { return ok_; }
    std::size_t size() const { return position_; }

private:
    bool typeValue(std::uint8_t major, std::uint64_t value) {
        std::uint8_t wire[9] = {};
        std::size_t size = 1;
        if (value < 24) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | value);
        } else if (value <= 0xffU) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 24U);
            wire[1] = static_cast<std::uint8_t>(value);
            size = 2;
        } else if (value <= 0xffffU) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 25U);
            put16(wire + 1, static_cast<std::uint16_t>(value));
            size = 3;
        } else if (value <= 0xffffffffU) {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 26U);
            put32(wire + 1, static_cast<std::uint32_t>(value));
            size = 5;
        } else {
            wire[0] = static_cast<std::uint8_t>((major << 5U) | 27U);
            for (std::size_t index = 0; index < 8; ++index) {
                wire[index + 1] = static_cast<std::uint8_t>(
                    value >> ((7U - index) * 8U));
            }
            size = 9;
        }
        return raw(wire, size);
    }

    bool raw(const void* value, std::size_t size) {
        if (!ok_ || (value == nullptr && size != 0) ||
            size > capacity_ - position_) {
            ok_ = false;
            return false;
        }
        if (size != 0) std::memcpy(output_ + position_, value, size);
        position_ += size;
        return true;
    }

    std::uint8_t* output_ = nullptr;
    std::size_t capacity_ = 0;
    std::size_t position_ = 0;
    bool ok_ = true;
};

class CborReader final {
public:
    CborReader(const std::uint8_t* input, std::size_t size)
        : input_(input), size_(size) {}

    bool unsignedValue(std::uint64_t* value) { return typeValue(0, value); }
    bool map(std::uint64_t* value) { return typeValue(5, value); }
    bool array(std::uint64_t* value) { return typeValue(4, value); }
    bool text(const std::uint8_t** value, std::size_t* length) {
        return sizedValue(3, value, length);
    }
    bool bytes(const std::uint8_t** value, std::size_t* length) {
        return sizedValue(2, value, length);
    }
    bool boolean(bool* value) {
        if (value == nullptr || position_ >= size_) return false;
        const std::uint8_t wire = input_[position_++];
        if (wire == 0xf4U) {
            *value = false;
            return true;
        }
        if (wire == 0xf5U) {
            *value = true;
            return true;
        }
        return false;
    }
    bool complete() const { return position_ == size_; }

private:
    bool typeValue(std::uint8_t expectedMajor, std::uint64_t* value) {
        if (value == nullptr || position_ >= size_) return false;
        const std::uint8_t initial = input_[position_++];
        if ((initial >> 5U) != expectedMajor) return false;
        const std::uint8_t additional = initial & 0x1fU;
        if (additional < 24) {
            *value = additional;
            return true;
        }
        std::size_t bytes = 0;
        if (additional == 24) bytes = 1;
        else if (additional == 25) bytes = 2;
        else if (additional == 26) bytes = 4;
        else if (additional == 27) bytes = 8;
        else return false;
        if (bytes > size_ - position_) return false;
        std::uint64_t decoded = 0;
        for (std::size_t index = 0; index < bytes; ++index) {
            decoded = (decoded << 8U) | input_[position_++];
        }
        if ((bytes == 1 && decoded < 24) ||
            (bytes == 2 && decoded <= 0xffU) ||
            (bytes == 4 && decoded <= 0xffffU) ||
            (bytes == 8 && decoded <= 0xffffffffU)) {
            return false;
        }
        *value = decoded;
        return true;
    }

    bool sizedValue(std::uint8_t major, const std::uint8_t** value,
                    std::size_t* length) {
        if (value == nullptr || length == nullptr) return false;
        std::uint64_t decoded = 0;
        if (!typeValue(major, &decoded) || decoded > size_ - position_) {
            return false;
        }
        *value = input_ + position_;
        *length = static_cast<std::size_t>(decoded);
        position_ += *length;
        return true;
    }

    const std::uint8_t* input_ = nullptr;
    std::size_t size_ = 0;
    std::size_t position_ = 0;
};

bool key(CborReader& reader, std::uint64_t expected) {
    std::uint64_t value = 0;
    return reader.unsignedValue(&value) && value == expected;
}

bool encodeIdentity(CborWriter& writer,
                    const domain::targets::TargetIdentity& identity) {
    return writer.map(3) && writer.unsignedValue(0) &&
        writer.unsignedValue(static_cast<std::uint8_t>(identity.kind)) &&
        writer.unsignedValue(1) &&
        writer.bytes(identity.value.data(), identity.length) &&
        writer.unsignedValue(2) &&
        writer.unsignedValue(identity.discriminator);
}

bool encodeEvidence(CborWriter& writer,
                    const domain::targets::TargetEvidenceRef& evidence) {
    return writer.map(4) && writer.unsignedValue(0) &&
        writer.bytes(evidence.sourceId.bytes.data(), evidence.sourceId.bytes.size()) &&
        writer.unsignedValue(1) &&
        writer.unsignedValue(evidence.sourceGeneration) &&
        writer.unsignedValue(2) &&
        writer.unsignedValue(evidence.observationSequence) &&
        writer.unsignedValue(3) &&
        writer.unsignedValue(evidence.observedMonotonicUs);
}

bool encodeRecord(CborWriter& writer,
                  const domain::targets::TargetRecord& record) {
    if (!writer.map(8) || !writer.unsignedValue(0) ||
        !writer.bytes(record.id.bytes.data(), record.id.bytes.size()) ||
        !writer.unsignedValue(1) || !writer.array(record.identityCount)) {
        return false;
    }
    for (std::size_t index = 0; index < record.identityCount; ++index) {
        if (!encodeIdentity(writer, record.identities[index])) return false;
    }
    if (!writer.unsignedValue(2) || !writer.array(record.evidenceCount)) {
        return false;
    }
    for (std::size_t index = 0; index < record.evidenceCount; ++index) {
        if (!encodeEvidence(writer, record.evidence[index])) return false;
    }
    if (!writer.unsignedValue(3) ||
        !writer.text(record.name.data(), record.nameLength) ||
        !writer.unsignedValue(4) ||
        !writer.text(record.notes.data(), record.notesLength) ||
        !writer.unsignedValue(5) || !writer.array(record.tagCount)) {
        return false;
    }
    for (std::size_t index = 0; index < record.tagCount; ++index) {
        if (!writer.text(record.tags[index].data(), record.tagLengths[index])) {
            return false;
        }
    }
    return writer.unsignedValue(6) && writer.boolean(record.favorite) &&
        writer.unsignedValue(7) && writer.unsignedValue(record.revision);
}

TargetCodecStatus decodeIdentity(CborReader& reader,
                                 domain::targets::TargetIdentity* output) {
    std::uint64_t count = 0;
    std::uint64_t value = 0;
    const std::uint8_t* bytes = nullptr;
    std::size_t length = 0;
    if (output == nullptr || !reader.map(&count) || count != 3 ||
        !key(reader, 0) || !reader.unsignedValue(&value) ||
        value < static_cast<std::uint8_t>(
            domain::targets::TargetIdentityKind::WifiBssid) ||
        value > static_cast<std::uint8_t>(
            domain::targets::TargetIdentityKind::BleAddress)) {
        return TargetCodecStatus::Malformed;
    }
    output->kind = static_cast<domain::targets::TargetIdentityKind>(value);
    if (!key(reader, 1) || !reader.bytes(&bytes, &length) ||
        length != output->value.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    std::memcpy(output->value.data(), bytes, length);
    output->length = static_cast<std::uint8_t>(length);
    if (!key(reader, 2) || !reader.unsignedValue(&value) || value > 0xffU) {
        return TargetCodecStatus::Malformed;
    }
    output->discriminator = static_cast<std::uint8_t>(value);
    return domain::targets::targetIdentityValid(*output)
        ? TargetCodecStatus::Valid : TargetCodecStatus::Malformed;
}

TargetCodecStatus decodeEvidence(CborReader& reader,
                                 domain::targets::TargetEvidenceRef* output) {
    std::uint64_t count = 0;
    std::uint64_t value = 0;
    const std::uint8_t* bytes = nullptr;
    std::size_t length = 0;
    if (output == nullptr || !reader.map(&count) || count != 4 ||
        !key(reader, 0) || !reader.bytes(&bytes, &length) ||
        length != output->sourceId.bytes.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    std::memcpy(output->sourceId.bytes.data(), bytes, length);
    if (!key(reader, 1) || !reader.unsignedValue(&value) ||
        value > std::numeric_limits<std::uint32_t>::max()) {
        return TargetCodecStatus::Malformed;
    }
    output->sourceGeneration = static_cast<std::uint32_t>(value);
    if (!key(reader, 2) ||
        !reader.unsignedValue(&output->observationSequence) ||
        !key(reader, 3) ||
        !reader.unsignedValue(&output->observedMonotonicUs)) {
        return TargetCodecStatus::Malformed;
    }
    return domain::targets::targetEvidenceValid(*output)
        ? TargetCodecStatus::Valid : TargetCodecStatus::Malformed;
}

TargetCodecStatus decodeText(CborReader& reader, std::uint64_t expectedKey,
                             char* output, std::size_t capacity,
                             std::size_t* outputLength) {
    const std::uint8_t* bytes = nullptr;
    std::size_t length = 0;
    if (!key(reader, expectedKey) || !reader.text(&bytes, &length)) {
        return TargetCodecStatus::Malformed;
    }
    if (output == nullptr || outputLength == nullptr || length >= capacity) {
        return TargetCodecStatus::BoundsExceeded;
    }
    if (length != 0) std::memcpy(output, bytes, length);
    output[length] = '\0';
    *outputLength = length;
    return TargetCodecStatus::Valid;
}

TargetCodecStatus decodeRecord(CborReader& reader,
                               domain::targets::TargetRecord* output) {
    if (output == nullptr) return TargetCodecStatus::InvalidArgument;
    *output = {};
    std::uint64_t count = 0;
    const std::uint8_t* bytes = nullptr;
    std::size_t length = 0;
    if (!reader.map(&count) || count != 8 || !key(reader, 0) ||
        !reader.bytes(&bytes, &length) || length != output->id.bytes.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    std::memcpy(output->id.bytes.data(), bytes, length);
    if (!key(reader, 1) || !reader.array(&count) ||
        count == 0 || count > output->identities.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->identityCount = static_cast<std::uint8_t>(count);
    for (std::size_t index = 0; index < output->identityCount; ++index) {
        const TargetCodecStatus status =
            decodeIdentity(reader, &output->identities[index]);
        if (status != TargetCodecStatus::Valid) return status;
    }
    if (!key(reader, 2) || !reader.array(&count) ||
        count == 0 || count > output->evidence.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->evidenceCount = static_cast<std::uint8_t>(count);
    for (std::size_t index = 0; index < output->evidenceCount; ++index) {
        const TargetCodecStatus status =
            decodeEvidence(reader, &output->evidence[index]);
        if (status != TargetCodecStatus::Valid) return status;
    }
    std::size_t textLength = 0;
    TargetCodecStatus status = decodeText(
        reader, 3, output->name.data(), output->name.size(), &textLength);
    if (status != TargetCodecStatus::Valid) return status;
    output->nameLength = static_cast<std::uint8_t>(textLength);
    status = decodeText(
        reader, 4, output->notes.data(), output->notes.size(), &textLength);
    if (status != TargetCodecStatus::Valid) return status;
    output->notesLength = static_cast<std::uint16_t>(textLength);
    if (!key(reader, 5) || !reader.array(&count) ||
        count > output->tags.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->tagCount = static_cast<std::uint8_t>(count);
    for (std::size_t index = 0; index < output->tagCount; ++index) {
        if (!reader.text(&bytes, &length) || length == 0 ||
            length >= output->tags[index].size()) {
            return TargetCodecStatus::BoundsExceeded;
        }
        std::memcpy(output->tags[index].data(), bytes, length);
        output->tags[index][length] = '\0';
        output->tagLengths[index] = static_cast<std::uint8_t>(length);
    }
    if (!key(reader, 6) || !reader.boolean(&output->favorite) ||
        !key(reader, 7)) {
        return TargetCodecStatus::Malformed;
    }
    std::uint64_t revision = 0;
    if (!reader.unsignedValue(&revision) || revision == 0 ||
        revision > std::numeric_limits<std::uint32_t>::max()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->revision = static_cast<std::uint32_t>(revision);
    return TargetCodecStatus::Valid;
}

bool encodeCorrelationFeature(
    CborWriter& writer,
    const domain::targets::CorrelationFeature& feature) {
    return writer.map(5) && writer.unsignedValue(0) &&
        writer.unsignedValue(static_cast<std::uint8_t>(feature.kind)) &&
        writer.unsignedValue(1) &&
        writer.unsignedValue(feature.strengthPermille) &&
        writer.unsignedValue(2) &&
        writer.unsignedValue(feature.maximumPoints) &&
        writer.unsignedValue(3) &&
        writer.unsignedValue(feature.awardedPoints) &&
        writer.unsignedValue(4) &&
        encodeEvidence(writer, feature.targetEvidence);
}

bool encodeCorrelationProposal(
    CborWriter& writer,
    const domain::targets::CorrelationProposal& proposal) {
    if (!writer.map(8) || !writer.unsignedValue(0) ||
        !writer.bytes(proposal.id.bytes.data(), proposal.id.bytes.size()) ||
        !writer.unsignedValue(1) ||
        !writer.bytes(proposal.targetId.bytes.data(),
                      proposal.targetId.bytes.size()) ||
        !writer.unsignedValue(2) ||
        !encodeIdentity(writer, proposal.candidateIdentity) ||
        !writer.unsignedValue(3) ||
        !encodeEvidence(writer, proposal.candidateEvidence) ||
        !writer.unsignedValue(4) || !writer.array(proposal.featureCount)) {
        return false;
    }
    for (std::size_t index = 0; index < proposal.featureCount; ++index) {
        if (!encodeCorrelationFeature(writer, proposal.features[index])) {
            return false;
        }
    }
    return writer.unsignedValue(5) &&
        writer.unsignedValue(proposal.scorePermille) &&
        writer.unsignedValue(6) &&
        writer.unsignedValue(static_cast<std::uint8_t>(proposal.confidence)) &&
        writer.unsignedValue(7) && writer.boolean(proposal.stale);
}

bool encodeCorrelationDecision(
    CborWriter& writer,
    const domain::targets::CorrelationDecisionRecord& record) {
    return writer.map(4) && writer.unsignedValue(0) &&
        encodeCorrelationProposal(writer, record.proposal) &&
        writer.unsignedValue(1) &&
        writer.unsignedValue(static_cast<std::uint8_t>(record.decision)) &&
        writer.unsignedValue(2) &&
        writer.unsignedValue(record.targetRevisionBefore) &&
        writer.unsignedValue(3) &&
        writer.unsignedValue(record.targetRevisionAfter);
}

TargetCodecStatus decodeCorrelationFeature(
    CborReader& reader, domain::targets::CorrelationFeature* output) {
    if (output == nullptr) return TargetCodecStatus::InvalidArgument;
    *output = {};
    std::uint64_t count = 0;
    std::uint64_t value = 0;
    if (!reader.map(&count) || count != 5 || !key(reader, 0) ||
        !reader.unsignedValue(&value) ||
        value < static_cast<std::uint8_t>(
            domain::targets::CorrelationFeatureKind::AssignedVendorMatch) ||
        value > static_cast<std::uint8_t>(
            domain::targets::CorrelationFeatureKind::SignalTrendMatch)) {
        return TargetCodecStatus::Malformed;
    }
    output->kind =
        static_cast<domain::targets::CorrelationFeatureKind>(value);
    if (!key(reader, 1) || !reader.unsignedValue(&value) ||
        value > 1000U) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->strengthPermille = static_cast<std::uint16_t>(value);
    if (!key(reader, 2) || !reader.unsignedValue(&value) ||
        value > 1000U) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->maximumPoints = static_cast<std::uint16_t>(value);
    if (!key(reader, 3) || !reader.unsignedValue(&value) ||
        value > 1000U) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->awardedPoints = static_cast<std::uint16_t>(value);
    if (!key(reader, 4)) return TargetCodecStatus::Malformed;
    return decodeEvidence(reader, &output->targetEvidence);
}

TargetCodecStatus decodeCorrelationProposal(
    CborReader& reader, domain::targets::CorrelationProposal* output) {
    if (output == nullptr) return TargetCodecStatus::InvalidArgument;
    *output = {};
    std::uint64_t count = 0;
    std::uint64_t value = 0;
    const std::uint8_t* bytes = nullptr;
    std::size_t length = 0;
    if (!reader.map(&count) || count != 8 || !key(reader, 0) ||
        !reader.bytes(&bytes, &length) ||
        length != output->id.bytes.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    std::memcpy(output->id.bytes.data(), bytes, length);
    if (!key(reader, 1) || !reader.bytes(&bytes, &length) ||
        length != output->targetId.bytes.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    std::memcpy(output->targetId.bytes.data(), bytes, length);
    if (!key(reader, 2)) return TargetCodecStatus::Malformed;
    TargetCodecStatus status =
        decodeIdentity(reader, &output->candidateIdentity);
    if (status != TargetCodecStatus::Valid) return status;
    if (!key(reader, 3)) return TargetCodecStatus::Malformed;
    status = decodeEvidence(reader, &output->candidateEvidence);
    if (status != TargetCodecStatus::Valid) return status;
    if (!key(reader, 4) || !reader.array(&count) || count == 0 ||
        count > output->features.size()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->featureCount = static_cast<std::uint8_t>(count);
    for (std::size_t index = 0; index < output->featureCount; ++index) {
        status = decodeCorrelationFeature(reader, &output->features[index]);
        if (status != TargetCodecStatus::Valid) return status;
    }
    if (!key(reader, 5) || !reader.unsignedValue(&value) || value > 1000U) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->scorePermille = static_cast<std::uint16_t>(value);
    if (!key(reader, 6) || !reader.unsignedValue(&value) ||
        value > static_cast<std::uint8_t>(
            domain::targets::CorrelationConfidence::Stale)) {
        return TargetCodecStatus::Malformed;
    }
    output->confidence =
        static_cast<domain::targets::CorrelationConfidence>(value);
    if (!key(reader, 7) || !reader.boolean(&output->stale)) {
        return TargetCodecStatus::Malformed;
    }
    return domain::targets::correlationProposalValid(*output)
        ? TargetCodecStatus::Valid : TargetCodecStatus::Malformed;
}

TargetCodecStatus decodeCorrelationDecision(
    CborReader& reader,
    domain::targets::CorrelationDecisionRecord* output) {
    if (output == nullptr) return TargetCodecStatus::InvalidArgument;
    *output = {};
    std::uint64_t count = 0;
    std::uint64_t value = 0;
    if (!reader.map(&count) || count != 4 || !key(reader, 0)) {
        return TargetCodecStatus::Malformed;
    }
    TargetCodecStatus status =
        decodeCorrelationProposal(reader, &output->proposal);
    if (status != TargetCodecStatus::Valid) return status;
    if (!key(reader, 1) || !reader.unsignedValue(&value) ||
        value < static_cast<std::uint8_t>(
            domain::targets::CorrelationDecision::Accept) ||
        value > static_cast<std::uint8_t>(
            domain::targets::CorrelationDecision::Reject)) {
        return TargetCodecStatus::Malformed;
    }
    output->decision =
        static_cast<domain::targets::CorrelationDecision>(value);
    if (!key(reader, 2) || !reader.unsignedValue(&value) || value == 0 ||
        value > std::numeric_limits<std::uint32_t>::max()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->targetRevisionBefore = static_cast<std::uint32_t>(value);
    if (!key(reader, 3) || !reader.unsignedValue(&value) || value == 0 ||
        value > std::numeric_limits<std::uint32_t>::max()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    output->targetRevisionAfter = static_cast<std::uint32_t>(value);
    return TargetCodecStatus::Valid;
}

}  // namespace

const char* targetCodecStatusName(TargetCodecStatus status) {
    switch (status) {
        case TargetCodecStatus::Valid: return "valid";
        case TargetCodecStatus::InvalidArgument: return "invalid_argument";
        case TargetCodecStatus::BufferTooSmall: return "buffer_too_small";
        case TargetCodecStatus::Malformed: return "malformed";
        case TargetCodecStatus::UnsupportedSchema: return "unsupported_schema";
        case TargetCodecStatus::BoundsExceeded: return "bounds_exceeded";
        case TargetCodecStatus::Conflict: return "conflict";
        case TargetCodecStatus::ChecksumMismatch: return "checksum_mismatch";
        case TargetCodecStatus::TrailingData: return "trailing_data";
    }
    return "malformed";
}

TargetCodecStatus encodeTargetCatalog(
    const domain::targets::TargetCatalog& catalog,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr || catalog.size() == 0 ||
        catalog.size() > domain::targets::TargetCatalog::kCapacity) {
        return TargetCodecStatus::InvalidArgument;
    }
    CborWriter writer(output, capacity);
    writer.map(2);
    writer.unsignedValue(0);
    writer.unsignedValue(kTargetCatalogSchemaVersion);
    writer.unsignedValue(1);
    writer.array(catalog.size());
    for (std::size_t index = 0; index < catalog.size(); ++index) {
        const domain::targets::TargetRecord* record = catalog.get(index);
        if (record == nullptr || !encodeRecord(writer, *record)) {
            return writer.ok() ? TargetCodecStatus::InvalidArgument
                               : TargetCodecStatus::BufferTooSmall;
        }
    }
    if (!writer.ok()) return TargetCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return TargetCodecStatus::Valid;
}

TargetCodecStatus decodeTargetCatalog(
    const std::uint8_t* input, std::size_t size,
    domain::targets::TargetCatalog* output) {
    if (input == nullptr || output == nullptr || size == 0 ||
        size > kTargetCatalogMaxBytes) {
        return TargetCodecStatus::InvalidArgument;
    }
    output->clear();
    CborReader reader(input, size);
    std::uint64_t count = 0;
    std::uint64_t version = 0;
    if (!reader.map(&count) || count != 2 || !key(reader, 0) ||
        !reader.unsignedValue(&version)) {
        return TargetCodecStatus::Malformed;
    }
    if (version != kTargetCatalogSchemaVersion) {
        return TargetCodecStatus::UnsupportedSchema;
    }
    if (!key(reader, 1) || !reader.array(&count) || count == 0 ||
        count > domain::targets::TargetCatalog::kCapacity) {
        return TargetCodecStatus::BoundsExceeded;
    }
    for (std::size_t index = 0; index < count; ++index) {
        domain::targets::TargetRecord record{};
        const TargetCodecStatus status = decodeRecord(reader, &record);
        if (status != TargetCodecStatus::Valid) {
            output->clear();
            return status;
        }
        if (output->restore(record) !=
            domain::targets::TargetMutationStatus::Created) {
            output->clear();
            return TargetCodecStatus::Conflict;
        }
    }
    if (!reader.complete()) {
        output->clear();
        return TargetCodecStatus::TrailingData;
    }
    return TargetCodecStatus::Valid;
}

TargetCodecStatus encodeTargetManifest(
    const domain::targets::TargetCatalog& catalog,
    const std::uint8_t* catalogBytes, std::size_t catalogSize,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (catalog.size() == 0 || catalog.size() > UINT16_MAX ||
        catalogBytes == nullptr || catalogSize == 0 ||
        catalogSize > kTargetCatalogMaxBytes || output == nullptr ||
        outputSize == nullptr) {
        return TargetCodecStatus::InvalidArgument;
    }
    CborWriter writer(output, capacity);
    writer.map(4);
    writer.unsignedValue(0);
    writer.unsignedValue(kTargetCatalogSchemaVersion);
    writer.unsignedValue(1);
    writer.unsignedValue(catalog.size());
    writer.unsignedValue(2);
    writer.unsignedValue(catalogSize);
    writer.unsignedValue(3);
    writer.unsignedValue(crc32c(catalogBytes, catalogSize));
    if (!writer.ok()) return TargetCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return TargetCodecStatus::Valid;
}

TargetCodecStatus decodeTargetManifest(
    const std::uint8_t* input, std::size_t size, TargetManifest* output) {
    if (input == nullptr || output == nullptr || size == 0 ||
        size > kTargetManifestMaxBytes) {
        return TargetCodecStatus::InvalidArgument;
    }
    CborReader reader(input, size);
    std::uint64_t count = 0;
    std::uint64_t value = 0;
    if (!reader.map(&count) || count != 4 || !key(reader, 0) ||
        !reader.unsignedValue(&value)) {
        return TargetCodecStatus::Malformed;
    }
    if (value != kTargetCatalogSchemaVersion) {
        return TargetCodecStatus::UnsupportedSchema;
    }
    TargetManifest manifest{};
    manifest.schemaVersion = static_cast<std::uint16_t>(value);
    if (!key(reader, 1) || !reader.unsignedValue(&value) || value == 0 ||
        value > domain::targets::TargetCatalog::kCapacity) {
        return TargetCodecStatus::BoundsExceeded;
    }
    manifest.targetCount = static_cast<std::uint16_t>(value);
    if (!key(reader, 2) || !reader.unsignedValue(&value) || value == 0 ||
        value > kTargetCatalogMaxBytes) {
        return TargetCodecStatus::BoundsExceeded;
    }
    manifest.catalogLength = static_cast<std::uint32_t>(value);
    if (!key(reader, 3) || !reader.unsignedValue(&value) ||
        value > std::numeric_limits<std::uint32_t>::max()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    manifest.catalogCrc32c = static_cast<std::uint32_t>(value);
    if (!reader.complete()) return TargetCodecStatus::TrailingData;
    *output = manifest;
    return TargetCodecStatus::Valid;
}

TargetCodecStatus reopenTargetCatalog(
    const std::uint8_t* manifestBytes, std::size_t manifestSize,
    const std::uint8_t* catalogBytes, std::size_t catalogSize,
    domain::targets::TargetCatalog* output) {
    if (output == nullptr) return TargetCodecStatus::InvalidArgument;
    output->clear();
    TargetManifest manifest{};
    const TargetCodecStatus manifestStatus = decodeTargetManifest(
        manifestBytes, manifestSize, &manifest);
    if (manifestStatus != TargetCodecStatus::Valid) return manifestStatus;
    if (manifest.catalogLength != catalogSize || catalogBytes == nullptr ||
        manifest.catalogCrc32c != crc32c(catalogBytes, catalogSize)) {
        return TargetCodecStatus::ChecksumMismatch;
    }
    const TargetCodecStatus catalogStatus =
        decodeTargetCatalog(catalogBytes, catalogSize, output);
    if (catalogStatus != TargetCodecStatus::Valid) return catalogStatus;
    if (output->size() != manifest.targetCount) {
        output->clear();
        return TargetCodecStatus::Malformed;
    }
    return TargetCodecStatus::Valid;
}

TargetCodecStatus encodeTargetState(
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (output == nullptr || outputSize == nullptr || catalog.size() == 0 ||
        catalog.size() > domain::targets::TargetCatalog::kCapacity ||
        decisions.size() > domain::targets::CorrelationDecisionLog::kCapacity) {
        return TargetCodecStatus::InvalidArgument;
    }
    CborWriter writer(output, capacity);
    writer.map(3);
    writer.unsignedValue(0);
    writer.unsignedValue(kTargetStateSchemaVersion);
    writer.unsignedValue(1);
    writer.array(catalog.size());
    for (std::size_t index = 0; index < catalog.size(); ++index) {
        const domain::targets::TargetRecord* record = catalog.get(index);
        if (record == nullptr || !encodeRecord(writer, *record)) {
            return writer.ok() ? TargetCodecStatus::InvalidArgument
                               : TargetCodecStatus::BufferTooSmall;
        }
    }
    writer.unsignedValue(2);
    writer.array(decisions.size());
    for (std::size_t index = 0; index < decisions.size(); ++index) {
        const domain::targets::CorrelationDecisionRecord* record =
            decisions.get(index);
        if (record == nullptr ||
            !domain::targets::correlationProposalValid(record->proposal) ||
            !encodeCorrelationDecision(writer, *record)) {
            return writer.ok() ? TargetCodecStatus::InvalidArgument
                               : TargetCodecStatus::BufferTooSmall;
        }
    }
    if (!writer.ok()) return TargetCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return TargetCodecStatus::Valid;
}

TargetCodecStatus decodeTargetState(
    const std::uint8_t* input, std::size_t size,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions) {
    if (input == nullptr || catalog == nullptr || decisions == nullptr ||
        size == 0 || size > kTargetStateMaxBytes) {
        return TargetCodecStatus::InvalidArgument;
    }
    catalog->clear();
    decisions->clear();
    CborReader reader(input, size);
    std::uint64_t count = 0;
    std::uint64_t version = 0;
    if (!reader.map(&count) || count != 3 || !key(reader, 0) ||
        !reader.unsignedValue(&version)) {
        return TargetCodecStatus::Malformed;
    }
    if (version != kTargetStateSchemaVersion) {
        return TargetCodecStatus::UnsupportedSchema;
    }
    if (!key(reader, 1) || !reader.array(&count) || count == 0 ||
        count > domain::targets::TargetCatalog::kCapacity) {
        return TargetCodecStatus::BoundsExceeded;
    }
    for (std::size_t index = 0; index < count; ++index) {
        domain::targets::TargetRecord record{};
        const TargetCodecStatus status = decodeRecord(reader, &record);
        if (status != TargetCodecStatus::Valid ||
            catalog->restore(record) !=
                domain::targets::TargetMutationStatus::Created) {
            catalog->clear();
            decisions->clear();
            return status == TargetCodecStatus::Valid
                ? TargetCodecStatus::Conflict : status;
        }
    }
    if (!key(reader, 2) || !reader.array(&count) ||
        count > domain::targets::CorrelationDecisionLog::kCapacity) {
        catalog->clear();
        return TargetCodecStatus::BoundsExceeded;
    }
    for (std::size_t index = 0; index < count; ++index) {
        domain::targets::CorrelationDecisionRecord record{};
        const TargetCodecStatus status =
            decodeCorrelationDecision(reader, &record);
        if (status != TargetCodecStatus::Valid ||
            (decisions->record(
                 record.proposal, record.decision,
                 record.targetRevisionBefore, record.targetRevisionAfter) !=
             (record.decision == domain::targets::CorrelationDecision::Accept
                  ? domain::targets::CorrelationDecisionStatus::Accepted
                  : domain::targets::CorrelationDecisionStatus::Rejected))) {
            catalog->clear();
            decisions->clear();
            return status == TargetCodecStatus::Valid
                ? TargetCodecStatus::Conflict : status;
        }
    }
    if (!reader.complete()) {
        catalog->clear();
        decisions->clear();
        return TargetCodecStatus::TrailingData;
    }
    return TargetCodecStatus::Valid;
}

TargetCodecStatus encodeTargetStateManifest(
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    const std::uint8_t* stateBytes, std::size_t stateSize,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (catalog.size() == 0 ||
        catalog.size() > domain::targets::TargetCatalog::kCapacity ||
        decisions.size() > domain::targets::CorrelationDecisionLog::kCapacity ||
        stateBytes == nullptr || stateSize == 0 ||
        stateSize > kTargetStateMaxBytes || output == nullptr ||
        outputSize == nullptr) {
        return TargetCodecStatus::InvalidArgument;
    }
    CborWriter writer(output, capacity);
    writer.map(5);
    writer.unsignedValue(0);
    writer.unsignedValue(kTargetStateSchemaVersion);
    writer.unsignedValue(1);
    writer.unsignedValue(catalog.size());
    writer.unsignedValue(2);
    writer.unsignedValue(decisions.size());
    writer.unsignedValue(3);
    writer.unsignedValue(stateSize);
    writer.unsignedValue(4);
    writer.unsignedValue(crc32c(stateBytes, stateSize));
    if (!writer.ok()) return TargetCodecStatus::BufferTooSmall;
    *outputSize = writer.size();
    return TargetCodecStatus::Valid;
}

TargetCodecStatus decodeTargetStateManifest(
    const std::uint8_t* input, std::size_t size,
    TargetStateManifest* output) {
    if (input == nullptr || output == nullptr || size == 0 ||
        size > kTargetStateManifestMaxBytes) {
        return TargetCodecStatus::InvalidArgument;
    }
    CborReader reader(input, size);
    std::uint64_t count = 0;
    std::uint64_t value = 0;
    if (!reader.map(&count) || count != 5 || !key(reader, 0) ||
        !reader.unsignedValue(&value)) {
        return TargetCodecStatus::Malformed;
    }
    if (value != kTargetStateSchemaVersion) {
        return TargetCodecStatus::UnsupportedSchema;
    }
    TargetStateManifest manifest{};
    manifest.schemaVersion = static_cast<std::uint16_t>(value);
    if (!key(reader, 1) || !reader.unsignedValue(&value) || value == 0 ||
        value > domain::targets::TargetCatalog::kCapacity) {
        return TargetCodecStatus::BoundsExceeded;
    }
    manifest.targetCount = static_cast<std::uint16_t>(value);
    if (!key(reader, 2) || !reader.unsignedValue(&value) ||
        value > domain::targets::CorrelationDecisionLog::kCapacity) {
        return TargetCodecStatus::BoundsExceeded;
    }
    manifest.decisionCount = static_cast<std::uint16_t>(value);
    if (!key(reader, 3) || !reader.unsignedValue(&value) || value == 0 ||
        value > kTargetStateMaxBytes) {
        return TargetCodecStatus::BoundsExceeded;
    }
    manifest.stateLength = static_cast<std::uint32_t>(value);
    if (!key(reader, 4) || !reader.unsignedValue(&value) ||
        value > std::numeric_limits<std::uint32_t>::max()) {
        return TargetCodecStatus::BoundsExceeded;
    }
    manifest.stateCrc32c = static_cast<std::uint32_t>(value);
    if (!reader.complete()) return TargetCodecStatus::TrailingData;
    *output = manifest;
    return TargetCodecStatus::Valid;
}

TargetCodecStatus reopenTargetState(
    const std::uint8_t* manifestBytes, std::size_t manifestSize,
    const std::uint8_t* stateBytes, std::size_t stateSize,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions) {
    if (catalog == nullptr || decisions == nullptr) {
        return TargetCodecStatus::InvalidArgument;
    }
    catalog->clear();
    decisions->clear();
    TargetStateManifest manifest{};
    const TargetCodecStatus manifestStatus = decodeTargetStateManifest(
        manifestBytes, manifestSize, &manifest);
    if (manifestStatus != TargetCodecStatus::Valid) return manifestStatus;
    if (manifest.stateLength != stateSize || stateBytes == nullptr ||
        manifest.stateCrc32c != crc32c(stateBytes, stateSize)) {
        return TargetCodecStatus::ChecksumMismatch;
    }
    const TargetCodecStatus stateStatus =
        decodeTargetState(stateBytes, stateSize, catalog, decisions);
    if (stateStatus != TargetCodecStatus::Valid) return stateStatus;
    if (catalog->size() != manifest.targetCount ||
        decisions->size() != manifest.decisionCount) {
        catalog->clear();
        decisions->clear();
        return TargetCodecStatus::Malformed;
    }
    return TargetCodecStatus::Valid;
}

}  // namespace leshy1::storage
