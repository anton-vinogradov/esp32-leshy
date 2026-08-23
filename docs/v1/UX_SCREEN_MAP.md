# ESP32-Leshy 1.x — UX-01: screen and Action map

*Read in: **English** · [Русский](UX_SCREEN_MAP.ru.md)*

Status: **S1 low-fidelity baseline**. Pixels, typography, and palette are frozen in
S2 on the real TFT; this map already binds task structure and Back/Stop behavior.

## Global shell

The current `UX-S01 Home` exposes seven implemented user jobs. The final `Device`
entry contains settings, checks and system information:

```text
Wi-Fi          find nearby networks
Bluetooth      find nearby devices
2.4 GHz        see busy channels
Sub-GHz        see air / record a signal
Capture        record Wi-Fi or infrared
Library        open saved records
Device
  Settings
  Self-Test   (Quick / Full-Guided)
  Diagnostics
  About
```

Every screen retains a context title, the truthful active receive/transmit antenna
summary, visible button roles, and a Back path. Storage state is shown only when it
changes the current result or action; it does not consume the global header. The
status bar never invents battery or power state without an authoritative
capability. Touch, physical buttons, and diagnostic automation emit the same typed
Actions.

Every live list of radio objects is ordered by descending received signal: the
strongest current RSSI is first and weaker entries follow. Equal RSSI keeps its
existing relative order, and a refresh anchors selection to the same identity so
resorting never silently changes the object under the user's cursor.

Screen space is budgeted by user value. A non-interactive one-line fact occupies
one compact line. A large row is reserved for a touch target and carries both its
task name and a useful outcome or explanation. A spacious result/detail region
must add useful context or a readable visualization, not an ornamental empty
frame. Healthy product screens do not expose implementation counters such as
sample, frame or redraw totals. Radio-object details therefore use compact identity
and channel/mode facts plus one shared qualitative and numeric signal meter.

## Navigation tree

```text
UX-S01 Home
├─ Survey
│  ├─ UX-S02 New Survey: sources, storage, duty-cycle preview
│  ├─ UX-S03 Running Survey: summary ↔ timeline ↔ list
│  │  └─ UX-S04 Observation Detail → Target / Radar / Capture
│  └─ UX-S05 Stop & Commit Result → Session Detail / Export / Home
├─ Targets
│  ├─ UX-S06 Target List: search, filter, sort
│  └─ UX-S07 Target Detail
│     ├─ UX-S08 Name / Tags / Notes / Identities / Merge-Split
│     ├─ UX-S09 Baseline & Compare
│     └─ UX-S10 Radar / Localize
├─ Capture
│  ├─ UX-S11 Capture Source: Wi-Fi packets / Sub-GHz / IR / NFC / Screenshot
│  ├─ UX-S12 Capture Setup: source, bounds, destination
│  ├─ UX-S13 Capture Running: progress, drops, explicit Stop
│  └─ UX-S14 Capture Result: raw metadata / derived decode / Save / Export / Lab
├─ Lab
│  ├─ UX-S18 Scope & Safety Context
│  ├─ UX-S19 Saved Capture + TX Parameters
│  ├─ UX-S20 Explicit Confirmation
│  ├─ UX-S21 Running TX: frequency, power, deadline, permanent Stop
│  └─ UX-S22 Result / Fault / Source Capture
├─ Library
│  ├─ UX-S15 Sessions / Captures / Exports / Screenshots
│  ├─ UX-S16 Item Detail: integrity, provenance, source/derived data
│  └─ UX-S17 Import / Export / Compare / Open in Lab
└─ Device
   ├─ Settings → UX-S25 Language / Display / Input / Feedback / Connectivity
   ├─ Self-Test → UX-S24 test context
   │  ├─ Quick: bounded read-only automatic plan
   │  └─ Full / Guided: scoped preflight → applicable checks → report
   ├─ Diagnostics → UX-S24 Capability / Module Detail / Report
   └─ About → UX-S27 Version / Profile / Update / Rollback / Recovery

UX-S28 Global dialog layer: unavailable reason, progress, confirm, error, panic.
```

Deep links open the existing screen with an entity ID rather than duplicating an
implementation: Observation→Target, Target→Capture, Capture→Lab, and
Library→Compare use the same controllers and Actions as Home entry.

## Typed Actions and physical mapping

| Action | Semantics | Buttons / touch |
|---|---|---|
| `Navigate` | move focus/selection without side effects | Up/Down; tap focus |
| `Open` | open selected item/detail | Right or Select per visible footer label; tap item |
| `Back` | close top view/dialog and restore selection | physical Left; no touch Back target or footer button |
| `Context` | show secondary actions for the current entity | Right with an explicit label; touch context button |
| `Start` | start the reviewed passive/configured workflow | Select on labelled Start |
| `Stop` | stop current Session/Capture/TX, then show result | Select/Left per permanent Stop label |
| `Confirm` | execute a displayed bounded mutation/TX/update/reset | Select only on a dedicated confirm screen; touch Confirm |
| `Cancel` | abandon without commit and release workers/leases | Left/Back; touch Cancel |
| `Save` | atomically persist a new result/derived metadata | labelled Select; touch Save |
| `Export` | create a versioned artifact after target/format preview | Context→Export or labelled action |
| `Panic` | stop every TX before navigation is processed | any Back/Left during TX; long Back is global fallback |

No gesture or serial-only command is the sole path to a core action. During TX,
`Back` never opens confirmation and physically stops transmission first. After stop,
ordinary Back traverses the stack.

## Capability ownership

| Section | Primary capabilities | Important transitions |
|---|---|---|
| Survey | CAP-009…CAP-017, CAP-042 | Observation→Target/Capture/Radar; stopped Session→Library |
| Targets | CAP-018…CAP-022, CAP-044 | Evidence→Observation/Capture; Target→Compare/Radar |
| Capture | CAP-023, CAP-024, CAP-026…CAP-031, CAP-042, CAP-043 | Result→Library/Export/Lab |
| Lab | CAP-032…CAP-037 | accepts only a saved immutable Capture; Result links back to source |
| Library | CAP-025…CAP-031, CAP-038, CAP-043, CAP-047 | item→Compare/Export/Lab; import never bypasses parsers |
| Device | CAP-001…CAP-008, CAP-045…CAP-047 | Diagnostics explains unavailability before task entry |
| Device → Settings | PR-011, NFR-010 | EN/RU switch; immediate application and persistent selection |
| Device → Self-Test | CAP-001…CAP-047 as applicable, PR-009 | Quick/Full use the same versioned checks as release HIL; report→Diagnostics/remedy/export |

## UX-01 acceptance

- Every `CAP-001…CAP-047` has one primary owner and a measurable
  entry → success/error/cancel → Back path.
- WF-01 uses Home→Device→Self-Test/Diagnostics; WF-02 uses UX-S02…S05; WF-03 uses UX-S15…S17;
  WF-04 uses UX-S06…S10; WF-05 uses UX-S18…S22.
- A primary task starts within four transitions from Home. A receiver may be a
  direct top-level job when that is the user's task; band/source selection remains
  a parameter beneath it.
- Back restores selection and never hides Stop except for the safety-first TX rule;
  Session/Capture Stop remains an explicit Action.
- Empty, unavailable, degraded, and fault states lead to Diagnostics or a remedy,
  never a knowingly broken screen.

Exact `0.90.0-product-menu` realizes this top-level map on board-01. Eight retained
TFT states and the machine checker bind Home, Device, Self-Test, Diagnostics and
About, including disabled future domains, touch-row entry, non-interactive chrome,
Left parent restoration and final zero ownership (`E-BUILD-091`/`E-AUTO-055`/
`E-HIL-115`/`E-UX-014`).

Exact `0.91.0-clean-status` refines the shell without changing this map: visible
raw-input diagnostics are removed, four Home rows fit at once, and exact real-TFT
evidence proves idle `RF --` versus active receive `RF RX` with final zero ownership
(`E-BUILD-092`/`E-AUTO-056`/`E-HIL-116`/`E-UX-015`).

Exact `0.92.0-spectrum-views` refines the two RF leaves: each has Spectrum and
Waterfall views; CC1101 adds a four-band chooser; Home alone carries the `LESHY`
brand while nested headers carry navigation context. The live viewport spans the
full 240 px width and 216 px height above the key legend. Exact HIL binds all four
CC bands, accumulated history, pause/resume and final zero ownership
(`E-BUILD-093`/`E-AUTO-057`/`E-HIL-117`/`E-UX-016`/`E-RADIO-005`).

Exact `0.93.0-product-menu` supersedes the executable Home portion of 0.90 without
discarding the 1.0 capability map. The current Home contains only implemented jobs,
in this order: Wi-Fi, Bluetooth, 2.4 GHz, Sub-GHz, Capture, Library, Device. Future
Targets and Lab stay in this document and the roadmap until they are usable. Wi-Fi
and Bluetooth open their own one-source Start row; 2.4 GHz opens live nRF24 directly;
Sub-GHz opens the CC band chooser; Device remains last and owns all service pages.
One connected-candidate command retains 13 actual TFT states and independently
verifies every entry, populated waterfalls, final Home and zero ownership with zero
manual button presses (`E-BUILD-094`/`E-AUTO-058`/`E-HIL-118`/`E-UX-017`/
`E-RADIO-006`).

Exact `0.94.0-home-identity` does not change the screen tree. It localizes
the root-only brand to `LESHY`/`Леший`, shows the build SemVer core on Home, and
removes the brand from About copy. Nested headers remain navigation context. The
physical candidate gate adds an English Home capture to the Russian product route
and restores Russian before final cleanup. Fourteen retained TFT states and exact
source/candidate bindings accept the result (`E-BUILD-095`/`E-AUTO-059`/
`E-HIL-119`/`E-UX-018`).

Candidate `0.95.0-inline-key-hints` does not change the screen tree or input map.
It changes only the shared physical-key legend: the former stacked key-over-label
cells become one mixed-case Roboto Condensed Medium 12 baseline, with `◀ Back`
left-aligned, `▲▼ Select` centered and the contextual action plus `OK▶` right-aligned.
The footer stays non-interactive; touch entry remains on enabled content rows.
Fourteen exact TFT states accept this refinement with `E-BUILD-096`/`E-AUTO-060`/
`E-HIL-120`/`E-UX-019`.

Exact `0.96.0-compact-ui-waterfall` also leaves the screen tree and normalized input
map unchanged. It compacts the shared shell instead: Home identity occupies one
line, nested page titles move into the 26 px header, and four 216×60 content rows
fill the viewport from y=32 with a 12 px inset. The RF leaves keep Spectrum and
Waterfall as sibling views, but the existing 112-row ring now advances on a fixed
26,785 us cadence independent of receiver sweep duration. Fourteen exact EN/RU
Home/menu/RF states and host timings 2.905…2.927 s across nRF24 and all four CC bands
accept the result (`E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`/
`E-RADIO-007`).

Exact `0.111.0-ble-nearby` supersedes the Bluetooth entry path from exact 0.93:
Home→Bluetooth now starts Nearby Devices directly rather than opening a technical
single-source Start row. The live list owns four 216×60 touch rows; Up/Down select,
Right or OK opens detail, and Left returns. The list shows advertised name (or an
explicit unnamed fallback), RSSI, address suffix and signal bars; detail shows the
full address and passivity. Duplicate timestamp-only observations draw nothing,
changed data redraws content rows only, and background discovery never redraws an
open detail. Five exact TFT states plus physical pixel comparisons accept this
non-flickering contract (`E-BUILD-111`/`E-AUTO-075`/`E-HIL-135`/`E-UX-030`).
