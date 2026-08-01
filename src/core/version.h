#pragma once

// Firmware version — SemVer, no leading 'v'. This is the single source of truth
// the OTA updater compares against the latest GitHub release tag (vMAJOR.MINOR.PATCH).
// Release builds override it from the git tag via -D LESHY_FW_VERSION (see the
// GitHub Actions release workflow); local dev builds fall back to this default.
#ifndef LESHY_FW_VERSION
#define LESHY_FW_VERSION "0.1.0"
#endif
