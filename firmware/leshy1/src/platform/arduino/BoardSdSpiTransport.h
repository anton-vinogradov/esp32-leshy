#pragma once

#include <cstdint>

#include "storage/SdIdentificationTransport.h"
#include "storage/SdSpiWireCodec.h"

namespace leshy1::platform::arduino {

class BoardSdSpiTransport final : public storage::SdIdentificationTransport,
                                  private storage::SdByteSource {
public:
    static void holdRadioTransmitPathsInactive();

    bool begin();
    void end();
    bool isPhysical() const override { return true; }
    bool exchange(std::uint8_t command, std::uint32_t argument,
                  storage::SdCommandResponse* response) override;
    bool readSingleBlock(std::uint32_t lba,
                         std::array<std::uint8_t, 512>* data,
                         std::uint16_t* receivedCrc16);

    bool physicalSpiStarted() const { return physicalSpiStarted_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    bool gpio21StableHigh() const { return gpio21StableHigh_; }
    std::uint32_t bytesClocked() const { return bytesClocked_; }
    std::uint16_t exchanges() const { return exchanges_; }
    std::uint8_t dataBlockReads() const { return dataBlockReads_; }
    storage::SdWireStatus lastWireStatus() const { return lastWireStatus_; }

private:
    bool readByte(std::uint8_t* value) override;
    std::uint8_t transfer(std::uint8_t value);
    bool guardSharedChipSelect();
    void deselect();

    bool transactionOpen_ = false;
    bool selected_ = false;
    bool physicalSpiStarted_ = false;
    bool cleanupComplete_ = false;
    bool gpio21StableHigh_ = true;
    bool identificationComplete_ = false;
    std::uint32_t bytesClocked_ = 0;
    std::uint16_t exchanges_ = 0;
    std::uint8_t dataBlockReads_ = 0;
    storage::SdWireStatus lastWireStatus_ = storage::SdWireStatus::Valid;
};

}  // namespace leshy1::platform::arduino
