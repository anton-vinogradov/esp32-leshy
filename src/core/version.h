#pragma once

// Firmware version — SemVer, no leading 'v'. This is the single source of truth
// the OTA updater compares against the latest GitHub release tag (vMAJOR.MINOR.PATCH).
// Release builds overwrite this whole file from the git tag (see the release workflow);
// local dev builds fall back to these defaults.
#ifndef LESHY_FW_VERSION
#define LESHY_FW_VERSION "0.7.0"
#endif
#ifndef LESHY_FW_DATE
#define LESHY_FW_DATE "dev"
#endif
