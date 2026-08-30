#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/automation/AutomationPackage.h"

namespace leshy1::apps::automation {

constexpr std::size_t kAutomationPackageNameBytes = 40U;

struct AutomationPackageCatalogEntry final {
    std::array<char, kAutomationPackageNameBytes> name{};
    std::uint32_t size = 0U;
};

// Fixed, lexicographically ordered view of externally supplied .lhau files.
// The catalog stores only filename metadata; package bytes never persist here.
class AutomationPackageCatalog final {
public:
    static constexpr std::size_t kCapacity = 4U;

    void clear();
    bool add(const char* name, std::uint32_t size);
    bool next();
    bool previous();

    const AutomationPackageCatalogEntry* get(std::size_t index) const;
    const AutomationPackageCatalogEntry* selected() const;
    std::size_t size() const { return size_; }
    std::size_t selection() const { return selection_; }

private:
    std::array<AutomationPackageCatalogEntry, kCapacity> entries_{};
    std::size_t size_ = 0U;
    std::size_t selection_ = 0U;
};

enum class AutomationInspectorSourceStatus : std::uint8_t {
    Empty,
    Inspected,
    TooLarge,
    ReadFailed,
};

const char* automationInspectorSourceStatusName(
    AutomationInspectorSourceStatus status);

struct AutomationInspectorModel final {
    AutomationInspectorSourceStatus sourceStatus =
        AutomationInspectorSourceStatus::Empty;
    std::array<char, kAutomationPackageNameBytes> sourceName{};
    std::uint32_t sourceSize = 0U;
    AutomationInspection inspection{};
    std::uint32_t revision = 0U;
};

// Passive product boundary. It retains a bounded summary only and deliberately
// exposes no execution, Action, HID, storage or resource operation.
class AutomationInspectorController final {
public:
    void clear();
    bool inspect(const char* sourceName, std::uint32_t declaredSize,
                 const std::uint8_t* bytes, std::size_t bytesRead,
                 std::uint16_t currentActionApiVersion,
                 AutomationSignatureVerifier* verifier);
    bool rejectSource(const char* sourceName, std::uint32_t declaredSize,
                      AutomationInspectorSourceStatus status);

    const AutomationInspectorModel& model() const { return model_; }

private:
    bool setSource(const char* sourceName, std::uint32_t declaredSize);
    void bumpRevision();

    AutomationInspectorModel model_{};
};

bool validAutomationPackageName(const char* name);

}  // namespace leshy1::apps::automation
