#include "ArduinoCompanionWebService.h"

#include <cctype>
#include <cstdio>
#include <cstring>

#include <esp_event.h>
#include <esp_heap_caps.h>
#include <esp_wifi.h>
#include <esp_wifi_default.h>

#include "services/companion/CompanionWebAdapter.h"

namespace leshy1::platform::arduino {
namespace {

using services::companion::CompanionWebMethod;
using services::companion::CompanionWebRequest;
using services::companion::CompanionWebRequestMetadata;
using services::companion::CompanionWebRoute;
using services::companion::CompanionWebStatus;

bool equalsIgnoreCase(const char* left, const char* right) {
    if (left == nullptr || right == nullptr) return false;
    while (*left != '\0' && *right != '\0') {
        if (std::tolower(static_cast<unsigned char>(*left)) !=
            std::tolower(static_cast<unsigned char>(*right))) {
            return false;
        }
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

char* trim(char* text) {
    if (text == nullptr) return text;
    while (*text == ' ' || *text == '\t') ++text;
    char* end = text + std::strlen(text);
    while (end > text && (end[-1] == ' ' || end[-1] == '\t')) --end;
    *end = '\0';
    return text;
}

bool parseLength(const char* text, std::size_t* output) {
    if (text == nullptr || output == nullptr || *text == '\0') return false;
    std::size_t value = 0;
    for (const char* cursor = text; *cursor != '\0'; ++cursor) {
        if (*cursor < '0' || *cursor > '9') return false;
        const std::size_t digit = static_cast<std::size_t>(*cursor - '0');
        if (value > (services::companion::kCompanionMaxFrameBytes + 1U -
                     digit) /
                        10U) {
            return false;
        }
        value = value * 10U + digit;
    }
    *output = value;
    return true;
}

const char* httpReason(std::uint16_t status) {
    switch (status) {
        case 200: return "OK";
        case 400: return "Bad Request";
        case 403: return "Forbidden";
        case 404: return "Not Found";
        case 405: return "Method Not Allowed";
        case 411: return "Length Required";
        case 413: return "Payload Too Large";
        case 415: return "Unsupported Media Type";
        case 431: return "Request Header Fields Too Large";
        default: return "Bad Request";
    }
}

}  // namespace

const char* ArduinoCompanionWebService::beginStageName(BeginStage stage) {
    switch (stage) {
        case BeginStage::Idle: return "idle";
        case BeginStage::NetworkCore: return "network_core";
        case BeginStage::EventLoop: return "event_loop";
        case BeginStage::Netif: return "netif";
        case BeginStage::WifiHandlers: return "wifi_handlers";
        case BeginStage::WifiInit: return "wifi_init";
        case BeginStage::RamStorage: return "ram_storage";
        case BeginStage::ApMode: return "ap_mode";
        case BeginStage::ApConfig: return "ap_config";
        case BeginStage::WifiStart: return "wifi_start";
        case BeginStage::Dhcp: return "dhcp";
        case BeginStage::Server: return "server";
        case BeginStage::Ready: return "ready";
    }
    return "idle";
}

bool ArduinoCompanionWebService::prepareNetworkCore() {
    if (networkCoreReady_) return true;
    beginStage_ = BeginStage::NetworkCore;
    lastError_ = esp_netif_init();
    networkCoreReady_ = lastError_ == ESP_OK;
    cleanupComplete_ = networkCoreReady_;
    return networkCoreReady_;
}

bool ArduinoCompanionWebService::failBegin(BeginStage stage,
                                           esp_err_t error) {
    beginStage_ = stage;
    lastError_ = error;
    cleanupRuntime();
    return false;
}

bool ArduinoCompanionWebService::begin(
    const services::companion::CompanionLocalCredentials& credentials) {
    if (active_ || !credentials.valid() || !networkCoreReady_ ||
        !cleanupComplete_) {
        return failBegin(BeginStage::NetworkCore, ESP_ERR_INVALID_STATE);
    }
    heapFreeBeforeBegin_ = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_8BIT));
    heapLargestBeforeBegin_ = static_cast<std::uint32_t>(
        heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    heapFreeAfterBegin_ = 0;
    heapFreeAfterStop_ = 0;
    cleanupComplete_ = false;
    lastError_ = ESP_OK;

    beginStage_ = BeginStage::EventLoop;
    esp_err_t error = esp_event_loop_create_default();
    if (error == ESP_OK) {
        eventLoopOwned_ = true;
    } else if (error != ESP_ERR_INVALID_STATE) {
        return failBegin(BeginStage::EventLoop, error);
    }

    beginStage_ = BeginStage::Netif;
    esp_netif_config_t netifConfig = ESP_NETIF_DEFAULT_WIFI_AP();
    apNetif_ = esp_netif_new(&netifConfig);
    if (apNetif_ == nullptr) return failBegin(BeginStage::Netif, ESP_ERR_NO_MEM);
    error = esp_netif_attach_wifi_ap(apNetif_);
    if (error != ESP_OK) return failBegin(BeginStage::Netif, error);
    wifiNetifAttached_ = true;

    beginStage_ = BeginStage::WifiHandlers;
    error = esp_wifi_set_default_wifi_ap_handlers();
    if (error != ESP_OK) return failBegin(BeginStage::WifiHandlers, error);

    beginStage_ = BeginStage::WifiInit;
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    init.static_rx_buf_num = kStaticRxBuffers;
    init.dynamic_rx_buf_num = kDynamicRxBuffers;
    init.tx_buf_type = 1;
    init.static_tx_buf_num = 0;
    init.dynamic_tx_buf_num = kDynamicTxBuffers;
    init.rx_mgmt_buf_type = 1;
    init.rx_mgmt_buf_num = kRxManagementBuffers;
    init.cache_tx_buf_num = kCacheTxBuffers;
    init.ampdu_rx_enable = 0;
    init.ampdu_tx_enable = 0;
    init.amsdu_tx_enable = 0;
    init.rx_ba_win = 1;
    init.mgmt_sbuf_num = kManagementShortBuffers;
    init.espnow_max_encrypt_num = 0;
    error = esp_wifi_init(&init);
    if (error != ESP_OK) return failBegin(BeginStage::WifiInit, error);
    wifiInitialized_ = true;

    beginStage_ = BeginStage::RamStorage;
    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error != ESP_OK) return failBegin(BeginStage::RamStorage, error);
    beginStage_ = BeginStage::ApMode;
    error = esp_wifi_set_mode(WIFI_MODE_AP);
    if (error != ESP_OK) return failBegin(BeginStage::ApMode, error);

    wifi_config_t config{};
    const std::size_t ssidLength = std::strlen(credentials.ssid.data());
    const std::size_t passphraseLength =
        std::strlen(credentials.passphrase.data());
    std::memcpy(config.ap.ssid, credentials.ssid.data(), ssidLength);
    config.ap.ssid_len = static_cast<std::uint8_t>(ssidLength);
    std::memcpy(config.ap.password, credentials.passphrase.data(),
                passphraseLength);
    config.ap.channel = 1;
    config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    config.ap.ssid_hidden = false;
    config.ap.max_connection = 1;
    config.ap.beacon_interval = 100;
    config.ap.pairwise_cipher = WIFI_CIPHER_TYPE_CCMP;
    config.ap.pmf_cfg.capable = true;
    config.ap.pmf_cfg.required = false;
    beginStage_ = BeginStage::ApConfig;
    error = esp_wifi_set_config(WIFI_IF_AP, &config);
    if (error != ESP_OK) return failBegin(BeginStage::ApConfig, error);
    beginStage_ = BeginStage::WifiStart;
    error = esp_wifi_start();
    if (error != ESP_OK) return failBegin(BeginStage::WifiStart, error);
    wifiStarted_ = true;

    beginStage_ = BeginStage::Dhcp;
    const std::uint32_t readyStartedMs = millis();
    esp_err_t readinessError = ESP_ERR_TIMEOUT;
    bool networkReady = false;
    while (static_cast<std::uint32_t>(millis() - readyStartedMs) <
           kApReadyTimeoutMs) {
        esp_netif_dhcp_status_t dhcpStatus = ESP_NETIF_DHCP_INIT;
        const esp_err_t statusError =
            esp_netif_dhcps_get_status(apNetif_, &dhcpStatus);
        const bool ipReady = apIpv4Ready();
        if (statusError == ESP_OK && ipReady &&
            dhcpStatus == ESP_NETIF_DHCP_STARTED) {
            networkReady = true;
            readinessError = ESP_OK;
            break;
        }
        if (statusError == ESP_OK && ipReady &&
            dhcpStatus != ESP_NETIF_DHCP_STARTED) {
            const esp_err_t startError = esp_netif_dhcps_start(apNetif_);
            if (startError != ESP_OK &&
                startError != ESP_ERR_ESP_NETIF_DHCP_ALREADY_STARTED &&
                startError != ESP_ERR_INVALID_STATE) {
                return failBegin(BeginStage::Dhcp, startError);
            }
            readinessError = startError;
        } else if (statusError != ESP_OK) {
            readinessError = statusError;
        }
        delay(kApReadyPollMs);
    }
    if (!networkReady || !apIpv4Ready() || !dhcpServerStarted()) {
        return failBegin(
            BeginStage::Dhcp,
            readinessError == ESP_OK ? ESP_ERR_TIMEOUT : readinessError);
    }

    beginStage_ = BeginStage::Server;
    server_.setNoDelay(true);
    server_.begin();
    if (!server_) return failBegin(BeginStage::Server, ESP_FAIL);
    active_ = true;
    requestsHandled_ = 0;
    requestsRejected_ = 0;
    resetClient();
    beginStage_ = BeginStage::Ready;
    heapFreeAfterBegin_ = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_8BIT));
    return true;
}

bool ArduinoCompanionWebService::apIpv4Ready() const {
    if (apNetif_ == nullptr) return false;
    esp_netif_ip_info_t info{};
    return esp_netif_get_ip_info(apNetif_, &info) == ESP_OK &&
        info.ip.addr != 0U && info.netmask.addr != 0U;
}

bool ArduinoCompanionWebService::dhcpServerStarted() const {
    if (apNetif_ == nullptr) return false;
    esp_netif_dhcp_status_t status = ESP_NETIF_DHCP_INIT;
    return esp_netif_dhcps_get_status(apNetif_, &status) == ESP_OK &&
        status == ESP_NETIF_DHCP_STARTED;
}

std::uint16_t ArduinoCompanionWebService::associatedStations() const {
    if (!wifiStarted_) return 0;
    wifi_sta_list_t stations{};
    if (esp_wifi_ap_get_sta_list(&stations) != ESP_OK) return 0;
    return static_cast<std::uint16_t>(stations.num);
}

bool ArduinoCompanionWebService::cleanupRuntime() {
    bool complete = true;
    resetClient();
    server_.end();
    if (wifiStarted_) {
        const esp_err_t error = esp_wifi_stop();
        if (error != ESP_OK) {
            complete = false;
            lastError_ = error;
        }
    }
    wifiStarted_ = false;
    if (apNetif_ != nullptr) {
        if (wifiNetifAttached_) {
            const esp_err_t error =
                esp_wifi_clear_default_wifi_driver_and_handlers(apNetif_);
            if (error != ESP_OK) {
                complete = false;
                lastError_ = error;
            }
        }
        wifiNetifAttached_ = false;
        esp_netif_destroy(apNetif_);
        apNetif_ = nullptr;
    }
    if (wifiInitialized_) {
        const esp_err_t error = esp_wifi_deinit();
        if (error != ESP_OK) {
            complete = false;
            lastError_ = error;
        }
    }
    wifiInitialized_ = false;
    if (eventLoopOwned_) {
        const esp_err_t error = esp_event_loop_delete_default();
        if (error != ESP_OK) {
            complete = false;
            lastError_ = error;
        }
    }
    eventLoopOwned_ = false;
    active_ = false;
    cleanupComplete_ = complete;
    heapFreeAfterStop_ = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_8BIT));
    return complete;
}

bool ArduinoCompanionWebService::stop() {
    return cleanupRuntime();
}

void ArduinoCompanionWebService::resetClient() {
    if (client_) client_.stop();
    client_ = NetworkClient{};
    request_.fill('\0');
    header_.fill('\0');
    response_.fill('\0');
    requestLength_ = 0;
    clientStartedUs_ = 0;
}

void ArduinoCompanionWebService::sendResponse(
    std::uint16_t status, const char* contentType, const char* body,
    std::size_t bodyLength) {
    if (!client_ || contentType == nullptr || body == nullptr) return;
    char headers[256] = {};
    const int length = std::snprintf(
        headers, sizeof(headers),
        "HTTP/1.1 %u %s\r\nContent-Type: %s\r\nContent-Length: %u\r\n"
        "Cache-Control: no-store\r\nConnection: close\r\n"
        "X-Content-Type-Options: nosniff\r\n\r\n",
        static_cast<unsigned>(status), httpReason(status), contentType,
        static_cast<unsigned>(bodyLength));
    if (length <= 0 || static_cast<std::size_t>(length) >= sizeof(headers)) {
        return;
    }
    client_.write(reinterpret_cast<const std::uint8_t*>(headers),
                  static_cast<std::size_t>(length));
    constexpr std::size_t kChunkBytes = 1024;
    std::size_t offset = 0;
    while (offset < bodyLength && client_) {
        const std::size_t remaining = bodyLength - offset;
        const std::size_t chunk = remaining < kChunkBytes
            ? remaining : kChunkBytes;
        const std::size_t written = client_.write(
            reinterpret_cast<const std::uint8_t*>(body + offset), chunk);
        if (written == 0) break;
        offset += written;
        yield();
    }
    client_.stop();
}

bool ArduinoCompanionWebService::processRequest(
    bool deviceSessionAuthorized, CompanionWebFrameHandler handler,
    void* context) {
    request_[requestLength_] = '\0';
    const char* delimiter = std::strstr(request_.data(), "\r\n\r\n");
    if (delimiter == nullptr) return false;
    const std::size_t headerLength =
        static_cast<std::size_t>(delimiter - request_.data()) + 4U;
    if (headerLength > kMaximumHeaderBytes) {
        constexpr char body[] =
            "{\"schema\":\"leshy.companion.response.v1\",\"kind\":"
            "\"error\",\"request_id\":\"\",\"status\":\"error\","
            "\"reason\":\"headers_too_large\"}\n";
        sendResponse(431, services::companion::kCompanionWebJsonContentType,
                     body, sizeof(body) - 1U);
        ++requestsRejected_;
        return true;
    }
    std::memcpy(header_.data(), request_.data(), headerLength);
    header_[headerLength] = '\0';

    CompanionWebRequestMetadata metadata{};
    char* lineEnd = std::strstr(header_.data(), "\r\n");
    if (lineEnd == nullptr) {
        ++requestsRejected_;
        resetClient();
        return true;
    }
    *lineEnd = '\0';
    char method[8] = {};
    char path[80] = {};
    char version[16] = {};
    int consumed = 0;
    if (std::sscanf(header_.data(), "%7s %79s %15s%n", method, path,
                    version, &consumed) != 3 ||
        header_.data()[consumed] != '\0' ||
        std::strcmp(version, "HTTP/1.1") != 0) {
        metadata.method = CompanionWebMethod::Other;
        path[0] = '\0';
    } else if (std::strcmp(method, "GET") == 0) {
        metadata.method = CompanionWebMethod::Get;
    } else if (std::strcmp(method, "POST") == 0) {
        metadata.method = CompanionWebMethod::Post;
    } else {
        metadata.method = CompanionWebMethod::Other;
    }
    metadata.path = path;
    metadata.pathLength = std::strlen(path);
    metadata.deviceSessionAuthorized = deviceSessionAuthorized;

    bool contentLengthSeen = false;
    bool invalidHeader = false;
    char* cursor = lineEnd + 2;
    while (*cursor != '\0') {
        char* next = std::strstr(cursor, "\r\n");
        if (next == nullptr) {
            invalidHeader = true;
            break;
        }
        *next = '\0';
        if (*cursor == '\0') break;
        char* colon = std::strchr(cursor, ':');
        if (colon == nullptr) {
            invalidHeader = true;
            break;
        }
        *colon = '\0';
        char* name = trim(cursor);
        char* value = trim(colon + 1);
        if (equalsIgnoreCase(name, "Content-Length")) {
            std::size_t parsed = 0;
            if (contentLengthSeen || !parseLength(value, &parsed)) {
                invalidHeader = true;
                break;
            }
            contentLengthSeen = true;
            metadata.declaredContentLength = parsed;
        } else if (equalsIgnoreCase(name, "Content-Type")) {
            if (metadata.contentType != nullptr) {
                invalidHeader = true;
                break;
            }
            metadata.contentType = value;
            metadata.contentTypeLength = std::strlen(value);
        } else if (equalsIgnoreCase(name, "Transfer-Encoding")) {
            metadata.chunked = true;
        }
        cursor = next + 2;
    }

    const std::size_t bodyLength = requestLength_ - headerLength;
    if (!invalidHeader && contentLengthSeen &&
        bodyLength < metadata.declaredContentLength) {
        return false;
    }

    CompanionWebRequest webRequest{};
    const CompanionWebStatus status = invalidHeader
        ? CompanionWebStatus::InvalidArgument
        : services::companion::validateCompanionWebRequest(
              metadata, request_.data() + headerLength, bodyLength,
              &webRequest);
    if (status != CompanionWebStatus::Ready) {
        std::size_t responseLength = 0;
        if (!services::companion::encodeCompanionWebError(
                status, response_.data(), response_.size(),
                &responseLength)) {
            resetClient();
            ++requestsRejected_;
            return true;
        }
        sendResponse(services::companion::companionWebHttpStatus(status),
                     services::companion::kCompanionWebJsonContentType,
                     response_.data(), responseLength);
        ++requestsRejected_;
        return true;
    }

    if (webRequest.route == CompanionWebRoute::Index) {
        std::size_t pageLength = 0;
        const char* page = services::companion::companionWebIndexHtml(
            &pageLength);
        sendResponse(200, services::companion::kCompanionWebHtmlContentType,
                     page, pageLength);
        ++requestsHandled_;
        return true;
    }

    if (handler == nullptr || webRequest.bodyLength >= request_.size()) {
        resetClient();
        ++requestsRejected_;
        return true;
    }
    char* body = const_cast<char*>(webRequest.body);
    body[webRequest.bodyLength] = '\0';
    std::size_t responseLength = 0;
    const bool encoded = handler(
        body, webRequest.bodyLength, response_.data(), response_.size(),
        &responseLength, context);
    if (!encoded || responseLength == 0 ||
        responseLength > services::companion::kCompanionMaxFrameBytes) {
        constexpr char error[] =
            "{\"schema\":\"leshy.companion.response.v1\",\"kind\":"
            "\"error\",\"request_id\":\"\",\"status\":\"error\","
            "\"reason\":\"response_encoding_failed\"}\n";
        sendResponse(400, services::companion::kCompanionWebJsonContentType,
                     error, sizeof(error) - 1U);
        ++requestsRejected_;
        return true;
    }
    sendResponse(200, services::companion::kCompanionWebJsonContentType,
                 response_.data(), responseLength);
    ++requestsHandled_;
    return true;
}

bool ArduinoCompanionWebService::poll(
    std::uint64_t nowUs, bool deviceSessionAuthorized,
    CompanionWebFrameHandler handler, void* context) {
    if (!active_) return false;
    if (!client_) {
        resetClient();
        if (!server_.hasClient()) return false;
        client_ = server_.accept();
        if (!client_) return false;
        clientStartedUs_ = nowUs == 0 ? 1 : nowUs;
        client_.setNoDelay(true);
    }
    if (nowUs >= clientStartedUs_ &&
        nowUs - clientStartedUs_ >= kClientDeadlineUs) {
        ++requestsRejected_;
        resetClient();
        return false;
    }
    std::size_t reads = 0;
    while (client_.available() > 0 && reads < 384U) {
        const int value = client_.read();
        if (value < 0) break;
        if (requestLength_ >= kRequestCapacity) {
            constexpr char body[] =
                "{\"schema\":\"leshy.companion.response.v1\",\"kind\":"
                "\"error\",\"request_id\":\"\",\"status\":\"error\","
                "\"reason\":\"frame_too_large\"}\n";
            sendResponse(413,
                         services::companion::kCompanionWebJsonContentType,
                         body, sizeof(body) - 1U);
            ++requestsRejected_;
            resetClient();
            return true;
        }
        request_[requestLength_++] = static_cast<char>(value);
        ++reads;
    }
    const bool complete = processRequest(
        deviceSessionAuthorized, handler, context);
    if (complete) {
        resetClient();
        return true;
    }
    if (!client_.connected() && client_.available() == 0) resetClient();
    return false;
}

}  // namespace leshy1::platform::arduino
