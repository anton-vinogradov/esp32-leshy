#include "ProductSurveyAdmission.h"

#include <cstring>

namespace leshy1::apps::survey {
namespace {

constexpr kernel::runtime::ResourceMask kProductSurveyResources =
    kernel::runtime::resourceMask(kernel::runtime::Resource::EspRf) |
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage) |
    kernel::runtime::resourceMask(kernel::runtime::Resource::RadioSpi);
constexpr kernel::runtime::ResourceMask kProductStoreResources =
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage) |
    kernel::runtime::resourceMask(kernel::runtime::Resource::RadioSpi);

constexpr std::uint8_t kWifiSourceMask = 1U << 0U;
constexpr std::uint8_t kBleSourceMask = 1U << 1U;
constexpr std::uint8_t kSupportedSourceMask =
    kWifiSourceMask | kBleSourceMask;

ProductSurveyPermit rejected(ProductSurveyAdmissionStatus status,
                              const ProductSurveyRequest& request) {
    ProductSurveyPermit permit;
    permit.status = status;
    permit.requiredResources = kProductSurveyResources;
    permit.selectedSourceMask = request.selectedSourceMask;
    permit.availableSourceMask = request.availableSourceMask;
    permit.degradedSourceMask = static_cast<std::uint8_t>(
        request.selectedSourceMask & ~request.availableSourceMask);
    return permit;
}

}  // namespace

const char* productSurveyAdmissionStatusName(
    ProductSurveyAdmissionStatus status) {
    switch (status) {
        case ProductSurveyAdmissionStatus::Permitted: return "permitted";
        case ProductSurveyAdmissionStatus::ExplicitStartRequired:
            return "explicit_start_required";
        case ProductSurveyAdmissionStatus::SourceUnavailable:
            return "source_unavailable";
        case ProductSurveyAdmissionStatus::PassivePlanRejected:
            return "passive_plan_rejected";
        case ProductSurveyAdmissionStatus::StoreRejected:
            return "store_rejected";
        case ProductSurveyAdmissionStatus::WritableStoreRequired:
            return "writable_store_required";
        case ProductSurveyAdmissionStatus::ResourcesMissing:
            return "resources_missing";
        case ProductSurveyAdmissionStatus::ResourceConflict:
            return "resource_conflict";
    }
    return "explicit_start_required";
}

ProductSurveyPermit authorizeProductSurvey(
    const ProductSurveyRequest& request) {
    if (!request.explicitStart) {
        return rejected(ProductSurveyAdmissionStatus::ExplicitStartRequired,
                        request);
    }
    const bool sourceMasksValid = request.selectedSourceMask != 0 &&
        (request.selectedSourceMask & ~kSupportedSourceMask) == 0 &&
        (request.availableSourceMask & ~request.selectedSourceMask) == 0;
    if (!sourceMasksValid || !request.sourceAvailable ||
        request.availableSourceMask == 0) {
        return rejected(ProductSurveyAdmissionStatus::SourceUnavailable,
                        request);
    }
    if (((request.selectedSourceMask & kWifiSourceMask) != 0 &&
         !drivers::wifi::validatePassivePlan(request.scanPlan)) ||
        ((request.selectedSourceMask & kBleSourceMask) != 0 &&
         !drivers::ble::validatePassivePlan(request.bleScanPlan))) {
        return rejected(ProductSurveyAdmissionStatus::PassivePlanRejected,
                        request);
    }
    if (!request.storePermit.allowed() || request.storePermit.rootPath == nullptr ||
        std::strcmp(request.storePermit.rootPath,
                    storage::kProductSessionStoreRoot) != 0 ||
        request.storePermit.requiredResources != kProductStoreResources ||
        request.storePermit.byteLimit == 0) {
        return rejected(ProductSurveyAdmissionStatus::StoreRejected, request);
    }
    if (request.storePermit.operation !=
            storage::ProductStoreOperation::CommitSession ||
        !request.storePermit.writable) {
        return rejected(ProductSurveyAdmissionStatus::WritableStoreRequired,
                        request);
    }
    if ((request.ownedResources & kProductSurveyResources) !=
        kProductSurveyResources) {
        return rejected(ProductSurveyAdmissionStatus::ResourcesMissing,
                        request);
    }
    if (request.conflictingOwner) {
        return rejected(ProductSurveyAdmissionStatus::ResourceConflict,
                        request);
    }
    ProductSurveyPermit permit;
    permit.status = ProductSurveyAdmissionStatus::Permitted;
    permit.requiredResources = kProductSurveyResources;
    permit.selectedSourceMask = request.selectedSourceMask;
    permit.availableSourceMask = request.availableSourceMask;
    permit.degradedSourceMask = static_cast<std::uint8_t>(
        request.selectedSourceMask & ~request.availableSourceMask);
    return permit;
}

}  // namespace leshy1::apps::survey
