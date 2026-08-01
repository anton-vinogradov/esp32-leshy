#include "OtaManager.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Update.h>
#include <time.h>
#include <string.h>
#include "esp_wifi.h"
#include "esp_ota_ops.h"
#include "mbedtls/sha256.h"

#include "../scan/ScanEngine.h"
#include "../net/NetManager.h"

// Mozilla root bundle embedded by arduino-esp32 (covers api.github.com and the
// *.githubusercontent.com download host the release URL redirects to).
extern const uint8_t rootca_crt_bundle_start[] asm("_binary_x509_crt_bundle_start");
extern const uint8_t rootca_crt_bundle_end[]   asm("_binary_x509_crt_bundle_end");

static const char* API =
    "https://api.github.com/repos/anton-vinogradov/esp32-leshy/releases/latest";

static void parseVer(const char* v, int o[3]) {
    o[0] = o[1] = o[2] = 0;
    if (*v == 'v' || *v == 'V') v++;
    sscanf(v, "%d.%d.%d", &o[0], &o[1], &o[2]);
}
static bool semverNewer(const char* remote, const char* local) {
    int r[3], l[3];
    parseVer(remote, r); parseVer(local, l);
    for (int i = 0; i < 3; i++) if (r[i] != l[i]) return r[i] > l[i];
    return false;
}

void OtaManager::begin(ScanEngine* eng, NetManager* net) { eng_ = eng; net_ = net; }

void OtaManager::markHealthy() {
    if (healthy_) return;
    healthy_ = true;
    const esp_partition_t* run = esp_ota_get_running_partition();
    esp_ota_img_states_t s;
    if (run && esp_ota_get_state_partition(run, &s) == ESP_OK && s == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();
        Serial.println("[OTA] running image confirmed valid (rollback cancelled)");
    }
}

bool OtaManager::syncTime() {
    if (time(nullptr) > 1700000000) return true;
    configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
    for (int i = 0; i < 160 && time(nullptr) < 1700000000; i++) vTaskDelay(pdMS_TO_TICKS(100));
    bool ok = time(nullptr) > 1700000000;
    Serial.printf("[OTA] time sync %s (epoch=%ld)\n", ok ? "ok" : "FAILED", (long)time(nullptr));
    return ok;
}

bool OtaManager::prep() {
    if (eng_) eng_->pause();
    vTaskDelay(pdMS_TO_TICKS(150));       // let any in-flight scan finish
    esp_wifi_set_promiscuous(false);      // reveal may have left it on
    WiFi.mode(WIFI_STA);
    if (net_ && !net_->connected()) net_->connect();
    return net_ && net_->connected();
}

void OtaManager::doCheck() {
    set(CHECKING);
    if (!prep())     { fail(E_NONET); return; }
    if (!syncTime()) { fail(E_TIME);  return; }

    WiFiClientSecure c;
    c.setCACertBundle(rootca_crt_bundle_start, rootca_crt_bundle_end - rootca_crt_bundle_start);
    c.setTimeout(15000);
    HTTPClient http;
    if (!http.begin(c, API)) { fail(E_API); return; }
    http.addHeader("User-Agent", "ESP32-Leshy");           // GitHub requires a User-Agent
    http.addHeader("Accept", "application/vnd.github+json");
    http.addHeader("X-GitHub-Api-Version", "2022-11-28");
    int code = http.GET();
    if (code == 404)                 { http.end(); fail(E_NORELEASE); return; }
    if (code == 403 || code == 429)  { http.end(); fail(E_RATELIMIT); return; }
    if (code != 200)                 { http.end(); fail(E_API); return; }

    JsonDocument filter;                                    // parse only what we need, from the stream
    filter["tag_name"] = true;
    filter["assets"][0]["name"] = true;
    filter["assets"][0]["browser_download_url"] = true;
    filter["assets"][0]["size"] = true;
    filter["assets"][0]["digest"] = true;
    JsonDocument doc;
    DeserializationError e = deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
    http.end();
    if (e) { fail(E_PARSE); return; }

    strlcpy(latest_, doc["tag_name"] | "", sizeof(latest_));
    url_[0] = digest_[0] = 0; size_ = 0;
    for (JsonObject a : doc["assets"].as<JsonArray>()) {
        if (strcmp(a["name"] | "", "firmware.bin") == 0) {
            strlcpy(url_,    a["browser_download_url"] | "", sizeof(url_));
            strlcpy(digest_, a["digest"] | "",              sizeof(digest_));
            size_ = a["size"] | 0;
            break;
        }
    }
    if (!url_[0]) { fail(E_NOASSET); return; }
    busy_ = false;
    set(semverNewer(latest_, LESHY_FW_VERSION) ? AVAILABLE : UPTODATE);
    Serial.printf("[OTA] latest=%s current=%s -> %s\n", latest_, LESHY_FW_VERSION,
                  phase_ == AVAILABLE ? "update available" : "up to date");
}

void OtaManager::doDownload() {
    set(DOWNLOADING); pct_ = 0;
    if (!prep()) { fail(E_NONET); return; }

    WiFiClientSecure c;
    c.setCACertBundle(rootca_crt_bundle_start, rootca_crt_bundle_end - rootca_crt_bundle_start);
    c.setTimeout(20000);
    HTTPClient http;
    if (!http.begin(c, url_)) { fail(E_HTTP); return; }
    http.addHeader("User-Agent", "ESP32-Leshy");
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS); // github.com -> *.githubusercontent.com
    int code = http.GET();
    if (code != 200) { http.end(); fail(E_HTTP); return; }

    int total = http.getSize();
    if (total <= 0) total = (int)size_;
    if (total <= 0) { http.end(); fail(E_SHORT); return; }
    if (!Update.begin(total)) { http.end(); fail(E_BEGIN); return; }

    bool useSha = strncmp(digest_, "sha256:", 7) == 0;
    mbedtls_sha256_context sha;
    if (useSha) { mbedtls_sha256_init(&sha); mbedtls_sha256_starts(&sha, 0); }

    WiFiClient* st = http.getStreamPtr();
    uint8_t buf[1460];
    int written = 0, lastYield = 0;
    uint32_t lastRx = millis();
    while (written < total) {
        size_t avail = st->available();
        if (avail) {
            int n = st->readBytes(buf, avail > sizeof(buf) ? sizeof(buf) : avail);
            if (n > 0) {
                if (Update.write(buf, n) != (size_t)n) { Update.abort(); http.end(); if (useSha) mbedtls_sha256_free(&sha); fail(E_WRITE); return; }
                if (useSha) mbedtls_sha256_update(&sha, buf, n);
                written += n; lastRx = millis();
                int p = (int)((int64_t)written * 100 / total);
                if (p != pct_) { pct_ = p; gen_ = gen_ + 1; }
            }
        } else {
            if (!st->connected() && st->available() == 0) break;   // FIN with buffer drained
            if (millis() - lastRx > 20000) { Update.abort(); http.end(); if (useSha) mbedtls_sha256_free(&sha); fail(E_SHORT); return; }
            vTaskDelay(pdMS_TO_TICKS(5));
        }
        if (written - lastYield >= 16384) { lastYield = written; vTaskDelay(1); }  // feed the watchdog
    }
    http.end();
    if (written != total) { Update.abort(); if (useSha) mbedtls_sha256_free(&sha); fail(E_SHORT); return; }

    if (useSha) {
        uint8_t out[32]; mbedtls_sha256_finish(&sha, out); mbedtls_sha256_free(&sha);
        char hex[65]; for (int i = 0; i < 32; i++) sprintf(hex + i * 2, "%02x", out[i]);
        if (strcasecmp(hex, digest_ + 7) != 0) { Update.abort(); fail(E_HASH); return; }
    }
    if (!Update.end(true)) { fail(E_END); return; }

    Serial.println("[OTA] update written & verified — rebooting");
    set(DONE);
    vTaskDelay(pdMS_TO_TICKS(1400));
    ESP.restart();
}

void OtaManager::checkTask(void* p) { ((OtaManager*)p)->doCheck();    vTaskDelete(nullptr); }
void OtaManager::updTask(void* p)   { ((OtaManager*)p)->doDownload(); vTaskDelete(nullptr); }

void OtaManager::startCheck() {
    if (busy_) return;
    busy_ = true; err_ = E_NONE;
    xTaskCreatePinnedToCore(checkTask, "otachk", 16384, this, 2, nullptr, 1);
}
void OtaManager::startUpdate() {
    if (busy_ || phase_ != AVAILABLE) return;
    busy_ = true; err_ = E_NONE;
    xTaskCreatePinnedToCore(updTask, "otaupd", 16384, this, 2, nullptr, 1);
}
