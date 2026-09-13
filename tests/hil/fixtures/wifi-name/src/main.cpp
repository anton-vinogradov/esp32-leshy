#include <Arduino.h>
#include <esp_app_desc.h>
#include <esp_event.h>
#include <esp_mac.h>
#include <esp_netif.h>
#include <esp_task_wdt.h>
#include <esp_wifi.h>
#include <cstdio>
#include <cstring>
#include "NameFixtureSession.h"

namespace {
constexpr char kSchema[] = "leshy.hil.wifi_name_fixture.v1";
constexpr char kVersion[] = "1.0.0-wifi-name-fixture";
constexpr char kName[] = "LESHY-NAME-HIL";
constexpr char kPassword[] = "fixture-only-937146";
constexpr std::uint8_t kChannel = 6;
leshy::hil::NameFixtureSession session;
bool initialized = false, radioStarted = false, watchdogReady = false;
char identity[13]{}, bssid[13]{}, appSha[65]{}, line[180]{};
std::size_t length = 0;
bool overflow = false;
esp_err_t lastError = ESP_OK;
const char* stopReason = "boot";
int8_t power = 0;

void hex(const std::uint8_t* bytes, std::size_t size, char* output) {
    for (std::size_t i = 0; i < size; ++i)
        std::snprintf(output + i * 2U, 3U, "%02x", bytes[i]);
}

void stop(const char* reason) {
    session.stop();
    if (radioStarted) {
        const esp_err_t result = esp_wifi_stop();
        if (result != ESP_OK) { lastError = result; ESP.restart(); return; }
    }
    radioStarted = false;
    power = 0;
    stopReason = reason;
}

void state(const char* kind = "state") {
    Serial.printf("{\"schema\":\"%s\",\"kind\":\"%s\","
                  "\"version\":\"%s\",\"mac\":\"%s\",\"bssid\":\"%s\","
                  "\"app_elf_sha256\":\"%s\",\"active\":%s,"
                  "\"hidden\":%s,\"radio_started\":%s,\"watchdog\":%s,"
                  "\"session\":\"%s\",\"stop_reason\":\"%s\","
                  "\"error\":%d,\"channel\":6,\"ssid\":\"%s\","
                  "\"power_quarter_dbm\":%d,\"limit_ms\":60000}\n",
                  kSchema, kind, kVersion, identity, bssid, appSha,
                  session.active() ? "true" : "false",
                  session.hidden() ? "true" : "false",
                  radioStarted ? "true" : "false",
                  watchdogReady ? "true" : "false", session.token(),
                  stopReason, static_cast<int>(lastError), kName, static_cast<int>(power));
}

bool configure() {
    wifi_config_t config{};
    std::memcpy(config.ap.ssid, kName, sizeof(kName) - 1U);
    config.ap.ssid_len = sizeof(kName) - 1U;
    std::memcpy(config.ap.password, kPassword, sizeof(kPassword) - 1U);
    config.ap.channel = kChannel;
    config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    config.ap.pairwise_cipher = WIFI_CIPHER_TYPE_CCMP;
    config.ap.ssid_hidden = session.hidden();
    config.ap.max_connection = 1;
    config.ap.beacon_interval = 100;
    lastError = esp_wifi_set_config(WIFI_IF_AP, &config);
    return lastError == ESP_OK;
}

bool start() {
    if (!initialized) {
        lastError = esp_netif_init();
        if (lastError != ESP_OK) return false;
        lastError = esp_event_loop_create_default();
        if (lastError != ESP_OK && lastError != ESP_ERR_INVALID_STATE) return false;
        wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
        config.nvs_enable = 0;
        lastError = esp_wifi_init(&config);
        if (lastError != ESP_OK) return false;
        initialized = true;
    }
    lastError = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (lastError != ESP_OK) return false;
    lastError = esp_wifi_set_mode(WIFI_MODE_AP);
    if (lastError != ESP_OK || !configure()) return false;
    lastError = esp_wifi_start();
    if (lastError != ESP_OK) return false;
    radioStarted = true;
    // SDK permits this only after start. Startup uses the PHY default;
    // do not claim minimum power before this successful readback.
    lastError = esp_wifi_set_max_tx_power(8);
    if (lastError != ESP_OK) return false;
    lastError = esp_wifi_get_max_tx_power(&power);
    if (lastError != ESP_OK || power != 8) return false;
    std::uint8_t address[6]{};
    lastError = esp_wifi_get_mac(WIFI_IF_AP, address);
    if (lastError != ESP_OK) return false;
    hex(address, 6U, bssid);
    stopReason = "none";
    return true;
}

void command(char* text) {
    char* context = nullptr;
    const char* name = strtok_r(text, " ", &context);
    if (name == nullptr) return;
    const char* a = strtok_r(nullptr, " ", &context);
    const char* b = strtok_r(nullptr, " ", &context);
    const char* c = strtok_r(nullptr, " ", &context);
    const bool extra = strtok_r(nullptr, " ", &context) != nullptr;
    if (std::strcmp(name, "stop") == 0) { stop("host"); state(); return; }
    if (std::strcmp(name, "state") == 0 && a == nullptr) { state(); return; }
    if (std::strcmp(name, "begin") == 0 && a && b && c && !extra &&
        watchdogReady && digitalRead(0) != LOW &&
        std::strcmp(a, appSha) == 0 && std::strcmp(b, identity) == 0 &&
        session.begin(c, millis())) {
        if (!start()) stop("start_failed");
        state(); return;
    }
    if ((std::strcmp(name, "visible") == 0 || std::strcmp(name, "hidden") == 0) &&
        a && b == nullptr && session.setHidden(a, name[0] == 'h', millis())) {
        if (!configure()) stop("config_failed");
        state(); return;
    }
    state("rejected");
}
}

void setup() {
    // External transmitters/IR/buzzer inactive; no SD/SPI/display operations.
    // Wi-Fi config uses RAM only. The full flash backup covers framework state.
    for (const int pin : {2, 14, 15, 47}) { pinMode(pin, OUTPUT); digitalWrite(pin, LOW); }
    for (const int pin : {4, 5, 10, 21, 48}) { pinMode(pin, OUTPUT); digitalWrite(pin, HIGH); }
    pinMode(0, INPUT_PULLUP);  // BOOT is the independent physical stop.
    std::uint8_t address[6]{};
    esp_read_mac(address, ESP_MAC_WIFI_STA);
    hex(address, 6U, identity);
    hex(esp_app_get_description()->app_elf_sha256, 32U, appSha);
    const esp_task_wdt_config_t watchdog{3000, 0, true};
    esp_err_t result = esp_task_wdt_reconfigure(&watchdog);
    if (result == ESP_ERR_INVALID_STATE) result = esp_task_wdt_init(&watchdog);
    watchdogReady = result == ESP_OK && esp_task_wdt_add(nullptr) == ESP_OK;
    Serial.begin(115200);
}

void loop() {
    if (watchdogReady) esp_task_wdt_reset();
    if (session.expire(millis())) stop("deadline");
    if (digitalRead(0) == LOW && radioStarted) stop("physical");
    // Bounded serial work cannot starve the deadline or physical stop.
    for (unsigned int count = 0; count < 64U && Serial.available(); ++count) {
        const char value = static_cast<char>(Serial.read());
        if (value == '\r') continue;
        if (value == '\n') {
            if (!overflow) { line[length] = '\0'; command(line); }
            else state("rejected");
            length = 0; overflow = false;
        } else if (!overflow && length + 1U < sizeof(line)) line[length++] = value;
        else overflow = true;
    }
    // A command processed on the deadline must not leave the radio running.
    if (!session.active() && radioStarted) stop("deadline");
    delay(1);
}
