# Permissioned Automation, HID и пассивная проверка BadUSB

*Читать на: [English](AUTOMATION_HID.md) · **Русский***

- **Возможность:** CAP-054
- **Требование:** PR-026
- **Workflow:** WF-08-A1/A2/A4
- **Архитектура:** [ADR-002](adr/ADR-002-resource-policy.ru.md),
  [ADR-004](adr/ADR-004-action-boundary.ru.md)
- **Состояние:** нормативный контракт; первый implementation slice — пассивный
  allocation-free inspector package и boundary допуска execution

## Результат для пользователя

`Lab → Automation / HID` сначала отвечает на четыре вопроса, ничего не исполняя:

1. кто подписал exact package и доверен ли signer;
2. какой класс target запрошен (`device`, `USB host` или `BLE peer`);
3. какие exact Actions или классы HID events содержатся внутри;
4. какие permissions, ceilings events/output и конечный runtime запрошены.

Действие по умолчанию — **Проверить**. Inspection никогда не отправляет USB/BLE HID
report, не запускает Action, не получает active resource и не сохраняет payload script.
Поэтому он объясняет unsigned, malformed, incompatible, over-permissioned или
over-budget package, не выдавая ему authority.

Execution — отдельный более поздний переход. Он недоступен, пока package не имеет
trusted cryptographic signature, каждый step не допущен policy, Device Lock не
аутентифицировал пользователя, exact target не выбран, granted permissions не
покрывают просмотренный request и не выполнен fresh target-bound confirmation. Cancel
до этого перехода ничего не отправляет.

## Канонический package v1

Signed package — bounded binary record, а не неоднозначный JSON или shell language.
Максимальный размер — 4 096 bytes. Первые 64 bytes содержат magic `LHAU`, версии
wire/kind/signature/target, exact lengths total/signed, версии script/minimum Action
API, mask permissions, ceilings runtime/events/output/steps, package ID 16 bytes,
signer key ID 8 bytes и нулевые reserved bytes. Далее идут bounded records steps.
Последние 64 bytes — raw signature ECDSA-P256/SHA-256 `r||s` над всеми предыдущими
bytes, включая algorithm и key ID.

Kinds package намеренно разделены:

| Kind | Допустимый target | Допустимые steps |
|---|---|---|
| Action automation | это устройство | Delay; один named typed Action ID |
| USB HID | один явно выбранный собственный USB host | Delay; один keyboard usage или bounded pointer event |
| BLE HID | один явно выбранный собственный BLE peer | Delay; один keyboard usage или bounded pointer event |

В package v1 нет raw USB reports, arbitrary descriptors, shell strings, raw GPIO,
radio commands, loops, jumps, recursion, hidden downloads или self-modifying payloads.
Следующая wire version требует compatibility review и migration test; она не может
молча расширить v1.

## Bounds и least privilege

- package ≤4 096 bytes; exact signed body; signature ровно 64 bytes;
- 1…32 steps без trailing или overlapping bytes;
- runtime 1…300 seconds, максимум 128 active events и 1 024 output bytes;
- каждый delay конечен; сумма durations steps не превышает runtime package;
- action IDs используют тот же bounded grammar, что общий Actions CLI;
- keyboard record содержит одну пару modifier/usage и implicit release; pointer
  record — одно bounded relative movement/wheel tuple;
- requested permissions точно равны permissions, выведенным из steps;
  неиспользуемая privilege — policy error, а не игнорируемое поле;
- selected target и fresh confirmation fingerprints совпадают constant-time до
  admission.

Inspection по умолчанию сообщает counts и classes. Он не сохраняет keystroke content,
bytes package, target identifiers или signature material в logs/evidence. Позже
explicit protected export может сохранить оригинальный package как item Library; это
не входит в первый slice.

## Boundary signature и trust

SHA-256 или CRC сами по себе никогда не называются trust. Parser передаёт одному
adapter verifier exact signed byte span, fixed signature и signer key ID. Только
`verified_trusted` делает policy-valid package execution-eligible. Missing/zero
signature, unknown signer, invalid signature, unavailable verifier, unsupported
algorithm или incompatible API остаются inspectable, но fail closed для execution.

Первый host/build slice использует injected verifier contract, чтобы tests доказали
exact byte span и ordering. Product execution остаётся disabled до подключения real
P-256 verifier и owner-visible workflow trust-store с physical acceptance. Ни test
double, ни локально придуманный checksum не может разрешить product package.

## Boundary execution

Когда path будет разрешён, каждый Action step поступает существующему typed
`ActionDispatcher`; automation не получает driver pointer или более широкий CLI.
USB и BLE HID получают раздельные classes resource/permission, permanent visible Stop,
освобождают reports до leases и не возобновляются после timeout, panic, watchdog, Back,
disconnect, reboot, lock или update. Active HID не требуется для passive package
inspection.

## Delivery slices

1. `next` — canonical parser, passive summary, interface verifier, strict ordering
   policy/admission и mutation/ceiling/permission/target negative host tests.
2. `planned` — выбор package из Library и compact EN/RU UI Inspector; malformed и
   unsigned packages можно посмотреть, но нельзя запустить.
3. `planned` — real P-256 trust adapter и owner-visible enrollment/revocation keys;
   cold restore и interaction Device Lock.
4. `planned` — execution named Action-only package через shared dispatcher, audit и
   cleanup timeout/cancel/panic.
5. `planned` — USB HID на exact owned fixture, затем отдельно BLE HID; каждый получает
   dedicated HIL no-output-before-confirm и physical stop.

Ни один slice не заявляет active HID по parser tests, screenshot или simulated target.

