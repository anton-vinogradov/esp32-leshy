# ESP32-Leshy 1.x — goal traceability

*Read in: **English** · [Русский](TRACEABILITY.ru.md)*

Document status: initial S1 matrix. Requirement acceptance text is not duplicated here; it
lives in [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md).

## Top-level goals

| Goal | User outcome | Jobs | Requirements | Stages | Final evidence |
|---|---|---|---|---|---|
| G-001 | One autonomous cross-radio session | J-01, J-03 | PR-001…PR-007, NFR-002…NFR-009 | S1–S4 | integration traces, storage fault tests, 8h HIL |
| G-002 | Identification, localization, and comparison | J-02, J-04 | PR-004, PR-006…PR-008, NFR-008…NFR-010 | S3, S6 | reference-workflow HIL + golden session diff |
| G-003 | Useful standard hardware coverage | J-03, J-05 | PR-001, PR-002, PR-009, PR-014 | S1, S2, S4, S5 | capability matrix + module HIL matrix |
| G-004 | Safe work on owned equipment | J-05, J-06 | PR-009, PR-013, NFR-002, NFR-006, NFR-007 | S1, S2, S5, S7, S8 | policy tests + physical TX-stop HIL |
| G-005 | Reliable offline-first field operation | J-01…J-05 | PR-005, PR-006, PR-010…PR-012, NFR-001…NFR-010 | S2–S8 | endurance, recovery, rollback, accessibility matrix |
| G-006 | Extension without a new monolith | J-03, J-06 | CR-001, CR-003, CR-009, PR-012, PR-013 | S2, S6, S7 | external sample extension + permission negative tests |

## Requirement stage coverage

| Group | Implementation owner | First gate | Full verification gate |
|---|---|---|---|
| PR-001, PR-002, PR-009 | boards + diagnostics service | S2 | S5 |
| PR-003, PR-004 | survey app + observation service + shared views | S3 | S4 |
| PR-005…PR-007 | session/storage/export services | S3 | S5/S8 |
| PR-008 | target service | S6 | S8 |
| PR-010 | update/recovery service | S2 prototype | S8 |
| PR-011 | strings/input/view contracts | S2 | S8 |
| PR-012 | Action API + companion | S3 contract | S6/S8 |
| PR-013 | safety/regulatory/runtime | S2 invariants | S7/S8 |
| PR-014 | board/drivers/apps | S1 scope | S5 |
| PR-015 | capture service + Wi-Fi driver + TFT evidence | S2 screenshot contract/S4 packet capture | S5/S8 |
| PR-016 | feedback service + board safe outputs | S2 idle invariant | S5/S8 |
| PR-017 | connectivity/secrets service | S2 boundary | S6/S8 |
| PR-018 | storage maintenance + recovery | S3 atomic contract | S5/S8 |
| PR-019 | offline enrichment service | S6 | S8 |
| NFR-001…NFR-006 | kernel/runtime/services | S2 | S4/S8 |
| NFR-007…NFR-009 | parsers/storage/schema | S3 | S8 |
| NFR-010 | UI/input/strings | S2 | S8 |

## Catalog and control evidence

| Scope | Requirements | First user-facing gate | Completeness |
|---|---|---|---|
| CAP-001…CAP-008 | PR-001/002/009…011/014, NFR-001/002/004/010 | DEMO-S2 | S5/S8 |
| CAP-009…CAP-017 | PR-003/004/014, NFR-004…006 | DEMO-S3 | S4/S8 |
| CAP-018…CAP-022 | PR-008, NFR-008 | DEMO-S6 | S6/S8 |
| CAP-023…CAP-031 | PR-005…007/009/014, NFR-007…009 | DEMO-S3 | S5/S8 |
| CAP-032…CAP-037 | PR-013/014, NFR-002/006/008 | DEMO-S7 | S7/S8 |
| CAP-038…CAP-041 | PR-002/010/012/013, NFR-006 | DEMO-S6 | S7/S8 |
| CAP-042…CAP-047 | PR-005/007…012/015…019, NFR-005…010 | DEMO-S2/S4 | S5/S8 |

UX-01…UX-07 close the S2 visual/interaction gate; UX-08 repeats in every
`DEMO-S2…DEMO-S8`. The complete evidence and retention protocol is defined by
[STAGE_DEMO.md](STAGE_DEMO.md).

## Research to requirements

| Source | Derived conclusion | Normative continuation |
|---|---|---|
| Competitive CR-001/002/010 | shared Actions, data as product, scenario UX | PR-003…PR-008, PR-012 |
| Competitive CR-004/009 | detected hardware and resource leases | PR-001, PR-002, PR-009, NFR-006 |
| Competitive CR-005/007/008 | portability, offline companion, safe updates | PR-007, PR-010, PR-012 |
| Vision safety principles | passive by default, visible bounded TX | PR-013, NFR-002, NFR-006 |
| [Capability catalog](CAPABILITY_CATALOG.md) + [product review](CAPABILITY_REVIEW.md) + [UX/UI baseline](UX_UI_BASELINE.md) + [Stage Demo](STAGE_DEMO.md) | complete scope is agreed in S1 as 47 capabilities; UX-01/02 bind IA/states, visual system in S2, feature-complete in S7, release-complete in S8 | `CAP-001…047`, `PR-001…019`, `UX-01…08`, `DEMO-S2…S8`; product/UX/test control points for every PR/NFR |
| [Hardware envelope](HARDWARE_ENVELOPE.md) + [HIL probe](HIL_PROBE.md) | hardware is main board, detachable RF shield, and explicit external assemblies; capabilities carry state/evidence; contested GPIO is never output-probed ambiguously | refines PR-001/003/009/014; `E-HW-DESIGN-001`, tool build `E-BUILD-002`, physical HIL `HW-T01…HW-T11`; gates S1/S2/S4/S5 |
| [Reference workflows](REFERENCE_WORKFLOWS.md) | core paths have explicit happy/error/cancel behavior and acceptance IDs `WF-01-A1…WF-05-A5` | covers J-01…J-06 and PR-001…PR-009/012…014; test ownership spans S2/S3/S6/S7/S8 |
| [Resource budget ledger](RESOURCE_BUDGETS.md) | no-PSRAM envelope, build/runtime measurements, provisional limits, and explicit unknowns are separated | refines NFR-001…006 and constrains S2/S3 targets; `E-BUDGET-001` |
| [Risk register](RISK_REGISTER.md) | hardware, integrity, safety, dependency, privacy, and scope risks have controls and closure owners | cross-cuts PR-001…PR-019/NFR-001…010; reviewed at every gate |
| Clean 1.x measurement target | independent pinned build implements BoardProfile, HardwareInventory→AppCatalog projection, unified display/input, buzzer-safe boot output, storage/runtime contracts, guarded SD identification/metadata/FAT persistence, throughput, reset instrumentation, shared recovery workspace, and an interactive exact-CID real passive Wi-Fi→FIFO→persistent SessionStore→cold-boot Library/export path with fail-closed ProductStore/ProductSurvey admission, abort cleanup, bounded Survey/Observation model, Session codec/store, and NDJSON evidence without legacy sources | `E-BUILD-003…047`, `E-HIL-006…054`; implementation evidence for PR-002 and slices of PR-003…007/009/012/NFR-002/003/005…010 plus lower bounds for PR-001/014, NFR-001/010, RB-02…06 |
| GPIO2 buzzer regression | upstream issue #117 and 0.x commit `04fd290` establish active-HIGH control and the boot LOW fix; 1.x expresses it as a dedicated safe-output invariant before console/display | `E-BUZZER-001`, `E-BUILD-028`, `E-HIL-031`; reduces R-004 and HW-U08; audible/electrical HW-T09 remains open |
| [UI automation contract](UI_AUTOMATION.md) | physical and diagnostic input share normalized Actions; actual TFT GRAM becomes reproducible PNG/state evidence without routine operator traversal | `UI-HIL-A1…A7`, `E-HIL-008`; S2 owner for PR-002/011/012 and NFR-001/002/003/010 |
| [Automated pre-release HIL](PRE_RELEASE_HIL.md) | the generic host runner and enrolled product runner flash an exact candidate, bind full app identity, exercise public Actions/diagnostic queries, capture real TFT, and emit hash-indexed evidence; the product lane additionally performs two boots, bounded passive scan/commit, recovery/export, and final lease checks without a resident service; GitHub OIDC/Sigstore promotion still re-verifies attested bytes without rebuilding | `E-AUTO-001…012`, `E-HIL-041…054`, ADR-005; retained checkers bind keypad, isolated boot, and real product Survey states; GitHub integration of the product lane, destructive lane, external-camera subset, and stable publish remain open |
| [Storage atomicity HIL](STORAGE_HIL.md) | fixed dual heads publish only after sync; an exact-fingerprint guard prevents implicit use of unknown media; guarded FAT commit/remount/reopen, real-source queue/batching, current-boot Library admission/export, six-boundary software-reset recovery, exact-CID write-blocked boot recovery, and interactive product commit/abort are physical | `E-STORAGE-001…005/019…023`, `E-SURVEY-003`, `E-LIBRARY-002/003`, `E-HIL-033…040/053/054`, `ST-HIL-A01…A10`; real Wi-Fi batching passes RB-06 and product Survey commits 2→3 then read-only recovers 3/15; power-cut and LittleFS parity remain S5/S8 |
| AppRuntime/ResourceBroker lease HIL | disabled apps acquire nothing; enabled launch acquires all requested resources atomically; Back releases ownership within the UI budget | `E-RUNTIME-001`, `E-BUILD-009`, `E-HIL-012`; first implementation evidence for ADR-002, PR-002/009, and NFR-003/006; physical bus arbitration remains S5/S7 evidence |
| Passive Wi-Fi Survey ingress | passive-only plans reject active/directed operation; the explicit board adapter disables NVS/credentials, owns/cleans its event loop, and calls no connect/config/raw-TX API; under lease 15 the product path normalizes records into FIFO 64, commits one authorized Session, and passes the reboot-validated Session to Library/export | `E-SURVEY-001…003`, `E-BUILD-010/034/036/037/046/047`, `E-HIL-013/037/039/040/053/054`, WF-02-A1/A5; product run accepts/forwards 15/15 with zero software TX calls or event errors; instrumented physical no-TX and endurance remain open |
| Product Survey workflow | simulated capability remains explicit/RF-free when unenrolled; after exact-card boot admission AppCatalog selects real/persistent provenance and lease 15. Explicit Start validates bounded cached space/root/CID, passive scan drains FIFO 64, Stop publishes/reopens exactly the next product generation, and reboot/export confirm it; Back from Running aborts without commit, while every failure preserves prior Library and cleans mount/backend | `E-SURVEY-004…006`, `E-STORAGE-023`, `E-LIBRARY-003`, `E-BUILD-011/040…042/046/047`, `E-HIL-014/046…048/053/054`, WF-02-A1/A2/A4/A5; interactive real worker and automated board lane are implemented for one card, with power-cut/dense RF/endurance still open |
| Session codec and offline reopen | a stopped bounded Session becomes canonical CBOR manifest/framed records; bounded SessionStore publishes/rejects/falls back atomically, survives host process death, runs the same fallback on board RAM, reopens without radio, and exports deterministic JSON | `E-STORAGE-003…005`, `E-BUILD-012/013`, `E-HIL-015/016`, WF-02-A4/WF-03-A1/A3; first implementation evidence for PR-005/006 and NFR-007…009; persistent target reset/power-cut remain open |
| Offline/persistent Library | a bounded controller admits only stopped/valid Sessions and exposes List/Detail with generation, integrity, simulated/persistent, and RF provenance; `SessionCatalog` staged-recovers the latest valid generation from one validated root, including corrupt-new fallback; exact-CID cold boot now replaces the simulated fixture and Back releases its Storage+UI lease | `E-LIBRARY-001…003`, `E-BUILD-014/037/040/046`, `E-HIL-017/040/046/053`, WF-03-A1/A3; implementation evidence for PR-006 and NFR-002/003/008/010; generic discovery semantics and multi-root policy remain open |
| Explicit Library export | Detail→Export Ready gates a bounded deterministic JSON artifact carrying Session summary and provenance; the physical recovered Session exports as `persistent=true`, `simulated=false`; command outside that state returns `not_requested` | `E-EXPORT-001`, `E-BUILD-015/037`, `E-HIL-018/040`; implementation evidence for PR-007/012 and NFR-002/003/007…010; WF-03-A2 full IDs/units/timestamps plus file/companion delivery remain open |
| Read-only media discovery | a typed adapter record refuses presence claims from non-authoritative card detect and requires RO mount/filesystem/fingerprint/capacity before `detected`; board-01 samples GPIO38 but performs no mount/write | `E-STORAGE-006`, `E-BUILD-016`, `E-HIL-019`, ST-HIL-A01 contract slice; implementation evidence for PR-001/005/009 and NFR-006/007; polarity, media identity, and filesystem remain open |
| Mount authorization | any SD mount attempt requires explicit target selection, proven RO-only driver behavior, format disabled, and exclusive Storage+RadioSpi ownership; stock SDFS fails closed before execution | `E-STORAGE-007`, `E-BUILD-017`, `E-HIL-020`, ST-HIL-A02 contract slice; implementation evidence for PR-005/009 and NFR-002/006/007; dedicated RO protocol and physical media remain open |
| SD identification-only plan and parser | a fixed bounded command plan reads OCR/CID/CSD initialization metadata and explicitly rejects write/program/erase/lock/general commands; the parser validates responses, CRC16, identity structure, and capacity | `E-STORAGE-008/009`, `E-BUILD-018/019`, `E-HIL-021/022`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-005…007; physical SPI remains open |
| Fake SD identification transport | a bounded state machine executes the identification plan against an exact command/argument fake, stops after 100 init attempts, rejects every injected exchange failure, and refuses physical transports before calls | `E-STORAGE-010`, `E-BUILD-020`, `E-HIL-023`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-002/005…007; resource-owned physical adapter remains open |
| SD SPI wire codec | allocation-free framing emits known CRC7 command packets and bounded parsers accept only valid R1/R3/R7 and CRC16-protected 16-byte identity data | `E-STORAGE-011`, `E-BUILD-021`, `E-HIL-024`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-005…007; chip-select, clocks, bus ownership, and physical card remain open |
| Physical SD identity | exact confirmation plus Storage+RadioSpi ownership permits one 400 kHz identification-only adapter; three board runs return stable CID/CSD/capacity and complete CS/CE/resource cleanup | `E-STORAGE-012`, `E-BUILD-022`, `E-HIL-025`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-002/005…007; block/filesystem reads, instrumented RF silence, radio recovery, and persistence remain open |
| Physical SD partition map | one separately authorized CMD17 reads only high-capacity LBA0; bounded CRC16/CRC32C and MBR geometry checks retain no raw sector | `E-STORAGE-013`, `E-BUILD-023`, `E-HIL-026`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-002/005…007; partition-boot, filesystem traversal, instrumented RF silence, and persistence remain open at this evidence point |
| Physical FAT32 boot geometry | a second permit derives the only allowed LBA from valid MBR metadata; one block confirms FAT32 signature, bounds, layout, and sanitized volume metadata without mounting | `E-STORAGE-014`, `E-BUILD-024`, `E-HIL-027`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-002/005…009; directory names/data, allocation traversal, radio recovery, and persistence remain open |
| Metadata-only FAT32 root directory | exact MBR/boot geometry derives the only allowed root LBA; approved `counts_hash_only` parsing emits entry classes/CRC32C, never names, and zeroes the raw buffer | `E-STORAGE-015/016`, `E-BUILD-025/026`, `E-HIL-028/029`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/006/009 and NFR-002/005…009; two-sector end marker completes this card-state root inventory while file/FAT chains, free space, and persistence remain open |
| FAT32 FSInfo technical metadata | the boot-declared in-reserved sector is the only permitted LBA; signatures, free/next hints, cluster bounds, and CRC32C are validated before the raw buffer is zeroed | `E-STORAGE-017`, `E-BUILD-027`, `E-HIL-030`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-002/005…009; hints are not a FAT scan, and VFS/persistence remain open |
| FAT32 reserved/root cross-check | the exact first FAT LBA derived from MBR/boot geometry permits one sector; the parser interprets FAT[0] media, FAT[1] health flags, and FAT[2] root allocation only, then bounded-cross-checks FSInfo and zeroes the buffer without chain traversal | `E-STORAGE-018`, `E-BUILD-029`, `E-HIL-032`, ST-HIL-A01/A02 contract slice; implementation evidence for PR-001/005/009 and NFR-002/005…009; full allocation recount, VFS/persistence, and instrumented RF silence remain open |
| Guarded physical FAT SessionStore | exact CID plus explicit disposable selection and a new bounded namespace authorize the historical SDFS path with format disabled; common `SessionStore` commits two generations, unmounts/remounts, and reopens generation 2 read-only; retry refuses the existing namespace with zero logical writes | `E-STORAGE-019`, `E-BUILD-030`, `E-HIL-033`, ST-HIL-A02/A03/A05/A06 slices; implementation evidence for PR-005/006/009 and NFR-002/005…009; reset was subsequently measured by E-HIL-035, while power-cut, product workflow, and LittleFS parity remain open |
| Guarded SD SessionStore throughput | the production-candidate ESP-IDF SDSPI path at actual 4 MHz commits through direct FatFs calls with exact `FRESULT` and real unmount/remount recovery; a fixed FIFO/policy requires 2 KiB/5 s/capacity/Stop/safe-shutdown and now accepts real passive Wi-Fi | `E-STORAGE-020/022`, `E-SURVEY-003`, `E-BUILD-031/035/036`, `E-HIL-034/037…039`, ST-HIL-A02/A03/A05/A06 slices; synthetic batching delivers 9,068 B/s and the real path 6,921 B/s vs required 2,184 B/s; power-cut, product workflow, and LittleFS parity remain open |
| Guarded software-reset recovery | a host-tested wrapper observes the six unchanged commit boundaries; exact-CID arm uses a unique bounded namespace and `esp_restart`, while exact-CID recovery reopens existing scratch read-only and requires software-reset reason, an allowed generation, unchanged prior hashes, zero writes/syncs, and complete cleanup; the runner checkpoints boundaries and only retries the exact fail-closed `missing_media` readiness signature | `E-STORAGE-021`, `E-BUILD-032`, `E-HIL-035`, ST-HIL-A02/A03/A04/A06 slices; six physical software-reset boundaries recover 1/1/1/1/1/2 on one card/board; physical power-cut, endurance, source-rate, product workflow, and LittleFS parity remain open |

## ADR coverage

| ADR | Requirements / risks | Implementation owner | Verification gates |
|---|---|---|---|
| [ADR-001](adr/ADR-001-toolchain.md) | PR-001/010/014, NFR-001/006; R-011/012/013 | platform/build | S2 clean target; S8 reproducibility/recovery |
| [ADR-002](adr/ADR-002-resource-policy.md) | PR-001/002/009/013/014, NFR-002/006; R-003/004/005/008/009 | kernel/boards/drivers | S2 invariants; S5/S7 physical HIL |
| [ADR-003](adr/ADR-003-storage-schema.md) | PR-003/005…008/012, NFR-007…009; R-006/010/014/016 | storage/session/library | S3 slice; S5/S8 fault/endurance |
| [ADR-004](adr/ADR-004-action-boundary.md) | PR-002/009/012/013, NFR-002/003/006; R-008/009/014/016 | SDK/kernel/services | S2 dispatcher; S6/S7/S8 transports/safety |
| [ADR-005](adr/ADR-005-pre-release-hil.md) | PR-002/010/011/012/014/015, NFR-001…003/005/007/010; R-004/006/011/012/014/016 | platform/verification/firmware | S1/S2 device-smoke; S8 signed immutable release gate |

All five decisions are accepted design constraints; none marks a requirement
implemented or verified.
