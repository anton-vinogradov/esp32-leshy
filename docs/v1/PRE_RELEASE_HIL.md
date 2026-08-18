# ESP32-Leshy 1.x — automated pre-release HIL

*Read in: **English** · [Русский](PRE_RELEASE_HIL.ru.md)*

Document status: **accepted ADR-005 operational contract; implementation v0.4**.

The goal is to prove automatically that one immutable release candidate runs on a
real ESP32-DIV, renders the expected screens, and finishes workflows without leaked
resources. Firmware exposes observable facts; an independent host runner decides
`pass/fail`, and the release pipeline verifies that result.

## Recommended flow

```text
commit / release candidate
  ↓
CI builds binary + map + manifest + SHA-256 exactly once
  ↓
immutable candidate artifact
  ↓
HIL station flashes that exact SHA to a real board
  ↓
cold boot → normal Actions → actual TFT captures → cleanup
  ↓
deterministic evidence archive
  ↓
GitHub OIDC/Sigstore signs candidate and evidence without a persistent private key
  ↓
release gate verifies suite, board, results, and the same SHA
  ↓
the same bytes are published; rebuilding is forbidden
```

This is a hybrid host-orchestrated design: a small safe evidence boundary belongs to
firmware, while scenarios, expected values, golden images, comparison, and release
policy remain external.

## Firmware side

The release candidate exposes stable versioned schemas over local USB for:

- build/profile/reset identity and a monotonic boot counter;
- capability inventory and resource ownership;
- normal typed Actions using the same path as physical buttons;
- public UI state without screen-specific setters;
- tiled readback of actual TFT GRAM with revision and byte count;
- bounded metrics, queue/drop/storage/error counters, and safe-output state;
- test-session start/end only as evidence markers, never as a hidden state setter.

Firmware does not contain expected screenshot hashes or declare its own behavior
successful. It reports facts. The runner must reach each screen through Home/Actions
and independently verify state, pixels, and cleanup.

Only read-only evidence, normal user Actions, and safe product operations belong in
release bytes. Fault injection, arbitrary GPIO/RF commands, raw memory, and permission
bypasses do not. Destructive storage/power-cut/radio HIL uses a separate diagnostic
image or external equipment; its evidence complements but never replaces smoke on
the exact release bytes.

The bottom-of-Home [Self-Test](SELF_TEST.md) is the user-facing client of this same
versioned check registry. Quick selects the bounded read-only subset; Full/Guided
selects every applicable check after explicit preflight. The host runner invokes the
same check IDs on exact release bytes, adds fixtures and endurance where authorized,
and remains the independent release oracle. There is no boot-time Quick detour and no
second, release-only definition of device health.

## Host-runner side

The suite is a versioned declarative manifest. Each scenario declares:

- required board/profile/capabilities and accepted degraded states;
- preconditions and explicit media/radio/storage authorization;
- cold/warm boot policy and timing bounds;
- a sequence of public Actions or user commands;
- assertions for page/state/owner/leases/counters;
- TFT capture points and a chosen visual comparator;
- error/cancel/Back path;
- final invariants: owner `none`, lease mask `0`, safe outputs, no unexpected reset,
  and bounded heap/drop/error delta.

The runner fails closed on candidate-SHA, firmware version/build ID, board profile,
suite schema, or required-capability mismatch. A retry is allowed only for a
preclassified transient signature and is retained in evidence; generic retry-until-
green is forbidden.

## Screenshot verification

Every frame retains raw RGB565, PNG, UI state, revision, and SHA-256.

Comparison has three modes:

1. **Exact:** byte-identical RGB565 for fully deterministic screens.
2. **Region-aware:** exact/threshold checks over named regions; dynamic time/RSSI/
   counter regions have explicit masks and separate semantic assertions.
3. **External camera:** a small mandatory RC subset for panel/backlight/orientation
   and gross physical rendering defects that GRAM readback cannot observe.

A global permissive pixel threshold is forbidden because it can hide missing
critical text or selection. Updating a golden requires a reviewable image diff,
reason, and suite version bump; the runner never rewrites baselines automatically.

### External-camera subset contract

The camera lane belongs to one foreground release procedure; it is not a resident
macOS service. It observes the physical panel in the same four stable states already
captured from GRAM by the product runner: `setup`, `running`, `committed`, and
`export`. One station manifest fixes:

- a `station_id` and exact platform `camera_id`;
- an invariant camera-frame size;
- a calibrated visible-panel quadrilateral ordered TL/TR/BR/BL;
- relative paths to each camera PNG and corresponding GRAM PNG;
- contrast, reference-correlation, and correct-orientation-margin thresholds.

`verify_1x_camera_subset.py` rectifies the panel, maps both camera and GRAM images
onto one bounded luminance grid, and compares the expected view with rotations
0/90/180/270. A blank/underexposed frame, changed dimensions, weak correlation,
rotation, missing/escaping path, or weakened release-policy floor fails closed. Its
result binds the manifest and every camera/GRAM PNG by SHA-256 and retains measured
values and failure reasons; rechecking those bindings inside the attested bundle
prevents replacement after optical verification.

The built-in macOS provider uses AVFoundation only as a one-shot command:

```sh
python3 tools/capture_macos_camera.py list
python3 tools/capture_macos_camera.py capture \
  --device-id '<exact platform camera id>' --output camera/setup.png
python3 tools/verify_1x_camera_subset.py \
  --manifest camera-manifest.json --output camera-result.json
```

The provider builds in a temporary directory, captures one PNG, and exits; it
installs nothing and never listens in the background. The verifier contract is not
tied to macOS or a camera model, so another one-shot capture provider may preserve
the same PNG/manifest boundary.

A synthetic positive/negative matrix is already part of host tests. The camera lane
becomes mandatory for stable-1.x promotion only after a real camera is attached, a
bench calibration is retained, and thresholds pass on board-01. Until then it does
not create a fictional gate: measurement 0.45 remains explicitly non-publishable.

## Evidence bundle and GitHub attestation

One run creates a self-contained directory:

```text
run.json                 suite/device/candidate/result summary
candidate-manifest.json  binary/map/partition hashes and budgets
serial.ndjson            unmodified device records
scenarios/*.json         actions, assertions, timings, cleanup
frames/*.rgb565          source display-controller bytes
frames/*.png             reviewable screenshots
frames/*.diff.png        visual failures or reviewed baseline changes
camera/*.png             external views of the same four product states
camera-manifest.json     station/camera/calibration and paired frame paths
camera-result.json       hashes, optical metrics, orientation and pass/fail
artifacts.sha256         hash of every retained file
runner-result.json       unsigned local result; not a release trust boundary
```

The runner result carries candidate SHA-256, firmware-reported build ID, suite
revision, board/profile ID, pass/fail, and bundle hash. After local verification, the
directory is packaged deterministically as `hil-evidence.tar.gz`. GitHub Actions
signs both candidate and archive through `actions/attest@v4`: the job receives a
short-lived OIDC identity, and Sigstore binds the signature to repository, commit,
workflow, and protected environment. This flow has no persistent private key, PEM
file, or GitHub secret containing a signing key.

`runner-result.json` can never make a bundle release-eligible by itself. The gate
requires successful `gh attestation verify` for both exact artifacts and then
rechecks all inner hashes, session identities, and candidate bindings.

## Release gates

| Gate | Frequency | Minimum scope |
|---|---|---|
| `device-smoke` | each merge/available station | flash, cold boot, Self-Test Quick, Home/Diagnostics/Back, product Survey→commit→Library→export, TFT, resources, safe outputs |
| `device-regression` | nightly/firmware change | Self-Test Full/Guided non-destructive plan, all available workflows, EN/RU golden matrix, repeated navigation, storage read/reopen |
| `release-candidate` | before publishing | same complete applicable Self-Test plan plus independent host verdict, Stage Demo, install/update/rollback, reboot paths, destructive HIL attestations, budgets, mandatory camera subset |

GitHub-hosted CI builds the candidate, runs host tests, and GitHub-attests the exact
binary. A dedicated self-hosted runner in the protected `hil-production` environment
first verifies candidate provenance, then flashes it and returns evidence. The
promotion job accepts only both GitHub attestations from
`.github/workflows/prerelease-hil.yml` on `main`, checks the required suite/board
matrix, and attaches the same binary; rebuilding between HIL and publication is
forbidden.

## Safety and privacy

- transport is local USB with no network listener;
- normal Actions do not bypass confirmations, permissions, or resource leases;
- screenshot/export is potentially sensitive and logs are sanitized by scenario
  policy;
- unknown media is never selected automatically;
- destructive scenarios require a separate suite, explicit device/media identity,
  and a physically dedicated bench;
- public pull requests never target the HIL runner; the environment permits only
  `main`, and the one-use runner is registered only for this repository after an
  explicit local `check`;
- timeout or runner crash must restore safe power/resources or quarantine the
  station until operator recovery.

## Alternatives

| Option | Advantages | Drawbacks | Role |
|---|---|---|---|
| Device-only self-verdict | host-independent, simple factory launch | firmware would validate itself; code/flash cost; weak candidate/golden trust | rejected as release authority; the UI remains a client of the shared checks |
| Separate test firmware | can include dangerous instrumentation | does not test exact release bytes; test-only behavior risk | destructive fault injection |
| Camera/button/power robot only | strongest black-box fidelity | costly, slow, harder diagnosis | small RC subset and physical qualities |
| Emulator/host screenshots only | fast, inexpensive CI | no real TFT/GPIO/bus/timing/build proof | early feedback, never the release gate |
| Hybrid host + firmware evidence boundary | exact candidate, real pixels/state, flexible suites, strict gate | needs a HIL station and versioned protocol | **recommended primary flow** |

## Implementation sequence

1. Merge current boot/UI/capture/metrics scripts into one manifest-driven runner
   holding one serial connection.
2. Freeze a minimum board-01 `device-smoke` and deterministic Home/Diagnostics/Back
   golden set.
3. Add firmware build identity/test-session envelope and evidence-bundle index.
4. Bring up a self-hosted HIL station, immutable candidate download, and keyless
   GitHub Artifact Attestations; do not fake-gate the existing 0.x release workflow
   before a real run exists.
5. Move 1.x publication to build-once/test/promote-same-bytes.
6. Add relay power-cycle, camera, and measurement instruments as available.

## One-time GitHub setup

Before the first `.github/workflows/prerelease-hil.yml` run:

1. Create the `hil-production` environment, allow deployments from `main` only, and
   do not require review. Running `release_1x.py check` locally is the explicit grant
   to access the connected board; an extra click would break the one-command contract
   without adding an independent reviewer in a single-maintainer repository.
2. Provide an authenticated GitHub CLI allowed to dispatch workflows, read
   attestations/artifacts, and temporarily register a repository runner, plus Python
   3 and USB access to the board.
3. Physical-job Python dependencies are installed from `tools/requirements-hil.txt`
   into an isolated job virtualenv.

No runner is preinstalled. `tools/release_1x.py` downloads the pinned official macOS
arm64 archive into `~/Library/Caches/esp32-leshy/actions-runner`, verifies its SHA-256,
and creates credentials/config/work directory from scratch in a temporary directory.
After the cloud build it registers an `--ephemeral` runner with the `leshy-hil` and
`esp32-div-v2` labels plus a unique `leshy-request-<id>` for that workflow run. It
cannot accidentally accept another queued job, executes exactly its one job,
deregisters, and exits. There is no permanent listener, macOS service, or `launchd`
unit.

No signing secret, PEM file, or public-key provisioning is needed. The serial path is
detected locally when exactly one board is connected, or supplied with `--port`, and
is passed only to that manual run; no GitHub variable is required.

## Operator release contract

With board-01 connected, run the complete gate as one command from a clean `main`
that matches `origin/main`:

```sh
./tools/release_1x.py check 1.0.0
```

The command checks the embedded version and serial port, dispatches a uniquely named
workflow, waits for the cloud build, starts the one-job runner, flashes the exact
candidate, executes device-smoke, and waits for promotion-proof. For a stable `1.x.y`,
success prints `RELEASE READY` and the exact next command:

```sh
./tools/release_1x.py publish <successful-run-id>
```

A prerelease/measurement version may validate the complete path but receives only
`VALIDATION PASSED — NON-PUBLISHABLE VERSION`; `publish` rejects it.

`publish` accepts only a successful manual `main` run with a stable `1.x.y` version,
downloads candidate/evidence again, verifies every file's GitHub attestation, the
bundle's inner binding to `firmware.bin`, and current HEAD equality with the tested
commit. Only then does it create the tag and GitHub Release from the same exact bytes,
without rebuilding. The historical `.github/workflows/release.yml` is restricted to
`v0.*` and cannot intercept a 1.x tag.

The GitHub Actions run, retained artifacts, and Sigstore attestations are canonical
evidence. A gitignored `release-checks/<run-id>.json` is only a convenient local
pointer; losing it does not affect eligibility. On failure the workflow is cancelled,
runner process/registration are cleaned up, and `RELEASE READY` is never printed.

## Current implementation evidence

Version v0.6 implements the first five items, on-demand lifecycle, exact-byte
promotion, and the combined product/generic lane. Both the earlier generic-only and
the current combined GitHub workflows have passed end to end:

- `tools/run_1x_prerelease_hil.py` loads a declarative suite, flashes the exact
  candidate through verified esptool only with explicit `--flash`, performs a cold
  reset, keeps one passive USB session for Actions/captures, and creates a bundle;
- `tests/hil/device-smoke.v1.json` revision 6 defines the dedicated bounded physical
  keypad frontend, fail-closed product admission,
  Home→Diagnostics→Back, and
  product Survey Setup→Running→Detail→Stop & Commit→Library→Detail→Export→Home,
  boot ≤2 s, board/profile, heap ≥128 KiB, owner/lease cleanup, and GPIO2 LOW;
- bounded query steps verify a typed serial artifact inside the same HIL session;
  action/query ambiguity and unsafe commands fail closed, while a partial
  `--scenario` run is never gate-eligible;
- generic UI regression and product-media recovery use explicit, non-overlapping
  device states. `storage.product.unenroll confirm` removes only the NVS CID and does
  not access the SD before deterministic `device-smoke`; afterwards
  `storage.product.enroll disposable-read-only <CID32>` may restore enrollment only
  after exact-CID read-only catalog admission with zero SD writes. Version 0.44 passed
  both halves on board-01 and retains a machine-checked product-boot artifact;
  `run_1x_release_hil.py` now owns this transition and restores enrollment even after
  a generic-lane failure;
- `tools/run_1x_product_survey_hil.py` is the service-free enrolled-media lane. With
  the device and exact product card connected, one invocation optionally flashes the
  exact candidate, performs pre/post cold boots, requires exact-CID read-only recovery,
  acknowledges Start before identity/scan/mount work, then polls the persistent worker
  into Running. It requires live source/lease/backend state, proves scan and observation
  counters advance while Detail is open, enforces Start/Stop callback and Detail/Back
  budgets, admits a write only after bounded cached-FSInfo and passive accounting pass,
  stops the source before committing exactly one next generation, captures
  Setup/Running/Detail/Committed/Export TFT frames, validates persistent Library
  export, and finishes at lease 0. Exceptions still emit terminal evidence and perform
  best-effort owned-state cleanup. The runner records its own source SHA-256 at runtime;
  the retained 0.59 worker run and exact runner bytes are independently machine-checked
  by `check_product_survey_worker_acceptance.py`; the retained 0.60 regression adds a
  source invariant that terminal `Idle` is exposed only after UI cleanup/commit and is
  checked by `check_product_survey_terminal_ack_acceptance.py`;
- `tools/run_1x_product_survey_cancel_hil.py` is the dedicated active-scan negative
  lane. It waits for firmware to expose a physically active passive scan, sends Back,
  requires the cancellation request to snapshot that active state, enforces a 150 ms
  acknowledgement budget and 10 ms callback budget, proves no generation/observation
  change after cold reboot, and ends with closed source/backend, zero writes, and lease
  0. `check_product_survey_active_cancel_acceptance.py` rehashes the retained failed
  0.61 input-probe incident and the exact passing 0.62 bundle; 0.62 also emits bounded
  PCF8574 boot-probe attempts/retries;
- `tools/run_1x_product_survey_missing_source_hil.py` is the exact-source negative
  lane. It arms a one-shot fault only from an idle Home with no runtime owner, enters
  Product Survey through public Actions, and requires a localized terminal TFT state
  after cleanup and lease release. It proves that source start and store open were not
  attempted, zero bytes/observations were created, Select cannot hidden-retry, Back
  returns Home, and cold read-only recovery preserves the prior generation. The exact
  0.68 candidate, runner bytes, framebuffer hashes, CID, invariant heap, zero writes,
  and prior Library 68/25 are independently rechecked by
  `check_product_survey_missing_source_acceptance.py`
  (`E-AUTO-032`/`E-HIL-092`/`E-SURVEY-007`);
- `tools/run_1x_runtime_degradation_hil.py` is the exact runtime-source negative
  lane. It arms a one-shot BLE-unavailable result only from idle Home without
  hardware/storage access, starts a public dual-source Survey, and requires the
  active mask to become Wi-Fi-only while at least two real Wi-Fi cycles continue.
  It then commits, cold-reopens and exports the exact unavailable window before
  returning Home at lease 0. The retained exact 0.75 run, five TFT captures,
  source/candidate hashes, timeline durations, CID and invariant heap are
  independently checked by `check_runtime_degradation_acceptance.py`
  (`E-AUTO-040`/`E-HIL-100`/`E-SURVEY-013`);
- `tools/run_1x_observation_browser_hil.py` is the exact common-browser lane. It
  observes the admitted post-flash boot before any independent reset, waits for one
  complete real Wi-Fi+BLE cycle, moves focus to Filter to stop RF and finalize a
  stable snapshot, then exercises All/Wi-Fi/BLE List/Detail and RSSI history. It
  saves without rescanning, cold-reopens/exports the same session and requires final
  lease 0. Exact 0.76 source/candidate/runner, nine TFT captures, filter counts,
  timeline equality, CID, heap and cleanup are independently checked by
  `check_observation_browser_acceptance.py`
  (`E-AUTO-041`/`E-HIL-101`/`E-SURVEY-014`);
- `tools/run_1x_capture_export_hil.py` is the exact Capture/export lane. It preserves
  the admitted post-flash boot, creates one real Wi-Fi+BLE Session, commits and
  cold-reopens schema v3, then validates immutable build/receive provenance and streams
  the raw canonical CSV between typed begin/end markers. Every sequence, timestamp,
  source, tuning, RSSI and hex-encoded identity/label row is checked; PCAP must return
  `unavailable_no_frame_payload` until raw frames exist. Exact 0.77 source/candidate,
  47-row CSV, ten TFT captures, CID, heap and cleanup are independently checked by
  `check_capture_export_acceptance.py`
  (`E-AUTO-042`/`E-HIL-102`/`E-SURVEY-015`);
- `tools/run_1x_wifi_frame_capture_hil.py` is the exact bounded packet-Capture lane.
  It flashes the exact candidate, preserves the admitted read-only product recovery,
  exercises Capture Setup→Running→manual Stop→PCAP→Back and parses every streamed
  PCAP global/record/radiotap field. It requires the 16×256-byte RAM bound, counted
  overflow, zero invalid/connect/raw-TX/storage calls, five exact TFT states, payload
  scrub and final lease 0. Passing repository evidence deliberately retains no raw
  802.11 or PCAP bytes, only hashes and non-identifying counts/tuning/RSSI ranges.
  Exact 0.78 is independently checked by `check_wifi_frame_capture_acceptance.py`
  (`E-AUTO-043`/`E-HIL-103`/`E-CAPTURE-001`);
- `tools/run_1x_littlefs_parity_hil.py` is the fail-closed disposable-flash lane.
  It selects only inactive OTA1 `app1`, requires two matching full reads and a
  firmware-side hash match before format, performs 32 common SessionStore commits
  plus read-only remount recovery, then restores and rehashes OTA1 and the partition
  table before a cold product-Library check. Passing evidence never retains the
  private backup. Exact 0.69 and the retained run are independently checked by
  `check_littlefs_parity_acceptance.py` (`E-AUTO-033`/`E-HIL-093`/
  `E-STORAGE-024`); reset-boundary and physical power-cut lanes remain separate;
- `tools/run_1x_ui_typography_hil.py` is the service-free exact-TFT typography lane.
  It requires an already flashed candidate, validates the running app identity and
  candidate artifact hashes, normalizes Home/language/persisted Self-Test mode, and
  captures 18 EN/RU framebuffers through public Actions/queries. It includes
  persistent Library detail, Quick result, Full preflight, all five guided common
  states and the honest blocked result, then restores a pixel-identical Russian Home.
  It requires Quick 8/8, Full 9/10 with one declared blocker, zero side effects/input
  errors/drops, LOW buzzer, invariant heap, and final lease 0. Exact 0.63 and the
  runner's own final bytes are independently checked by
  `check_ui_typography_acceptance.py` (`E-AUTO-027`/`E-HIL-087`/`E-UX-008`);
- `tools/run_1x_release_hil.py` is the release-facing foreground orchestrator. It
  runs product first, derives the admitted exact CID, safely removes only its NVS
  enrollment, flashes and runs generic `device-smoke` revision 6, performs exact-CID
  read-only re-enrollment, and proves a final enrolled Home/owner-none/lease-0 boot;
  `verify_1x_release_hil_bundle.py` independently validates both child bundles and
  every state boundary before GitHub can attest the combined archive;
- golden bootstrap creates missing compressed RGB565 only and refuses to overwrite
  existing files; a normal run requires exact Home/Back and masked-exact Diagnostics
  with one explicit dynamic region;
- `tools/verify_1x_prerelease_bundle.py` rehashes every artifact and checks the exact
  candidate, suite/version, full ESP app ELF SHA-256, and local-result binding; an
  unsigned local result is rejected by default and can only be development-verified
  explicitly inside an already GitHub-verified archive;
- `tools/esp_app_identity.py` independently reads the 32-byte ELF digest from the app
  descriptor, while firmware reports that same digest from the running image
  descriptor at cold boot and via `metrics`; any mismatch prevents a gate-eligible
  result;
- host tests deliberately break a manifest, app descriptor, unmasked pixel,
  artifact, candidate hash, and build identity;
- the runner creates a random 128-bit run ID; firmware accepts `hil.begin` only for
  the exact running app identity, rejects a nested session, and ends only that same
  ID. Manifest, begin/end, run, and local result must agree;

The current direct product-lane command is:

```bash
python tools/run_1x_product_survey_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.62.0-input-probe-resilience-measure \
  --output /tmp/leshy-product-survey-hil --flash
```

The dedicated active-scan cancellation regression is:

```bash
python tools/run_1x_product_survey_cancel_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.62.0-input-probe-resilience-measure \
  --expected-cid FE343253440000002000000055019CB7 \
  --output /tmp/leshy-product-survey-cancel-hil --flash
```

The dedicated missing-source terminal-state regression is:

```bash
python tools/run_1x_product_survey_missing_source_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.68.0-missing-source-tft-measure \
  --expected-cid FE343253440000002000000055019CB7 \
  --output /tmp/leshy-product-survey-missing-source-hil --flash
```

The exact typography regression, after building and flashing the same candidate, is:

```bash
python tools/run_1x_ui_typography_hil.py \
  --port /dev/cu.usbmodem2101 \
  --expected-version 0.63.0-roboto-condensed-ui-measure \
  --expected-app-elf-sha256 3171e472c40c49484922c9c1b0ca82b60f2a3b71deedeaf8008604d8751eb01a \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --factory firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.factory.bin \
  --map firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.map \
  --output /tmp/leshy-ui-typography-hil
```

- omitted `--expected-cid` is discovered only from an admitted enrollment whose
  expected and observed 32-byte fingerprints match; an explicit value remains
  available for dedicated-media jobs;
- the candidate is first copied to `candidate/firmware.bin` inside the new bundle,
  rehashed, and only then flashed; the verifier defaults to that indexed copy, so
  evidence no longer depends on a mutable build path;
- `tools/package_1x_prerelease_bundle.py` creates a deterministic `tar.gz`, while
  `.github/workflows/prerelease-hil.yml` builds once, GitHub-attests the candidate,
  runs the combined physical HIL in `hil-production`, attests the evidence archive,
  and rechecks both provenance records, both HIL lanes, state restoration, and exact
  bytes in a separate promotion job;
- ad-hoc Ed25519 signing has been removed from the production design: neither runner
  nor verifier accepts a local signature as release trust;
- `tools/release_1x.py check` automatically performs preflight→dispatch→cloud
  build→ephemeral one-job runner→physical HIL→promotion-proof and retains only a
  disposable local receipt; `publish` re-proves provenance/same bytes and creates a
  1.x Release without rebuilding. Host tests cover SemVer/run identity, the exact
  artifact set, serial selection, and unsafe archive rejection.

The foreground endurance lane composes that exact product command rather than
creating a resident agent or macOS service:

```bash
python tools/run_1x_product_endurance_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.51.0-hardware-boot-watchdog-measure \
  --output /tmp/leshy-product-endurance-hil \
  --duration-seconds 28800 --minimum-cycles 32 --maximum-cycles 64 \
  --interval-seconds 900 --flash --release-endurance
```

It flashes only cycle 1, verifies candidate/app/CID continuity on every later cycle,
and checkpoints the aggregate run plus SHA-256 index after each child. Each cycle
must advance exactly one generation, keep scan/pipeline drops at zero, perform two
read-only recovery boots, retain four GRAM captures, preserve the first heap tuple,
and finish at Home with no owner or lease. A 30-second heartbeat keeps the one-shot
foreground process observable. `--release-endurance` is rejected unless verified
flashing, at least 28,800 seconds, and at least 32 cycles are all configured; short
development runs remain `gate_eligible=false` even when they pass.

`E-HIL-059` is the first retained runner smoke: three cycles, six cold boots,
generation 12→15, 51/51 observations, zero drops/heap drift, and final lease 0. It is
deliberately not endurance evidence. The required 8 h/32-cycle lane is a separate
run, while physical power-cut and the external-camera subset remain separate gates.

The first 0.46 release-endurance attempt is retained as `E-HIL-060`, not discarded:
it positively exercised reset-separated boot retry and then failed closed on a
separate Product Start raw-identity transient. The 0.47 retry fixed that narrow
entry but `E-HIL-061` exposed a lower boot-recovery call that did not return.
Final 0.48 therefore binds RTC retry state to the exact app, retries Product Start
only before filesystem access, and surrounds enrolled boot recovery with a 4 s
independent-core watchdog. The watchdog writes no log and runs no shutdown handler;
it records only RTC state and calls `esp_restart_noos`. `E-HIL-063` deterministically
injects that timeout and recovers generation 27 read-only with zero SD writes;
`E-HIL-064` then advances 27→30 with 45/45 observations, zero drops, and invariant
heap. The retained incident/regression artifact is checked by
`check_product_recovery_acceptance.py`; it is still a short local result, not the
8 h release gate.

The next 0.48 release attempt is retained as `E-HIL-065`: cycle 1 exhausted all
three Product Start identity attempts with an empty CID, then exposed a host
summarizer `TypeError` on the intentionally incomplete failed-child record. The
aggregate checkpoint is recovered as failed. The runner now validates missing retry
and timeout metrics without throwing and retains any unexpected orchestration
exception in the terminal checkpoint.

`E-HIL-066` compares 32 isolated identification-only runs at each clock. On the same
board/card, 400 kHz produced 13/32 valid results and a seven-failure streak, while
100 kHz produced 24/32 and a maximum streak of two. All attempts were read-only,
cleaned the bus, and returned ownership to zero. Candidate 0.49 therefore uses
100 kHz and permits at most eight cleaned raw-only Product Start attempts, including
an empty-CID parse rejection, before any filesystem call. `E-HIL-067/068` then pass
an exact product cycle and a 35→38 three-cycle regression with 46/46 forwarded,
zero drops, invariant heap, and final lease 0. The retained artifact is checked by
`check_product_start_resilience_acceptance.py`; the 8 h/32-cycle gate remains open.

The 0.49 release lane then completed six cycles (generation 38→44, 96/96
forwarded, zero drops and invariant heap) before cycle 7 exhausted the separate
three-attempt boot budget after 5,719.273 seconds (`E-HIL-069`). A safe immediate
probe recovered the exact CID in 6/8 attempts, proving that the media remained
intact and the failure was transient. A proposed 64-byte R1 poll was rejected by
the 32+32 read-only experiment `E-HIL-070`; it did not improve valid reads over
the retained 16-byte limit. Candidate 0.50 instead aligns the narrow reset-separated
boot policy with the existing eight-attempt Product Start budget. The exact
three-cycle regression `E-HIL-071` advances 44→47 with 39/39 forwarded, two
natural boot retries, zero drops/heap drift, and lease 0. The retained artifact is
checked by `check_product_boot_resilience_acceptance.py`; a fresh 8 h/32-cycle run
is still required.

That fresh 0.50 lane failed as retained `E-HIL-072`: cycle 1 advanced 47→48 with
16/16 forwarded and a clean final lease, but cycle 2 produced two clean boot retry
records and then hung after the third ROM app entry. The scheduler-based 4 s
watchdog never reset it; safe DTR/RTS and loader probes received no serial data.
The final cleanup/lease/write state is unknown and therefore fails closed. Candidate
0.51 adds a panic-enabled hardware Task WDT tier whose IRAM hook records only the
armed exact-app timeout. After physical power recovery, `E-HIL-073` flashes/verifies
the exact candidate, observes Task WDT on `loopTask`, reset reason 6, and read-only
attempt-2 recovery with `timeout_restarts=1`, zero writes, complete cleanup, and
lease 0. `E-HIL-074` then advances 48→51 with 37/37 forwarded, six cold boots,
zero drops/heap drift, and final lease 0. The retained failure and successful fix
are checked by `check_product_hardware_watchdog_acceptance.py`; only a new complete
8 h/32-cycle result remains before promotion.

Local combined run `E-HIL-055` passed on the exact 0.45 candidate: product run
`408bad8f085d7012fbc85fa57bdd363d` committed generation 4→5 with 20 passive Wi-Fi
observations, generic run `9c81c9f3d0f9cb0bdb69ebc8d002e8ce` passed all ten
revision-6 goldens, and read-only re-enrollment/final cold boot recovered generation
5/20 with zero SD writes and lease 0. The independent verifier accepted all 64 files;
the deterministic archive is `760fad19…6abad`. That standalone archive remains local
evidence; the following GitHub-native run supplies canonical release trust.

GitHub-native combined run
[`31987498533`](https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31987498533)
on commit `b878b95` passed build/physical/promotion in 2:32/1:39/0:30. GitHub-attested
app `05865dc1…18d1a9` and evidence archive `fcc1e5fe…5992` passed provenance and inner
same-byte verification. Product run `7476ff6b2c0d96a5332e01079302662d` committed
generation 5→6 with 16/16 passive observations; generic run
`a15e136702f65bb29cb811e74d29c330` passed ten goldens; final read-only re-enrollment
recovered 6/16 with zero SD writes and lease 0. The ephemeral runner removed its
credentials and registration, repository runner count returned to zero, and the
measurement version correctly produced `VALIDATION PASSED — NON-PUBLISHABLE VERSION`
without a Release.

Bootstrap run `31975374875` stopped fail-closed before runner registration or flash
on a safe internal symlink in the official archive; the workflow was cancelled and
zero runners remained registered. After allowing archive-internal links only and
adding a negative escape test, rerun
[`31975573475`](https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31975573475)
on commit `97e7145` passed end to end: cloud build/attestation 2:26, physical HIL 59 s,
and promotion-proof 31 s. Exact app `ef08797c…9d63a`, factory
`87457cc7…280af`, ELF `e2d5b32c…edb94`, and evidence archive
`d395d913…162d` are GitHub-attested. The board was ready in 502.053 ms; Actions took
85.164/95.840 ms; Home/Diagnostics/Back had zero mismatched pixels; final owner was
none/lease 0, free/min heap 238,728/233,332 B, and GPIO2 LOW. Session ID
`abbcd74e55aa5c05cfbb4f11a6492902` matched every boundary. The ephemeral runner
removed credentials/registration and exited; repository runners after the run: 0.
The measurement version is intentionally non-publishable.

Final hardened run
[`31976152593`](https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31976152593)
on commit `714ac83` repeated the complete path with exactly pinned Node.js 24 Actions
and no compatibility fallback: cloud build/attestation 2:30, physical HIL 56 s, and
promotion-proof 28 s. Exact app `16ab071a…7799a`, factory `05013e92…f3f9`, ELF
`70ee2b5d…da1`, map `e2761e95…56f1`, and evidence archive `1799719f…5bd` passed
attestation and same-byte verification. Run ID is
`1585357a5c3b4f5bf70dec0e3b5fe317`; ready took 501.840 ms, Actions
85.126/95.192 ms, all three TFT comparisons had zero mismatch, final owner was
`none`/lease `0`, heap total/free/min was 281,392/238,728/233,332 B, and GPIO2 was
LOW. The runner removed credentials and registration, repository runners remained
at 0, and the command correctly ended with
`VALIDATION PASSED — NON-PUBLISHABLE VERSION`; no Release was created.

Board-01 was flashed twice with app candidate SHA-256
`e95d7ede560943744f9b981bf2063b6f31077b600198bc8fa6a528c77e04441b`.
The first run created missing goldens after visual review; the second reflashed the
same bytes and passed cold boot→Home→Diagnostics→Back with 0 mismatched pixels,
ready marker 501.72 ms, action acknowledgements 84.204/95.963 ms, final owner
`none`/lease `0`, free/min heap 238,832/233,436 B, and GPIO2 LOW. Runner result is
`passed=true`, `gate_eligible=true`; bundle verification reports
`development_verified=true` but `release_eligible=false` because this historical run
was outside the GitHub attestation workflow. `run.json` SHA-256:
`16136f08…780f17`.

The next `0.36.0-prerelease-build-identity-measure` candidate adds independent
runtime identity. App SHA-256 `47bd62ad…66cecd5` carries ELF SHA-256
`2e5dfcc2…274e6`; the runner extracted it before flashing and both cold boot and a
repeated `metrics` record reported that full digest. Corrected physical run `c`
reached ready in 505.962 ms, acknowledged Actions in 85.338/94.918 ms, and passed
three visual comparisons with zero mismatch; `run.json` is `d011e052…60dbf8` and
the artifact index is `c021993e…4f318`. Two preceding runs remain failed evidence:
one detected a truncated runtime digest and the other a bounded formatter refusing
an oversized boot record. They prove fail-closed behavior but are not gate passes.

Candidate `0.37.0-prerelease-test-session-measure` completes the test-session
envelope. Self-contained physical run `b` flashed bundled app SHA-256
`25f1bacb…cd83c6` carrying ELF SHA-256 `0c5277bb…ef7ed8`. Run ID
`803dd8cfbd28657240fd64af50019588` agrees across manifest, device begin/end, run,
and attestation; session state moves active true→false and UI revision 0→2. Ready
took 502.245 ms, Actions 84.116/95.379 ms, and all three TFT comparisons had zero
mismatch. `run.json` is `8466fe45…d76948`, the artifact index is
`2f3cb367…4be3e7`, and verification passes without an external candidate argument.

Candidate `0.38.0-product-survey-workflow-measure` expands `device-smoke` to
revision 2. Local full-suite run `ddf0203694d3011788f1762cec64ff11` flashed exact
app `9240cccc…c3e370`, reached ready in 502.731 ms, executed 17 Actions, and verified
idempotent Stop (`changed=false`). Ten real-TFT comparisons had zero mismatch; the
serial export retained generation 2, three observations, zero drops, and
`simulated=true`/`persistent=false`/`radio_touched=false`. Final owner was `none`,
lease `0`, heap total/free/min was 281,360/238,696/233,300 B, and GPIO2 was LOW;
`run.json` is `af5d493f…c2a7` and the artifact index is `c73f08d1…6376d`. This is
local development evidence; a GitHub-native revision-2 attestation has not run yet.

Candidate `0.39.0-product-survey-pipeline-measure` adds a real bounded software FIFO
between the simulated source and Survey in that same scenario. Suite revision 3
requires pipeline ready→drained→committed, counters received/forwarded 3/3, depth 0,
high-water 3, drop 0, and batch trigger none→stop. Full run
`dc64d3b8d0438567a737f9a97d1cf078` flashed exact app `3f3b487b…d3fb19`, reached
ready in 502.915 ms, and executed 17 Actions in at most 98.594 ms; all ten TFT frames
matched reviewed goldens with zero pixel differences. Final owner/lease was
`none`/`0`, heap total/free/min was 281,272/238,608/233,212 B, and GPIO2 was LOW;
`run.json` is `9716a080…074a8f`, index `27da0a1c…cd2b6`. This is local development
evidence; a GitHub-native revision-3 attestation has not run yet.

Candidate `0.40.0-product-admission-policy-measure` advances the suite to revision 4
without changing screens or goldens. A new bounded query before any hardware I/O
requires `explicit_start_required`, store `missing_media`, exact
`/leshy/sessions/v1`, combined resources 14, passive/persistent true, simulated
fallback false, and hardware/radio/mount/write false. Full run
`51a294577b902dd2bd1ed53908e86597` flashed exact app
`83cac871…4d25844`/ELF `dadad5b7…503713`, reached ready in 507.234 ms, retained 17
Actions at no more than 99.066 ms, ten zero-mismatch TFT comparisons, final
owner/lease `none`/`0`, heap total/free/min 281,272/238,608/233,212 B, and GPIO2
LOW. `run.json` is `6361d40e…deafaa`, index `e3796ec3…9608f1`; the verifier accepts
it as unsigned local development evidence but not release-eligible evidence. This
run intentionally did not start the real product RF/SD lifecycle.

Candidate `0.41.0-keypad-frontend-measure` advances the suite to revision 5 after a
physical responsiveness regression exposed that serial Actions did not test the
PCF8574 frontend. The candidate samples/debounces in a dedicated task and queues
stable transitions independently of synchronous TFT redraw. Run
`490608019ef55ae5c230ed1254a82fad` flashed exact app
`03dc165c…70c05c5`/ELF `21f31ab2…ae8958`, reached ready in 503.916 ms, observed a
5 ms maximum keypad sample gap with 930 valid/0 erroneous reads and zero queue
drops, and retained ten zero-mismatch TFT comparisons. Final owner/lease was
`none`/`0`, heap total/free/min was 281,184/233,556/228,160 B, and GPIO2 was LOW.
`run.json` is `ab29096a…b97ee`, index `3b3a3ccb…a0f8ce`. This automatic run proves
the deployed frontend/task/queue contract but intentionally cannot generate
physical switch edges; UI-HIL-A8 is a separate guided pre-release artifact.

The guided edge test then caught two defects that the serial-only suite could not.
On 0.41, a chaotic run captured 43 presses/43 releases with no I2C error but dropped
46 queued press/release transitions. On 0.42, press-only queueing plus state batching
still delivered only 27 of 48 captured presses and dropped 21 because per-action
diagnostic output and a 16-entry queue remained on the consumer path. Both automatic
runs were green, so these are explicit negative evidence `E-HIL-050/051`.

Candidate `0.43.0-keypad-burst-buffer-measure` advances the suite to revision 6,
uses a 64-entry press-only ordered queue, drains the accumulated actions before one
TFT redraw, and emits one diagnostic record per batch. Automatic run
`d28fac6bd45fc9713d7e5e1f114af86c` flashed exact app
`cf0adf5a…befbab0`/ELF `8114a78b…eec75e`, reached ready in 503.657 ms, retained ten
zero-mismatch frames, final owner/lease `none`/`0`, heap total/free/min
281,176/233,140/227,744 B, and GPIO2 LOW. `run.json` is `1990446e…9e1e46`, index
`742ee472…2d557`. The bound physical UI-HIL-A8 artifact then records exactly ten of
each key, 50 presses, 50 releases, 50 public UI dispatches/revisions, 5 ms maximum
sample gap, high-water 6/64, and zero I2C errors, ambiguity, residual depth, or drops.
The retained physical artifact SHA-256 is `c7b8af2e…7523dbdc`.

A historical copy of this real bundle was signed with a temporary Ed25519 key and
returned `release_eligible=true`; the temporary key and copy were then destroyed.
Experiment `E-AUTO-003` proved the mechanics, but the 2026-08-17 product decision
rejected a persistent station key and the production code path has been removed.
`hil-production` is restricted to exactly branch `main`, and the GitHub workflow path
is closed by the evidence above. Queue/quarantine and expansion of the release-candidate
suite remain open.

Low-level GitHub-native verification for diagnostics:

```sh
gh attestation verify <artifact> \
  --repo anton-vinogradov/esp32-leshy \
  --signer-workflow anton-vinogradov/esp32-leshy/.github/workflows/prerelease-hil.yml \
  --source-ref refs/heads/main \
  --source-digest <commit-sha>
```

The candidate and evidence archive live as artifacts of the exact GitHub Actions
run; attestations live in GitHub/Sigstore. After promotion, the same exact bytes and
evidence should be attached to the GitHub Release. There is no secret signing key to
store.

ADR-005 acceptance authorizes incremental implementation of this flow. The 0.x
release workflow is restricted to its own `v0.*` tags; a contract or an unexecuted
runner alone is not a completed release gate.

The 17 August 2026 product decision stopped the 0.51 lane after 12 fully green
cycles/11,330.816 s in order to transition S1→S2. `E-HIL-075` retains the aggregate
and all child hashes, generation 51→63, 144/144 observations, 24 cold boots, 48 TFT
captures, invariant heap, and zero drops/retries/timeouts. The runner remains honestly
`interrupted`/`gate_eligible=false`: this is accepted engineering evidence for the
current slice, not release promotion. The full 8 h/32-cycle floor runs as NFR-004 in
`DEMO-S4` on the completed cross-radio passive platform.
