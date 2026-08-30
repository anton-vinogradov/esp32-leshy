#include "AutomationTrustStore.h"

#include <algorithm>
#include <cstring>

namespace leshy1::apps::automation {
namespace {

constexpr std::size_t kRecordHeaderBytes = 16U;
constexpr std::size_t kRecordKeyBytes = kAutomationKeyIdBytes +
    kAutomationP256PublicKeyBytes + kAutomationTrustLabelBytes;
constexpr std::size_t kRecordCrcOffset = kAutomationTrustRecordBytes - 4U;
static_assert(kRecordHeaderBytes +
                  kRecordKeyBytes * kAutomationTrustMaximumKeys + 4U ==
              kAutomationTrustRecordBytes);

bool anyNonZero(const std::uint8_t* bytes, std::size_t size) {
    if (bytes == nullptr) return false;
    std::uint8_t combined = 0U;
    for (std::size_t index = 0U; index < size; ++index) {
        combined = static_cast<std::uint8_t>(combined | bytes[index]);
    }
    return combined != 0U;
}

bool equalKeyId(
    const std::array<std::uint8_t, kAutomationKeyIdBytes>& left,
    const std::array<std::uint8_t, kAutomationKeyIdBytes>& right) {
    std::uint8_t difference = 0U;
    for (std::size_t index = 0U; index < left.size(); ++index) {
        difference = static_cast<std::uint8_t>(
            difference | static_cast<std::uint8_t>(left[index] ^ right[index]));
    }
    return difference == 0U;
}

bool validLabel(const std::array<char, kAutomationTrustLabelBytes + 1U>& label) {
    bool terminated = false;
    std::size_t size = 0U;
    for (; size < label.size(); ++size) {
        const unsigned char value = static_cast<unsigned char>(label[size]);
        if (value == 0U) {
            terminated = true;
            break;
        }
        if (value < 0x20U || value > 0x7eU) return false;
    }
    if (!terminated || size == 0U || size > kAutomationTrustLabelBytes) {
        return false;
    }
    for (std::size_t index = size + 1U; index < label.size(); ++index) {
        if (label[index] != '\0') return false;
    }
    return true;
}

std::uint32_t read32(const std::uint8_t* bytes) {
    return static_cast<std::uint32_t>(bytes[0]) |
        (static_cast<std::uint32_t>(bytes[1]) << 8U) |
        (static_cast<std::uint32_t>(bytes[2]) << 16U) |
        (static_cast<std::uint32_t>(bytes[3]) << 24U);
}

std::uint16_t read16(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>(bytes[0]) |
        static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(bytes[1]) << 8U);
}

void write16(std::uint8_t* bytes, std::uint16_t value) {
    bytes[0] = static_cast<std::uint8_t>(value & 0xffU);
    bytes[1] = static_cast<std::uint8_t>(value >> 8U);
}

void write32(std::uint8_t* bytes, std::uint32_t value) {
    bytes[0] = static_cast<std::uint8_t>(value & 0xffU);
    bytes[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
    bytes[2] = static_cast<std::uint8_t>((value >> 16U) & 0xffU);
    bytes[3] = static_cast<std::uint8_t>(value >> 24U);
}

std::uint32_t crc32(const std::uint8_t* bytes, std::size_t size) {
    std::uint32_t crc = 0xffffffffU;
    for (std::size_t index = 0U; index < size; ++index) {
        crc ^= bytes[index];
        for (std::uint8_t bit = 0U; bit < 8U; ++bit) {
            const std::uint32_t mask =
                static_cast<std::uint32_t>(0U - (crc & 1U));
            crc = (crc >> 1U) ^ (0xedb88320U & mask);
        }
    }
    return ~crc;
}

AutomationTrustMutationStatus authorize(
    AutomationTrustMutationAuthorization authorization) {
    if (!authorization.deviceUnlocked) {
        return AutomationTrustMutationStatus::AuthenticationRequired;
    }
    if (!authorization.confirmationFresh) {
        return AutomationTrustMutationStatus::ConfirmationRequired;
    }
    return AutomationTrustMutationStatus::Applied;
}

}  // namespace

const char* automationTrustLoadStatusName(AutomationTrustLoadStatus status) {
    switch (status) {
        case AutomationTrustLoadStatus::Loaded: return "loaded";
        case AutomationTrustLoadStatus::Missing: return "missing";
        case AutomationTrustLoadStatus::Corrupt: return "corrupt";
        case AutomationTrustLoadStatus::Error: return "error";
    }
    return "invalid";
}

const char* automationTrustMutationStatusName(
    AutomationTrustMutationStatus status) {
    switch (status) {
        case AutomationTrustMutationStatus::Applied: return "applied";
        case AutomationTrustMutationStatus::AuthenticationRequired:
            return "authentication_required";
        case AutomationTrustMutationStatus::ConfirmationRequired:
            return "confirmation_required";
        case AutomationTrustMutationStatus::InvalidKey: return "invalid_key";
        case AutomationTrustMutationStatus::DuplicateKey: return "duplicate_key";
        case AutomationTrustMutationStatus::KeyIdConflict:
            return "key_id_conflict";
        case AutomationTrustMutationStatus::Full: return "full";
        case AutomationTrustMutationStatus::NotFound: return "not_found";
        case AutomationTrustMutationStatus::PersistenceFailed:
            return "persistence_failed";
        case AutomationTrustMutationStatus::StoreUnavailable:
            return "store_unavailable";
    }
    return "invalid";
}

bool validAutomationTrustedKey(const AutomationTrustedKey& key) {
    return anyNonZero(key.keyId.data(), key.keyId.size()) &&
        key.publicKey[0] == 0x04U &&
        anyNonZero(key.publicKey.data() + 1U, key.publicKey.size() - 1U) &&
        validLabel(key.label);
}

bool validAutomationTrustSnapshot(const AutomationTrustSnapshot& snapshot) {
    if (snapshot.schemaVersion != kAutomationTrustSchemaVersion ||
        snapshot.count > kAutomationTrustMaximumKeys ||
        (snapshot.count != 0U && snapshot.generation == 0U)) {
        return false;
    }
    for (std::size_t index = 0U; index < snapshot.count; ++index) {
        if (!validAutomationTrustedKey(snapshot.keys[index])) return false;
        for (std::size_t previous = 0U; previous < index; ++previous) {
            if (equalKeyId(snapshot.keys[index].keyId,
                           snapshot.keys[previous].keyId)) {
                return false;
            }
        }
    }
    for (std::size_t index = snapshot.count; index < snapshot.keys.size(); ++index) {
        const AutomationTrustedKey& key = snapshot.keys[index];
        if (anyNonZero(key.keyId.data(), key.keyId.size()) ||
            anyNonZero(key.publicKey.data(), key.publicKey.size()) ||
            key.label[0] != '\0') {
            return false;
        }
    }
    return true;
}

bool encodeAutomationTrustRecord(const AutomationTrustSnapshot& snapshot,
                                 AutomationTrustRecord* output) {
    if (output == nullptr || !validAutomationTrustSnapshot(snapshot)) {
        return false;
    }
    output->fill(0U);
    std::memcpy(output->data(), "LHTS", 4U);
    write16(output->data() + 4U, kAutomationTrustSchemaVersion);
    write16(output->data() + 6U,
            static_cast<std::uint16_t>(kAutomationTrustRecordBytes));
    write32(output->data() + 8U, snapshot.generation);
    (*output)[12U] = snapshot.count;
    for (std::size_t index = 0U; index < snapshot.count; ++index) {
        const AutomationTrustedKey& key = snapshot.keys[index];
        std::uint8_t* encoded = output->data() + kRecordHeaderBytes +
            index * kRecordKeyBytes;
        std::memcpy(encoded, key.keyId.data(), key.keyId.size());
        encoded += key.keyId.size();
        std::memcpy(encoded, key.publicKey.data(), key.publicKey.size());
        encoded += key.publicKey.size();
        std::memcpy(encoded, key.label.data(), kAutomationTrustLabelBytes);
    }
    write32(output->data() + kRecordCrcOffset,
            crc32(output->data(), kRecordCrcOffset));
    return true;
}

bool decodeAutomationTrustRecord(const AutomationTrustRecord& record,
                                 AutomationTrustSnapshot* output) {
    if (output == nullptr) return false;
    *output = {};
    const bool header = std::memcmp(record.data(), "LHTS", 4U) == 0 &&
        read16(record.data() + 4U) == kAutomationTrustSchemaVersion;
    const std::uint16_t declaredBytes = read16(record.data() + 6U);
    if (!header || declaredBytes != kAutomationTrustRecordBytes ||
        record[13U] != 0U || record[14U] != 0U || record[15U] != 0U ||
        read32(record.data() + kRecordCrcOffset) !=
            crc32(record.data(), kRecordCrcOffset)) {
        return false;
    }
    AutomationTrustSnapshot decoded{};
    decoded.generation = read32(record.data() + 8U);
    decoded.count = record[12U];
    if (decoded.count > decoded.keys.size()) return false;
    for (std::size_t index = 0U; index < decoded.count; ++index) {
        AutomationTrustedKey& key = decoded.keys[index];
        const std::uint8_t* encoded = record.data() + kRecordHeaderBytes +
            index * kRecordKeyBytes;
        std::memcpy(key.keyId.data(), encoded, key.keyId.size());
        encoded += key.keyId.size();
        std::memcpy(key.publicKey.data(), encoded, key.publicKey.size());
        encoded += key.publicKey.size();
        std::memcpy(key.label.data(), encoded, kAutomationTrustLabelBytes);
        key.label[kAutomationTrustLabelBytes] = '\0';
    }
    // Canonical records keep every unused key slot zero.
    const std::size_t used = kRecordHeaderBytes +
        static_cast<std::size_t>(decoded.count) * kRecordKeyBytes;
    for (std::size_t index = used; index < kRecordCrcOffset; ++index) {
        if (record[index] != 0U) return false;
    }
    if (!validAutomationTrustSnapshot(decoded)) return false;
    *output = decoded;
    return true;
}

const AutomationTrustedKey* findAutomationTrustedKey(
    const AutomationTrustSnapshot& snapshot,
    const std::array<std::uint8_t, kAutomationKeyIdBytes>& keyId) {
    if (!validAutomationTrustSnapshot(snapshot)) return nullptr;
    for (std::size_t index = 0U; index < snapshot.count; ++index) {
        if (equalKeyId(snapshot.keys[index].keyId, keyId)) {
            return &snapshot.keys[index];
        }
    }
    return nullptr;
}

bool AutomationTrustStore::restore() {
    snapshot_ = {};
    loadStatus_ = backend_.load(&snapshot_);
    if (loadStatus_ == AutomationTrustLoadStatus::Missing) {
        snapshot_ = {};
        ready_ = true;
        return true;
    }
    ready_ = loadStatus_ == AutomationTrustLoadStatus::Loaded &&
        validAutomationTrustSnapshot(snapshot_);
    if (!ready_) snapshot_ = {};
    return ready_;
}

AutomationTrustMutationStatus AutomationTrustStore::enroll(
    const AutomationTrustedKey& key,
    AutomationTrustMutationAuthorization authorization) {
    const AutomationTrustMutationStatus admission = authorize(authorization);
    if (admission != AutomationTrustMutationStatus::Applied) return admission;
    if (!ready_) return AutomationTrustMutationStatus::StoreUnavailable;
    if (!validAutomationTrustedKey(key)) {
        return AutomationTrustMutationStatus::InvalidKey;
    }
    const AutomationTrustedKey* existing =
        findAutomationTrustedKey(snapshot_, key.keyId);
    if (existing != nullptr) {
        return existing->publicKey == key.publicKey &&
                       existing->label == key.label
            ? AutomationTrustMutationStatus::DuplicateKey
            : AutomationTrustMutationStatus::KeyIdConflict;
    }
    if (snapshot_.count >= snapshot_.keys.size()) {
        return AutomationTrustMutationStatus::Full;
    }
    AutomationTrustSnapshot candidate = snapshot_;
    candidate.keys[candidate.count++] = key;
    ++candidate.generation;
    if (candidate.generation == 0U || !validAutomationTrustSnapshot(candidate)) {
        return AutomationTrustMutationStatus::PersistenceFailed;
    }
    if (!backend_.save(candidate)) {
        return AutomationTrustMutationStatus::PersistenceFailed;
    }
    snapshot_ = candidate;
    loadStatus_ = AutomationTrustLoadStatus::Loaded;
    return AutomationTrustMutationStatus::Applied;
}

AutomationTrustMutationStatus AutomationTrustStore::revoke(
    const std::array<std::uint8_t, kAutomationKeyIdBytes>& keyId,
    AutomationTrustMutationAuthorization authorization) {
    const AutomationTrustMutationStatus admission = authorize(authorization);
    if (admission != AutomationTrustMutationStatus::Applied) return admission;
    if (!ready_) return AutomationTrustMutationStatus::StoreUnavailable;
    std::size_t found = snapshot_.count;
    for (std::size_t index = 0U; index < snapshot_.count; ++index) {
        if (equalKeyId(snapshot_.keys[index].keyId, keyId)) {
            found = index;
            break;
        }
    }
    if (found == snapshot_.count) return AutomationTrustMutationStatus::NotFound;
    AutomationTrustSnapshot candidate = snapshot_;
    for (std::size_t index = found + 1U; index < candidate.count; ++index) {
        candidate.keys[index - 1U] = candidate.keys[index];
    }
    candidate.keys[candidate.count - 1U] = {};
    --candidate.count;
    ++candidate.generation;
    if (candidate.generation == 0U || !validAutomationTrustSnapshot(candidate)) {
        return AutomationTrustMutationStatus::PersistenceFailed;
    }
    if (!backend_.save(candidate)) {
        return AutomationTrustMutationStatus::PersistenceFailed;
    }
    snapshot_ = candidate;
    loadStatus_ = AutomationTrustLoadStatus::Loaded;
    return AutomationTrustMutationStatus::Applied;
}

}  // namespace leshy1::apps::automation
