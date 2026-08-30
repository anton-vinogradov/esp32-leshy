# Контракт Device Lock

*Читать на: [English](DEVICE_LOCK.md) · **Русский***

Device Lock — локальная граница безопасности для защищённых настроек, secrets,
сохранённого evidence, export, backup и companion-доступа. Она никогда не должна
отключать Stop, panic, cleanup, update recovery или destructive factory reset.

## Текущая граница реализации

Exact host/build `1.0.0-dev.277` содержит state machine, credential record,
production adapters crypto/NVS ESP32-S3 и read-only restore при загрузке. Product UI
пока не настраивает PIN, а существующие screens/exports ещё не проходят admission
через эту границу. Поэтому checkpoint является foundation, а не заявлением, что
сохранённые данные уже защищены от physical access.

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

## Evidence gates

1. `done` — pure state machine, retry/recovery negatives, corruption record,
   production crypto/NVS build и read-only boot restore (`dev.277`).
2. `next` — on-device UI PIN setup/lock/unlock, измеренный PBKDF2 watchdog budget,
   cold persistence, reset-resistant retry и HIL безопасных операций.
3. `planned` — admission каждого protected UI/export/backup/companion/settings
   action через access matrix и authenticated-encryption key envelope.
4. `planned` — destructive recovery/power-cut matrix, взаимодействие signed
   update/recovery, privacy review и release HIL.
