# ESP32-Leshy 1.x — 1.0 catalog product review

*Read in: **English** · [Русский](CAPABILITY_REVIEW.ru.md)*

Date: 17 August 2026. Result: **product scope coherent; catalog baseline reviewed;
the PRD technical baseline is accepted by `E-GATE-001`**.

## Inputs and review rules

The review maps [Vision](VISION.md), J-01…J-06 and PR/NFR in the
[PRD](PRODUCT_REQUIREMENTS.md), WF-01…WF-05, hardware envelope, delivery stages, and
explicit exclusions to every [catalog](CAPABILITY_CATALOG.md) row.

A 1.0 capability remains only when it has an authorized user outcome, primary IA
owner, requirement, stage, error/cancel path, and verifiable result. A 0.x or
competitor menu item is not sufficient. Conditional hardware remains in scope but
must fail closed when its assembly/evidence is absent.

## Gaps found and closed

| Finding | Why broad rows were insufficient | Baseline correction |
|---|---|---|
| CRV-01 Wi-Fi capture | scan plus generic PCAP export did not promise a real packet/channel workflow needed for parity and evidence | CAP-042 + PR-015: passive bounded monitor/Capture, PCAP, drops, no hidden TX |
| CRV-02 Screenshot | Vision named screenshots but the catalog lacked a user Action, provenance, and Library path | CAP-043 + PR-015: real-TFT screenshot as evidence artifact |
| CRV-03 Offline enrichment | Target promised identities but not version/provenance for local OUI/BLE/protocol data | CAP-044 + PR-019: raw facts stay available; database only enriches |
| CRV-04 Feedback hardware | Settings named sound without an owner for GPIO2/WS2812, quiet mode, or safe idle | CAP-045 + PR-016: one service, idle LOW, bounded cues, non-color fallback |
| CRV-05 Connectivity/secrets | OTA/companion needed networking but setup, offline degradation, and secret boundary were not a user capability | CAP-046 + PR-017: scoped Wi-Fi/USB, no secret export, offline Survey/Library |
| CRV-06 Data maintenance | firmware update recovery is not user-data backup/restore and factory reset | CAP-047 + PR-018: preview/checksum/cancel/recovery and immutable-raw protection |

## Overlap review

- CAP-009/023/042 do not duplicate: Session is context, Capture is an immutable
  artifact, and Wi-Fi monitor is a concrete passive producer.
- CAP-026/027 do not duplicate: one defines formats, the other safe import/export
  transports and parsers.
- CAP-029…031 and CAP-034…036 separate capture/read from Lab replay/write; this is a
  safety boundary rather than duplicate menus.
- CAP-007 and CAP-047 separate firmware recovery from user-data maintenance.
- CAP-017/044 separate measured localization from reference enrichment; database
  content never changes RSSI evidence.

## Coverage outcome

| Check | Result |
|---|---|
| Jobs | J-01…J-06 have capability and WF owners |
| Requirements | PR-001…PR-019 and NFR-001…NFR-010 appear in stages/traceability; PRD is accepted as baseline 1.0 while verification remains staged |
| Information architecture | Every CAP-001…CAP-047 has a primary owner under the UX-S01 six-task Home |
| Error/cancel behavior | UX-02 defines unavailable/loading/degraded/error/confirm/success and cleanup for every screen family |
| Hardware conditionals | RF shield, GPS, PN532, and sound HW-T09 never become unconditional availability |
| Safety | Passive Capture is separate from Lab; every TX has scope/confirm/deadline/Stop/Panic |
| Explicit exclusions | Cloud/default telemetry, executable marketplace, broad boards, and attack-count parity remain post-1.0 |

## Verdict

Product review accepts CAP-001…CAP-047 as the complete working 1.0 boundary. A new
major capability after this review needs a separate `J/PR/CAP`, risk impact, and
stage proposal; wording and acceptance may be refined without hidden scope growth.

Together with constrained hardware/resource evidence, this scope review closes S1
through `E-GATE-001`. It does not mark capabilities implemented or verified; those
states require the applicable S2…S8 evidence and gates.
