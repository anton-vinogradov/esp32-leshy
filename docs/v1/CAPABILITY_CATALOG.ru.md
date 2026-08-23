# ESP32-Leshy 1.x — каталог возможностей 1.0

*Read in: [English](CAPABILITY_CATALOG.md) · **Русский***

Статус документа: **product-reviewed baseline scope 1.0**, 16 августа 2026 года.

Этот каталог — пользовательское представление границы 1.0. Нормативные критерии
остаются в [PRODUCT_REQUIREMENTS.ru.md](PRODUCT_REQUIREMENTS.ru.md), а текущее
состояние реализации — только в [STATUS.ru.md](STATUS.ru.md). Возможность не считается
готовой из-за существования строки: её статус повышается до `verified` только по
связанному evidence.

## Как читать каталог

- **P0** — без возможности 1.0.0 не выпускается;
- **P1** — входит в согласованную полноту 1.0 и замораживается не позднее S7;
- **conditional** — обязательна для 1.0, когда соответствующий штатный или явно
  выбранный optional assembly объявлен и обнаружен;
- **S2…S7** — этап, на котором появляется законченный пользовательский путь;
- **S8** проверяет выпуск, но не добавляет крупные возможности.

До принятия S1 допустимы уточнения формулировок и приоритета. Добавление новой строки
после S1 требует связи с `J-*`, `PR/NFR-*`, этапом и тестом; после feature freeze S7 —
отдельного изменения границы релиза.

## Платформа и устройство

| ID | Возможность 1.0 | Обязательство | Требования | Этап готовности |
|---|---|---|---|---|
| CAP-001 | Boot probe определяет профиль платы, main/RF assembly и состояния capabilities с evidence | P0 | PR-001, PR-014 | S2/S5 |
| CAP-002 | Главный экран строится по доступным возможностям и объясняет disabled/conflicted/fault до запуска | P0 | PR-002 | S2 |
| CAP-003 | Diagnostics выполняет безопасный self-test без TX и экспортирует отчёт | P0 | PR-009 | S2/S5 |
| CAP-004 | TFT, кнопки и touch используют единые Actions; есть калибровка и доступный Back | P0 | PR-002, NFR-002, NFR-010 | S2 |
| CAP-005 | Настройки языка EN/RU, яркости, темы, звука и поведения экрана сохраняются локально | P1 | PR-011, NFR-010 | S2/S5 |
| CAP-006 | Питание, заряд, low-voltage safe-write, sleep/resume и причины reset видимы и проверяемы | P0 | PR-009, NFR-004 | S5 |
| CAP-007 | Browser install, stable/beta update, подпись, rollback и recovery image | P0 | PR-010 | S8 |
| CAP-008 | Локальные логи, crash journal и диагностический bundle не требуют облака | P1 | PR-009, PR-012 | S6/S8 |

## Обзор и наблюдения

| ID | Возможность 1.0 | Обязательство | Требования | Этап готовности |
|---|---|---|---|---|
| CAP-009 | Start/Stop создаёт ограниченную Survey Session с явной конфигурацией и provenance | P0 | PR-003 | S3 |
| CAP-010 | Пассивный Wi-Fi scan публикует нормализованные Observation | P0 | PR-003 | S3 |
| CAP-011 | Пассивный BLE scan/sniff публикует нормализованные Observation | P0 | PR-003 | S4 |
| CAP-012 | Три nRF24 дают пассивную картину активности 2.4 ГГц без скрытого TX | P0, conditional RF shield | PR-003, PR-014 | S4/S5 |
| CAP-013 | CC1101 даёт пассивный Sub-GHz spectrum/activity и RSSI/frequency evidence | P0, conditional RF shield | PR-003, PR-014 | S4/S5 |
| CAP-014 | GPS добавляет fix, спутники, время и track к Session, если explicit assembly выбран | conditional | PR-003, PR-014 | S4/S5 |
| CAP-015 | Общая timeline показывает источники, duty cycle, временную недоступность и dropped events | P0 | PR-003, NFR-004, NFR-005 | S4 |
| CAP-016 | Общие List/Detail/filter ведут себя одинаково для поддерживаемых радио | P0 | PR-004 | S3/S4 |
| CAP-017 | Radar/localize показывает историю RSSI и понятные пределы оценки близости | P1 | PR-004 | S4/S6 |
| CAP-042 | Пассивный Wi-Fi channel/packet monitor создаёт bounded Capture и совместимый PCAP с drop counters без скрытого TX | P0 | PR-003, PR-007, PR-015 | S4 |

Implementation checkpoint: exact `0.115.0-wifi-device-intelligence` углубляет
текущий detail CAP-016 «Устройства Wi-Fi» пассивными фактами management/data frames,
закреплённой lookup IEEE MA-L на 39 984 записи, явной обработкой private MAC и
selected-channel радаром текущего сигнала. Это первый полезный срез CAP-017 и
CAP-044, но он не закрывает ни один из них: retained RSSI history, localization
semantics, BLE/services/protocol profiles, Target correlation и persistent identity
history остаются в S6.

Exact `0.116.0-wifi-channel-average` уточняет presentation и decision rule «Каналов»
CAP-042. Последний passive airtime dwell остаётся виден узким цветным столбцом,
широкий серый столбец показывает арифметическое среднее с момента входа для каждого
канала 1…13, а наименее занятый основной канал 1/6/11 выбирается по этим средним.
Среднее bounded, allocation-free и volatile; это не calibrated CCA utilization и не
постоянный site survey.

Более поздний exact `0.120.0-wifi-channel-choice` устраняет скрытое ограничение 1/6/11.
Теперь участвует каждый измеренный канал 1…13, а главным критерием служит то же
серое среднее за сессию, которое пользователь видит на графике. Равные средние
разрешаются bounded-оценкой давления соседних каналов с весами 3/2/1; она не может
перевесить меньшее видимое среднее. На оси подсвечивается только рекомендованный
канал. Это всё ещё оценка airtime принятых кадров, а не calibrated RF energy/CCA
или регуляторный oracle настройки роутера.

Exact `0.121.0-wifi-channel-neutral-bars` удаляет последний визуальный остаток
устаревшего ограничения. Цвет текущего столбца зависит только от измеренной
загрузки; каналы 1/6/11 больше не получают особый цвет при низкой загрузке.
Единственным голубым номером остаётся рекомендация. Измерение и ranking не меняются.

Exact `0.122.2-ble-device-intelligence` углубляет CAP-011/016/017 для Bluetooth
«Устройства рядом». Fixed catalog теперь монотонно объединяет passive advertisement
facts, закреплённый lookup 4 012 назначенных компаний Bluetooth SIG, доступные
классификации device/subtype/tracker/service и volatile signal statistics.
Strongest-first строки сохраняют identity после начала взаимодействия, а detail
показывает vendor, address/type, connectable/scannable, TX power/appearance/service,
когда они объявлены, и встроенный current/range/trend radar. Прошивка не посылает
scan request, pairing или active probe и не сохраняет enriched device passport.
Один bounded retry разрешён только для transient failure старта/завершения scan;
принятый physical run не потребовал его, поэтому recovery этой ветки остаётся
source-contract, а не injected HIL evidence.

Exact `0.123.0-nrf24-signal-finder` углубляет CAP-012 второй пользовательской
задачей рядом с принятыми Спектром/Водопадом: «Найти сигнал» пульта, метки или
датчика. Она использует все обнаруженные nRF24, изучает два коротких окна фона и
показывает только локальный отклик над этим фоном с точной частотой и ближайшим
каналом Wi-Fi, когда это осмысленно. Путь allocation-free, volatile и RX-only.
Physical ambient/waiting path и немерцающий график проходят; deterministic host
injection доказывает mapping найденного сигнала. До controlled source на board-02
не заявляются physical found result и calibrated power/distance.

Exact `0.124.1-cc1101-frequency-finder` углубляет CAP-013 соответствующей задачей
Sub-GHz рядом с «Обзором эфира» и «Захватом RAW». Она пассивно покрывает 275…950 МГц
1 099 receiver bins с шагом 250 кГц, строит median-of-three ambient floor, отвергает
common drift и окрестности гармоник тактовой частоты платы и сообщает точные кГц
плюс ближайшую подсказку диапазона 315/433/868/915 МГц. Два независимых ambient run
отвергают невоспроизводимые пики, ложно принятые 0.124.0; failed predecessor сохранён
рядом с corrected evidence. Deterministic host injection доказывает настоящий
локальный отклик на 433 250 кГц. Physical positive detection и calibrated frequency,
power/distance остаются открыты до controlled source на board-02.

Exact `0.117.0-wifi-device-live-detail` уточняет presentation CAP-016/017: открытие
Wi-Fi-клиента сразу фиксирует его наблюдавшийся канал и показывает identity facts
вместе с live RSSI meter/range/trend на одном экране. Left снимает фиксацию канала и
возвращает прямо к стабильному списку. Удалено промежуточное navigation-only state;
active probing, calibrated distance или retained history не добавлены.

Exact `0.118.0-wifi-network-intelligence` углубляет CAP-010/016 для «Сетей рядом».
Каждый BSSID может показать вендора IEEE MA-L и все нормализованные факты из passive
scan record ESP-IDF: auth/ciphers, channel/frequency/width, PHY, WPS/FTM/RX antenna и
country/channel constraints. Пустой SSID остаётся явно скрытым, пока поздний пассивно
принятый beacon или probe response этого BSSID не сообщит имя; enrichment монотонен
и сохраняет navigation identity. Это только passive discovery, не directed probing,
association, decryption, уверенное определение типа устройства или persistent
tracking сети.

Exact `0.119.0-wifi-network-live-radar` завершает baseline presentation detail
CAP-010/016 текущим RSSI, качественной силой, шкалой, volatile минимумом/максимумом и
последним trend выбранного fixed BSSID на том же экране. Samples приходят из
продолжающегося all-channel passive discovery и сбрасываются при входе в задачу.
Это полезная относительная proximity feedback, но не selected-channel direct receiver,
calibrated range, исторический Target tracking или доказательство packet traffic.

## Цели и сравнение

| ID | Возможность 1.0 | Обязательство | Требования | Этап готовности |
|---|---|---|---|---|
| CAP-018 | Target хранит identities и историю исходных Observation | P1 | PR-008 | S6 |
| CAP-019 | Пользователь добавляет Target теги, заметки, имя и избранное | P1 | PR-008 | S6 |
| CAP-020 | Корреляция объясняет признаки/confidence; merge/split обратимы | P1 | PR-008 | S6 |
| CAP-021 | Baseline/diff сравнивает проходы и показывает новые, исчезнувшие и изменившиеся цели | P1 | J-04, PR-008 | S6 |
| CAP-022 | Каждый вывод compare/correlation открывает исходное доказательство | P1 | PR-008, NFR-008 | S6 |

## Захват, библиотека и переносимость данных

| ID | Возможность 1.0 | Обязательство | Требования | Этап готовности |
|---|---|---|---|---|
| CAP-023 | Capture неизменяем и хранит время, источник, частоту/канал, RSSI, координаты и настройки приёма | P0 | PR-005, NFR-008 | S3/S4 |
| CAP-024 | Session/Capture записываются атомарно и восстанавливаются после reset/power loss | P0 | PR-005, NFR-009 | S3/S5 |
| CAP-025 | Library открывает сохранённые Session/Capture офлайн, с list/detail/search/filter | P0 | PR-006 | S3/S6 |
| CAP-026 | Экспорт поддерживает JSON/CSV summary, PCAP для совместимых кадров и переносимые radio formats | P0/P1 | PR-007 | S3/S5 |
| CAP-027 | Import/export через SD, USB и local companion использует versioned schemas и fail-closed parser | P0 | PR-007, NFR-007, NFR-009 | S5/S6 |
| CAP-028 | SD и LittleFS имеют явную identity, capacity, recovery, integrity и degraded behavior | P0 | PR-005, PR-006, PR-009 | S3/S5 |
| CAP-029 | IR capture/decode/library сохраняет оригинал и производные результаты | P0, conditional RF shield | PR-007, PR-014 | S5 |
| CAP-030 | Sub-GHz RAW/decode/library сохраняет pulses, radio parameters и производные результаты | P0, conditional RF shield | PR-007, PR-014 | S5 |
| CAP-031 | PN532 читает tag/NDEF info и versioned dump при explicit assembly без GPIO-конфликта | conditional | PR-007, PR-014 | S5 |
| CAP-043 | Пользователь сохраняет screenshot реального TFT с build/state/time provenance и открывает его в Library/export | P1 | J-03, PR-015 | S2/S5 |

## Разрешённая лаборатория

| ID | Возможность 1.0 | Обязательство | Требования | Этап готовности |
|---|---|---|---|---|
| CAP-032 | Lab context отделён от пассивных сценариев и показывает область работ, частоту, мощность, время и TX state | P0 для любого TX | PR-013 | S7 |
| CAP-033 | Back, timeout, panic и fault физически прекращают каждый разрешённый TX path | P0 для любого TX | PR-013, NFR-002, NFR-006 | S7 |
| CAP-034 | IR replay доступен только для выбранного сохранённого Capture в разрешённом контуре | conditional | PR-013, PR-014 | S5/S7 |
| CAP-035 | Sub-GHz replay/TX использует ResourceBroker, bounds, явное подтверждение и исходный immutable Capture | conditional | PR-013, PR-014 | S5/S7 |
| CAP-036 | NFC write/restore выполняется только для поддерживаемой собственной метки с preview и verify | conditional | PR-013, PR-014 | S5/S7 |
| CAP-037 | Protocol workbench сравнивает pulses/waveforms, аннотирует поля и создаёт производный decode | P1 | J-06, NFR-008 | S7 |

## Companion и расширяемость

| ID | Возможность 1.0 | Обязательство | Требования | Этап готовности |
|---|---|---|---|---|
| CAP-038 | Local Web/USB companion просматривает, ищет, сравнивает и экспортирует через те же Actions/schema | P1 | PR-012 | S6 |
| CAP-039 | App descriptor объявляет capabilities, resources, permissions, safety и строки до запуска | P1 | PR-002, PR-013 | S7 |
| CAP-040 | Decoder/profile packages имеют version compatibility, integrity/signature и scoped storage | P1 | PR-010, PR-012 | S7/S8 |
| CAP-041 | SDK содержит sample extension, simulator trace kit и проверки, не позволяющие обойти leases/policy | P1 | PR-012, PR-013, NFR-006 | S7 |

## Идентификация и обслуживание устройства

| ID | Возможность 1.0 | Обязательство | Требования | Этап готовности |
|---|---|---|---|---|
| CAP-044 | Офлайн-база OUI/BLE company/services/protocol profiles обогащает факты с версией и provenance, но не подменяет исходное evidence | P1 | PR-008, PR-019 | S6 |
| CAP-045 | Единый feedback service управляет WS2812 и buzzer: quiet mode, idle GPIO2 LOW, bounded tones и доступные без цвета capture/proximity/fault cues | P1, conditional HW-T09 для sound | PR-009, PR-011, PR-016, NFR-010 | S5/S6 |
| CAP-046 | Локальная настройка Wi-Fi/USB connectivity хранит secrets отдельно, не экспортирует их и не делает сеть условием Survey/Library | P0 для PR-010/012 | PR-010, PR-012, PR-017 | S2/S6/S8 |
| CAP-047 | Versioned backup/restore и factory reset показывают scope/preview/checksum и не перезаписывают raw Capture без явного подтверждения | P1 | PR-005, PR-010, PR-018, NFR-008/009 | S5/S8 |

## Явно после 1.0

Не входят в этот каталог как обязательства 1.0: облачный аккаунт и telemetry по
умолчанию, публичный marketplace исполняемых приложений, массовая поддержка других
ESP32-плат, скрытые/disruptive действия и количество атак как метрика паритета.
Кандидат после 1.0 получает собственную пользовательскую задачу, risk review и stage
proposal; он не добавляется в таблицу задним числом.

## Gate полноты

- **S1 scope gate:** каждая `CAP-*` связана с requirement, приоритетом и этапом;
  каталог и явные исключения проходят product review.
- **S2 UX gate:** для всех разделов существует navigation/state baseline на реальном
  TFT, включая disabled/error/empty/running/confirm states.
- **S7 feature-complete gate:** все P0/P1 и применимые conditional возможности имеют
  завершённый путь или явно принятый `deferred/rejected` requirement.
- **S8 release-complete gate:** все P0 verified, нет открытых P0/P1 дефектов, а
  применимые P1 прошли release matrix.
