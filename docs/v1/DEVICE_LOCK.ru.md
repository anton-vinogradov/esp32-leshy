# Контракт Device Lock

*Читать на: [English](DEVICE_LOCK.md) · **Русский***

Device Lock — локальная граница безопасности для защищённых настроек, secrets,
сохранённого evidence, export, backup и companion-доступа. Она никогда не должна
отключать Stop, panic, cleanup, update recovery или destructive factory reset.

## Текущая граница реализации

Exact physical `1.0.0-dev.278` принимает responsive on-device status/PIN editor и
watchdog-cooperative production PBKDF2 поверх foundation dev.277. Exact physical
`1.0.0-dev.280` затем принимает isolated enrollment PIN, cold restore locked,
полные post-KDF задержки 5/15 секунд, cold restore retry, unlock generation 4 и
explicit cleanup, одновременно доказывая virgin product namespace. Existing
protected actions ещё не проходят admission через boundary, physical path
`recovery_only` пятой попытки не принят, а access control не выдаётся за encryption
сохранённого content.

## Пользовательский контракт

- Owner выбирает локальный PIN из 6–12 цифр. Повторы и простые возрастающие или
  убывающие последовательности отклоняются.
- Raw PIN никогда не сохраняется, не логируется, не экспортируется и не остаётся
  внутри Device Lock.
- Unlock volatile: истекает через 10 минут бездействия, через 30 минут общего
  времени, при clock rollback, reset, update/recovery или другой system boundary.
- Неверный PIN durable учитывается до допуска следующей попытки. Задержки —
  5 секунд, 15 секунд, 60 секунд и 5 минут; пятая ошибка переводит устройство в
  destructive-recovery-only. Reset не сокращает задержку.
- Recovery никогда не раскрывает protected content. Сначала стираются protected
  data, затем credential и provisioned latch. Любая частичная ошибка остаётся locked.

## Состояния

| Состояние | Значение | Protected access |
|---|---|---|
| `unconfigured` | credential ещё никогда не был опубликован | требуется setup |
| `locked` | credential валиден, попытка разрешена | запрещён |
| `retry_delay` | persistent failed attempt, timer активен | запрещён |
| `recovery_only` | пять неверных попыток | только destructive recovery |
| `unlocked` | bounded volatile owner session | по operation policy |
| `fault` | expected state отсутствует, повреждён или недоступен | запрещён |

Status, Lock, Stop, panic, cleanup, update recovery и confirmed factory reset
доступны в любом состоянии. Protected UI/evidence, secret read, export, backup,
companion и sensitive settings требуют `unlocked`.

## Credential и storage

- verifier: PBKDF2-HMAC-SHA-256, 120 000 iterations;
- salt: 16 bytes из hardware RNG ESP32-S3;
- verifier: 32 bytes с constant-time comparison;
- record: fixed little-endian `LDLK` schema v1 размером 68 bytes с generation,
  persistent failure count, проверкой reserved bytes и CRC32;
- storage: NVS namespace `leshy1-lock`, credential `credential.v1` и независимый
  latch `enrolled.v1`;
- порядок публикации: commit credential, затем commit latch;
- destructive clear: protected data, commit удаления credential, затем commit latch.

Latch отличает действительно virgin device от пропавшего expected credential. Он
не может противостоять полному physical erase flash. Защита сохранённого evidence
от offline чтения требует planned authenticated-encryption envelope и signed chain
update/recovery; один access-control не выдаётся за data-at-rest encryption.

Physical HIL persistence использует отдельный disposable namespace
`leshy1-lock-hil`. Каждый boot по умолчанию выбирает product namespace; surviving
fixture HIL только поднимает `cleanup_required` и не даёт завершить session HIL до
explicit cleanup. Runner не читает и не копирует весь partition NVS, не пишет и не
стирает `leshy1-lock`, затирает buffer временного PIN и после final cold boot снова
доказывает virgin product state.

## Evidence gates

1. `done` — pure state machine, retry/recovery negatives, corruption record,
   production crypto/NVS build и read-only boot restore (`dev.277`).
2. `done` — physical непостоянные status/PIN editor, два exact production KDF,
   cooperative watchdog scheduling, incremental repaint и zero credential/storage/
   radio mutation (`dev.278`).
3. `done` — physical enrollment PIN, cold restore credential, reset-resistant
   задержки 5/15 секунд и explicit cleanup isolated fixture (`dev.280`).
4. `next` — physical `recovery_only` на пятой попытке, ordering destructive recovery
   и HIL safe operations; admission каждого protected UI/export/backup/companion/settings
   action через access matrix и authenticated-encryption key envelope.
5. `planned` — destructive recovery/power-cut matrix, взаимодействие signed
   update/recovery, privacy review и release HIL.
