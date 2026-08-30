# Permissioned Automation, HID and passive BadUSB inspection

*Read in: **English** · [Русский](AUTOMATION_HID.ru.md)*

- **Capability:** CAP-054
- **Requirement:** PR-026
- **Workflow:** WF-08-A1/A2/A4
- **Architecture:** [ADR-002](adr/ADR-002-resource-policy.md),
  [ADR-004](adr/ADR-004-action-boundary.md)
- **State:** slice 1 is accepted; slice 2 is implemented in exact host/build
  `1.0.0-dev.289` and physically routed in exact `1.0.0-dev.288`: the passive,
  allocation-free package inspector and
  execution-admission boundary are connected to a read-only Lab product route; the
  top-level Lab route is physically accepted, while nested package TFT evidence,
  real trust and active execution remain unaccepted

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
exact byte span and ordering. Production execution remains disabled until the real
P-256 verifier and an owner-visible trust-store workflow are connected and physically
accepted. No test double or locally invented checksum may promote a product package.

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
2. `implemented / physical nested gate next` — bounded SD package discovery and a
   compact EN/RU Lab → Automation Inspector UI; malformed and unsigned packages are
   viewable but not runnable. Exact dev.289 host/build keeps every EN/RU label inside
   its measured pixel budget; exact dev.288 physically accepts the Lab top-level
   route and zero-output boundary, not yet the nested `.lhau` summary frames.
3. `planned` — real P-256 trust adapter and owner-visible key enrollment/revocation;
   cold restore and Device Lock interaction.
4. `planned` — named Action-only package execution through the shared dispatcher,
   audit and timeout/cancel/panic cleanup.
5. `planned` — USB HID on an exact owned fixture, then separately BLE HID; each gets a
   dedicated no-output-before-confirm and physical-stop HIL.

No slice may claim active HID from parser tests, a screenshot, or a simulated target.
