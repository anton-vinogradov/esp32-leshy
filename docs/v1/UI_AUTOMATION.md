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
requires 12 ms of stable state, and places bounded normalized events in a 16-entry
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
| UI-HIL-A8 | 10 ordinary presses of each physical key produce exactly 50 presses and 50 releases, 10 per normalized action, with no ambiguity, I2C error, duplicate, or queue drop | guided physical burst + before/after `input.state` artifact |

Each reference workflow receives an automated UI scenario as its screen states are
implemented. Operator involvement is reserved for evidence the display controller
cannot supply, not routine menu traversal.

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
`millis()` wrap. The dedicated input task remains at a measured 5 ms maximum gap
during full `device-smoke` revision 5; its initial state reports 930 valid reads,
zero read/queue errors, and an empty 16-entry queue. The exact candidate then passed
the prior workflow and all ten TFT comparisons unchanged (`E-HIL-049`). UI-HIL-A8
still requires the operator-generated physical edges; serial Actions are not a
substitute for that evidence.
