#include <Arduino.h>
#include <SPI.h>
#include <esp_app_desc.h>
#include <esp_mac.h>
#include <esp_task_wdt.h>
#include <driver/gpio.h>
#include <soc/gpio_struct.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "FixtureSession.h"

#ifndef LESHY_FIXTURE_VERSION
#define LESHY_FIXTURE_VERSION "0.2.0-bounded-signals"
#endif

namespace {

using leshy::hil::fixture::FixtureSession;
using leshy::hil::fixture::FixtureState;
using leshy::hil::fixture::fixtureSignalName;
using leshy::hil::fixture::fixtureStateName;

constexpr int kBuzzerPin = 2;
constexpr int kIrTxPin = 14;
constexpr int kNrfCe1Pin = 15;
constexpr int kNrfCe2Pin = 47;
constexpr int kNrfCe3Pin = 14;
constexpr int kIrRxPin = 21;
constexpr int kRadioMosiPin = 11;
constexpr int kRadioSckPin = 12;
constexpr int kRadioMisoPin = 13;
constexpr int kNrfCsn1Pin = 4;
constexpr int kNrfCsn2Pin = 48;
constexpr int kNrfCsn3Pin = 21;
constexpr int kCc1101CsPin = 5;
constexpr int kSdCsPin = 10;
constexpr std::uint32_t kCarrierHz = 38000;
constexpr std::uint8_t kCarrierResolutionBits = 8;
constexpr std::uint8_t kCarrierDuty = 85;
constexpr std::uint32_t kNecCode = 0xCB34EF10U;
constexpr std::uint32_t kConsoleBaud = 115200;
constexpr std::uint32_t kNrfSpiHz = 8000000;
constexpr std::uint8_t kNrfReadRegister = 0x00;
constexpr std::uint8_t kNrfWriteRegister = 0x20;
constexpr std::uint8_t kNrfRegConfig = 0x00;
constexpr std::uint8_t kNrfRegEnableAutoAck = 0x01;
constexpr std::uint8_t kNrfRegEnableReceiveAddress = 0x02;
constexpr std::uint8_t kNrfRegRfChannel = 0x05;
constexpr std::uint8_t kNrfRegRfSetup = 0x06;
constexpr std::uint8_t kNrfChannel = 42;
constexpr std::uint16_t kNrfFrequencyMhz = 2400U + kNrfChannel;
constexpr std::int8_t kNrfPowerDbm = -18;
constexpr std::uint8_t kNrfMinimumPowerCarrierSetup = 0x90;

FixtureSession session;
char runningAppSha256[65]{};
char runningFixtureId[17]{};
char commandBuffer[224]{};
std::size_t commandLength = 0;
bool carrierReady = false;
bool watchdogReady = false;
bool identityReady = false;
bool nrfBusStarted = false;
bool nrfTransactionOpen = false;
bool nrfCarrierActive = false;
bool nrfPoweredDown = true;
std::uint32_t nrfCarrierStartedUs = 0;

void IRAM_ATTR quiesceFromIsr() {
    GPIO.out_w1tc = (1U << kBuzzerPin) | (1U << kIrTxPin) |
                     (1U << kNrfCe1Pin);
    GPIO.out1_w1tc.val = (1U << (kNrfCe2Pin - 32U));
}

void holdChipSelectsHigh() {
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
    }
}

void holdNrfCeLow() {
    digitalWrite(kNrfCe1Pin, LOW);
    digitalWrite(kNrfCe2Pin, LOW);
    digitalWrite(kNrfCe3Pin, LOW);
}

void beginNrfBus() {
    holdNrfCeLow();
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
        pinMode(pin, OUTPUT);
    }
    SPI.begin(kRadioSckPin, kRadioMisoPin, kRadioMosiPin, -1);
    nrfBusStarted = true;
    SPI.beginTransaction(SPISettings(kNrfSpiHz, MSBFIRST, SPI_MODE0));
    nrfTransactionOpen = true;
}

void endNrfBus() {
    holdNrfCeLow();
    holdChipSelectsHigh();
    if (nrfTransactionOpen) {
        SPI.endTransaction();
        nrfTransactionOpen = false;
    }
    if (nrfBusStarted) {
        SPI.end();
        nrfBusStarted = false;
    }
    pinMode(kNrfCsn3Pin, INPUT);
}

void nrfWriteRegister(std::uint8_t reg, std::uint8_t value) {
    digitalWrite(kNrfCsn1Pin, LOW);
    SPI.transfer(kNrfWriteRegister | (reg & 0x1FU));
    SPI.transfer(value);
    digitalWrite(kNrfCsn1Pin, HIGH);
}

std::uint8_t nrfReadRegister(std::uint8_t reg) {
    digitalWrite(kNrfCsn1Pin, LOW);
    SPI.transfer(kNrfReadRegister | (reg & 0x1FU));
    const std::uint8_t value = SPI.transfer(0xFF);
    digitalWrite(kNrfCsn1Pin, HIGH);
    return value;
}

bool powerDownNrf() {
    holdNrfCeLow();
    const bool startedHere = !nrfBusStarted;
    if (startedHere) beginNrfBus();
    nrfWriteRegister(kNrfRegConfig, 0x00);
    nrfPoweredDown = (nrfReadRegister(kNrfRegConfig) & 0x02U) == 0;
    if (startedHere) endNrfBus();
    return nrfPoweredDown;
}

bool stopNrfCarrier() {
    holdNrfCeLow();
    if (nrfBusStarted) {
        nrfWriteRegister(kNrfRegConfig, 0x00);
        nrfPoweredDown = (nrfReadRegister(kNrfRegConfig) & 0x02U) == 0;
    }
    endNrfBus();
    nrfCarrierActive = false;
    return nrfPoweredDown;
}

void quiesceOutputs() {
    ledcWrite(kIrTxPin, 0);
    digitalWrite(kBuzzerPin, LOW);
    digitalWrite(kIrTxPin, LOW);
    stopNrfCarrier();
}

bool outputsInactive() {
    return gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe3Pin)) == 0;
}

void establishBootInvariant() {
    for (const int pin : {kBuzzerPin, kIrTxPin, kNrfCe1Pin, kNrfCe2Pin}) {
        digitalWrite(pin, LOW);
        pinMode(pin, OUTPUT);
    }
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
        pinMode(pin, OUTPUT);
    }
    carrierReady = ledcAttach(
        kIrTxPin, kCarrierHz, kCarrierResolutionBits);
    ledcWrite(kIrTxPin, 0);
    digitalWrite(kBuzzerPin, LOW);
    holdNrfCeLow();
    holdChipSelectsHigh();
    nrfPoweredDown = powerDownNrf();
    pinMode(kIrRxPin, INPUT);
}

void formatIdentity() {
    const esp_app_desc_t* description = esp_app_get_description();
    bool appIdentityReady = false;
    if (description != nullptr &&
        description->magic_word == ESP_APP_DESC_MAGIC_WORD) {
        constexpr char kHex[] = "0123456789abcdef";
        for (std::size_t index = 0;
             index < sizeof(description->app_elf_sha256); ++index) {
            const std::uint8_t value = description->app_elf_sha256[index];
            runningAppSha256[index * 2U] = kHex[value >> 4U];
            runningAppSha256[index * 2U + 1U] = kHex[value & 0x0FU];
        }
        appIdentityReady = true;
    }
    std::uint8_t mac[6]{};
    const bool macReady = esp_efuse_mac_get_default(mac) == ESP_OK;
    if (macReady) {
        std::snprintf(
            runningFixtureId, sizeof(runningFixtureId),
            "0000%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2],
            mac[3], mac[4], mac[5]);
    }
    identityReady = appIdentityReady && macReady;
}

void emitState(const char* kind) {
    const auto& report = session.report();
    Serial.printf(
        "{\"schema\":\"leshy.hil.fixture.signal.v1\",\"kind\":\"%s\","
        "\"version\":\"%s\",\"role\":\"bounded_signal_fixture\","
        "\"fixture_id\":\"%s\",\"app_elf_sha256\":\"%s\","
        "\"identity_ready\":%s,"
        "\"state\":\"%s\",\"session_id\":\"%s\","
        "\"signal\":\"%s\",\"vector_id\":\"%s\","
        "\"armed\":%s,\"deadline_ms\":%lu,"
        "\"start_count\":%lu,\"stop_count\":%lu,\"panic_count\":%lu,"
        "\"emission_count\":%lu,\"last_duration_us\":%lu,"
        "\"maximum_duration_us\":%lu,"
        "\"ir_tx_gpio\":14,\"ir_rx_gpio\":21,"
        "\"ir_tx_inactive\":%s,\"nrf_ce_inactive\":%s,"
        "\"nrf_powered_down\":%s,\"nrf_carrier_active\":%s,"
        "\"buzzer_inactive\":%s,\"output_inactive\":%s,"
        "\"carrier_hz\":38000,\"maximum_ir_emission_us\":100000,"
        "\"nrf_module_slot\":1,\"nrf_channel\":42,"
        "\"nrf_frequency_mhz\":2442,\"nrf_power_dbm\":-18,"
        "\"nrf_rf_setup\":144,\"nrf_carrier_duration_us\":2000000,"
        "\"maximum_nrf_carrier_us\":2500000,"
        "\"session_lifetime_ms\":5000,"
        "\"fixed_vector_only\":true,\"auto_arm\":false,"
        "\"watchdog_armed\":%s,\"last_error\":\"%s\"}\n",
        kind, LESHY_FIXTURE_VERSION, runningFixtureId, runningAppSha256,
        identityReady ? "true" : "false",
        fixtureStateName(report.state), session.sessionId(),
        fixtureSignalName(report.signal), session.vectorId(),
        report.state == leshy::hil::fixture::FixtureState::Armed
            ? "true" : "false",
        static_cast<unsigned long>(report.deadlineMs),
        static_cast<unsigned long>(report.startCount),
        static_cast<unsigned long>(report.stopCount),
        static_cast<unsigned long>(report.panicCount),
        static_cast<unsigned long>(report.emissionCount),
        static_cast<unsigned long>(report.lastDurationUs),
        static_cast<unsigned long>(report.maximumDurationUs),
        gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0 ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
                gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
                gpio_get_level(static_cast<gpio_num_t>(kNrfCe3Pin)) == 0
            ? "true" : "false",
        nrfPoweredDown ? "true" : "false",
        nrfCarrierActive ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0 ? "true" : "false",
        outputsInactive() ? "true" : "false",
        watchdogReady ? "true" : "false", report.lastError);
}

void emitError(const char* reason) {
    quiesceOutputs();
    session.panic(outputsInactive() && nrfPoweredDown);
    Serial.printf(
        "{\"schema\":\"leshy.hil.fixture.signal.v1\",\"kind\":\"error\","
        "\"reason\":\"%s\",\"state\":\"%s\","
        "\"ir_tx_inactive\":%s,\"nrf_ce_inactive\":%s,"
        "\"nrf_powered_down\":%s,\"buzzer_inactive\":%s}\n",
        reason, fixtureStateName(session.report().state),
        gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0 ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
                gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
                gpio_get_level(static_cast<gpio_num_t>(kNrfCe3Pin)) == 0
            ? "true" : "false",
        nrfPoweredDown ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0
            ? "true" : "false");
}

void mark(std::uint32_t durationUs) {
    ledcWrite(kIrTxPin, kCarrierDuty);
    delayMicroseconds(durationUs);
    ledcWrite(kIrTxPin, 0);
}

void space(std::uint32_t durationUs) {
    ledcWrite(kIrTxPin, 0);
    delayMicroseconds(durationUs);
}

std::uint32_t emitFixedNecVector() {
    const std::uint32_t started = micros();
    mark(9000);
    space(4500);
    for (std::uint8_t bit = 0; bit < 32; ++bit) {
        mark(560);
        space((kNecCode & (1UL << bit)) != 0 ? 1690 : 560);
    }
    mark(560);
    quiesceOutputs();
    return static_cast<std::uint32_t>(micros() - started);
}

bool startFixedNrf24Carrier() {
    if (nrfCarrierActive || nrfBusStarted || !outputsInactive() ||
        !nrfPoweredDown) {
        return false;
    }
    beginNrfBus();
    nrfWriteRegister(kNrfRegConfig, 0x00);
    nrfWriteRegister(kNrfRegEnableAutoAck, 0x00);
    nrfWriteRegister(kNrfRegEnableReceiveAddress, 0x00);
    nrfWriteRegister(kNrfRegRfChannel, kNrfChannel);
    nrfWriteRegister(kNrfRegRfSetup, kNrfMinimumPowerCarrierSetup);
    nrfWriteRegister(kNrfRegConfig, 0x02);
    const bool configured =
        nrfReadRegister(kNrfRegRfChannel) == kNrfChannel &&
        nrfReadRegister(kNrfRegRfSetup) == kNrfMinimumPowerCarrierSetup &&
        (nrfReadRegister(kNrfRegConfig) & 0x03U) == 0x02U;
    if (!configured) {
        stopNrfCarrier();
        return false;
    }
    delayMicroseconds(2000);
    nrfPoweredDown = false;
    nrfCarrierStartedUs = micros();
    digitalWrite(kNrfCe1Pin, HIGH);
    nrfCarrierActive = true;
    return true;
}

bool nrfCarrierOutputValid() {
    return nrfCarrierActive &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 1 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe3Pin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0;
}

void serviceFixtureHardware() {
    if (!nrfCarrierActive) {
        quiesceOutputs();
        session.service(millis(), outputsInactive() && nrfPoweredDown);
        return;
    }
    const std::uint32_t durationUs =
        static_cast<std::uint32_t>(micros() - nrfCarrierStartedUs);
    if (!nrfCarrierOutputValid()) {
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
        return;
    }
    if (durationUs < leshy::hil::fixture::kNrf24CarrierDurationUs) return;
    const bool inactive = stopNrfCarrier() && outputsInactive();
    session.complete(durationUs, inactive);
}

char* nextToken(char** context) {
    return strtok_r(nullptr, " ", context);
}

void handleCommand(char* line) {
    char* context = nullptr;
    const char* command = strtok_r(line, " ", &context);
    if (command == nullptr) return;
    if (std::strcmp(command, "ping") == 0) {
        Serial.println(
            "{\"schema\":\"leshy.boot.v1\",\"kind\":\"pong\","
            "\"fixture\":true}");
        return;
    }
    if (std::strcmp(command, "fixture.identity") == 0) {
        emitState("ready");
        return;
    }
    if (std::strcmp(command, "fixture.state") == 0) {
        serviceFixtureHardware();
        emitState("state");
        return;
    }
    if (std::strcmp(command, "fixture.begin") == 0) {
        const char* sessionId = nextToken(&context);
        const char* appSha256 = nextToken(&context);
        const char* fixtureId = nextToken(&context);
        if (nextToken(&context) != nullptr ||
            !session.begin(sessionId, appSha256, runningAppSha256,
                           fixtureId, runningFixtureId, millis(),
                           outputsInactive() && nrfPoweredDown)) {
            emitError(session.report().lastError);
            return;
        }
        emitState("armed");
        return;
    }
    if (std::strcmp(command, "fixture.ir.nec.once") == 0) {
        const char* sessionId = nextToken(&context);
        const char* vectorId = nextToken(&context);
        if (nextToken(&context) != nullptr || !carrierReady ||
            !session.authorizeNecOnce(sessionId, vectorId, millis())) {
            emitError(carrierReady ? session.report().lastError
                                   : "carrier_unavailable");
            return;
        }
        const std::uint32_t durationUs = emitFixedNecVector();
        if (!session.complete(durationUs, outputsInactive())) {
            emitError(session.report().lastError);
            return;
        }
        emitState("result");
        return;
    }
    if (std::strcmp(command, "fixture.nrf24.carrier.start") == 0) {
        const char* sessionId = nextToken(&context);
        const char* vectorId = nextToken(&context);
        if (nextToken(&context) != nullptr ||
            !session.authorizeNrf24CarrierOnce(
                sessionId, vectorId, millis())) {
            emitError(session.report().lastError);
            return;
        }
        if (!startFixedNrf24Carrier()) {
            emitError("nrf24_carrier_unavailable");
            return;
        }
        emitState("running");
        return;
    }
    if (std::strcmp(command, "fixture.stop") == 0) {
        const char* sessionId = nextToken(&context);
        quiesceOutputs();
        if (nextToken(&context) != nullptr ||
            !session.stop(sessionId, outputsInactive() && nrfPoweredDown)) {
            emitError(session.report().lastError);
            return;
        }
        emitState("state");
        return;
    }
    if (std::strcmp(command, "fixture.panic") == 0) {
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
        emitState("state");
        return;
    }
    emitError("unknown_command");
}

void pollConsole() {
    while (Serial.available() > 0) {
        const char value = static_cast<char>(Serial.read());
        if (value == '\r') continue;
        if (value == '\n') {
            commandBuffer[commandLength] = '\0';
            handleCommand(commandBuffer);
            commandLength = 0;
        } else if (commandLength + 1U < sizeof(commandBuffer)) {
            commandBuffer[commandLength++] = value;
        } else {
            commandLength = 0;
            emitError("command_too_long");
        }
    }
}

}  // namespace

extern "C" void IRAM_ATTR esp_task_wdt_isr_user_handler() {
    quiesceFromIsr();
}

void setup() {
    establishBootInvariant();
    formatIdentity();
    Serial.begin(kConsoleBaud);
    const esp_err_t watchdogStatus = esp_task_wdt_status(nullptr);
    watchdogReady = watchdogStatus == ESP_OK ||
        (watchdogStatus == ESP_ERR_NOT_FOUND &&
         esp_task_wdt_add(nullptr) == ESP_OK);
    if (watchdogReady) watchdogReady = esp_task_wdt_reset() == ESP_OK;
    if (!carrierReady || !watchdogReady || !identityReady || !nrfPoweredDown ||
        !outputsInactive()) {
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
    }
    delay(20);
    emitState("ready");
}

void loop() {
    pollConsole();
    serviceFixtureHardware();
    if (watchdogReady && esp_task_wdt_reset() != ESP_OK) {
        watchdogReady = false;
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
    }
    delay(1);
}
