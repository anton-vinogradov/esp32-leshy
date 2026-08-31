# ESP32-Leshy 1.x product requirements

Document status: **accepted 1.0 baseline, expanded by product decision**, 1 September 2026.

This document turns the [product vision](VISION.md) and
[competitive analysis](COMPETITIVE_ANALYSIS.md) into a testable 1.0.0 boundary.
Wording and acceptance may be refined through governance, while scope and IDs are
fixed for decision and test traceability.

## Product promise

ESP32-Leshy 1.x is an autonomous field tool that collects observations from the
available ESP32-DIV radios into one session, helps investigate a signal source, and
preserves verifiable source data for later analysis. It remains useful without a
phone, account, or internet connection.

Its product identity is an **evidence-first multi-radio instrument with a separate,
bounded Owned Lab**. Passive inspection and reproducible evidence are the default;
active experiments exist only as named, scoped recipes for equipment the operator
owns or is explicitly authorized to test.

## User jobs

- **J-01 Survey:** record the radio environment in one session and see what changed.
- **J-02 Identify/locate:** inspect evidence and RSSI history, then approach a source.
- **J-03 Capture:** preserve source data with time, location, and receiver context.
- **J-04 Compare:** compare sessions or captures without manually reviewing all data.
- **J-05 Diagnose:** see modules, conflicts, and remediation before an action fails.
- **J-06 Authorized lab:** reproduce an owned signal with visible parameters, a
  deadline, and immediate physical stop.
- **J-07 Defensive field inspection:** detect, explain, and preserve evidence of
  suspicious wireless activity without turning observation into an automatic attack.
- **J-08 Secure and automate owned equipment:** protect local evidence, inspect an
  explicitly selected serial/BLE target, and run permissioned bounded automation.

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
| PR-006 | Reopen and manage evidence offline after reboot | Lists, details, and source captures work with radios inactive; delete uses recoverable Trash/Undo before permanent purge | P0 |
| PR-007 | Export portable data | PCAP where compatible, JSON/CSV summaries, Flipper-compatible `.sub`, and compatible IR/NFC formats where feasible | P0/P1 |
| PR-008 | Preserve Target history, notes, tags, and identity links | Merge/split is reversible; automatic links expose confidence/evidence | P1 |
| PR-009 | Diagnose resources, firmware workflows, and installed hardware through an explicit Self-Test app | Home→Device→Self-Test offers read-only Quick and scoped Full/Guided modes; both use the same versioned checks as release HIL, report `not_applicable/blocked` honestly, leave zero leases, and save an exportable report; no Self-Test runs automatically at boot | P0 |
| PR-010 | Document install, update, and recovery | Browser install, signed stable/beta OTA, signed SD update, rollback, and recovery pass HIL | P0 |
| PR-011 | Provide an accessible, configurable core experience in EN/RU | One build switches language without truncating critical copy; font scale, contrast/reduced-motion, input repeat, favorites, hidden apps, and shortcuts persist locally | P1 |
| PR-012 | Use the same Actions/schema in the local companion | Offline viewing/export; permissions are no broader than the local session | P1 |
| PR-013 | Restrict active actions to Lab context | Parameters, indication, timer, and stop are visible; panic/expiry physically stops TX | P0 for any shipped TX |
| PR-014 | Cover documented ESP32-DIV v2 configurations | Main board and RF shield have probes/baseline workflows; GPS and PN532 use separate explicit assembly profiles without GPIO5/6 contention | P0 |
| PR-015 | Preserve verifiable passive evidence through Field Capture | Wi-Fi packet/channel monitor produces a bounded immutable Capture and compatible PCAP with drop counters; a real-TFT screenshot includes build/state/time provenance; neither path enables hidden TX | P0 for Wi-Fi capture, P1 for screenshot |
| PR-016 | Route visual and sound feedback through one safe service | Apps cannot access WS2812/buzzer directly; quiet mode persists; GPIO2 stays LOW outside a bounded tone; fault/TX/critical state is understandable without sound or color | P1, sound conditional on HW-T09 |
| PR-017 | Keep connectivity offline-first and secrets scoped | Wi-Fi/USB setup stores credentials outside Sessions/reports/backups; Survey/Library work without a network; OTA/companion receive only explicitly granted scope | P0 for PR-010/012 |
| PR-018 | Make backup/restore and factory reset safe for user data | Scope, schema, checksum, and overwrite plan appear before execution; cancel changes nothing; raw Capture is never replaced silently; restore/reset have recovery tests | P1 |
| PR-019 | Keep offline enrichment subordinate to source facts | OUI/BLE/protocol database exposes version/provenance; missing or stale data leaves raw identity available and never invents correlation | P1 |
| PR-020 | Detect suspicious wireless conditions passively and explain every alert | Airspace Guard exposes named detector profiles and sensitivity, labels detector/version/threshold/confidence, covers WPA3/PMF/SAE and cross-radio jamming indicators, and opens exact source evidence; insufficient data remains inconclusive and never triggers an active response | P1 |
| PR-021 | Capture Wi-Fi authentication evidence as a focused passive workflow | EAPOL/PMKID and complete/incomplete handshake state are explicit; immutable evidence exports compatible PCAP and `hc22000` with provenance; no active provocation occurs outside a separately admitted Lab recipe | P1 |
| PR-022 | Provide an offline Field Survey workflow | Wi-Fi AP/station and BLE observations are deduplicated and, when GPS is available, bound to a track with satellite diagnostics, POIs, and field notes; revisit comparison and WiGLE-compatible local export preserve source IDs and uncertainty without requiring cloud upload | P1 |
| PR-023 | Inspect BLE beyond advertisement summaries without hidden connection | Compatible raw packets remain exportable; connected GATT enumeration requires an explicit mode transition, selected target, permission, visible connection state, separate lease, and deterministic disconnect/cleanup | P1 |
| PR-024 | Protect local secrets and evidence through Device Lock | First-run/local PIN setup, bounded retry and documented recovery cannot bypass safe cleanup, panic, update recovery, or factory reset; the lock overlay may continue a previously admitted safe Capture but controls, identities, and exports reveal no protected content; the owner can explicitly disable PIN protection without deleting or re-encrypting existing data and can enroll a new PIN later | P0 before a release stores credentials or sensitive captures |
| PR-025 | Expose a bounded [Serial Console and shared Actions CLI](SERIAL_CONSOLE.md) | User explicitly selects a named UART profile/baud/mode and target; ResourceBroker owns the session; exit/error releases it; CLI permissions are no broader than on-device Actions and raw GPIO control is absent | P1 |
| PR-026 | Run [permissioned signed automation and explicitly scoped HID workflows](AUTOMATION_HID.md) | Package signature/version/permissions, resource ceilings, action preview, finite runtime and cancel/panic are mandatory; USB/BLE HID requires a confirmed target/scope, while BadUSB inspection is passive by default | P1 |
| PR-027 | Ship only named, individually accepted wireless Lab recipes | Every Wi-Fi/BLE/nRF/IR recipe declares owned fixture/target, region, channel/frequency, power, duration, expected evidence and hardware stop path; targeted handshake-assist, synthetic iBeacon/identity emulation, MouseJack injection, bounded robustness/crash and IR-camera tests are admitted only when target and containment are proven; unbounded or indiscriminate output and secret harvesting are rejected | P0 for any shipped active output |
| PR-028 | Capture and inspect nRF24 ESB evidence | Compatible ESB packets are retained and decoded; passive MouseJack detection is available; injection exists only as a separately admitted Owned Lab fixture recipe | P1 |
| PR-029 | Provide a read-only Live Companion | USB Wireshark/extcap streams compatible Wi-Fi/BLE evidence and mirrors the TFT without changing the host network, widening permissions, or becoming required for autonomous use | P1 |
| PR-030 | Provide advanced NFC/EMV inspection within hardware capability | Conditional PN532 workflows cover NDEF/ISO14443-4 emulation, erase, bounded owned-tag recovery, and redacted EMV protocol metadata; PAN, expiry, submitted PIN, and equivalent payment secrets are never retained | P1, conditional PN532 |
| PR-031 | Control Leshy's own and synthetic lab identities | STA/AP randomization is locally configurable; identity emulation derives only from an owned Capture or explicit synthetic template and is ephemeral, provenance-labeled, time-bounded, and confined to Owned Lab | P1 |
| PR-032 | Inspect physical USB devices safely | Conditional USB Host shows VID/PID/class/interfaces and bounded signed keyboard/HID inspection only after OTG/VBUS/current-limit and deterministic cleanup qualification | P1, conditional hardware profile |
| PR-033 | Verify owned evidence without disguising cracking as observation | Bounded local or companion-assisted verification supports owned Wi-Fi/NFC/Sub-GHz/fixed-code evidence with preview, budget, pause/stop, checkpoint and provenance; leaked/default secret corpora are not bundled | P1 |
| PR-034 | Test an owned isolated network fixture | Read-only LAN inventory is available normally; captive-portal/ARP/DHCP/MITM robustness recipes require an explicitly selected isolated fixture, bounded duration and physical Stop; a training portal records the outcome, never the submitted secret | P1 |

## System requirements

| ID | Budget or invariant |
|---|---|
| NFR-001 | Cold boot to an interactive screen ≤ 2 s on a healthy standard setup |
| NFR-002 | Back is handled ≤ 150 ms and releases foreground leases |
| NFR-003 | UI callbacks block a core ≤ 10 ms; long operations are cancellable |
| NFR-004 | A release endurance run covers at least 45 minutes and eight complete passive Survey cycles, finishes within a one-hour operational budget, and has no monotonic heap growth, UI freeze, drops, leaked leases, or Session corruption |
| NFR-005 | Queues are bounded; overflow is measured and cannot corrupt memory |
| NFR-006 | No driver/app uses shared radio/SPI/UART/filesystem outside a lease/service contract |
| NFR-007 | Imported formats have bounds tests and fuzz corpora; malformed input cannot reboot the device |
| NFR-008 | Source Captures are immutable; decode/edit operations create derived data |
| NFR-009 | Schemas migrate forward or fail clearly without source-data loss |
| NFR-010 | Critical state never depends on color alone; standard buttons operate all core workflows |
| NFR-011 | Real submitted credentials, payment identifiers, PINs, and equivalent secrets are never retained in persistence, logs, screenshots, reports, or exports; useful protocol metadata is minimized and redacted |
| NFR-012 | Every active output has an explicit selected target or qualified fixture, declared scope and expiry, visible state, deterministic cleanup, and physical Stop; broadcast stress/interference requires proven isolation/interlock |
| NFR-013 | No app, script, signed package, developer mode, or companion command can bypass ResourceBroker, Safety Supervisor, watchdog, permission review, expiry, or physical Stop |

## 1.0.0 boundary

In scope: an independent ESP32-DIV v2 build; Diagnostics, Survey, Targets,
Capture/Library, settings; passive baseline workflows for all standard receivers;
Airspace Guard, focused Wi-Fi authentication Capture, offline Field Survey, BLE
Inspector, nRF24 ESB Workbench, Advanced NFC/EMV, USB Host Inspector, Owned Evidence
Verification and Owned Network Lab; Device Lock, Privacy Identity, bounded Serial
Console/Actions CLI, and read-only Live Companion; permissioned signed automation/HID
and individually admitted wireless/IR Lab recipes; Wi-Fi packet/PCAP Capture,
screenshot evidence, versioned offline enrichment and portable `.sub`; SafetyPolicy-
approved IR/NFC work on owned devices; SD/LittleFS storage and portable exports;
scoped connectivity, safe LED/buzzer feedback, backup/restore/factory reset; browser
install, signed OTA/SD update, rollback/recovery; EN/RU UI; host, HIL, and endurance
gates.

Not required for 1.0.0: other boards without a profile owner and HIL target; cloud
accounts or default telemetry; public executable catalogs/mobile sync before SDK and
threat-model stability; authenticated DIV-to-DIV Peer Link; unexplained or
irreversible identity correlation. Those are deferred scope, not permission to relax
NFR-011…NFR-013.

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

## Baseline acceptance record

`E-GATE-001` accepts the 1.0 baseline because:

- the [hardware map](HARDWARE_ENVELOPE.md) is supported by schematic, 0.x code, and
  safe board-01 HIL; unavailable instruments, a second board, and optional assemblies
  have fail-closed defaults plus named S4/S5/S8 evidence instead of invented claims;
- J-01…J-08 have happy/error/cancel paths in the
  [reference workflows](REFERENCE_WORKFLOWS.md);
- every P0 traces to an architecture component and test type;
- flash/RAM/storage budgets are measured, while power/shared-bus limits are explicitly
  constrained in the [resource budget ledger](RESOURCE_BUDGETS.md).

`accepted` fixes mandatory scope; `implemented` and `verified` are assigned separately
from evidence at the applicable S2…S8 gates.
