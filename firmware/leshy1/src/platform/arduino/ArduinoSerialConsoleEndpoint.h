#pragma once

#include <HardwareSerial.h>

#include <cstddef>
#include <cstdint>

#include "services/actions/ActionDispatcher.h"
#include "services/serial/SerialConsoleBuffer.h"
#include "services/serial/SerialConsoleContract.h"

namespace leshy1::platform::arduino {

struct ArduinoSerialConsoleStats final {
    bool configured = false;
    bool active = false;
    bool cleanupComplete = true;
    std::uint32_t bytesReceived = 0U;
    std::uint32_t bytesTransmitted = 0U;
    std::uint32_t droppedBytes = 0U;
    std::size_t bufferedBytes = 0U;
    std::size_t highWaterBytes = 0U;
};

class ArduinoSerialConsoleEndpoint final
    : public services::actions::ActionEndpoint {
public:
    explicit ArduinoSerialConsoleEndpoint(HardwareSerial& serial)
        : serial_(serial) {}

    services::serial::SerialConsolePreflightStatus configure(
        const services::serial::SerialConsoleConfig& config,
        const services::serial::SerialConsoleHardware& hardware);

    bool start(std::uint32_t nowMs) override;
    services::actions::ActionEndpointState tick(
        std::uint32_t nowMs) override;
    void cancel() override;

    bool pop(std::uint8_t* output);
    std::size_t write(const std::uint8_t* data, std::size_t length);
    ArduinoSerialConsoleStats stats() const;
    const services::serial::SerialConsoleConfig& config() const {
        return config_;
    }

private:
    static std::uint32_t arduinoFraming(
        services::serial::SerialConsoleFraming framing);
    void stop();

    HardwareSerial& serial_;
    services::serial::SerialConsoleBuffer buffer_{};
    services::serial::SerialConsoleConfig config_{};
    bool configured_ = false;
    bool active_ = false;
    bool cleanupComplete_ = true;
    std::uint32_t bytesReceived_ = 0U;
    std::uint32_t bytesTransmitted_ = 0U;
};

}  // namespace leshy1::platform::arduino
