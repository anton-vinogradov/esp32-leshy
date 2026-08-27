# ESP32-Leshy 1.x competitive analysis

Market snapshot: **15 August 2026**.

Feature-level parity audit: **27 August 2026**.

This is a product-direction document, not a firmware leaderboard. Projects are
compared by how well they support an end-to-end workflow:

> discover → identify → locate → capture → compare → safely reproduce in an
> owned lab → preserve or export the result.

A larger collection of isolated features is not, by itself, a product advantage.

## Method

The review uses the projects' official repositories and documentation. It is a
qualitative review of documented capabilities, not a controlled hardware
benchmark. The main dimensions are ESP32-DIV hardware depth, passive discovery,
capture and export, common action semantics across front ends, extensibility,
field UX, portability, release safety, testability, and shared-resource safety.

## Strategic comparison set

### ESP32-DIV original

The [original ESP32-DIV firmware](https://github.com/CiferTech/ESP32-DIV) is the
hardware and feature-coverage baseline. It demonstrates the device's breadth
across Wi-Fi, BLE, NRF24, Sub-GHz, IR, NFC, GPS, and system utilities. Leshy should
retain that hardware depth while replacing isolated screens with connected
workflows and durable artifacts.

### GhostESP

[GhostESP](https://github.com/GhostESP-Revival/GhostESP) is the closest strategic
reference for firmware as a platform. Its documented direction includes an
ESP-IDF-native core, shared commands across several front ends, portable capture
formats, multi-ESP operation, Lua and native applications, permissions, and
scoped storage.

Leshy should match the unified action and data pipeline, then differentiate with
deep ESP32-DIV integration, deterministic handling of conflicting pins/buses, a
strict Observation/Target/Session model, and a complete offline-first workflow.

### Bruce

[Bruce](https://github.com/BruceDevices/firmware) is a benchmark for feature
breadth, board portability, community contribution, scripting, and accessible
installation. Leshy should adopt clear board adapters and an easy contribution
path, but should not expand its board matrix before the core data, resource, and
workflow contracts are stable on ESP32-DIV.

### ESP32 Marauder

[ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder) is a mature,
focused benchmark for Wi-Fi/BLE field workflows, PCAP/SD capture, hardware
variants, and releases. Leshy should match dependable capture and export, then go
beyond the single-radio view with cross-radio sessions, comparison, source
location, and a shared observation library.

### Flipper Zero firmware

The [official Flipper Zero firmware](https://github.com/flipperdevices/flipperzero-firmware)
targets different hardware but is a benchmark for product cohesion: stable
applications, an SDK boundary, portable file formats, system/user application
separation, predictable navigation, and an extension ecosystem.

Leshy should use similarly durable application and file contracts while joining
Wi-Fi/BLE and external radios in a single session and using ESP32 networking for
a local companion interface.

## Secondary references

- [NEMO](https://github.com/n0xa/m5stick-nemo) is useful for predictable
  button-driven navigation and clear positioning, but is not the Leshy
  architecture target.
- [CapibaraZero](https://github.com/CapibaraZero/fw) is archived and directs users
  to Bruce. It is a useful warning that platform sustainability matters more than
  an ambitious feature inventory.

## Qualitative matrix

The labels describe documented product emphasis, not the presence or absence of
an individual feature.

| Project | ESP32-DIV / multi-radio | Wi-Fi capture | Data and export | Extensions | Multiple front ends | Cohesive UX |
|---|---|---|---|---|---|---|
| ESP32-DIV original | strong | present | limited | limited | limited | limited |
| GhostESP | present | strong | strong | strong | strong | strong |
| Bruce | broad board support | present | present | present | present | present |
| ESP32 Marauder | limited | strong | strong | limited | present | strong in its niche |
| Flipper Zero | different hardware | limited | strong | strong | ecosystem strength | strong |
| Leshy 1.x target | deep support | strong | strong | strong after 1.0 | strong | unified cross-radio UX |

## Feature-level parity audit

The qualitative matrix above describes product direction; it does **not** prove
that every useful competitor workflow exists in the Leshy catalog. The second
review checked the current official feature inventories of
[ESP32-DIV](https://github.com/cifertech/ESP32-DIV/wiki/Features),
[GhostESP](https://github.com/GhostESP-Revival/GhostESP),
[Bruce](https://github.com/brucedevices/firmware),
[ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder/wiki/marauder-versions),
[Flipper Zero](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/ReadMe.md),
and, as a secondary defensive reference,
[NEMO](https://github.com/n0xa/m5stick-nemo/blob/main/README.md). It compares
user outcomes rather than menu spelling or every protocol toggle.

Verdict: **CAP-001…CAP-047 were coherent for the previously frozen scope, but were
not a complete competitor-feature inventory.** The product decision of 27 August
accepts eight of the nine audited families as `CAP-048…CAP-055`; each now has normal
`J/PR/CAP/risk/stage` traceability and an S7 owner. `CF-005 Peer Link` remains an
explicit post-1.0 item rather than a hidden requirement.

| Feature family found in official competitor docs | Current Leshy coverage | Audit result |
|---|---|---|
| Board probe, capability-aware UI, settings, power, diagnostics, install/update/recovery | CAP-001…008, CAP-045…047 | explicit and stronger as one lifecycle |
| Buttons/touch, stable navigation, themes, brightness and accessible feedback | CAP-004/005/045 | explicit |
| Session, Capture, Library, SD/LittleFS integrity, portable formats and backup | CAP-009/023…031/040/043/047 | explicit; raw arbitrary-file manager deliberately omitted |
| One command model across device, automation, USB and local Web | CR-001, PR-012, CAP-038/041 | platform contract exists; interactive serial monitor/UART bridge is not a user capability (`CF-007`) |
| Wi-Fi network/client discovery, vendor/facts, hidden-name enrichment and radar | CAP-010/016/017/044 | explicit |
| Wi-Fi channel view, packet monitor, raw frame Capture and PCAP | CAP-023/026/042 | explicit |
| EAPOL/PMKID/4-way-handshake recognition, focused capture and `hc22000`/live-analysis export | only generic raw Capture/PCAP | real workflow is missing (`CF-002`) |
| Wi-Fi AP/station and BLE wardriving with GPS track and WiGLE-compatible local result | CAP-009/011/014/023/026 provide parts | finished field workflow is missing (`CF-003`) |
| Passive deauth/PineAP/evil-twin/WPS, tracker/skimmer/drone and jamming-warning views | individual observations may exist | defensive detection and explained alert workflow is missing (`CF-001`) |
| BLE scan, identity/vendor/service advertisement facts and radar | CAP-011/016/017/044 | explicit |
| BLE raw packet Capture/Wireshark path and opt-in GATT/service/characteristic inspection | generic sniff/export wording only | raw acceptance needs refinement; connected GATT inspection is missing (`CF-004`) |
| nRF24/Sub-GHz spectrum, waterfall, finder, RAW/decode/library and bounded replay | CAP-012/013/030/035/037/040 | explicit |
| IR learn/decode/library/replay and portable/universal profile packages | CAP-029/034/040 | covered by the generic profile model; TV-B-Gone is a profile, not another architecture |
| NFC read/dump/decode, portable data and verified write/restore | CAP-031/036/040 | explicit for the declared PN532 assembly |
| Authenticated peer operation, remote receiver/source and two-device evidence exchange | no user capability | missing (`CF-005`) |
| First-run setup, local PIN/lock and protection of captures/secrets on a lost device | secret storage exists, access control does not | missing (`CF-006`) |
| Executable SD apps/scripts plus USB/BLE HID and defensive BadUSB inspection | descriptors/SDK exist but no runtime/HID outcome | absent from 1.0 (`CF-008`) |
| Concrete authorized Wi-Fi/BLE/nRF lab recipes | CAP-032/033 define safety; CAP-034…036 cover only IR/Sub-GHz/NFC actions | wireless Lab action set is undecided (`CF-009`) |
| General LAN discovery, port/service/banner scan, SSH/Telnet, ARP tools and VPN | no coverage | adjacent network-toolkit job, deliberately outside current core |
| LF RFID/iButton, FM, Zigbee/802.15.4, Ethernet, camera, microphone/audio and printer | stock ESP32-DIV lacks the required assemblies | conditional expansion, not 1.0 parity |
| Jammers, broad floods/spam, credential-harvesting portals and disruptive clone/crash actions | no coverage | deliberately rejected as a feature-count target |
| U2F, games, decorative clocks and generic QR utilities | no coverage | useful on other products, but not part of the Leshy radio-observation job |

### Audited gaps and final scope decision

| ID | Candidate user outcome | Why it is materially different from an existing row | Final disposition |
|---|---|---|---|
| CF-001 | **Airspace Guard** passively detects and explains deauth/disassociation bursts, PineAP/evil-twin indicators, suspicious BLE trackers/skimmers/drone IDs and loss/jamming indicators; alerts always open source evidence | CAP-042 records frames but does not turn them into a defensive conclusion | accepted as `CAP-048`, `PR-020`, S7; RX-only and evidence-backed |
| CF-002 | **Wi-Fi authentication Capture** recognizes EAPOL, PMKID and completed/incomplete handshakes, saves focused evidence, and exports PCAP plus `hc22000`; live host streaming stays local and bounded | a generic PCAP does not tell the user whether usable authentication evidence was captured | accepted as `CAP-049`, `PR-021`, S7; passive path only outside an approved Lab recipe |
| CF-003 | **Field Survey** records Wi-Fi AP/station and BLE observations with GPS track, deduplication, revisit comparison and WiGLE-compatible local export | GPS metadata plus generic CSV is not an end-to-end wardriving job | accepted as `CAP-050`, `PR-022`, S7; direct cloud upload remains optional/post-1.0 |
| CF-004 | **BLE Inspector** preserves raw compatible packets and, after an explicit connected-mode transition, enumerates GATT services/characteristics with provenance | advertisement service IDs are not GATT inspection | accepted as `CAP-051`, `PR-023`, S7; connected GATT is explicit, permissioned and separately leased |
| CF-005 | **Peer Link** securely pairs two DIVs for remote receiver/source control, evidence transfer and repeatable dual-device test scenarios | the current companion is host-to-device and cannot use one DIV to verify another | explicitly deferred until after 1.0; no `CAP-*` is reserved |
| CF-006 | **Device Lock** provides first-run security setup, local PIN/lock, bounded retry/recovery and protects secrets and saved evidence without disabling safe capture cleanup | scoped secrets protect data at rest from export, not from physical UI access | accepted as `CAP-052`, `PR-024`, S7 |
| CF-007 | **Serial Console** offers a bounded on-device serial monitor/UART bridge and the documented Actions CLI without bypassing policy or leases | diagnostics/logs do not operate another UART target | accepted as `CAP-053`, `PR-025`, S7; raw GPIO control remains outside the base product |
| CF-008 | **Automation/HID** runs permissioned signed scripts and explicitly scoped USB/BLE HID or BadUSB-inspection workflows | CAP-039…041 describe extension contracts, not an executable user outcome | accepted as `CAP-054`, `PR-026`, S7; defensive inspection is passive and HID execution is explicit/scoped |
| CF-009 | **Authorized wireless Lab recipes** provide named, bounded Wi-Fi/BLE/nRF fixture workflows instead of an empty generic TX shell | CAP-032/033 make TX safe but do not define which wireless experiments exist | accepted as `CAP-055`, `PR-027`, S7; recipes are admitted individually and never include jamming, indiscriminate flood, crash or credential harvest |

### Audit accounting

- **Explicitly represented:** the complete passive multi-radio foundation,
  on-device analysis, durable evidence, IR/NFC/Sub-GHz owned-lab paths, update,
  recovery, companion, settings, feedback and extension boundaries.
- **Accepted into 1.x:** `CF-001…CF-004` and `CF-006…CF-009`, now
  `CAP-048…CAP-055` with S7 ownership.
- **Explicitly after 1.0:** `CF-005 Peer Link`.
- **Intentionally not copied:** broad disruption, social-engineering credential
  capture, generic LAN attack tooling, and functions requiring unrelated hardware.
- **Scope claim:** the project now has a traced 55-capability 1.x baseline covering
  every accepted useful competitor family; that is not a claim that all 55 are
  implemented or verified yet.

## What 1.x must match

- reliable browser installation, OTA, and recovery;
- full probing of the standard ESP32-DIV modules and honest unavailable states;
- stable list, detail, signal/radar, and timeline views;
- session recording to SD and export in common formats;
- a library of saved signals, devices, and sessions;
- 0.x hardware parity for IR, NFC, GPS, NRF24, and CC1101 before 1.0;
- versioned configuration formats and migrations.

## Where 1.x should lead

1. A common Observation/Target/Session domain model across radios.
2. One cross-radio survey that safely schedules mutually exclusive hardware.
3. Explicit leases for SPI, radio modes, GPIO, memory, storage, and display.
4. Durable, timestamped data as the default output of discovery.
5. One action semantic for buttons, CLI, local Web UI, and automation.
6. Clear separation and confirmation of passive and active lab workflows.
7. Complete offline operation; a companion interface enhances rather than
   unlocks the product.
8. Host-tested workflows, hardware-in-the-loop drivers, verified manifests, and
   a known rollback path.
9. A single bilingual string contract plus contrast, scale, and button-only
   accessibility.

## What we deliberately do not copy

- feature-count competition and giant menus;
- separate implementations of the same action per front end;
- dozens of boards before the platform contract is stable;
- plugins with unrestricted hardware or filesystem access;
- proprietary formats where a portable format exists;
- indistinguishable passive monitoring and active lab functions.

## Derived requirements

| ID | Requirement | Priority |
|---|---|---|
| CR-001 | One Action/Command API for UI, CLI, Web UI, and automation | P0 |
| CR-002 | Sessions and capture files are first-class objects | P0 |
| CR-003 | Application descriptors, capabilities, permissions, and scoped storage | P1 |
| CR-004 | Menus and actions reflect detected hardware | P0 |
| CR-005 | PCAP and compatible IR/NFC/Sub-GHz formats where feasible | P0/P1 |
| CR-006 | Contrast, text scale, button navigation, and no color-only state | P1 |
| CR-007 | A useful offline local Web/USB companion | P1 |
| CR-008 | Stable/beta channels, signed manifest, verification, and rollback | P0 |
| CR-009 | Resource leases and safe degradation under hardware conflicts | P0 |
| CR-010 | Scenario- and result-oriented navigation | P0 |

These feed the [product requirements](PRODUCT_REQUIREMENTS.md) and must trace to
an architecture decision, test, and acceptance criterion.

## Decision

1.x starts from three foundations: this competitive snapshot, a map of actual
ESP32-DIV capabilities and conflicts, and the target user jobs/workflows. The 1.0
requirements and architecture boundary are frozen only after those foundations.

The first implementation slice is a complete **Survey Session**, not an isolated
driver: probe available hardware, collect passive observations, show a unified
list and details, and persist the session.
