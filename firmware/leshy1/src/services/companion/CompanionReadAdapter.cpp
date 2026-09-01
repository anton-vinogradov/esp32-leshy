#include "CompanionReadAdapter.h"

#include <array>
#include <cstdio>
#include <cstring>

#include "apps/capture/RadiotapPcap.h"

namespace leshy1::services::companion {
namespace {

struct StringToken final {
    const char* data = nullptr;
    std::size_t size = 0;
};

bool tokenEquals(const StringToken& token, const char* expected) {
    const std::size_t size = std::strlen(expected);
    return token.size == size &&
        std::memcmp(token.data, expected, size) == 0;
}

class JsonCursor final {
public:
    JsonCursor(const char* data, std::size_t size)
        : data_(data), size_(size) {}

    void skipWhitespace() {
        while (offset_ < size_) {
            const char value = data_[offset_];
            if (value != ' ' && value != '\t' && value != '\r' &&
                value != '\n') {
                break;
            }
            ++offset_;
        }
    }

    bool consume(char expected) {
        skipWhitespace();
        if (offset_ >= size_ || data_[offset_] != expected) return false;
        ++offset_;
        return true;
    }

    bool parseString(StringToken* output) {
        if (output == nullptr || !consume('"')) return false;
        const std::size_t start = offset_;
        while (offset_ < size_) {
            const unsigned char value =
                static_cast<unsigned char>(data_[offset_]);
            if (value == '"') {
                output->data = data_ + start;
                output->size = offset_ - start;
                ++offset_;
                return true;
            }
            if (value == '\\' || value < 0x20U || value > 0x7eU) {
                return false;
            }
            ++offset_;
        }
        return false;
    }

    bool parseUnsigned(std::uint32_t* output) {
        if (output == nullptr) return false;
        skipWhitespace();
        if (offset_ >= size_ || data_[offset_] < '0' ||
            data_[offset_] > '9') {
            return false;
        }
        if (data_[offset_] == '0' && offset_ + 1U < size_ &&
            data_[offset_ + 1U] >= '0' && data_[offset_ + 1U] <= '9') {
            return false;
        }
        std::uint32_t value = 0;
        while (offset_ < size_ && data_[offset_] >= '0' &&
               data_[offset_] <= '9') {
            const std::uint32_t digit =
                static_cast<std::uint32_t>(data_[offset_] - '0');
            if (value > UINT32_MAX / 10U ||
                (value == UINT32_MAX / 10U &&
                 digit > UINT32_MAX % 10U)) {
                return false;
            }
            value = value * 10U + digit;
            ++offset_;
        }
        *output = value;
        return true;
    }

    bool finished() {
        skipWhitespace();
        return offset_ == size_;
    }

private:
    const char* data_ = nullptr;
    std::size_t size_ = 0;
    std::size_t offset_ = 0;
};

enum Field : std::uint16_t {
    SchemaField = 1U << 0U,
    KindField = 1U << 1U,
    RequestIdField = 1U << 2U,
    OffsetField = 1U << 3U,
    TargetIdField = 1U << 4U,
    SourceIdField = 1U << 5U,
    GenerationField = 1U << 6U,
    BaselineIdField = 1U << 7U,
    BaselineGenerationField = 1U << 8U,
    CurrentIdField = 1U << 9U,
    CurrentGenerationField = 1U << 10U,
    SectionField = 1U << 11U,
};

constexpr std::uint16_t kCommonFields =
    SchemaField | KindField | RequestIdField;

bool validRequestId(const StringToken& token) {
    if (token.size == 0 || token.size > kCompanionRequestIdCapacity) {
        return false;
    }
    for (std::size_t index = 0; index < token.size; ++index) {
        const char value = token.data[index];
        const bool valid = (value >= 'a' && value <= 'z') ||
            (value >= 'A' && value <= 'Z') ||
            (value >= '0' && value <= '9') || value == '.' || value == '_' ||
            value == '-';
        if (!valid) return false;
    }
    return true;
}

std::uint8_t hexNibble(char value) {
    if (value >= '0' && value <= '9') {
        return static_cast<std::uint8_t>(value - '0');
    }
    if (value >= 'a' && value <= 'f') {
        return static_cast<std::uint8_t>(value - 'a' + 10);
    }
    if (value >= 'A' && value <= 'F') {
        return static_cast<std::uint8_t>(value - 'A' + 10);
    }
    return 0xffU;
}

template <typename Id>
bool parseId(const StringToken& token, Id* output) {
    if (output == nullptr || token.size != Id::kSize * 2U) return false;
    Id candidate{};
    bool nonzero = false;
    for (std::size_t index = 0; index < Id::kSize; ++index) {
        const std::uint8_t high = hexNibble(token.data[index * 2U]);
        const std::uint8_t low = hexNibble(token.data[index * 2U + 1U]);
        if (high > 0x0fU || low > 0x0fU) return false;
        candidate.bytes[index] = static_cast<std::uint8_t>((high << 4U) | low);
        nonzero = nonzero || candidate.bytes[index] != 0;
    }
    if (!nonzero) return false;
    *output = candidate;
    return true;
}

bool parseKind(const StringToken& token, CompanionReadKind* output) {
    if (output == nullptr) return false;
    if (tokenEquals(token, "session.list")) {
        *output = CompanionReadKind::SessionList;
    } else if (tokenEquals(token, "session.detail")) {
        *output = CompanionReadKind::SessionDetail;
    } else if (tokenEquals(token, "target.list")) {
        *output = CompanionReadKind::TargetList;
    } else if (tokenEquals(token, "target.detail")) {
        *output = CompanionReadKind::TargetDetail;
    } else if (tokenEquals(token, "target.compare")) {
        *output = CompanionReadKind::TargetCompare;
    } else if (tokenEquals(token, "capture.live.read")) {
        *output = CompanionReadKind::CaptureLiveRead;
    } else {
        return false;
    }
    return true;
}

const char* kindName(CompanionReadKind kind) {
    switch (kind) {
        case CompanionReadKind::SessionList: return "session.list";
        case CompanionReadKind::SessionDetail: return "session.detail";
        case CompanionReadKind::TargetList: return "target.list";
        case CompanionReadKind::TargetDetail: return "target.detail";
        case CompanionReadKind::TargetCompare: return "target.compare";
        case CompanionReadKind::CaptureLiveRead: return "capture.live.read";
    }
    return "error";
}

bool parseSection(const StringToken& token,
                  CompanionTargetDetailSection* output) {
    if (output == nullptr) return false;
    if (tokenEquals(token, "summary")) {
        *output = CompanionTargetDetailSection::Summary;
    } else if (tokenEquals(token, "notes")) {
        *output = CompanionTargetDetailSection::Notes;
    } else if (tokenEquals(token, "tags")) {
        *output = CompanionTargetDetailSection::Tags;
    } else if (tokenEquals(token, "identities")) {
        *output = CompanionTargetDetailSection::Identities;
    } else if (tokenEquals(token, "evidence")) {
        *output = CompanionTargetDetailSection::Evidence;
    } else {
        return false;
    }
    return true;
}

const char* sectionName(CompanionTargetDetailSection section) {
    switch (section) {
        case CompanionTargetDetailSection::Summary: return "summary";
        case CompanionTargetDetailSection::Notes: return "notes";
        case CompanionTargetDetailSection::Tags: return "tags";
        case CompanionTargetDetailSection::Identities: return "identities";
        case CompanionTargetDetailSection::Evidence: return "evidence";
    }
    return "summary";
}

std::uint16_t requiredFields(CompanionReadKind kind) {
    switch (kind) {
        case CompanionReadKind::SessionList:
        case CompanionReadKind::TargetList:
        case CompanionReadKind::CaptureLiveRead:
            return kCommonFields | OffsetField;
        case CompanionReadKind::SessionDetail:
            return kCommonFields | SourceIdField | GenerationField;
        case CompanionReadKind::TargetDetail:
            return kCommonFields | TargetIdField | SectionField | OffsetField;
        case CompanionReadKind::TargetCompare:
            return kCommonFields | BaselineIdField |
                BaselineGenerationField | CurrentIdField |
                CurrentGenerationField | OffsetField;
    }
    return kCommonFields;
}

class BufferWriter final {
public:
    BufferWriter(char* output, std::size_t capacity)
        : output_(output), capacity_(capacity) {}

    bool append(const char* value) {
        return value != nullptr && append(value, std::strlen(value));
    }

    bool append(const char* value, std::size_t length) {
        if (failed_ || value == nullptr || length > capacity_ - size_) {
            failed_ = true;
            return false;
        }
        if (length != 0) std::memcpy(output_ + size_, value, length);
        size_ += length;
        return true;
    }

    bool appendUnsigned(std::uint64_t value) {
        char text[24] = {};
        const int written = std::snprintf(
            text, sizeof(text), "%llu",
            static_cast<unsigned long long>(value));
        return written > 0 && static_cast<std::size_t>(written) < sizeof(text) &&
            append(text, static_cast<std::size_t>(written));
    }

    bool appendSigned(std::int64_t value) {
        char text[24] = {};
        const int written = std::snprintf(
            text, sizeof(text), "%lld",
            static_cast<long long>(value));
        return written > 0 && static_cast<std::size_t>(written) < sizeof(text) &&
            append(text, static_cast<std::size_t>(written));
    }

    bool appendHex(const std::uint8_t* value, std::size_t length) {
        static constexpr char kHex[] = "0123456789ABCDEF";
        if (value == nullptr) return false;
        for (std::size_t index = 0; index < length; ++index) {
            const char bytes[2] = {
                kHex[(value[index] >> 4U) & 0x0fU],
                kHex[value[index] & 0x0fU],
            };
            if (!append(bytes, sizeof(bytes))) return false;
        }
        return true;
    }

    bool finish(std::size_t* size) {
        if (size == nullptr || failed_ || size_ >= capacity_) return false;
        output_[size_] = '\0';
        *size = size_;
        return true;
    }

private:
    char* output_ = nullptr;
    std::size_t capacity_ = 0;
    std::size_t size_ = 0;
    bool failed_ = false;
};

template <typename Id>
bool appendId(BufferWriter* writer, const Id& id) {
    return writer != nullptr && writer->appendHex(id.bytes.data(), id.bytes.size());
}

bool sameSource(const domain::targets::TargetComparisonSource& left,
                const domain::targets::TargetComparisonSource& right) {
    return left.generation == right.generation &&
        left.id.bytes == right.id.bytes;
}

const CompanionReadSessionBinding* findSession(
    const CompanionReadContext& context,
    const domain::targets::TargetComparisonSource& source) {
    for (std::size_t index = 0; index < context.sessionCount; ++index) {
        const auto& binding = context.sessions[index];
        if (binding.session != nullptr && sameSource(binding.source, source)) {
            return &binding;
        }
    }
    return nullptr;
}

CompanionCapability capabilityForKind(CompanionReadKind kind) {
    switch (kind) {
        case CompanionReadKind::SessionList:
            return CompanionCapability::SessionList;
        case CompanionReadKind::SessionDetail:
            return CompanionCapability::SessionDetail;
        case CompanionReadKind::TargetList:
            return CompanionCapability::TargetList;
        case CompanionReadKind::TargetDetail:
            return CompanionCapability::TargetDetail;
        case CompanionReadKind::TargetCompare:
            return CompanionCapability::TargetCompare;
        case CompanionReadKind::CaptureLiveRead:
            return CompanionCapability::CaptureLiveWifi;
    }
    return CompanionCapability::SessionList;
}

bool appendResponseStart(BufferWriter* writer, CompanionReadKind kind,
                         const CompanionReadRequest& request,
                         CompanionReadStatus status) {
    return writer->append("{\"schema\":\"") &&
        writer->append(kCompanionResponseSchema) &&
        writer->append("\",\"kind\":\"") && writer->append(kindName(kind)) &&
        writer->append("\",\"request_id\":\"") &&
        writer->append(request.requestId.data(), request.requestIdLength) &&
        writer->append("\",\"status\":\"") &&
        writer->append(status == CompanionReadStatus::Ok ? "ok" : "error") &&
        writer->append("\",\"reason\":\"") &&
        writer->append(companionReadReason(status)) && writer->append("\"");
}

bool appendNextOffset(BufferWriter* writer, std::size_t next,
                      std::size_t total) {
    if (!writer->append(",\"next_offset\":")) return false;
    return next < total ? writer->appendUnsigned(next)
                        : writer->append("null");
}

bool encodeError(BufferWriter* writer, const CompanionReadRequest& request,
                 CompanionReadStatus status) {
    return appendResponseStart(writer, request.kind, request, status) &&
        writer->append("}\n");
}

bool encodeSessionList(BufferWriter* writer, const CompanionReadContext& context,
                       const CompanionReadRequest& request) {
    const std::size_t offset = request.offset;
    if (offset > context.sessionCount) {
        return encodeError(writer, request,
                           CompanionReadStatus::OffsetOutOfRange);
    }
    if (!appendResponseStart(writer, request.kind, request,
                             CompanionReadStatus::Ok) ||
        !writer->append(",\"offset\":") || !writer->appendUnsigned(offset) ||
        !appendNextOffset(writer, context.sessionCount, context.sessionCount) ||
        !writer->append(",\"items\":[")) {
        return false;
    }
    bool first = true;
    for (std::size_t index = offset; index < context.sessionCount; ++index) {
        const auto& binding = context.sessions[index];
        if (binding.session == nullptr) continue;
        if (!first && !writer->append(",")) return false;
        first = false;
        if (!writer->append("{\"source_id\":\"") ||
            !appendId(writer, binding.source.id) ||
            !writer->append("\",\"generation\":") ||
            !writer->appendUnsigned(binding.source.generation) ||
            !writer->append(",\"session_id\":\"") ||
            !writer->append(binding.session->id()) ||
            !writer->append("\",\"observations\":") ||
            !writer->appendUnsigned(binding.session->size()) ||
            !writer->append("}")) {
            return false;
        }
    }
    return writer->append("]}\n");
}

bool encodeSessionDetail(BufferWriter* writer,
                         const CompanionReadContext& context,
                         const CompanionReadRequest& request) {
    const auto* binding = findSession(context, request.source);
    if (binding == nullptr) {
        return encodeError(writer, request, CompanionReadStatus::NotFound);
    }
    const auto& session = *binding->session;
    return appendResponseStart(writer, request.kind, request,
                               CompanionReadStatus::Ok) &&
        writer->append(",\"source_id\":\"") &&
        appendId(writer, binding->source.id) &&
        writer->append("\",\"generation\":") &&
        writer->appendUnsigned(binding->source.generation) &&
        writer->append(",\"session_id\":\"") && writer->append(session.id()) &&
        writer->append("\",\"state\":\"stopped\",\"started_us\":") &&
        writer->appendUnsigned(session.startedUs()) &&
        writer->append(",\"stopped_us\":") &&
        writer->appendUnsigned(session.stoppedUs()) &&
        writer->append(",\"observations\":") &&
        writer->appendUnsigned(session.size()) &&
        writer->append(",\"dropped\":") &&
        writer->appendUnsigned(session.dropped()) && writer->append("}\n");
}

bool appendTargetSummary(BufferWriter* writer,
                         const domain::targets::TargetRecord& target) {
    return writer->append("{\"target_id\":\"") && appendId(writer, target.id) &&
        writer->append("\",\"revision\":") &&
        writer->appendUnsigned(target.revision) &&
        writer->append(",\"favorite\":") &&
        writer->append(target.favorite ? "true" : "false") &&
        writer->append(",\"name_hex\":\"") &&
        writer->appendHex(reinterpret_cast<const std::uint8_t*>(
                              target.name.data()),
                          target.nameLength) &&
        writer->append("\",\"identity_count\":") &&
        writer->appendUnsigned(target.identityCount) &&
        writer->append(",\"evidence_count\":") &&
        writer->appendUnsigned(target.evidenceCount) &&
        writer->append(",\"tag_count\":") &&
        writer->appendUnsigned(target.tagCount) && writer->append("}");
}

bool encodeTargetList(BufferWriter* writer, const CompanionReadContext& context,
                      const CompanionReadRequest& request) {
    const std::size_t total = context.targets == nullptr
        ? 0 : context.targets->size();
    const std::size_t offset = request.offset;
    if (offset > total) {
        return encodeError(writer, request,
                           CompanionReadStatus::OffsetOutOfRange);
    }
    if (!appendResponseStart(writer, request.kind, request,
                             CompanionReadStatus::Ok) ||
        !writer->append(",\"offset\":") || !writer->appendUnsigned(offset) ||
        !appendNextOffset(writer, offset + 1U, total) ||
        !writer->append(",\"items\":[")) {
        return false;
    }
    if (offset < total) {
        const auto* target = context.targets->get(offset);
        if (target == nullptr || !appendTargetSummary(writer, *target)) {
            return false;
        }
    }
    return writer->append("]}\n");
}

const char* identityKindName(domain::targets::TargetIdentityKind kind) {
    switch (kind) {
        case domain::targets::TargetIdentityKind::WifiBssid:
            return "wifi_bssid";
        case domain::targets::TargetIdentityKind::WifiStation:
            return "wifi_station";
        case domain::targets::TargetIdentityKind::BleAddress:
            return "ble_address";
    }
    return "unknown";
}

bool encodeTargetDetail(BufferWriter* writer,
                        const CompanionReadContext& context,
                        const CompanionReadRequest& request) {
    const auto* target = context.targets == nullptr
        ? nullptr : context.targets->find(request.targetId);
    if (target == nullptr) {
        return encodeError(writer, request, CompanionReadStatus::NotFound);
    }
    const std::size_t offset = request.offset;
    std::size_t sectionSize = 0;
    switch (request.section) {
        case CompanionTargetDetailSection::Summary:
            sectionSize = 0;
            break;
        case CompanionTargetDetailSection::Notes:
            sectionSize = target->notesLength;
            break;
        case CompanionTargetDetailSection::Tags:
            sectionSize = target->tagCount;
            break;
        case CompanionTargetDetailSection::Identities:
            sectionSize = target->identityCount;
            break;
        case CompanionTargetDetailSection::Evidence:
            sectionSize = target->evidenceCount;
            break;
    }
    if ((request.section == CompanionTargetDetailSection::Summary &&
         offset != 0) ||
        (request.section != CompanionTargetDetailSection::Summary &&
         offset > sectionSize)) {
        return encodeError(writer, request,
                           CompanionReadStatus::OffsetOutOfRange);
    }
    if (!appendResponseStart(writer, request.kind, request,
                             CompanionReadStatus::Ok) ||
        !writer->append(",\"target_id\":\"") ||
        !appendId(writer, target->id) ||
        !writer->append("\",\"section\":\"") ||
        !writer->append(sectionName(request.section)) ||
        !writer->append("\"")) {
        return false;
    }
    switch (request.section) {
        case CompanionTargetDetailSection::Summary:
            return writer->append(",\"revision\":") &&
                writer->appendUnsigned(target->revision) &&
                writer->append(",\"favorite\":") &&
                writer->append(target->favorite ? "true" : "false") &&
                writer->append(",\"name_hex\":\"") &&
                writer->appendHex(reinterpret_cast<const std::uint8_t*>(
                                      target->name.data()),
                                  target->nameLength) &&
                writer->append("\",\"identity_count\":") &&
                writer->appendUnsigned(target->identityCount) &&
                writer->append(",\"evidence_count\":") &&
                writer->appendUnsigned(target->evidenceCount) &&
                writer->append(",\"tag_count\":") &&
                writer->appendUnsigned(target->tagCount) &&
                writer->append("}\n");
        case CompanionTargetDetailSection::Notes: {
            constexpr std::size_t kNotesPerFrame = 80;
            const std::size_t end = offset + kNotesPerFrame < sectionSize
                ? offset + kNotesPerFrame : sectionSize;
            return writer->append(",\"encoding\":\"hex\",\"offset\":") &&
                writer->appendUnsigned(offset) &&
                appendNextOffset(writer, end, sectionSize) &&
                writer->append(",\"value\":\"") &&
                writer->appendHex(reinterpret_cast<const std::uint8_t*>(
                                      target->notes.data() + offset),
                                  end - offset) &&
                writer->append("\"}\n");
        }
        case CompanionTargetDetailSection::Tags: {
            constexpr std::size_t kTagsPerFrame = 2;
            const std::size_t end = offset + kTagsPerFrame < sectionSize
                ? offset + kTagsPerFrame : sectionSize;
            if (!writer->append(",\"encoding\":\"hex\",\"offset\":") ||
                !writer->appendUnsigned(offset) ||
                !appendNextOffset(writer, end, sectionSize) ||
                !writer->append(",\"items\":[")) {
                return false;
            }
            for (std::size_t index = offset; index < end; ++index) {
                if (index != offset && !writer->append(",")) return false;
                if (!writer->append("\"") ||
                    !writer->appendHex(reinterpret_cast<const std::uint8_t*>(
                                          target->tags[index].data()),
                                      target->tagLengths[index]) ||
                    !writer->append("\"")) {
                    return false;
                }
            }
            return writer->append("]}\n");
        }
        case CompanionTargetDetailSection::Identities: {
            if (!writer->append(",\"offset\":") ||
                !writer->appendUnsigned(offset) ||
                !appendNextOffset(writer, offset + 2U,
                                  target->identityCount) ||
                !writer->append(",\"items\":[")) {
                return false;
            }
            const std::size_t end = offset + 2U < target->identityCount
                ? offset + 2U : target->identityCount;
            for (std::size_t index = offset; index < end; ++index) {
                const auto& identity = target->identities[index];
                if (index != offset && !writer->append(",")) return false;
                if (!writer->append("{\"kind\":\"") ||
                    !writer->append(identityKindName(identity.kind)) ||
                    !writer->append("\",\"value\":\"") ||
                    !writer->appendHex(identity.value.data(), identity.length) ||
                    !writer->append("\",\"discriminator\":") ||
                    !writer->appendUnsigned(identity.discriminator) ||
                    !writer->append("}")) {
                    return false;
                }
            }
            return writer->append("]}\n");
        }
        case CompanionTargetDetailSection::Evidence: {
            if (!writer->append(",\"offset\":") ||
                !writer->appendUnsigned(offset) ||
                !appendNextOffset(writer, offset + 2U,
                                  target->evidenceCount) ||
                !writer->append(",\"items\":[")) {
                return false;
            }
            const std::size_t end = offset + 2U < target->evidenceCount
                ? offset + 2U : target->evidenceCount;
            for (std::size_t index = offset; index < end; ++index) {
                const auto& evidence = target->evidence[index];
                if (index != offset && !writer->append(",")) return false;
                if (!writer->append("{\"source_id\":\"") ||
                    !appendId(writer, evidence.sourceId) ||
                    !writer->append("\",\"generation\":") ||
                    !writer->appendUnsigned(evidence.sourceGeneration) ||
                    !writer->append(",\"sequence\":") ||
                    !writer->appendUnsigned(evidence.observationSequence) ||
                    !writer->append(",\"observed_us\":") ||
                    !writer->appendUnsigned(evidence.observedMonotonicUs) ||
                    !writer->append("}")) {
                    return false;
                }
            }
            return writer->append("]}\n");
        }
    }
    return false;
}

bool encodeTargetCompare(BufferWriter* writer,
                         const CompanionReadContext& context,
                         const CompanionReadRequest& request) {
    const auto* comparison = context.comparison;
    if (findSession(context, request.baseline) == nullptr ||
        findSession(context, request.current) == nullptr) {
        return encodeError(writer, request,
                           CompanionReadStatus::SourceUnavailable);
    }
    if (comparison == nullptr || !comparison->compared() ||
        !sameSource(comparison->baseline, request.baseline) ||
        !sameSource(comparison->current, request.current)) {
        return encodeError(writer, request,
                           CompanionReadStatus::ResultUnavailable);
    }
    const std::size_t offset = request.offset;
    if (offset > comparison->size) {
        return encodeError(writer, request,
                           CompanionReadStatus::OffsetOutOfRange);
    }
    if (!appendResponseStart(writer, request.kind, request,
                             CompanionReadStatus::Ok) ||
        !writer->append(",\"offset\":") || !writer->appendUnsigned(offset) ||
        !appendNextOffset(writer, offset + 1U, comparison->size) ||
        !writer->append(",\"counts\":{\"added\":") ||
        !writer->appendUnsigned(comparison->added) ||
        !writer->append(",\"removed\":") ||
        !writer->appendUnsigned(comparison->removed) ||
        !writer->append(",\"changed\":") ||
        !writer->appendUnsigned(comparison->changed) ||
        !writer->append(",\"unchanged\":") ||
        !writer->appendUnsigned(comparison->unchanged) ||
        !writer->append("},\"items\":[")) {
        return false;
    }
    if (offset < comparison->size) {
        const auto* item = comparison->get(offset);
        if (item == nullptr || !writer->append("{\"target_id\":\"") ||
            !appendId(writer, item->targetId) ||
            !writer->append("\",\"class\":\"") ||
            !writer->append(domain::targets::targetComparisonClassName(
                item->classification)) ||
            !writer->append("\",\"changes\":") ||
            !writer->appendUnsigned(item->changes) ||
            !writer->append(",\"baseline_evidence\":") ||
            !writer->appendUnsigned(item->baselineEvidenceCount) ||
            !writer->append(",\"current_evidence\":") ||
            !writer->appendUnsigned(item->currentEvidenceCount) ||
            !writer->append("}")) {
            return false;
        }
    }
    return writer->append("]}\n");
}

bool encodeCaptureLiveRead(BufferWriter* writer,
                           const CompanionReadContext& context,
                           const CompanionReadRequest& request) {
    if (context.liveWifiCapture == nullptr) {
        return encodeError(writer, request,
                           CompanionReadStatus::SourceUnavailable);
    }
    std::array<std::uint8_t,
               apps::capture::kRadiotapPcapChunkCapacity> bytes{};
    const apps::capture::PcapStreamChunk chunk =
        apps::capture::readRadiotapPcapChunk(
            *context.liveWifiCapture, request.offset, bytes.data(),
            bytes.size());
    if (!chunk.valid) {
        return encodeError(writer, request,
                           CompanionReadStatus::OffsetOutOfRange);
    }
    const std::size_t next = chunk.offset + chunk.bytesRead;
    if (!appendResponseStart(writer, request.kind, request,
                             CompanionReadStatus::Ok) ||
        !writer->append(",\"source\":\"wifi\",\"link_type\":127,") ||
        !writer->append("\"offset\":") ||
        !writer->appendUnsigned(chunk.offset) ||
        !writer->append(",\"next_offset\":") ||
        !(context.liveWifiTerminal && next >= chunk.availableBytes
              ? writer->append("null")
              : writer->appendUnsigned(next)) ||
        !writer->append(",\"available_bytes\":") ||
        !writer->appendUnsigned(chunk.availableBytes) ||
        !writer->append(",\"frames\":") ||
        !writer->appendUnsigned(chunk.frameCount) ||
        !writer->append(",\"dropped\":") ||
        !writer->appendUnsigned(context.liveWifiDropped) ||
        !writer->append(",\"terminal\":") ||
        !writer->append(context.liveWifiTerminal ? "true" : "false") ||
        !writer->append(",\"cleanup_complete\":") ||
        !writer->append(context.liveWifiCleanupComplete ? "true" : "false") ||
        !writer->append(",\"encoding\":\"hex\",\"data_hex\":\"") ||
        !writer->appendHex(bytes.data(), chunk.bytesRead) ||
        !writer->append("\"}\n")) {
        return false;
    }
    return true;
}

bool publishScratch(const std::array<char, kCompanionMaxFrameBytes + 1U>& scratch,
                    std::size_t size, char* output, std::size_t capacity,
                    std::size_t* outputLength) {
    if (outputLength != nullptr) *outputLength = 0;
    if (output == nullptr || outputLength == nullptr || size >= capacity) {
        return false;
    }
    std::memcpy(output, scratch.data(), size + 1U);
    *outputLength = size;
    return true;
}

}  // namespace

const char* companionReadParseReason(CompanionReadParseStatus status) {
    switch (status) {
        case CompanionReadParseStatus::Parsed: return "none";
        case CompanionReadParseStatus::InvalidArgument: return "invalid_argument";
        case CompanionReadParseStatus::Empty: return "empty";
        case CompanionReadParseStatus::TooLarge: return "frame_too_large";
        case CompanionReadParseStatus::MalformedJson: return "malformed_json";
        case CompanionReadParseStatus::UnknownField: return "unknown_field";
        case CompanionReadParseStatus::DuplicateField: return "duplicate_field";
        case CompanionReadParseStatus::MissingField: return "missing_field";
        case CompanionReadParseStatus::UnsupportedSchema:
            return "unsupported_schema";
        case CompanionReadParseStatus::UnsupportedKind: return "unsupported_kind";
        case CompanionReadParseStatus::InvalidRequestId:
            return "invalid_request_id";
        case CompanionReadParseStatus::InvalidIdentifier:
            return "invalid_identifier";
        case CompanionReadParseStatus::InvalidNumber: return "invalid_number";
        case CompanionReadParseStatus::InvalidSection: return "invalid_section";
        case CompanionReadParseStatus::FieldNotAllowed:
            return "field_not_allowed";
    }
    return "invalid_status";
}

CompanionReadParseStatus parseCompanionReadRequest(
    const char* frame, std::size_t frameLength, CompanionReadRequest* output) {
    if (frame == nullptr || output == nullptr) {
        return CompanionReadParseStatus::InvalidArgument;
    }
    if (frameLength == 0) return CompanionReadParseStatus::Empty;
    if (frameLength > kCompanionMaxFrameBytes) {
        return CompanionReadParseStatus::TooLarge;
    }
    JsonCursor cursor(frame, frameLength);
    if (!cursor.consume('{')) return CompanionReadParseStatus::MalformedJson;

    CompanionReadRequest candidate{};
    StringToken schema{};
    StringToken kind{};
    StringToken requestId{};
    StringToken section{};
    std::uint16_t fields = 0;
    if (cursor.consume('}')) return CompanionReadParseStatus::MissingField;
    while (true) {
        StringToken field{};
        if (!cursor.parseString(&field) || !cursor.consume(':')) {
            return CompanionReadParseStatus::MalformedJson;
        }
        std::uint16_t bit = 0;
        if (tokenEquals(field, "schema")) {
            bit = SchemaField;
            if (!cursor.parseString(&schema)) {
                return CompanionReadParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "kind")) {
            bit = KindField;
            if (!cursor.parseString(&kind)) {
                return CompanionReadParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "request_id")) {
            bit = RequestIdField;
            if (!cursor.parseString(&requestId)) {
                return CompanionReadParseStatus::MalformedJson;
            }
        } else if (tokenEquals(field, "offset")) {
            bit = OffsetField;
            std::uint32_t value = 0;
            if (!cursor.parseUnsigned(&value)) {
                return CompanionReadParseStatus::InvalidNumber;
            }
            candidate.offset = value;
        } else if (tokenEquals(field, "target_id")) {
            bit = TargetIdField;
            StringToken value{};
            if (!cursor.parseString(&value) ||
                !parseId(value, &candidate.targetId)) {
                return CompanionReadParseStatus::InvalidIdentifier;
            }
        } else if (tokenEquals(field, "source_id")) {
            bit = SourceIdField;
            StringToken value{};
            if (!cursor.parseString(&value) ||
                !parseId(value, &candidate.source.id)) {
                return CompanionReadParseStatus::InvalidIdentifier;
            }
        } else if (tokenEquals(field, "generation")) {
            bit = GenerationField;
            if (!cursor.parseUnsigned(&candidate.source.generation) ||
                candidate.source.generation == 0) {
                return CompanionReadParseStatus::InvalidNumber;
            }
        } else if (tokenEquals(field, "baseline_source_id")) {
            bit = BaselineIdField;
            StringToken value{};
            if (!cursor.parseString(&value) ||
                !parseId(value, &candidate.baseline.id)) {
                return CompanionReadParseStatus::InvalidIdentifier;
            }
        } else if (tokenEquals(field, "baseline_generation")) {
            bit = BaselineGenerationField;
            if (!cursor.parseUnsigned(&candidate.baseline.generation) ||
                candidate.baseline.generation == 0) {
                return CompanionReadParseStatus::InvalidNumber;
            }
        } else if (tokenEquals(field, "current_source_id")) {
            bit = CurrentIdField;
            StringToken value{};
            if (!cursor.parseString(&value) ||
                !parseId(value, &candidate.current.id)) {
                return CompanionReadParseStatus::InvalidIdentifier;
            }
        } else if (tokenEquals(field, "current_generation")) {
            bit = CurrentGenerationField;
            if (!cursor.parseUnsigned(&candidate.current.generation) ||
                candidate.current.generation == 0) {
                return CompanionReadParseStatus::InvalidNumber;
            }
        } else if (tokenEquals(field, "section")) {
            bit = SectionField;
            if (!cursor.parseString(&section)) {
                return CompanionReadParseStatus::MalformedJson;
            }
        } else {
            return CompanionReadParseStatus::UnknownField;
        }
        if ((fields & bit) != 0) {
            return CompanionReadParseStatus::DuplicateField;
        }
        fields |= bit;
        if (cursor.consume('}')) break;
        if (!cursor.consume(',')) return CompanionReadParseStatus::MalformedJson;
    }
    if (!cursor.finished()) return CompanionReadParseStatus::MalformedJson;
    if ((fields & kCommonFields) != kCommonFields) {
        return CompanionReadParseStatus::MissingField;
    }
    if (!tokenEquals(schema, kCompanionRequestSchema)) {
        return CompanionReadParseStatus::UnsupportedSchema;
    }
    if (!parseKind(kind, &candidate.kind)) {
        return CompanionReadParseStatus::UnsupportedKind;
    }
    if (!validRequestId(requestId)) {
        return CompanionReadParseStatus::InvalidRequestId;
    }
    const std::uint16_t required = requiredFields(candidate.kind);
    if ((fields & required) != required) {
        return CompanionReadParseStatus::MissingField;
    }
    if ((fields & ~required) != 0) {
        return CompanionReadParseStatus::FieldNotAllowed;
    }
    if (candidate.kind != CompanionReadKind::CaptureLiveRead &&
        candidate.offset > UINT8_MAX) {
        return CompanionReadParseStatus::InvalidNumber;
    }
    if (candidate.kind == CompanionReadKind::TargetDetail &&
        !parseSection(section, &candidate.section)) {
        return CompanionReadParseStatus::InvalidSection;
    }
    candidate.requestIdLength = static_cast<std::uint8_t>(requestId.size);
    std::memcpy(candidate.requestId.data(), requestId.data, requestId.size);
    candidate.requestId[requestId.size] = '\0';
    *output = candidate;
    return CompanionReadParseStatus::Parsed;
}

CompanionCapabilityMask companionReadCapabilities(
    const CompanionReadContext& context) {
    CompanionCapabilityMask result = 0;
    bool sessionsValid = context.sessionCount > 0 &&
        context.sessionCount <= context.sessions.size();
    for (std::size_t index = 0; sessionsValid &&
         index < context.sessionCount; ++index) {
        const auto& binding = context.sessions[index];
        sessionsValid = binding.session != nullptr &&
            binding.session->state() == survey::SessionState::Stopped &&
            domain::targets::sourceIdValid(binding.source.id) &&
            binding.source.generation != 0;
    }
    if (sessionsValid) {
        result |= companionCapabilityMask(CompanionCapability::SessionList) |
            companionCapabilityMask(CompanionCapability::SessionDetail);
    }
    if (context.targets != nullptr) {
        result |= companionCapabilityMask(CompanionCapability::TargetList) |
            companionCapabilityMask(CompanionCapability::TargetDetail);
    }
    if (sessionsValid && context.sessionCount == 2 &&
        context.targets != nullptr && context.comparison != nullptr &&
        context.comparison->compared() &&
        sameSource(context.comparison->baseline, context.sessions[0].source) &&
        sameSource(context.comparison->current, context.sessions[1].source)) {
        result |= companionCapabilityMask(CompanionCapability::TargetCompare);
    }
    if (context.liveWifiCapture != nullptr &&
        context.liveWifiCapture->snapLength() != 0U) {
        result |= companionCapabilityMask(
            CompanionCapability::CaptureLiveWifi);
    }
    return result;
}

const char* companionReadReason(CompanionReadStatus status) {
    switch (status) {
        case CompanionReadStatus::Ok: return "none";
        case CompanionReadStatus::InvalidRequest: return "invalid_request";
        case CompanionReadStatus::NotConnected: return "not_connected";
        case CompanionReadStatus::CapabilityDenied: return "capability_denied";
        case CompanionReadStatus::CapabilityUnavailable:
            return "capability_unavailable";
        case CompanionReadStatus::NotFound: return "not_found";
        case CompanionReadStatus::OffsetOutOfRange:
            return "offset_out_of_range";
        case CompanionReadStatus::SourceUnavailable:
            return "source_unavailable";
        case CompanionReadStatus::ResultUnavailable:
            return "result_unavailable";
    }
    return "invalid_status";
}

bool encodeCompanionReadResponse(
    const CompanionConnection& connection,
    const CompanionReadContext& context,
    const CompanionReadRequest& request,
    char* output, std::size_t capacity, std::size_t* outputLength) {
    if (outputLength != nullptr) *outputLength = 0;
    if (output == nullptr || outputLength == nullptr || capacity == 0) {
        return false;
    }
    std::array<char, kCompanionMaxFrameBytes + 1U> scratch{};
    BufferWriter writer(scratch.data(), scratch.size());
    const CompanionCapability capability = capabilityForKind(request.kind);
    const CompanionCapabilityMask bit = companionCapabilityMask(capability);
    bool encoded = false;
    if (!connection.ready()) {
        encoded = encodeError(&writer, request,
                              CompanionReadStatus::NotConnected);
    } else if ((connection.grantedCapabilities & bit) == 0) {
        encoded = encodeError(&writer, request,
                              CompanionReadStatus::CapabilityDenied);
    } else if ((companionReadCapabilities(context) & bit) == 0) {
        encoded = encodeError(&writer, request,
                              CompanionReadStatus::CapabilityUnavailable);
    } else {
        switch (request.kind) {
            case CompanionReadKind::SessionList:
                encoded = encodeSessionList(&writer, context, request);
                break;
            case CompanionReadKind::SessionDetail:
                encoded = encodeSessionDetail(&writer, context, request);
                break;
            case CompanionReadKind::TargetList:
                encoded = encodeTargetList(&writer, context, request);
                break;
            case CompanionReadKind::TargetDetail:
                encoded = encodeTargetDetail(&writer, context, request);
                break;
            case CompanionReadKind::TargetCompare:
                encoded = encodeTargetCompare(&writer, context, request);
                break;
            case CompanionReadKind::CaptureLiveRead:
                encoded = encodeCaptureLiveRead(&writer, context, request);
                break;
        }
    }
    std::size_t size = 0;
    if (!encoded || !writer.finish(&size) ||
        size > kCompanionMaxFrameBytes) {
        return false;
    }
    return publishScratch(scratch, size, output, capacity, outputLength);
}

bool encodeCompanionReadParseError(
    CompanionReadParseStatus status, char* output, std::size_t capacity,
    std::size_t* outputLength) {
    if (outputLength != nullptr) *outputLength = 0;
    if (output == nullptr || outputLength == nullptr ||
        status == CompanionReadParseStatus::Parsed) {
        return false;
    }
    std::array<char, kCompanionMaxFrameBytes + 1U> scratch{};
    BufferWriter writer(scratch.data(), scratch.size());
    if (!writer.append("{\"schema\":\"") ||
        !writer.append(kCompanionResponseSchema) ||
        !writer.append("\",\"kind\":\"error\",\"request_id\":\"\"," 
                       "\"status\":\"error\",\"reason\":\"") ||
        !writer.append(companionReadParseReason(status)) ||
        !writer.append("\"}\n")) {
        return false;
    }
    std::size_t size = 0;
    if (!writer.finish(&size)) return false;
    return publishScratch(scratch, size, output, capacity, outputLength);
}

}  // namespace leshy1::services::companion
