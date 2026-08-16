# ESP32-Leshy 1.x — UX/UI baseline

*Read in: **English** · [Русский](UX_UI_BASELINE.ru.md)*

Status: **mandatory S1/S2 control point**; low-fidelity UX-01/UX-02 are fixed while
the UX-03…UX-07 visual baseline remains an S2 deliverable.

This document defines when user experience is reviewed and when visual appearance
becomes an implementation constraint. It does not replace the
[reference workflows](REFERENCE_WORKFLOWS.md) and does not hold live status.

## Two consecutive decisions

### S1 — product UX direction

Before S1 closes, the project agrees:

- the `Survey / Targets / Capture / Lab / Library / Device` information
  architecture;
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

## Gate

**S1 UX direction accepted:** UX-01/UX-02 exist in low fidelity, every catalog
section has an IA location, and open product choices are recorded before code.

**S2 UX/UI baseline accepted:** UX-01…UX-07 are evidenced on the real TFT; WF-01 and
the platform portion of WF-02 use the same Actions through buttons and diagnostic
automation; no state depends on the 0.x UI. UX-08 repeats at every later Stage Demo.
