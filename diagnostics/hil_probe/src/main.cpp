#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>

#include <esp_chip_info.h>
#include <esp_partition.h>
#include <esp_rom_spiflash.h>
#include <esp_system.h>

#include "ProbeLogic.h"

namespace {

constexpr uint32_t kConsoleBaud = 115200;
constexpr uint32_t kGpsBaud = 9600;
constexpr uint32_t kGpsListenMs = 10000;
constexpr uint32_t kGpsPreflightMs = 2200;
constexpr uint32_t kRadioSpiHz = 1000000;

constexpr int kI2cSda = 8;
constexpr int kI2cScl = 9;
constexpr int kRadioMosi = 11;
constexpr int kRadioSck = 12;
constexpr int kRadioMiso = 13;
constexpr int kNrfCe[] = {15, 47, 14};
constexpr int kNrfCsn[] = {4, 48, 21};
constexpr int kSdCs = 10;
constexpr int kCcCs = 5;
constexpr int kCcGdo0 = 6;
constexpr int kCcGdo2 = 3;
constexpr int kContestedPins[] = {0, 2, 3, 5, 6, 21};

constexpr uint8_t kNrfReadRegister = 0x00;
constexpr uint8_t kNrfRegConfig = 0x00;
constexpr uint8_t kNrfRegRfChannel = 0x05;
constexpr uint8_t kNrfRegRfSetup = 0x06;
constexpr uint8_t kNrfRegFeature = 0x1D;
constexpr uint8_t kCcReadPartNumber = 0xF0;
constexpr uint8_t kCcReadVersion = 0xF1;

constexpr char kSchema[] = "leshy.hil.v1";
constexpr char kRfConfirmation[] = "rf-read shield-no-gps-no-pn532";

char usbCommand[96] = {};
char uartCommand[96] = {};
size_t usbCommandLength = 0;
size_t uartCommandLength = 0;

void broadcast(const char* line) {
    Serial.println(line);
    Serial0.println(line);
}

template <typename... Args>
void emit(const char* format, Args... args) {
    char line[640];
    snprintf(line, sizeof(line), format, args...);
    broadcast(line);
}

void holdTransmitPathsInactive() {
    // NRF CE is the only direct enable path. LOW is safe for both NRF and the IR
    // transmitter sharing GPIO14. No code in this image ever drives CE HIGH.
    for (int pin : kNrfCe) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }

    for (int pin : kContestedPins) pinMode(pin, INPUT);
    pinMode(kRadioMosi, INPUT);
    pinMode(kRadioMiso, INPUT);
    pinMode(kRadioSck, INPUT);
    pinMode(kNrfCsn[0], INPUT);
    pinMode(kNrfCsn[1], INPUT);
    pinMode(kNrfCsn[2], INPUT);
    pinMode(kSdCs, INPUT);
    pinMode(kCcGdo0, INPUT);
    pinMode(kCcGdo2, INPUT);
}

const char* resetReasonName(esp_reset_reason_t reason) {
    switch (reason) {
        case ESP_RST_POWERON: return "power_on";
        case ESP_RST_EXT: return "external";
        case ESP_RST_SW: return "software";
        case ESP_RST_PANIC: return "panic";
        case ESP_RST_INT_WDT: return "interrupt_watchdog";
        case ESP_RST_TASK_WDT: return "task_watchdog";
        case ESP_RST_WDT: return "watchdog";
        case ESP_RST_DEEPSLEEP: return "deep_sleep";
        case ESP_RST_BROWNOUT: return "brownout";
        case ESP_RST_SDIO: return "sdio";
        case ESP_RST_USB: return "usb";
        case ESP_RST_JTAG: return "jtag";
        case ESP_RST_EFUSE: return "efuse_error";
        case ESP_RST_PWR_GLITCH: return "power_glitch";
        case ESP_RST_CPU_LOCKUP: return "cpu_lockup";
        default: return "unknown";
    }
}

void emitInventory() {
    esp_chip_info_t chip = {};
    esp_chip_info(&chip);
    const uint64_t mac = ESP.getEfuseMac();
    const uint32_t flashDeviceId = g_rom_flashchip.device_id;
    const uint32_t flashBytes = ESP.getFlashChipSize();
    const uint32_t psramBytes = ESP.getPsramSize();
    const esp_reset_reason_t resetReason = esp_reset_reason();

    emit("{\"schema\":\"%s\",\"test\":\"HW-T01\",\"kind\":\"chip\","
         "\"probe_version\":\"%s\",\"model\":\"%s\",\"revision\":%u,"
         "\"cores\":%u,\"features\":%lu,\"efuse_mac\":\"%04lX%08lX\"}",
         kSchema, LESHY_HIL_PROBE_VERSION, ESP.getChipModel(),
         static_cast<unsigned>(chip.revision), static_cast<unsigned>(chip.cores),
         static_cast<unsigned long>(chip.features),
         static_cast<unsigned long>(mac >> 32), static_cast<unsigned long>(mac));

    emit("{\"schema\":\"%s\",\"test\":\"HW-T01\",\"kind\":\"memory\","
         "\"flash_device_id\":\"0x%08lX\",\"flash_bytes\":%lu,"
         "\"flash_speed_hz\":%lu,\"psram_found\":%s,\"psram_bytes\":%lu,"
         "\"heap_total\":%lu,\"heap_free\":%lu,\"heap_min_free\":%lu}",
         kSchema, static_cast<unsigned long>(flashDeviceId),
         static_cast<unsigned long>(flashBytes),
         static_cast<unsigned long>(ESP.getFlashChipSpeed()),
         psramFound() ? "true" : "false", static_cast<unsigned long>(psramBytes),
         static_cast<unsigned long>(ESP.getHeapSize()),
         static_cast<unsigned long>(ESP.getFreeHeap()),
         static_cast<unsigned long>(ESP.getMinFreeHeap()));

    emit("{\"schema\":\"%s\",\"test\":\"HW-T11\",\"kind\":\"boot\","
         "\"reset_reason\":\"%s\",\"reset_reason_code\":%u,"
         "\"idf\":\"%s\",\"arduino\":\"%s\",\"cpu_mhz\":%lu}",
         kSchema, resetReasonName(resetReason), static_cast<unsigned>(resetReason),
         ESP.getSdkVersion(), ESP.getCoreVersion(),
         static_cast<unsigned long>(ESP.getCpuFreqMHz()));

    esp_partition_iterator_t current =
        esp_partition_find(ESP_PARTITION_TYPE_ANY, ESP_PARTITION_SUBTYPE_ANY, nullptr);
    while (current != nullptr) {
        const esp_partition_t* partition = esp_partition_get(current);
        if (partition != nullptr) {
            emit("{\"schema\":\"%s\",\"test\":\"HW-T01\","
                 "\"kind\":\"partition\",\"label\":\"%s\",\"type\":%u,"
                 "\"subtype\":%u,\"address\":%lu,\"size\":%lu}",
                 kSchema, partition->label, static_cast<unsigned>(partition->type),
                 static_cast<unsigned>(partition->subtype),
                 static_cast<unsigned long>(partition->address),
                 static_cast<unsigned long>(partition->size));
        }
        current = esp_partition_next(current);
    }
}

void emitHelp() {
    emit("{\"schema\":\"%s\",\"kind\":\"help\",\"commands\":["
         "\"inventory\",\"i2c-read\",\"gps-listen\","
         "\"rf-read shield-no-gps-no-pn532\",\"help\"],"
         "\"warning\":\"RF read requires physical absence of GPS and PN532; no TX commands exist\"}",
         kSchema);
}

void runI2cReadProbe() {
    Wire.begin(kI2cSda, kI2cScl, 100000);
    Wire.setTimeOut(20);
    unsigned found = 0;

    for (uint8_t address = 0x08; address <= 0x77; ++address) {
        const uint8_t received = Wire.requestFrom(address, static_cast<uint8_t>(1), true);
        if (received == 1U) {
            const int value = Wire.read();
            ++found;
            emit("{\"schema\":\"%s\",\"test\":\"HW-T04\","
                 "\"kind\":\"i2c_read\",\"address\":\"0x%02X\","
                 "\"value\":\"0x%02X\"}",
                 kSchema, address, value & 0xFF);
        }
        delay(1);
    }

    Wire.end();
    pinMode(kI2cSda, INPUT);
    pinMode(kI2cScl, INPUT);
    emit("{\"schema\":\"%s\",\"test\":\"HW-T04\",\"kind\":\"summary\","
         "\"readable_addresses\":%u,\"writes\":0}",
         kSchema, found);
}

struct GpsResult {
    unsigned lines = 0;
    unsigned validNmea = 0;
    unsigned bytes = 0;
};

GpsResult listenForGps(uint32_t durationMs) {
    GpsResult result;
    char line[128] = {};
    size_t length = 0;

    pinMode(kCcCs, INPUT);
    Serial1.begin(kGpsBaud, SERIAL_8N1, kCcCs, -1);
    const uint32_t started = millis();
    while (millis() - started < durationMs) {
        while (Serial1.available() > 0) {
            const char value = static_cast<char>(Serial1.read());
            ++result.bytes;
            if (value == '\n' || value == '\r') {
                if (length > 0) {
                    ++result.lines;
                    if (leshy::hil::validNmeaChecksum(line, length)) ++result.validNmea;
                    length = 0;
                }
            } else if (length + 1 < sizeof(line)) {
                line[length++] = value;
                line[length] = '\0';
            } else {
                length = 0;
            }
        }
        delay(1);
    }
    Serial1.end();
    pinMode(kCcCs, INPUT);
    return result;
}

void runGpsListenProbe() {
    const GpsResult result = listenForGps(kGpsListenMs);
    emit("{\"schema\":\"%s\",\"test\":\"HW-T07\",\"kind\":\"gps_passive\","
         "\"duration_ms\":%lu,\"baud\":%lu,\"bytes\":%u,\"lines\":%u,"
         "\"valid_nmea\":%u,\"gpio5_writes\":0,\"detected\":%s}",
         kSchema, static_cast<unsigned long>(kGpsListenMs),
         static_cast<unsigned long>(kGpsBaud), result.bytes, result.lines,
         result.validNmea, result.validNmea > 0 ? "true" : "false");
}

uint8_t readNrfRegister(int chipSelect, uint8_t reg, uint8_t* status) {
    digitalWrite(chipSelect, LOW);
    *status = SPI.transfer(kNrfReadRegister | (reg & 0x1FU));
    const uint8_t value = SPI.transfer(0xFF);
    digitalWrite(chipSelect, HIGH);
    return value;
}

leshy::hil::NrfObservation readNrf(int chipSelect) {
    leshy::hil::NrfObservation observation = {};
    observation.config = readNrfRegister(chipSelect, kNrfRegConfig, &observation.status);
    uint8_t ignored = 0;
    observation.channel = readNrfRegister(chipSelect, kNrfRegRfChannel, &ignored);
    observation.rfSetup = readNrfRegister(chipSelect, kNrfRegRfSetup, &ignored);
    observation.feature = readNrfRegister(chipSelect, kNrfRegFeature, &ignored);
    return observation;
}

bool waitForCcReady() {
    const uint32_t started = micros();
    while (digitalRead(kRadioMiso) != LOW) {
        if (micros() - started > 2000U) return false;
    }
    return true;
}

bool readCcStatusRegister(uint8_t command, uint8_t* chipStatus, uint8_t* value) {
    digitalWrite(kCcCs, LOW);
    if (!waitForCcReady()) {
        digitalWrite(kCcCs, HIGH);
        return false;
    }
    *chipStatus = SPI.transfer(command);
    *value = SPI.transfer(0xFF);
    digitalWrite(kCcCs, HIGH);
    return true;
}

void emitNrf(unsigned slot, const leshy::hil::NrfObservation& value) {
    emit("{\"schema\":\"%s\",\"test\":\"HW-T06\",\"kind\":\"nrf_read\","
         "\"slot\":%u,\"status\":\"0x%02X\",\"config\":\"0x%02X\","
         "\"channel\":%u,\"rf_setup\":\"0x%02X\",\"feature\":\"0x%02X\","
         "\"state\":\"%s\",\"ce_high_events\":0}",
         kSchema, slot, value.status, value.config, value.channel, value.rfSetup,
         value.feature, leshy::hil::plausibleNrfObservation(value) ? "detected" : "unknown");
}

void runRfReadProbe() {
    const GpsResult preflight = listenForGps(kGpsPreflightMs);
    if (preflight.validNmea > 0) {
        emit("{\"schema\":\"%s\",\"test\":\"HW-T06\",\"kind\":\"aborted\","
             "\"reason\":\"gps_detected_on_gpio5\",\"valid_nmea\":%u}",
             kSchema, preflight.validNmea);
        return;
    }

    // The operator confirmation guarantees that GPIO5 is not driven by GPS and no
    // PN532 is attached. Slot 3 is intentionally not selected: its CSN shares
    // GPIO21 with the IR receiver output and remains gated by HW-T08.
    pinMode(kNrfCsn[0], OUTPUT);
    pinMode(kNrfCsn[1], OUTPUT);
    pinMode(kSdCs, OUTPUT);
    pinMode(kCcCs, OUTPUT);
    digitalWrite(kNrfCsn[0], HIGH);
    digitalWrite(kNrfCsn[1], HIGH);
    digitalWrite(kSdCs, HIGH);
    digitalWrite(kCcCs, HIGH);
    pinMode(kNrfCsn[2], INPUT);
    for (int pin : kNrfCe) digitalWrite(pin, LOW);

    SPI.begin(kRadioSck, kRadioMiso, kRadioMosi, -1);
    SPI.beginTransaction(SPISettings(kRadioSpiHz, MSBFIRST, SPI_MODE0));

    emitNrf(1, readNrf(kNrfCsn[0]));
    emitNrf(2, readNrf(kNrfCsn[1]));
    emit("{\"schema\":\"%s\",\"test\":\"HW-T08\",\"kind\":\"nrf_read\","
         "\"slot\":3,\"state\":\"unknown\","
         "\"reason\":\"gpio21_ir_receiver_contention_not_characterized\"}",
         kSchema);

    uint8_t partStatus = 0xFF;
    uint8_t versionStatus = 0xFF;
    uint8_t partNumber = 0xFF;
    uint8_t version = 0xFF;
    const bool partRead =
        readCcStatusRegister(kCcReadPartNumber, &partStatus, &partNumber);
    const bool versionRead =
        readCcStatusRegister(kCcReadVersion, &versionStatus, &version);
    const bool plausible = partRead && versionRead &&
        leshy::hil::plausibleCcObservation(versionStatus, partNumber, version);
    emit("{\"schema\":\"%s\",\"test\":\"HW-T06\",\"kind\":\"cc1101_read\","
         "\"partnum\":\"0x%02X\",\"version\":\"0x%02X\","
         "\"status\":\"0x%02X\",\"ready\":%s,\"state\":\"%s\","
         "\"command_strobes\":0}",
         kSchema, partNumber, version, versionStatus,
         (partRead && versionRead) ? "true" : "false", plausible ? "detected" : "unknown");

    SPI.endTransaction();
    SPI.end();
    pinMode(kRadioMosi, INPUT);
    pinMode(kRadioMiso, INPUT);
    pinMode(kRadioSck, INPUT);
    for (int pin : kNrfCe) digitalWrite(pin, LOW);
    emit("{\"schema\":\"%s\",\"test\":\"HW-T06\",\"kind\":\"summary\","
         "\"rf_tx_commands\":0,\"ir_tx_events\":0,\"nrf_ce_high_events\":0}",
         kSchema);
}

void handleCommand(const char* command, const char* source) {
    emit("{\"schema\":\"%s\",\"test\":\"HW-T11\",\"kind\":\"command\","
         "\"source\":\"%s\"}", kSchema, source);

    if (strcmp(command, "inventory") == 0) {
        emitInventory();
    } else if (strcmp(command, "i2c-read") == 0) {
        runI2cReadProbe();
    } else if (strcmp(command, "gps-listen") == 0) {
        runGpsListenProbe();
    } else if (strcmp(command, kRfConfirmation) == 0) {
        runRfReadProbe();
    } else if (strcmp(command, "help") == 0 || command[0] == '\0') {
        emitHelp();
    } else {
        emit("{\"schema\":\"%s\",\"kind\":\"error\","
             "\"reason\":\"unknown_command\"}", kSchema);
    }
}

void pollConsole(Stream& stream, const char* source, char* command,
                 size_t* commandLength) {
    while (stream.available() > 0) {
        const char value = static_cast<char>(stream.read());
        if (value == '\n' || value == '\r') {
            if (*commandLength > 0) {
                command[*commandLength] = '\0';
                handleCommand(command, source);
                *commandLength = 0;
            }
        } else if (value >= 0x20 && value <= 0x7E) {
            if (*commandLength + 1 < 96) command[(*commandLength)++] = value;
        }
    }
}

}  // namespace

void setup() {
    holdTransmitPathsInactive();
    Serial0.begin(kConsoleBaud);
    Serial.begin(kConsoleBaud);
    delay(250);

    emit("{\"schema\":\"%s\",\"test\":\"HW-T11\",\"kind\":\"ready\","
         "\"probe_version\":\"%s\",\"baud\":%lu,"
         "\"default_policy\":\"read_only_no_tx\"}",
         kSchema, LESHY_HIL_PROBE_VERSION, static_cast<unsigned long>(kConsoleBaud));
    emitInventory();
    emitHelp();
}

void loop() {
    pollConsole(Serial, "native_usb", usbCommand, &usbCommandLength);
    pollConsole(Serial0, "cp2102_uart0", uartCommand, &uartCommandLength);
    delay(1);
}
