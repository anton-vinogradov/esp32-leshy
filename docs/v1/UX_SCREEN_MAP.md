# ESP32-Leshy 1.x — UX-01: screen and Action map

*Read in: **English** · [Русский](UX_SCREEN_MAP.ru.md)*

Status: **S1 low-fidelity baseline**. Pixels, typography, and palette are frozen in
S2 on the real TFT; this map already binds task structure and Back/Stop behavior.

## Global shell

`UX-S01 Home` exposes six jobs rather than a radio-module list:

```text
Survey      Targets     Capture
Lab         Library     Device
```

Every screen retains context title, storage/power state, active Session or TX,
visible button roles, and a Back path. The status bar never invents battery
percentage without an authoritative capability. Touch, physical buttons, and
diagnostic automation emit the same typed Actions.

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
   ├─ UX-S23 Device Dashboard
   ├─ UX-S24 Diagnostics / Capability / Module Detail / Report
   ├─ UX-S25 Language / Display / Input / Feedback / Connectivity
   ├─ UX-S26 Storage / Backup-Restore / Factory Reset
   └─ UX-S27 Install / Update / Rollback / Recovery / About

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
| `Back` | close top view/dialog and restore selection | Left; visible Back area |
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

## UX-01 acceptance

- Every `CAP-001…CAP-047` has one primary owner and a measurable
  entry → success/error/cancel → Back path.
- WF-01 uses UX-S23/S24; WF-02 uses UX-S02…S05; WF-03 uses UX-S15…S17;
  WF-04 uses UX-S06…S10; WF-05 uses UX-S18…S22.
- A primary task starts within four transitions from Home; receivers remain
  filters/parameters rather than top-level IA.
- Back restores selection and never hides Stop except for the safety-first TX rule;
  Session/Capture Stop remains an explicit Action.
- Empty, unavailable, degraded, and fault states lead to Diagnostics or a remedy,
  never a knowingly broken screen.
