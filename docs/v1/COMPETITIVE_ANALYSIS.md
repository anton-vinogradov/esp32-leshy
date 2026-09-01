# ESP32-Leshy 1.x competitive analysis

Market snapshot: **15 August 2026**.

Feature-level parity audit: **27 August 2026**; official-source re-audit completed
**1 September 2026**.

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

The 1 September re-audit superseded the earlier claim that the 55-row catalog
already covered every useful competitor outcome. The owner accepted every useful
result compatible with an evidence-first multi-radio instrument and a separate
bounded Owned Lab. Refinements landed in existing rows and seven distinct outcomes
became `CAP-056…CAP-062`; **62 is now the fixed 1.0 denominator**. Deferred
integrations and three non-negotiable safety/privacy boundaries remain visible below.

| Feature family found in official competitor docs | Current Leshy coverage | Audit result |
|---|---|---|
| Board probe, capability-aware UI, settings, power, diagnostics, install/update/recovery | CAP-001…008, CAP-045…047 | explicit and stronger as one lifecycle |
| Buttons/touch, stable navigation, themes, brightness and accessible feedback | CAP-004/005/045 | explicit |
| Session, Capture, Library, SD/LittleFS integrity, portable formats and backup | CAP-009/023…031/040/043/047 | explicit; raw arbitrary-file manager deliberately omitted |
| One command model across device, automation, USB and local Web | CR-001, PR-012, CAP-038/041/053/057 | shared Actions, bounded Serial Console and read-only Live Companion are explicit |
| Wi-Fi network/client discovery, vendor/facts, hidden-name enrichment and radar | CAP-010/016/017/044 | explicit |
| Wi-Fi channel view, packet monitor, raw frame Capture and PCAP | CAP-023/026/042 | explicit |
| EAPOL/PMKID/4-way-handshake recognition, focused capture and `hc22000`/live-analysis export | CAP-049/057/061 | focused passive Capture is accepted; bounded owned-evidence verification and live stream are planned |
| Wi-Fi AP/station and BLE wardriving with GPS track and WiGLE-compatible local result | CAP-050 | accepted end-to-end Field Survey; GPS/POI refinements remain conditional/active |
| Passive deauth/PineAP/evil-twin/WPS, tracker/skimmer/drone and jamming-warning views | CAP-048 | evidence-backed Airspace Guard accepted; expanded named profiles remain active |
| BLE scan, identity/vendor/service advertisement facts and radar | CAP-011/016/017/044 | explicit |
| BLE raw packet Capture/Wireshark path and opt-in GATT/service/characteristic inspection | CAP-051/057 | explicit GATT inspector plus planned read-only live extcap |
| nRF24/Sub-GHz spectrum, waterfall, finder, ESB/RAW/decode/library and bounded replay | CAP-012/013/030/035/037/040/056 | explicit; ESB workbench is planned S7 |
| IR learn/decode/library/replay and portable/universal profile packages | CAP-029/034/040 | covered by the generic profile model; TV-B-Gone is a profile, not another architecture |
| NFC read/dump/decode/emulation/erase/owned-tag recovery, redacted EMV and verified write/restore | CAP-031/036/040/058 | explicit for the declared PN532 assembly |
| Authenticated peer operation, remote receiver/source and two-device evidence exchange | no user capability | missing (`CF-005`) |
| First-run setup, local PIN/lock and protection of captures/secrets on a lost device | CAP-052 | explicit; protected storage/PIN is accepted and lock-overlay refinement is active |
| Executable SD apps/scripts plus USB/BLE HID and defensive BadUSB inspection | CAP-054/060 | permissioned runtime/HID plus conditional physical USB Host Inspector |
| Concrete authorized Wi-Fi/BLE/nRF/IR lab recipes | CAP-032…036/055/056/062 | named Owned Lab set accepted; every active recipe still needs individual containment evidence |
| General LAN discovery and isolated LAN robustness tests | CAP-062 | read-only inventory and bounded Owned Network Lab accepted; generic remote-admin toolbox remains post-1.0 |
| LF RFID/iButton, FM, Zigbee/802.15.4, Ethernet, camera, microphone/audio and printer | stock ESP32-DIV lacks the required assemblies | conditional expansion, not 1.0 parity |
| Targeted stress/interference/identity recipes | CAP-055/056/062 | accepted only for selected owned/authorized isolated fixtures; indiscriminate output and secret retention remain prohibited |
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
| CF-009 | **Authorized wireless Lab recipes** provide named, bounded Wi-Fi/BLE/nRF/IR fixture workflows instead of an empty generic TX shell | CAP-032/033 make active output safe but do not define which experiments exist | accepted as `CAP-055`, `PR-027`, S7; targeted handshake assist, synthetic identity/iBeacon, MouseJack injection, bounded robustness/crash/interference and IR-camera tests are individually admitted only with proven target/containment; indiscriminate output and secret retention remain prohibited |

### Audit accounting

- **Explicitly represented:** the complete passive multi-radio foundation,
  on-device analysis, durable evidence, IR/NFC/Sub-GHz owned-lab paths, update,
  recovery, companion, settings, feedback and extension boundaries.
- **Accepted into 1.x:** `CF-001…CF-004` and `CF-006…CF-009`, now
  `CAP-048…CAP-055` with S7 ownership.
- **Explicitly after 1.0:** `CF-005 Peer Link`.
- **Accepted from the 1 September re-audit:** all valuable refinements plus
  `CAP-056…CAP-062`, under the same S7 evidence and safety gates.
- **Hard exclusions:** retaining real submitted credentials/payment secrets;
  unbounded or indiscriminate active output; bypassing broker/safety/watchdog/Stop.
- **Scope claim:** the project has a traced, frozen **62-capability** 1.x baseline
  covering every current useful competitor outcome accepted for this product. This
  is a scope claim, not a claim that all 62 are implemented or verified.

### 1 September 2026 re-audit ledger

Seven separate official-source reviews checked every project named by this
document. Counts are not treated as one leaderboard because the projects group
features differently; the useful result is the normalized outcome ledger below.

| Project snapshot | Result against the pre-decision frozen 55 |
|---|---|
| [ESP32-DIV `main`, release 1.7.0 / flasher 1.7.2](https://github.com/cifertech/ESP32-DIV) | 21 documented README outcomes covered, 11 narrower and 17 deliberately excluded; ESB capture/defensive MouseJack and Sub-GHz jamming detection are the largest safe gaps |
| [GhostESP Revival 2.1.1](https://github.com/GhostESP-Revival/GhostESP) | core workflow covered, but live Wireshark, defensive/compliance depth, concrete decoder inventory, NFC dictionary work and accessibility are narrower or absent |
| [Bruce 1.16.1](https://github.com/BruceDevices/firmware/releases/tag/1.16.1) | Leshy is stronger in evidence and safety, but PN532 emulation, safe BLE assessment, user app organization, offline owned-handshake verification and explicit USB MSC need decisions |
| [ESP32 Marauder 1.15.1](https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1) | the 55-job product scope is broader; SAE capture, detector/Fox Hunt profiles and field POI are useful acceptance refinements |
| [Flipper Zero stable 1.4.3 / current official dev](https://github.com/flipperdevices/flipperzero-firmware) | 43 of 55 planned Leshy outcomes are equal or broader and 12 are narrower, mainly mature IR/Sub-GHz/NFC, companion and extension UX |
| [NEMO 3.2.2](https://github.com/n0xa/m5stick-nemo/releases/tag/v3.2.2) | 52 of 55 are equal or broader; physical USB BadUSB inspection, a ready TV profile pack and broader locale packaging are narrower |
| [CapibaraZero 0.5.2](https://github.com/CapibaraZero/fw/releases/tag/0.5.2) | archived/deprecated and officially migrated to Bruce; no unique parity requirement remains, so it stays a historical sustainability reference |

#### Safe/relevant outcomes — final disposition

`Refine` means the user job was already one of the original 55 and its acceptance is
now concrete. `Accepted` names the new capability. `Post-1.0` remains visible but
does not silently expand the fixed 62-row release boundary.

| ID | Normalized competitor outcome | Current coverage | Classification |
|---|---|---|---|
| RA-01 | Named Airspace profiles, passive WPA3/PMF/SAE compliance, configurable explained sensitivity and Wi-Fi/BLE/nRF/Sub-GHz jamming warnings | FUNC-44/48/49 | `Refine CAP-048`; named profiles, sensitivity and cross-radio warnings are measurable acceptance |
| RA-02 | nRF24 ESB packet capture/decode and defensive MouseJack scan | FUNC-12/23/37 only provide spectrum/generic Capture foundations | `Accepted CAP-056/PR-028`; injection is a separate Owned Lab recipe |
| RA-03 | Flipper-compatible `.sub` plus a declared minimum Sub-GHz decoder inventory | FUNC-30/37/40 | `Refine CAP-030`; portable format and declared decoder inventory are measurable |
| RA-04 | PN532 NDEF/ISO14443-4 emulation, explicit erase and bounded dictionary recovery for an owned tag | FUNC-31/36/40 cover read and verified restore | `Accepted CAP-058/PR-030`; conditional hardware and secret-minimization gates apply |
| RA-05 | Live USB Wireshark/extcap for Wi-Fi and BLE plus read-only screen mirroring | FUNC-26/38/51 export files and share Actions but do not promise live streams or pixels | `Accepted CAP-057/PR-029`; read-only and no host-network mutation |
| RA-06 | Font scale, high contrast, reduced motion, input-repeat control and outdoor/epilepsy-safe presentation | FUNC-04/05 | `Refine CAP-005` |
| RA-07 | Lock overlay that allows an already-started safe Capture to continue while protecting controls/data | FUNC-52 | `Refine CAP-052`; Stop remains reachable and protected content stays hidden |
| RA-08 | Ready signed IR remote/TV profile pack, multi-button remote UX and favorites | FUNC-29/34/40 | `Refine CAP-034`; deliver a useful signed corpus, not only package architecture |
| RA-09 | Library trash/undo, optional BLE/mobile sync/share, USB Mass Storage and public app catalog | FUNC-25/27/38/41 cover local typed data and extension contracts | trash/undo `Refine CAP-025`; mobile/MSC/catalog remain `Post-1.0` |
| RA-10 | Favorite/hide/show applications, startup job, shortcuts and a privacy presentation | FUNC-02/05 | organization/startup `Refine CAP-005`; privacy is CAP-052/059, not a deceptive dummy UI |
| RA-11 | Signed offline firmware update from SD in addition to browser/OTA/recovery | FUNC-07 | `Refine CAP-007` |
| RA-12 | Per-satellite GPS diagnostics and field POI/notes during Survey | FUNC-14/50 | `Refine CAP-050` |
| RA-13 | Privacy MAC randomization for Leshy's own STA/AP without cloning another identity | FUNC-46 does not promise it | `Accepted CAP-059/PR-031`; synthetic lab identity is ephemeral/provenanced |
| RA-14 | Offline wordlist verification of the owner's own captured Wi-Fi authentication evidence | FUNC-49 ends at classification/export | `Accepted CAP-061/PR-033`; Leshy exports validated canonical `hc22000`, the computer companion runs the curated common/weak and vendor-default corpus, and no plaintext match returns to Leshy |
| RA-15 | Individually admitted iBeacon, MouseJack fixture injection and targeted handshake-assist recipes | FUNC-55 requires named recipes but names none | `Refine CAP-055/056`; named recipes require target, containment, expiry and Stop |
| RA-16 | Physical USB-host BadUSB enumeration and optional keyboard-host/relay | FUNC-54 inspects packages, not a connected USB device | `Accepted CAP-060/PR-032`, conditional on VBUS/OTG/current-limit/cleanup qualification |
| RA-17 | External-module protocol with discovery, heartbeat, checksum, RPC and negotiated transport | no base outcome | `Post-1.0`; useful for Leshy2/expansion modules |
| RA-18 | Joined-LAN inventory, U2F and other safe non-radio utilities | intentionally outside the radio job | inventory/isolated robustness `Accepted CAP-062/PR-034`; U2F/general utilities remain `Post-1.0` |
| RA-19 | Visible regulatory domain and channels 1–14 only when legal and supported | FUNC-05/42/55 are region-aware but the user contract is incomplete | `Refine CAP-005/042/055`; channel 14 is never a universal default |

#### Remaining non-negotiable exclusions

The review reduced the earlier broad rejection list to three enforceable product
boundaries. Everything useful that can satisfy them is now either in the 62-row plan
or explicitly deferred.

| Excluded behavior | Why it remains excluded | What is accepted instead |
|---|---|---|
| Retaining real submitted credentials, payment identifiers/PINs, or equivalent secrets | Storage turns a diagnostic into a secret-collection product, creates unnecessary breach/privacy liability, and adds no value to the evidence needed to prove protocol behavior | A training portal records success/failure only; NFC/EMV keeps redacted protocol metadata; evidence verification stores provenance/results, never submitted secrets |
| Unbounded or indiscriminate active output without a selected target/qualified isolated fixture, scope, expiry and physical Stop | Ambient floods/interference cannot prove who is affected, cannot produce trustworthy bounded evidence, and cannot guarantee cleanup or legal containment | Named Owned Lab recipes may perform targeted handshake assist, identity/iBeacon emulation, MouseJack injection, bounded robustness/crash/interference, IR-camera, and isolated LAN tests when containment is machine-checked |
| Bypassing ResourceBroker, Safety Supervisor, watchdog, permission review, expiry, cleanup or physical Stop | A bypass makes the UI, evidence, leases and emergency stop untrustworthy; signing or developer mode does not make uncontrolled hardware access safe | Signed packages and developer workflows use the same brokered Actions, budgets, audit trail and stop path as built-in apps |

#### Deferred rather than rejected

These outcomes are not forbidden; they are omitted from the 1.0 denominator for a
specific sequencing reason:

| Deferred outcome | Why not in 1.0 | Revisit trigger |
|---|---|---|
| Authenticated DIV-to-DIV Peer Link | adds pairing, mutual authentication, remote-control authorization, conflict ownership, resumable evidence sync and a two-device failure matrix; Live Companion and local HIL cover the nearer user jobs | two healthy supported DIVs, stable Action/schema APIs and a reviewed peer threat model |
| External-module protocol | discovery/heartbeat/checksum/RPC/transport negotiation cannot be fixed before the first real expansion module and its power/bus envelope exist | named module owner, hardware profile and HIL fixture |
| Mobile sync/share | adds phone-platform lifecycle, pairing, background permission and privacy/support work while USB/local Web already provide offline export | stable companion protocol plus a maintained mobile client owner |
| USB Mass Storage | convenient but creates concurrent filesystem ownership, host-eject, dirty-volume and protected-data exposure paths that conflict with the current atomic typed store | proven read-only snapshot or exclusive-unmount design with power-cut/eject HIL |
| Public reviewed app catalog | package runtime/signature is valuable and remains in 1.0; public discovery adds moderation, revocation, hosting and supply-chain operations | stable SDK/package ABI, revocation service and review/support owner |
| Cloud/default telemetry or automatic upload | default networking weakens offline-first/privacy and creates account/credential/retention obligations; explicit local WiGLE/export already preserves user choice | optional, explicit opt-in client with a separate privacy and retention review |
| Generic SSH/Telnet/VPN/DNS/SMB/SNMP toolbox, U2F and unrelated pocket utilities | useful individually but do not improve the core evidence chain, would crowd navigation and multiply security/support surfaces | deliver as reviewed extensions after the SDK and user demand prove a coherent job |
| Games, pets, clocks, QR/media/printer novelties | consume flash/RAM/menu/test budget without strengthening Survey, Capture, analysis or Owned Lab | optional extension after 1.0; never a core parity gate |
| Broad ESP32 board matrix | every board multiplies pin, display, power, radio, storage and HIL combinations; depth and honest failure behavior on ESP32-DIV is more valuable for 1.0 | one profile owner and physical HIL target per new board |
| Deceptive dummy/privacy screen | a fake state can mislead the owner and automated evidence while adding no protection; real privacy is already served by Device Lock overlay and Privacy Identity | no separate core feature; only truthful, explicitly labeled presentation modes are acceptable |

Hardware-only differences such as 125 kHz RFID, iButton, ST25R-specific modes,
5 GHz, 802.15.4, Ethernet, camera, microphone/audio, haptics, FM and LoRa are not
policy rejections. They remain unavailable until an explicitly supported assembly
exists.

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
