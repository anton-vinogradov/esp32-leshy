# Device Lock contract

*Read in: **English** · [Русский](DEVICE_LOCK.ru.md)*

Device Lock is the local security boundary for protected settings, secrets,
saved evidence, export, backup and companion access. It must never disable Stop,
panic, cleanup, update recovery or a destructive factory reset.

## Current implementation boundary

Exact host/build `1.0.0-dev.277` provides the state machine, credential record,
production ESP32-S3 crypto/NVS adapters and read-only boot restore. The product UI
does not yet enroll a PIN and existing screens/exports are not yet admitted through
this boundary. Therefore this checkpoint is a foundation, not a claim that stored
content is already protected from physical access.

## User contract

- The owner chooses a 6–12 digit local PIN. Repeated and simple ascending or
  descending sequences are rejected.
- The raw PIN is never persisted, logged, exported or retained by Device Lock.
- Unlock is volatile: it expires after 10 minutes idle, after 30 minutes total,
  on clock rollback, reset, update/recovery or another system boundary.
- A wrong PIN is durably counted before another attempt is admitted. Delays are
  5 seconds, 15 seconds, 60 seconds and 5 minutes; the fifth failure enters
  destructive-recovery-only state. Resetting cannot shorten a delay.
- Recovery never reveals protected content. It erases protected data first and
  clears the credential and provisioned latch only after that erase is durable.
  Any partial failure stays locked.

## States

| State | Meaning | Protected access |
|---|---|---|
| `unconfigured` | no credential has ever been published | setup required |
| `locked` | valid credential, attempt allowed | denied |
| `retry_delay` | persistent failed attempt, timer running | denied |
| `recovery_only` | five failed attempts | destructive recovery only |
| `unlocked` | bounded volatile owner session | allowed by operation policy |
| `fault` | missing expected, corrupt or unavailable security state | denied |

Status, Lock, Stop, panic, cleanup, update recovery and confirmed factory reset
remain available in every state. Protected UI/evidence, secret reads, export,
backup, companion and sensitive settings require `unlocked`.

## Credential and storage

- verifier: PBKDF2-HMAC-SHA-256, 120,000 iterations;
- salt: 16 bytes from the ESP32-S3 hardware RNG;
- verifier: 32 bytes, compared in constant time;
- record: fixed 68-byte little-endian `LDLK` schema v1 with generation, persistent
  failure count, reserved-byte validation and CRC32 transport-corruption check;
- storage: NVS namespace `leshy1-lock`, credential `credential.v1` and an
  independent `enrolled.v1` latch;
- publication order: credential commit, then latch commit;
- destructive clear order: protected data, credential commit, then latch commit.

The latch distinguishes a genuinely virgin device from a missing expected
credential. It cannot defeat a complete physical flash erase. Protection against
offline reading of stored evidence requires the planned authenticated-encryption
envelope and signed update/recovery chain; access-control wiring alone is not
represented as data-at-rest encryption.

## Evidence gates

1. `done` — pure state machine, retry/recovery negatives, record corruption,
   production crypto/NVS build and read-only boot restore (`dev.277`).
2. `next` — on-device PIN setup/lock/unlock UI, measured PBKDF2 watchdog budget,
   cold persistence, reset-resistant retry and safe-operation HIL.
3. `planned` — route every protected UI/export/backup/companion/settings action
   through the access matrix and add an authenticated-encryption key envelope.
4. `planned` — destructive recovery/power-cut matrix, signed update/recovery
   interaction, privacy review and release HIL.
