#include "FixtureSession.h"

#include <cstring>

namespace leshy::hil::fixture {

const char* fixtureSignalName(FixtureSignal signal) {
    switch (signal) {
        case FixtureSignal::None: return "none";
        case FixtureSignal::InfraredNec: return "infrared_nec";
        case FixtureSignal::Nrf24Carrier: return "nrf24_carrier";
        case FixtureSignal::Cc1101Ook: return "cc1101_ook";
        case FixtureSignal::Cc1101Fsk: return "cc1101_fsk";
    }
    return "none";
}

const char* fixtureStateName(FixtureState state) {
    switch (state) {
        case FixtureState::Idle: return "idle";
        case FixtureState::Armed: return "armed";
        case FixtureState::Running: return "running";
        case FixtureState::Complete: return "complete";
        case FixtureState::Stopped: return "stopped";
        case FixtureState::Expired: return "expired";
        case FixtureState::Panicked: return "panicked";
        case FixtureState::Fault: return "fault";
    }
    return "fault";
}

bool FixtureSession::same(const char* left, const char* right) {
    return left != nullptr && right != nullptr && std::strcmp(left, right) == 0;
}

bool FixtureSession::validHex(const char* value, std::uint8_t length,
                              bool uppercaseOnly) {
    if (value == nullptr || std::strlen(value) != length) return false;
    for (std::uint8_t index = 0; index < length; ++index) {
        const char ch = value[index];
        const bool digit = ch >= '0' && ch <= '9';
        const bool lower = !uppercaseOnly && ch >= 'a' && ch <= 'f';
        const bool upper = ch >= 'A' && ch <= 'F';
        if (!digit && !lower && !upper) return false;
    }
    return true;
}

void FixtureSession::reject(const char* reason) {
    report_.lastError = reason;
}

bool FixtureSession::begin(const char* sessionId,
                           const char* requestedAppSha256,
                           const char* runningAppSha256,
                           const char* requestedFixtureId,
                           const char* runningFixtureId,
                           std::uint32_t nowMs, bool outputInactive) {
    if (report_.state == FixtureState::Running) {
        reject("already_running");
        return false;
    }
    if (!outputInactive) {
        report_.state = FixtureState::Fault;
        report_.outputInactive = false;
        reject("output_not_inactive");
        return false;
    }
    if (!validHex(sessionId, 32, false)) {
        reject("invalid_session_id");
        return false;
    }
    if (!validHex(requestedAppSha256, 64, false) ||
        !same(requestedAppSha256, runningAppSha256)) {
        reject("app_identity_mismatch");
        return false;
    }
    if (!validHex(requestedFixtureId, 16, true) ||
        !same(requestedFixtureId, runningFixtureId)) {
        reject("fixture_identity_mismatch");
        return false;
    }
    std::memcpy(sessionId_, sessionId, 33);
    report_.state = FixtureState::Armed;
    report_.deadlineMs = nowMs + kSessionLifetimeMs;
    report_.lastDurationUs = 0;
    report_.maximumDurationUs = 0;
    report_.signal = FixtureSignal::None;
    report_.outputInactive = true;
    report_.lastError = "none";
    return true;
}

bool FixtureSession::authorizeNecOnce(const char* sessionId,
                                      const char* vectorId,
                                      std::uint32_t nowMs) {
    return authorizeFixedOnce(sessionId, vectorId, kNecVectorId,
                              FixtureSignal::InfraredNec,
                              kMaximumIrEmissionUs, nowMs);
}

bool FixtureSession::authorizeNrf24CarrierOnce(const char* sessionId,
                                               const char* vectorId,
                                               std::uint32_t nowMs) {
    return authorizeFixedOnce(sessionId, vectorId, kNrf24VectorId,
                              FixtureSignal::Nrf24Carrier,
                              kMaximumNrf24CarrierUs, nowMs);
}

bool FixtureSession::authorizeCc1101OokOnce(const char* sessionId,
                                            const char* vectorId,
                                            std::uint32_t nowMs) {
    return authorizeFixedOnce(sessionId, vectorId, kCc1101OokVectorId,
                              FixtureSignal::Cc1101Ook,
                              kMaximumCc1101EmissionUs, nowMs);
}

bool FixtureSession::authorizeCc1101FskOnce(const char* sessionId,
                                            const char* vectorId,
                                            std::uint32_t nowMs) {
    return authorizeFixedOnce(sessionId, vectorId, kCc1101FskVectorId,
                              FixtureSignal::Cc1101Fsk,
                              kMaximumCc1101EmissionUs, nowMs);
}

bool FixtureSession::authorizeFixedOnce(const char* sessionId,
                                        const char* vectorId,
                                        const char* allowedVectorId,
                                        FixtureSignal signal,
                                        std::uint32_t maximumDurationUs,
                                        std::uint32_t nowMs) {
    if (report_.state != FixtureState::Armed) {
        reject("not_armed");
        return false;
    }
    if (!same(sessionId, sessionId_)) {
        reject("session_mismatch");
        return false;
    }
    if (!same(vectorId, allowedVectorId)) {
        reject("vector_not_allowed");
        return false;
    }
    if (static_cast<std::int32_t>(nowMs - report_.deadlineMs) >= 0) {
        report_.state = FixtureState::Expired;
        ++report_.stopCount;
        reject("session_expired");
        return false;
    }
    report_.state = FixtureState::Running;
    report_.signal = signal;
    report_.maximumDurationUs = maximumDurationUs;
    report_.outputInactive = false;
    report_.lastError = "none";
    ++report_.startCount;
    return true;
}

bool FixtureSession::complete(std::uint32_t durationUs, bool outputInactive) {
    if (report_.state != FixtureState::Running) {
        reject("not_running");
        return false;
    }
    report_.lastDurationUs = durationUs;
    report_.outputInactive = outputInactive;
    ++report_.stopCount;
    if (!outputInactive || durationUs == 0 ||
        report_.maximumDurationUs == 0 ||
        durationUs > report_.maximumDurationUs) {
        report_.state = FixtureState::Fault;
        reject(!outputInactive ? "output_not_inactive" : "duration_out_of_bounds");
        return false;
    }
    report_.state = FixtureState::Complete;
    report_.lastError = "none";
    ++report_.emissionCount;
    return true;
}

const char* FixtureSession::vectorId() const {
    switch (report_.signal) {
        case FixtureSignal::InfraredNec: return kNecVectorId;
        case FixtureSignal::Nrf24Carrier: return kNrf24VectorId;
        case FixtureSignal::Cc1101Ook: return kCc1101OokVectorId;
        case FixtureSignal::Cc1101Fsk: return kCc1101FskVectorId;
        case FixtureSignal::None: return "none";
    }
    return "none";
}

bool FixtureSession::stop(const char* sessionId, bool outputInactive) {
    if (!same(sessionId, sessionId_)) {
        reject("session_mismatch");
        return false;
    }
    if (report_.state == FixtureState::Running ||
        report_.state == FixtureState::Armed) {
        ++report_.stopCount;
    }
    report_.state = outputInactive ? FixtureState::Stopped : FixtureState::Fault;
    report_.outputInactive = outputInactive;
    report_.lastError = outputInactive ? "none" : "output_not_inactive";
    return outputInactive;
}

void FixtureSession::panic(bool outputInactive) {
    if (report_.state == FixtureState::Running ||
        report_.state == FixtureState::Armed) {
        ++report_.stopCount;
    }
    ++report_.panicCount;
    report_.state = outputInactive ? FixtureState::Panicked : FixtureState::Fault;
    report_.outputInactive = outputInactive;
    report_.lastError = outputInactive ? "panic" : "output_not_inactive";
}

bool FixtureSession::service(std::uint32_t nowMs, bool outputInactive) {
    report_.outputInactive = outputInactive;
    if (!outputInactive) {
        report_.state = FixtureState::Fault;
        reject("output_not_inactive");
        return true;
    }
    if (report_.state == FixtureState::Armed &&
        static_cast<std::int32_t>(nowMs - report_.deadlineMs) >= 0) {
        report_.state = FixtureState::Expired;
        ++report_.stopCount;
        reject("session_expired");
        return true;
    }
    return false;
}

}  // namespace leshy::hil::fixture
