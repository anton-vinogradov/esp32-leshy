# ESP32-Leshy 1.x — UX-02: state matrix

*Read in: **English** · [Русский](UX_STATE_MATRIX.ru.md)*

Status: **S1 low-fidelity baseline**. The matrix binds product controllers, EN/RU
copy, and future TFT snapshots; it does not claim that a state is implemented.

## Common state rules

- State comes from domain/service layers; a view never infers success from color or
  animation.
- `Unavailable` appears before lease/start with reason, evidence, and one safe next
  action: Diagnostics, another source, or cancel.
- `Loading/Starting` is bounded, exposes cancel, and never blocks the input callback.
- `Degraded` names the missing part and impact; continuation follows a reviewed
  policy rather than silent substitution.
- `Error` preserves source evidence, releases workers/leases, and offers only a safe
  retry, report, recovery, or Back path.
- `Confirm` is reserved for mutation, TX, update, restore/reset, or overwrite; Back
  cancels without side effects. Passive navigation needs no confirmation.
- `Success` exposes the created entity/artifact, integrity, target, and next actions.
  A toast without an accessible result is not success.

## Primary-screen matrix

| Context | Unavailable / Empty | Loading / Starting | Active / Running | Degraded | Error | Confirm | Success | Back / Cancel invariant |
|---|---|---|---|---|---|---|---|---|
| UX-S01 Home | disabled task carries a short reason; Home is never empty because Device remains available | capability refresh retains prior inventory | shows active Session/TX/storage operation | badge + reason, never false READY | global fault opens UX-S24 | absent | ordinary selectable Home | Back never enters undefined state; TX panic-stops first |
| UX-S02 Survey Setup | no passive source: reason + Diagnostics; unavailable storage offers volatile preview only when workflow policy allows | preview checks capabilities/resources/storage with visible Cancel | not running yet | incompatible source is removed with reason and final duty-cycle preview | start creates no Session and leaves zero leases | only for an explicitly degraded/volatile plan | Start opens exactly one UX-S03 Session | Back may retain draft settings but never workers/leases |
| UX-S03 Running Survey | not applicable after successful Start | source join/leave progress is bounded | timer, sources, duty cycle, drops, storage, List/Timeline, and Stop | failed source is named; others continue only under preview policy | stop workers and commit a valid prefix or show no-commit | Stop needs no destructive confirmation | UX-S05 exposes commit/integrity | child Back does not stop Session; explicit Stop is idempotent |
| UX-S04 Observation Detail | missing/corrupt Observation shows source link and integrity error | bounded payload/decode load with Cancel | immutable facts + Target/Radar/Capture actions | missing enrichment leaves raw facts | decoder fault never changes source | mutation only for tag/note/derived decode | new Target/Capture/derived record has an ID | Back restores prior UX-S03 selection |
| UX-S05 Stop & Commit | no-commit explains start/cancel/storage outcome | stop/sync progress is bounded and UI remains responsive | source accepts no new data beyond stop boundary | partial Session is explicit | old committed generation remains available | overwrite is never default | Session ID, size/integrity/storage, Open/Export/Home | repeated Stop writes nothing; Back cannot lose result |
| UX-S06 Targets | empty explains how to create Survey/Target with no fake sample | bounded index/search | filter/sort/selection | stale/missing enrichment is separate | corrupt index opens recovery/report | delete/merge only on a separate screen | created/changed Target is visible | Back retains filter/selection |
| UX-S07…S10 Target/Compare/Radar | missing evidence never becomes a confident Target | history/diff/radar start is cancellable | source facts, confidence, RSSI history, evidence links | partial identities/sessions are listed | radio loss stops Radar without changing Target | merge/split/note mutation shows affected IDs | diff/merge/split is reversible and opens evidence | Back stops Radar lease ≤150 ms and retains Target |
| UX-S11/S12 Capture Setup | unsupported source disabled before entry; screenshot remains available with healthy TFT/storage | validate bounds, destination, capacity, and resources | not capturing yet | optional format/decoder may be missing while raw Capture remains valid | failure creates no false Capture | active/directed mode redirects to Lab; passive Start stays separate | Start creates one running context | Cancel leaves zero workers/leases/files |
| UX-S13 Capture Running | source loss becomes degraded/error, not empty | bounded arm/start | duration/bytes/packets/drops/frequency and permanent Stop | incomplete payload is explicit | stop + cleanup; no corrupt committed artifact | absent for Stop | UX-S14 only after validation/commit | Back equals labelled Stop only when shown; repeated Stop is safe |
| UX-S14 Capture Result | missing raw blob is integrity fault | decode/save/export is cancellable | immutable raw + derived annotations | unknown protocol or missing DB does not block raw view | derived failure never changes raw | operation-specific save/export/overwrite preview | Capture ID, checksum/schema/source, Library/Lab links | Back retains committed Capture and closes temporary buffers |
| UX-S15…S17 Library/Import/Export | empty offers Survey/Capture/Import; missing media is explicit | scan/validate/import/export with progress and Cancel | offline read never starts radios | partial/read-only media has a reason | malformed/future schema fails closed with report | import target/overwrite/export destination preview | artifact size/checksum/schema/path | Back never deletes artifact and releases storage lease |
| UX-S18…S20 Lab Scope/Confirm | no saved compatible Capture or TX capability: reason + Library/Diagnostics | cancellable regulatory/resource check | TX still forbidden | forbidden range/power is never silently lowered | validation leaves hardware inactive | separate screen shows scope, source hash, frequency, power, deadline, Stop; default focus Cancel | Confirm grants bounded TX lease and opens UX-S21 | Back/Cancel issues no TX command |
| UX-S21 Lab Running | not applicable after Confirm | hardware arm stays inside deadline and remains stoppable | permanent TX indicator/frequency/power/countdown/Stop; GPIO/LED state | any telemetry loss is fault and stop | hardware stop precedes error UI | absent | UX-S22 only after physical-stop acknowledgement | any Back/Left, timeout, panic, fault calls `stopTransmit()` first |
| UX-S22 Lab Result | source Capture remains available or shows integrity fault | bounded log/result commit | TX is already off | incomplete result is explicit | stop failure remains critical and blocks new TX | repeat/replay passes UX-S20 again | duration/parameters/stop reason/source hash | Back releases TX/resources; reopening result never transmits |
| UX-S23/S24 Device/Diagnostics/Self-Test | module is always declared/detected/available/conflicted/fault/unknown; an absent profile module is `not_applicable`, never fake pass | Quick is bounded/read-only; Full preflights applicable checks, fixtures, time, and side effects before work | per-check progress, current resource, cancel boundary, and pass/fail/blocked counts; no hidden TX | missing fixture/evidence is `blocked` or `inconclusive` with impact | fault is isolated, cleanup runs first, partial report remains exportable | Quick needs no confirm; Full confirms only declared write/sound/radio side effects with default Cancel | report has plan/build/profile/check/result/evidence/artifact hashes and final ownership | Back cancels at a safe boundary, stops workers, publishes partial report, and releases leases |
| UX-S25 Settings/Connectivity/Feedback | unavailable setting hidden/disabled with hardware reason | bounded apply/test | language/theme/quiet/connectivity preview does not change Session | offline is not error; unavailable network service is named | secret never appears in report/log | Save network/feedback change shows scope and masks secrets | read-back value and persistence state | Cancel restores committed settings; buzzer idles LOW |
| UX-S26 Storage/Backup/Reset | no media/backup has reason; factory reset is never default | scan/checksum/restore progress with safe-boundary Cancel | write target/bytes/generation visible | read-only fallback is named | prior generation remains; recovery path shown | scope/schema/checksum/overwrite plan, default Cancel | verify after write/restore; reset exposes recovery entry | pre-commit Back changes nothing; post-commit opens result |
| UX-S27 Update/Recovery | offline does not block SD/USB recovery; no compatible image has reason | bounded download/verify/write progress | channel/version/signature/slot visible | beta/rollback state explicit | interrupted update boots recovery | version/channel/signature/rollback plan, default Cancel | booted version/hash/provenance + rollback entry | pre-publish Cancel retains current image; Back cannot interrupt unsafe boundary |
| UX-S28 Global Dialog | reason/evidence/next action, never a dead end | operation/progress/Cancel | applies to underlying context only | impact text required | report ID + safe recovery | destructive/active confirm is never preselected | returns created ID/result | modal Back deterministic; panic outranks modal stack |
| UX-S29…S32 Defensive inspection | no finding is not an error; unavailable detector/GPS/export/GATT has an exact reason | detector/capture/route/connect start is bounded and cancellable | evidence/confidence, auth completion, route facts or selected GATT target stays visible | missing location/enrichment/raw support is explicit | source evidence is preserved; no active fallback | only connected GATT needs explicit target/permission confirm | saved artifact exposes schema/checksum/source/uncertainty | Back stops receiver/connection, disconnects and leaves zero leases |
| UX-S30 Wi-Fi Authentication Capture | invalid target/channel or unavailable receive source gives an exact reason; no EAPOL/PMKID is not success or error | fixed target/channel and remaining time; live counts show candidates separately from retained/dropped input, never terminal EAPOL before Stop | stable bounded capture; only changed content repaints | any loss, invalid accounting or unsupported evidence is explicit and forces `inconclusive` | inconsistent report, zero-mask peer or all-zero Key MIC in M2/M3/M4 fails closed; cleanup precedes result | none: receive-only Repeat needs no active confirmation | volatile/RAM-only/not saved result orders `inconclusive` before Full/PMKID/Partial; `exportEligibility=NotEvaluated`; Actions→Peer→Evidence→Detail opens only valid immutable evidence | Up/Down stays in level; Right/OK enters; Left/Back reverses one level; Repeat starts the same bounded capture; final Back leaves zero leases |
| UX-S33/S34 Lock/Serial | locked content is hidden; unavailable recovery/UART has remedy | unlock and UART validation are bounded | retry state or exact pins/baud/target/lease is visible | no transcript/storage is allowed unless explicitly selected | bounded denial/overrun/disconnect scrubs buffers first | PIN changes and serial start preview protected scope/target | unlock or saved transcript/result is explicit | Stop/recovery remains available while locked; Serial Back releases UART |
| UX-S35/S36 Automation/Recipes | unsigned/forbidden/incompatible package/recipe is disabled with reason | signature/policy/resource/target validation is cancellable | permissions, target, ceilings, deadline and output/stop stay visible | optional result transport never widens permissions | watchdog/policy/fault invokes idempotent cleanup | target/effects/HID/TX scope defaults to Cancel | audit/evidence result names package/recipe and stop reason | Cancel-before-confirm emits nothing; Back/panic stops output before navigation |

## Copy and visual evidence for S2

For every family, S2 creates EN/RU fixtures for at least normal, selected,
unavailable, empty, degraded, error, confirm, and running where applicable. A
snapshot records screen ID, state, capabilities, active owner/lease, and Action
labels. Critical state is conveyed by text/shape/icon and never only red/green or
buzzer output.

## UX-02 acceptance

- Every WF-01…WF-08 state appears in this matrix; no error/cancel path exists only in
  workflow prose.
- Every Start/Confirm defines Starting, Error, Cancel, and cleanup outcomes.
- Every storage mutation keeps the old committed generation until new publication.
- Every TX state has one immediate Back/Panic stop path executed before
  navigation/error rendering.
- S2 `DEMO-S2` captures UX-S01, UX-S24, unavailable/degraded/error dialog, and Back;
  later Stage Demos add their rows without inventing a new IA.
