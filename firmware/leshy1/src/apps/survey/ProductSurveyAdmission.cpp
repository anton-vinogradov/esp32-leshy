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

ProductSurveyPermit rejected(ProductSurveyAdmissionStatus status) {
    return {status, kProductSurveyResources, true, true, false};
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
        return rejected(ProductSurveyAdmissionStatus::ExplicitStartRequired);
    }
    if (!request.sourceAvailable) {
        return rejected(ProductSurveyAdmissionStatus::SourceUnavailable);
    }
    if (!drivers::wifi::validatePassivePlan(request.scanPlan)) {
        return rejected(ProductSurveyAdmissionStatus::PassivePlanRejected);
    }
    if (!request.storePermit.allowed() || request.storePermit.rootPath == nullptr ||
        std::strcmp(request.storePermit.rootPath,
                    storage::kProductSessionStoreRoot) != 0 ||
        request.storePermit.requiredResources != kProductStoreResources ||
        request.storePermit.byteLimit == 0) {
        return rejected(ProductSurveyAdmissionStatus::StoreRejected);
    }
    if (request.storePermit.operation !=
            storage::ProductStoreOperation::CommitSession ||
        !request.storePermit.writable) {
        return rejected(ProductSurveyAdmissionStatus::WritableStoreRequired);
    }
    if ((request.ownedResources & kProductSurveyResources) !=
        kProductSurveyResources) {
        return rejected(ProductSurveyAdmissionStatus::ResourcesMissing);
    }
    if (request.conflictingOwner) {
        return rejected(ProductSurveyAdmissionStatus::ResourceConflict);
    }
    return {ProductSurveyAdmissionStatus::Permitted, kProductSurveyResources,
            true, true, false};
}

}  // namespace leshy1::apps::survey
