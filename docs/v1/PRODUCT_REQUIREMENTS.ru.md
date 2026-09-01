# ESP32-Leshy 1.x — требования продукта

Статус документа: **принятый baseline 1.0, расширенный product decision**, 1 сентября 2026 года.

Этот документ превращает [продуктовую концепцию](VISION.ru.md) и
[конкурентный анализ](COMPETITIVE_ANALYSIS.ru.md) в проверяемую границу 1.0.0.
Формулировки и acceptance уточняются через governance, но scope и идентификаторы
зафиксированы для трассировки решений и тестов.

## Обещание продукта

ESP32-Leshy 1.x — автономный переносной инструмент, который собирает наблюдения из
нескольких доступных радиоподсистем ESP32-DIV в одну сессию, помогает исследовать
источник сигнала и сохраняет проверяемые исходные данные для последующего анализа.

Он должен быть полезен без телефона, аккаунта и интернета. Локальный Web/USB
companion дополняет экран устройства, но не является условием базовой работы.

Продуктовая сущность Leshy — **evidence-first multi-radio instrument с отдельной
bounded Owned Lab**. Пассивное исследование и воспроизводимые evidence являются
нормой; active experiments существуют только как именованные scoped recipes для
собственного оборудования или явно разрешённого стенда.

## Пользовательские задачи

### J-01. Обзор окружения

«Когда я прихожу на объект, я хочу запустить одну сессию и увидеть доступную
радиоактивность, чтобы быстро понять, что присутствует и что изменилось».

### J-02. Идентификация и локализация

«Когда найден неизвестный источник, я хочу открыть его карточку, увидеть признаки и
историю RSSI и включить режим локализации, чтобы приблизиться к источнику».

### J-03. Захват и доказательство

«Когда сигнал важен, я хочу сохранить исходный захват вместе со временем,
координатами и условиями приёма, чтобы результат можно было проверить позже».

### J-04. Сравнение

«Когда я возвращаюсь на объект или повторяю действие своего устройства, я хочу
сравнить сессии/захваты и увидеть различия, не просматривая всё вручную».

### J-05. Диагностика самого Leshy

«Когда функция недоступна, я хочу до её запуска увидеть найденные модули, конфликт
ресурсов и возможное исправление, а не получить необъяснимый сбой».

### J-06. Разрешённая лаборатория

«Когда я исследую собственное устройство, я хочу безопасно воспроизвести сохранённый
сигнал с видимыми параметрами, таймаутом и мгновенной остановкой».

### J-07. Защитная полевая проверка

«Когда эфир выглядит подозрительно, я хочу пассивно обнаружить и понять событие,
открыть исходное evidence и сохранить его, не превращая наблюдение в автоматическую
атаку».

### J-08. Защита и автоматизация своего оборудования

«Когда Leshy хранит чувствительные данные или управляет моим стендом, я хочу
защитить локальные evidence, явно выбрать serial/BLE target и запускать только
permissioned bounded automation».

## Термины продукта

- **Observation** — неизменяемый факт приёма с временем, источником, каналом или
  частотой, RSSI и ссылкой на payload.
- **Target** — локальная долговечная сущность, объединяющая одну или несколько
  идентичностей и историю наблюдений. Автокорреляция всегда объяснима и обратима.
- **Capture** — неизменяемый исходный blob и производные декодирования.
- **Session** — ограниченный во времени контекст наблюдений, конфигурации устройства
  и, если доступны, координат.
- **Action** — одна доменная операция, одинаковая для UI, CLI, Web UI и тестов.
- **Capability** — возможность, подтверждённая сборкой и boot probe на этом устройстве.
- **Resource lease** — явное ограниченное владение аппаратным или системным ресурсом.

## Функциональные требования 1.0.0

| ID | Требование | Приёмка | Приоритет |
|---|---|---|---|
| PR-001 | Boot probe определяет main board, assembly profile и безопасно проверяемые модули | Diagnostics показывает declared/detected/available/conflicted/fault/unknown, evidence и причину; неоднозначность не приводит к перебору output modes | P0 |
| PR-002 | Меню строится по capabilities | Недоступное действие скрыто или отключено с объяснением до запуска | P0 |
| PR-003 | Survey создаёт единую Session | Wi-Fi/BLE и все доступные detected receivers представлены общей временной шкалой с честным duty cycle; отсутствующий external GPS/PN532 не считается дефектом | P0 |
| PR-004 | Общие List/Detail/Radar доступны для поддерживаемых Observation/Target | Back, фильтры и единицы измерения ведут себя одинаково между радио | P0 |
| PR-005 | Session/Capture сохраняются атомарно | Прерывание питания во время записи не повреждает уже подтверждённые данные | P0 |
| PR-006 | Сохранённые evidence можно открыть и управлять ими офлайн после reboot | Список, детали и исходные capture доступны без активного радио; удаление сначала использует восстанавливаемую Корзину/Отмену до окончательной очистки | P0 |
| PR-007 | Есть экспорт переносимых данных | PCAP для совместимых сетевых захватов; JSON/CSV summary; Flipper-compatible `.sub`; совместимые IR/NFC форматы где возможно | P0/P1 |
| PR-008 | Target хранит историю, заметки, теги и связи identity | Merge/split обратимы; автоматическое объединение показывает confidence и признаки | P1 |
| PR-009 | Явное приложение Self-Test проверяет ресурсы, firmware workflows и установленное hardware | Home→Устройство→Самопроверка предлагает read-only Quick и scoped Full/Guided; оба режима используют те же versioned checks, что release HIL, честно показывают `not_applicable/blocked`, оставляют zero leases и сохраняют экспортируемый отчёт; при boot Self-Test автоматически не запускается | P0 |
| PR-010 | Установка, update и recovery документированы | Browser install, stable/beta OTA, signed SD update, проверка подписи, rollback и recovery проходят HIL | P0 |
| PR-011 | Базовые сценарии доступны и настраиваются на EN/RU | Переключение языка не требует другой сборки и не обрезает критические сообщения; font scale, contrast/reduced motion, input repeat, favorites, hidden apps и shortcuts сохраняются локально | P1 |
| PR-012 | Локальный companion использует те же Actions и schema | Просмотр/экспорт не требует облака; права не шире, чем у локальной сессии | P1 |
| PR-013 | Активные действия доступны только в Lab context | Параметры/индикатор/таймер/stop видимы; panic и expiry физически прекращают TX | P0 для любого включённого TX |
| PR-014 | 1.0.0 покрывает документированные конфигурации ESP32-DIV v2 | Main board и RF shield имеют probe/базовые сценарии; GPS и PN532 поддерживаются отдельными explicit assembly profiles без GPIO5/6 contention | P0 |
| PR-015 | Field Capture сохраняет проверяемое пассивное evidence | Wi-Fi packet/channel monitor выдаёт bounded immutable Capture и совместимый PCAP с drop counters; screenshot реального TFT содержит build/state/time provenance; ни один путь не включает скрытый TX | P0 для Wi-Fi capture, P1 для screenshot |
| PR-016 | Визуальный и звуковой feedback управляется одним безопасным сервисом | WS2812/buzzer недоступны apps напрямую; quiet mode сохраняется; GPIO2 всегда LOW вне bounded tone; fault/TX/critical state различим без звука и цвета | P1, sound conditional HW-T09 |
| PR-017 | Connectivity не нарушает offline-first и границу секретов | Wi-Fi/USB setup хранит credentials отдельно от Sessions/reports/backups; Survey/Library работают без сети; OTA/companion получают только явно выданный scope | P0 для PR-010/012 |
| PR-018 | Backup/restore и factory reset безопасны для пользовательских данных | До операции показаны scope, schema, checksum и overwrite plan; cancel ничего не меняет; raw Capture не заменяется молча; restore и reset имеют recovery test | P1 |
| PR-019 | Офлайн-обогащение не подменяет исходные факты | OUI/BLE/protocol database показывает version/provenance; отсутствие или устаревание базы оставляет raw identity доступной и не создаёт ложную корреляцию | P1 |
| PR-020 | Пассивно обнаруживать подозрительные wireless-состояния и объяснять каждый alert | Защита эфира предлагает named detector profiles и sensitivity, показывает detector/version/threshold/confidence, учитывает WPA3/PMF/SAE и cross-radio признаки jamming и открывает exact source evidence; недостаточные данные остаются inconclusive и никогда не запускают active response | P1 |
| PR-021 | Выделить захват Wi-Fi-аутентификации в законченный passive workflow | EAPOL/PMKID и complete/incomplete handshake state явны; immutable evidence экспортируется в совместимые PCAP и `hc22000` с provenance; active provocation отсутствует вне отдельно принятого Lab recipe | P1 |
| PR-022 | Дать законченный offline Field Survey | Wi-Fi AP/station и BLE observations дедуплицируются и при наличии GPS связываются с track, satellite diagnostics, POI и field notes; сравнение повторного прохода и локальный WiGLE-compatible export сохраняют source IDs/uncertainty и не требуют cloud upload | P1 |
| PR-023 | Исследовать BLE глубже advertisement summary без скрытого подключения | Совместимые raw packets экспортируются; connected GATT enumeration требует явного mode transition, выбранного target, permission, visible connection state, отдельного lease и детерминированного disconnect/cleanup | P1 |
| PR-024 | Защищать локальные secrets и evidence через Device Lock | First-run/local PIN setup, bounded retry и документированный recovery не обходят safe cleanup, panic, update recovery или factory reset; lock overlay может продолжать ранее разрешённый безопасный Capture, но controls, identities и export не раскрывают protected content; owner может явно отключить PIN без удаления или перешифрования существующих данных и позже установить новый PIN | P0 до релиза, хранящего credentials или чувствительные captures |
| PR-025 | Дать bounded [Serial Console и общий Actions CLI](SERIAL_CONSOLE.ru.md) | Пользователь явно выбирает named UART profile/baud/mode и target; ResourceBroker владеет session; exit/error освобождает её; permissions CLI не шире on-device Actions, raw GPIO control отсутствует | P1 |
| PR-026 | Запускать [permissioned signed automation и явно scoped HID workflows](AUTOMATION_HID.ru.md) | Signature/version/permissions package, resource ceilings, action preview, finite runtime и cancel/panic обязательны; USB/BLE HID требует подтверждённого target/scope, а BadUSB inspection по умолчанию пассивен | P1 |
| PR-027 | Поставлять только именованные и отдельно принятые wireless Lab recipes | Каждый Wi-Fi/BLE/nRF/IR recipe объявляет owned fixture/target, region, channel/frequency, явный power profile, duration, expected evidence и hardware stop path; targeted handshake-assist, synthetic iBeacon/identity emulation, MouseJack injection, проверка устойчивости к RF-помехе на выбранном канале, другие bounded robustness/crash и IR-camera tests допускаются только при доказанных target и containment. Interference recipe может выбирать полную qualified мощность железа, требует isolated fixture/interlock и fail closed, если containment не подтверждён; UI/evidence отличают requested radio power setting от независимо измеренной мощности. Unbounded/indiscriminate ambient output и harvesting secrets отклоняются | P0 для любого shipped active output |
| PR-028 | Захватывать и исследовать nRF24 ESB evidence | Совместимые ESB packets сохраняются и декодируются; доступен passive MouseJack detection; injection существует только как отдельно допущенный recipe Owned Lab на собственном fixture | P1 |
| PR-029 | Дать read-only Live Companion | USB Wireshark/extcap передаёт совместимые Wi-Fi/BLE evidence и зеркалирует TFT без изменения host network, расширения permissions или превращения companion в обязательную часть автономной работы | P1 |
| PR-030 | Дать Advanced NFC/EMV в пределах аппаратных возможностей | Conditional PN532 workflows включают NDEF/ISO14443-4 emulation, erase, bounded recovery собственной метки и redacted EMV protocol metadata; PAN, expiry, submitted PIN и эквивалентные payment secrets никогда не сохраняются | P1, conditional PN532 |
| PR-031 | Управлять собственными и synthetic lab identities Leshy | Randomization STA/AP настраивается локально; identity emulation создаётся только из owned Capture или явного synthetic template, остаётся ephemeral, provenance-labeled, time-bounded и доступна только в Owned Lab | P1 |
| PR-032 | Безопасно исследовать физические USB-устройства | Conditional USB Host показывает VID/PID/class/interfaces и bounded signed keyboard/HID inspection только после квалификации OTG/VBUS/current limit и deterministic cleanup | P1, conditional hardware profile |
| PR-033 | Проверять собственные evidence, не маскируя cracking под наблюдение | Leshy валидирует явно собственный PMKID/полный EAPOL evidence и экспортирует canonical `hc22000`; bounded verification на компьютерном companion сравнивает его с versioned corpus распространённых/слабых паролей и vendor-default patterns с preview, budget, pause/stop, checkpoint и provenance. Companion может показать match владельцу, но plaintext никогда не возвращается на Leshy и не сохраняется в его logs/screenshots/reports/exports; durable result содержит класс слабости, version/source/rank corpus, стоимость проверки и ссылки на evidence. Identity-linked leaked credential collections не поставляются. Проверки NFC/Sub-GHz/fixed-code могут оставаться local или companion-assisted | P1 |
| PR-034 | Проверять собственный изолированный network fixture | Read-only LAN inventory доступен штатно; captive-portal/ARP/DHCP/MITM robustness recipes требуют явно выбранного isolated fixture, bounded duration и physical Stop; training portal сохраняет outcome, но никогда submitted secret | P1 |

## Системные требования

| ID | Бюджет или инвариант |
|---|---|
| NFR-001 | Холодный boot до интерактивного экрана ≤ 2 с при исправной штатной конфигурации |
| NFR-002 | Back обрабатывается ≤ 150 мс и освобождает foreground leases |
| NFR-003 | UI callback не блокирует core дольше 10 мс; долгие операции отменяемы |
| NFR-004 | Release endurance охватывает не менее 45 минут и восьми полных циклов passive Survey, укладывается в операционный бюджет один час и не имеет монотонного роста heap, зависания UI, drops, утечек leases или повреждения Session |
| NFR-005 | Очереди bounded; overflow измеряется, отражается в Diagnostics и не портит память |
| NFR-006 | Ни один driver/app не использует общий radio/SPI/UART/filesystem вне lease/service contract |
| NFR-007 | Все импортируемые форматы имеют bounds tests и fuzz corpus; ошибочный файл не перезагружает устройство |
| NFR-008 | Исходный Capture неизменяем; декодирование и редактирование создают производные данные |
| NFR-009 | Версии schema мигрируются вперёд или отклоняются с понятной ошибкой без потери исходника |
| NFR-010 | Критическое состояние различимо без цвета; всё основное управление возможно штатными кнопками |
| NFR-011 | Реальные submitted credentials, payment identifiers, PIN и эквивалентные secrets никогда не сохраняются в persistence, logs, screenshots, reports или exports; полезная protocol metadata минимизируется и редактируется |
| NFR-012 | Любой active output имеет явно выбранный target или qualified fixture, declared scope/expiry, видимое состояние, deterministic cleanup и physical Stop; broadcast stress/interference требует доказанной isolation/interlock |
| NFR-013 | Ни app, script, signed package, developer mode, ни companion command не могут обойти ResourceBroker, Safety Supervisor, watchdog, permission review, expiry или physical Stop |

## Граница 1.0.0

Входит:

- независимая от 0.x firmware target для ESP32-DIV v2;
- Diagnostics, Survey, Targets, Capture/Library и Device settings;
- пассивные базовые сценарии всех штатных приёмников;
- Защита эфира, focused Wi-Fi authentication Capture, offline Field Survey, BLE
  Inspector, nRF24 ESB Workbench, Advanced NFC/EMV, USB Host Inspector, Owned
  Evidence Verification и Owned Network Lab;
- Device Lock, Privacy Identity, bounded Serial Console/Actions CLI и read-only Live
  Companion;
- permissioned signed automation/HID и отдельно допускаемые wireless/IR Lab recipes;
- Wi-Fi packet/PCAP Capture, screenshot evidence и versioned offline enrichment;
- IR/NFC операции с собственными устройствами и метками, прошедшие SafetyPolicy;
- SD/LittleFS storage, импорт/экспорт, portable `.sub`, browser install, signed
  OTA/SD update, rollback/recovery;
- scoped connectivity, safe LED/buzzer feedback и backup/restore/factory reset;
- EN/RU UI, host tests, HIL smoke и endurance gate.

Не входит в обязательную границу:

- поддержка других плат без владельца board profile и HIL target;
- облачный аккаунт, публичное облачное хранилище или telemetry по умолчанию;
- публичный каталог исполняемых приложений/mobile sync до стабилизации SDK и threat model;
- authenticated DIV-to-DIV Peer Link;
- количество disruptive/attack-функций как критерий паритета;
- автоматическая корреляция личностей без объяснения и ручного отменяемого решения.

Это отложенный scope, а не разрешение ослаблять `NFR-011…NFR-013`.

## Первый вертикальный срез: Survey Session

Срез считается готовым только как законченный пользовательский путь:

1. чистая target 1.x загружается и выполняет HardwareProbe;
2. пользователь открывает Survey и запускает сессию;
3. один пассивный источник публикует нормализованные Observation;
4. общий List открывает Detail; Back не останавливает систему некорректно;
5. сессия останавливается и атомарно сохраняется;
6. после reboot она открывается при выключенном радио;
7. summary экспортируется в JSON;
8. host tests проверяют domain/storage/navigation, HIL — boot/input/source/stop;
9. отсутствие источника показывает понятное состояние и не оставляет lease.

Первым источником выбирается тот, который после аппаратной карты даст наименьший
риск bring-up. Предварительный кандидат — пассивный Wi-Fi scan: он не зависит от
внешнего модуля и проверяет всю цепочку данных. Выбор не замораживается до фиксации
resource envelope платы.

## Запись принятия baseline

`E-GATE-001` принимает baseline 1.0, потому что:

- [карта аппаратуры](HARDWARE_ENVELOPE.ru.md) подтверждена схемой, кодом 0.x и
  безопасным board-01 HIL; недоступные приборы, вторая плата и optional assemblies
  имеют fail-closed defaults и named S4/S5/S8 evidence вместо вымышленных claims;
- для J-01…J-08 описаны happy path, cancel/error и критерии приёмки в
  [эталонных сценариях](REFERENCE_WORKFLOWS.ru.md);
- каждое P0-требование связано с компонентом архитектуры и типом теста;
- flash/RAM/storage бюджеты измерены, а power/shared-bus limits явно constrained в
  [реестре ресурсных бюджетов](RESOURCE_BUDGETS.ru.md).

`accepted` фиксирует обязательный scope; `implemented` и `verified` назначаются
отдельно по evidence соответствующих S2…S8 gates.
