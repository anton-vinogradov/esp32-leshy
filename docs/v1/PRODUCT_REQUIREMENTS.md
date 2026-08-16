# ESP32-Leshy 1.x product requirements

Document status: **draft 0.2 after product review**, 16 August 2026.

This document turns the [product vision](VISION.md) and
[competitive analysis](COMPETITIVE_ANALYSIS.md) into a testable 1.0.0 boundary. It
will be refined after the hardware map and reference-workflow validation; IDs are
already stable for decision and test traceability.

## Product promise

ESP32-Leshy 1.x is an autonomous field tool that collects observations from the
available ESP32-DIV radios into one session, helps investigate a signal source, and
preserves verifiable source data for later analysis. It remains useful without a
phone, account, or internet connection.

## User jobs

- **J-01 Survey:** record the radio environment in one session and see what changed.
- **J-02 Identify/locate:** inspect evidence and RSSI history, then approach a source.
- **J-03 Capture:** preserve source data with time, location, and receiver context.
- **J-04 Compare:** compare sessions or captures without manually reviewing all data.
- **J-05 Diagnose:** see modules, conflicts, and remediation before an action fails.
- **J-06 Authorized lab:** reproduce an owned signal with visible parameters, a
  deadline, and immediate physical stop.

## Product terms

- **Observation:** an immutable reception fact with time, source, channel/frequency,
  RSSI, and an optional payload reference.
- **Target:** a durable local entity joining identities and observation history;
  automatic correlation is explainable and reversible.
- **Capture:** an immutable source blob plus derived decodes.
- **Session:** a bounded observation context including device configuration and
  location when available.
- **Action:** one domain operation shared by UI, CLI, Web UI, and tests.
- **Capability:** a feature confirmed by the build and boot probe on this device.
- **Resource lease:** explicit, bounded ownership of hardware or a system resource.

## 1.0.0 functional requirements

| ID | Requirement | Acceptance summary | Priority |
|---|---|---|---|
| PR-001 | Identify the main board and assembly profile, then safely probe eligible modules | Diagnostics reports declared/detected/available/conflicted/fault/unknown with evidence; ambiguity never triggers trial output modes | P0 |
| PR-002 | Build menus from capabilities | An unavailable action is hidden or disabled with an explanation before launch | P0 |
| PR-003 | Survey creates one Session | Wi-Fi/BLE and all available detected receivers share a timeline with honest duty cycle; absent external GPS/PN532 is not a defect | P0 |
| PR-004 | Shared List/Detail/Radar patterns | Back, filters, and units behave consistently across supported radios | P0 |
| PR-005 | Persist Session/Capture atomically | Power loss cannot corrupt previously committed data | P0 |
| PR-006 | Reopen a Session offline after reboot | Lists, details, and source captures work with radios inactive | P0 |
| PR-007 | Export portable data | PCAP where compatible, JSON/CSV summaries, and compatible IR/NFC/Sub-GHz formats where feasible | P0/P1 |
| PR-008 | Preserve Target history, notes, tags, and identity links | Merge/split is reversible; automatic links expose confidence/evidence | P1 |
| PR-009 | Diagnose resources and basic modules | Self-test performs no transmission and saves an exportable report | P0 |
| PR-010 | Document install, update, and recovery | Browser install, signed stable/beta OTA, rollback, and recovery pass HIL | P0 |
| PR-011 | Provide the core experience in EN/RU | One build switches language without truncating critical copy | P1 |
| PR-012 | Use the same Actions/schema in the local companion | Offline viewing/export; permissions are no broader than the local session | P1 |
| PR-013 | Restrict active actions to Lab context | Parameters, indication, timer, and stop are visible; panic/expiry physically stops TX | P0 for any shipped TX |
| PR-014 | Cover documented ESP32-DIV v2 configurations | Main board and RF shield have probes/baseline workflows; GPS and PN532 use separate explicit assembly profiles without GPIO5/6 contention | P0 |
| PR-015 | Preserve verifiable passive evidence through Field Capture | Wi-Fi packet/channel monitor produces a bounded immutable Capture and compatible PCAP with drop counters; a real-TFT screenshot includes build/state/time provenance; neither path enables hidden TX | P0 for Wi-Fi capture, P1 for screenshot |
| PR-016 | Route visual and sound feedback through one safe service | Apps cannot access WS2812/buzzer directly; quiet mode persists; GPIO2 stays LOW outside a bounded tone; fault/TX/critical state is understandable without sound or color | P1, sound conditional on HW-T09 |
| PR-017 | Keep connectivity offline-first and secrets scoped | Wi-Fi/USB setup stores credentials outside Sessions/reports/backups; Survey/Library work without a network; OTA/companion receive only explicitly granted scope | P0 for PR-010/012 |
| PR-018 | Make backup/restore and factory reset safe for user data | Scope, schema, checksum, and overwrite plan appear before execution; cancel changes nothing; raw Capture is never replaced silently; restore/reset have recovery tests | P1 |
| PR-019 | Keep offline enrichment subordinate to source facts | OUI/BLE/protocol database exposes version/provenance; missing or stale data leaves raw identity available and never invents correlation | P1 |

## System requirements

| ID | Budget or invariant |
|---|---|
| NFR-001 | Cold boot to an interactive screen ≤ 2 s on a healthy standard setup |
| NFR-002 | Back is handled ≤ 150 ms and releases foreground leases |
| NFR-003 | UI callbacks block a core ≤ 10 ms; long operations are cancellable |
| NFR-004 | An 8-hour passive Survey has no monotonic heap growth, UI freeze, or Session corruption |
| NFR-005 | Queues are bounded; overflow is measured and cannot corrupt memory |
| NFR-006 | No driver/app uses shared radio/SPI/UART/filesystem outside a lease/service contract |
| NFR-007 | Imported formats have bounds tests and fuzz corpora; malformed input cannot reboot the device |
| NFR-008 | Source Captures are immutable; decode/edit operations create derived data |
| NFR-009 | Schemas migrate forward or fail clearly without source-data loss |
| NFR-010 | Critical state never depends on color alone; standard buttons operate all core workflows |

## 1.0.0 boundary

In scope: an independent ESP32-DIV v2 build; Diagnostics, Survey, Targets,
Capture/Library, settings; passive baseline workflows for all standard receivers;
Wi-Fi packet/PCAP Capture, screenshot evidence, versioned offline enrichment;
SafetyPolicy-approved IR/NFC work on owned devices; SD/LittleFS storage and portable
exports; scoped connectivity, safe LED/buzzer feedback, backup/restore/factory reset;
browser install, OTA/rollback/recovery; EN/RU UI; host, HIL, and endurance gates.

Not required for 1.0.0: other boards without a profile owner and HIL target; cloud
accounts or default telemetry; an executable app store before SDK/threat-model
stability; attack-count parity; unexplained or irreversible identity correlation.

## First vertical slice: Survey Session

1. The clean 1.x target boots and runs HardwareProbe.
2. The user opens Survey and starts a session.
3. One passive source publishes normalized Observations.
4. The shared List opens Detail and Back behaves correctly.
5. Stop atomically persists the Session.
6. The Session reopens after reboot with radios inactive.
7. A JSON summary exports successfully.
8. Host tests cover domain/storage/navigation; HIL covers boot/input/source/stop.
9. A missing source explains itself and leaves no lease behind.

The first source is selected after the hardware map. Passive Wi-Fi scan is the
provisional candidate because it needs no external module while exercising the full
data path.

## Baseline gate

The draft becomes the 1.0 baseline after the [hardware map](HARDWARE_ENVELOPE.md) is
confirmed against the schematic, 0.x code, and `HW-T01…HW-T11` on an ESP32-DIV v2;
J-01…J-06 have happy/error/cancel paths in the
[reference workflows](REFERENCE_WORKFLOWS.md);
every P0 traces to an architecture component and test type; and flash, RAM, storage,
and power budgets are measured or explicitly constrained in the
[resource budget ledger](RESOURCE_BUDGETS.md).
