# ADR-005: hybrid host-orchestrated pre-release HIL

*Read in: **English** · [Русский](ADR-005-pre-release-hil.ru.md)*

- status: `accepted`
- date: 2026-08-16
- amended: 2026-08-17 — release trust moved to keyless GitHub Artifact
  Attestations; a persistent station key was rejected; a one-command on-demand
  ephemeral runner lifecycle without a macOS service was accepted
- requirements: PR-010, PR-014, PR-015, NFR-001…003, NFR-005, NFR-010
- stages: S2…S8

## Context

Release 1.x must be verified automatically on real hardware, including navigation,
actual TFT pixels, resource cleanup, and physical workflows. Current serial/action/
capture/HIL scripts prove feasibility, but the release workflow publishes binaries
without device attestation and the separate commands are not a versioned suite.

A full firmware self-test creates self-validation risk. A separate test image does
not prove exact release bytes. An external robot alone is too expensive for every
commit, while an emulator alone does not verify the device.

## Proposed decision

Adopt a hybrid boundary:

1. Release bytes expose a local USB evidence plane for identity, public state/
   metrics, normal typed Actions, actual TFT GRAM capture, and safe-output state.
2. The host runner owns the manifest, expectations, golden images, comparison,
   retries, and pass/fail result.
3. CI builds a candidate once and GitHub-attests the exact artifact through OIDC/
   Sigstore; the HIL station verifies provenance, flashes the exact SHA, and produces
   an evidence bundle. GitHub Actions attests the packaged bundle, while the publish
   job verifies both attestations and promotes the same bytes without rebuilding.
4. Destructive HIL remains a separate diagnostic-image/external-equipment lane and
   never replaces smoke of the exact release candidate.
5. A small camera/power subset complements GRAM capture before RC for physical
   properties invisible to the display controller.
6. The operator runs `tools/release_1x.py check <version>` with the board connected.
   It dispatches the workflow and starts a temporary `--ephemeral` runner for exactly
   one physical job. `publish <run-id>` promotes only a successful stable 1.x run and
   never rebuilds the candidate.

Operational contract: [PRE_RELEASE_HIL.md](../PRE_RELEASE_HIL.md).

## Alternatives

- full on-device self-test;
- separate test firmware as the only gate;
- camera/button/power robot only;
- emulator/host screenshots only;
- publication after manual review of unsigned logs.

Each remains useful as an auxiliary layer but does not replace the recommended flow.

## Consequences

- A versioned USB protocol, manifest schema, golden review, and HIL station are
  required.
- The release artifact is immutable across build, physical test, and publication.
- Neither HIL station nor repository stores a long-lived signing private key;
  identity derives from the GitHub workflow, commit/ref, and protected environment.
- The runner archive may be cached after SHA-256 verification, but config, token, and
  work directory are single-use; a persistent listener/`launchd` is forbidden.
- A safe evidence plane remains in production bytes; dangerous instrumentation does
  not.
- Release may wait for an available station; queueing and quarantine become part of
  deployment reliability.
- GRAM capture removes routine work but cannot replace camera, RF/power/audio
  instruments where physical measurement is required.

## Verification

- one manifest-driven runner completes cold boot→Home→Diagnostics→Back, retains raw/
  PNG/state, and proves lease 0/safe outputs;
- intentional golden/state/candidate-hash mismatch fails closed;
- an interrupted runner quarantines the station or proves safe recovery;
- `gh attestation verify` checks candidate and evidence archive against the pinned
  repository, signer workflow, and `refs/heads/main`; the inner verifier binds the
  archive to the exact published binary again;
- `check` never prints `RELEASE READY` after any cloud/HIL/provenance failure, while
  `publish` rejects a non-main run, different HEAD, prerelease version, or unexpected
  artifact;
- two consecutive RCs pass the unchanged DEMO-S8 release suite.
