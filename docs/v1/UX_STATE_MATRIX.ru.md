# ESP32-Leshy 1.x — UX-02: матрица состояний

*Read in: [English](UX_STATE_MATRIX.md) · **Русский***

Статус: **low-fidelity baseline S1**. Матрица обязательна для product controllers,
EN/RU copy и будущих TFT snapshots; она не означает, что state уже реализован.

## Общие правила состояния

- State приходит из domain/service, а view не выводит успех из цвета или анимации.
- `Unavailable` показывается до lease/start с reason, evidence и одним безопасным
  следующим действием: Diagnostics, выбрать другой source или отменить.
- `Loading/Starting` всегда bounded, показывает cancel и не блокирует input callback.
- `Degraded` называет недоступную часть и влияние на результат; продолжение требует
  заранее определённой policy, а не молчаливой подмены.
- `Error` сохраняет исходное evidence, освобождает workers/leases и предлагает только
  retry, report, recovery или Back, которые действительно безопасны.
- `Confirm` нужен только для mutation, TX, update, restore/reset или overwrite; Back
  отменяет без side effect. Passive navigation не требует confirm.
- `Success` показывает созданный entity/artifact, integrity, target и следующие
  действия. Toast без доступного результата не считается success.

## Матрица основных экранов

| Контекст | Unavailable / Empty | Loading / Starting | Active / Running | Degraded | Error | Confirm | Success | Back / Cancel invariant |
|---|---|---|---|---|---|---|---|---|
| UX-S01 Home | disabled task содержит короткую причину; пустого Home не бывает — Device остаётся доступен | capability refresh не скрывает прошлый inventory | показывает active Session/TX/storage operation | badge + reason, без ложного READY | global fault ведёт в UX-S24 | отсутствует | обычный selectable Home | Back не выходит в undefined state; TX сначала panic-stop |
| UX-S02 Survey Setup | нет passive source: reason + Diagnostics; storage unavailable предлагает bounded volatile preview только если workflow это допускает | preview проверяет capabilities/resources/storage, Cancel видим | ещё не running | несовместимый source снят с объяснением и итоговым duty cycle | start не создаёт Session и оставляет zero leases | только если выбран explicitly degraded/volatile plan | Start переходит ровно в одну UX-S03 Session | Back сохраняет настройки draft, но не workers/leases |
| UX-S03 Running Survey | не применимо после successful Start | source join/leave имеет bounded progress | timer, sources, duty cycle, drops, storage state, List/Timeline и Stop | failed source назван; остальные продолжаются только по preview policy | Stop workers, сохранить допустимый committed prefix или показать no-commit | Stop не требует destructive confirm | UX-S05 показывает commit/integrity | Back из child не останавливает Session; explicit Stop идемпотентен |
| UX-S04 Observation Detail | Observation missing/corrupt показывает source link и integrity error | bounded payload/decode load, Cancel | immutable facts + Target/Radar/Capture actions | enrichment отсутствует — raw facts остаются | decoder fault не портит source | mutation только для tag/note/derived decode | новый Target/Capture/derived record имеет ID | Back возвращает прежнюю selection UX-S03 |
| UX-S05 Stop & Commit | no-commit объясняет start/cancel/storage outcome | stop/sync progress bounded; UI остаётся responsive | source уже не получает новые data после stop boundary | partial Session явно маркирована | старый committed generation остаётся доступен | overwrite никогда не default | Session ID, size/integrity/storage и Open/Export/Home | повторный Stop ничего не пишет; Back не теряет result |
| UX-S06 Targets | empty показывает, как создать Survey/Target, без fake sample | bounded index/search | filter/sort/selection | enrichment stale/missing показан отдельно | corrupt index открывает recovery/report | delete/merge только отдельно | созданный/изменённый Target видим | Back сохраняет filter/selection |
| UX-S07…S10 Target/Compare/Radar | missing evidence не превращается в уверенный Target | history/diff/radar start cancellable | source facts, confidence, RSSI history и evidence links | часть identities/sessions недоступна с перечислением | radio loss останавливает Radar, но не меняет Target | merge/split/note mutation показывает affected IDs | diff/merge/split обратим и открывает evidence | Back прекращает Radar lease ≤150 мс и сохраняет Target |
| UX-S11/S12 Capture Setup | неподдерживаемый source disabled до входа; screenshot остаётся доступен при рабочем TFT/storage | проверка bounds, destination, capacity и resource preview | ещё не capture | формат/decoder optional; raw Capture остаётся возможным | failure не создаёт false Capture | active/directed mode переводится только в Lab; passive Start отдельный | Start создаёт один running context | Cancel оставляет zero workers/leases/files |
| UX-S13 Capture Running | source loss становится degraded/error, не empty | bounded arm/start | duration/bytes/packets/drops/frequency и permanent Stop | payload incomplete маркирован, не скрыт | stop + cleanup; no corrupt committed artifact | отсутствует для Stop | UX-S14 только после validation/commit | Back равен явному Stop только когда label это показывает; повторный Stop безопасен |
| UX-S14 Capture Result | missing raw blob = integrity fault | decode/save/export cancellable | immutable raw + derived annotations | unknown protocol или отсутствующая DB не мешают raw view | derived failure не меняет raw | Save/export/overwrite preview по операции | Capture ID, checksum/schema/source и Library/Lab link | Back сохраняет committed Capture и закрывает temporary buffers |
| UX-S15…S17 Library/Import/Export | empty предлагает Survey/Capture/Import; missing media — explicit unavailable | scan/validate/import/export с progress и Cancel | offline read не запускает radios | часть media/read-only доступна с reason | malformed/future schema fail closed, report доступен | import target/overwrite/export destination preview | artifact size/checksum/schema/path | Back не удаляет artifact и освобождает storage lease |
| UX-S18…S20 Lab Scope/Confirm | нет saved compatible Capture или TX capability — reason + Library/Diagnostics | regulatory/resource check cancellable | TX ещё запрещён | запрещённый range/power не «понижается» молча | validation оставляет hardware inactive | отдельный экран: scope, source hash, frequency, power, deadline, Stop; default focus Cancel | Confirm выдаёт bounded TX lease и открывает UX-S21 | Back/Cancel не выполняет ни одной TX command |
| UX-S21 Lab Running | не применимо после Confirm | hardware arm входит в deadline и остаётся stoppable | постоянные TX indicator/frequency/power/countdown/Stop; GPIO/LED state | любой telemetry loss считается fault и stop | hardware stop выполняется до error UI | отсутствует | UX-S22 только после physical stop acknowledgement | любой Back/Left, timeout, panic, fault сначала `stopTransmit()` |
| UX-S22 Lab Result | source Capture всегда доступен либо integrity fault | log/result commit bounded | TX уже off | incomplete result явно обозначен | stop failure остаётся critical fault и блокирует новый TX | повтор/replay снова проходит UX-S20 | duration/parameters/stop reason/source hash | Back освобождает TX/resources; повторный result view не передаёт |
| UX-S23/S24 Device/Diagnostics/Self-Test | module state всегда declared/detected/available/conflicted/fault/unknown; отсутствующий по profile модуль получает `not_applicable`, не fake pass | Quick bounded/read-only; Full до работы показывает applicable checks, fixtures, время и side effects | progress каждого check, current resource, cancel boundary и counts pass/fail/blocked; никакого hidden TX | missing fixture/evidence получает `blocked` или `inconclusive` с impact | fault изолирован, cleanup выполняется первым, partial report остаётся экспортируемым | Quick не требует confirm; Full подтверждает только объявленные write/sound/radio side effects с default Cancel | report содержит plan/build/profile/check/result/evidence/artifact hashes и final ownership | Back отменяет на safe boundary, останавливает workers, публикует partial report и освобождает leases |
| UX-S25 Settings/Connectivity/Feedback | unavailable setting hidden/disabled с hardware reason | apply/test bounded | preview языка/theme/quiet/connectivity не меняет Session | offline не error; network service unavailable named | secret не показывается в report/log | Save network/feedback changes показывает scope; secret masked | новое значение read-back и persist state | Cancel восстанавливает committed settings; buzzer idle LOW |
| UX-S26 Storage/Backup/Reset | no media/backup даёт reason; factory reset всё равно не default | scan/checksum/restore progress, Cancel по безопасной boundary | write target/bytes/generation видимы | read-only fallback назван | prior generation сохраняется; recovery path показан | scope/schema/checksum/overwrite plan, default Cancel | verify after write/restore; reset показывает recovery entry | Back до commit ничего не меняет; после commit открывает result |
| UX-S27 Update/Recovery | offline не блокирует SD/USB recovery; no compatible image = reason | download/verify/write bounded с progress | channel/version/signature/slot видимы | beta/rollback state explicit | interrupted update boot/recovery остаётся доступен | version/channel/signature/rollback plan, default Cancel | booted version/hash/provenance + rollback entry | Cancel до publish сохраняет current image; Back не прерывает unsafe boundary |
| UX-S28 Global Dialog | reason/evidence/next action, без тупика | operation name/progress/Cancel | применяется только к underlying context | impact text обязателен | report ID и safe recovery | destructive/active confirm никогда не preselected | возвращает созданный ID/result | modal Back детерминирован; panic имеет приоритет над modal stack |
| UX-S29…S32 Defensive inspection | отсутствие finding не error; unavailable detector/GPS/export/GATT имеет exact reason | detector/capture/route/connect start bounded/cancellable | evidence/confidence, auth completion, route facts или selected GATT target видимы | missing location/enrichment/raw support explicit | source evidence сохраняется; active fallback отсутствует | только connected GATT требует explicit target/permission confirm | saved artifact показывает schema/checksum/source/uncertainty | Back останавливает receiver/connection, disconnect-ит и оставляет zero leases |
| UX-S33/S34 Lock/Serial | locked content скрыт; unavailable recovery/UART имеет remedy | unlock и UART validation bounded | retry state или exact pins/baud/target/lease видимы | transcript/storage не разрешён без explicit selection | bounded denial/overrun/disconnect сначала scrub-ит buffers | PIN change и serial start показывают protected scope/target | unlock или saved transcript/result explicit | Stop/recovery доступны при lock; Serial Back освобождает UART |
| UX-S35/S36 Automation/Recipes | unsigned/forbidden/incompatible package/recipe disabled с reason | signature/policy/resource/target validation cancellable | permissions, target, ceilings, deadline и output/stop видимы | optional result transport не расширяет permissions | watchdog/policy/fault вызывает idempotent cleanup | target/effects/HID/TX scope имеет default Cancel | audit/evidence result называет package/recipe и stop reason | Cancel-before-confirm ничего не отправляет; Back/panic останавливает output до navigation |

## Copy и visual evidence для S2

Для каждого семейства S2 создаёт EN/RU fixtures минимум для normal, selected,
unavailable, empty, degraded, error, confirm и running (если применимо). Snapshot
содержит screen ID, state, capabilities, active owner/lease и Action labels. Критичный
state различим текстом/формой/icon и не зависит только от red/green или buzzer.

## Acceptance UX-02

- Все состояния WF-01…WF-08 представлены строками матрицы; нет error/cancel path,
  существующего только в prose workflow.
- Любой Start/Confirm имеет определённые Starting, Error, Cancel и cleanup outcomes.
- Любой storage mutation сохраняет старый committed generation до нового publish.
- Любой TX state имеет один немедленный Back/Panic stop path, который выполняется до
  navigation/error rendering.
- S2 `DEMO-S2` снимает UX-S01, UX-S24, unavailable/degraded/error dialog и Back;
  следующие Stage Demo добавляют состояния соответствующих строк без новой IA.
