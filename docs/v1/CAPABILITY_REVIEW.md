# ESP32-Leshy 1.x — 1.0 catalog product review

*Read in: **English** · [Русский](CAPABILITY_REVIEW.ru.md)*

Date: 17 August 2026. Result: **product scope coherent; catalog baseline reviewed;
the PRD technical baseline is accepted by `E-GATE-001`**.

Competitor-feature addenda: **27 August and 1 September 2026**.

## Inputs and review rules

The review maps [Vision](VISION.md), J-01…J-08 and PR/NFR in the
[PRD](PRODUCT_REQUIREMENTS.md), WF-01…WF-08, hardware envelope, delivery stages, and
explicit exclusions to every [catalog](CAPABILITY_CATALOG.md) row.

A 1.0 capability remains only when it has an authorized user outcome, primary IA
owner, requirement, stage, error/cancel path, and verifiable result. A 0.x or
competitor menu item is not sufficient. Conditional hardware remains in scope but
must fail closed when its assembly/evidence is absent.

## Gaps found and closed

| Finding | Why broad rows were insufficient | Baseline correction |
|---|---|---|
| CRV-01 Wi-Fi capture | scan plus generic PCAP export did not promise a real packet/channel workflow needed for parity and evidence | CAP-042 + PR-015: passive bounded monitor/Capture, PCAP, drops, no hidden TX |
| CRV-02 Screenshot | Vision named screenshots but the catalog lacked a user Action, provenance, and Library path | CAP-043 + PR-015: real-TFT screenshot as evidence artifact |
| CRV-03 Offline enrichment | Target promised identities but not version/provenance for local OUI/BLE/protocol data | CAP-044 + PR-019: raw facts stay available; database only enriches |
| CRV-04 Feedback hardware | Settings named sound without an owner for GPIO2/WS2812, quiet mode, or safe idle | CAP-045 + PR-016: one service, idle LOW, bounded cues, non-color fallback |
| CRV-05 Connectivity/secrets | OTA/companion needed networking but setup, offline degradation, and secret boundary were not a user capability | CAP-046 + PR-017: scoped Wi-Fi/USB, no secret export, offline Survey/Library |
| CRV-06 Data maintenance | firmware update recovery is not user-data backup/restore and factory reset | CAP-047 + PR-018: preview/checksum/cancel/recovery and immutable-raw protection |

## Overlap review

- CAP-009/023/042 do not duplicate: Session is context, Capture is an immutable
  artifact, and Wi-Fi monitor is a concrete passive producer.
- CAP-026/027 do not duplicate: one defines formats, the other safe import/export
  transports and parsers.
- CAP-029…031 and CAP-034…036 separate capture/read from Lab replay/write; this is a
  safety boundary rather than duplicate menus.
- CAP-007 and CAP-047 separate firmware recovery from user-data maintenance.
- CAP-017/044 separate measured localization from reference enrichment; database
  content never changes RSSI evidence.

## Coverage outcome

| Check | Result |
|---|---|
| Jobs | J-01…J-08 have capability and WF owners |
| Requirements | PR-001…PR-034 and NFR-001…NFR-013 appear in stages/traceability; PRD is accepted as baseline 1.0 while verification remains staged |
| Information architecture | Every CAP-001…CAP-062 has a primary owner under the UX-S01 task hierarchy |
| Error/cancel behavior | UX-02 defines unavailable/loading/degraded/error/confirm/success and cleanup for every screen family |
| Hardware conditionals | RF shield, GPS, PN532, and sound HW-T09 never become unconditional availability |
| Safety | Passive Capture is separate from Owned Lab; every active output has selected target/fixture, scope, confirmation, deadline, cleanup and physical Stop; no extension can bypass platform enforcement |
| Hard exclusions | Retaining real submitted credentials/payment secrets; unbounded or indiscriminate active output; bypass of broker/safety/watchdog/Stop |
| Deferred, not rejected | Cloud/default telemetry, Peer Link, public executable catalog/mobile sync, external-module protocol, and broad board matrix remain post-1.0 |

## Verdict

Product review initially accepted CAP-001…CAP-047. The later
[feature-level competitor audit](COMPETITIVE_ANALYSIS.md#feature-level-parity-audit)
found nine useful or strategically relevant families (`CF-001…CF-009`). The explicit
27 August product decision accepts all except `CF-005 Peer Link`: the eight accepted
families are now `CAP-048…CAP-055`, `PR-020…PR-027`, and `WF-06…WF-08`, owned by S7.
The 1 September decision then accepted every useful outcome of the seven-source
competitor re-audit that fits the evidence-first instrument plus bounded Owned Lab:
existing capabilities received concrete acceptance refinements and seven new rows
`CAP-056…CAP-062`/`PR-028…PR-034` were added under S7. The stable 1.0 boundary is
therefore **62 capabilities**.

Only three product boundaries are non-negotiable: Leshy does not retain real
submitted credentials or payment secrets; it does not provide unbounded or
indiscriminate active output without a selected target/qualified isolated fixture;
and no app, script, package, developer mode, or companion path can bypass
ResourceBroker, Safety Supervisor, watchdog, expiry, or physical Stop. Targeted
handshake assist, identity/iBeacon emulation, MouseJack injection, bounded
robustness/crash/interference tests, portal/ARP/DHCP/MITM fixtures, evidence
verification, and IR-camera tests are not blanket exclusions: they are named Owned
Lab recipes whose admission must prove scope, containment, time bound and cleanup.

Peer Link and the other deferred integrations remain explicit post-1.0 scope rather
than hidden omissions. They do not change the fixed denominator until a later
product decision creates a new release boundary.

Together with constrained hardware/resource evidence, this scope review closes S1
through `E-GATE-001`. It does not mark capabilities implemented or verified; those
states require the applicable S2…S8 evidence and gates.
