#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "storage/SdIdentification.h"
#include "kernel/runtime/Resources.h"

namespace leshy1::storage {

struct SdCommandResponse final {
    std::uint8_t r1 = 0xFF;
    std::uint32_t trailing = 0;
    std::array<std::uint8_t, 16> data{};
    std::uint16_t dataCrc16 = 0;
};

class SdIdentificationTransport {
public:
    virtual ~SdIdentificationTransport() = default;
    virtual bool isPhysical() const = 0;
    virtual bool exchange(std::uint8_t command, std::uint32_t argument,
                          SdCommandResponse* response) = 0;
};

enum class SdTransportRunStatus : std::uint8_t {
    Valid,
    InvalidPlan,
    PhysicalTransportRejected,
    PhysicalTargetRequired,
    ReadOnlyContractRequired,
    ResourcesMissing,
    ResourceConflict,
    ExchangeFailed,
    InitTimeout,
    ParseRejected,
};

struct SdTransportRunResult final {
    SdTransportRunStatus status = SdTransportRunStatus::InvalidPlan;
    SdIdentificationStatus parseStatus = SdIdentificationStatus::InvalidPlan;
    SdIdentity identity{};
    std::uint16_t commandsAttempted = 0;
    std::uint16_t commandsCompleted = 0;
    bool physicalTransport = false;
};

struct SdTransportRunPolicy final {
    bool allowPhysical = false;
    bool explicitlySelected = false;
    bool identificationOnly = false;
    kernel::runtime::ResourceMask ownedResources = 0;
    bool conflictingOwner = false;
};

constexpr kernel::runtime::ResourceMask kSdIdentificationResources =
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage) |
    kernel::runtime::resourceMask(kernel::runtime::Resource::RadioSpi);

const char* sdTransportRunStatusName(SdTransportRunStatus status);
SdTransportRunResult runSdIdentificationStateMachine(
    const SdReadOnlyPlan& plan, SdIdentificationTransport& transport);
SdTransportRunResult runSdIdentificationStateMachine(
    const SdReadOnlyPlan& plan, SdIdentificationTransport& transport,
    const SdTransportRunPolicy& policy);
bool formatSdTransportRunJson(const SdTransportRunResult& result, char* output,
                              std::size_t capacity);

// A deterministic no-I/O transport used by host and board evidence. It validates
// every command/argument and synthesizes responses; it cannot touch SPI or radio.
class GoldenFakeSdTransport final : public SdIdentificationTransport {
public:
    explicit GoldenFakeSdTransport(std::uint16_t readyAfterAttempts = 3,
                                   std::uint16_t failAtExchange = 0);

    bool isPhysical() const override { return false; }
    bool exchange(std::uint8_t command, std::uint32_t argument,
                  SdCommandResponse* response) override;
    std::uint16_t exchanges() const { return exchanges_; }
    bool sequenceViolation() const { return sequenceViolation_; }

private:
    enum class Phase : std::uint8_t { Cmd0, Cmd8, Cmd55, Acmd41, Cmd58, Cmd10, Cmd9, Done };

    std::uint16_t readyAfterAttempts_ = 3;
    std::uint16_t failAtExchange_ = 0;
    std::uint16_t exchanges_ = 0;
    std::uint16_t initAttempts_ = 0;
    Phase phase_ = Phase::Cmd0;
    bool sequenceViolation_ = false;
};

}  // namespace leshy1::storage
