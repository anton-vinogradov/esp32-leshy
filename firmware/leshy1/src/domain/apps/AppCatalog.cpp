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

    const bool frameCapture = available(inventory, "capture.wifi_passive");
    items_[size_++] = {
        "capture", "CAPTURE",
        frameCapture ? "wifi frames / explicit sd save" : "passive capture unavailable",
        4, frameCapture, false,
        kernel::runtime::resourceMask(
            kernel::runtime::Resource::UiForeground) |
            kernel::runtime::resourceMask(kernel::runtime::Resource::EspRf)};

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
        "targets", "TARGETS", "planned product capability", 7, false, false, 0};

    items_[size_++] = {
        "lab", "LAB", "planned authorized workspace", 8, false, false, 0};

    // Service functions live below the final product-level Device entry rather
    // than competing with user jobs on Home. Device remains available on a
    // degraded profile because diagnostics and an honest Self-Test are remedies.
    items_[size_++] = {
        "device", "DEVICE", "settings / checks / information", 9, true, false,
        kernel::runtime::resourceMask(kernel::runtime::Resource::UiForeground)};
}

const AppMenuItem* AppCatalog::get(std::size_t index) const {
    return index < size_ ? &items_[index] : nullptr;
}

}  // namespace leshy1::domain::apps
