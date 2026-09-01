# Конкурентный анализ ESP32-Leshy 1.x

Срез рынка: **15 августа 2026 года**.

Пофункциональный аудит паритета: **27 августа 2026 года**; повторный аудит по
официальным источникам завершён **1 сентября 2026 года**.

Этот документ задаёт направление продукта, а не рейтинг прошивок. Мы сравниваем
решения по тому, насколько хорошо они помогают пройти полный рабочий сценарий:

> обнаружить → распознать → локализовать → записать → сравнить → безопасно
> воспроизвести в своей лаборатории → сохранить или экспортировать результат.

Количество отдельных функций и демонстрационных воздействий само по себе не
считается преимуществом.

## Методика

Оценка основана на официальных репозиториях и документации проектов. Это
качественный обзор заявленных и видимых возможностей, а не сравнительное
лабораторное тестирование на одинаковом железе.

Мы рассматриваем девять измерений:

1. глубина поддержки аппаратуры ESP32-DIV;
2. обнаружение и пассивное наблюдение Wi-Fi, BLE и внешних радиомодулей;
3. запись, организация и экспорт результатов;
4. единая модель действий между экраном, CLI, Web UI и companion-приложением;
5. расширяемость без пересборки всего firmware;
6. понятность и доступность интерфейса в полевых условиях;
7. переносимость между платами без потери целостности продукта;
8. обновление, восстановление и совместимость данных;
9. тестируемость и безопасное управление общими ресурсами платы.

## Стратегическая группа

### ESP32-DIV original

[Оригинальная ESP32-DIV firmware](https://github.com/CiferTech/ESP32-DIV) —
аппаратная и функциональная точка отсчёта. Она показывает ширину возможностей
самого устройства: Wi-Fi, BLE, NRF24, Sub-GHz, IR, NFC, GPS и системные функции.
Для Leshy это минимальная планка аппаратного покрытия, но не образец архитектуры
или информационной модели.

**Что взять:** знание разводки, проверенные драйверные пути и полноту модулей.

**Что изменить:** перейти от набора независимых экранов к связанному сценарию
наблюдения и артефактам, которые можно открыть, сравнить и экспортировать.

### GhostESP

[GhostESP](https://github.com/GhostESP-Revival/GhostESP) — наиболее близкий
стратегический конкурент по направлению «устройство как платформа». Проект
опирается на ESP-IDF, связывает UI, CLI, Web UI и внешние клиенты одной системой
команд, поддерживает PCAP и другие переносимые форматы, несколько ESP через
GhostLink, Lua и нативные приложения с разрешениями и ограниченным хранилищем.

**Что взять как ориентир:** единое ядро действий, данные как первоклассный
результат, разрешения приложений, плагины, доступность UI, развитую цепочку
экспорта.

**Где превосходить:** цельный сценарий именно для ESP32-DIV, детерминированная
работа при конфликтующих GPIO/шинах, одинаково качественный офлайн-режим без
обязательной облачной части, строгая модель Observation/Target/Session.

### Bruce

[Bruce](https://github.com/BruceDevices/firmware) — ориентир по ширине функций,
сообществу и поддержке множества плат. В проекте есть общие интерфейсы плат,
меню, файловые сценарии, скриптинг и несколько способов установки.

**Что взять как ориентир:** адаптеры плат, вклад сообщества, быстрый путь от идеи
до доступной пользователю функции, удобную установку.

**Где не повторять компромисс:** не расширять матрицу плат раньше, чем стабильно
работают модель данных, ресурсы и базовые сценарии на ESP32-DIV; не превращать
главное меню в каталог несвязанных экспериментов.

### ESP32 Marauder

[ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder) — зрелый
специализированный ориентир по Wi-Fi/BLE-наблюдению, PCAP, SD-карте, вариантам
аппаратуры и процессу релизов. Он важен не широтой всех радиодиапазонов, а
глубиной одного ключевого направления.

**Что взять как ориентир:** устойчивые полевые Wi-Fi-сценарии, запись трафика,
понятный жизненный цикл релизов и аппаратных вариантов.

**Где превосходить:** единая сессия для нескольких радиоподсистем, встроенное
сравнение результатов, локализация источников и общая библиотека наблюдений.

### Flipper Zero firmware

[Официальная firmware Flipper Zero](https://github.com/flipperdevices/flipperzero-firmware)
работает на другом классе устройства, но остаётся ориентиром продуктовой
целостности: стабильные приложения, SDK, файловые форматы, разделение системных и
пользовательских приложений, понятная навигация и экосистема.

**Что взять как ориентир:** контракт приложения, устойчивые форматы файлов,
совместимость между версиями, чёткую границу платформы и пользовательских
расширений.

**Где превосходить:** объединить в одной сессии Wi-Fi/BLE и внешние радиомодули,
использовать сетевые возможности ESP32 для локального companion-интерфейса и
сделать доступную платформу на массовом железе.

## Вторичная группа

- [NEMO](https://github.com/n0xa/m5stick-nemo) полезен как пример простой,
  предсказуемой навигации несколькими кнопками и ясного позиционирования, но не
  является архитектурным эталоном для Leshy.
- [CapibaraZero](https://github.com/CapibaraZero/fw) архивирован и направляет
  пользователей в Bruce. Это полезное предупреждение: широкая амбиция без
  устойчивой платформы и сообщества может закончиться миграцией, а не продуктом.

## Качественная матрица

Обозначения: **сильная** — направление является одной из опор проекта;
**есть** — возможность заметна, но не определяет продукт; **ограниченная** — не
является сильной стороной или рассчитана на другой класс устройства.

| Решение | ESP32-DIV и multi-radio | Wi-Fi capture | Данные и экспорт | Расширения | Несколько интерфейсов | Цельный UX |
|---|---|---|---|---|---|---|
| ESP32-DIV original | сильная | есть | ограниченная | ограниченная | ограниченная | ограниченный |
| GhostESP | есть | сильная | сильная | сильная | сильная | сильный |
| Bruce | сильная широта плат | есть | есть | есть | есть | есть |
| ESP32 Marauder | ограниченная | сильная | сильная | ограниченная | есть | сильный в своей нише |
| Flipper Zero | другой hardware | ограниченная | сильная | сильная | сильная экосистема | сильный |
| Leshy 1.x, цель | сильная глубина | сильная | сильная | сильная после 1.0 | сильная | единый cross-radio UX |

## Пофункциональный аудит паритета

Качественная матрица выше задаёт направление продукта, но **не** доказывает, что
в каталоге Leshy есть каждый полезный сценарий конкурентов. Второе review проверило
актуальные официальные списки возможностей
[ESP32-DIV](https://github.com/cifertech/ESP32-DIV/wiki/Features),
[GhostESP](https://github.com/GhostESP-Revival/GhostESP),
[Bruce](https://github.com/brucedevices/firmware),
[ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder/wiki/marauder-versions),
[Flipper Zero](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/ReadMe.md)
и, как дополнительный defensive-ориентир,
[NEMO](https://github.com/n0xa/m5stick-nemo/blob/main/README.md). Сравнивались
пользовательские результаты, а не написание пунктов меню и не каждый protocol
toggle.

Вердикт: **CAP-001…CAP-047 образовывали цельную ранее замороженную границу, но не
были полным перечнем конкурентных функций.** Решением от 27 августа восемь из
девяти найденных семейств приняты как `CAP-048…CAP-055`; каждое получило обычную
трассировку `J/PR/CAP/risk/stage` и владельца S7. `CF-005 Peer Link` остаётся явно
отложенной функцией после 1.0, а не скрытым требованием.

Повторный аудит от 1 сентября отменил прежнее утверждение, что каталог из 55 строк
уже покрывает каждый полезный outcome конкурентов. Владелец принял все полезные
результаты, совместимые с evidence-first multi-radio instrument и отдельной bounded
Owned Lab. Refinements внесены в существующие строки, семь самостоятельных outcomes
стали `CAP-056…CAP-062`; **62 теперь фиксированный знаменатель 1.0**. Отложенные
integrations и три непересматриваемые safety/privacy границы явно перечислены ниже.

| Семейство из официальных документов конкурентов | Текущее покрытие Leshy | Результат аудита |
|---|---|---|
| Boot probe, capability-aware UI, настройки, питание, диагностика, установка/update/recovery | CAP-001…008, CAP-045…047 | явно покрыто и собрано в более цельный lifecycle |
| Кнопки/touch, стабильная навигация, темы, яркость и доступная обратная связь | CAP-004/005/045 | явно покрыто |
| Session, Capture, Library, целостность SD/LittleFS, переносимые форматы и backup | CAP-009/023…031/040/043/047 | явно покрыто; произвольный raw file manager сознательно не нужен |
| Одна command model для устройства, automation, USB и local Web | CR-001, PR-012, CAP-038/041/053/057 | shared Actions, bounded Serial Console и read-only Live Companion явны |
| Wi-Fi network/client discovery, vendor/facts, раскрытие hidden name и radar | CAP-010/016/017/044 | явно покрыто |
| Wi-Fi channels, packet monitor, raw frame Capture и PCAP | CAP-023/026/042 | явно покрыто |
| Распознавание EAPOL/PMKID/4-way handshake, focused capture и экспорт `hc22000`/live analysis | CAP-049/057/061 | focused passive Capture принят; bounded owned-evidence verification и live stream запланированы |
| Wardriving Wi-Fi AP/station и BLE с GPS track и локальным WiGLE-compatible результатом | CAP-050 | end-to-end Field Survey принят; GPS/POI refinements conditional/active |
| Passive deauth/PineAP/evil-twin/WPS, tracker/skimmer/drone и jamming-warning views | CAP-048 | evidence-backed Защита эфира принята; expanded named profiles active |
| BLE scan, identity/vendor/service advertisement facts и radar | CAP-011/016/017/044 | явно покрыто |
| BLE raw packet Capture/Wireshark и opt-in GATT/service/characteristic inspection | CAP-051/057 | explicit GATT Inspector плюс planned read-only live extcap |
| nRF24/Sub-GHz spectrum, waterfall, finder, ESB/RAW/decode/library и bounded replay | CAP-012/013/030/035/037/040/056 | явно покрыто; ESB Workbench planned S7 |
| IR learn/decode/library/replay и переносимые/universal profile packages | CAP-029/034/040 | покрыто общей моделью профилей; TV-B-Gone — профиль, а не отдельная архитектура |
| NFC read/dump/decode/emulation/erase/owned-tag recovery, redacted EMV и verified write/restore | CAP-031/036/040/058 | явно покрыто для declared PN532 assembly |
| Authenticated peer operation, remote receiver/source и обмен two-device evidence | пользовательской возможности нет | отсутствует (`CF-005`) |
| First-run setup, local PIN/lock и защита captures/secrets при потере устройства | CAP-052 | explicit; protected storage/PIN приняты, lock-overlay refinement active |
| Исполняемые SD apps/scripts, USB/BLE HID и defensive BadUSB inspection | CAP-054/060 | permissioned runtime/HID плюс conditional physical USB Host Inspector |
| Конкретные authorized Wi-Fi/BLE/nRF/IR Lab recipes | CAP-032…036/055/056/062 | named Owned Lab set принят; каждый active recipe требует individual containment evidence |
| Общий LAN discovery и isolated LAN robustness tests | CAP-062 | read-only inventory и bounded Owned Network Lab приняты; общий remote-admin toolbox остаётся post-1.0 |
| LF RFID/iButton, FM, Zigbee/802.15.4, Ethernet, camera, microphone/audio и printer | штатный ESP32-DIV не имеет нужных assemblies | conditional expansion, не паритет 1.0 |
| Targeted stress/interference/identity recipes | CAP-055/056/062 | допускаются только для selected owned/authorized isolated fixtures; indiscriminate output и secret retention запрещены |
| U2F, игры, декоративные часы и общие QR utilities | покрытия нет | полезно в других продуктах, но не относится к задаче radio observation Leshy |

### Найденные пробелы и окончательное решение о scope

| ID | Candidate user outcome | Чем он существенно отличается от существующей строки | Итоговое решение |
|---|---|---|---|
| CF-001 | **Защита эфира** пассивно обнаруживает и объясняет deauth/disassociation bursts, признаки PineAP/evil twin, подозрительные BLE tracker/skimmer/drone IDs и loss/jamming indicators; alert всегда открывает source evidence | CAP-042 записывает frames, но не формирует defensive conclusion | принято как `CAP-048`, `PR-020`, S7; только RX и evidence-backed |
| CF-002 | **Захват Wi-Fi-аутентификации** распознаёт EAPOL, PMKID и complete/incomplete handshakes, сохраняет focused evidence и экспортирует PCAP плюс `hc22000`; live host streaming остаётся local и bounded | общий PCAP не отвечает пользователю, получено ли пригодное authentication evidence | принято как `CAP-049`, `PR-021`, S7; вне отдельно принятого Lab recipe путь только passive |
| CF-003 | **Полевой обзор** записывает Wi-Fi AP/station и BLE с GPS track, deduplication, сравнением повторного визита и локальным WiGLE-compatible экспортом | GPS metadata плюс общий CSV не образуют end-to-end wardriving job | принято как `CAP-050`, `PR-022`, S7; direct cloud upload остаётся optional/post-1.0 |
| CF-004 | **BLE Inspector** сохраняет совместимые raw packets и после явного перехода в connected mode перечисляет GATT services/characteristics с provenance | service IDs из advertisements не равны GATT inspection | принято как `CAP-051`, `PR-023`, S7; connected GATT явный, permissioned и получает отдельный lease |
| CF-005 | **Peer Link** безопасно связывает два DIV для remote receiver/source control, evidence transfer и повторяемых two-device test scenarios | нынешний companion связывает host и device, но не позволяет одному DIV проверять другой | явно отложено после 1.0; `CAP-*` не резервируется |
| CF-006 | **Блокировка устройства** даёт first-run security setup, local PIN/lock, bounded retry/recovery и защищает secrets/saved evidence без нарушения safe capture cleanup | scoped secrets запрещают экспорт, но не закрывают physical UI | принято как `CAP-052`, `PR-024`, S7 |
| CF-007 | **Serial Console** даёт bounded on-device serial monitor/UART bridge и документированный Actions CLI без обхода policy/leases | diagnostics/logs не работают с внешним UART target | принято как `CAP-053`, `PR-025`, S7; raw GPIO control остаётся вне base product |
| CF-008 | **Automation/HID** запускает permissioned signed scripts и явно scoped USB/BLE HID или BadUSB-inspection workflows | CAP-039…041 описывают extension contracts, но не исполняемый user outcome | принято как `CAP-054`, `PR-026`, S7; defensive inspection пассивна, HID execution явный и scoped |
| CF-009 | **Authorized wireless Lab recipes** дают именованные bounded Wi-Fi/BLE/nRF/IR fixture workflows вместо пустой общей active-оболочки | CAP-032/033 делают output безопасным, но не определяют существующие experiments | принято как `CAP-055`, `PR-027`, S7; targeted handshake assist, synthetic identity/iBeacon, MouseJack injection, bounded robustness/crash/interference и IR-camera tests принимаются отдельно только с доказанными target/containment; indiscriminate output и secret retention запрещены |

### Итог аудита

- **Явно представлены:** полный passive multi-radio foundation, on-device analysis,
  durable evidence, owned-lab пути IR/NFC/Sub-GHz, update, recovery, companion,
  настройки, feedback и extension boundaries.
- **Приняты в 1.x:** `CF-001…CF-004` и `CF-006…CF-009`, теперь
  `CAP-048…CAP-055` с владельцем S7.
- **Явно после 1.0:** `CF-005 Peer Link`.
- **Принято из аудита 1 сентября:** все ценные refinements плюс
  `CAP-056…CAP-062` под теми же S7 evidence/safety gates.
- **Жёсткие исключения:** сохранение реальных submitted credentials/payment
  secrets; unbounded/indiscriminate active output; обход broker/safety/watchdog/Stop.
- **Scope claim:** проект имеет трассируемый фиксированный baseline 1.x из **62
  capabilities**, покрывающий все принятые для продукта актуальные полезные outcomes
  конкурентов. Это scope claim, а не заявление, что все 62 реализованы или verified.

### Реестр повторного аудита от 1 сентября 2026 года

Семь отдельных review по официальным источникам проверили каждый проект из этого
документа. Их числа нельзя складывать как рейтинг: проекты по-разному группируют
функции. Нормализованный реестр outcomes ниже — полезный результат сравнения.

| Срез проекта | Результат относительно 55 до product decision |
|---|---|
| [ESP32-DIV `main`, release 1.7.0 / flasher 1.7.2](https://github.com/cifertech/ESP32-DIV) | 21 outcome из текущего README покрыт, для 11 наше обещание уже, 17 сознательно исключены; крупнейшие безопасные пробелы — ESB capture/defensive MouseJack и Sub-GHz jamming detection |
| [GhostESP Revival 2.1.1](https://github.com/GhostESP-Revival/GhostESP) | core workflow покрыт, но live Wireshark, глубина defensive/compliance, конкретный decoder inventory, NFC dictionary workflow и accessibility уже или отсутствуют |
| [Bruce 1.16.1](https://github.com/BruceDevices/firmware/releases/tag/1.16.1) | Leshy сильнее в evidence/safety, но нужны решения по PN532 emulation, safe BLE assessment, организации apps, offline verification собственного handshake и явному USB MSC |
| [ESP32 Marauder 1.15.1](https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1) | продуктовый scope 55 шире; SAE capture, detector/Fox Hunt profiles и field POI полезно уточнить в acceptance |
| [Flipper Zero stable 1.4.3 / current official dev](https://github.com/flipperdevices/flipperzero-firmware) | 43 из 55 запланированных outcomes Leshy равны или шире, 12 уже — в основном зрелые IR/Sub-GHz/NFC, companion и extension UX |
| [NEMO 3.2.2](https://github.com/n0xa/m5stick-nemo/releases/tag/v3.2.2) | 52 из 55 равны или шире; physical USB BadUSB inspection, готовый TV profile pack и более широкая упаковка локалей уже |
| [CapibaraZero 0.5.2](https://github.com/CapibaraZero/fw/releases/tag/0.5.2) | архивирован/deprecated и официально мигрировал в Bruce; уникального parity requirement не осталось, поэтому это historical sustainability reference |

#### Безопасные и релевантные outcomes — итоговое решение

`Refine` означает, что пользовательская задача уже входила в исходные 55 и теперь
получила конкретную acceptance. `Accepted` называет новую capability. `Post-1.0`
сохраняет видимость, не расширяя скрыто фиксированную границу из 62 строк.

| ID | Нормализованный outcome конкурентов | Текущее покрытие | Класс |
|---|---|---|---|
| RA-01 | Именованные Airspace profiles, passive WPA3/PMF/SAE compliance, понятная sensitivity и Wi-Fi/BLE/nRF/Sub-GHz jamming warnings | FUNC-44/48/49 | `Refine CAP-048`; profiles, sensitivity и cross-radio warnings получили измеримую acceptance |
| RA-02 | nRF24 ESB packet capture/decode и defensive MouseJack scan | FUNC-12/23/37 дают лишь spectrum и общий фундамент Capture | `Accepted CAP-056/PR-028`; injection — отдельный Owned Lab recipe |
| RA-03 | Flipper-compatible `.sub` и объявленный minimum Sub-GHz decoder inventory | FUNC-30/37/40 | `Refine CAP-030`; portable format и declared inventory измеримы |
| RA-04 | PN532 NDEF/ISO14443-4 emulation, явный erase и bounded dictionary recovery своей метки | FUNC-31/36/40 покрывают read и verified restore | `Accepted CAP-058/PR-030`; conditional hardware и secret minimization обязательны |
| RA-05 | Live USB Wireshark/extcap для Wi-Fi/BLE и read-only screen mirroring | FUNC-26/38/51 экспортируют файлы и общие Actions, но не обещают live stream/pixels | `Accepted CAP-057/PR-029`; read-only, без изменения host network |
| RA-06 | Масштаб шрифта, high contrast, reduced motion, скорость repeat и outdoor/epilepsy-safe presentation | FUNC-04/05 | `Refine CAP-005` |
| RA-07 | Lock overlay, под которым уже запущенный безопасный Capture продолжает работать, а controls/data защищены | FUNC-52 | `Refine CAP-052`; Stop доступен, protected content скрыт |
| RA-08 | Готовый signed IR remote/TV profile pack, multi-button remote UX и favorites | FUNC-29/34/40 | `Refine CAP-034`; поставляется полезный signed corpus |
| RA-09 | Library trash/undo, optional BLE/mobile sync/share, USB Mass Storage и public app catalog | FUNC-25/27/38/41 покрывают local typed data и extension contracts | trash/undo — `Refine CAP-025`; mobile/MSC/catalog — `Post-1.0` |
| RA-10 | Favorite/hide/show apps, startup job, shortcuts и privacy presentation | FUNC-02/05 | organization/startup — `Refine CAP-005`; privacy — CAP-052/059, без deceptive dummy UI |
| RA-11 | Signed offline update с SD вдобавок к browser/OTA/recovery | FUNC-07 | `Refine CAP-007` |
| RA-12 | Per-satellite GPS diagnostics и field POI/notes во время Survey | FUNC-14/50 | `Refine CAP-050` |
| RA-13 | Privacy MAC randomization собственного STA/AP Leshy без клонирования чужой identity | FUNC-46 этого не обещает | `Accepted CAP-059/PR-031`; synthetic identity ephemeral/provenanced |
| RA-14 | Offline wordlist verification собственного Wi-Fi authentication Capture | FUNC-49 заканчивается на classification/export | `Accepted CAP-061/PR-033`; Leshy экспортирует validated canonical `hc22000`, компьютерный companion проверяет curated corpus распространённых/слабых паролей и vendor-default patterns, plaintext match на Leshy не возвращается |
| RA-15 | Отдельно принятые iBeacon, MouseJack fixture injection и targeted handshake-assist recipes | FUNC-55 требует именованных recipes, но не называет их | `Refine CAP-055/056`; target, containment, expiry и Stop обязательны |
| RA-16 | Physical USB-host BadUSB enumeration и optional keyboard-host/relay | FUNC-54 инспектирует packages, а не подключённый USB device | `Accepted CAP-060/PR-032` после VBUS/OTG/current-limit/cleanup qualification |
| RA-17 | Протокол внешних модулей с discovery, heartbeat, checksum, RPC и negotiated transport | base outcome отсутствует | `Post-1.0`; полезно для Leshy2/expansion modules |
| RA-18 | Joined-LAN inventory, U2F и другие безопасные non-radio utilities | сознательно вне radio job | inventory/isolated robustness — `Accepted CAP-062/PR-034`; U2F/general utilities — `Post-1.0` |
| RA-19 | Видимый regulatory domain и каналы 1–14 только когда это законно и поддержано | FUNC-05/42/55 region-aware, но user contract неполон | `Refine CAP-005/042/055`; channel 14 никогда не universal default |

#### Оставшиеся непересматриваемые исключения

Review сократил прежний широкий список отказов до трёх исполнимых продуктовых
границ. Всё полезное, что им соответствует, теперь либо входит в план из 62 строк,
либо явно отложено.

| Исключённое поведение | Почему оно не принимается | Что принято вместо него |
|---|---|---|
| Сохранение реальных submitted credentials, payment identifiers/PIN или эквивалентных secrets | Persistence превращает диагностику в продукт по сбору секретов, создаёт ненужные breach/privacy риски и не добавляет evidence, необходимого для доказательства поведения протокола | Training portal хранит только success/failure; NFC/EMV сохраняет redacted protocol metadata; evidence verification — provenance/result, но не submitted secret |
| Unbounded/indiscriminate active output без selected target/qualified isolated fixture, scope, expiry и physical Stop | Ambient flood/interference не доказывает круг затронутых устройств, не даёт надёжного bounded evidence и не гарантирует cleanup/legal containment | Именованные Owned Lab recipes могут делать targeted handshake assist, identity/iBeacon emulation, MouseJack injection, bounded robustness/crash/interference, IR-camera и isolated LAN tests при machine-checked containment |
| Обход ResourceBroker, Safety Supervisor, watchdog, permission review, expiry, cleanup или physical Stop | Bypass делает недостоверными UI, evidence, leases и emergency stop; подпись или developer mode не превращают uncontrolled hardware access в безопасный | Signed packages и developer workflows используют те же brokered Actions, budgets, audit trail и stop path, что built-in apps |

#### Отложено, а не отвергнуто

Эти outcomes не запрещены; они не входят в знаменатель 1.0 по конкретной причине
очерёдности:

| Отложенный outcome | Почему не в 1.0 | Условие возврата |
|---|---|---|
| Authenticated DIV-to-DIV Peer Link | добавляет pairing, mutual authentication, remote-control authorization, conflict ownership, resumable evidence sync и two-device failure matrix; Live Companion/local HIL уже закрывают более близкие user jobs | два исправных supported DIV, стабильные Action/schema API и reviewed peer threat model |
| Протокол внешних модулей | discovery/heartbeat/checksum/RPC/transport negotiation нельзя честно зафиксировать до появления первого реального expansion module и его power/bus envelope | named module owner, hardware profile и HIL fixture |
| Mobile sync/share | добавляет phone-platform lifecycle, pairing, background permissions и privacy/support, пока USB/local Web уже дают offline export | стабильный companion protocol и владелец поддерживаемого mobile client |
| USB Mass Storage | удобен, но создаёт concurrent filesystem ownership, host-eject, dirty-volume и protected-data exposure, конфликтующие с atomic typed store | доказанный read-only snapshot или exclusive-unmount design с power-cut/eject HIL |
| Public reviewed app catalog | package runtime/signature полезны и входят в 1.0; public discovery добавляет moderation, revocation, hosting и supply-chain operations | стабильные SDK/package ABI, revocation service и review/support owner |
| Cloud/default telemetry или automatic upload | default networking ослабляет offline-first/privacy и создаёт account/credential/retention obligations; явный local WiGLE/export сохраняет выбор пользователя | optional explicit opt-in client с отдельным privacy/retention review |
| Generic SSH/Telnet/VPN/DNS/SMB/SNMP toolbox, U2F и unrelated pocket utilities | по отдельности полезны, но не усиливают evidence chain, перегружают navigation и умножают security/support surfaces | reviewed extensions после стабилизации SDK и подтверждённого user job |
| Games, pets, clocks, QR/media/printer novelties | расходуют flash/RAM/menu/test budget, не усиливая Survey, Capture, analysis или Owned Lab | optional extension после 1.0; никогда не core parity gate |
| Broad ESP32 board matrix | каждая плата умножает pin/display/power/radio/storage/HIL combinations; глубина и честный failure behavior ESP32-DIV ценнее для 1.0 | отдельный profile owner и physical HIL target для каждой платы |
| Deceptive dummy/privacy screen | fake state может ввести owner и automated evidence в заблуждение, не добавляя защиты; реальную privacy уже дают Device Lock overlay и Privacy Identity | отдельной core feature не будет; допустимы только truthful явно маркированные presentation modes |

Чисто аппаратные различия — 125 kHz RFID, iButton, ST25R-specific modes, 5 GHz,
802.15.4, Ethernet, camera, microphone/audio, haptics, FM и LoRa — не считаются
policy rejection. Они остаются unavailable, пока не появится явно поддержанная
assembly.

Матрица не утверждает отсутствия конкретной функции. Она показывает, что является
документированной продуктовой опорой каждого проекта.

## Что 1.x обязан догнать

Для 1.0 недостаточно новой внутренней архитектуры. Пользователь должен получить:

- надёжную установку из браузера, OTA и путь восстановления;
- обнаружение всех штатных модулей ESP32-DIV и честное отображение недоступных;
- стабильные представления списка, карточки объекта, радара/уровня сигнала и
  временной шкалы;
- запись сессий на SD и экспорт в распространённые форматы;
- библиотеку сохранённых сигналов, устройств и сессий;
- функциональный паритет 0.x по IR, NFC, GPS, NRF24 и CC1101 до объявления 1.0;
- документированный формат конфигурации и миграцию между версиями.

## Где 1.x должен выйти вперёд

1. **Единая предметная модель.** Wi-Fi AP, BLE beacon, NRF24-активность,
   Sub-GHz-сигнал, NFC-объект и IR-сигнал становятся наблюдениями внутри Session,
   а не несвязанными структурами каждого экрана.
2. **Cross-radio survey.** Один сценарий показывает активность всех доступных
   приёмников, учитывая невозможность безопасной одновременной работы некоторых
   модулей.
3. **Явное владение ресурсами.** SPI, radio mode, GPIO, память, файловая система и
   дисплей выдаются через broker; конфликт не приводит к скрытой порче состояния.
4. **Данные раньше демонстрации.** Любое наблюдение можно сохранить с временем,
   источником, координатами и параметрами приёма, если они доступны.
5. **Одна семантика действий.** Кнопка на устройстве, CLI и локальный Web UI
   вызывают одну и ту же команду с одинаковой проверкой возможностей и прав.
6. **Безопасное лабораторное воспроизведение.** Пассивные сценарии отделены от
   активных; активные действия требуют контекста, явного подтверждения и
   документированной области законного применения.
7. **Офлайн в основе.** Устройство полностью полезно без аккаунта, облака и
   интернета; companion-интерфейс усиливает, но не разблокирует базовые функции.
8. **Проверяемость.** Логика сценариев тестируется на host, драйверы — через HIL,
   а релиз содержит машинно проверяемый manifest и известный путь rollback.
9. **Двуязычность и доступность.** Русский и английский — один контракт строк;
   темы, контраст, размер текста и управление кнопками учитываются заранее.

## Чего мы сознательно не копируем

- гонку за максимальным числом пунктов меню;
- несколько реализаций одного действия отдельно для UI, CLI и Web UI;
- поддержку десятков плат до стабилизации контракта платформы;
- плагины с неограниченным доступом к GPIO, радио и файловой системе;
- собственные закрытые форматы там, где существует переносимый формат;
- смешивание пассивного мониторинга и активных лабораторных функций в одном
  неразличимом потоке.

## Требования, полученные из анализа

| ID | Требование | Источник давления | Приоритет |
|---|---|---|---|
| CR-001 | Один Action/Command API для UI, CLI, Web UI и автоматизации | GhostESP, Flipper | P0 |
| CR-002 | Session и файлы захвата — первоклассные объекты, а не побочный лог | Marauder, GhostESP | P0 |
| CR-003 | Descriptor приложения, capabilities, permissions и scoped storage | GhostESP, Flipper | P1 |
| CR-004 | Меню и действия строятся по реально обнаруженной аппаратуре | Bruce, разнообразие ESP32-DIV | P0 |
| CR-005 | PCAP и совместимые IR/NFC/Sub-GHz форматы там, где это технически возможно | Marauder, GhostESP, Flipper | P0/P1 |
| CR-006 | Контраст, масштаб текста, управление кнопками и отсутствие цветовой зависимости | GhostESP, Flipper | P1 |
| CR-007 | Полезный офлайн local Web/USB companion без облачной зависимости | GhostESP | P1 |
| CR-008 | Stable/beta каналы, подписанный manifest, проверка и rollback | зрелые release-процессы | P0 |
| CR-009 | Resource leases и безопасная деградация при конфликте модулей | специфика ESP32-DIV | P0 |
| CR-010 | Навигация строится вокруг сценариев и результатов, не вокруг списка драйверов | общий вывод | P0 |

Эти пункты переходят в [требования продукта](PRODUCT_REQUIREMENTS.ru.md) и должны
иметь трассировку до архитектурного решения, теста и критерия приёмки.

## Решение

Работу над 1.x начинаем с трёх параллельных по смыслу, но последовательно
фиксируемых оснований:

1. этот конкурентный срез;
2. карта реальных возможностей и конфликтов аппаратуры ESP32-DIV;
3. пользовательские задачи и эталонные сценарии.

Только после них замораживаются требования 1.0 и границы архитектуры. Первый
реализуемый вертикальный срез — не отдельный драйвер, а **Survey Session**:
обнаружить доступную аппаратуру, собрать пассивные наблюдения, показать их одним
списком, открыть карточку и сохранить сессию.
