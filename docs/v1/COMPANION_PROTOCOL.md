# ESP32-Leshy 1.x — local companion protocol

*Read in: **English** · [Русский](COMPANION_PROTOCOL.ru.md)*

This document defines the versioned boundary shared by the local USB and Web
companion adapters. It implements [ADR-004](adr/ADR-004-action-boundary.md): a
transport may adapt typed Actions and read-only projections, but never receives a
driver, filesystem, radio, or wider-permission API.

## Connection envelope v1

Both transports accept the same bounded JSON object. USB carries one object per
NDJSON line; the local Web presentation carries the identical JSON body in one HTTP
request. A frame is at most 512 bytes and the parser uses caller-owned fixed storage.

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

| Scope | Meaning | Current S6.5 transport slices |
|---|---|---|
| `session.read` | list/open immutable Session projections | available only from the live, ready Targets snapshot |
| `target.read` | list/open Target and evidence projections | available only from the same live Targets catalog |
| `target.compare` | invoke/read `target.compare` over exact Session bindings | available only for the already-computed exact pair; also requires both read scopes |
| `target.mutate` | typed Target metadata mutations | available with `target.read` for Favorite, Name, Notes and tag add/remove while Targets is ready; correlation/merge remain unavailable |
| `library.export` | device-side export Action | remains unavailable; the first offline export is assembled by the companion from the granted read projections |
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

After a successful connect, either accepted transport uses the following exact request
shapes. Fields
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
Leaving Targets destroys that working set and resets the transport grant; reconnecting
to a new Targets instance is mandatory. The physically accepted runtime transport is
native USB CDC. `Serial0` remains the legacy diagnostic console and cannot negotiate
this protocol.

## Offline snapshot and local search v1

The first export slice deliberately adds no wider device capability. A host companion
walks every bounded `session.*`, `target.*` and `target.compare` page over an already
granted read-only native-USB session, verifies each summary/count boundary, and then
creates one local `leshy.companion.offline.v1` snapshot. The device-side
`library.export` scope therefore remains unavailable and the exporter receives no
filesystem, storage, network or radio path.

The artifact has exact top-level fields: schema/kind/protocol/source transport,
`complete:true`, counts, two stopped Sessions, 1…16 complete Targets, comparison
coordinates/counts/items, and `snapshot_id`. Target text remains canonical uppercase
hex UTF-8; identities and evidence retain their typed, bounded records. Unknown
fields, partial snapshots, malformed or over-bound text/IDs, duplicate Target or
comparison IDs, inconsistent counts/session coordinates, non-canonical JSON and a
mismatched digest all fail closed. `snapshot_id` is lowercase SHA-256 over compact
sorted-key JSON of the complete payload without the ID itself; the export file is
that same canonical JSON with one final newline.

Local search validates the whole snapshot before use and then case-folds name, notes
and tags. Radio identities can be searched by kind, exact hex, or punctuation-free
hex, so a displayed colon-separated MAC matches its stored identity. Results preserve
the stable Target order and report only the matched field classes. The snapshot can
contain user-authored names/notes and observed device identities: it is a local user
artifact and must not be copied into retained/public HIL evidence. Compact evidence
retains only hashes, counts, searched field classes and Boolean match results.

## Local Web presentation and runtime lifecycle

The Web adapter serves a self-contained offline page at exact
`GET /` and accepts the shared request body only at exact
`POST /api/v1/companion`. The API requires exact `Content-Type: application/json`, a
known non-zero `Content-Length` no greater than 512 bytes and an explicitly authorized
device session. Chunked bodies, GET bodies, unknown routes, wrong methods or media
types, empty/mismatched/oversized bodies and an unavailable session fail closed before
the companion parser sees a byte. Transport errors use bounded schema-v1 JSON and
never publish a partial request.

The responsive page loads no external scripts, fonts, images or network resources. It
renders Sessions, Targets, Compare and Target details from the same paged projections;
Favorite alone is exposed as a first mutation and still performs
preview -> explicit browser confirmation -> one-time confirm -> status. All device
text is escaped before HTML insertion. The presentation adapter owns no Wi-Fi,
credential, storage, driver or radio API.

Exact 0.181 runtime activation is intentionally separate. In ready Targets, the user
opens Detail -> Actions -> Local Web. The first Right opens a consent overlay and does
not start a network; a second Right creates a random RAM-only WPA2/CCMP credential and
starts one local AP/listener. Credentials are neither persisted nor emitted by the
diagnostic protocol. Admission is one client with a 10-minute idle and 30-minute
absolute lifetime. Back/stop destroys the listener, AP, authorization and credential.
Targets foreground memory and the idle Survey worker are suspended only while needed
to admit the Wi-Fi driver on the zero-PSRAM profile; Targets returns on stop and the
worker returns after leaving Targets. The one-time network core may remain initialized,
but it retains no listener, AP, credential or grant.

Candidate 0.182 adds a physical-HIL-only observability boundary without changing that
user contract. `companion.web.hil-seed` is admitted only inside an exact active HIL
session, after the Local Web consent overlay is staged, before authorization and only
once. It accepts exactly 16 non-zero entropy bytes, returns only an armed/not-armed
result plus the public SoftAP MAC, and never returns the resulting SSID or passphrase.
Start consumes and scrubs the value; stop, HIL end and every failure also scrub it.
Normal user starts still call the ESP hardware RNG and cannot select this path.

The paired macOS runner requires the exact serial port, a **dedicated idle** Wi-Fi
interface, its enabled network service and the expected SoftAP MAC as explicit
arguments. An interface with an SSID, association or IPv4 fingerprint is rejected
before any network mutation; the Mac's active Wi-Fi is never eligible. On the
dedicated interface it snapshots only power and association, joins the derived
temporary AP, disables ambient HTTP proxies, walks
every page of Session/Target/Compare over HTTP, compares the same pages over native
USB, and performs a Favorite toggle/restore through two confirmed atomic mutations.
It never records the entropy, temporary passphrase or prior SSID, refuses to overwrite
an existing preferred network with the temporary SSID and removes the HIL profile it
created. A `finally` path must prove the prior powered-off, saved-network, or
powered-on/disconnected state was restored before the run may pass. This is a
host/build-ready gate definition only;
physical HTTP parity is not accepted until its retained run passes.

## Trust and lifecycle rules

- A local cable or loopback socket is transport locality, not authorization.
- A connection is bound to one explicit device-session permission mask and the exact
  foreground Targets snapshot; leaving it, reset, or revoke removes the grant.
- Capabilities are advertised only after exact scope negotiation; unavailable future
  functions are not presented as working.
- Host assembly of an offline snapshot does not advertise or imply the unavailable
  device-side `library.export` scope.
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
path. No running Web listener, export, or connectivity implementation is implied by
that physical checkpoint.

Exact `0.173.0-companion-local-web` at source
`9ae7ee5a6013f219cb0cdf406ef5cf1ce57934e3` adds the local Web presentation boundary
described above. Native tests cover exact routes and the 512/513-byte boundary, denial
without partial publication, bounded errors and the offline-page contract; the
embedded JavaScript passes syntax checking and the production image builds twice with
identical hashes from a workspace-local PlatformIO core. This is host/build evidence
only: no network listener was started, no board or serial port was touched and the
accepted physical baseline remains 0.172.

Exact `0.181.0-companion-web-deferred-worker-restore` at source
`6e0f2be76240e38d12805cfd654a7d70c61ae3d8` physically accepts the lifecycle above on
the original DIV. The matching installed partition table is preflighted before the
single application flash. The run retains exact CID, Session generation 161/59,
bounded memory transitions, zero storage writes, zero raw radio TX commands, no port
discovery/Cardputer opens and final lease 0. Two failed precursors remain evidence of
the real Wi-Fi allocation and premature worker-restore defects. The host deliberately
does not join the temporary AP, so no physical HTTP request or USB/Web payload parity is
claimed by this checkpoint.

The 0.182 through 0.195 physical-HTTP candidates remain rejected. The latest exact
0.195 candidate preserves the proven two-buffer Wi-Fi admission profile and serves a
deterministic gzip index (6,596 bytes source, 2,790 bytes on wire), but the physical
request still stopped at 2,048/2,790 bytes. The same attempt then timed out while
restoring the active Mac link. The board cleanup nevertheless reached Home with no
lease; no USB/Web parity or mutation claim is accepted. The runner now fail-closes on
any active host interface and can be resumed only with a dedicated idle adapter or an
external client that cannot disturb the laptop's network.

`0.195.0-companion-web-gzip-index` is currently a host/build candidate. Its
one-shot HIL entropy parser, zeroization, scope guards, deterministic credential test
vector, dedicated-interface guard, proxy-free HTTP client, full pagination/parity and
confirmed mutation/restore assertions pass host checks. Physical HTTP remains open.

The same exact 0.195 image now has a separately accepted offline USB-only result.
`E-COMPANION-006` walks all bounded read projections and creates a canonical
`leshy.companion.offline.v1` snapshot containing 2 Sessions, 16 complete Targets and
7 comparison items. Two runs retain the same snapshot ID and 11,521-byte file SHA;
local search covers name, notes, tags and normalized identities. No application flash,
network tool, Mac Wi-Fi change, device write or private payload/query retention occurs.
Device-side `library.export` remains unavailable. A failed precursor also exposed the
post-Web defect present at that checkpoint: Targets could fail its read-only mount
with `ESP_ERR_NO_MEM` until device reset. Offline export/search is accepted.

Exact `0.196.2-companion-post-web-shared-scratch` and `E-COMPANION-007` close that
reopen defect without using a host network interface. The device-only run starts and
stops the DIV SoftAP with zero associated stations; Stop removes the server, AP
driver/netif/event loop, authorization and RAM credential. The pinned ESP-IDF does
not support `esp_netif` deinitialization, so its network core is explicitly
process-lifetime. Post-Web Targets therefore suspends the idle Survey worker and
reuses the existing static Session/Target codec union for the 24,808-byte Target wire
codec and 11,272-byte admission scratch. It reopens 16 Targets and 7 comparison items,
reproduces the accepted 11,521-byte snapshot, restores the worker and finishes
Home/none/lease 0. Physical HTTP payload parity remains deferred to a dedicated
client; active Mac Wi-Fi is prohibited.
