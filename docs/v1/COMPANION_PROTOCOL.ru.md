# ESP32-Leshy 1.x — протокол локального companion

*Читать на: [English](COMPANION_PROTOCOL.md) · **Русский***

Этот документ задаёт versioned boundary, общий для локальных adapter USB и Web. Он
реализует [ADR-004](adr/ADR-004-action-boundary.ru.md): transport может адаптировать
typed Actions и read-only projections, но не получает API drivers, filesystem,
radio или permissions шире разрешённых.

## Envelope соединения v1

Оба transport принимают один bounded JSON object. USB переносит по одному object в
строке NDJSON; последующий local Web adapter переносит идентичный JSON body. Размер
frame не превышает 512 bytes, parser использует только fixed storage caller.

```json
{"schema":"leshy.companion.request.v1","kind":"connect","request_id":"desktop-01","protocol":1,"scopes":["session.read","target.read","target.compare"]}
```

| Поле | Contract |
|---|---|
| `schema` | exact `leshy.companion.request.v1` |
| `kind` | exact `connect` в этом slice |
| `request_id` | 1…32 ASCII letters, digits, `.`, `_` или `-`; без изменений возвращается в response |
| `protocol` | integer `1` |
| `scopes` | непустой unique array известных scope ID |

Unknown/duplicate/missing fields, unknown/duplicate scopes, escapes, controls,
non-ASCII envelope strings, oversized/truncated/trailing input, другая schema, kind
или protocol fail-close-ятся. Failed parse не публикует partial request.

## Scopes и capabilities

Распознавание scope намеренно отделено от его доступности. Поэтому старый v1 client
получает стабильный `scope_unavailable` для известной возможности, ещё не
реализованной или не разрешённой.

| Scope | Значение | Первый slice S6.5 |
|---|---|---|
| `session.read` | list/open immutable projections Session | доступен, если выдан device session |
| `target.read` | list/open projections Target и evidence | доступен, если выдан device session |
| `target.compare` | invoke/read `target.compare` над exact bindings Session | доступен; также требует оба read scope |
| `target.mutate` | typed mutations metadata/correlation/merge Target | известен, недоступен до slice confirmed mutation |
| `library.export` | versioned offline export | известен, недоступен до slice export |
| `connectivity.manage` | lifecycle local connectivity/secrets | известен, недоступен до slice connectivity |

Ambient scope не существует. Transport передаёт scopes, выданные текущей device
session, и scopes, реально реализованные сейчас; обе маски по умолчанию нулевые.
Отдельная mask available-capability также по умолчанию нулевая, поэтому выданный
scope не может рекламировать operation, adapter которой ещё не подключён. Request
принимается только целиком, granted scope mask точно равна requested mask. Partial или
silent downgrade запрещены.

Первый read-only catalog capabilities детерминирован; entry попадает в response
только при явно available adapter:

| Capability | Нужный scope | Typed Action |
|---|---|---|
| `session.list` / `session.detail` | `session.read` | read-only projection без mutation Action |
| `target.list` / `target.detail` | `target.read` | read-only projection без mutation Action |
| `target.compare` | все три read scope | существующие request/result schema v1 `target.compare` |

Navigation не становится Action только потому, что её отображает remote view. Само
сравнение уже проходит через общую typed Action boundary. Последующие mutations
обязаны переиспользовать существующие descriptors Target/merge и не могут добавлять
transport-only storage calls.

## Envelope response

Успешный negotiation USB возвращает одну deterministic запись NDJSON:

```json
{"schema":"leshy.companion.response.v1","kind":"connect","request_id":"desktop-01","status":"ready","reason":"none","protocol":1,"transport":"usb_serial_ndjson","scopes":["session.read","target.read","target.compare"],"capabilities":["session.list","session.detail","target.list","target.detail","target.compare"],"max_frame_bytes":512}
```

Web adapter меняет только `transport` на `local_web_json`. Denial возвращает пустые
granted scopes/capabilities и одну стабильную reason: `scope_denied`,
`scope_unavailable` или `scope_dependency_missing`. Encoding также all-or-nothing:
при малом caller buffer length равна нулю и partial bytes не выдаются.

## Правила trust и lifecycle

- Local cable или loopback socket задаёт locality transport, а не authorization.
- Connection связан с одной явной permission mask device session и теряет все scopes
  при закрытии, reset или revoke этой session.
- Capabilities рекламируются только после exact negotiation scopes; будущие
  недоступные функции не выдаются за работающие.
- Слой не владеет storage, driver, radio, secrets или teardown application.
- Parser проверяется exact valid frames, malformed/duplicate/unknown cases, каждым
  truncation golden frame, size limits, scope dependency/permission tests и
  deterministic encoding USB/Web.

Следующий slice подключает `session.list/detail`, `target.list/detail` и
`target.compare` к принятому envelope через явно выбранный USB port.
