#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/auth/WifiAuthenticationArtifactPolicy.h"
#include "domain/captures/WifiFrame.h"

namespace leshy1::apps::auth {

using WifiAuthenticationArtifactByteSink = bool (*)(
    const std::uint8_t* data, std::size_t size, void* context);

enum class WifiAuthenticationHc22000Status : std::uint8_t {
    Valid,
    InvalidArgument,
    PolicyRejected,
    EvidenceMismatch,
    NoArtifact,
    OutputFailed,
};

const char* wifiAuthenticationHc22000StatusName(
    WifiAuthenticationHc22000Status status);

struct WifiAuthenticationHc22000Result final {
    WifiAuthenticationHc22000Status status =
        WifiAuthenticationHc22000Status::InvalidArgument;
    std::size_t bytesWritten = 0U;
    std::size_t recordsWritten = 0U;
    std::size_t pmkidRecordsWritten = 0U;
    std::size_t eapolRecordsWritten = 0U;

    bool valid() const {
        return status == WifiAuthenticationHc22000Status::Valid;
    }
};

// Writes canonical hashcat mode-22000 text records.  The implementation is
// bounded and allocation-free.  It performs a complete validation pass before
// the first sink call, re-decodes every selected immutable source frame, emits
// WPA*01 PMKID records and strict M1->M2 WPA*02 records, and zeros the Key MIC
// inside the exported EAPOL packet while preserving its original MIC field.
WifiAuthenticationHc22000Result writeWifiAuthenticationHc22000(
    const services::auth::WifiAuthenticationCaptureReport& report,
    const storage::AuthenticationCaptureProvenance& provenance,
    const domain::captures::WifiFrameSource& source,
    WifiAuthenticationArtifactByteSink sink, void* context);

// Returns zero unless the exact same validation and serialization path would
// succeed.  No payload-sized buffer is allocated.
std::size_t wifiAuthenticationHc22000Size(
    const services::auth::WifiAuthenticationCaptureReport& report,
    const storage::AuthenticationCaptureProvenance& provenance,
    const domain::captures::WifiFrameSource& source);

}  // namespace leshy1::apps::auth
