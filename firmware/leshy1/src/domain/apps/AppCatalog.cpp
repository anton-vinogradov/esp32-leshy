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
    const bool wifi = realSurvey || simulatedSurvey;
    const auto surveyResources = persistentSurvey
        ? kernel::runtime::resourceMask(
              kernel::runtime::Resource::UiForeground) |
              kernel::runtime::resourceMask(
                  kernel::runtime::Resource::EspRf) |
              kernel::runtime::resourceMask(
                  kernel::runtime::Resource::Storage) |
              kernel::runtime::resourceMask(
                  kernel::runtime::Resource::RadioSpi)
        : (simulatedSurvey && !realSurvey)
              ? kernel::runtime::resourceMask(
                    kernel::runtime::Resource::UiForeground)
              : kernel::runtime::Resource::UiForeground |
                    kernel::runtime::Resource::EspRf;
    items_[size_++] = {"wifi", "WI-FI",
                       persistentSurvey
                           ? "passive / persistent"
                           : (realSurvey
                                  ? "ready"
                                  : (simulatedSurvey
                                         ? "simulated / rf off"
                                         : "passive source unavailable")),
                       2, wifi, !realSurvey && simulatedSurvey,
                       surveyResources};

    const bool ble = available(inventory, "radio.ble");
    items_[size_++] = {
        "ble", "BLUETOOTH", ble ? "passive / persistent"
                                    : "passive source unavailable",
        2, ble, false, surveyResources};

    // The fitted receiver shield is part of the exact board profile. Expose
    // its two user-facing receive-only jobs directly instead of hiding them
    // behind the internal Survey workflow.
    const bool spectrum = available(inventory, "board.profile");
    const auto spectrumResources =
        kernel::runtime::resourceMask(
            kernel::runtime::Resource::UiForeground) |
        kernel::runtime::resourceMask(
            kernel::runtime::Resource::RadioSpi);
    items_[size_++] = {"spectrum24", "2.4 GHZ", "spectrum / waterfall",
                       2, spectrum, false, spectrumResources};
    items_[size_++] = {"subghz", "SUB-GHZ", "315 / 433 / 868 / 915",
                       2, spectrum, false, spectrumResources};

    const bool frameCapture = available(inventory, "capture.wifi_passive");
    items_[size_++] = {
        "capture", "CAPTURE",
        frameCapture ? "wifi / infrared / explicit sd save" : "passive capture unavailable",
        4, frameCapture, false,
        kernel::runtime::resourceMask(
            kernel::runtime::Resource::UiForeground) |
            kernel::runtime::resourceMask(kernel::runtime::Resource::EspRf) |
            kernel::runtime::resourceMask(kernel::runtime::Resource::RadioSpi)};

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

    // Service functions remain the final entry. Planned Targets and Lab work
    // stays in the documented roadmap until there is a usable screen behind it.
    items_[size_++] = {
        "device", "DEVICE", "settings / checks / information", 9, true, false,
        kernel::runtime::resourceMask(kernel::runtime::Resource::UiForeground)};
}

const AppMenuItem* AppCatalog::get(std::size_t index) const {
    return index < size_ ? &items_[index] : nullptr;
}

}  // namespace leshy1::domain::apps
