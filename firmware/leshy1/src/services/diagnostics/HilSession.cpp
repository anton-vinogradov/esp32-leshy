#include "services/diagnostics/HilSession.h"

#include <cstring>

namespace leshy1::services::diagnostics {
namespace {

bool isLowerHex(const char* value, std::size_t length) {
    if (value == nullptr || std::strlen(value) != length) return false;
    for (std::size_t i = 0; i < length; ++i) {
        const char character = value[i];
        if (!((character >= '0' && character <= '9') ||
              (character >= 'a' && character <= 'f'))) {
            return false;
        }
    }
    return true;
}

}  // namespace

HilSessionStatus HilSession::begin(const char* sessionId,
                                   const char* candidateAppIdentity,
                                   const char* runningAppIdentity) {
    if (active_) return HilSessionStatus::AlreadyActive;
    if (!isLowerHex(sessionId, kSessionIdLength)) {
        return HilSessionStatus::InvalidSessionId;
    }
    if (!isLowerHex(candidateAppIdentity, kAppIdentityLength) ||
        !isLowerHex(runningAppIdentity, kAppIdentityLength)) {
        return HilSessionStatus::InvalidAppIdentity;
    }
    if (std::strcmp(candidateAppIdentity, runningAppIdentity) != 0) {
        return HilSessionStatus::AppIdentityMismatch;
    }
    std::memcpy(id_.data(), sessionId, kSessionIdLength + 1);
    active_ = true;
    return HilSessionStatus::Begun;
}

HilSessionStatus HilSession::end(const char* sessionId) {
    if (!active_) return HilSessionStatus::NotActive;
    if (!isLowerHex(sessionId, kSessionIdLength)) {
        return HilSessionStatus::InvalidSessionId;
    }
    if (std::strcmp(sessionId, id_.data()) != 0) {
        return HilSessionStatus::SessionMismatch;
    }
    active_ = false;
    return HilSessionStatus::Ended;
}

const char* hilSessionStatusName(HilSessionStatus status) {
    switch (status) {
        case HilSessionStatus::Begun: return "begun";
        case HilSessionStatus::Ended: return "ended";
        case HilSessionStatus::InvalidSessionId: return "invalid_session_id";
        case HilSessionStatus::InvalidAppIdentity: return "invalid_app_identity";
        case HilSessionStatus::AppIdentityMismatch: return "app_identity_mismatch";
        case HilSessionStatus::AlreadyActive: return "already_active";
        case HilSessionStatus::NotActive: return "not_active";
        case HilSessionStatus::SessionMismatch: return "session_mismatch";
    }
    return "unknown";
}

}  // namespace leshy1::services::diagnostics
