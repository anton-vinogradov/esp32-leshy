# ADR-001 — clean 1.x toolchain and framework boundary

*Read in: **English** · [Русский](ADR-001-toolchain.ru.md)*

- **Status:** accepted
- **Date:** 2026-08-16
- **Requirements:** PR-001, PR-010, PR-014; NFR-001, NFR-006
- **Risks:** R-011, R-012, R-013
- **Stage:** S1 decision; implemented first in S2

## Context

0.x and the feasibility contracts currently share one PlatformIO/Arduino build. The
installed platform is reproducible and already exposes ESP-IDF 5.5.4/FreeRTOS APIs,
but copying the legacy source tree would preserve its lifecycle and dependency
coupling. A native ESP-IDF rewrite would remove Arduino globals but would also force
display/input/library bring-up before validating the first product slice.

## Decision

1. Create an independent 1.x PlatformIO environment and source tree; it compiles no
   0.x application or screen source.
2. Pin the platform to pioarduino `55.03.39`, Arduino-ESP32 `3.3.9`, ESP-IDF `5.5.4`,
   and exact direct library versions. Floating ranges are forbidden in the 1.x env.
3. Use Arduino-ESP32 as the board-support/framework layer for S2. Direct Arduino,
   ESP-IDF, and FreeRTOS calls exist only under `platform/` or a hardware driver;
   domain/kernel/services code remains host-testable standard C++.
4. Compile as C++17 with warnings treated as CI failures for new 1.x code. CI builds
   from an empty dependency cache and records tool versions plus image/map sizes.
5. Target the measured N16/no-PSRAM profile. Partition layout follows ADR-003 and
   RB-02; two bootable slots and recovery remain mandatory.
6. A dependency is admitted only with owner, pinned source/version, license review,
   bounded API wrapper, and a host/simulated alternative where practical.

## Alternatives

- **Continue the 0.x environment/tree:** rejected; it violates the generation
  boundary and makes feature removal unsafe.
- **Native ESP-IDF immediately:** deferred, not rejected forever. Its migration cost
  is unjustified before S2/S3 measurement; platform adapters preserve that option.
- **Unpinned registry packages:** rejected because API drift already broke BLE builds.

## Consequences

S2 can reuse proven board ecosystem support without making Arduino the domain
architecture. The project accepts pioarduino availability as a supply risk and
mitigates it with exact artifacts, clean-cache CI, and adapters. Superseding this ADR
requires a clean build, size/boot comparison, and working display/input/storage
smoke on board-01.

## Verification

- clean target contains no 0.x source paths;
- two clean-cache CI builds produce identical version manifests and firmware hashes;
- host tests compile without Arduino headers;
- build satisfies RB-02/RB-03; HIL proves boot, display, input, recovery.
