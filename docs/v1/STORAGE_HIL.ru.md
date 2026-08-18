# ESP32-Leshy 1.x — HIL атомарности storage

*Читать на: [English](STORAGE_HIL.md) · **Русский***

Статус документа: **обязательный safety/verification protocol; host logic, real-file
fixture, guarded physical FAT commit/remount, per-generation и batched 32-sample SD
throughput, real-source queue/persistence и host/static six-boundary software-reset
matrix реализованы; exact product UI/reboot/export и missing-source
real-TFT/zero-lease path плюс normal/remount и six-boundary software-reset
LittleFS parity проверены; управляемый physical power-cut остаётся отдельной
fixture lane `DEMO-S4`**.

Протокол проверяет ADR-003 без риска для неизвестной SD card или сохранённых данных
во flash. Обычная diagnostic image никогда не форматирует и не записывает storage
при boot или capability detection.

## Реализованный логический контракт

Allocation-free `storage/AtomicHead` задаёт 24-байтную big-endian head record:

| Поле | Байт | Правило |
|---|---:|---|
| magic | 4 | `LSHH` |
| schema | 2 | version 1; неподдерживаемая версия fail closed |
| flags | 2 | zero в v1 |
| generation | 4 | serial-number comparison с rollover |
| manifest length | 4 | совпадает с referenced manifest |
| manifest CRC32C | 4 | совпадает с manifest evidence |
| head CRC32C | 4 | покрывает предыдущие 20 байт |

Recovery проверяет оба head и их manifests, затем выбирает наибольшее валидное
generation. Одинаковое generation с разной manifest identity и разница ровно в
половину диапазона дают `conflict`, а не угаданного победителя. Отсутствие валидного
head даёт `none`; оба результата требуют явного recovery UI.

Порядок commit фиксирован: write payloads → sync payloads → write manifest → sync
manifest → write older head slot → sync head. Только последний успешный sync публикует
новое generation.

Host tests внедряют отказ на каждой границе. Все шесть incomplete commits выбирают
предыдущее generation; complete path выбирает новое. Также проверяются bounds,
стандартный CRC32C vector, каждое one-bit повреждение head, missing/mismatched
manifest, split-brain и rollover generation.

`storage/SessionCodec` теперь задаёт bounded payload contract за этим head. Schema 1
использует canonical CBOR manifest и canonical CBOR observations, framed big-endian
length и CRC32C. Footer segment `LSHS` на 24 bytes аутентифицирует schema, flags,
record count, body length, body/footer CRC32C. Fixed limits: manifest 256 bytes,
record 128 bytes, segment 12 288 bytes и 64 observations. Decoder отклоняет future
schemas, non-canonical/malformed/trailing data, invalid timeline, bounds violation и
checksum mismatch. Host tests изменяют каждый bit manifest, обрывают segment на
каждом byte и изменяют один bit в каждом segment byte. Exact golden Session
открывается и выдаёт deterministic bounded JSON.

Board-01 `0.10.0-session-codec-measure` повторяет encode → head selection → reopen →
JSON после explicit Stop и сообщает `storage_written=false` и
`radio_touched=false`. Это подтверждает тот же allocation-free codec на target, но
не является evidence filesystem, reset или power-cut.

Guarded host filesystem fixture затем выполняет commit в actual files внутри
isolated каталога `mkdtemp`. Она требует тот же exact-fingerprint,
explicit-disposable, bounded permit `StorageGuard`; sync и files, и parent directory;
открывает выбранное generation; проверяет prior bytes и удаляет fixture. Шесть
injected write/sync failures восстанавливают generation 1, complete commit —
generation 2. Это real file/`fsync` evidence, но failures моделируются return/crash
images, а не ESP reset или power cut.

Общий `SessionStore` теперь владеет layout и orchestration с fixed buffers: automatic
generation/older-slot selection, uint32 rollover, commit, полной manifest/segment
validation, reopen и corrupt-new fallback. Он отличает действительно empty store от
corrupt/ambiguous heads; только empty может инициализироваться, ambiguity ничего не
записывает. POSIX fixture делает recovery через тот же contract.

Вторая matrix убивает writer process через `SIGKILL` после каждой реальной operation.
Recovery в surviving process выбирает generation 1 до публикации head и generation 2
после полного write head. Последнее валидно даже до `fsync` head: payload и manifest
уже durable, а полный head может пережить crash. Все шесть результатов открывают три
observations и сохраняют prior bytes.

Board-01 `0.11.0-session-store-measure` запускает тот же common `SessionStore` через
bounded, явно non-persistent two-generation RAM adapter. Он автоматически публикует
generation 1/A, затем 2/B, открывает generation 2, меняет один byte её segment,
классифицирует `invalid_payload` и делает fallback на generation 1. Обе открывают три
observations. Adapter моделирует шесть file и шесть directory sync calls, сообщая
`physical_storage_written=false` и `radio_touched=false`. Это закрывает evidence target
orchestration/fallback, но не persistence.

Board-01 `0.12.0-library-offline-measure` добавляет bounded Library List/Detail
controller над этой reopened metadata. Первый image отклонён: stack canary обнаружил
полную временную `SurveySession` в `reopenSession`; теперь decode сбрасывает и заполняет
caller-owned bounded storage напрямую. Исправленный image показывает generation,
integrity и явный volatile/RF-off provenance, удерживая только UI lease.

Board-01 `0.13.0-library-export-measure` добавляет explicit action
Detail→Export Ready. Только этот state выдаёт bounded deterministic serial artifact
`leshy.library.export.v1`; Home возвращает `not_requested`. Artifact сохраняет
generation, integrity, simulated/persistent state, storage backend, transport, RF
state и Session summary. Это transport evidence, не persisted file.

Board-01 `0.14.0-storage-discovery-measure` вводит typed boundary
`ReadOnlyMediaAdapter`. Board implementation читает GPIO38 без перенастройки и
получает level 0, но по HW-U06 этот level non-authoritative. Поэтому status остаётся
`unknown`: claims mount, filesystem, fingerprint, capacity и free space отсутствуют,
writes disabled, `StorageGuard` обязателен. Host validation запрещает claims
present/absent по non-authoritative detect и требует полную read-only metadata до
перехода result в `detected`.

Board-01 `0.15.0-mount-policy-measure` добавляет gate до driver execution. Mount
attempt требует explicit selection, proven read-only driver, format disabled и
exclusive ownership Storage+RadioSpi. У установленного Arduino `SDFS::begin` нет
read-only option, а class предоставляет raw writes, поэтому board сообщает actual
`explicit_target_required` и hypothetical `driver_not_read_only`. SPI/mount operation
не выполняется.

Board-01 `0.16.0-sd-ro-protocol-measure` добавляет dedicated identification-only plan
вне SDFS: CMD0, CMD8, CMD55/ACMD41, CMD58, CMD10 и CMD9 с bounded init. Host tests
явно отклоняют write/program/erase/lock/general commands и любое plan drift. Board
сообщает valid plan при execution disabled; SD commands не выполняются.

Board-01 `0.17.0-sd-parser-measure` добавляет bounded response parser. Он проверяет
R1 state, CMD8 echo, initialization count, OCR, CID/CSD CRC16, identity sanity, CSD
v2 structure и capacity. Host tests отклоняют каждую one-bit mutation в 16-byte CID
и CSD. Board разбирает synthetic transcript, сообщая zero commands и отсутствие
physical SPI, write или radio activity.

Board-01 `0.18.0-sd-transport-measure` добавляет executable state machine над strict
deterministic fake. Golden case завершает eleven exchanges за three init attempts.
Host injection отклоняет failure на каждом exchange, останавливает never-ready card
после 100 attempts/202 exchanges и отказывает physical transports до первого call.
Physical adapter в этом slice не существует и не запускается.

Board-01 `0.19.0-sd-wire-measure` добавляет allocation-free wire framing без bus
adapter. CMD0/CMD8 совпадают с known CRC7 packets; R1 и data-token polling bounded,
R3/R7 trailing values exact, а wire CRC16 для CID/CSD обязателен. Host fixtures
отклоняют invalid arguments, mutating commands, timeout, unexpected token,
truncation и checksum mismatch. Board сообщает zero commands и execution disabled.

Board-01 `0.20.0-sd-physical-id-measure` добавляет guarded physical adapter 400 kHz.
Exact confirmation command получает Storage+RadioSpi, держит NRF CE LOW и остальные
known chip selects HIGH, требует GPIO21 HIGH, затем выполняет только identification.
Три runs возвращают одинаковые CID/CSD и capacity 62 534 975 488 B; cold/warm init
занимает 8/2/2 attempts. Каждый run завершает cleanup и освобождает mask 12→0.
Discovery остаётся unmounted/unknown; data block, filesystem, write, format и radio
commands не выполняются.

Board-01 `0.21.0-sd-sector0-measure` добавляет один отдельно guarded CMD17 после
valid physical identity. Authorization разрешает только LBA0/count 1 для selected
high-capacity read-only target при ownership Storage+RadioSpi без conflict. Physical
run читает ровно один block, проверяет wire CRC16 `5391` и сообщает valid MBR с
partition type `0x0C`, LBA 2 048, length 122 136 512 sectors и LBA0 CRC32C
`1784529910`. Raw block не сохраняется, cleanup снова возвращает 12→0.

Board-01 `0.22.0-sd-boot-inspect-measure` добавляет ещё один metadata permit, LBA
которого обязан совпадать с first partition LBA из valid MBR. Ровно два total blocks
(LBA0 и boot) подтверждают FAT32 geometry: 512 B/sector, 64 sectors/cluster, 14 906
sectors/FAT, root cluster 2 и 122 136 512 total sectors. Boot CRC32C/wire CRC16 равны
`3945425518`/`9849`. Raw sectors не сохраняются; mount/filesystem APIs,
directory/file reads, write, format и radio TX остаются disabled. Следующий sector
содержит directory entries и поэтому пересекает границу между geometry и возможным
user-data evidence.

Для этой границы operator одобрил `counts_hash_only`. Board-01
`0.23.0-sd-root-metadata-measure` выводит root LBA 32 768 из validated FAT32 geometry
и разрешает ровно один block. First-sector report содержит только CRC32C и aggregate
classes slots: 16 active, включая 8 LFN, 2 directory, 5 file и 1 volume-label.
Host privacy fixtures помещают identifiable short/LFN names в raw bytes и доказывают,
что formatted evidence их не содержит. Board сразу после aggregation обнуляет
reused directory buffer 512 B.

Board-01 `0.24.0-sd-root-cluster-measure` расширяет ту же policy на sequential
sectors, bounded declared cluster из 64 sectors. End marker найден во втором sector,
после чего scan останавливается: 29 examined slots, 26 active, 2 deleted, 12 LFN,
6 directory, 7 file, 1 volume-label и zero invalid. Aggregate CRC32C равен
`1849301523`. Четыре total blocks включают LBA0, boot и два directory sectors;
FAT chain не затрагивается. Каждый raw directory buffer обнуляется, names и file data
не retained.

Board-01 `0.25.0-sd-fsinfo-measure` затем читает только FAT32 FSInfo sector,
declared по reserved-sector offset 1 (absolute LBA 2 049). Lead/structure/trailing
signatures и bounds валидны. Technical hints: 1 907 095 free clusters из 1 907 903
data clusters и next-free cluster 888; CRC32C `1661032487`, wire CRC16 `49708`.
Это hints, не full FAT allocation proof. Buffer обнуляется; names, directory entries,
FAT entries и file data не читаются. Перенос mutually exclusive probes в один shared
workspace уменьшает static RAM с 95 620 B в 0.24 до 90 004 B без изменения safety
boundary.

Семантика reserved entries следует
[Microsoft FAT32 Specification 1.03 (`fatgen103.doc`)](https://www.microsoft.com/en-au/download/details.aspx?id=53426).
Board-01 `0.27.0-sd-fat-reserved-measure` добавляет ровно один first-FAT sector
к fresh LBA0/boot/FSInfo evidence и разбирает только FAT[0], FAT[1], FAT[2]. First
FAT LBA 2 956 выведен из reserved offset 908. FAT[0] `0x0FFFFFF8` совпадает с boot
media `0xF8`; FAT[1] `0x0FFFFFFF` означает clean shutdown/no hard error; FAT[2]
`0x0FFFFFFF` завершает root cluster 2. FSInfo free 1 907 095/1 907 903 и next-free
888 совместимы с этим минимальным allocation evidence. Это не full recount: parser
не follow chain после FAT[2], даже если entry указывает на следующий cluster. FSInfo
и FAT buffers обнуляются; names, directory/file data, VFS, mount и writes отсутствуют.

`StorageGuard` теперь реализует authorization boundary physical fixture. Bounded
permit выдаётся только после exact fingerprint match, explicit disposable selection,
безопасного нового run ID/namespace, consistent capacity, non-zero byte limit и
free-space reserve. Negative host tests покрывают все причины отказа.

Board-01 `0.28.0-sd-session-store-measure` — первый guarded writable physical slice.
Explicit command содержит exact CID и fresh run ID, получает Storage+RadioSpi,
mount SDFS с disabled format и ограничивает общий `SessionStore` каталогом
`/leshy-hil/s1-session-store-20260816-d`. Generations 1/A и 2/B commit с шестью file
и шестью directory sync; настоящий unmount/remount с последующим read-only reopen
возвращает generation 2 и три synthetic observations. Записано 440 logical bytes
внутри permit 65 536 B. Повтор той же команды отказывает существующий scratch path и
пишет zero bytes. Existing paths не удаляются, user names/file payload не читаются,
radio TX command не выполняется.

FatFs `f_sync` за Arduino `File::flush` — durability boundary adapter для files и
directory entries. Успешный normal remount не является evidence reset на каждой
commit boundary или потери питания. До успешной Session write run также выявил и
исправил oversized recovery temporary на loop stack и неверную проверку nested directory.

## Безопасность physical fixture

Physical run разрешён только на явно выбранной цели:

- disposable SD card, capacity/CID fingerprint которой сохранён для этого run; или
- dedicated disposable LittleFS image/partition для HIL, не текущий раздел данных
  product/legacy.

Принятая реализация 0.69/0.70 использует только pinned inactive OTA1 partition `app1` по
`0x410000` размером 4 MiB. Firmware доказывает, что running и boot partitions находятся
в другом месте, product `spiffs` не пересекается с target, и хеширует все 4 MiB до
format. Host требует два одинаковых чтения, передаёт exact hash firmware, хранит
private backup до совпадения полного restore readback и partition table и удаляет
private copy только после verification. Поэтому passing public bundle содержит только
hashes/logs, но не OTA contents.

Сначала выполняется read-only discovery. Target с неожиданным fingerprint,
существующим scratch namespace, mount error, недостатком места или filesystem
inconsistency отклоняется. Все записи bounded каталогом `/leshy-hil/<run-id>/`;
format, изменение partition table и запись вне namespace запрещены. Cleanup идёт
только после сохранения evidence hashes; здесь cleanup означает unmount и recovery
resources/GPIO, а не удаление evidence namespace.

Logical reset injection (`esp_restart`) проверяет reopen/recovery, но не заменяет
реальный power cut. Для закрытия PR-005/RB-06 нужен управляемый источник или power
switch, независимо обрывающий питание на каждой persisted boundary.

Exact 0.58 S3 progress (`E-AUTO-023`/`E-HIL-083`) переиспользует тот же production
path: 10/10 passive observations остаются live через List→Detail→Back, Back
подтверждён за 102,636 ms, Stop продвигает generation 65→66, а cold read-only reopen
экспортирует ту же persistent/non-simulated generation при неактивных radios и final
lease zero. Это закрыло gap normal product navigation UI, но source всё ещё был
one-shot operation в UI loop.

Exact worker progress 0.59 (`E-BUILD-061`/`E-AUTO-024`/`E-HIL-084`) переносит
identity, mount, source и commit work за persistent Core-0 task с bounded очередями
events/observations (8/64). Callbacks Start/Stop возвращаются за 13/10 us; активный
source продвигается с 14 observations/одного scan до 27/двух scans при открытом
Detail, достигает high-water 10/64 при zero drops, затем останавливается до
единственного commit 66→67. Cold read-only recovery/export возвращает exact
generation 67/27 с zero heap drift, zero writes и final lease zero. Runner сохраняет
собственный exact runtime-emitted source hash и fail-closed terminal/cleanup evidence.
Это принимает только нормальный asynchronous worker path; ни один результат не
заменяет controlled physical cuts или LittleFS parity.

Саморевью worker обнаружило, что его control state становился `Idle` после enqueue
terminal event, а не после обработки события UI. Version 0.60 сохраняет worker
non-idle до завершения cancellation cleanup или single commit/cleanup на Core 1 и
добавляет static rejection rule для worker-side `Idle`. Exact E-HIL-085 затем
продвигает generation 67→68 с 25/25 forwarded, двумя live scan cycles, zero
drops/heap drift, callbacks Start/Stop 12/8 us, read-only recovery/export и final
lease zero. Этот normal-path regression подтверждает fix, но не заявляет deliberately
timed repeated-Start injection или power-cut boundary.

Exact evidence active cancel 0.62 (`E-BUILD-063`/`E-AUTO-026`/`E-HIL-086`) ждёт,
пока physical passive scanner сообщит active blocking scan, затем отправляет Back.
Callback 9 us фиксирует, что cancellation запрошен во время этого scan; terminal
cleanup закрывает source/backend и освобождает lease 15→0 до cold read-only reboot.
Generation/observations остаются ровно 68/25 при zero physical/logical SD writes и
zero heap drift. Первая попытка 0.61 сохранена failed: post-cancel boot потерял
one-shot read PCF8574. 0.62 добавляет bounded telemetry 1…8 попыток input probe, оба
regression boot проходят. На этой точке evidence physical power-cut и LittleFS parity
оставались открыты; 0.69 далее принимает normal/remount parity, а 0.70 —
six-boundary software-reset matrix.

Exact evidence missing-source 0.68 (`E-BUILD-069`/`E-AUTO-032`/`E-HIL-092`/
`E-SURVEY-007`) взводит one-shot diagnostic failure только из idle Home, затем
потребляет её на реальной Product Start source boundary. Exact-CID identity и bounded
store permit validation завершаются первыми, но `scanner.begin` и SessionStore open
не запускаются. Localized русский TFT 240×320 остаётся на `СКАНЕР / НЕДОСТУПЕН`
после полного cleanup и lease 15→0, явно сообщает об отсутствии source/Session и
сохранности prior Library, оставляя только Left/Home. Select не вызывает hidden
retry. Cold read-only recovery до и после остаётся generation 68/25 с zero physical
writes; source start/store open/bytes written/observations равны false/false/0/0.
Это закрывает критерий 9 S3 без подмены physical power-cut или LittleFS parity.

Exact parity LittleFS 0.69 (`E-BUILD-070`/`E-AUTO-033`/`E-HIL-093`/
`E-STORAGE-024`) выполняет неизменный common `SessionStore` через explicit inactive
OTA1 LittleFS adapter. Он завершает 32/32 generations и 96 file плюс 96 covered
directory sync barriers, восстанавливает generation 32 с 64 observations до и после
read-only remount и измеряет min/p50/p95/p99/max commit time как
65 748/155 467/847 921/978 403/978 403 us. Encoded throughput равен 18 586 B/s при
цели RB-06 2 184 B/s. Product `spiffs`, SD, NVS и radio не затрагиваются; lease 4→0,
cleanup complete. Host восстанавливает exact SHA-256 OTA1 `ade2400f…d661` и
неизменный SHA-256 partition table `339bda68…5ba2`, затем cold read-only recovery
возвращает прежнюю product generation 68/25 с zero writes. Это принимает
normal/throughput ST-HIL-A07, но не LittleFS reset-boundary matrix и не physical
power cut.

Exact reset recovery LittleFS 0.70 (`E-BUILD-071`/`E-AUTO-034`/`E-HIL-094`/
`E-STORAGE-025`) связывает каждую попытку с текущим SHA-256 всего inactive OTA1,
exact CID, run ID и одной из шести неизменённых boundaries `SessionStore`. Valid
software-reset RTC continuity token разрешает только read-only reopen с typed
`ReadPermit`; recovery принимает generations 1/1/1/1/1/2, неизменные prior/manifest
CRC и ровно zero bytes written, file syncs и directory syncs. Host сначала доказывает
два одинаковых чтения target, восстанавливает OTA1 ровно одной flash write, затем
повторяет только независимую read-only verification до сравнения partition table и
cold reopen product generation 68/25. Все шесть попыток закрывают resources,
оставляют lease zero и сохраняют heap 266 616/202 200/182 148 B. Это принимает
software-reset matrix ST-HIL-A07. Управляемый physical power-cut намеренно остаётся
отдельным evidence `DEMO-S4` и не подменяется `esp_restart`.

## Реализованный и физически проверенный software-reset harness

Version `0.30.0-sd-session-reset-measure` добавляет diagnostic wrapper
`SessionStoreBoundaryIo` вокруг неизменённого common commit path. Он считает
только успешно завершённую logical operation. Write boundary срабатывает
после успеха underlying `writeFile`; sync boundary — только после успеха
`syncFile` и directory barrier adapter. Host tests останавливаются после
каждой из шести boundaries, восстанавливают allowed generation и сохраняют bytes
generation 1.

| Номер | Boundary | Allowed recovery после software reset |
|---:|---|---|
| 1 | payload write | generation 1 |
| 2 | payload file + directory sync | generation 1 |
| 3 | manifest write | generation 1 |
| 4 | manifest file + directory sync | generation 1 |
| 5 | older-head write | generation 1 или 2; complete unsynced head может выжить |
| 6 | head file + directory sync | generation 2 |

Write-side command требует exact CID, уникальный run ID, новый scratch namespace,
bound 64 KiB и ownership Storage+RadioSpi. Он полностью commits generation 1,
сохраняет sizes и CRC32C manifest/segment, затем вызывает `esp_restart`
сразу после выбранной boundary generation 2:

```text
storage.sd.session-store reset disposable-write <CID32> <run-id> <1..6>
```

После boot отдельная command заново доказывает exact CID и existing namespace,
открывает `SessionStoreIo` read-only, пишет/синхронизирует zero bytes, проверяет
software-reset reason, allowed recovered generation и три observations, сравнивает bytes
prior manifest/segment с deterministic CRC32C, затем unmount и release resources:

```text
storage.sd.session-store recover disposable-read-only <CID32> <run-id> <1..6>
```

`tools/run_1x_sd_reset_matrix.py` последовательно использует шесть уникальных
namespaces, сохраняет checkpoint после каждой completed boundary и отказывается без
`--execute-reset-matrix`. Recovery делает не более трёх попыток с exponential
backoff. Повтор разрешён только для наблюдавшегося fail-closed readiness signature:
fingerprint не совпал, `missing_media`, zero writes/syncs и complete cleanup. Ошибка
integrity, CID, namespace или recovery oracle останавливает run немедленно.

Board-01 с exact SD CID `FE343253440000002000000055019CB7` прошла все шесть
physical boundaries `esp_restart`. Восстановлены generations `1/1/1/1/1/2`; каждый
reopen вернул три observations, сохранил CRC32C 155-byte segment и 41-byte manifest
generation 1, записал/синхронизировал zero bytes, вернул `FR_OK` и освободил resources
12→0. На boundary 4 первая immediate попытка дала transient `missing_media`;
zero-write read-only retry восстановил generation 1, а final read-only audit всех
шести namespaces прошёл. Это закрывает ST-HIL-A04/A06 для одной комбинации
board/card/software-reset, но не physical power-cut или endurance.

Version `0.31.0-sd-session-ram-review` затем удалила redundant physical-recovery
`SurveySession` 4 672 B и переиспользовала
`SessionStoreWorkspace::validationSession`, которым common recovery path уже владеет
и пользуется последовательно. Static RAM снизилась с 99 932 до 95 260 B. Новый
exact-CID boundary-6 run достиг `sync_head`, восстановил required generation 2 с
unchanged prior hashes и zero recovery writes/syncs, завершив cleanup с первой
попытки. Это regression evidence E-BUILD-033/E-HIL-036 для shared workspace, а не
повтор full six-boundary matrix.

Version `0.33.0-sd-session-batch-throughput-measure` добавила fixed FIFO 64
observations и policy публикации: 2 048 encoded B, 5 s maximum latency, capacity,
explicit Stop или safe shutdown. Host tests покрывают FIFO wrap-around, drop/high-water
и scrub counters, все triggers/precedence и overflow-safe расчёт. По измеренным Wi-Fi
p99 546 B/s, safety factor 4 и прежнему commit p99 591 651 µs minimum batch равен
1 293 B; выбранный target 2 048 B выше этого bound.

Physical exact-CID run в новом namespace
`/leshy-hil/s1-batch-throughput-20260816-a` committed 32 поколения по 64 observations
и 4 609 B encoded segment. Все 32 commits и 96+96 barriers завершены, generation 32
с 64 observations открыто до и после remount. Encoded payload service rate 9 068 B/s
против RB-06 required 2 184 B/s: pass с margin 4,15×. Форматирование, deletion,
existing-path overwrite и radio TX отсутствовали; resources вернулись 12→0. Это
закрывает performance части batching design, но synthetic fixture ещё не доказывает
real passive Wi-Fi→queue→SessionStore path.

Version `0.34.0-wifi-passive-persist-measure` затем получила единый atomic lease
EspRf+Storage+RadioSpi и соединила physical passive scanner с этим FIFO/policy и
guarded FAT SessionStore. Exact-CID run сделал четыре scans, принял 29 observations
при FIFO high-water 9/64 и zero drops, после 5 s latency trigger committed generation
1 с segment 1 334 B за 192 729 µs. Recovery до unmount и после real remount/read-only
reopen вернул все 29 observations. Effective encoded payload rate 6 921 B/s проходит
RB-06 в 3,17×; cleanup вернул combined resource mask 14→0. Identifiers не emitted в
evidence, но намеренно retained только внутри нового isolated scratch Session. Это
technical end-to-end path; product Start/Running/Stop, reboot Library и export ещё
не используют его.

Version `0.35.0-persistent-library-admission-measure` перестаёт восстанавливать
simulated RAM Library после успешного path. Новый exact-CID namespace
`/leshy-hil/s3-wifi-library-20260816-a` принял 52 observations из четырёх scans,
FIFO high-water 18/64 и zero drops; size trigger committed generation 1 с segment
2 499 B за 192 867 µs. Recovery после real remount вернул все 52, effective rate
12 957 B/s проходит RB-06 в 5,93×. Проверенная Session copied в caller-owned Library
workspace и получает runtime capability `library.persistent_session`, не объявляя
всю SD generic-available. Actual TFT path Home→List→Detail→Export показывает
READY, `PERSISTENT SESSION | REAL`, generation 1/valid и `PERSISTED YES`; serial
artifact имеет `persistent=true`, `simulated=false`, Wi-Fi 52. Back освобождает
Storage+UI lease 5→0. Это был current-boot admission после explicit command;
version 0.44 ниже закрывает отдельный safe boot mount/catalog/recovery path.

Version 0.40 добавляет product-level authorization поверх доказанного технического
path. Для boot catalog разрешён только exact enrolled fingerprint, existing
`/leshy/sessions/v1`, гарантированно read-only non-writable driver и lease 12.
Initialize/commit требуют explicit selection, writable driver, byte budget и те же
ресурсы; format запрещён. Combined Survey gate требует passive plan и lease 14 и
никогда не делает simulated/RAM fallback. Это host + non-I/O board policy evidence,
не mount или запись на product namespace.

Version 0.44 реализует этот board lifecycle. Один explicit bootstrap на выбранной
test card создал `/leshy/sessions/v1`, committed generation 1 с 17 passive Wi-Fi
observations (895 logical bytes, три file и три directory sync), recovered её и только
после этого enrolled exact CID. Каждый следующий accepted boot использует ESP-IDF
FAT/diskio adapter: status содержит `STA_PROTECT`, write/trim callbacks возвращают
`RES_WRPRT`, format disabled. Boot path держит lease 12, проверяет raw CID/CSD
capacity, открывает только product root, staged latest valid catalog в Library,
unmount и release 12→0. `f_getfree` и filesystem-capacity query намеренно отсутствуют:
реальный full-FAT scan на 64 GB card уже приводил cold boot к зависанию.

Test state управляется явно. `storage.product.unenroll confirm` удаляет только CID
из NVS и не обращается к SD, поэтому generic `device-smoke` v6 сохраняет deterministic
simulated/RAM fixture и десять существующих goldens.
`storage.product.enroll disposable-read-only <CID32>` сохраняет CID в NVS только
после успешного read-only catalog recovery. Exact candidate 0.44 прошёл generic HIL
в un-enrolled state, был re-enrolled с zero SD writes, затем cold-booted в persistent
Library generation 1/17; export valid/non-simulated/RF-off, Back освободил lease 5→0.
Machine-checked retained artifact:
[`board-01-product-boot-0.44.json`](../../tests/hil/evidence/board-01-product-boot-0.44.json).

Version 0.45 закрывает interactive worker boundary на той же enrolled card. Explicit
product Start использует cached FAT/FSInfo free-cluster hint вместо `f_getfree`,
допускает bounded commit 64 KiB плюс reserve 1 MiB, запускает passive Wi-Fi под lease
15 и держит mount только до Stop/abort. Automatic exact-candidate lane принял и
forwarded 15/15 observations без reject/drop, опубликовал generation 2→3, cleanly
unmounted, затем cold boot восстановил ровно 3/15 через write-blocked driver и
экспортировал из persistent Library. Отдельный Back-from-Running probe сохранил
generation 2 без commit и с lease 0. Retained evidence:
[`board-01-product-survey-0.45.json`](../../tests/hil/evidence/board-01-product-survey-0.45.json).

Короткий repeatability probe затем повторил exact local 0.45 product path дважды:
одна verified flash и следующий цикл без flash непрерывно продвинули generation
6→7→8, приняли и передали 44/44 observations без drop, выполнили четыре read-only
cold-boot recovery и сохранили одинаковые heap total/free/min во всех точках. Это
раннее evidence отсутствия накопительного сбоя, но два цикла не заменяют release
endurance ≥45 минут/≥8 циклов
endurance. Retained summary:
[`board-01-product-repeatability-0.45.json`](../../tests/hil/evidence/board-01-product-repeatability-0.45.json).

Этот probe также обнаружил intermittent cold-boot identity failure: enrolled CID
валиден, observed CID равен всем нулям, mount/root/catalog ещё не начинались, permit
сообщает `missing_media`, cleanup complete, ownership возвращён в zero, записей не
было. Промежуточный эксперимент 0.46 повторял весь raw identity + mount path внутри
одного boot. Он завершил два цикла 9→10→11, но следующий post-commit boot остановился
после ROM loader и потерял USB endpoint до полного снятия питания. Поэтому
`E-HIL-058` отклоняет same-boot re-entry.

Сохранённый design 0.46 разрешает retry только для этой точной fail-closed signature.
В одном boot выполняется одна попытка; RTC no-init state хранит максимум два software
restart с задержками 250/500 ms, то есть максимум три attempts. Non-software reset,
unenrolled device, success, любая более широкая ошибка, leaked ownership, incomplete
cleanup или write-blocker hit сбрасывают/запрещают retry. Final recovery evidence
публикует `attempts` и `transient_retries`; product и endurance runners проверяют
`1..3` и `retries = attempts - 1`, а расширенный ready budget разрешают только после
фактического retry.

После полного снятия питания exact candidate 0.46 прошёл three-cycle smoke
endurance runner `E-HIL-059`: generation 12→15, 51/51 observations forwarded, шесть
read-only boots, двенадцать captures, zero drops, invariant heap и final lease 0.
Все шесть boots завершились на attempt 1, поэтому результат проверяет normal path и
bounded orchestrator, но ещё не даёт positive evidence reset retry. Retained summary:
[`board-01-product-endurance-smoke-0.46.json`](../../tests/hil/evidence/board-01-product-endurance-smoke-0.46.json).

Первый restart release 0.48 позже fail-closed завершился на explicit Product Start
после трёх exchanges с пустым CID (`E-HIL-065`). Same-board comparison 32+32
read-only затем измерил 13 valid identifications и maximum failure streak семь на
400 kHz против 24 valid и maximum streak два на 100 kHz (`E-HIL-066`). Каждый
attempt очищал bus, возвращал ownership в zero и не отправлял write command.
Product identification теперь работает на 100 kHz. Explicit Product Start может
повторить максимум восемь полностью cleaned raw-only attempts для exchange/init
failure или parse rejection с пустым CID и по-прежнему не может mount/write до
exact CID. Boot recovery остаётся отдельной reset-separated policy максимум на три
attempts. Exact 0.49 затем прошёл один полный product run и three-cycle regression
35→38 (`E-HIL-067/068`). Retained summary:
[`board-01-product-start-resilience-0.49.json`](../../tests/hil/evidence/board-01-product-start-resilience-0.49.json).

Release gate 0.49 затем завершил шесть exact-candidate cycles, generation 38→44 и
96/96 forwarded observations, но cycle 7 после 5 719,273 s исчерпал отдельный boot
identity budget из трёх attempts (`E-HIL-069`). Terminal recovery record остаётся
fail-closed: empty observed CID, no read-only mount или catalog admission, zero
blocked/physical writes, complete cleanup и ownership zero. Немедленный read-only
probe вернул exact CID в 6/8 attempts, поэтому card и prior generation не потеряны.

Diagnostic comparison 32+32 отклонил увеличение bounded R1 response poll с 16 до 64
byte: extended candidate дал 13 valid identities и четыре response timeouts, а
retained control 16 byte — 15 valid identities и no timeout; у обоих maximum failure
streak четыре и каждый cleanup завершён без writes (`E-HIL-070`). Поэтому candidate
0.50 сохраняет wire policy 100 kHz/16 byte и меняет только narrow reset-separated
boot budget с трёх до восьми attempts. Host tests покрывают attempts 3…7 и exhaustion
на 8; неизменный no-OS watchdog 4 s по-прежнему ограничивает каждый recovery call.
Exact three-cycle regression продвигает 44→47 с 39/39 forwarded, двумя natural
retries, zero drops/heap drift и final lease 0 (`E-HIL-071`). Retained summary:
[`board-01-product-boot-resilience-0.50.json`](../../tests/hil/evidence/board-01-product-boot-resilience-0.50.json).

Следующий release lane 0.50 завершился fail после одного complete cycle
(`E-HIL-072`). Cycle 2 выдал две clean reset-separated retry records, но третий
attempt дошёл до ROM app entry и затем не выдал ни firmware output, ни reset от
software watchdog 4 s. Serial endpoint остался виден, но не отвечал на безопасные
external reset и loader probes. Final cleanup, lease и write state нельзя наблюдать,
поэтому все три сохраняются как unknown, а gate fail closed. Candidate 0.51 сохраняет
software tier и дополнительно подписывает recovery task на panic-enabled ESP-IDF
Task WDT 5 s; его IRAM ISR сохраняет RTC timeout marker без console, filesystem или
shutdown work. После physical power recovery E-HIL-073 наблюдает Task WDT на
`loopTask`, reset reason 6 и exact-CID read-only recovery attempt 2 с одним timeout
restart, zero writes, complete cleanup и lease 0. Затем E-HIL-074 продвигает
generation 48→51 с 37/37 forwarded, шестью cold boots, zero drops/heap drift и
final lease 0. Retained summary:
[`board-01-product-hardware-watchdog-0.51.json`](../../tests/hil/evidence/board-01-product-hardware-watchdog-0.51.json).

## Приёмка

| ID | Обязательный результат |
|---|---|
| ST-HIL-A01 | Read-only discovery сохраняет media kind, capacity, filesystem, stable fingerprint и free space |
| ST-HIL-A02 | Run отклоняет media без явно выбранных disposable fingerprint и scratch namespace |
| ST-HIL-A03 | Все операции confined новым bounded `/leshy-hil/<run-id>/` namespace |
| ST-HIL-A04 | Reset injection на всех шести boundaries всегда восстанавливает prior valid generation или полностью synced new one |
| ST-HIL-A05 | Torn head, bad CRC, missing manifest и manifest mismatch никогда не становятся current |
| ST-HIL-A06 | Хэши ранее committed payload не меняются после каждого recovery |
| ST-HIL-A07 | SD и LittleFS измеряются отдельно; throughput report содержит sample size, p50/p95/p99, sync latency и free-space delta |
| ST-HIL-A08 | Physical power-cut повторяет boundary matrix до verification PR-005/RB-06 |
| ST-HIL-A09 | Enrolled exact-CID cold boot допускает latest valid product Session через write-blocking driver с zero SD writes и complete lease/mount cleanup |
| ST-HIL-A10 | Explicit product Survey принимает real passive observations, публикует ровно одну следующую bounded generation, переживает read-only reboot/export и aborts без commit или leaked lease |
| ST-HIL-A11 | Missing source Product Survey показывает localized real-TFT unavailable state только после полного cleanup; source/store start, Session, write, hidden retry и leaked lease отсутствуют, prior Library переживает reboot |

Offline Library/reopen, bounded export, non-mounting discovery, mount policy, SD
identity/geometry/technical-metadata paths, guarded FAT `SessionStore` commit плюс
remount/reopen, 32-commit p50/p95/p99 throughput distribution и host/static reset harness
плюс physical six-boundary matrix реализованы. Fixed queue и batched publish cadence
теперь host-tested, а E-HIL-038 даёт 9 068 encoded B/s при цели RB-06 2 184 B/s.
E-HIL-053 закрывает ST-HIL-A09, а E-HIL-054 — ST-HIL-A10 на одной board/card,
сохраняя изоляцию generic fixture от product enrollment. E-HIL-058 отклоняет
same-boot re-entry; E-HIL-059 подтверждает три normal reset-separated cycles и
инварианты endurance runner. E-HIL-069 сохраняет failed gate 0.49, E-HIL-071
подтверждает policy восемь attempts через два natural physical reset retries, а
E-HIL-072 отклоняет software-watchdog-only recovery после app-entry hang, а
E-HIL-073/074 подтверждают hardware fallback 0.51 и three-cycle product regression.
E-HIL-075 добавляет 12 последовательных cycles, generation 51→63, 144/144 records,
24 cold boots, invariant heap и zero drops при final lease 0; операторская остановка
сохранена как `interrupted`, поэтому это engineering checkpoint, не release-pass.
NFR-004 ≥45 минут/≥8 циклов с часовым бюджетом остаётся `DEMO-S4`. E-HIL-092
закрывает ST-HIL-A11 на
той же board/card с localized real-TFT failure, zero source/store start, неизменной
generation 68/25 и final lease 0. E-HIL-093 закрывает normal/remount половину
ST-HIL-A07 на изолированном и полностью восстановленном inactive OTA1 target. Те же
шесть commit boundaries всё ещё требуют отдельной LittleFS reset matrix, а physical
power-cut — controller.
