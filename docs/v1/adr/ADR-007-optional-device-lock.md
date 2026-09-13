# ADR-007: optional Device Lock from first boot

*Read in: **English** · [Русский](ADR-007-optional-device-lock.ru.md)*

- Status: **accepted** by the owner on 13 September 2026.
- Requirements: PR-024, CAP-052; stage: S6.5 functional-first UX / S7 security.
- Context: the shared ProtectedUi gate blocked virgin-device Wi-Fi and spectrum
  menus until a PIN was created, even if the owner intended to disable it. The
  durable store already distinguishes virgin from missing-expected credentials
  and initializes a random data key before PIN setup.
- Decision: initialized virgin devices work without PIN; enrollment remains an
  optional Device → Lock action. Preserve the distinct unconfigured and disabled
  states and existing record/file formats. Access requires a successfully restored
  local key, never just a default enum value. Locked, retry, recovery-only, corrupt,
  missing-expected and unavailable-store states stay closed; update cannot disable
  an existing PIN. No-PIN operation is not an authenticated owner session.
- Alternatives: mandatory setup then disable adds no protection for an owner who
  chooses no PIN; per-radio exceptions leave inconsistent UI/export policies;
  automatically resetting credentials would be a security bypass and is rejected.
- Consequences: no-PIN data lacks PIN-based possession protection. Existing encrypted
  files stay encrypted with the same key; enabling PIN wraps that key, disabling
  retains it. No migration, media enrollment or erasure is part of this change.
  Existing independent strong-auth, RF admission, watchdog, Stop, target and
  storage rules remain unchanged. Lock is a no-op without PIN; it still revokes
  an authenticated session. Cancelled reset must not erase a no-PIN volatile key.
- Verification: host tests cover pre-restore denial, all shared operation classes,
  bootstrap failures, cold restore/key continuity, optional enrollment/locked
  restore/retry/recovery, and cancel. A focused board run must use genuine product
  state (no fixture unlock), open passive menus, preserve credentials and SD,
  retain exact firmware identity, and return all leases. No full-board acceptance
  follows from this policy change. Historical setup-required evidence is retained.
