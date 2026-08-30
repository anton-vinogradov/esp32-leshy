# Device Lock contract

*Read in: **English** · [Русский](DEVICE_LOCK.ru.md)*

Device Lock is the local security boundary for protected settings, secrets,
saved evidence, export, backup and companion access. It must never disable Stop,
panic, cleanup, update recovery or a destructive factory reset.

## Current implementation boundary

Exact physical `1.0.0-dev.278` accepts the responsive on-device status/PIN editor
and watchdog-cooperative production PBKDF2 path over the dev.277 foundation. Exact
physical `1.0.0-dev.280` then accepts isolated PIN enrollment, cold locked restore,
full post-KDF 5/15-second retry intervals, cold retry restore, generation-4 unlock
and explicit cleanup while proving the product namespace remains virgin. Existing
protected actions are not yet admitted through the boundary, the fifth-attempt
`recovery_only` path is not physically accepted, and access control is not a claim
of encrypted stored content.

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

Physical persistence HIL uses the separate disposable namespace
`leshy1-lock-hil`. Every boot defaults to the product namespace; a surviving HIL
fixture only raises `cleanup_required` and prevents the HIL session from ending
until explicit cleanup. The runner never reads or copies the whole NVS partition,
never writes or erases `leshy1-lock`, wipes the ephemeral PIN buffer, and proves a
virgin product state again after a final cold boot.

## Evidence gates

1. `done` — pure state machine, retry/recovery negatives, record corruption,
   production crypto/NVS build and read-only boot restore (`dev.277`).
2. `done` — physical non-persistent status/PIN editor, two exact production KDFs,
   cooperative watchdog scheduling, incremental repaint and zero credential/storage/
   radio mutation (`dev.278`).
3. `done` — physical PIN enrollment, cold credential restore, reset-resistant
   5/15-second retry delay and explicit isolated-fixture cleanup (`dev.280`).
4. `next` — physical fifth-attempt `recovery_only`, destructive recovery ordering,
   and safe-operation HIL; route every protected UI/export/backup/companion/settings action
   through the access matrix and add an authenticated-encryption key envelope.
5. `planned` — destructive recovery/power-cut matrix, signed update/recovery
   interaction, privacy review and release HIL.
