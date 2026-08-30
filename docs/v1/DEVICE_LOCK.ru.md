# Контракт Device Lock

*Читать на: [English](DEVICE_LOCK.md) · **Русский***

Device Lock — локальная граница безопасности для защищённых настроек, secrets,
сохранённого evidence, export, backup и companion-доступа. Она никогда не должна
отключать Stop, panic, cleanup, update recovery или destructive factory reset.

## Текущая граница реализации

Exact physical `1.0.0-dev.278` принимает responsive on-device status/PIN editor и
watchdog-cooperative production PBKDF2 поверх foundation dev.277. Exact physical
`1.0.0-dev.280` принимает isolated enrollment PIN, cold restore locked и
reset-resistant retry. Exact physical `1.0.0-dev.281` затем принимает все пять
неверных попыток до cold-restored `recovery_only`, полную matrix
protected-deny/safe-allow, непрозрачный отказ реального запуска Library, export без
возврата content, non-destructive preview reset, destructive recovery с erase до
credential и explicit cleanup fixture. Exact physical `1.0.0-dev.283` добавляет
authenticated encrypted product storage: PIN-wrapped random data key, chunked files
`LENC` AES-256-GCM, binding path/header/chunk, ciphertext separation, exact-size
validation и authenticated read-only cold reopen. Implementation boundary CAP-052
закрыт; power-cut, взаимодействие signed update/recovery и privacy review остаются
release hardening, а не отсутствующей product functionality.

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
- record: fixed little-endian `LDLK` schema v2 размером 128 bytes с generation,
  persistent failure count, wrapped data-key material, проверкой reserved bytes и
  CRC32;
- storage: NVS namespace `leshy1-lock`, credential `credential.v2`, bootstrap key
  `data-key.v1` и независимый latch `enrolled.v1`;
- порядок публикации: commit credential, затем commit latch;
- destructive clear: protected data, commit удаления credential, затем commit latch.

Latch отличает действительно virgin device от пропавшего expected credential. Он
не может противостоять полному physical erase flash. Для offline-защиты сохранённого
evidence используется случайный 256-bit data key. До setup PIN key bootstrapped в
NVS, поэтому normal product storage сразу encrypted. При настройке PIN из master
PBKDF2 120 000 rounds выводятся независимые domains verifier и wrapping key, data key
wrap-ится AES-256-GCM, credential v2 durable публикуется, bootstrap copy стирается.
Lock, reset, watchdog и update boundaries стирают volatile copy data key. Protected
Session files используют отдельный namespace `enc-` и 32-byte header `LENC`; каждый
plaintext chunk 256 bytes получает отдельные nonce и authentication tag 16 bytes,
а AAD связывает path, header и chunk index. Legacy plaintext files никогда не
интерпретируются как encrypted heads.

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
4. `done` — physical `recovery_only` на пятой попытке, cold restore, ordering
   destructive recovery, matrix safe operations и реальные отказы protected
   UI/export без возврата content (`dev.281`).
5. `done` — authenticated-encryption key envelope, encrypted product storage,
   physical ciphertext separation и authenticated cold reopen exact CID (`dev.283`).
6. `planned` — destructive recovery/power-cut matrix, взаимодействие signed
   update/recovery, privacy review и release HIL.
