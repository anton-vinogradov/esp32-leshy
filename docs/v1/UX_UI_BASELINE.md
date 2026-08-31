# ESP32-Leshy 1.x — UX/UI baseline

*Read in: **English** · [Русский](UX_UI_BASELINE.ru.md)*

Status: **S1 product UX direction and S2 visual gate accepted**. Low-fidelity
UX-01/UX-02 are fixed, UX-03…UX-07 are evidenced, and reproducible `DEMO-S2`
passes on the exact 0.58 candidate. UX-08 repeats at each later Stage Demo.

This document defines when user experience is reviewed and when visual appearance
becomes an implementation constraint. It does not replace the
[reference workflows](REFERENCE_WORKFLOWS.md) and does not hold live status.

## Two consecutive decisions

### S1 — product UX direction

Before S1 closes, the project agrees:

- the product-first `Survey / Capture / Library / Targets / Lab / Device`
  information architecture; service functions live below the final `Device` entry
  as `Settings / Self-Test / Diagnostics / About` rather than competing on Home;
- primary J-01…J-08 paths and the home of every `CAP-*`;
- common Start/Stop, Select, Back, confirm, cancel, and panic semantics;
- mandatory path states: unavailable, empty, loading, running, partial/degraded,
  error, confirm, and success;
- which evidence must fit on TFT and what belongs in Detail/companion;
- non-color accessibility, button operation, EN/RU, and touch limits.

This review answers “how does a person complete the job” without freezing pixels
before real-display verification.

### S2 — visual and interaction baseline

On the independent target and real TFT, the project freezes:

- the 240×320 grid, safe areas, vertical rhythm, and list density;
- typography roles, title/list/detail/metadata hierarchy, and EN/RU truncation;
- palette and contrast for normal/selected/disabled/warning/error/TX without
  relying on color alone;
- Home, status bar, list row, detail field, graph, dialog, progress, and
  unavailable-explanation components;
- button/touch mapping, focus, long press, debounce, and permanent Back path;
- motion/update budgets so radio and storage never block UI;
- visual TX indication, timeout, and panic even though active actions arrive in S7.

After the gate, a base component or interaction-pattern change requires a baseline
update, TFT evidence, and affected acceptance tests.

Self-Test follows the dedicated [product contract](SELF_TEST.md): its explicit
Quick and Full/Guided modes reuse ordinary Actions and components. It is the second
visible item under `Device`, not a boot screen, hidden service menu, or release-only
serial path.

## Required baseline artifacts

| ID | Artifact | Verifiable result |
|---|---|---|
| [UX-01](UX_SCREEN_MAP.md) | Screen and Action map | Every `CAP-*` has entry, success/error/cancel, and return path |
| [UX-02](UX_STATE_MATRIX.md) | State matrix | Primary screens define empty/loading/running/degraded/error/confirm states |
| UX-03 | Design tokens | Color, text, spacing, border, and focus roles are fixed rather than per-screen hex values |
| UX-04 | Component sheet | Shared elements render at 240×320 and are reused across radios |
| UX-05 | EN/RU content fit | Critical strings fit or have a defined safe abbreviation |
| UX-06 | Input/accessibility map | All primary actions work with buttons; state is distinguishable without color |
| UX-07 | Real-TFT evidence | Home, List, Detail, dialog, error/degraded, and running states are captured by UI automation |
| UX-08 | Usability walkthrough | WF-01…WF-08 run on-board without hidden serial-only actions |

## UX-03 visual-token S2 candidate

The first implementation slice lives in `ui/VisualTheme.h`. Screens consume
semantic roles rather than TFT constants or local RGB values. UX-03 is accepted as
an artifact; the complete S2 visual baseline still requires UX-04…07.

| Role | RGB | Purpose |
|---|---|---|
| Canvas / Header | `#07100C` / `#1A3A28` | quiet dark field and stable brand anchor |
| Surface / Focus | `#0D1611` / `#1A4E34` | rows and current keyboard focus |
| Primary / Secondary / Muted | `#E7CF8F` / `#C6D0C8` / `#68756B` | text hierarchy without relying on size alone |
| Focus | `#F5C542` | selected object or primary Action, not a warning |
| Positive / Warning / Danger | `#55D98A` / `#F7A641` / `#F05D5E` | state is always duplicated by text/shape |

Current geometry fixes 240×320, a 12 px edge, 216 px content width, a compact 26 px
information/navigation header, 4 px radius, four 216×60 px Home rows with 5 px
gaps, a divider at y=293, and a 26 px physical-key footer. The footer cannot
overlap product content and the header/footer are never touch targets.

Exact candidate 0.52 accepted the historical 42 px header/y=236/input-status
geometry as implementation evidence: six retained
240×320 TFT frames are bound to the candidate and a standard-library pixel audit
checks the complete brand/divider/input geometry and empty bottom guard rows. The
audit found a wrapped Library footer outside its region; the copy was shortened,
rebuilt, flashed, and re-captured. UX-07 remains partial because dialog and
unavailable/degraded/error states plus the EN/RU matrix are still open.

## UX-04 shared component sheet

The allocation-free contract in `ui/UiComponents.h` is the 240×320 component
sheet used by product screens. It owns component rectangles and tones; screens own
content and state. Bounds and non-overlap are compile-time assertions and native
tests, so a screen cannot silently move its content into the fixed footer.

| Component | Geometry/role | Current reuse |
|---|---|---|
| Header + title | 240×26 information/status bar; Home owns localized brand/version, nested screens put the current page title inside the same bar | every product view |
| Home row | 216×60; four enlarged touch targets form a scrolling visible window above the footer | seven-job Home and the four-item Device menu |
| Choice row | 216×52; up to three enlarged choices fit above the footer | Quick / Full-Guided, Language, Survey plan/source/filter |
| Metric row | five 216×28 result slots | Full preflight and Quick/Full result |
| Footer divider | fixed at y=293 | every interactive screen |
| Spatial navigation | three 70×26 physical-key action cells; no visible raw-input diagnostic | every interactive screen and HIL |

Exact candidate `0.54.0-ui-components-measure` accepts UX-04 through
`E-BUILD-056`/`E-HIL-078`/`E-UX-004`: Home and Self-Test consume the same renderer
primitives; four actual TFT frames pass the pixel/trace checker; Quick passes 8/8;
input has zero errors/drops, buzzer remains LOW, and Back returns owner/lease to
`none`/`0`. This accepted the component system; at that point UX-05…07 and
`DEMO-S2` were still open.

The 0.88 touch corrective keeps the accepted component vocabulary but enlarges Home
from five 28 px rows to a three-row 46 px visible window and standardizes choice rows
at 46 px. Header/footer are excluded from hit testing; the footer is still only a
physical-key legend, and physical Left remains the sole Back control.

## UX-05 EN/RU content fit

`ui/UiStrings.def` is the single allocation-free catalog for every current S2
renderer string except the invariant `LESHY` brand and compact protocol-status
tokens. It currently defines 134
stable IDs, both EN and RU variants (268 strings total), and the pixel budget of
every use. Exact 0.63 measured the former 127-ID prose-footer catalog; 0.64 replaces
its 19 context sentences with 15 compact spatial-action labels.
`tools/generate_ui_gfx_font.py` reproducibly generates the faces, while
`tools/check_ui_language_contract.py` measures their metrics, rejects a
missing translation or overflowing string, and verifies that renderers do not
reintroduce local user-facing literals.

Both languages now use the official vendored OFL-licensed Roboto Condensed variable
source pinned by SHA-256. Generation selects its Medium named instance (weight 500)
and emits 16 px body plus 12 px metadata faces over the required ASCII and Cyrillic
range without runtime font loading or heap allocation. `Device → Settings` opens
Language, applies EN/RU immediately, and persists the selection in NVS namespace
`leshy1-ui`, key `lang.v1`; `ui.language en|ru` exercises the same controller boundary
used by the screen. The earlier PT Sans Narrow source and exact 0.55 evidence remain
historical provenance, not the current face.

UX-05 accepts encoding coverage, persistence, geometric fit, and the selected
small-raster face; physical-panel optics and personal vision still belong to the
usability walkthrough. The Roboto replacement required eight safe copy shortenings.
All current 246 variants fit their declared generated-glyph pixel budgets with zero
overflow; the retained 0.63 typography run remains the historical 254/254 proof.

Exact candidate `0.55.0-ui-language-measure` accepts UX-05 through
`E-BUILD-057`/`E-HIL-079`/`E-UX-005`. Actual 240×320 TFT captures cover Home,
Diagnostics, Survey, Library, Language, Self-Test, and Quick result in Russian plus
Home and Language in English. Russian survives an exact-candidate flash/reset;
Quick remains 8/8 with zero RF/storage/buzzer side effects, input errors and drops
remain zero, the buzzer is LOW, and final owner/lease is `none`/`0`. The retained
artifact and independent checker bind the frames, catalog, font source, candidate
hashes, state trace, and final cleanup. At that point UX-06/UX-07 and `DEMO-S2`
remained open.

Exact candidate `0.63.0-roboto-condensed-ui-measure` supersedes only the typography
layer through `E-BUILD-064`/`E-AUTO-027`/`E-HIL-087`/`E-UX-008`; it does not reopen
or promote a Stage gate. The idempotent device runner captures 18 actual 240×320
frames: Russian Home/Diagnostics/Survey/Library detail/Language/Self-Test, Full
preflight, all five common states and both results, plus English Home/Language and a
pixel-identical final Russian Home. Quick passes 8/8, Full remains honestly 9/10 with
one blocked capability-coverage check, radio/storage/buzzer side effects and input
errors/drops stay zero, heap remains 272,688/208,912/188,720 B before and after, the
buzzer is LOW, and final owner/lease is `none`/`0`. The retained checker rehashes the
official TTF, OFL, generated face, exact candidate, runner, every frame/trace and the
final cleanup.

## UX-06 button and non-color accessibility

The binding [input/accessibility map](UX_ACCESSIBILITY.md) maps all five physical
PCF8574 keys and diagnostic `Back` to normalized Actions for every current screen.
A selected row now carries a geometric outline and filled chevron in addition to
palette contrast. Unavailable, running, committed, error, pass, fail, blocked,
persistent/volatile, simulated, and passive states remain explicit text.

Exact candidate `0.56.0-ui-accessibility-measure` accepts UX-06 through
`E-BUILD-058`/`E-HIL-080`/`E-UX-006`. Retained physical evidence binds 10 presses
of each key with 50/50/50 presses/releases/dispatched and zero errors, ambiguity,
or drops. The exact TFT run moves focus across all five Home rows, Survey, Library,
Language, and both Self-Test choices through public Actions; the pixel checker
proves the outline/chevron independent of color. Quick remains 8/8, input remains
healthy, the buzzer remains LOW, and final owner/lease is `none`/`0`. At that
evidence point UX-07 and `DEMO-S2` remained open.

Exact candidate `0.64.0-spatial-navigation-measure` refines UX-06 through
`E-BUILD-065`/`E-AUTO-028`/`E-HIL-088`/`E-UX-009`. A 40 px footer now contains
three spatial cells: Left/Back, Up+Down/Select, and Right+OK/Enter. Direction icons
are drawn geometrically, action labels use Roboto Condensed Medium 16, and technical
RF/storage state remains in the body instead of competing with controls. Right and
Select open the same Home and nested Library destinations; Survey Stop/save moves
inside Detail so the stable navigation model has no list-level exception. Nine
exact TFT frames, 15 public transitions, invariant heap, healthy input, buzzer LOW,
and final Russian Home with lease 0 are independently checked.

Exact candidate `0.65.0-compact-incremental-ui-measure` keeps the same three-cell
mapping but uses 12 px labels in a 26 px footer. Selection changes now repaint only
the old/new rows, never clear the whole screen, and expose measured `render_mode`/
`render_us` diagnostics. The exact TFT lane proves eight incremental transitions at
19.901–28.981 ms, nine final frames, 21 public transitions and zero heap/input/
resource drift (`E-BUILD-066`/`E-AUTO-029`/`E-HIL-089`/`E-UX-010`).

Exact candidate `0.66.0-ordered-key-repaint-measure` restored one-event/one-repaint,
but failed user acceptance because synchronous serial telemetry still ran after the
render timer. Ten presses reached queue high-water 5/64 and visibly lagged.

Exact candidate `0.67.0-nonblocking-keypath-measure` removes that USB/UART work from
the hot path. The user confirmed responsive navigation over 75 physical presses;
high-water is 1/64, maximum queue latency is 1.256 ms, the last changed focus is
16.703 ms end-to-end, and serial writes/errors/drops are zero. Exact TFT rendering
remains 13.972–23.058 ms (`E-BUILD-068`/`E-AUTO-031`/`E-HIL-091`/`E-UX-012`).

## UX-07 real-TFT common-state evidence

Exact candidate `0.57.0-ui-state-evidence-measure` accepts UX-07 through
`E-BUILD-059`/`E-HIL-081`/`E-UX-007`. The final Home item opens Self-Test without
any boot detour, selects Full/Guided through ordinary Actions, and renders a
preflight plus explicit dialog/confirm, unavailable, degraded, error, and running
cards. Each card combines text, a fixed square outline, and a semantic tone; the
machine checker binds nine actual 240×320 TFT captures, distinct framebuffer hashes,
exact Action/state revisions, and the card geometry.

The same run executes plan version 2. Its eight Quick platform checks and
`full.ui.common_states` pass, while `full.capability.coverage` remains honestly
blocked: 9 passed, 0 failed, 1 blocked. Radio TX, storage writes, and buzzer
activations remain zero; heap is 272,760/224,280/188,792 B, input errors/drops are
zero, GPIO2 is LOW, and final owner/lease is `none`/`0`. This closes the real-TFT
common-state artifact, not the full capability plan or release gate. The combined
platform gate is closed by the subsequent exact 0.58 `DEMO-S2` evidence.

## Product-first menu refinement

Exact candidate `0.90.0-product-menu` realizes the final top-level information
architecture without reopening the S2 baseline. Home now contains
`Survey / Capture / Library / Targets / Lab / Device`; the unfinished Targets and
Lab entries are visibly disabled, while Device contains Settings, Self-Test,
Diagnostics and About. Shared 216×46 px rows serve both the physical navigator and
touch. The 26 px footer remains a physical-key legend and is not a touch target;
Left alone restores child→Device→Home.

`E-BUILD-091`/`E-AUTO-055`/`E-HIL-115`/`E-UX-014` retain eight actual 240×320 TFT
states, exact candidate/runner bytes, touch chrome misses, nested parent state,
heap 231,772/166,812/147,460 B and final owner/lease `none`/`0`. The first HIL run is
also retained as a runner-only revision expectation error; the candidate was not
reflashed for the passing retry.

## Compact status and content refinement

Exact candidate `0.91.0-clean-status` removes the visible `RAW 0xFF` input
diagnostic from the product shell. The recovered space changes the Home viewport
from three to four 216×46 px rows and moves the footer divider to y=282; the final
26 px remain only the spatial legend for physical keys. The 34 px header keeps the
short `LESHY` anchor and two textual states:

- `SD OK` means the enrolled medium matches, read-only recovery is guaranteed and
  cleanup is complete; `SD !` is an enrolled-media fault and `SD --` means no
  enrolled ready medium is claimed;
- `RF RX` means a product Survey, Wi-Fi Capture, nRF24 spectrum or CC1101 spectrum
  receiver is actually running; `RF --` means no receive path is active.

No battery percentage or power state appears until a reliable measured capability
exists. `E-BUILD-092`/`E-AUTO-056`/`E-HIL-116`/`E-UX-015` bind eight menu and six RF
TFT states. Exact framebuffer crops distinguish real nRF24 receive from pause/Home;
the same run proves zero TX/storage side effects, invariant heap and final lease 0.

## Full-width RF views and contextual header

Exact candidate `0.92.0-spectrum-views` supersedes the repeated-brand part of the
0.91 shell: `LESHY` is visible on Home only; every nested screen uses that left-hand
header space for its current section or task. Both receiver workflows now provide
Spectrum and Waterfall. Up/Down switches the view, Right/OK pauses or resumes, and
Left stops and returns. The live graph uses x=0…239 and y=62…277, with a compact
metrics overlay and axis but no decorative plot frame. CC1101 selection is an
ordinary four-row 315/433/868/915 MHz menu.

The waterfall is a fixed, allocation-free 112-row ring and appends only the newest
screen line during acquisition. `E-BUILD-093`/`E-AUTO-057`/`E-HIL-117`/`E-UX-016`/
`E-RADIO-005` bind 22 TFT states, 32 accumulated nRF24 rows, 16 accumulated CC1101
rows, stable pause/resume, all CC bands, invariant heap/storage and final lease 0.
It is an activity/RSSI visualization, not a calibrated analyzer.

Candidate `0.96.0-compact-ui-waterfall` decouples this visual time axis from each
receiver's hardware sweep duration. nRF24 and every CC1101 band now snapshot the
latest receive-only spectrum on one fixed 26,785 us cadence: 112 rows span at most
3,000,000 us and fill the complete graph area. Exact physical acceptance proves,
rather than infers, the timing on nRF24 plus 315/433/868/915 MHz: host-observed
fill is 2.905/2.927/2.918/2.916/2.924 s respectively, while device telemetry stays
at 2.814…2.857 s. All paths reach 112 rows with zero TX/storage side effects,
unchanged storage, stabilized invariant heap and final lease 0
(`E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`/`E-RADIO-007`).

## Implemented-job Home and one-command physical checkpoint

Exact candidate `0.93.0-product-menu` supersedes the executable Home part of 0.90.
Only implemented jobs appear: Wi-Fi, Bluetooth, 2.4 GHz, Sub-GHz, Capture, Library
and Device. Future Targets/Lab remain in the 1.0 roadmap, not as dead menu entries.
Wi-Fi/BLE each open a one-source Start row, 2.4 GHz offers Air overview / Find a signal,
Sub-GHz opens the CC band chooser, and Device remains the final service container.

The connected-board checkpoint is now one foreground command:

```sh
./tools/verify_connected_candidate.sh
```

It requires a clean committed candidate and exactly one connected board, then runs
host tests, documentation checks, the exact build, exactly one flash, normal public
Actions, automatic TFT captures and an independent verifier. The accepted run used
zero manual button presses and retained 13 actual frames, all seven openable entries,
Wi-Fi/BLE source masks 1/2, populated nRF24/CC1101 waterfalls, stable pause/resume,
unchanged generation 95/0, invariant heap and final owner/lease `none`/`0`
(`E-BUILD-094`/`E-AUTO-058`/`E-HIL-118`/`E-UX-017`/`E-RADIO-006`).

## Localized Home identity and visible version

Exact `0.94.0-home-identity` makes the root identity explicit and keeps it
out of navigation context. Home alone renders `LESHY` in English or `Леший` in
Russian. No About or nested-screen string repeats either brand spelling; nested
headers continue to name the current section or task.

The same 34 px Home header renders the SemVer core derived from the build identity
(`v0.94.0`) immediately below the localized brand. The complete build identity
(`0.94.0-home-identity`) remains available in About and diagnostics. SD/RF status
tokens stay right-aligned and unchanged. The connected-candidate workflow must
capture both English and Russian Home automatically, restore Russian, and bind the
screens to the exact flashed candidate without manual button presses. The accepted
run retains 14 real TFT states, all seven Home jobs, both populated waterfalls,
unchanged generation 95/0 and heap, and final owner/lease `none`/`0`
(`E-BUILD-095`/`E-AUTO-059`/`E-HIL-119`/`E-UX-018`).

Candidate `0.96.0-compact-ui-waterfall` keeps the root-only identity contract and
makes Home read `LESHY v0.96.0` or `Леший v0.96.0` on one line. The 16 px brand
and 12 px SemVer use a shared baseline with a fixed 5 px gap; measured text widths
leave the right-aligned SD/RF status region untouched. On nested screens the actual
page title moves into that information bar, eliminating a duplicate body title;
the bar shrinks from 34 to 26 px and content starts at y=32. Four enlarged 216×60
menu targets now fill the available viewport. Interactive menu/list rows use one
shared 12 px horizontal inset and vertically centered two-line text. Exact bilingual
physical acceptance retains 14 Home/menu/RF states from one flash with zero manual
presses, exact CID, unchanged generation 95/0, stabilized invariant heap and final
owner/lease `none`/`0` (`E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`).

## Inline physical-key legend

Candidate `0.95.0-inline-key-hints` restores the successful 0.x presentation
model without restoring its renderer. The 26 px footer is one quiet baseline,
not three stacked pseudo-buttons. Roboto Condensed Medium 12 renders the action
beside its physical-key symbol in mixed case and one secondary color: `◀ Back`
is edge-aligned left, `▲▼ Select` is centered, and `Enter OK▶` is edge-aligned
right. Empty actions leave their zone empty.

The symbols keep the established 1.x semantics: Left is the parent/stop path,
Up/Down changes the current selection or view, and Right or OK enters or performs
the named action. The six-pixel outer anchors and optical vertical centering are
derived from the readable 0.x footer geometry; labels remain generated EN/RU font
text and never become touch targets. The connected-candidate gate captures Home,
nested menus and live RF views so the compact legend is checked in every
combination. Exact physical checkpoint 0.95 retains 14 TFT states with one flash,
zero manual presses, unchanged heap/storage and final lease 0 (`E-BUILD-096`/
`E-AUTO-060`/`E-HIL-120`/`E-UX-019`).

## Outcome-first product content contract

Candidate 0.105 treats documentation as the source of truth for what belongs on a
product screen. Before adding a field, the screen must answer: **what result does
the user expect from this feature, what do they need to understand that result,
and what can they do next?** Visible content follows this order:

1. current page/task in the header;
2. result or meaningful live state;
3. parameters needed to interpret or change that result;
4. a user-relevant warning or remedy, only when applicable;
5. available physical-key actions in the fixed footer.

| Surface | Expected user outcome | Show | Keep in diagnostics/evidence, not the product screen |
|---|---|---|---|
| Home | choose a task by its result | job name plus a plain-language outcome | protocol, module, storage and implementation terminology |
| Wi-Fi / Bluetooth | find nearby networks or devices | name, signal, channel/address where useful, found count, filter and availability | FIFO, duty cycle, generation, queue/drop telemetry when healthy |
| 2.4 GHz / Sub-GHz spectrum | identify quiet and busy parts of the band | active RX antennas, mode, clear color legend, one-pixel data, channel/frequency axis | sweep/sample counters, peaks, internal cadence and buffer state |
| 2.4 GHz signal finder | find the frequency of a remote, tag or sensor | two-step ambient/action instruction, exact frequency, nearest Wi-Fi channel where applicable and full-width response graph | windows, sweeps, thresholds, response-bin counts and receiver wire counters |
| Sub-GHz frequency finder | find which frequency an owned remote, tag or sensor uses | two-step ambient/action instruction, exact kHz, nearest standard-band hint and full-width response graph | bins, sweeps, calibration strategy, threshold, harmonic mask and CC1101 wire counters |
| Wi-Fi Capture | obtain a bounded PCAP recording | purpose, duration, live packet count/current channel, loss warning only if non-zero, privacy confirmation and save outcome | snap length, payload bytes, raw-memory lifecycle, internal persist status/generation |
| Infrared Capture | read a remote-control key | where to point/what to press, detected/no-signal result, protocol and code only when decoded, save outcome | GPIO, sample gaps, zero-valued code, raw pulse count and receiver safety invariants |
| Sub-GHz signal Capture | record a signal from the user's remote/sensor | chosen frequency, simple action, detected/recorded/no-signal result, remedy and save outcome | threshold, samples, pulse capacity, OOK implementation and future FSK/GDO0 work |
| Library | recognize and reopen a saved result | friendly record type, saved/temporary/recovered state, useful decoded content and available export formats | session ID, generation, `valid` integrity token, history duty and raw byte counts |
| Device | configure or check the product | plain Settings/Self-Test/Diagnostics/About entry outcomes | technical data is allowed inside explicitly opened Diagnostics, Self-Test and About because it is the requested task |

The USB diagnostic API, retained HIL artifacts and storage metadata keep the full
engineering detail; hiding it from the TFT does not remove observability. The host
guard `tools/check_product_ui_content.py`, called by `tools/test.sh`, rejects a
product renderer that reintroduces the listed developer-facing fields and requires
the outcome-oriented Home, scan, Capture and Library strings to remain wired.

Exact candidate 0.106 physically exercises the contract after one fresh flash and
three exact-hash reuse runs. Its retained 37 TFT states cover every Home entry,
populated RF views, Wi-Fi Capture and honest no-signal IR/Sub-GHz results. The
privacy-safe Capture review exports no wireless payload and writes no SD data;
machine checks bind exact firmware identity, CID/catalog/heap, graph-only waterfall
updates and final lease 0 (`E-BUILD-106`/`E-AUTO-070`/`E-HIL-130`/`E-UX-025`).

Exact 0.107 applies the baseline to the first final Wi-Fi job. `Wi-Fi→Nearby
Networks` starts collection directly and uses the whole content area for four stable,
finger-sized network rows; selection opens BSSID/channel/RSSI/sample detail. The
bounded catalog deduplicates real results by BSSID and never invents security data.
During live collection only changed data rows may repaint: the 26 px header and
footer remain byte-identical, and an open detail screen stays visually frozen while
background collection continues. Physical evidence records 42 changed content
pixels, zero changed chrome pixels and zero changed detail pixels
(`E-BUILD-107`/`E-AUTO-071`/`E-HIL-131`/`E-UX-026`).

Exact 0.108 applies the same rule to `Wi-Fi→Wi-Fi Devices`. The list uses four
full-width touch rows and exposes only MAC, evidence-backed activity state, channel
and RSSI; passive reception cannot truthfully supply a human name or vendor. A
bounded 1…13 channel monitor continues behind detail, but the detail framebuffer is
deliberately frozen. Physical comparison records 12,940 changed list-content pixels,
zero changed header/footer pixels and zero changed detail pixels while accepted
frames and channel hops advance (`E-BUILD-108`/`E-AUTO-072`/`E-HIL-132`/`E-UX-027`).

Exact 0.109 extends the rule to `Wi-Fi→Channels`. The screen uses the full
content width for thirteen labelled channel bars on a black idle background and
shows only an honest lower-bound `airtime ~0–8%` scale plus the least-busy
measured primary among 1/6/11. A live refresh paints only a changed bar and, when
needed, the recommendation. Header, scale, channel axis and footer stay untouched;
the physical two-sweep comparison records 1,074 dynamic and zero static changed
pixels (`E-BUILD-109`/`E-AUTO-073`/`E-HIL-133`/`E-UX-028`).

## Smart repaint contract

Smart repaint is the default rule for every product screen, not an optimization
owned by individual features:

1. entering a different scene may clear and render its static chrome exactly once;
2. a live tick first compares the user-visible presentation model with the last
   rendered model; an unchanged tick is a strict no-op;
3. a changed scalar/text field is composed off-screen and pushed atomically into
   its bounded dirty rectangle; it may not erase its complete row or page;
4. a graph changes only affected columns or the newest waterfall row, while axes,
   legend, header and footer remain untouched;
5. selection, sorting and structural catalog changes repaint only the old/new rows
   that actually changed; selected identity is stable even when signal ordering
   changes;
6. every call to the shared renderer explicitly chooses scene-transition or
   dirty-only scope. A default full-render argument is forbidden.

Host guard `tools/check_live_render_contract.py` enforces the shared no-change
tri-state, explicit renderer scope, atomic signal fields, incremental spectrum
columns and one-row waterfalls. Exact host/build `1.0.0-dev.332` extends this to
the Bluetooth-device list: an RSSI-only update atomically replaces only the second
text line, and the signal glyph changes only when its quantized level changes.
It also fixes an unrelated truthfulness defect found during the same review: a
mounted read-only SD whose optional `/leshy/automation/v1` directory has not been
created is an empty first-use Automation state, not `SD CARD UNAVAILABLE`.

This is source/build acceptance (`E-BUILD-217`/`E-AUTO-193`), not a claim that all
physical flicker is closed. The connected-board delta must verify the Bluetooth
list, the Lab empty state and unchanged header/footer pixels before dev.332 becomes
the physical UX baseline; later live screens must satisfy this same contract when
they enter the functional-first queue.

## Gate

**S1 UX direction accepted:** UX-01/UX-02 exist in low fidelity, every catalog
section has an IA location, and open product choices are recorded before code.

**S2 UX/UI baseline accepted:** UX-01…UX-07 are evidenced on the real TFT; WF-01 and
the platform portion of WF-02 use the same Actions through buttons and diagnostic
automation; no state depends on the 0.x UI. Exact candidate 0.58 completes 29 steps,
nine zero-mismatch TFT comparisons, Quick 8/8, and zero final leases in `DEMO-S2`
(`E-AUTO-022`/`E-HIL-082`/`E-GATE-002`). UX-08 repeats at every later Stage Demo.
