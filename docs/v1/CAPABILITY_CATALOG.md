# ESP32-Leshy 1.x — 1.0 capability catalog

*Read in: **English** · [Русский](CAPABILITY_CATALOG.ru.md)*

Document status: **product-reviewed 1.0 scope baseline**, 16 August 2026.

This catalog is the user-facing view of the 1.0 boundary. Normative acceptance
criteria remain in [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md), while current
implementation state lives only in [STATUS.md](STATUS.md). A row is not done merely
because it exists: it becomes `verified` only through linked evidence.

## How to read the catalog

- **P0** — 1.0.0 cannot ship without it;
- **P1** — part of agreed 1.0 completeness and frozen no later than S7;
- **conditional** — required for 1.0 when the corresponding stock or explicitly
  selected optional assembly is declared and detected;
- **S2…S7** — the stage that delivers the complete user path;
- **S8** verifies the release and does not add major capabilities.

Wording and priority can be refined until S1 is accepted. A new row after S1 needs a
`J-*`, `PR/NFR-*`, stage, and test link; after the S7 feature freeze it requires an
explicit release-boundary change.

## Platform and device

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-001 | Boot probe identifies board, main/RF assembly, and capability states with evidence | P0 | PR-001, PR-014 | S2/S5 |
| CAP-002 | Home is projected from available capabilities and explains disabled/conflicted/fault before launch | P0 | PR-002 | S2 |
| CAP-003 | Diagnostics performs a safe no-TX self-test and exports a report | P0 | PR-009 | S2/S5 |
| CAP-004 | TFT, buttons, and touch use common Actions, calibration, and an accessible Back path | P0 | PR-002, NFR-002, NFR-010 | S2 |
| CAP-005 | EN/RU language, brightness, theme, sound, and screen behavior settings persist locally | P1 | PR-011, NFR-010 | S2/S5 |
| CAP-006 | Power, charging, low-voltage safe writes, sleep/resume, and reset reasons are visible and testable | P0 | PR-009, NFR-004 | S5 |
| CAP-007 | Browser install, stable/beta update, signatures, rollback, and recovery image | P0 | PR-010 | S8 |
| CAP-008 | Local logs, crash journal, and diagnostic bundle work without cloud services | P1 | PR-009, PR-012 | S6/S8 |

## Survey and observations

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-009 | Start/Stop creates a bounded Survey Session with explicit configuration and provenance | P0 | PR-003 | S3 |
| CAP-010 | Passive Wi-Fi scan publishes normalized Observations | P0 | PR-003 | S3 |
| CAP-011 | Passive BLE scan/sniff publishes normalized Observations | P0 | PR-003 | S4 |
| CAP-012 | Three nRF24 receivers provide passive 2.4 GHz activity without hidden TX | P0, conditional RF shield | PR-003, PR-014 | S4/S5 |
| CAP-013 | CC1101 provides passive Sub-GHz spectrum/activity and RSSI/frequency evidence | P0, conditional RF shield | PR-003, PR-014 | S4/S5 |
| CAP-014 | GPS adds fix, satellites, time, and track to a Session when an explicit assembly is selected | conditional | PR-003, PR-014 | S4/S5 |
| CAP-015 | A common timeline shows sources, duty cycle, temporary unavailability, and dropped events | P0 | PR-003, NFR-004, NFR-005 | S4 |
| CAP-016 | Common List/Detail/filter behavior is consistent across supported radios | P0 | PR-004 | S3/S4 |
| CAP-017 | Radar/localize shows RSSI history and honest proximity limits | P1 | PR-004 | S4/S6 |
| CAP-042 | Passive Wi-Fi channel/packet monitor creates a bounded Capture and compatible PCAP with drop counters and no hidden TX | P0 | PR-003, PR-007, PR-015 | S4 |

Implementation checkpoint: exact `0.115.0-wifi-device-intelligence` deepens the
current CAP-016 Wi-Fi Devices detail with passive management/data-frame facts, a
pinned 39,984-entry IEEE MA-L lookup, explicit private-MAC handling and a
selected-channel current-signal radar. This is the first useful slice of CAP-017 and
CAP-044, but it does not close either: retained RSSI history, localization semantics,
BLE/services/protocol profiles, Target correlation and persistent identity history
remain owned by S6.

## Targets and comparison

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-018 | Target retains identities and source Observation history | P1 | PR-008 | S6 |
| CAP-019 | Users add Target tags, notes, name, and favorite state | P1 | PR-008 | S6 |
| CAP-020 | Correlation explains signals/confidence; merge/split are reversible | P1 | PR-008 | S6 |
| CAP-021 | Baseline/diff compares visits and shows new, missing, and changed targets | P1 | J-04, PR-008 | S6 |
| CAP-022 | Every compare/correlation conclusion opens its source evidence | P1 | PR-008, NFR-008 | S6 |

## Capture, library, and data portability

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-023 | Capture is immutable and stores time, source, frequency/channel, RSSI, coordinates, and receive settings | P0 | PR-005, NFR-008 | S3/S4 |
| CAP-024 | Session/Capture writes are atomic and recover after reset or power loss | P0 | PR-005, NFR-009 | S3/S5 |
| CAP-025 | Library opens saved Session/Capture data offline with list/detail/search/filter | P0 | PR-006 | S3/S6 |
| CAP-026 | Export provides JSON/CSV summary, PCAP for compatible frames, and portable radio formats | P0/P1 | PR-007 | S3/S5 |
| CAP-027 | SD, USB, and local companion import/export use versioned schemas and fail-closed parsers | P0 | PR-007, NFR-007, NFR-009 | S5/S6 |
| CAP-028 | SD and LittleFS expose identity, capacity, recovery, integrity, and degraded behavior | P0 | PR-005, PR-006, PR-009 | S3/S5 |
| CAP-029 | IR capture/decode/library preserves the original and derived results | P0, conditional RF shield | PR-007, PR-014 | S5 |
| CAP-030 | Sub-GHz RAW/decode/library preserves pulses, radio parameters, and derived results | P0, conditional RF shield | PR-007, PR-014 | S5 |
| CAP-031 | PN532 reads tag/NDEF info and versioned dumps under an explicit non-conflicting assembly | conditional | PR-007, PR-014 | S5 |
| CAP-043 | A user saves a real-TFT screenshot with build/state/time provenance and opens it in Library/export | P1 | J-03, PR-015 | S2/S5 |

## Authorized Lab

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-032 | Lab context is separate from passive work and shows scope, frequency, power, time, and TX state | P0 for any TX | PR-013 | S7 |
| CAP-033 | Back, timeout, panic, and fault physically stop every enabled TX path | P0 for any TX | PR-013, NFR-002, NFR-006 | S7 |
| CAP-034 | IR replay is available only for a selected saved Capture in an authorized context | conditional | PR-013, PR-014 | S5/S7 |
| CAP-035 | Sub-GHz replay/TX uses ResourceBroker, bounds, explicit confirmation, and an immutable source Capture | conditional | PR-013, PR-014 | S5/S7 |
| CAP-036 | NFC write/restore runs only for a supported owned tag with preview and verify | conditional | PR-013, PR-014 | S5/S7 |
| CAP-037 | Protocol workbench compares pulses/waveforms, annotates fields, and creates derived decodes | P1 | J-06, NFR-008 | S7 |

## Companion and extensibility

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-038 | Local Web/USB companion views, searches, compares, and exports through the same Actions/schema | P1 | PR-012 | S6 |
| CAP-039 | App descriptor declares capabilities, resources, permissions, safety, and strings before launch | P1 | PR-002, PR-013 | S7 |
| CAP-040 | Decoder/profile packages have version compatibility, integrity/signature, and scoped storage | P1 | PR-010, PR-012 | S7/S8 |
| CAP-041 | SDK includes a sample extension, simulator trace kit, and checks that cannot bypass leases/policy | P1 | PR-012, PR-013, NFR-006 | S7 |

## Identification and device maintenance

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-044 | Offline OUI/BLE company/services/protocol profiles enrich facts with version and provenance without replacing source evidence | P1 | PR-008, PR-019 | S6 |
| CAP-045 | One feedback service owns WS2812 and buzzer: quiet mode, idle GPIO2 LOW, bounded tones, and non-color-only capture/proximity/fault cues | P1, conditional HW-T09 for sound | PR-009, PR-011, PR-016, NFR-010 | S5/S6 |
| CAP-046 | Local Wi-Fi/USB connectivity setup keeps secrets separate, never exports them, and never makes networking a Survey/Library prerequisite | P0 for PR-010/012 | PR-010, PR-012, PR-017 | S2/S6/S8 |
| CAP-047 | Versioned backup/restore and factory reset show scope/preview/checksum and never overwrite raw Capture without explicit confirmation | P1 | PR-005, PR-010, PR-018, NFR-008/009 | S5/S8 |

## Explicitly after 1.0

Cloud accounts and default telemetry, a public executable-app marketplace, broad
support for unrelated ESP32 boards, hidden/disruptive actions, and attack count as a
parity metric are not 1.0 commitments. A post-1.0 candidate gets its own user job,
risk review, and stage proposal; it is not inserted retroactively.

## Completeness gates

- **S1 scope gate:** every `CAP-*` has a requirement, priority, and stage; the
  catalog and explicit exclusions pass product review.
- **S2 UX gate:** every section has a navigation/state baseline on the real TFT,
  including disabled/error/empty/running/confirm states.
- **S7 feature-complete gate:** every P0/P1 and applicable conditional capability
  has a complete path or an explicitly accepted `deferred/rejected` requirement.
- **S8 release-complete gate:** every P0 is verified, no P0/P1 defects remain open,
  and applicable P1 capabilities pass the release matrix.
