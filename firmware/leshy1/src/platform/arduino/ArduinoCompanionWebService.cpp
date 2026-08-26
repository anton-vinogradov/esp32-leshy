#include "ArduinoCompanionWebService.h"

#include <WiFi.h>

#include <cctype>
#include <cstdio>
#include <cstring>

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

bool ArduinoCompanionWebService::begin(
    const services::companion::CompanionLocalCredentials& credentials) {
    if (active_ || !credentials.valid()) return false;
    WiFi.persistent(false);
    if (!WiFi.mode(WIFI_AP) ||
        !WiFi.softAP(credentials.ssid.data(), credentials.passphrase.data(),
                     1, false, 1)) {
        WiFi.softAPdisconnect(true);
        WiFi.mode(WIFI_OFF);
        return false;
    }
    server_.setNoDelay(true);
    server_.begin();
    if (!server_) {
        WiFi.softAPdisconnect(true);
        WiFi.mode(WIFI_OFF);
        return false;
    }
    active_ = true;
    requestsHandled_ = 0;
    requestsRejected_ = 0;
    resetClient();
    return true;
}

void ArduinoCompanionWebService::stop() {
    resetClient();
    server_.end();
    if (active_) {
        WiFi.softAPdisconnect(true);
        WiFi.mode(WIFI_OFF);
    }
    active_ = false;
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
