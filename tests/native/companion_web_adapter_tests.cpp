#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

#include "services/companion/CompanionWebAdapter.h"

using namespace leshy1::services::companion;

namespace {

int failures = 0;

#define CHECK(expression)                                                                       \
    do {                                                                                        \
        if (!(expression)) {                                                                    \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                         \
        }                                                                                       \
    } while (false)

CompanionWebRequestMetadata request(CompanionWebMethod method,
                                    const char* path) {
    CompanionWebRequestMetadata value{};
    value.method = method;
    value.path = path;
    value.pathLength = std::strlen(path);
    value.deviceSessionAuthorized = true;
    return value;
}

CompanionWebRequestMetadata api(std::size_t length) {
    auto value = request(CompanionWebMethod::Post, kCompanionWebApiPath);
    value.contentType = kCompanionWebJsonContentType;
    value.contentTypeLength = std::strlen(value.contentType);
    value.declaredContentLength = length;
    return value;
}

void testExactIndexAndApiRoutes() {
    CompanionWebRequest output{};
    auto metadata = request(CompanionWebMethod::Get, kCompanionWebIndexPath);
    CHECK(validateCompanionWebRequest(metadata, nullptr, 0, &output) ==
          CompanionWebStatus::Ready);
    CHECK(output.route == CompanionWebRoute::Index);
    CHECK(output.body == nullptr);

    metadata = request(CompanionWebMethod::Get, kCompanionWebAppPath);
    output = {};
    CHECK(validateCompanionWebRequest(metadata, nullptr, 0, &output) ==
          CompanionWebStatus::Ready);
    CHECK(output.route == CompanionWebRoute::App);
    CHECK(output.body == nullptr);

    const std::string body =
        "{\"schema\":\"leshy.companion.request.v1\","
        "\"kind\":\"connect\",\"request_id\":\"web-1\","
        "\"protocol\":1,\"scopes\":[\"target.read\"]}";
    metadata = api(body.size());
    output = {};
    CHECK(validateCompanionWebRequest(
              metadata, body.data(), body.size(), &output) ==
          CompanionWebStatus::Ready);
    CHECK(output.route == CompanionWebRoute::CompanionApi);
    CHECK(output.body == body.data());
    CHECK(output.bodyLength == body.size());

    CompanionConnectRequest connect{};
    CHECK(parseCompanionConnectRequest(
              output.body, output.bodyLength, &connect) ==
          CompanionParseStatus::Parsed);
    CHECK(connect.requestedScopes ==
          companionScopeMask(CompanionScope::TargetRead));
}

void testBoundaryFailsClosedWithoutPublishingPartialRequest() {
    const std::string body = "{}";
    CompanionWebRequest output{};
    output.route = CompanionWebRoute::Index;
    output.body = reinterpret_cast<const char*>(0x1);
    output.bodyLength = 77;

    auto denied = api(body.size());
    denied.deviceSessionAuthorized = false;
    CHECK(validateCompanionWebRequest(
              denied, body.data(), body.size(), &output) ==
          CompanionWebStatus::SessionUnavailable);

    auto wrongPath = api(body.size());
    wrongPath.path = "/api/v2/companion";
    wrongPath.pathLength = std::strlen(wrongPath.path);
    CHECK(validateCompanionWebRequest(
              wrongPath, body.data(), body.size(), &output) ==
          CompanionWebStatus::NotFound);

    auto wrongMethod = api(body.size());
    wrongMethod.method = CompanionWebMethod::Get;
    CHECK(validateCompanionWebRequest(
              wrongMethod, body.data(), body.size(), &output) ==
          CompanionWebStatus::MethodNotAllowed);

    auto wrongType = api(body.size());
    wrongType.contentType = "text/plain";
    wrongType.contentTypeLength = std::strlen(wrongType.contentType);
    CHECK(validateCompanionWebRequest(
              wrongType, body.data(), body.size(), &output) ==
          CompanionWebStatus::UnsupportedMediaType);

    auto chunked = api(body.size());
    chunked.chunked = true;
    CHECK(validateCompanionWebRequest(
              chunked, body.data(), body.size(), &output) ==
          CompanionWebStatus::ChunkedUnsupported);

    auto mismatch = api(body.size() + 1U);
    CHECK(validateCompanionWebRequest(
              mismatch, body.data(), body.size(), &output) ==
          CompanionWebStatus::LengthMismatch);

    auto empty = api(0);
    CHECK(validateCompanionWebRequest(empty, nullptr, 0, &output) ==
          CompanionWebStatus::EmptyBody);

    auto indexBody = request(CompanionWebMethod::Get,
                             kCompanionWebIndexPath);
    indexBody.declaredContentLength = body.size();
    CHECK(validateCompanionWebRequest(
              indexBody, body.data(), body.size(), &output) ==
          CompanionWebStatus::UnexpectedBody);

    CHECK(output.route == CompanionWebRoute::Index);
    CHECK(output.body == reinterpret_cast<const char*>(0x1));
    CHECK(output.bodyLength == 77);
}

void testExact512ByteBodyLimit() {
    std::string exactBody(kCompanionMaxFrameBytes, 'x');
    CompanionWebRequest output{};
    auto metadata = api(exactBody.size());
    CHECK(validateCompanionWebRequest(
              metadata, exactBody.data(), exactBody.size(), &output) ==
          CompanionWebStatus::Ready);
    CHECK(output.bodyLength == kCompanionMaxFrameBytes);

    exactBody.push_back('x');
    metadata = api(exactBody.size());
    CHECK(validateCompanionWebRequest(
              metadata, exactBody.data(), exactBody.size(), &output) ==
          CompanionWebStatus::BodyTooLarge);
}

void testBoundedErrorsAndHttpMapping() {
    CHECK(companionWebHttpStatus(CompanionWebStatus::Ready) == 200);
    CHECK(companionWebHttpStatus(CompanionWebStatus::SessionUnavailable) ==
          403);
    CHECK(companionWebHttpStatus(CompanionWebStatus::MethodNotAllowed) == 405);
    CHECK(companionWebHttpStatus(CompanionWebStatus::BodyTooLarge) == 413);
    CHECK(companionWebHttpStatus(CompanionWebStatus::UnsupportedMediaType) ==
          415);

    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionWebError(
        CompanionWebStatus::BodyTooLarge, output.data(), output.size(),
        &length));
    CHECK(length <= kCompanionMaxFrameBytes);
    CHECK(std::strstr(output.data(), kCompanionResponseSchema) != nullptr);
    CHECK(std::strstr(output.data(), "\"reason\":\"frame_too_large\"") !=
          nullptr);

    std::array<char, 12> tooSmall{};
    tooSmall.fill('Q');
    length = 99;
    CHECK(!encodeCompanionWebError(
        CompanionWebStatus::NotFound, tooSmall.data(), tooSmall.size(),
        &length));
    CHECK(length == 0);
    for (char value : tooSmall) CHECK(value == 'Q');
}

void testOfflinePageUsesOnlyTheSharedContract() {
    std::size_t length = 0;
    const char* html = companionWebIndexHtml(&length);
    CHECK(html != nullptr);
    CHECK(length == std::strlen(html));
    CHECK(length < 16384);
    const std::string page(html, length);
    std::size_t scriptLength = 0;
    const char* javascript = companionWebAppJavascript(&scriptLength);
    CHECK(javascript != nullptr);
    CHECK(scriptLength == std::strlen(javascript));
    CHECK(scriptLength < 16384);
    const std::string script(javascript, scriptLength);
    const std::string complete = page + script;
    CHECK(page.find("<script src=\"/app.js\">") != std::string::npos);
    CHECK(complete.find("/api/v1/companion") != std::string::npos);
    CHECK(complete.find("leshy.companion.request.v1") != std::string::npos);
    CHECK(complete.find("leshy.companion.offline.v1") != std::string::npos);
    CHECK(complete.find("local_web_json") != std::string::npos);
    CHECK(complete.find("session.list") != std::string::npos);
    CHECK(complete.find("target.list") != std::string::npos);
    CHECK(complete.find("target.compare") != std::string::npos);
    CHECK(complete.find("target.mutation.preview") != std::string::npos);
    CHECK(complete.find("target.mutation.confirm") != std::string::npos);
    CHECK(complete.find("target.mutation.status") != std::string::npos);
    CHECK(complete.find("target.favorite.set") != std::string::npos);
    CHECK(complete.find("targetMatches") != std::string::npos);
    CHECK(complete.find("exportSnapshot") != std::string::npos);
    CHECK(complete.find("sha256") != std::string::npos);
    CHECK(complete.find("snapshot_integrity_unavailable") != std::string::npos);
    CHECK(complete.find("esc(JSON.stringify") != std::string::npos);
    CHECK(complete.find("&amp;") != std::string::npos);
    CHECK(page.find("data-copy=\"sessions\"") != std::string::npos);
    CHECK(page.find("Recorded sessions") != std::string::npos);
    CHECK(page.find(u8"Записи") != std::string::npos);
    CHECK(page.find(u8"Найти цель") != std::string::npos);
    CHECK(complete.find("navigator.language") != std::string::npos);
    CHECK(complete.find("applyLanguage") != std::string::npos);
    CHECK(complete.find("humanReason") != std::string::npos);
    CHECK(complete.find("http://") == std::string::npos);
    CHECK(complete.find("https://") == std::string::npos);
    CHECK(page.find("<script src=\"http") == std::string::npos);
    CHECK(page.find("<link") == std::string::npos);

    std::size_t gzipLength = 0;
    const std::uint8_t* gzip = companionWebIndexGzip(&gzipLength);
    CHECK(gzip != nullptr);
    CHECK(gzipLength > 18);
    CHECK(gzipLength < 4096);
    CHECK(gzip[0] == 0x1f);
    CHECK(gzip[1] == 0x8b);
    CHECK(gzip[2] == 0x08);

    std::size_t appGzipLength = 0;
    const std::uint8_t* appGzip = companionWebAppGzip(&appGzipLength);
    CHECK(appGzip != nullptr);
    CHECK(appGzipLength > 18);
    CHECK(appGzipLength < 4096);
    CHECK(appGzip[0] == 0x1f);
    CHECK(appGzip[1] == 0x8b);
    CHECK(appGzip[2] == 0x08);
}

}  // namespace

int main() {
    static_assert(sizeof(CompanionWebRequest) <= 32,
                  "web request view must remain bounded");
    testExactIndexAndApiRoutes();
    testBoundaryFailsClosedWithoutPublishingPartialRequest();
    testExact512ByteBodyLimit();
    testBoundedErrorsAndHttpMapping();
    testOfflinePageUsesOnlyTheSharedContract();
    if (failures != 0) {
        std::cerr << failures << " companion web adapter checks failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "companion web adapter tests passed\n";
    return EXIT_SUCCESS;
}
