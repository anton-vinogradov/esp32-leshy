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

| Scope | Meaning | Current S6.5 USB slice |
|---|---|---|
| `session.read` | list/open immutable Session projections | available only from the live, ready Targets snapshot |
| `target.read` | list/open Target and evidence projections | available only from the same live Targets catalog |
| `target.compare` | invoke/read `target.compare` over exact Session bindings | available only for the already-computed exact pair; also requires both read scopes |
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

## Read-only request set

After a successful connect, USB accepts the following exact request shapes. Fields
are order-independent, but every operation has an exact field set: missing,
duplicate, unknown, or fields belonging to another operation are rejected. IDs are
32 uppercase/lowercase hex digits and generations are non-zero integers.

```json
{"schema":"leshy.companion.request.v1","kind":"session.list","request_id":"s1","offset":0}
{"schema":"leshy.companion.request.v1","kind":"session.detail","request_id":"s2","source_id":"0123456789ABCDEF0123456789ABCDEF","generation":161}
{"schema":"leshy.companion.request.v1","kind":"target.list","request_id":"t1","offset":0}
{"schema":"leshy.companion.request.v1","kind":"target.detail","request_id":"t2","target_id":"0123456789ABCDEF0123456789ABCDEF","section":"summary","offset":0}
{"schema":"leshy.companion.request.v1","kind":"target.compare","request_id":"c1","baseline_source_id":"0123456789ABCDEF0123456789ABCDEF","baseline_generation":160,"current_source_id":"FEDCBA9876543210FEDCBA9876543210","current_generation":161,"offset":0}
```

`target.detail` has five sections: `summary`, `notes`, `tags`, `identities`, and
`evidence`. Variable text is returned as hex (`name_hex`, or `encoding:"hex"`) so
all byte values remain deterministic without JSON escape growth. Lists and long
sections are page-bounded:

- `session.list` returns the complete bounded two-session pair;
- `target.list` and `target.compare` return one item per frame;
- `notes` returns at most 80 source bytes per frame;
- `tags`, `identities`, and `evidence` return at most two items per frame.

Every paged success contains `offset` and `next_offset`; `null` means complete.
The caller repeats the exact request coordinates with that offset. An offset beyond
the current section returns `offset_out_of_range`. A missing exact Session/Target,
pair, grant, or live capability returns a stable error and no projection payload.

The adapter reads only the two stopped Session bindings, Target catalog and existing
comparison object already owned by the foreground Targets product. It does not mount
storage, reload a catalog, recompute comparison, mutate metadata, or touch a radio.
Leaving Targets destroys that working set and resets the USB grant; reconnecting to a
new Targets instance is mandatory. JSON companion frames are accepted by native USB
CDC only. `Serial0` remains the legacy diagnostic console and cannot negotiate this
protocol.

## Trust and lifecycle rules

- A local cable or loopback socket is transport locality, not authorization.
- A connection is bound to one explicit device-session permission mask and the exact
  foreground Targets snapshot; leaving it, reset, or revoke removes the grant.
- Capabilities are advertised only after exact scope negotiation; unavailable future
  functions are not presented as working.
- This layer owns no storage, driver, radio, secret, or application teardown path.
- Parsers are exercised with exact valid frames, malformed/duplicate/unknown cases,
  every truncation of a golden frame, size limits, scope dependency/permission tests,
  and deterministic USB/Web encoding.

This source/build slice wires all five read-only projections to native USB. Physical
acceptance still requires the explicitly selected board/port delta HIL; no Web,
mutation, export, or connectivity implementation is implied.
