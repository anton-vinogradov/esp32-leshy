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

- the `Survey / Targets / Capture / Lab / Library / Device` information
  architecture plus direct `Language` access and a persistent bottom-of-Home
  `Self-Test` utility entry;
- primary J-01…J-06 paths and the home of every `CAP-*`;
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
Quick and Full/Guided modes reuse ordinary Actions and components. It is not a boot
screen, hidden service menu, or release-only serial path.

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
| UX-08 | Usability walkthrough | WF-01…WF-05 run on-board without hidden serial-only actions |

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

Geometry fixes 240×320, 12 px edge, 216 px content width, 42 px header, 40 px row,
7 px gap, 4 px radius, and a dedicated footer below y=236. The footer cannot overlap
product content; three list rows must fit above it.

Exact candidate 0.52 accepts UX-03 as implementation evidence: six retained
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
| Header + title | 240×42 brand anchor; 216 px title region | Home and every Self-Test view |
| Home row | 216×46; three finger-sized rows form a scrolling visible window above the footer | capability Home, Language, and final Self-Test item |
| Choice row | 216×46; up to three finger-sized choices fit above the footer | Quick / Full-Guided, Language, Survey plan/source/filter |
| Metric row | five 216×28 result slots | Full preflight and Quick/Full result |
| Footer divider | fixed at y=236 | every interactive screen |
| Input status + spatial navigation | 216×28 input plus three 70×26 action cells | every interactive screen and HIL |

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
renderer string except the invariant `LESHY 1.x` brand. It currently defines 123
stable IDs, both EN and RU variants (246 strings total), and the pixel budget of
every use. Exact 0.63 measured the former 127-ID prose-footer catalog; 0.64 replaces
its 19 context sentences with 15 compact spatial-action labels.
`tools/generate_ui_gfx_font.py` reproducibly generates the faces, while
`tools/check_ui_language_contract.py` measures their metrics, rejects a
missing translation or overflowing string, and verifies that renderers do not
reintroduce local user-facing literals.

Both languages now use the official vendored OFL-licensed Roboto Condensed variable
source pinned by SHA-256. Generation selects its Medium named instance (weight 500)
and emits 16 px body plus 12 px metadata faces over the required ASCII and Cyrillic
range without runtime font loading or heap allocation. `Language` is the next-to-last
Home item, applies EN/RU immediately, and persists the selection in NVS namespace
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

## Gate

**S1 UX direction accepted:** UX-01/UX-02 exist in low fidelity, every catalog
section has an IA location, and open product choices are recorded before code.

**S2 UX/UI baseline accepted:** UX-01…UX-07 are evidenced on the real TFT; WF-01 and
the platform portion of WF-02 use the same Actions through buttons and diagnostic
automation; no state depends on the 0.x UI. Exact candidate 0.58 completes 29 steps,
nine zero-mismatch TFT comparisons, Quick 8/8, and zero final leases in `DEMO-S2`
(`E-AUTO-022`/`E-HIL-082`/`E-GATE-002`). UX-08 repeats at every later Stage Demo.
