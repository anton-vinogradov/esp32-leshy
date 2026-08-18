# ESP32-Leshy 1.x — UI automation and visual evidence

*Read in: **English** · [Русский](UI_AUTOMATION.ru.md)*

Document status: **binding S2 verification contract; transport proven on the S1
measurement target**.

UI checks must not depend on an operator repeatedly photographing the display or
pressing keys. Physical input and diagnostic input enter the same action handler;
the diagnostic transport may observe and drive UI, but may not mutate screen state
directly.

## Contracts

### One action path

The normalized actions are `up`, `down`, `left`, `right`, `select`, and `back`.
The PCF8574 frontend samples active-low inputs every 5 ms in a dedicated task,
requires 12 ms of stable state, and places bounded normalized events in a 64-entry
queue. The UI loop and the local serial command `ui.key <action>` both call the same
allocation-free controller. TFT redraws therefore cannot block physical sampling.
A response reports the accepted action, whether state changed, current
page/selection, and monotonically increasing UI revision.

`input.state` exposes valid/error samples, raw/stable transitions, per-key press
counters, maximum sample gap, ambiguity, queue depth, and queue drops. An invalid
I2C read never changes debounced state; a stable release is required before the same
key can emit another action. Multi-key press edges fail closed as ambiguous.

`ui.state` observes the same public UI state without changing it. Automation never
calls a screen-specific setter, bypasses Back cleanup, or invents a test-only menu.
As the product Navigator replaces the probe controller, this transport stays at the
normalized Action boundary.

`ui.language en|ru` selects through the same persistent `LanguageController` used
by the public Language screen. It is an automation entry into a product operation,
not a separate renderer override; `ui.state` reports both active language and
Language-screen selection.

### Actual display capture

`ui.capture` reads the ILI9341 display GRAM in four-row tiles and returns:

1. one NDJSON `frame_begin` record with width, height, format, byte count, and UI
   revision;
2. exactly `width × height × 2` bytes of `rgb565be` pixels;
3. one NDJSON `frame_end` record with the same byte count and revision.

The 240×320 target therefore transfers 153,600 bytes. Its tile buffer is 1,920 B;
capture does not require PSRAM or a permanent framebuffer. The host converts those
pixels to PNG and records SHA-256 for the source pixels and PNG.

This proves display-controller contents, orientation, rendering, and navigation
state. It does not prove backlight brightness, viewing angle, panel damage, touch
alignment, or physical color calibration; those still require appropriate physical
HIL evidence.

## Reproducible host path

Use the Python environment that already contains PlatformIO's serial dependency:

```sh
"$HOME/.platformio/penv/bin/python" tools/capture_1x_ui.py \
  --port /dev/cu.usbmodem2101 \
  --keys down,down,select \
  --output ui-automation.png
```

The tool opens native USB without DTR/RTS transitions, executes the actions, reads
the TFT pixels, checks that the device still reports the same revision after capture,
and writes `ui-automation.png` plus `ui-automation.png.json`. A scenario should keep
one connection when it needs several intermediate frames; opening or closing the
evidence client must not reset the board.

## Acceptance

| ID | Required result | Evidence |
|---|---|---|
| UI-HIL-A1 | Every physical navigation action has the same normalized diagnostic action | controller unit test + physical/serial traces |
| UI-HIL-A2 | An invalid action is rejected without state change or reboot | negative protocol test |
| UI-HIL-A3 | Back traverses the public Navigator path and preserves/release semantics | state trace + resource ownership trace |
| UI-HIL-A4 | Capture byte count, dimensions, format, and begin/end revision agree | host protocol check |
| UI-HIL-A5 | Post-capture state is reachable and has the captured revision | JSON evidence sidecar |
| UI-HIL-A6 | Golden/snapshot comparison ignores no critical text or selection state | host visual test per screen/state |
| UI-HIL-A7 | UI client connect, capture, and disconnect do not reset the board | reset counter/revision continuity trace |
| UI-HIL-A8 | 10 ordinary presses of each physical key produce exactly 50 presses and 50 releases, 10 per normalized action, 50 dispatched public UI actions, and no ambiguity, I2C error, duplicate, or queue drop | guided physical burst + machine-checked [before/after artifact](../../tests/hil/evidence/board-01-keypad-0.43.json) |

Each reference workflow receives an automated UI scenario as its screen states are
implemented. Operator involvement is reserved for evidence the display controller
cannot supply, not routine menu traversal.

The on-device [Self-Test](SELF_TEST.md) uses this same normalized Action and capture
boundary. Its Quick and Full/Guided plans never introduce screen setters or a second
test-only navigation path; release automation selects the same versioned check IDs
and independently verifies the resulting report, frames, and final cleanup.

## Current evidence

Board-01 running `0.3.0-ui-automation-measure` accepted diagnostic actions through
the same `UiController` as the five active-low PCF8574 inputs. A stateful trace moved
from home to the Automation page, captured 240×320 RGB565, and returned the same UI
revision after capture. A second connection preserved revision/state when the client
suppressed DTR/RTS. This proves the transport and probe navigation shell.

The first manifest-driven `device-smoke` for
`0.35.0-storage-product-measure` then reflashed the exact candidate on board-01,
observed readiness in 502 ms, traversed Home→Diagnostics→Back through public
Actions, and captured three real-TFT frames automatically. Both stable Home frames
matched compressed RGB565 goldens pixel-for-pixel; Diagnostics matched outside the
explicitly recorded dynamic heap/timing region. The bundle contains raw frames,
PNG, state/serial traces, the candidate manifest, and a SHA-256 index; a separate
fail-closed verifier accepted it as unsigned development evidence but not a
release-eligible attestation. This proves the reproducible UI-HIL-A3…A6 automation
path for current screens, but not final product screens, physical-panel appearance,
or NFR-001/NFR-002/NFR-010 in full.

A repeated candidate-0.36 `device-smoke` retained the same goldens and again
reported zero pixel mismatch for Home/Diagnostics/Back while binding the frames to
the full firmware-reported ELF SHA-256 of the running image (`E-HIL-042`).

Candidate 0.37 again produced zero mismatch and additionally bounded every
Action/capture by one device-acknowledged run ID from UI revision 0 through 2
(`E-HIL-043`).

Candidate 0.38 expands the suite through product Survey→commit→Library→export:
seven new real-TFT goldens and the three existing frames match with zero pixel
differences; a bounded serial query verifies export generation 2/3 observations/0
drops, and final Back restores owner `none`/lease `0` (`E-HIL-046`). Automation now
covers the first product vertical slice, although this UI run still uses a
simulated/RAM/RF-off source and store.

Candidate 0.39 makes pipeline state part of the screen/state contract: Running shows
FIFO depth/high-water/drop, Result retains high-water/drop, and HIL assertions
require received/forwarded 3/3 plus trigger none→stop. The seven prior 0.38 goldens
are retained with a version suffix; seven 0.39 frames were recaptured from the TFT,
reviewed, and then matched with zero differences in the full revision-3 run
(`E-HIL-047`).

Candidate 0.40 leaves the visual contract unchanged: revision 4 adds a bounded
product-admission query before navigation and reuses the same ten reviewed TFT
comparisons with zero mismatch. The query proves that without explicit Start and a
trusted persistent store there is no hidden hardware/radio/storage action or
simulated fallback (`E-HIL-048`).

Candidate 0.41 replaces the inherited 35 ms single-sample edge detector after the
operator observed roughly one accepted press in ten. Host tests cover bounce,
invalid reads, held keys, stable release, all five mappings, ambiguous chords, and
`millis()` wrap. Its automatic revision-5 run passed, but the first physical stress
falsified the 16-entry transition queue: the frontend captured 43 presses and 43
releases at a 5 ms maximum gap while 46 queued transitions were dropped. Candidate
0.42 queued presses only and batch-applied state before redraw; its automatic run
passed, but a structured physical attempt captured 48 presses and delivered only 27,
with 21 press drops. These failures are retained as `E-HIL-050/051` rather than
being hidden by the serial-only test.

Candidate 0.43 sizes the ordered press queue for the entire 50-action acceptance
burst, drains accumulated state before one redraw, and emits one diagnostic record
per batch. `device-smoke` revision 6 retained the complete workflow and ten
zero-mismatch TFT frames. UI-HIL-A8 then passed on the exact same app: every key was
10, presses/releases/dispatched were 50/50/50, UI revision advanced by 50, maximum
sample gap was 5 ms, queue high-water was only 6/64, and errors, ambiguity, queue
depth, and drops were all zero (`E-HIL-052`).

Candidate 0.52 adds semantic visual roles without changing the Action/capture
boundary. An exact product-aware run retained setup/running/result/export plus final
Home and Library frames, bound them to app `39fc2c92…43ace`, and finished with 9/9
forwarded, zero drops, and owner/lease `none`/`0` (`E-HIL-076`). A pixel audit also
detected and closed footer overflow. This accepts UX-03 and part of UX-07; it does
not yet prove the Self-Test screens or remaining dialog/error/degraded states.

Candidate 0.53 then reaches the last Home item exclusively through normalized
Actions, captures mode/Quick result/Full preflight/blocked result/final Home, and
binds the same stable check IDs into `leshy.self_test.report.v1`. The first capture
regression exposed and retained a loop-task stack panic in the enlarged state
record; moving both large records to one static bounded workspace fixed it. The
exact rerun passes Quick 8/8 and returns owner/lease `none`/`0`; Full remains
visibly and machine-readably blocked on incomplete capability coverage (`E-HIL-077`).

Candidate 0.55 adds one EN/RU catalog and persistent Language screen without
changing the Action/capture boundary. The exact run retains Russian Home,
Diagnostics, Survey, Library, Language, Self-Test, and Quick result plus English
Home/Language, proves Russian persistence across flash/reset, and finishes Quick
8/8 with zero input errors/drops, buzzer LOW, and owner/lease `none`/`0`
(`E-HIL-079`/`E-UX-005`).

Candidate 0.56 adds an outline and filled chevron to every focused shared/menu/list
row. Twelve exact current TFT captures traverse Home, Survey, Library, Language,
both Self-Test choices, Quick result, and final cleanup only through normalized
Actions. A standard-library pixel audit verifies the cue independently of color and
combines it with the retained 50-event physical-key acceptance (`E-HIL-052/080`,
`E-UX-006`).

Candidate 0.57 uses that same path to select the final Home item and Full/Guided,
then captures preflight, dialog/confirm, unavailable, degraded, error, running,
blocked result, and final Home. The checker binds all nine 240×320 frames to exact
revisions and candidate identity, proves the geometric square cue on every state
card, and verifies plan 2 as 9 pass/0 fail/1 blocked with zero side effects and final
owner/lease `none`/`0` (`E-HIL-081`/`E-UX-007`). This accepts UX-07; the combined
`DEMO-S2` then passes on exact committed candidate 0.58 (`E-AUTO-022`/`E-HIL-082`/
`E-GATE-002`). Its revision-1 suite performs 29 public Action/query steps, matches
nine separately recorded and manually reviewed 240×320 goldens with zero mismatch,
checks semantic `self_test_visual_state` identities for dialog/unavailable, runs
Quick 8/8, and independently verifies final Home, safe outputs, heap/input health,
and zero leases. The retained verifier makes the same path reusable by later Stage
Demos and S8 release promotion without making this local unsigned S2 run a release.

Candidate 0.63 adds the idempotent 18-state typography lane: it normalizes persisted
Home/language/Self-Test state, captures both languages and every guided common
state, runs Quick/Full, and returns Russian Home without heap/input/output drift
(`E-AUTO-027`/`E-HIL-087`). Candidate 0.64 adds a narrower spatial-navigation lane.
It proves Right and Select as equivalent inward Actions, Left and diagnostic Back as
equivalent return Actions, nested Library entry by both keys, and Up/Down selection;
nine exact TFT frames independently verify the three 70×40 footer cells and final
lease 0 (`E-AUTO-028`/`E-HIL-088`/`E-UX-009`). No camera or manual menu traversal is
required for this regression.

Candidate 0.65 extends the same lane with machine-visible render telemetry. It checks
the compact 70×26 cells, records `full` versus `incremental` mode, and fails closed if
any changed-row-only Home/Language/Self-Test selection exceeds 40 ms. The retained
board run covers nine frames and 21 transitions; all eight incremental transitions
measure 19.901–28.981 ms, with invariant heap and final lease 0
(`E-AUTO-029`/`E-HIL-089`/`E-UX-010`). Source checks also reject a reintroduced
interactive `fillScreen` or removal of the old/new-row render path.

Candidate 0.66 added one-event/one-repaint source checks, but its render-only timer
missed blocking post-render serial telemetry; user acceptance failed at queue
high-water 5/64. Candidate 0.67 therefore rejects `broadcast`/`println` anywhere in
the physical dispatch slice and exposes timing only through on-demand `input.state`.
The retained lane binds the failed incident, 75 user-confirmed physical presses,
high-water 1/64, 1.256 ms maximum queue latency, zero serial writes/errors/drops,
nine exact frames and 21 transitions (`E-AUTO-031`/`E-HIL-091`/`E-UX-012`).

Candidate 0.68 adds a product failure-state lane without camera or manual traversal.
It injects one unavailable passive source at its real start boundary, captures the
localized TFT terminal state, rejects a hidden Select retry, returns Home with Back,
and cold-reboots to prove the prior Library is unchanged. Exact framebuffer bytes,
candidate and runner hashes, CID, zero source/store starts, zero writes, invariant
heap, and final lease 0 are retained in `E-AUTO-032`/`E-HIL-092`.
