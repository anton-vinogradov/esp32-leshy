# ESP32-Leshy 1.x — local companion protocol

*Read in: **English** · [Русский](COMPANION_PROTOCOL.ru.md)*

This document defines the versioned boundary shared by the local USB and Web
companion adapters. It implements [ADR-004](adr/ADR-004-action-boundary.md): a
transport may adapt typed Actions and read-only projections, but never receives a
driver, filesystem, radio, or wider-permission API.

## Connection envelope v1

Both transports accept the same bounded JSON object. USB carries one object per
NDJSON line; the later local Web adapter carries the identical JSON body. A frame is
at most 512 bytes and the parser uses caller-owned fixed storage.

```json
{"schema":"leshy.companion.request.v1","kind":"connect","request_id":"desktop-01","protocol":1,"scopes":["session.read","target.read","target.compare"]}
```

| Field | Contract |
|---|---|
| `schema` | exact `leshy.companion.request.v1` |
| `kind` | exact `connect` in this slice |
| `request_id` | 1…32 ASCII letters, digits, `.`, `_`, or `-`; echoed unchanged |
| `protocol` | integer `1` |
| `scopes` | non-empty unique array of known scope IDs |

Unknown/duplicate/missing fields, unknown/duplicate scopes, escapes, controls,
non-ASCII envelope strings, oversized/truncated/trailing input, a different schema,
kind, or protocol all fail closed. A failed parse does not publish a partial request.

## Scopes and capabilities

Scope recognition and scope availability are deliberately separate. This lets an
older v1 client receive a stable `scope_unavailable` result for a known capability
that is not implemented or granted yet.

| Scope | Meaning | S6.5 first slice |
|---|---|---|
| `session.read` | list/open immutable Session projections | available when the device session grants it |
| `target.read` | list/open Target and evidence projections | available when the device session grants it |
| `target.compare` | invoke/read `target.compare` over exact Session bindings | available; also requires both read scopes |
| `target.mutate` | typed Target metadata/correlation/merge mutations | known, unavailable until the confirmed-mutation slice |
| `library.export` | versioned offline export | known, unavailable until the export slice |
| `connectivity.manage` | manage local connectivity/secrets lifecycle | known, unavailable until the connectivity slice |

No scope is ambient. The transport supplies both the scopes granted by the current
device session and the currently implemented scopes; both default to zero. A separate
available-capability mask also defaults to zero, so granting a scope cannot advertise
an operation whose adapter has not been wired. A request is accepted only as a whole
and its granted scope mask exactly equals its requested mask. There is no partial or
silent downgrade.

The first read-only capability catalog is deterministic; an entry appears in a
response only when its adapter is explicitly marked available:

| Capability | Required scope | Typed Action |
|---|---|---|
| `session.list` / `session.detail` | `session.read` | read-only projection; no mutation Action |
| `target.list` / `target.detail` | `target.read` | read-only projection; no mutation Action |
| `target.compare` | all three read scopes | existing `target.compare` request/result schema v1 |

Navigation does not become an Action merely because a remote view renders it. The
comparison itself already crosses the shared typed Action boundary. Later mutations
must reuse the existing Target/merge descriptors and cannot introduce transport-only
storage calls.

## Response envelope

A successful USB negotiation returns one deterministic NDJSON record:

```json
{"schema":"leshy.companion.response.v1","kind":"connect","request_id":"desktop-01","status":"ready","reason":"none","protocol":1,"transport":"usb_serial_ndjson","scopes":["session.read","target.read","target.compare"],"capabilities":["session.list","session.detail","target.list","target.detail","target.compare"],"max_frame_bytes":512}
```

The Web adapter changes only `transport` to `local_web_json`. A denial returns no
granted scopes or capabilities and one stable reason: `scope_denied`,
`scope_unavailable`, or `scope_dependency_missing`. Encoding is also all-or-nothing:
an undersized caller buffer receives length zero and no partial bytes.

## Trust and lifecycle rules

- A local cable or loopback socket is transport locality, not authorization.
- A connection is bound to one explicit device-session permission mask and loses all
  scopes when that session closes, resets, or revokes access.
- Capabilities are advertised only after exact scope negotiation; unavailable future
  functions are not presented as working.
- This layer owns no storage, driver, radio, secret, or application teardown path.
- Parsers are exercised with exact valid frames, malformed/duplicate/unknown cases,
  every truncation of a golden frame, size limits, scope dependency/permission tests,
  and deterministic USB/Web encoding.

The next slice wires `session.list/detail`, `target.list/detail`, and
`target.compare` to this accepted envelope over an explicitly selected USB port.
