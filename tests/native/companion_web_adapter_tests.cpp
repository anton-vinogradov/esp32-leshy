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
    CHECK(page.find("/api/v1/companion") != std::string::npos);
    CHECK(page.find("leshy.companion.request.v1") != std::string::npos);
    CHECK(page.find("session.list") != std::string::npos);
    CHECK(page.find("target.list") != std::string::npos);
    CHECK(page.find("target.compare") != std::string::npos);
    CHECK(page.find("target.mutation.preview") != std::string::npos);
    CHECK(page.find("target.mutation.confirm") != std::string::npos);
    CHECK(page.find("target.mutation.status") != std::string::npos);
    CHECK(page.find("target.favorite.set") != std::string::npos);
    CHECK(page.find("esc(JSON.stringify") != std::string::npos);
    CHECK(page.find("&amp;") != std::string::npos);
    CHECK(page.find("http://") == std::string::npos);
    CHECK(page.find("https://") == std::string::npos);
    CHECK(page.find("<script src=") == std::string::npos);
    CHECK(page.find("<link") == std::string::npos);
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
