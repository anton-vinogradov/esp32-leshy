#include "AutomationInspectorController.h"

#include <cstring>

namespace leshy1::apps::automation {
namespace {

bool allowedNameCharacter(char value) {
    return (value >= 'a' && value <= 'z') ||
        (value >= 'A' && value <= 'Z') ||
        (value >= '0' && value <= '9') || value == '-' || value == '_' ||
        value == '.';
}

void secureClear(void* value, std::size_t size) {
    volatile std::uint8_t* cursor = static_cast<volatile std::uint8_t*>(value);
    while (size-- != 0U) *cursor++ = 0U;
}

}  // namespace

bool validAutomationPackageName(const char* name) {
    if (name == nullptr || name[0] == '\0') return false;
    std::size_t length = 0U;
    while (length < kAutomationPackageNameBytes && name[length] != '\0') {
        if (!allowedNameCharacter(name[length])) return false;
        ++length;
    }
    if (length < 6U || length >= kAutomationPackageNameBytes ||
        name[length] != '\0') {
        return false;
    }
    const char* suffix = name + length - 5U;
    return suffix[0] == '.' &&
        (suffix[1] == 'l' || suffix[1] == 'L') &&
        (suffix[2] == 'h' || suffix[2] == 'H') &&
        (suffix[3] == 'a' || suffix[3] == 'A') &&
        (suffix[4] == 'u' || suffix[4] == 'U');
}

void AutomationPackageCatalog::clear() {
    secureClear(entries_.data(), sizeof(entries_));
    size_ = 0U;
    selection_ = 0U;
}

bool AutomationPackageCatalog::add(const char* name, std::uint32_t size) {
    if (!validAutomationPackageName(name)) return false;
    std::size_t insertion = 0U;
    while (insertion < size_ &&
           std::strcmp(entries_[insertion].name.data(), name) < 0) {
        ++insertion;
    }
    if (insertion < size_ &&
        std::strcmp(entries_[insertion].name.data(), name) == 0) {
        return false;
    }
    if (size_ == entries_.size() && insertion == size_) return false;
    const std::size_t destinationEnd =
        size_ < entries_.size() ? size_ : entries_.size() - 1U;
    for (std::size_t index = destinationEnd; index > insertion; --index) {
        entries_[index] = entries_[index - 1U];
    }
    AutomationPackageCatalogEntry& entry = entries_[insertion];
    entry = {};
    std::strncpy(entry.name.data(), name, entry.name.size() - 1U);
    entry.size = size;
    if (size_ < entries_.size()) ++size_;
    return true;
}

bool AutomationPackageCatalog::next() {
    if (selection_ + 1U >= size_) return false;
    ++selection_;
    return true;
}

bool AutomationPackageCatalog::previous() {
    if (selection_ == 0U) return false;
    --selection_;
    return true;
}

const AutomationPackageCatalogEntry* AutomationPackageCatalog::get(
    std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

const AutomationPackageCatalogEntry* AutomationPackageCatalog::selected() const {
    return get(selection_);
}

const char* automationInspectorSourceStatusName(
    AutomationInspectorSourceStatus status) {
    switch (status) {
        case AutomationInspectorSourceStatus::Empty: return "empty";
        case AutomationInspectorSourceStatus::Inspected: return "inspected";
        case AutomationInspectorSourceStatus::TooLarge: return "too_large";
        case AutomationInspectorSourceStatus::ReadFailed: return "read_failed";
    }
    return "invalid";
}

void AutomationInspectorController::bumpRevision() {
    ++model_.revision;
    if (model_.revision == 0U) model_.revision = 1U;
}

void AutomationInspectorController::clear() {
    const std::uint32_t revision = model_.revision;
    secureClear(&model_, sizeof(model_));
    model_.sourceStatus = AutomationInspectorSourceStatus::Empty;
    model_.revision = revision;
    bumpRevision();
}

bool AutomationInspectorController::setSource(
    const char* sourceName, std::uint32_t declaredSize) {
    if (!validAutomationPackageName(sourceName)) return false;
    std::strncpy(model_.sourceName.data(), sourceName,
                 model_.sourceName.size() - 1U);
    model_.sourceSize = declaredSize;
    return true;
}

bool AutomationInspectorController::inspect(
    const char* sourceName, std::uint32_t declaredSize,
    const std::uint8_t* bytes, std::size_t bytesRead,
    std::uint16_t currentActionApiVersion,
    AutomationSignatureVerifier* verifier) {
    clear();
    if (!setSource(sourceName, declaredSize)) return false;
    if (declaredSize > kAutomationMaximumPackageBytes) {
        model_.sourceStatus = AutomationInspectorSourceStatus::TooLarge;
        model_.inspection.parseStatus = AutomationParseStatus::TooLarge;
        bumpRevision();
        return true;
    }
    if (bytes == nullptr || bytesRead != declaredSize) {
        model_.sourceStatus = AutomationInspectorSourceStatus::ReadFailed;
        model_.inspection.parseStatus =
            AutomationParseStatus::InvalidArgument;
        bumpRevision();
        return true;
    }
    model_.inspection = inspectAutomationPackage(
        bytes, bytesRead, currentActionApiVersion, verifier);
    model_.sourceStatus = AutomationInspectorSourceStatus::Inspected;
    bumpRevision();
    return true;
}

bool AutomationInspectorController::rejectSource(
    const char* sourceName, std::uint32_t declaredSize,
    AutomationInspectorSourceStatus status) {
    if (status != AutomationInspectorSourceStatus::TooLarge &&
        status != AutomationInspectorSourceStatus::ReadFailed) {
        return false;
    }
    clear();
    if (!setSource(sourceName, declaredSize)) return false;
    model_.sourceStatus = status;
    model_.inspection.parseStatus =
        status == AutomationInspectorSourceStatus::TooLarge
            ? AutomationParseStatus::TooLarge
            : AutomationParseStatus::InvalidArgument;
    bumpRevision();
    return true;
}

}  // namespace leshy1::apps::automation
