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
| `target.mutate` | typed Target metadata mutations | available with `target.read` for Favorite, Name, Notes and tag add/remove while Targets is ready; correlation/merge remain unavailable |
| `library.export` | versioned offline export | known, unavailable until the export slice |
| `connectivity.manage` | manage local connectivity/secrets lifecycle | known, unavailable until the connectivity slice |

No scope is ambient. The transport supplies both the scopes granted by the current
device session and the currently implemented scopes; both default to zero. A separate
available-capability mask also defaults to zero, so granting a scope cannot advertise
an operation whose adapter has not been wired. A request is accepted only as a whole
and its granted scope mask exactly equals its requested mask. There is no partial or
silent downgrade.

The capability catalog is deterministic; an entry appears in a
response only when its adapter is explicitly marked available:

| Capability | Required scope | Typed Action |
|---|---|---|
| `session.list` / `session.detail` | `session.read` | read-only projection; no mutation Action |
| `target.list` / `target.detail` | `target.read` | read-only projection; no mutation Action |
| `target.compare` | all three read scopes | existing `target.compare` request/result schema v1 |
| `target.favorite.set` | `target.read` + `target.mutate` | existing `target.favorite.set` request/result schema v1 |
| `target.name.set` / `target.notes.set` | `target.read` + `target.mutate` | existing metadata Actions schema v1 |
| `target.tag.add` / `target.tag.remove` | `target.read` + `target.mutate` | existing tag Actions schema v1 |

Navigation does not become an Action merely because a remote view renders it. The
comparison itself already crosses the shared typed Action boundary. Later mutations
must reuse the existing Target/merge descriptors and cannot introduce transport-only
storage calls.

## Confirmed Target metadata mutations

A mutation connection explicitly requests `target.read` and `target.mutate`. The
client first obtains the stable Target ID, current revision and value through the
read projection. It then submits a preview; preview is read-only and returns no
confirmation ID unless the typed Action would change the exact current revision.

```json
{"schema":"leshy.companion.request.v1","kind":"target.mutation.preview","request_id":"p1","action":"target.favorite.set","target_id":"0123456789ABCDEF0123456789ABCDEF","expected_revision":7,"favorite":true}
{"schema":"leshy.companion.request.v1","kind":"target.mutation.preview","request_id":"p2","action":"target.name.set","target_id":"0123456789ABCDEF0123456789ABCDEF","expected_revision":7,"value_base64":"TGVzaHk="}
```

Text Actions use canonical Base64 so a complete 160-byte Notes value still fits the
shared 512-byte frame. The decoded value must satisfy the same bounded UTF-8 Target
record validation as the on-device UI. Favorite uses only the Boolean `favorite`
field; text Actions use only `value_base64`. Wrong, extra or mixed fields fail
closed.

A successful preview returns a random non-zero 128-bit `mutation_id`, state
`previewed`, the exact expected revision and proposed next Target revision. The
client must explicitly confirm that one ID:

```json
{"schema":"leshy.companion.request.v1","kind":"target.mutation.confirm","request_id":"c1","mutation_id":"0102030405060708090A0B0C0D0E0F10"}
{"schema":"leshy.companion.request.v1","kind":"target.mutation.status","request_id":"s1","mutation_id":"0102030405060708090A0B0C0D0E0F10"}
```

Confirm re-runs the shared preview against the live revision, consumes the ID once,
and then queues the same typed Action used by the TFT UI. The existing supervised
exact-CID worker alone owns power admission, writable mount, schema-v3 dual-head
publication, reopen verification and cleanup. Status reports `saving`, `saved` or
`failed`; a repeated confirm returns `already_confirmed`. Unknown IDs, stale
revisions, no-op values, missing scope/capability, a concurrent mutation and a grant
revoked by leaving Targets all fail without a storage write. The companion adapter
has no storage or driver include and cannot manufacture a wider Action.

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

The read adapter reads only the two stopped Session bindings, Target catalog and existing
comparison object already owned by the foreground Targets product. It does not mount
storage, reload a catalog, recompute comparison, mutate metadata, or touch a radio.
The mutation adapter validates and queues only the five existing metadata Actions;
it never receives the writable store or radio objects.
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

Exact `0.170.0-companion-usb-rx` physically accepts all five read-only projections on
the explicitly selected original-DIV native USB port. The retained delta proves two
Sessions, 16 Targets, all five Target-detail sections, seven comparison rows, the exact
512/513-byte accept/reject boundary, grant revocation after leaving Targets, invariant
released heap and zero storage writes, radio TX, input drops, port discovery or
Cardputer opens. Exact `0.172.0-companion-target-mutate` physically accepts the bounded
mutation extension on the same port and foreground grant. It advertises Target
Favorite/Name/Notes/Tag add/remove, binds a random nonzero 128-bit mutation ID to the
previewed value and exact revision, allows one confirm, observes the existing supervised
atomic worker through status, and revokes everything after leaving Targets. A Favorite
round trip publishes two exact-CID generations with three writes, three file syncs and
three directory syncs each, cold-reopens the restored value, and leaves Home with no
lease or TX. No-op, stale revision, unknown or changed token, replay and Home requests
fail before another write. Retained failed precursors distinguish a navigation-harness
assumption and a stale macOS native-USB descriptor from firmware failure. The shared
reset helper now closes before ESP32-S3 re-enumeration and reconnects to the exact port;
its contract checker prevents active runners from returning to the stale-descriptor
path. No Web, export, or connectivity implementation is implied.
