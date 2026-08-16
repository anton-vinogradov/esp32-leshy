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
3. **External camera:** a small mandatory RC subset for panel/backlight/orientation/
   physical damage that GRAM readback cannot observe.

A global permissive pixel threshold is forbidden because it can hide missing
critical text or selection. Updating a golden requires a reviewable image diff,
reason, and suite version bump; the runner never rewrites baselines automatically.

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
| `device-smoke` | each merge/available station | flash, cold boot, Home/Diagnostics/Back, product Survey→commit→Library→export, TFT, resources, safe outputs |
| `device-regression` | nightly/firmware change | all available non-destructive workflows, EN/RU golden matrix, repeated navigation, storage read/reopen |
| `release-candidate` | before publishing | full applicable Stage Demo, install/update/rollback, reboot paths, destructive HIL attestations, budgets, mandatory camera subset |

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
| Full on-device self-test | host-independent, simple factory launch | firmware validates itself; code/flash cost; hard-to-change golden/policy | low-level POST/module checks only |
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

Version v0.5 implements the first five items, on-demand lifecycle, and exact-byte
promotion; a real GitHub workflow run now passes:

- `tools/run_1x_prerelease_hil.py` loads a declarative suite, flashes the exact
  candidate through verified esptool only with explicit `--flash`, performs a cold
  reset, keeps one passive USB session for Actions/captures, and creates a bundle;
- `tests/hil/device-smoke.v1.json` revision 2 defines Home→Diagnostics→Back and
  product Survey Setup→Running→Detail→Stop & Commit→Library→Detail→Export→Home,
  boot ≤2 s, board/profile, heap ≥128 KiB, owner/lease cleanup, and GPIO2 LOW;
- bounded query steps verify a typed serial artifact inside the same HIL session;
  action/query ambiguity and unsafe commands fail closed, while a partial
  `--scenario` run is never gate-eligible;
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
- the candidate is first copied to `candidate/firmware.bin` inside the new bundle,
  rehashed, and only then flashed; the verifier defaults to that indexed copy, so
  evidence no longer depends on a mutable build path;
- `tools/package_1x_prerelease_bundle.py` creates a deterministic `tar.gz`, while
  `.github/workflows/prerelease-hil.yml` builds once, GitHub-attests the candidate,
  runs physical HIL in `hil-production`, attests the evidence archive, and rechecks
  both provenance records and exact bytes in a separate promotion job;
- ad-hoc Ed25519 signing has been removed from the production design: neither runner
  nor verifier accepts a local signature as release trust;
- `tools/release_1x.py check` automatically performs preflight→dispatch→cloud
  build→ephemeral one-job runner→physical HIL→promotion-proof and retains only a
  disposable local receipt; `publish` re-proves provenance/same bytes and creates a
  1.x Release without rebuilding. Host tests cover SemVer/run identity, the exact
  artifact set, serial selection, and unsafe archive rejection.

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
