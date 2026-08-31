# ESP32-Leshy 1.x — reference workflows

*Read in: **English** · [Русский](REFERENCE_WORKFLOWS.ru.md)*

Document status: **S1 baseline candidate**. These workflows refine the acceptance
boundary of existing `J-*`, `PR-*`, and `NFR-*` IDs; they do not claim that a 1.x
binary exists. A workflow is verified only by the evidence named below.

## Purpose and rules

The workflows define the product as observable user outcomes rather than menu
structure. Each one has a happy path, an error path, a cancel/back path, measurable
acceptance, and an evidence plan.

- Tests use fixed inventory and Session fixtures so EN/RU builds see identical data.
- `Back` is a system action: it is handled within 150 ms and releases any foreground
  leases that the exited context owns (`NFR-002`).
- An error never silently substitutes a different receiver, assembly profile,
  storage target, or active mode.
- A cancel leaves already committed source data unchanged and does not leave an
  operation or lease running.
- Critical state and the available stop action are understandable without color.
- Secrets are absent from reports and exports unless a format explicitly requires
  user-selected source data.

## Workflow index

| ID | User outcome | Jobs | Primary requirements | First implementation gate |
|---|---|---|---|---|
| WF-01 | Understand what this device can safely do | J-05 | PR-001, PR-002, PR-009, PR-014; NFR-001/002/006/010 | S2 |
| WF-02 | Record one useful passive Survey Session | J-01, J-03 | PR-003…PR-005; NFR-002…006/010 | S3 |
| WF-03 | Reopen and export evidence offline | J-03 | PR-005…PR-007, PR-012; NFR-007…010 | S3 |
| WF-04 | Investigate, locate, and compare a Target | J-02, J-04 | PR-004, PR-006, PR-008; NFR-002/008…010 | S6 |
| WF-05 | Run and physically stop an authorized Lab action | J-06 | PR-002, PR-009, PR-013; NFR-002/003/006/010 | S7 |
| WF-06 | Detect and preserve explained wireless evidence in the field | J-03, J-07 | PR-020…PR-023; NFR-002/005…010 | S7 |
| WF-07 | Unlock the device and operate an explicit serial target safely | J-05, J-08 | PR-017, PR-024, PR-025; NFR-002/006/010 | S7 |
| WF-08 | Run permissioned automation, owned-evidence verification, or an authorized Owned Lab recipe | J-03, J-06, J-08 | PR-013, PR-026…PR-034; NFR-002/003/005…007/010…013 | S7 |

## WF-01 — boot, diagnose, decide

**Precondition:** a declared ESP32-DIV v2 assembly profile is installed; no external
assembly is inferred from legacy flags.

**Happy path**

1. Cold boot reaches an interactive home screen.
2. Diagnostics shows the board, firmware/build, storage, and every declared module.
3. Each capability is `declared`, `detected`, `available`, `conflicted`, `fault`, or
   `unknown`, with evidence and a reason.
4. Menus enable only compatible actions; the user can export the diagnostic report.
5. The final Home item opens Device, then Self-Test: Quick runs a safe read-only plan, while
   Full/Guided previews applicable checks/fixtures/side effects before it starts.

**Error path:** an ambiguous GPIO5/6 or GPIO14/21 assembly remains `conflicted` or
`unknown`; Diagnostics explains the expected assembly/profile and performs no trial
output mode. A missing module becomes `fault` only when the profile declared it.
An absent profile module is `not_applicable`; a missing fixture or unprovable result
is `blocked/inconclusive`, never silently passed.

**Cancel/back path:** leaving Diagnostics returns to the previous screen without
starting a module or retaining a foreground lease. Back during Self-Test stops at a
safe boundary, cleans up, and retains an exportable partial report.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-01-A1 | Healthy cold boot reaches interactive UI in ≤ 2 s | HIL timestamp/video trace |
| WF-01-A2 | Golden inventory fixtures render every state, evidence, and reason identically in EN/RU | snapshot tests |
| WF-01-A3 | An unavailable action is disabled or hidden before `Action` start and before lease acquisition | Action/ResourceBroker integration trace |
| WF-01-A4 | Probe/report path emits no RF/IR TX command and exports no saved credentials | policy tests + HIL detector trace + report scan |
| WF-01-A5 | Back is acknowledged in ≤ 150 ms and the ownership table is empty for the exited context | input/resource trace |
| WF-01-A6 | User Quick/Full and release HIL invoke the same versioned check IDs; the host rejects missing checks, wrong candidate identity, unexpected side effects, or nonzero final ownership | Self-Test contract tests + physical HIL report verifier |

## WF-02 — create and save a passive Survey Session

**Precondition:** WF-01 completed; at least one passive source is available. Passive
Wi-Fi is the provisional first source because it needs no external assembly.

**Happy path**

1. Survey previews available, unavailable, and mutually exclusive sources before
   start.
2. Start creates exactly one Session with a stable ID, build/profile metadata, and
   requested source configuration.
3. Normalized Observations enter one monotonic timeline. List opens Detail; Back
   returns to the List while the Session keeps running.
4. Stop ends source workers, commits the Session atomically, and reports the saved
   location.
5. The saved Session is offered as the next action.

**Error path:** a source that fails at start is shown with its reason. Other selected
sources may continue only if the preview declared that degraded mode; otherwise the
whole start fails before a Session is committed. Storage failure never overwrites a
previously committed Session.

**Cancel/back path:** cancel during start yields no committed Session and no leases.
Back from a child view does not implicitly stop Survey. Explicit Stop is idempotent;
repeated Stop cannot create a second commit.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-02-A1 | A golden passive trace produces one Session and the expected ordered Observation set | simulated-driver integration test |
| WF-02-A2 | Each source records actual active windows/duty cycle; unavailable sources create no fabricated observations | Session schema assertions |
| WF-02-A3 | Detail/List navigation preserves selection; Back meets 150 ms and does not leak or accidentally stop source leases | navigation/resource trace |
| WF-02-A4 | Stop commits once; reboot/power-cut injection cannot corrupt older committed data | storage fault matrix + HIL power-cut test |
| WF-02-A5 | Failed/cancelled start leaves zero workers, zero foreground leases, and no visible committed Session | negative integration test |
| WF-02-A6 | A ≥45-minute/≥8-cycle passive run completes inside the one-hour release budget with no monotonic heap growth, UI freeze, drops, leaked leases, or Session corruption | endurance HIL |

## WF-03 — reopen and export offline

**Precondition:** at least one committed Session fixture exists on SD or LittleFS.

**Happy path**

1. After reboot, Library opens while all radio receivers remain inactive.
2. The user opens Session List and Detail, including source Captures and integrity
   state.
3. Export writes a versioned JSON summary; compatible formats appear only for data
   that can represent them without invention.
4. The completed file is reported with size, checksum, schema version, and target.

**Error path:** missing media, insufficient space, checksum failure, malformed input,
or a future unsupported schema produces a specific recovery action. The original
Session/Capture remains byte-identical.

**Cancel/back path:** cancelling export removes or invalidates its temporary output,
keeps the committed source intact, and releases storage. Leaving Library never starts
a radio.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-03-A1 | Golden Session reopens after reboot with zero radio leases and matching counts/checksums | offline integration test + lease trace |
| WF-03-A2 | JSON export validates against its declared schema and preserves source IDs/units/timestamps | schema and golden-file test |
| WF-03-A3 | Failure/cancel at every write boundary leaves the source hash unchanged and no committed partial export | storage fault-injection matrix |
| WF-03-A4 | Malformed or newer-schema input fails clearly without reboot or source modification | bounds/fuzz/migration tests |
| WF-03-A5 | Back meets 150 ms; EN/RU critical errors fit and remain understandable without color | HIL input + UI snapshot tests |

## WF-04 — investigate, locate, and compare

**Precondition:** two golden Sessions contain repeated and unique identities; a live
receiver is optional for localization.

**Happy path**

1. A common Observation List opens Detail with consistent channel/frequency/RSSI
   units and provenance.
2. The user creates or opens a Target. Suggested identity links show confidence and
   the evidence used.
3. Radar/localization, when supported, shows RSSI history and sample age rather than
   claiming physical distance.
4. Compare shows added, removed, changed, and unchanged facts between Sessions.
5. Merge/split, notes, and tags produce an auditable, reversible Target revision.

**Error path:** stale samples, insufficient identity evidence, missing receiver, or
incompatible Session versions are explicit. They never create a confident automatic
merge or a fabricated distance.

**Cancel/back path:** cancelling edit/merge/split preserves the prior Target revision.
Back from live localization stops its worker and lease within 150 ms but does not
modify the underlying Session.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-04-A1 | List/Detail/Radar fixtures use consistent units, filters, identity, and provenance across radio types | shared-view contract tests |
| WF-04-A2 | A golden pair yields the exact expected added/removed/changed/unchanged diff | golden comparison test |
| WF-04-A3 | Merge followed by split restores the prior identity graph and source references | Target property/round-trip test |
| WF-04-A4 | Low-confidence/stale fixtures are labelled and never auto-merged or rendered as distance | negative domain/UI tests |
| WF-04-A5 | Cancel makes no revision; Back from localization meets 150 ms and leaves no receiver lease | domain/resource HIL trace |

## WF-05 — bounded authorized Lab action

**Precondition:** the user is working with owned/authorized equipment; the action,
region, hardware stop path, and assembly profile are available. If no active action
ships, PR-013 remains a mandatory invariant for future activation, not a reason to
fake a capability.

**Happy path**

1. The user explicitly enters Lab context and chooses an available active action.
2. Frequency/channel, power, duration, target/fixture, regulatory result, and the
   physical Stop control are visible before confirmation.
3. A separate confirmation starts a deadline-bound TX lease. Active state remains
   visible without relying on color.
4. Stop or expiry calls the hardware stop path first, verifies idle state, releases
   resources, and records a local audit result without secrets.

**Error path:** unsupported hardware, conflicting lease, invalid parameter, region
block, detector/self-test failure, or missing physical-stop evidence blocks before
TX. There is no best-effort fallback to a different channel/power/module.

**Cancel/back path:** cancel before confirmation produces zero TX. Back/panic during
an action invokes the same physical stop path as expiry; reboot never resumes an
active action.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-05-A1 | Every TX start is preceded by Lab context, valid policy result, explicit confirmation, and a finite deadline | policy/Action audit test |
| WF-05-A2 | Cancel before confirmation produces no CE/TX event | logic analyzer/RF detector HIL |
| WF-05-A3 | Back/panic is handled in ≤ 150 ms; hardware idle is independently observed before lease release | input + logic/RF HIL trace |
| WF-05-A4 | Expiry, driver error, and watchdog use the same idempotent stop path; no reboot resumes TX | fault-injection + reboot HIL |
| WF-05-A5 | Blocked parameters and resource conflicts fail before hardware start with an actionable EN/RU reason | policy/resource/UI tests |

## WF-06 — defensive field inspection

**Precondition:** passive Wi-Fi/BLE reception is available; GPS and connected BLE are
optional capabilities. No alert authorizes a countermeasure or hidden connection.

**Happy path**

1. Airspace Guard opens the strongest current finding with detector version,
   threshold, confidence, uncertainty, and exact source frames/observations.
2. Focused Wi-Fi authentication Capture reports EAPOL/PMKID and complete/incomplete
   handshake state, then saves immutable PCAP/`hc22000` evidence.
3. Field Survey deduplicates Wi-Fi AP/station and BLE observations, attaches GPS track
   when available, compares a revisit, and exports a local WiGLE-compatible artifact.
4. BLE Inspector preserves compatible raw packets; connected GATT starts only after
   the user selects a target, reviews permissions, and confirms the mode transition.

**Error path:** insufficient evidence remains inconclusive; missing GPS yields an
unlocated result; unsupported capture/export or refused GATT connection is explicit.
No fallback starts active Wi-Fi or connects/pairs to another BLE identity.

**Cancel/back path:** Back stops the current receiver/connection, finalizes only an
explicitly saved artifact, disconnects GATT, and leaves zero foreground leases.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-06-A1 | Every alert opens exact source evidence and exposes detector version/threshold/confidence; an insufficient fixture stays inconclusive | detector golden/negative tests |
| WF-06-A2 | Authentication fixtures yield exact complete/incomplete state and schema-valid PCAP/`hc22000` without active provocation | parser/export fixtures + no-TX trace |
| WF-06-A3 | Field Survey deduplicates a golden revisit and exports matching Wi-Fi/BLE/location facts; no-GPS remains valid and explicit | golden route/export tests |
| WF-06-A4 | BLE connected mode requires explicit target/permission and always disconnects/releases its lease on Back, timeout, or error | Action/resource integration + HIL |
| WF-06-A5 | All four paths preserve raw evidence, bounded queues/drop counters, stable navigation, and EN/RU error meaning | schema/UI/resource matrix |

## WF-07 — protected device and bounded serial console

**Precondition:** the owner has configured Device Lock or explicitly chooses to do
so; an external UART target is owned/authorized and its voltage/pins are known.

**Happy path**

1. Device Lock accepts a local PIN setup or unlock under a bounded retry policy.
2. Protected captures, secrets, exports, and sensitive settings remain unavailable
   while locked; safe Stop/panic/cleanup and recovery entry remain available.
3. Device → Serial Console previews pins, voltage assumption, baud, framing, mode,
   target, permissions, and conflicting resources before acquiring a UART lease.
4. The console and Actions CLI use the same bounded Actions; exit releases the UART
   and stores no transcript unless the user explicitly saves one.

**Error path:** wrong PIN, unavailable recovery material, unsafe UART configuration,
conflict, overrun, disconnect, or unsupported CLI Action fails with a bounded delay
and remedy. There is no raw GPIO or policy-bypass fallback.

**Cancel/back path:** cancel changes neither lock state nor target; Back closes the
console, scrubs unsaved buffers, and releases UART/input/storage ownership.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-07-A1 | Locked fixtures reveal no protected content through UI, logs, companion, backup, or export while Stop/panic/recovery remain usable | access-control matrix |
| WF-07-A2 | Retry/recovery is bounded, auditable, and cannot be used to bypass update/recovery or safe cleanup | security negative tests |
| WF-07-A3 | Serial start requires reviewed pins/baud/target and an exclusive lease; Back/error leaves zero UART ownership | Action/resource HIL |
| WF-07-A4 | Actions CLI and on-device UI produce the same authorization/result for golden and forbidden operations | shared-Action contract tests |

## WF-08 — permissioned automation and wireless Lab recipe

**Precondition:** a signed compatible package or individually admitted recipe exists;
any active target/fixture is owned and the physical stop path has evidence.

**Happy path**

1. The user reviews package/recipe identity, signature, permissions, target, resource
   ceilings, expected effects, duration, and output artifact.
2. Automation executes only declared Actions; HID additionally requires explicit
   USB/BLE target and scope confirmation. BadUSB inspection is passive by default.
3. A wireless recipe enters Lab and repeats the WF-05 policy/confirm/deadline/visible
   TX/physical-stop contract for its exact Wi-Fi/BLE/nRF fixture.
4. Completion records a bounded audit/evidence result and releases all resources.

**Error path:** unsigned/incompatible package, undeclared permission, exhausted
budget, missing target, region block, watchdog, or detector failure stops before or
during the same idempotent cleanup path. Forbidden recipe classes are not loadable.

**Cancel/back path:** cancel before confirm produces no HID/TX. Back/panic during
execution stops outputs first, then releases leases and reports the reason.

| Acceptance ID | Observable result | Evidence |
|---|---|---|
| WF-08-A1 | Unsigned, over-permissioned, incompatible, or over-budget automation fails before an undeclared Action/resource is used | package/policy negative tests |
| WF-08-A2 | HID requires explicit target/scope and cancel-before-confirm emits no report/input; passive inspection emits none at all | USB/BLE HIL trace |
| WF-08-A3 | Every wireless recipe maps to its reviewed fixture/region/power/channel/time bounds and inherits WF-05-A1…A5 | recipe manifest tests + RF HIL |
| WF-08-A4 | Timeout, fault, watchdog, Back, and panic converge on idempotent cleanup with no resumed output after reboot | fault/reboot/physical-stop HIL |

## S1 review result

The eight workflows cover `J-01…J-08`. Their acceptance IDs are specification targets,
not current evidence. S1 can baseline the PRD only after prototype budgets and the
remaining hardware unknowns are either measured or explicitly constrained. Later
stages add the test evidence without weakening these paths.
