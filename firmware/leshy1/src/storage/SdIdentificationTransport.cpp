#include "SdIdentificationTransport.h"

#include <cstdio>

namespace leshy1::storage {
namespace {

constexpr std::uint32_t kCmd8Argument = 0x000001AAU;
constexpr std::uint32_t kAcmd41Argument = 0x40000000U;

bool execute(SdIdentificationTransport& transport, std::uint8_t command,
             std::uint32_t argument, SdCommandResponse* response,
             SdTransportRunResult* result) {
    ++result->commandsAttempted;
    if (!transport.exchange(command, argument, response)) return false;
    ++result->commandsCompleted;
    return true;
}

}  // namespace

const char* sdTransportRunStatusName(SdTransportRunStatus status) {
    switch (status) {
        case SdTransportRunStatus::Valid: return "valid";
        case SdTransportRunStatus::InvalidPlan: return "invalid_plan";
        case SdTransportRunStatus::PhysicalTransportRejected:
            return "physical_transport_rejected";
        case SdTransportRunStatus::PhysicalTargetRequired:
            return "physical_target_required";
        case SdTransportRunStatus::ReadOnlyContractRequired:
            return "read_only_contract_required";
        case SdTransportRunStatus::ResourcesMissing: return "resources_missing";
        case SdTransportRunStatus::ResourceConflict: return "resource_conflict";
        case SdTransportRunStatus::ExchangeFailed: return "exchange_failed";
        case SdTransportRunStatus::InitTimeout: return "init_timeout";
        case SdTransportRunStatus::ParseRejected: return "parse_rejected";
    }
    return "exchange_failed";
}

SdTransportRunResult runSdIdentificationStateMachine(
    const SdReadOnlyPlan& plan, SdIdentificationTransport& transport) {
    return runSdIdentificationStateMachine(plan, transport, {});
}

SdTransportRunResult runSdIdentificationStateMachine(
    const SdReadOnlyPlan& plan, SdIdentificationTransport& transport,
    const SdTransportRunPolicy& policy) {
    SdTransportRunResult result;
    if (validateSdIdentificationPlan(plan) != SdReadOnlyPlanStatus::Valid) return result;
    result.physicalTransport = transport.isPhysical();
    if (result.physicalTransport) {
        if (!policy.allowPhysical) {
            result.status = SdTransportRunStatus::PhysicalTransportRejected;
            return result;
        }
        if (!policy.explicitlySelected) {
            result.status = SdTransportRunStatus::PhysicalTargetRequired;
            return result;
        }
        if (!policy.identificationOnly) {
            result.status = SdTransportRunStatus::ReadOnlyContractRequired;
            return result;
        }
        if ((policy.ownedResources & kSdIdentificationResources) !=
            kSdIdentificationResources) {
            result.status = SdTransportRunStatus::ResourcesMissing;
            return result;
        }
        if (policy.conflictingOwner) {
            result.status = SdTransportRunStatus::ResourceConflict;
            return result;
        }
    }

    SdIdentificationTranscript transcript;
    SdCommandResponse response;
    if (!execute(transport, 0, 0, &response, &result)) {
        result.status = SdTransportRunStatus::ExchangeFailed;
        return result;
    }
    transcript.cmd0R1 = response.r1;
    if (!execute(transport, 8, kCmd8Argument, &response, &result)) {
        result.status = SdTransportRunStatus::ExchangeFailed;
        return result;
    }
    transcript.cmd8R1 = response.r1;
    transcript.cmd8Echo = response.trailing;

    bool ready = false;
    for (std::uint16_t attempt = 1; attempt <= plan.maxInitAttempts; ++attempt) {
        if (!execute(transport, 55, 0, &response, &result)) {
            result.status = SdTransportRunStatus::ExchangeFailed;
            return result;
        }
        transcript.cmd55R1 = response.r1;
        if (!execute(transport, 41, kAcmd41Argument, &response, &result)) {
            result.status = SdTransportRunStatus::ExchangeFailed;
            return result;
        }
        transcript.acmd41R1 = response.r1;
        transcript.initAttempts = attempt;
        if (response.r1 == 0x00) {
            ready = true;
            break;
        }
    }
    if (!ready) {
        result.status = SdTransportRunStatus::InitTimeout;
        return result;
    }

    if (!execute(transport, 58, 0, &response, &result)) {
        result.status = SdTransportRunStatus::ExchangeFailed;
        return result;
    }
    transcript.cmd58R1 = response.r1;
    transcript.ocr = response.trailing;
    if (!execute(transport, 10, 0, &response, &result)) {
        result.status = SdTransportRunStatus::ExchangeFailed;
        return result;
    }
    transcript.cmd10R1 = response.r1;
    transcript.cid = response.data;
    transcript.cidCrc16 = response.dataCrc16;
    if (!execute(transport, 9, 0, &response, &result)) {
        result.status = SdTransportRunStatus::ExchangeFailed;
        return result;
    }
    transcript.cmd9R1 = response.r1;
    transcript.csd = response.data;
    transcript.csdCrc16 = response.dataCrc16;

    result.parseStatus = parseSdIdentification(plan, transcript, &result.identity);
    result.status = result.parseStatus == SdIdentificationStatus::Valid
                        ? SdTransportRunStatus::Valid
                        : SdTransportRunStatus::ParseRejected;
    return result;
}

bool formatSdTransportRunJson(const SdTransportRunResult& result, char* output,
                              std::size_t capacity) {
    if (output == nullptr || capacity == 0 || result.status != SdTransportRunStatus::Valid ||
        result.parseStatus != SdIdentificationStatus::Valid) {
        if (output != nullptr && capacity > 0) output[0] = '\0';
        return false;
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.storage.sd.transport.v1\",\"kind\":\"result\","
        "\"status\":\"valid\",\"transport\":\"%s\","
        "\"physical_spi_executed\":%s,\"shared_spi_touched\":%s,"
        "\"commands_attempted\":%u,"
        "\"commands_completed\":%u,\"init_attempts\":%u,"
        "\"capacity_bytes\":%llu,\"write_commands\":false,"
        "\"radio_touched\":false}",
        result.physicalTransport ? "physical_spi" : "golden_fake",
        result.physicalTransport ? "true" : "false",
        result.physicalTransport ? "true" : "false",
        static_cast<unsigned>(result.commandsAttempted),
        static_cast<unsigned>(result.commandsCompleted),
        static_cast<unsigned>(result.identity.initAttempts),
        static_cast<unsigned long long>(result.identity.capacityBytes));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

GoldenFakeSdTransport::GoldenFakeSdTransport(std::uint16_t readyAfterAttempts,
                                             std::uint16_t failAtExchange)
    : readyAfterAttempts_(readyAfterAttempts), failAtExchange_(failAtExchange) {}

bool GoldenFakeSdTransport::exchange(std::uint8_t command, std::uint32_t argument,
                                     SdCommandResponse* response) {
    ++exchanges_;
    if (response == nullptr ||
        (failAtExchange_ != 0 && exchanges_ == failAtExchange_)) return false;
    *response = {};
    bool valid = false;
    switch (phase_) {
        case Phase::Cmd0:
            valid = command == 0 && argument == 0;
            response->r1 = 0x01;
            phase_ = Phase::Cmd8;
            break;
        case Phase::Cmd8:
            valid = command == 8 && argument == kCmd8Argument;
            response->r1 = 0x01;
            response->trailing = kCmd8Argument;
            phase_ = Phase::Cmd55;
            break;
        case Phase::Cmd55:
            valid = command == 55 && argument == 0;
            response->r1 = 0x01;
            phase_ = Phase::Acmd41;
            break;
        case Phase::Acmd41:
            valid = command == 41 && argument == kAcmd41Argument;
            ++initAttempts_;
            response->r1 = initAttempts_ >= readyAfterAttempts_ ? 0x00 : 0x01;
            phase_ = response->r1 == 0x00 ? Phase::Cmd58 : Phase::Cmd55;
            break;
        case Phase::Cmd58:
            valid = command == 58 && argument == 0;
            response->r1 = 0x00;
            response->trailing = goldenSdIdentificationTranscript().ocr;
            phase_ = Phase::Cmd10;
            break;
        case Phase::Cmd10: {
            valid = command == 10 && argument == 0;
            const SdIdentificationTranscript golden = goldenSdIdentificationTranscript();
            response->r1 = 0x00;
            response->data = golden.cid;
            response->dataCrc16 = golden.cidCrc16;
            phase_ = Phase::Cmd9;
            break;
        }
        case Phase::Cmd9: {
            valid = command == 9 && argument == 0;
            const SdIdentificationTranscript golden = goldenSdIdentificationTranscript();
            response->r1 = 0x00;
            response->data = golden.csd;
            response->dataCrc16 = golden.csdCrc16;
            phase_ = Phase::Done;
            break;
        }
        case Phase::Done: valid = false; break;
    }
    if (!valid) sequenceViolation_ = true;
    return valid;
}

}  // namespace leshy1::storage
