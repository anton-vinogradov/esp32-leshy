# ESP32-Leshy 1.x — UX-06 input and accessibility map

*Read in: **English** · [Русский](UX_ACCESSIBILITY.ru.md)*

Status: **UX-06 accepted and spatial navigation refined on exact 0.64 TFT evidence**.

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
direction icon/key legend and one localized 16 px action label. Technical state such
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
