# ADR-008: live radio browsing without SD

*Read in: **English** · [Русский](ADR-008-live-radio-without-sd.ru.md)*

- Status: **accepted**, owner confirmed on 13 September 2026.
- Requirements: PR-003/004/005, CAP-009/010/011; stage S6.5.
- Context: live Wi-Fi/BLE lists reused durable Survey admission, preventing
  reception on a new device with no enrolled SD.
- Decision: networks/devices/graphs use an explicit volatile RX-only mode.
  It shares the worker, bounded queues, timeline, Stop and watchdog, but does
  not read CID, mount SD or obtain a write permit. Its data disappears on
  exit/reset; no claim of saving is made. Only explicit Save/Field Visit needs
  ready exact-CID storage, valid keys and the existing atomic commit policy.
  Persistent requests must never silently fall back to RAM on media failure.
- Alternatives: requiring a card for viewing is unnecessary coupling; forging
  a writable permit violates the storage boundary and is forbidden; duplicating
  scanners risks diverging watchdog, cleanup and UX behavior.
- Consequences: no new file format, key migration, SD enrollment or formatting.
  Key access, radio ownership/coexistence, RF TX and Stop rules are unchanged.
  ADR-007 PIN policy is not broadened.
- Verification: host admission covers live/persistent and negative resource,
  source, passive and commit cases; product HIL checks live data, zero SD
  identification/mount/write, zero TX, Back and re-entry. Known-signal antenna
  and durable-write qualification remain separate.
