#pragma once

#include <cstdint>

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
    drivers::wifi::WifiScanPlan scanPlan{};
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

    bool allowed() const {
        return status == ProductSurveyAdmissionStatus::Permitted;
    }
};

// Final fail-closed gate before a product Survey may start real hardware. A
// requested real Session is never silently downgraded to simulated input or RAM.
ProductSurveyPermit authorizeProductSurvey(
    const ProductSurveyRequest& request);

}  // namespace leshy1::apps::survey
