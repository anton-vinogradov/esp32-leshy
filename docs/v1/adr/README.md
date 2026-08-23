# ESP32-Leshy 1.x — architecture decision records

*Read in: **English** · [Русский](README.ru.md)*

Accepted ADRs are binding below requirements and above general architecture text.
Changing one requires a new ADR that supersedes it; history is not rewritten.

| ADR | Status | Decision | Main requirements/risks |
|---|---|---|---|
| [ADR-001](ADR-001-toolchain.md) | accepted | pinned PlatformIO + Arduino-ESP32/IDF platform behind adapters; clean 1.x target | PR-010/014, NFR-001/006, R-011/012/013 |
| [ADR-002](ADR-002-resource-policy.md) | accepted | fail-closed capabilities and atomic exclusive resource leases | PR-001/002/009/013/014, NFR-002/006, R-003/004/008/009 |
| [ADR-003](ADR-003-storage-schema.md) | accepted | versioned CBOR records, immutable payloads, append-only segments, dual commit heads | PR-005…008/012, NFR-007…009, R-006/010/014/016 |
| [ADR-004](ADR-004-action-boundary.md) | accepted | one typed Action dispatcher for UI, CLI, companion, and tests | PR-002/012/013, NFR-002/003/006, R-008/009/016 |
| [ADR-005](ADR-005-pre-release-hil.md) | accepted | hybrid host runner + safe firmware evidence plane; build once, test and publish exact bytes | PR-010/014/015, NFR-001…003/005/010 |
| [ADR-006](ADR-006-bounded-signal-fixture.md) | accepted | separate source-bound fixture with fixed, minimum-power and hard-time-bounded signal vectors | PR-009/014, NFR-001/002/005/006, R-018 |

Acceptance selects the design and tests to build. It does not mark its requirements
implemented or verified.
