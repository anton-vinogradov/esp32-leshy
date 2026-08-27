# ESP32-Leshy 1.x — протокол локального companion

*Читать на: [English](COMPANION_PROTOCOL.md) · **Русский***

Этот документ задаёт versioned boundary, общий для локальных adapter USB и Web. Он
реализует [ADR-004](adr/ADR-004-action-boundary.ru.md): transport может адаптировать
typed Actions и read-only projections, но не получает API drivers, filesystem,
radio или permissions шире разрешённых.

## Envelope соединения v1

Оба transport принимают один bounded JSON object. USB переносит по одному object в
строке NDJSON; local Web presentation переносит идентичный JSON body в одном HTTP
request. Размер frame не превышает 512 bytes, parser использует только fixed storage
caller.

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

| Scope | Значение | Текущие transport slices S6.5 |
|---|---|---|
| `session.read` | list/open immutable projections Session | доступен только из live ready snapshot экрана Targets |
| `target.read` | list/open projections Target и evidence | доступен только из того же live catalog Targets |
| `target.compare` | invoke/read `target.compare` над exact bindings Session | доступен только для уже вычисленной exact пары; также требует оба read scope |
| `target.mutate` | typed mutations metadata Target | доступен вместе с `target.read` для Favorite, Name, Notes и add/remove tag при ready Targets; correlation/merge пока недоступны |
| `library.export` | device-side Action export | остаётся недоступным; первый offline export companion собирает из выданных read projections |
| `connectivity.manage` | lifecycle local connectivity/secrets | известен, недоступен до slice connectivity |

Ambient scope не существует. Transport передаёт scopes, выданные текущей device
session, и scopes, реально реализованные сейчас; обе маски по умолчанию нулевые.
Отдельная mask available-capability также по умолчанию нулевая, поэтому выданный
scope не может рекламировать operation, adapter которой ещё не подключён. Request
принимается только целиком, granted scope mask точно равна requested mask. Partial или
silent downgrade запрещены.

Catalog capabilities детерминирован; entry попадает в response
только при явно available adapter:

| Capability | Нужный scope | Typed Action |
|---|---|---|
| `session.list` / `session.detail` | `session.read` | read-only projection без mutation Action |
| `target.list` / `target.detail` | `target.read` | read-only projection без mutation Action |
| `target.compare` | все три read scope | существующие request/result schema v1 `target.compare` |
| `target.favorite.set` | `target.read` + `target.mutate` | существующий Action `target.favorite.set` schema v1 |
| `target.name.set` / `target.notes.set` | `target.read` + `target.mutate` | существующие metadata Actions schema v1 |
| `target.tag.add` / `target.tag.remove` | `target.read` + `target.mutate` | существующие Actions tags schema v1 |

Navigation не становится Action только потому, что её отображает remote view. Само
сравнение уже проходит через общую typed Action boundary. Последующие mutations
обязаны переиспользовать существующие descriptors Target/merge и не могут добавлять
transport-only storage calls.

## Подтверждаемые mutations metadata Target

Connection для mutation явно запрашивает `target.read` и `target.mutate`. Client
сначала получает stable Target ID, current revision и значение через read projection,
затем отправляет preview. Preview ничего не меняет и не выдаёт confirmation ID, если
typed Action не меняет exact current revision.

```json
{"schema":"leshy.companion.request.v1","kind":"target.mutation.preview","request_id":"p1","action":"target.favorite.set","target_id":"0123456789ABCDEF0123456789ABCDEF","expected_revision":7,"favorite":true}
{"schema":"leshy.companion.request.v1","kind":"target.mutation.preview","request_id":"p2","action":"target.name.set","target_id":"0123456789ABCDEF0123456789ABCDEF","expected_revision":7,"value_base64":"TGVzaHk="}
```

Text Actions используют canonical Base64, поэтому полное значение Notes 160 bytes
помещается в общий frame 512 bytes. Decoded значение проходит ту же bounded UTF-8
validation record Target, что и TFT UI. Favorite использует только Boolean поле
`favorite`, text Actions — только `value_base64`; лишние или смешанные поля
fail-close-ятся.

Успешный preview возвращает случайный ненулевой 128-bit `mutation_id`, состояние
`previewed`, exact expected revision и предложенную следующую revision Target. Client
обязан явно подтвердить этот ID:

```json
{"schema":"leshy.companion.request.v1","kind":"target.mutation.confirm","request_id":"c1","mutation_id":"0102030405060708090A0B0C0D0E0F10"}
{"schema":"leshy.companion.request.v1","kind":"target.mutation.status","request_id":"s1","mutation_id":"0102030405060708090A0B0C0D0E0F10"}
```

Confirm повторяет общий preview на live revision, потребляет ID один раз и ставит в
очередь тот же typed Action, который использует TFT UI. Только существующий
supervised exact-CID worker владеет power admission, writable mount, публикацией
dual-head schema v3, reopen verification и cleanup. Status сообщает `saving`, `saved`
или `failed`; повторный confirm возвращает `already_confirmed`. Unknown ID, stale
revision, no-op значение, отсутствующий scope/capability, параллельная mutation или
отозванный при выходе из Targets grant отказываются без storage write. Adapter
companion не включает storage/drivers и не может создать расширенный Action.

## Envelope response

Успешный negotiation USB возвращает одну deterministic запись NDJSON:

```json
{"schema":"leshy.companion.response.v1","kind":"connect","request_id":"desktop-01","status":"ready","reason":"none","protocol":1,"transport":"usb_serial_ndjson","scopes":["session.read","target.read","target.compare"],"capabilities":["session.list","session.detail","target.list","target.detail","target.compare"],"max_frame_bytes":512}
```

Web adapter меняет только `transport` на `local_web_json`. Denial возвращает пустые
granted scopes/capabilities и одну стабильную reason: `scope_denied`,
`scope_unavailable` или `scope_dependency_missing`. Encoding также all-or-nothing:
при малом caller buffer length равна нулю и partial bytes не выдаются.

## Набор read-only requests

После успешного connect любой принятый transport использует следующие exact формы
request. Порядок полей
не важен, но у каждой operation exact набор полей: missing, duplicate, unknown или
поля другой operation отклоняются. IDs содержат 32 hex digits в любом регистре,
generations — ненулевые integers.

```json
{"schema":"leshy.companion.request.v1","kind":"session.list","request_id":"s1","offset":0}
{"schema":"leshy.companion.request.v1","kind":"session.detail","request_id":"s2","source_id":"0123456789ABCDEF0123456789ABCDEF","generation":161}
{"schema":"leshy.companion.request.v1","kind":"target.list","request_id":"t1","offset":0}
{"schema":"leshy.companion.request.v1","kind":"target.detail","request_id":"t2","target_id":"0123456789ABCDEF0123456789ABCDEF","section":"summary","offset":0}
{"schema":"leshy.companion.request.v1","kind":"target.compare","request_id":"c1","baseline_source_id":"0123456789ABCDEF0123456789ABCDEF","baseline_generation":160,"current_source_id":"FEDCBA9876543210FEDCBA9876543210","current_generation":161,"offset":0}
```

У `target.detail` пять sections: `summary`, `notes`, `tags`, `identities` и
`evidence`. Variable text возвращается как hex (`name_hex` или `encoding:"hex"`),
чтобы любые bytes оставались deterministic без роста JSON escapes. Lists и длинные
sections page-bounded:

- `session.list` возвращает целиком bounded пару из двух Sessions;
- `target.list` и `target.compare` возвращают один item на frame;
- `notes` возвращает не более 80 source bytes на frame;
- `tags`, `identities` и `evidence` возвращают не более двух items на frame.

Каждый paged success содержит `offset` и `next_offset`; `null` означает конец.
Caller повторяет exact coordinates request с этим offset. Offset за текущей section
возвращает `offset_out_of_range`. Отсутствие exact Session/Target, pair, grant или
live capability возвращает стабильную error без projection payload.

Read adapter читает только две stopped Session bindings, Target catalog и существующий
comparison object, которыми уже владеет foreground product Targets. Он не mount-ит
storage, не перечитывает catalog, не пересчитывает comparison, не меняет metadata и
не касается radio. Mutation adapter только валидирует и ставит в очередь пять
существующих metadata Actions; writable store и radio objects ему недоступны. Выход
из Targets уничтожает working set и сбрасывает transport grant; для нового instance
Targets обязателен новый connect. Физически принят только runtime transport native
USB CDC. `Serial0` остаётся legacy diagnostic console и не может согласовать этот
protocol.

## Offline snapshot и локальный поиск v1

Первый slice export намеренно не добавляет устройству более широкую capability. Host
companion обходит все bounded страницы `session.*`, `target.*` и `target.compare` в
уже разрешённой read-only native-USB session, проверяет каждую границу summary/count и
собирает один локальный snapshot `leshy.companion.offline.v1`. Поэтому device-side
scope `library.export` остаётся недоступным, а exporter не получает path к filesystem,
storage, network или radio.

Artifact имеет точный top-level набор полей: schema/kind/protocol/source transport,
`complete:true`, counts, две остановленные Sessions, 1…16 полных Targets, coordinates/
counts/items comparison и `snapshot_id`. Текст Target остаётся canonical uppercase
hex UTF-8; identities и evidence сохраняют typed bounded records. Unknown fields,
partial snapshot, malformed либо over-bound text/ID, duplicate ID Target/comparison,
несогласованные counts/coordinates Session, non-canonical JSON и неверный digest
fail-close-ятся. `snapshot_id` — lowercase SHA-256 compact sorted-key JSON полного
payload без самого ID; export file — тот же canonical JSON с одним финальным newline.

Локальный поиск сначала валидирует snapshot целиком, затем case-fold-ит name, notes и
tags. Radio identity ищется по kind, exact hex либо hex без знаков пунктуации, поэтому
показанный MAC с двоеточиями совпадает с хранимой identity. Результаты сохраняют
стабильный порядок Target и сообщают только классы совпавших полей. Snapshot может
содержать пользовательские имена/заметки и наблюдавшиеся identities устройств: это
локальный пользовательский artifact, его нельзя переносить в retained/public HIL
evidence. Compact evidence сохраняет только hashes, counts, классы поисковых полей и
Boolean результаты совпадений.

## Presentation local Web и runtime lifecycle

Web adapter отдаёт self-contained offline page по exact
`GET /` и принимает общий request body только по exact
`POST /api/v1/companion`. API требует exact `Content-Type: application/json`, известный
ненулевой `Content-Length` не больше 512 bytes и явно авторизованную device session.
Chunked body, body у GET, неизвестный route, неверные method/media type,
empty/mismatched/oversized body и недоступная session fail-close-ятся до передачи
байта companion parser. Ошибки transport используют bounded JSON schema v1 и не
публикуют partial request.

Responsive page не загружает внешние scripts, fonts, images или network resources.
Она показывает Sessions, Targets, Compare и detail Target из тех же paged projections;
первой mutation доступно только Favorite, всё ещё через
preview -> явное browser confirmation -> одноразовый confirm -> status. Все данные
device экранируются до вставки в HTML. Presentation adapter не владеет Wi-Fi,
credentials, storage, drivers или radio API.

Runtime activation exact 0.181 намеренно отделена. В ready Targets пользователь
открывает Detail -> Actions -> Local Web. Первое Right показывает consent overlay и
не запускает сеть; второе Right создаёт случайный RAM-only credential WPA2/CCMP и
запускает одну local AP/listener. Credentials не сохраняются и не выдаются diagnostic
protocol. Admission ограничен одним client, 10 минутами idle и 30 минутами absolute.
Back/Stop уничтожает listener, AP, authorization и credential. Foreground memory
Targets и idle worker Survey suspend-ятся только на время admission Wi-Fi driver на
profile без PSRAM; Targets возвращается при Stop, worker — после выхода из Targets.
One-time network core может остаться initialized, но не удерживает listener, AP,
credential или grant.

Candidate 0.182 добавляет observability boundary только для physical HIL, не меняя
этот пользовательский contract. `companion.web.hil-seed` принимается только внутри
exact active HIL session, после staging consent overlay Local Web, до authorization и
только один раз. Он принимает ровно 16 ненулевых bytes entropy, возвращает только
armed/not-armed и публичный SoftAP MAC и никогда не возвращает полученные SSID или
passphrase. Start потребляет и очищает значение; Stop, HIL end и любой отказ также его
очищают. Обычный пользовательский start по-прежнему вызывает hardware RNG ESP и не
может выбрать этот path.

Парный runner macOS требует явными arguments exact serial port, **отдельный idle**
interface Wi-Fi, его enabled network service и ожидаемый SoftAP MAC. Interface с SSID,
association или IPv4 fingerprint отклоняется до любой mutation сети; активный Wi-Fi
Mac никогда не допускается. На отдельном interface runner сохраняет только power и
association, подключается к derived temporary AP, отключает ambient HTTP proxies,
проходит каждую страницу Session/Target/Compare по HTTP, сравнивает те же страницы по
native USB и выполняет Favorite toggle/restore через две confirmed atomic mutations.
Он не записывает entropy, temporary passphrase или прежний SSID, отказывается
перезаписывать existing preferred network с temporary SSID и удаляет созданный HIL
profile. Ветка `finally` обязана доказать восстановление прежнего состояния
powered-off, saved-network или powered-on/disconnected, иначе run не может пройти.
Пока это только готовое по
host/build определение gate; physical HTTP parity не принята без retained passing run.

## Правила trust и lifecycle

- Local cable или loopback socket задаёт locality transport, а не authorization.
- Connection связан с одной явной permission mask device session и exact foreground
  snapshot Targets; выход, reset или revoke удаляет grant.
- Capabilities рекламируются только после exact negotiation scopes; будущие
  недоступные функции не выдаются за работающие.
- Host-сборка offline snapshot не рекламирует и не подразумевает недоступный
  device-side scope `library.export`.
- Слой не владеет storage, driver, radio, secrets или teardown application.
- Parser проверяется exact valid frames, malformed/duplicate/unknown cases, каждым
  truncation golden frame, size limits, scope dependency/permission tests и
  deterministic encoding USB/Web.

Exact `0.170.0-companion-usb-rx` физически принимает все пять read-only projections
на явно выбранном native-USB port оригинального DIV. Retained delta доказывает две
Sessions, 16 Targets, все пять detail sections Target, семь строк comparison, exact
boundary accept/reject 512/513 bytes, отзыв grant после выхода из Targets, invariant
released heap и zero storage writes, radio TX, input drops, port discovery или
открытий Cardputer. Exact `0.172.0-companion-target-mutate` физически принимает bounded
mutation extension на том же port и foreground grant. Он рекламирует Favorite/Name/
Notes/Tag add/remove Target, связывает случайный ненулевой mutation ID 128 bit с
previewed value и exact revision, разрешает один confirm, наблюдает существующий
supervised atomic worker через status и отзывает всё после выхода из Targets. Round
trip Favorite публикует два exact-CID поколения с тремя writes, тремя file syncs и
тремя directory syncs каждое, cold-reopen-ит восстановленное значение и оставляет Home
без lease или TX. No-op, stale revision, unknown/changed token, replay и запросы из
Home отказывают до новой write. Retained failed precursors отделяют неверное ожидание
navigation harness и stale descriptor native USB macOS от firmware failure. Общий reset
helper теперь закрывается до re-enumeration ESP32-S3 и reconnect-ится к exact port;
contract checker не даёт active runners вернуться к stale-descriptor path. Running
Web listener, export или connectivity implementation этим physical checkpoint не
заявляются.

Exact `0.173.0-companion-local-web` на source
`9ae7ee5a6013f219cb0cdf406ef5cf1ce57934e3` добавляет описанную выше boundary local
Web presentation. Native tests покрывают exact routes, boundary 512/513 bytes, denial
без partial publication, bounded errors и contract offline page; embedded JavaScript
проходит syntax check, а production image дважды собирается с идентичными hashes из
workspace-local core PlatformIO. Это только host/build evidence: network listener не
запускался, board и serial ports не затрагивались, accepted physical baseline остаётся
0.172.

Exact `0.181.0-companion-web-deferred-worker-restore` на source
`6e0f2be76240e38d12805cfd654a7d70c61ae3d8` физически принимает этот lifecycle на
оригинальном DIV. Matching installed partition table проверяется до единственной
application flash. Run сохраняет exact CID, Session generation 161/59, bounded memory
transitions, zero storage writes, zero raw radio TX commands, отсутствие port
discovery/Cardputer opens и final lease 0. Два failed precursor остаются evidence
реальных дефектов Wi-Fi allocation и преждевременного восстановления worker. Host
намеренно не подключается к temporary AP, поэтому этот checkpoint не заявляет physical
HTTP request или parity payload USB/Web.

Physical-HTTP candidates 0.182–0.195 остаются отклонёнными. Последний exact candidate
0.195 сохраняет доказанный admission profile Wi-Fi на двух buffers и отдаёт
deterministic gzip index (6 596 bytes source, 2 790 bytes on wire), но physical request
остановился на 2 048/2 790 bytes. Тот же attempt затем получил timeout восстановления
активного link Mac. Cleanup платы всё равно пришёл в Home без lease; parity USB/Web и
mutation claim не принимаются. Runner теперь fail-close-ится на любом активном
interface host и может быть продолжен только с отдельным idle adapter либо внешним
client, который не способен нарушить сеть ноутбука.

`0.195.0-companion-web-gzip-index` сейчас является host/build candidate. Host checks
проходят для one-shot parser entropy HIL, zeroization и scope guards, deterministic test
vector credential, guard отдельного interface, HTTP client без proxy, полной
pagination/parity и confirmed mutation/restore assertions. Physical HTTP остаётся
открыт.

Тот же exact image 0.195 теперь имеет отдельно принятый offline USB-only result.
`E-COMPANION-006` обходит все bounded read projections и создаёт canonical snapshot
`leshy.companion.offline.v1` с 2 Session, 16 полными Target и 7 comparison items.
Два run сохраняют одинаковый snapshot ID и SHA файла 11 521 byte; local search
охватывает name, notes, tags и normalized identities. Application flash, network
tools, изменение Wi-Fi Mac, writes устройства и retention private payload/query не
происходят. Device-side `library.export` остаётся недоступным. Failed precursor также
выявляет открытый firmware defect: после прежнего lifecycle Local Web Targets может
получить fail read-only mount `ESP_ERR_NO_MEM` до reset устройства. Offline
export/search принят, но reclamation Web memory и physical HTTP parity остаются открыты.
