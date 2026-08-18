#pragma once

#include <cstdint>

#include "drivers/ble/BlePassiveContract.h"
#include "drivers/wifi/WifiPassiveContract.h"
#include "kernel/runtime/Resources.h"
#include "storage/ProductStorePolicy.h"

namespace leshy1::apps::survey {

enum class ProductSurveyAdmissionStatus : std::uint8_t {
    Permitted,
    ExplicitStartRequired,
    SourceUnavailable,
    PassivePlanRejected,
    StoreRejected,
    WritableStoreRequired,
    ResourcesMissing,
    ResourceConflict,
};

const char* productSurveyAdmissionStatusName(
    ProductSurveyAdmissionStatus status);

struct ProductSurveyRequest final {
    bool explicitStart = false;
    bool sourceAvailable = false;
    std::uint8_t selectedSourceMask = 1;
    std::uint8_t availableSourceMask = 1;
    drivers::wifi::WifiScanPlan scanPlan{};
    drivers::ble::BleScanPlan bleScanPlan{};
    storage::ProductStorePermit storePermit{};
    kernel::runtime::ResourceMask ownedResources = 0;
    bool conflictingOwner = false;
};

struct ProductSurveyPermit final {
    ProductSurveyAdmissionStatus status =
        ProductSurveyAdmissionStatus::ExplicitStartRequired;
    kernel::runtime::ResourceMask requiredResources = 0;
    bool passive = true;
    bool persistent = true;
    bool simulated = false;
    std::uint8_t selectedSourceMask = 0;
    std::uint8_t availableSourceMask = 0;
    std::uint8_t degradedSourceMask = 0;

    bool allowed() const {
        return status == ProductSurveyAdmissionStatus::Permitted;
    }
};

// Final fail-closed gate before a product Survey may start real hardware. A
// requested real Session is never silently downgraded to simulated input or RAM.
ProductSurveyPermit authorizeProductSurvey(
    const ProductSurveyRequest& request);

}  // namespace leshy1::apps::survey
