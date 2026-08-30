# Permissioned Automation, HID and passive BadUSB inspection

*Read in: **English** · [Русский](AUTOMATION_HID.ru.md)*

- **Capability:** CAP-054
- **Requirement:** PR-026
- **Workflow:** WF-08-A1/A2/A4
- **Architecture:** [ADR-002](adr/ADR-002-resource-policy.md),
  [ADR-004](adr/ADR-004-action-boundary.md)
- **State:** slices 1 and 2 are accepted. Slice 3 has a physical owner-UI checkpoint
  in `1.0.0-dev.306`: the product restores a bounded canonical P-256 public-key trust
  store from NVS, uses a real mbedTLS verifier for passive inspection and exposes the
  protected list/import/revoke route as the last Device item. Positive enrollment,
  cold restore/revocation and all active execution remain unaccepted

## User outcome

`Lab → Automation / HID` first answers four questions without executing anything:

1. who signed this exact package and whether that signer is trusted;
2. which target class it requests (`device`, `USB host`, or `BLE peer`);
3. which exact Actions or HID event classes it contains;
4. which permissions, event/output ceilings, and finite runtime it requests.

The default action is **Inspect**. Inspection never emits a USB/BLE HID report,
starts an Action, acquires an active resource, or persists script payload. It can
therefore explain an unsigned, malformed, incompatible, over-permissioned, or
over-budget package without granting that package authority.

Execution is a later, separate transition. It is unavailable until the package has a
trusted cryptographic signature, every step is policy-admitted, Device Lock has
authenticated the user, the exact target is selected, granted permissions cover the
reviewed request, and a fresh target-bound confirmation has been made. Cancel before
that transition emits nothing.

## Canonical package v1

The signed package is a bounded binary record rather than ambiguous JSON or a shell
language. Maximum package size is 4,096 bytes. The first 64 bytes contain magic
`LHAU`, wire/kind/signature/target versions, exact total and signed lengths, script and
minimum Action-API versions, permission mask, runtime/event/output/step ceilings, a
16-byte package ID, an 8-byte signer key ID, and zero reserved bytes. A sequence of
bounded step records follows. The final 64 bytes are a raw ECDSA-P256/SHA-256 `r||s`
signature over every preceding byte, including algorithm and key ID.

Package kinds are deliberately disjoint:

| Kind | Allowed target | Allowed steps |
|---|---|---|
| Action automation | this device | Delay; one named typed Action ID |
| USB HID | one explicitly selected owned USB host | Delay; one keyboard usage or bounded pointer event |
| BLE HID | one explicitly selected owned BLE peer | Delay; one keyboard usage or bounded pointer event |

There are no raw USB reports, arbitrary descriptors, shell strings, raw GPIO, radio
commands, loops, jumps, recursion, hidden downloads, or self-modifying payloads in
package v1. A later wire version requires a compatibility review and migration test;
it cannot silently widen v1.

## Bounds and least privilege

- package ≤4,096 bytes; signed body exact; signature exactly 64 bytes;
- 1…32 steps and no trailing or overlapping bytes;
- runtime 1…300 seconds, at most 128 active events and 1,024 output bytes;
- each delay is finite; sum of step durations cannot exceed package runtime;
- action IDs use the same bounded grammar as the shared Actions CLI;
- keyboard records contain one modifier/usage pair and an implicit release; pointer
  records contain one bounded relative movement/wheel tuple;
- requested permissions must equal the permissions implied by contained steps;
  unused privilege is a policy error, not an ignored field;
- selected target and fresh confirmation fingerprints match in constant time before
  admission.

Inspection reports counts and classes by default. It does not retain keystroke
content, package bytes, target identifiers, or signature material in logs/evidence.
An explicit protected export may later preserve the original package as a Library
item; that is not part of the first slice.

## Signature and trust boundary

SHA-256 or CRC alone is never reported as trust. The parser exposes the exact signed
byte span, fixed signature and signer key ID to one verifier adapter. Only
`verified_trusted` makes a policy-valid package execution-eligible. Missing/zero
signature, unknown signer, invalid signature, unavailable verifier, unsupported
algorithm, or incompatible API remain inspectable but fail closed for execution.

The first host/build slice uses an injected verifier contract so tests can prove the
exact byte span and ordering. Exact host/build `1.0.0-dev.304` connects the production
passive Inspector to mbedTLS ECDSA-P256/SHA-256 verification and a canonical NVS
trust record. The store contains at most four public SEC1 points, labels and derived
8-byte key IDs; it never contains a private key. Missing storage restores as an empty
ready store, while malformed storage fails closed. Enrollment/revocation is atomic,
generation-counted and requires both an unlocked Device Lock state and a fresh
confirmation. The owner-visible Device route lists at most four public keys and reads
exactly `/leshy/automation/v1/automation-owner.lhak` from SD. Import validates the
public point and derived key ID before a separate review; mutation still requires a
fresh 30-second confirmation. Exact physical dev.306 accepts the EN/RU list, button
and touch import paths and missing-bundle result without confirming mutation: trust
count/generation remain unchanged, SD is read-only, private-key/Action/HID/RF output
stays zero and execution remains disabled. Positive enrollment and cold restore are a
separate gate. No test double or locally invented checksum may promote a package.

An enrollment artifact is a fixed 128-byte public-only `LHAK` v1 bundle. The protected
GitHub `automation-signing` environment keeps
`LESHY_AUTOMATION_P256_PRIVATE_KEY_PEM` as a secret, derives the public key inside the
job and uploads only `.lhak` plus public JSON metadata. The private temporary file is
removed by the job trap and is never committed or uploaded.

## Execution boundary

When enabled later, each Action step is submitted to the existing typed
`ActionDispatcher`; automation receives no driver pointer and no broader CLI. USB and
BLE HID obtain separate resource/permission classes, have a permanent visible Stop,
release reports before leases, and cannot resume after timeout, panic, watchdog, Back,
disconnect, reboot, lock, or update. Active HID is never required for passive package
inspection.

## Delivery slices

1. `done` — canonical parser, passive summary, verifier interface, strict
   policy/admission order, and mutation/ceiling/permission/target negative host tests.
2. `done` — bounded SD package discovery and
   a compact EN/RU Lab → Automation Inspector UI; malformed and unsigned packages are
   viewable but not runnable. Exact dev.289 host/build keeps every EN/RU label inside
   its measured pixel budget; exact dev.288 physically accepts the Lab top-level
   route and zero-output boundary. Exact physical dev.303 creates only fixed
   `malformed.lhau` and `unsigned.lhau` files below one exact-CID
   `/leshy-hil/<run-id>` StorageGuard directory, drives the public nested UI in EN/RU,
   retains two byte-identical frames per result and proves zero
   Action/HID/resource/RF output, then removes both files and the isolated Device Lock
   fixture before HIL ends. The [machine-checked evidence](../../tests/hil/evidence/board-01-automation-inspector-1.0.0-dev.303.json)
   binds the single-flash lineage, candidate hashes, exact CID and final
   Home/none/lease 0. The product `/leshy/automation/v1` namespace is never written.
3. `in progress` — exact host/build dev.304 connects the real P-256 verifier,
   canonical four-key NVS store, atomic authenticated mutation contract and
   GitHub-built public-only enrollment bundle. Exact physical dev.306 adds the final
   Device item for list/import/revoke, validates only the fixed public bundle path and
   accepts stable EN/RU button/touch missing-bundle behavior with unchanged trust and
   zero output in [machine-checked evidence](../../tests/hil/evidence/board-01-automation-trust-ui-1.0.0-dev.306.json).
   Authenticated positive enrollment, cold restore, trusted/unknown/invalid inspection
   and revocation remain open; execution is still disconnected.
4. `planned` — named Action-only package execution through the shared dispatcher,
   audit and timeout/cancel/panic cleanup.
5. `planned` — USB HID on an exact owned fixture, then separately BLE HID; each gets a
   dedicated no-output-before-confirm and physical-stop HIL.

No slice may claim active HID from parser tests, a screenshot, or a simulated target.
