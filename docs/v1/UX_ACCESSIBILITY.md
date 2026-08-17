# ESP32-Leshy 1.x — UX-06 input and accessibility map

*Read in: **English** · [Русский](UX_ACCESSIBILITY.ru.md)*

Status: **UX-06 accepted; ordered, non-blocking physical-key navigation measured on exact 0.67 TFT evidence**.

UX-06 requires every current primary operation to remain reachable with the five
physical buttons and every state/focus distinction to remain understandable without
color. Diagnostic automation enters the same normalized Action boundary and is not
a substitute for a physical control.

## Physical and normalized controls

| Physical key | PCF8574 input | Normalized Action | Stable meaning |
|---|---:|---|---|
| Up | P7, active low | `Up` | previous enabled or visible choice |
| Down | P5, active low | `Down` | next enabled or visible choice |
| Left | P3, active low | `Left` | Back/Cancel; safety-first Stop during TX |
| Right | P4, active low | `Right` | enter/open; same inward direction as Select |
| Select | P6, active low | `Select` | enter/open the selected item; context action at a terminal destination |
| diagnostic only | — | `Back` | same return boundary as physical Left |

The input task samples every 5 ms, debounces for 12 ms, emits one action per stable
press, requires release before repetition, and rejects simultaneous key edges as
ambiguous. The retained 50-press physical test proves 10 presses of each key with
50/50 press/release/dispatched events, zero errors/ambiguity/drops, and a 5 ms
maximum sample gap.

## Screen action map

| Context | Up/Down | Select | Right | Left/Back |
|---|---|---|---|---|
| Home | move focus | open enabled item | open enabled item | no hidden mutation |
| Language | choose EN/RU | apply and persist | apply and persist | Home |
| Self-Test modes | choose Quick/Full | run/open preflight | run/open preflight | Home |
| Self-Test preflight/result | — | run applicable checks | run applicable checks | modes |
| Survey setup | — | Start | Start | cancel/Home |
| Survey running list | move observation focus | Detail | Detail | cancel without commit |
| Survey detail while running | — | Stop/save | Stop/save | list |
| Survey result/error | — | — | — | Home without hidden retry |
| Library list | move Session focus | Detail | Detail | Home |
| Library detail | — | Export | Export | list |
| Export ready | — | — | — | detail |
| Diagnostics | — | — | — | Home |

The footer is a spatial control map rather than prose: Left is the left cell,
Up/Down the center cell, and Right+OK the right cell. Each active cell has a drawn
direction icon/key legend and one localized 12 px action label in a 26 px footer. Technical state such
as RF/storage provenance remains in the screen body. An unavailable Home item does
not open and displays its reason rather than relying on a muted color.

## Non-color state contract

- Focus is shown by a persistent outline and filled chevron; palette contrast is
  secondary evidence only.
- Running, committed, error, pass, fail, blocked, persistent/volatile, simulated,
  passive RX-only, and unavailable states are written explicitly on screen.
- Warning, positive, and danger colors never carry the only state signal.
- Every nested screen has a physical Left path; TX later adds a permanent
  safety-first Stop rule without changing that key.

`tools/check_ui_accessibility_contract.py` binds this map to source, geometry,
localized state strings, native tests, and retained physical-key evidence. Exact
candidate `0.56.0-ui-accessibility-measure` then moves focus over all five Home rows,
Survey, Library, Language, and both Self-Test choices through public Actions on the
actual TFT. The pixel audit finds a 210 px outline plus at least 67 chevron pixels
on every focused row; Quick remains 8/8 and final owner/lease is `none`/`0`.
`E-BUILD-058`/`E-HIL-080`/`E-UX-006` therefore accept UX-06, not UX-07,
`DEMO-S2`, or a release gate.

Exact candidate `0.64.0-spatial-navigation-measure` restores the proven 0.x spatial
model and removes the prose footer. `E-AUTO-028` drives Right and Select through the
same inward paths, Left and diagnostic Back through the same return paths, and
Up/Down through bounded selection. Nine exact EN/RU TFT frames verify the 40 px,
three-cell component on Home, Diagnostics, Survey setup, Library list/detail,
Language, and Self-Test. Survey Stop/save now lives inside Detail so Right no longer
contradicts its stable inward meaning. `E-BUILD-065`/`E-HIL-088`/`E-UX-009` refine
the accepted UX-06 contract without promoting S3 or a release.

Exact candidate `0.65.0-compact-incremental-ui-measure` preserves that mapping while
shrinking the footer from 40 to 26 px. It also restores the 0.x repaint rule: an
Up/Down selection redraws only the old and new opaque rows; a full transition clears
only content below the already-painted header, and no interactive path calls
`fillScreen`. Eight Home/Language/Self-Test selection transitions measure
19.901–28.981 ms on the actual panel (40 ms fail-closed ceiling), versus the observed
63.615 ms whole-page redraw. Nine exact frames, 21 transitions, invariant heap and
clean input/buzzer/lease state are bound by `E-BUILD-066`/`E-AUTO-029`/`E-HIL-089`/
`E-UX-010`.

Exact candidate `0.66.0-ordered-key-repaint-measure` ported the 0.x ordering rule,
but user acceptance still failed. The render-only lane measured 13.927–23.043 ms
while missing synchronous post-render USB/UART telemetry; ten physical presses
produced queue high-water 5/64 and the same delayed jump reported by the user.

Exact candidate `0.67.0-nonblocking-keypath-measure` removes every serial write from
the physical hot path and exposes queue/end-to-end timing only through on-demand
`input.state`. The user confirmed the lag was gone after 75 physical presses; the
retained run records 75/75/75 press/release/dispatched events, queue high-water 1,
maximum queue latency 1.256 ms, zero errors/drops/serial writes, and a last changed
focus end-to-end time of 16.703 ms. Nine TFT frames/21 transitions remain exact and
eight incremental renders measure 13.972–23.058 ms (`E-BUILD-068`/`E-AUTO-031`/
`E-HIL-091`/`E-UX-012`).
