# ESP32-Leshy 1.x — architecture decision records

*Читать на: [English](README.md) · **Русский***

Accepted ADR обязательны ниже requirements и выше общего текста architecture.
Изменение оформляется новым ADR со статусом superseded; история не переписывается.

| ADR | Статус | Решение | Основные requirements/risks |
|---|---|---|---|
| [ADR-001](ADR-001-toolchain.ru.md) | accepted | pinned PlatformIO + Arduino-ESP32/IDF за adapters; clean target 1.x | PR-010/014, NFR-001/006, R-011/012/013 |
| [ADR-002](ADR-002-resource-policy.ru.md) | accepted | fail-closed capabilities и atomic exclusive resource leases | PR-001/002/009/013/014, NFR-002/006, R-003/004/008/009 |
| [ADR-003](ADR-003-storage-schema.ru.md) | accepted | versioned CBOR records, immutable payloads, append-only segments, dual commit heads | PR-005…008/012, NFR-007…009, R-006/010/014/016 |
| [ADR-004](ADR-004-action-boundary.ru.md) | accepted | единый typed Action dispatcher для UI, CLI, companion и tests | PR-002/012/013, NFR-002/003/006, R-008/009/016 |
| [ADR-005](ADR-005-pre-release-hil.ru.md) | accepted | hybrid host-runner + safe firmware evidence plane; build once, test и publish exact bytes | PR-010/014/015, NFR-001…003/005/010 |
| [ADR-006](ADR-006-bounded-signal-fixture.ru.md) | accepted | отдельный source-bound fixture с fixed, minimum-power и hard-time-bounded signal vectors | PR-009/014, NFR-001/002/005/006, R-018 |

Acceptance выбирает design и будущие tests. Он не переводит requirements в
implemented или verified.
