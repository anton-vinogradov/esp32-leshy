# ESP32-Leshy 1.x — UX-01: screen and Action map

*Read in: **English** · [Русский](UX_SCREEN_MAP.ru.md)*

Status: **implemented task-first 1.x map**. Exact physical `1.0.0-dev.328` accepts
the Home hierarchy and direct controlled Lab entry on the real TFT; this map binds
task structure, color semantics and Back/Stop behavior.

## Global shell

The current `UX-S01 Home` is one flat nine-entry list, ordered into five conceptual
groups without extra group pages or taps. Labels describe the result the user wants,
not an internal subsystem:

```text
Nearby
  WI-FI NEARBY        find networks and Wi-Fi devices
  BLUETOOTH NEARBY    find Bluetooth devices
Air
  2.4 GHZ AIR         see 2.4 GHz activity / find a signal
  SUB-GHZ AIR         see Sub-GHz activity / find a signal
Evidence
  RECORD              record Wi-Fi, Sub-GHz or infrared evidence
  MY TARGETS          reopen named/correlated objects and Radar
  SAVED RECORDS       open sessions, captures and exports
Controlled
  LAB                 direct advanced entry; red label and warning, yellow focus
Service
  DEVICE              final muted entry
  Settings
  Self-Test   (Quick / Full-Guided)
  Diagnostics
  About
```

Red on `LAB` means “controlled functionality—review before use”; it does not mean
that merely opening the entry transmits. The current entry is a read-only Inspector.
Any future active action keeps its own preview, explicit confirmation, interlock,
deadline and permanent Stop. Selection remains the common yellow geometric focus,
so warning severity and navigation state are never encoded by the same color.

Every screen retains a context title, the truthful active receive/transmit antenna
summary, visible button roles, and a Back path. Storage state is shown only when it
changes the current result or action; it does not consume the global header. The
status bar never invents battery or power state without an authoritative
capability. Touch, physical buttons, and diagnostic automation emit the same typed
Actions.

Every live list of radio objects is ordered by descending received signal: the
strongest current RSSI is first and weaker entries follow. Equal RSSI keeps its
existing relative order, and a refresh anchors selection to the same identity so
resorting never silently changes the object under the user's cursor. For an
interactive live list, descending signal defines the order before navigation.
The first Navigate/Open action freezes the visible identity order until the user
leaves that task: current signal values still update in place, while rows and the
object under the cursor cannot jump. Re-entering takes a new strongest-first
snapshot and includes newly discovered objects.

Screen space is budgeted by user value. A non-interactive one-line fact occupies
one compact line. A large row is reserved for a touch target and carries both its
task name and a useful outcome or explanation. A spacious result/detail region
must add useful context or a readable visualization, not an ornamental empty
frame. Healthy product screens do not expose implementation counters such as
sample, frame or redraw totals. Radio-object details therefore use compact identity
and channel/mode facts plus one shared qualitative and numeric signal meter.

## Navigation tree

The tree below is the capability hierarchy. The executable Home keeps the stable
flat order above for one-tap access; group names are semantic documentation, not
additional screens. Deep links may open `Target / Radar / Capture / Lab` from a
result while preserving the same typed Action and safety admission path.

```text
UX-S01 Home
├─ Survey
│  ├─ UX-S02 New Survey: sources, storage, duty-cycle preview
│  ├─ UX-S03 Running Survey: summary ↔ timeline ↔ list
│  │  └─ UX-S04 Observation Detail → Target / Radar / Capture
│  ├─ UX-S05 Stop & Commit Result → Session Detail / Export / Home
│  ├─ UX-S29 Airspace Guard: findings → explanation → exact evidence
│  └─ UX-S31 Field Survey: sources / GPS / revisit / local export
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
│  ├─ UX-S14 Capture Result: raw metadata / derived decode / Save / Export / Lab
│  ├─ UX-S30 Wi-Fi Authentication Capture
│  │  ├─ Running: remaining time / candidate frames / retained/drop accounting
│  │  └─ Result → Actions → Peer → Evidence → Detail
│  │     └─ Repeat: start the same bounded capture again
│  └─ UX-S32 BLE Inspector: raw packets / explicit connected GATT
├─ Lab
│  ├─ UX-S18 Scope & Safety Context
│  ├─ UX-S19 Saved Capture + TX Parameters
│  ├─ UX-S20 Explicit Confirmation
│  ├─ UX-S21 Running TX: frequency, power, deadline, permanent Stop
│  ├─ UX-S22 Result / Fault / Source Capture
│  ├─ UX-S35 Automation / HID: package, permissions, target, preview
│  └─ UX-S36 Wireless Recipes: admitted Wi-Fi / BLE / nRF fixtures
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
   ├─ About → UX-S27 Version / Profile / Update / Rollback / Recovery
   ├─ Lock → UX-S33 Setup / Unlock / Recovery / Protected Scope
   └─ Serial Console → UX-S34 UART Preview / Running / Save Result

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
| Survey | CAP-009…CAP-017, CAP-042, CAP-048, CAP-050 | Observation/finding→Target/Capture/Radar/evidence; stopped Session/Field Survey→Library/export |
| Targets | CAP-018…CAP-022, CAP-044 | Evidence→Observation/Capture; Target→Compare/Radar |
| Capture | CAP-023, CAP-024, CAP-026…CAP-031, CAP-042, CAP-043, CAP-051 | Result→Library/Export/Lab; GATT requires explicit connected mode |
| Wi-Fi Authentication Capture | CAP-049 | Result→Actions→Peer→Evidence→Detail; production Actions are Details/Save/Repeat, Save requires explicit confirmation and atomically persists schema-8 evidence, while PCAP and useful-evidence-gated `hc22000` export reopen the exact stored generation |
| Lab | CAP-032…CAP-037, CAP-054, CAP-055 | accepts only reviewed source/package/recipe; Result links back to source and audit evidence |
| Library | CAP-025…CAP-031, CAP-038, CAP-043, CAP-047 | item→Compare/Export/Lab; import never bypasses parsers |
| Device | CAP-001…CAP-008, CAP-045…CAP-047, CAP-052, CAP-053 | Diagnostics explains unavailability before task entry; Lock never blocks Stop/recovery; Serial owns one explicit UART lease |
| Device → Settings | PR-011, NFR-010 | EN/RU switch; immediate application and persistent selection |
| Device → Self-Test | CAP-001…CAP-055 as applicable, PR-009 | Quick/Full use the same versioned checks as release HIL; report→Diagnostics/remedy/export |

## UX-S31 Offline Field Survey baseline

The user starts this job to answer three questions: what is present here, what is
new or missing since the previous visit, and how to carry the result away. The
product workflow therefore has three compact levels:

1. **Setup** shows receive sources `Wi-Fi AP + stations` and `Bluetooth`, the
   selected revisit baseline or `First visit`, storage readiness, and location as
   `GPS ready`, `No GPS hardware`, or `Waiting for fix`. Stock ESP32-DIV has no
   authoritative GPS, so `No GPS hardware` is the normal truthful state and never
   blocks a local survey.
2. **Running** uses the full content area for elapsed time, unique total, New,
   Seen again and the strongest recent objects. A switch opens the strongest-first
   AP/station/BLE list; navigation freezes identity order while signal values update.
   Implementation counters, redraw totals and empty decorative frames are absent.
   Stop remains explicit and Back cancels through the common bounded cleanup path.
3. **Result** leads with `New / Seen again / Missing`, then AP/station/BLE totals.
   Actions are Save, Compare details, Export native record and Export WiGLE. A
   capacity/source loss produces an explicit incomplete result and disables compare
   claims. WiGLE is marked `ready to upload` only with trusted UTC and location;
   otherwise it is an honest local export with blank fields. Wi-Fi stations remain
   available in the native result even though WiGLE 1.6 has no station row type.

Exact host/build dev.256 accepts only the bounded catalog, comparison and row
serializer behind this screen contract. Product state wiring, persistence/export
routing, live station capture, optional GPS adapter and physical pixels remain open.

Exact host/build dev.257 accepts the first product slice: the Wi-Fi menu describes
Wi-Fi+Bluetooth comparison, Setup replaces its unrelated RF-spectrum action with an
explicit `Previous field visit` / `First visit` choice, every available receiver is
selected by default, and only an exact complete `field-visit-live` record may become
the automatic baseline. Result shows unique or New/Seen/Missing plus Wi-Fi/BLE totals;
incomplete input shows `Result incomplete` and publishes no comparison. The existing
strongest-first live observation browser remains the Running view for this slice.
The richer live New/Seen rollup, station capture and optional GPS adapter remain open.

Exact physical dev.263 accepts the result-export presentation and route. Right/OK on
a stopped complete Field Survey opens Library Export Ready without reacquiring radio
ownership. The screen states that native CSV is ready, and that WiGLE has no GPS/UTC
instead of claiming upload readiness; USB is named as the transfer path. Only the
Export Ready content is changed and its exact pixels are retained. Native and WiGLE
payloads are parsed by automation in memory and are not written to host evidence.

Exact physical dev.248 accepts the original UX-S30 result hierarchy on the original
DIV. Exact host/build dev.249 extends its production Actions to Details, Save and
Repeat. Save first opens explicit confirmation, then shows Saving and terminal
Saved/Failed state; it commits schema-8 authentication provenance atomically and
accepts Saved only after exact-generation reopen, re-analysis and artifact
validation. A valid stored capture remains exportable as PCAP even when no useful
authentication material exists; canonical `hc22000` becomes ready only for a valid
PMKID or replay-consistent M1→M2 pair. Synthetic HIL results remain volatile and
cannot offer Save or Export. On terminal results, `inconclusive` has priority over
Full, PMKID and Partial evidence; peers with no valid message mask are not navigable.
Up/Down changes selection only within the current level, Right/OK moves inward,
Left/Back returns exactly one level, and Repeat starts the same bounded receive-only
capture. Live/tone/selection updates repaint only changed content, not the whole
screen. A title is repainted only when its visible tone/color changes; identical
list/detail titles are left intact, and the footer changes only when its visible
hints differ. The dev.249 Save/reopen/export extension still requires physical TFT,
SD and useful-evidence acceptance; dev.248 remains the physical baseline.

## UX-01 acceptance

- Every `CAP-001…CAP-055` has one primary owner and a measurable
  entry → success/error/cancel → Back path.
- WF-01 uses Home→Device→Self-Test/Diagnostics; WF-02 uses UX-S02…S05; WF-03 uses UX-S15…S17;
  WF-04 uses UX-S06…S10; WF-05 uses UX-S18…S22; WF-06 uses UX-S29…S32;
  WF-07 uses UX-S33/S34; WF-08 uses UX-S35/S36 plus UX-S18…S22.
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
and Bluetooth open their own one-source Start row; 2.4 GHz opens Air overview / Find a signal;
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

Exact `0.122.2-ble-device-intelligence` replaces that intentionally sparse baseline
without adding a page. Each of the four rows uses its first line for the best
available name/type and its second for a different useful vendor, state or RSSI fact;
duplicate captions are suppressed. Opening a row keeps the same identity and shows a
compact passive passport above one integrated signal card. Continued discovery
repaints only that card: the name, address, vendor and advertisement facts stay
pixel-identical, while current dBm, meter, volatile range and trend may change.
The accepted 240×320 frames change 111 list-content/zero chrome pixels and 3,234
radar/zero static-or-chrome pixels (`E-BUILD-122`/`E-AUTO-086`/`E-HIL-146`/
`E-UX-041`).

Exact `0.123.0-nrf24-signal-finder` changes the 2.4 GHz entry from one implicit
live view into two explicit outcome rows: **Air overview** (Spectrum/Waterfall) and
**Find a signal** (remote/tag/sensor). Finder first says to leave the source off
while two ambient windows are learned, then asks the user to turn it on and hold it
near the antennas. The screen keeps the `RX N1+2+3` status, a black full-width
2,402…2,484 MHz response plot and **Again**; when detected it replaces the prompt
with exact MHz and nearest Wi-Fi channel. During live search only the result when
its state changes and the graph bars may redraw. Eight exact TFT states plus a
two-frame comparison accept zero changes in header, legend, axis and footer
(`E-BUILD-123`/`E-AUTO-087`/`E-HIL-147`/`E-UX-042`).

Exact `0.124.1-cc1101-frequency-finder` gives Sub-GHz three explicit rows:
**Air overview**, **Find frequency**, and **RAW Capture**. Finder first asks the user
to keep the source off while three ambient sweeps are learned, then asks to activate
and bring it near the antennas. The screen retains `RX CC`, a black full-width
275…950 MHz response plot with frequency axis and **Again**. A found result replaces
the prompt with exact kHz and the nearest standard band hint; healthy runs expose no
sweep/bin/counter telemetry. Search redraws only changed result and graph regions.
Fresh and independent ambient runs accept 1,455 graph and zero static changed pixels
(`E-BUILD-124`/`E-AUTO-088`/`E-HIL-148`/`E-UX-043`).

Exact `0.113.0-dense-details` applies the screen-space rule to the three implemented
radio-object details without changing navigation. Bluetooth Device, Wi-Fi Network
and Wi-Fi Device compact identity/channel-or-mode facts above one shared signal
card containing qualitative strength, numeric dBm and a weak-to-strong meter.
Healthy sample/frame counters are removed. One fresh flash and two same-hash reuse
runs retain 17 TFT states; all three open details remain pixel-identical during
background reception (`E-BUILD-113`/`E-AUTO-077`/`E-HIL-137`/`E-UX-032`).

Exact `0.114.0-stable-network-nav` makes this live-list rule concrete for
Wi-Fi→Nearby Networks. Before interaction, current RSSI determines descending order.
The first Up/Down/Open action freezes the visible BSSID sequence; RSSI and channel
continue updating in place, but the cursor, row identities and selected network do
not jump. Networks first discovered after the lock appear on task re-entry. A fresh
physical run exercises eight actions and two further scans across 23 locked rows
without changing selection, visible size, BSSID-order hash or selected-BSSID hash
(`E-BUILD-114`/`E-AUTO-078`/`E-HIL-138`/`E-UX-033`).

Exact `0.115.0-wifi-device-intelligence` turns Wi-Fi→Devices into a three-level
user flow: strongest-first live list → stable device passport → live signal radar.
The primary row label prefers passively advertised WPS device name/model/maker, then
the embedded IEEE OUI maker, then MAC. The passport uses the full viewport for MAC
type, maker, model, Wi-Fi generation/channel, directed SSID, BSSID, observation
duration/state and an explicit passive-evidence note; unavailable facts read as
unknown rather than being guessed. Right or OK advances, Left returns. First
interaction freezes row identities, and radar pins reception to the selected channel
while updating only its RSSI state/range card. Eight exact TFT states verify zero
static-chrome repaint and a pixel-stable passport during background traffic
(`E-BUILD-115`/`E-AUTO-079`/`E-HIL-139`/`E-UX-034`).

Exact `0.116.0-wifi-channel-average` refines Wi-Fi→Channels without adding another
screen. The full 1…13 axis remains visible on a black graph. Each channel overlays a
narrow colored latest-dwell bar on a wider gray session-mean bar; a gray swatch and
`AVG`/`СРЕД` label explain the encoding. `BEST`/`СВОБОДНЕЕ` compares the session
means of 1/6/11, so one short burst cannot alone flip the recommendation. Only a
changed bar or recommendation is redrawn. Four exact TFT states prove visible gray
means and zero changes outside live regions (`E-BUILD-116`/`E-AUTO-080`/
`E-HIL-140`/`E-UX-035`).

Later exact `0.120.0-wifi-channel-choice` makes that recommendation legible and consistent
with the graph. All measured labels 1…13 are candidates; the lowest visible gray
mean wins, equal means use adjacent-channel pressure only as a tie-break, and only
the resulting channel number is cyan. The old permanent cyan 1/6/11 labels and the
English `BEST 1/6/11` copy are removed. Exact board evidence recommends and
highlights channel 13 after both the second and third full sweep
(`E-BUILD-120`/`E-AUTO-084`/`E-HIL-144`/`E-UX-039`).

Self-review exact `0.121.0-wifi-channel-neutral-bars` also removes the legacy green
low-load tint that still applied only to 1/6/11. Current bars now use one
load-dependent palette for every channel; cyan remains exclusive to the actual
recommended axis label. Fresh physical evidence changes only the live region and
leaves static chrome exact (`E-BUILD-121`/`E-AUTO-085`/`E-HIL-145`/`E-UX-040`).

Exact `0.117.0-wifi-device-live-detail` collapses the historical three-level
Wi-Fi→Devices flow into strongest-first list → integrated live information. Right
or OK immediately opens the selected identity and pins its channel; the upper
identity/MAC/passive-evidence region stays stable while only generation/channel,
network or observed state, signal meter, range and trend update below it. Left
unlocks and returns directly to the list. Six physical TFT states prove 2,120
live-region and zero identity/chrome changed pixels (`E-BUILD-117`/`E-AUTO-081`/
`E-HIL-141`/`E-UX-036`).

Exact `0.118.0-wifi-network-intelligence` makes Nearby Networks answer “what is this
network?” rather than expose scan telemetry. The detail uses the viewport for
SSID/BSSID and maker, security/ciphers, radio channel/frequency/width/PHY,
WPS/FTM/RX antenna and country/channel limits when broadcast. Missing facts remain
honestly unknown. A hidden SSID reads `Hidden`; passive reception keeps listening,
and a later beacon or probe response for the same BSSID replaces it in place without
moving the cursor. A later empty record cannot erase the learned name or richer
facts. The firmware sends no directed probe. Static passport content redraws only
when it is enriched; normal live refresh is confined to the RSSI line. Six physical
TFT states prove zero changed pixels outside that line while the native suite proves
hidden→known monotonic merge (`E-BUILD-118`/`E-AUTO-082`/`E-HIL-142`/`E-UX-037`).

Exact `0.119.0-wifi-network-live-radar` keeps that passport and uses its remaining
lower viewport for the selected BSSID's live signal. One compact card shows the
qualitative state, numeric dBm, meter, minimum/maximum since entry and latest trend;
there is no extra route or technical sample counter. Passive scans continue across
all channels so the network list and hidden-name enrichment remain useful. Only the
card redraws on a visible signal change; the identity, facts, header and footer do
not flash. Six physical TFT states prove 86 changed pixels inside the card and zero
outside/chrome pixels (`E-BUILD-119`/`E-AUTO-083`/`E-HIL-143`/`E-UX-038`).
