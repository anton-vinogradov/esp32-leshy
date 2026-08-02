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

// The download's TLS handshake keeps a full-size mbedTLS record buffer per direction;
// CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN is 16 KB, so each is ~16.9 KB and must be one
// contiguous block, and both are live at once. On a heap fragmented by a BLE session
// the largest free BLOCK — not total free heap — is what decides whether the handshake
// can even start, so gate on that. Below this, say "reboot first" instead of failing
// later with a cryptic TLS "connection refused".
static const size_t OTA_MIN_DL_BLOCK = 2 * (16384 + 2048) + 8192;   // ~44 KB: two record buffers + handshake slack

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
    if (eng_ && !eng_->pauseAndWait()) {  // radio must be free before TLS — don't race the scan task
        Serial.println("[OTA] scan engine did not go idle");
        diag(0, "radio busy (scan)");
        return false;
    }
    esp_wifi_set_promiscuous(false);      // reveal may have left it on
    WiFi.mode(WIFI_STA);
    if (net_ && !net_->connected()) net_->connect();
    if (!(net_ && net_->connected())) {
        char d[48]; snprintf(d, sizeof(d), "wifi not connected (wl=%d)", (int)WiFi.status());
        diag(0, d); return false;      // wl_status is not an HTTP code — keep it in detail
    }
    return true;
}

void OtaManager::doCheck() {
    set(CHECKING);
    Serial.printf("[OTA] check start: free heap=%u largest block=%u\n",
                  (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
    if (!prep())     { fail(E_NONET); return; }                 // prep() already set the detail
    if (!syncTime()) { char d[48]; snprintf(d, sizeof(d), "no NTP time (epoch=%ld)", (long)time(nullptr));
                       diag(0, d); fail(E_TIME); return; }

    WiFiClientSecure c;
    c.setCACertBundle(rootca_crt_bundle_start, rootca_crt_bundle_end - rootca_crt_bundle_start);
    c.setTimeout(15000);
    HTTPClient http;
    if (!http.begin(c, API)) { diag(0, "TLS begin failed"); fail(E_API); return; }
    http.addHeader("User-Agent", "ESP32-Leshy");           // GitHub requires a User-Agent
    http.addHeader("Accept", "application/vnd.github+json");
    http.addHeader("X-GitHub-Api-Version", "2022-11-28");
    int code = http.GET();
    if (code == 404)                 { http.end(); diag(404, "");  fail(E_NORELEASE); return; }  // title/hint already say it
    if (code == 403 || code == 429)  { http.end(); diag(code, ""); fail(E_RATELIMIT); return; }
    if (code != 200) {
        char d[56];
        if (code < 0) snprintf(d, sizeof(d), "conn: %s", http.errorToString(code).c_str());
        else          snprintf(d, sizeof(d), "unexpected HTTP %d", code);
        http.end(); diag(code, d); fail(E_API); return;
    }

    JsonDocument filter;                                    // parse only what we need, from the stream
    filter["tag_name"] = true;
    filter["assets"][0]["name"] = true;
    filter["assets"][0]["browser_download_url"] = true;
    filter["assets"][0]["size"] = true;
    filter["assets"][0]["digest"] = true;
    JsonDocument doc;
    DeserializationError e = deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
    http.end();
    if (e) { diag(200, e.c_str()); fail(E_PARSE); return; }

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
    if (!url_[0]) { diag(200, ""); fail(E_NOASSET); return; }   // title/hint already say "no firmware.bin"
    busy_ = false;
    set(semverNewer(latest_, LESHY_FW_VERSION) ? AVAILABLE : UPTODATE);
    Serial.printf("[OTA] latest=%s current=%s -> %s\n", latest_, LESHY_FW_VERSION,
                  phase_ == AVAILABLE ? "update available" : "up to date");
}

void OtaManager::doDownload() {
    set(DOWNLOADING); pct_ = 0;
    if (!prep()) { fail(E_NONET); return; }   // prep() paused the scan → the BLE stack is now safe to tear down

    // Backstop: BLE is normally freed the moment the update screen opens (gotoOta), which
    // is what keeps the heap unfragmented enough to reach this download. Cover any other
    // path here too — freeing it now still hands back ~70 KB of headroom, and this path
    // always ends in a reboot so it's safe. No-op (returns false) when already released.
    if (eng_ && eng_->releaseBleForOta())
        Serial.printf("[OTA] BLE released at download: free=%u largest=%u\n",
                      (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());

    // Honest gate: if the heap is still too fragmented to fit the two ~16 KB record
    // buffers, tell the user to reboot instead of failing on the TLS handshake.
    unsigned largest = ESP.getMaxAllocHeap();
    if (largest < OTA_MIN_DL_BLOCK) {
        char d[72];
        snprintf(d, sizeof(d), "largest block %uK < %uK needed", largest / 1024,
                 (unsigned)(OTA_MIN_DL_BLOCK / 1024));
        Serial.printf("[OTA] download blocked: %s (free=%u)\n", d, (unsigned)ESP.getFreeHeap());
        diag(0, d); fail(E_NOMEM); return;
    }

    WiFiClientSecure c;
    c.setCACertBundle(rootca_crt_bundle_start, rootca_crt_bundle_end - rootca_crt_bundle_start);
    c.setTimeout(20000);
    HTTPClient http;
    if (!http.begin(c, url_)) { diag(0, "TLS begin failed"); fail(E_HTTP); return; }
    http.addHeader("User-Agent", "ESP32-Leshy");
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS); // github.com -> *.githubusercontent.com
    int code = http.GET();
    if (code != 200) {
        char d[56];
        if (code < 0) snprintf(d, sizeof(d), "conn: %s", http.errorToString(code).c_str());
        else          snprintf(d, sizeof(d), "download HTTP %d", code);
        http.end(); diag(code, d); fail(E_HTTP); return;
    }

    int total = http.getSize();
    if (total <= 0) total = (int)size_;
    if (total <= 0) { http.end(); diag(0, "asset size unknown"); fail(E_SHORT); return; }
    if (!Update.begin(total)) { http.end(); diagUpd("begin"); fail(E_BEGIN); return; }

    bool useSha = strncmp(digest_, "sha256:", 7) == 0;
    if (!useSha) Serial.println("[OTA] WARNING: release asset has no sha256 digest — image not checksum-verified");
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
                if (Update.write(buf, n) != (size_t)n) { char d[72]; snprintf(d, sizeof(d), "flash write @%d: %s", written, Update.errorString()); diag(0, d); Update.abort(); http.end(); if (useSha) mbedtls_sha256_free(&sha); fail(E_WRITE); return; }
                if (useSha) mbedtls_sha256_update(&sha, buf, n);
                written += n; lastRx = millis();
                int p = (int)((int64_t)written * 100 / total);
                if (p != pct_) { pct_ = p; gen_ = gen_ + 1; }
            }
        } else {
            if (!st->connected() && st->available() == 0) break;   // FIN with buffer drained
            if (millis() - lastRx > 20000) { char d[48]; snprintf(d, sizeof(d), "stream stalled 20s @%d bytes", written); diag(0, d); Update.abort(); http.end(); if (useSha) mbedtls_sha256_free(&sha); fail(E_SHORT); return; }
            vTaskDelay(pdMS_TO_TICKS(5));
        }
        if (written - lastYield >= 16384) { lastYield = written; vTaskDelay(1); }  // feed the watchdog
    }
    http.end();
    if (written != total) { char d[40]; snprintf(d, sizeof(d), "got %d/%d bytes", written, total); diag(0, d); Update.abort(); if (useSha) mbedtls_sha256_free(&sha); fail(E_SHORT); return; }

    if (useSha) {
        uint8_t out[32]; mbedtls_sha256_finish(&sha, out); mbedtls_sha256_free(&sha);
        char hex[65]; for (int i = 0; i < 32; i++) sprintf(hex + i * 2, "%02x", out[i]);
        if (strcasecmp(hex, digest_ + 7) != 0) { diag(0, ""); Update.abort(); fail(E_HASH); return; }  // title/hint already say it
    }
    if (!Update.end(true)) { diagUpd("end"); fail(E_END); return; }

    Serial.println("[OTA] update written & verified — rebooting");
    set(DONE);
    vTaskDelay(pdMS_TO_TICKS(1400));
    ESP.restart();
}

// Update.begin()/write()/end() can return false WITHOUT setting an error code (e.g. the
// 4 KB scratch buffer failed to allocate) — errorString() would then say "No Error" and
// hide the real cause. Fall back to the heap state, which is what actually matters here.
void OtaManager::diagUpd(const char* stage) {
    uint8_t ue = Update.getError();
    if (ue) { diag(0, Update.errorString()); return; }
    char d[72];
    snprintf(d, sizeof(d), "%s: no err, heap free=%u max=%u", stage,
             (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
    diag(0, d);
}

void OtaManager::checkTask(void* p) { ((OtaManager*)p)->doCheck();    vTaskDelete(nullptr); }
void OtaManager::updTask(void* p)   { ((OtaManager*)p)->doDownload(); vTaskDelete(nullptr); }

void OtaManager::startCheck() {
    if (busy_) return;
    busy_ = true; err_ = E_NONE; httpCode_ = 0; detail_[0] = 0;
    set(CHECKING);                         // publish CHECKING before the task exists, so a create failure can't strand a stale phase
    if (xTaskCreatePinnedToCore(checkTask, "otachk", 16384, this, 2, nullptr, 1) != pdPASS) {
        diag(0, "no RAM for OTA task"); fail(E_NOMEM);   // fail() clears busy_ and bumps gen_ → screen repaints
    }
}
void OtaManager::startUpdate() {
    if (busy_ || phase_ != AVAILABLE) return;
    busy_ = true; err_ = E_NONE; httpCode_ = 0; detail_[0] = 0;
    set(DOWNLOADING);                       // so failPhase() is correct if the task can't be created
    if (xTaskCreatePinnedToCore(updTask, "otaupd", 16384, this, 2, nullptr, 1) != pdPASS) {
        diag(0, "no RAM for OTA task"); fail(E_NOMEM);
    }
}
