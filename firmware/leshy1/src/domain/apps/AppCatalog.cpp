#include "AppCatalog.h"

namespace leshy1::domain::apps {
namespace {

bool available(const hardware::HardwareInventory& inventory, const char* key) {
    const hardware::CapabilityRecord* record = inventory.find(key);
    return record != nullptr && record->state == hardware::CapabilityState::Available;
}

}  // namespace

void AppCatalog::rebuild(const hardware::HardwareInventory& inventory) {
    size_ = 0;
    const bool diagnostics = available(inventory, "board.profile");
    items_[size_++] = {"diagnostics", "DIAGNOSTICS",
                       diagnostics ? "ready" : "board profile unavailable", 1, diagnostics,
                       false,
                       kernel::runtime::resourceMask(kernel::runtime::Resource::UiForeground)};

    const bool persistentSurvey =
        available(inventory, "survey.persistent_passive");
    const bool wifiSurvey = available(inventory, "radio.wifi");
    const bool simulatedSurvey = available(inventory, "survey.simulated");
    const bool realSurvey = persistentSurvey || wifiSurvey;
    const bool survey = realSurvey || simulatedSurvey;
    items_[size_++] = {"survey", "SURVEY",
                       persistentSurvey
                           ? "passive / persistent"
                           : (realSurvey
                                  ? "ready"
                                  : (simulatedSurvey
                                         ? "simulated / rf off"
                                         : "passive source unavailable")),
                       2, survey, !realSurvey && simulatedSurvey,
                       persistentSurvey
                           ? kernel::runtime::resourceMask(
                                 kernel::runtime::Resource::UiForeground) |
                                 kernel::runtime::resourceMask(
                                     kernel::runtime::Resource::EspRf) |
                                 kernel::runtime::resourceMask(
                                     kernel::runtime::Resource::Storage) |
                                 kernel::runtime::resourceMask(
                                     kernel::runtime::Resource::RadioSpi)
                           : (simulatedSurvey && !realSurvey)
                           ? kernel::runtime::resourceMask(kernel::runtime::Resource::UiForeground)
                           : kernel::runtime::Resource::UiForeground |
                                 kernel::runtime::Resource::EspRf};

    const bool persistentLibrary = available(inventory, "storage.sd") ||
                                   available(inventory, "library.persistent_session");
    const bool simulatedLibrary =
        !persistentLibrary && available(inventory, "library.simulated");
    const bool library = persistentLibrary || simulatedLibrary;
    items_[size_++] = {"library", "LIBRARY",
                       simulatedLibrary ? "simulated / ram only"
                                        : (persistentLibrary ? "ready"
                                                             : "storage unavailable"),
                       3, library, simulatedLibrary,
                       simulatedLibrary
                           ? kernel::runtime::resourceMask(kernel::runtime::Resource::UiForeground)
                           : kernel::runtime::Resource::UiForeground |
                                 kernel::runtime::Resource::Storage};

    items_[size_++] = {
        "language", "LANGUAGE", "interface language", 4, true, false,
        kernel::runtime::resourceMask(kernel::runtime::Resource::UiForeground)};

    // Self-Test remains the final utility item even when the profile is
    // degraded: explaining a failed check is part of its purpose. Opening it
    // owns only the UI; Quick starts no hardware or storage resource.
    items_[size_++] = {
        "self-test", "SELF-TEST", "quick / full guided", 5, true, false,
        kernel::runtime::resourceMask(kernel::runtime::Resource::UiForeground)};
}

const AppMenuItem* AppCatalog::get(std::size_t index) const {
    return index < size_ ? &items_[index] : nullptr;
}

}  // namespace leshy1::domain::apps
