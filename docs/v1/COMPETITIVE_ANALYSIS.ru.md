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

Повторный аудит от 1 сентября отменяет прежнее утверждение, что этот каталог уже
покрывает каждое полезное семейство конкурентов. В актуальных официальных релизах
есть безопасные и релевантные outcomes, для которых замороженный каталог уже,
чем у конкурента, или не содержит покрытия. Пока владелец явно не решит судьбу каждого
кандидата, **55 остаётся фиксированным текущим знаменателем, а не заявлением о
паритете**. Кандидаты и принципиальные исключения учитываются отдельно, без
скрытого расширения существующих строк.

| Семейство из официальных документов конкурентов | Текущее покрытие Leshy | Результат аудита |
|---|---|---|
| Boot probe, capability-aware UI, настройки, питание, диагностика, установка/update/recovery | CAP-001…008, CAP-045…047 | явно покрыто и собрано в более цельный lifecycle |
| Кнопки/touch, стабильная навигация, темы, яркость и доступная обратная связь | CAP-004/005/045 | явно покрыто |
| Session, Capture, Library, целостность SD/LittleFS, переносимые форматы и backup | CAP-009/023…031/040/043/047 | явно покрыто; произвольный raw file manager сознательно не нужен |
| Одна command model для устройства, automation, USB и local Web | CR-001, PR-012, CAP-038/041 | platform contract есть; пользовательского serial monitor/UART bridge нет (`CF-007`) |
| Wi-Fi network/client discovery, vendor/facts, раскрытие hidden name и radar | CAP-010/016/017/044 | явно покрыто |
| Wi-Fi channels, packet monitor, raw frame Capture и PCAP | CAP-023/026/042 | явно покрыто |
| Распознавание EAPOL/PMKID/4-way handshake, focused capture и экспорт `hc22000`/live analysis | только общий raw Capture/PCAP | законченный workflow отсутствует (`CF-002`) |
| Wardriving Wi-Fi AP/station и BLE с GPS track и локальным WiGLE-compatible результатом | CAP-009/011/014/023/026 дают части | законченный field workflow отсутствует (`CF-003`) |
| Passive deauth/PineAP/evil-twin/WPS, tracker/skimmer/drone и jamming-warning views | отдельные observations могут существовать | defensive detection и объяснимый alert workflow отсутствуют (`CF-001`) |
| BLE scan, identity/vendor/service advertisement facts и radar | CAP-011/016/017/044 | явно покрыто |
| BLE raw packet Capture/Wireshark и opt-in GATT/service/characteristic inspection | только общая формулировка sniff/export | raw acceptance нужно уточнить; connected GATT отсутствует (`CF-004`) |
| nRF24/Sub-GHz spectrum, waterfall, finder, RAW/decode/library и bounded replay | CAP-012/013/030/035/037/040 | явно покрыто |
| IR learn/decode/library/replay и переносимые/universal profile packages | CAP-029/034/040 | покрыто общей моделью профилей; TV-B-Gone — профиль, а не отдельная архитектура |
| NFC read/dump/decode, переносимые данные и verified write/restore | CAP-031/036/040 | явно покрыто для declared PN532 assembly |
| Authenticated peer operation, remote receiver/source и обмен two-device evidence | пользовательской возможности нет | отсутствует (`CF-005`) |
| First-run setup, local PIN/lock и защита captures/secrets при потере устройства | secret storage есть, access control нет | отсутствует (`CF-006`) |
| Исполняемые SD apps/scripts, USB/BLE HID и defensive BadUSB inspection | descriptors/SDK есть, runtime/HID outcome нет | отсутствует в 1.0 (`CF-008`) |
| Конкретные authorized Wi-Fi/BLE/nRF Lab recipes | CAP-032/033 задают safety; CAP-034…036 дают только IR/Sub-GHz/NFC actions | набор wireless Lab действий не решён (`CF-009`) |
| Общий LAN discovery, port/service/banner scan, SSH/Telnet, ARP tools и VPN | покрытия нет | соседняя задача network toolkit, сознательно вне текущего core |
| LF RFID/iButton, FM, Zigbee/802.15.4, Ethernet, camera, microphone/audio и printer | штатный ESP32-DIV не имеет нужных assemblies | conditional expansion, не паритет 1.0 |
| Jammers, широкие flood/spam, credential-harvesting portals и disruptive clone/crash actions | покрытия нет | сознательно отклонено как цель feature-count parity |
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
| CF-009 | **Authorized wireless Lab recipes** дают именованные bounded Wi-Fi/BLE/nRF fixture workflows вместо пустой общей TX-оболочки | CAP-032/033 делают TX безопасным, но не определяют существующие wireless experiments | принято как `CAP-055`, `PR-027`, S7; каждый recipe принимается отдельно, без jamming, indiscriminate flood, crash и credential harvest |

### Итог аудита

- **Явно представлены:** полный passive multi-radio foundation, on-device analysis,
  durable evidence, owned-lab пути IR/NFC/Sub-GHz, update, recovery, companion,
  настройки, feedback и extension boundaries.
- **Приняты в 1.x:** `CF-001…CF-004` и `CF-006…CF-009`, теперь
  `CAP-048…CAP-055` с владельцем S7.
- **Явно после 1.0:** `CF-005 Peer Link`.
- **Сознательно не копируются:** broad disruption, social-engineering credential
  capture, generic LAN attack tooling и функции для отсутствующего железа.
- **Scope claim:** проект имеет трассируемый, пока замороженный baseline 1.x из 55
  capabilities. Повторный аудит от 1 сентября завершён, но решения по его
  кандидатам открыты, поэтому это пока не
  утверждение о строгом паритете со всеми актуальными полезными outcomes
  конкурентов и не утверждение, что все 55 уже реализованы или проверены.

### Реестр повторного аудита от 1 сентября 2026 года

Семь отдельных review по официальным источникам проверили каждый проект из этого
документа. Их числа нельзя складывать как рейтинг: проекты по-разному группируют
функции. Нормализованный реестр outcomes ниже — полезный результат сравнения.

| Срез проекта | Результат относительно замороженных 55 |
|---|---|
| [ESP32-DIV `main`, release 1.7.0 / flasher 1.7.2](https://github.com/cifertech/ESP32-DIV) | 21 outcome из текущего README покрыт, для 11 наше обещание уже, 17 сознательно исключены; крупнейшие безопасные пробелы — ESB capture/defensive MouseJack и Sub-GHz jamming detection |
| [GhostESP Revival 2.1.1](https://github.com/GhostESP-Revival/GhostESP) | core workflow покрыт, но live Wireshark, глубина defensive/compliance, конкретный decoder inventory, NFC dictionary workflow и accessibility уже или отсутствуют |
| [Bruce 1.16.1](https://github.com/BruceDevices/firmware/releases/tag/1.16.1) | Leshy сильнее в evidence/safety, но нужны решения по PN532 emulation, safe BLE assessment, организации apps, offline verification собственного handshake и явному USB MSC |
| [ESP32 Marauder 1.15.1](https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1) | продуктовый scope 55 шире; SAE capture, detector/Fox Hunt profiles и field POI полезно уточнить в acceptance |
| [Flipper Zero stable 1.4.3 / current official dev](https://github.com/flipperdevices/flipperzero-firmware) | 43 из 55 запланированных outcomes Leshy равны или шире, 12 уже — в основном зрелые IR/Sub-GHz/NFC, companion и extension UX |
| [NEMO 3.2.2](https://github.com/n0xa/m5stick-nemo/releases/tag/v3.2.2) | 52 из 55 равны или шире; physical USB BadUSB inspection, готовый TV profile pack и более широкая упаковка локалей уже |
| [CapibaraZero 0.5.2](https://github.com/CapibaraZero/fw/releases/tag/0.5.2) | архивирован/deprecated и официально мигрировал в Bruce; уникального parity requirement не осталось, поэтому это historical sustainability reference |

#### Безопасные и релевантные outcomes, ожидающие решения

`Refine` означает, что пользовательская задача уже входит в 55 и её acceptance
можно сделать конкретнее без маскировки другой задачи. `Decision` означает
самостоятельный outcome, который нельзя прятать внутри существующей строки.
`Post-1.0` сохраняет видимость без скрытого расширения release boundary.

| ID | Нормализованный outcome конкурентов | Текущее покрытие | Класс |
|---|---|---|---|
| RA-01 | Именованные Airspace profiles, passive WPA3/PMF/SAE compliance, понятная sensitivity и Wi-Fi/BLE/nRF/Sub-GHz jamming warnings | FUNC-44/48/49 | `Refine`; inventory detectors и evidence semantics входят в текущую acceptance |
| RA-02 | nRF24 ESB packet capture/decode и defensive MouseJack scan | FUNC-12/23/37 дают лишь spectrum и общий фундамент Capture | `Decision`; packet workflow не равен экрану spectrum |
| RA-03 | Flipper-compatible `.sub` и объявленный minimum Sub-GHz decoder inventory | FUNC-30/37/40 | `Refine`; portability и поставляемый inventory должны стать измеримыми |
| RA-04 | PN532 NDEF/ISO14443-4 emulation, явный erase и bounded dictionary recovery своей метки | FUNC-31/36/40 покрывают read и verified restore | `Decision`; emulation и key recovery добавляют отдельную active/security семантику |
| RA-05 | Live USB Wireshark/extcap для Wi-Fi/BLE и read-only screen mirroring | FUNC-26/38/51 экспортируют файлы и общие Actions, но не обещают live stream/pixels | `Decision`; полезно для анализа, поддержки и HIL |
| RA-06 | Масштаб шрифта, high contrast, reduced motion, скорость repeat и outdoor/epilepsy-safe presentation | FUNC-04/05 | `Refine`; завершает уже принятую accessibility-задачу |
| RA-07 | Lock overlay, под которым уже запущенный безопасный Capture продолжает работать, а controls/data защищены | FUNC-52 | `Refine`; нужно определить lifecycle, Stop и privacy semantics |
| RA-08 | Готовый signed IR remote/TV profile pack, multi-button remote UX и favorites | FUNC-29/34/40 | `Refine`; пользователю нужен полезный corpus, а не только package architecture |
| RA-09 | Library trash/undo, optional BLE/mobile sync/share, USB Mass Storage и public app catalog | FUNC-25/27/38/41 покрывают local typed data и extension contracts | trash/undo — `Refine`; mobile/MSC/catalog — `Post-1.0 decision` |
| RA-10 | Favorite/hide/show apps, startup job, shortcuts и privacy/dummy presentation | FUNC-02/05 | `Decision`; организация продукта, а не radio capability |
| RA-11 | Signed offline update с SD вдобавок к browser/OTA/recovery | FUNC-07 | `Refine`; ещё один verified transport той же update-задачи |
| RA-12 | Per-satellite GPS diagnostics и field POI/notes во время Survey | FUNC-14/50 | `Refine`; конкретная полевая acceptance |
| RA-13 | Privacy MAC randomization собственного STA/AP Leshy без клонирования чужой identity | FUNC-46 этого не обещает | `Decision`; privacy benefit с последствиями для provenance |
| RA-14 | Offline wordlist verification собственного Wi-Fi authentication Capture | FUNC-49 заканчивается на classification/export | `Decision`; полезный offline analysis рядом с policy credential recovery |
| RA-15 | Отдельно принятые iBeacon, MouseJack fixture injection и targeted handshake-assist recipes | FUNC-55 требует именованных recipes, но не называет их | `Decision по каждому recipe`; общего разрешения нет |
| RA-16 | Physical USB-host BadUSB enumeration и optional keyboard-host/relay | FUNC-54 инспектирует packages, а не подключённый USB device | `Decision + hardware qualification`; сначала VBUS/OTG/cleanup |
| RA-17 | Протокол внешних модулей с discovery, heartbeat, checksum, RPC и negotiated transport | base outcome отсутствует | `Post-1.0`; полезно для Leshy2/expansion modules |
| RA-18 | Joined-LAN inventory, U2F и другие безопасные non-radio utilities | сознательно вне radio job | `Decision`; отдельная ширина продукта, а не parity по умолчанию |
| RA-19 | Видимый regulatory domain и каналы 1–14 только когда это законно и поддержано | FUNC-05/42/55 region-aware, но user contract неполон | `Refine`; channel 14 никогда не universal default |

#### Нормализованный реестр принципиальных исключений

Это реальные функции конкурентов, а не скрытая незавершённая работа. Они остаются
вне 55, пока владелец явно не изменит product policy.

| Исключённое семейство | Примеры у конкурентов | Причина и принятый tradeoff |
|---|---|---|
| Массовое нарушение радио | Wi-Fi deauth/disassociation/CSA/SAE floods, BLE/nRF/Sub-GHz/RFID jamming | меньше one-button DoS; сохраняются физическая ограничиваемость, предсказуемый cleanup и защищаемое назначение продукта |
| Flood, spam и crash modes | beacon/probe/auth floods, Sour Apple, Apple/Android/Windows pairing spam, BLE crash chains | меньше prank/stress-demo; нет неизбирательного воздействия без durable evidence |
| Credential harvesting и social engineering | Evil Portal/Karma portal, fake login, keystroke/password viewer, Responder/LLMNR interception | нет turnkey phishing lab; Leshy не становится скрытым сборщиком secrets |
| Identity impersonation | AP/STA clone, Karma response, AirTag/drone spoof, Find My sound trigger | меньше тестов proprietary flows; сохраняется provenance и не загрязняются identity ecosystems |
| Unbounded brute force/key recovery | De Bruijn/fixed-code brute force, unrestricted MIFARE nested/hardnested/dictionaries | меньше attack breadth; bounded analysis собственного evidence остаётся отдельным явным решением RA-04/RA-14 |
| Active LAN interference | DHCP starvation, ARP poison/NetCut/MITM и disruption stations | Marauder/Bruce шире как network attack tools; Leshy остаётся evidence-backed radio instrument |
| Unrestricted execution/raw hardware bypass | unsigned BadUSB, raw Wi-Fi TX/GPIO/bus hooks, unrestricted JS/native apps, shell/file manager | меньше сторонняя экосистема на старте; ResourceBroker, scoped storage, signatures и Safety Supervisor остаются enforceable |
| Arbitrary active replay/credential creation | unscoped Sub-GHz remote generation, arbitrary NFC UID/Magic card clone, LF RFID/iButton credentials | меньше universal cloning; поддержанный active path начинается с своего immutable evidence и остаётся bounded/stoppable |
| Извлечение платёжных данных | EMV PAN/expiry readers | исключается privacy-sensitive ниша со слабой связью с основной задачей |
| Помеха ИК-камерам | continuous IR Dazzler/night-vision interference | меньше один эффектный demo; нет намеренного sensor disruption и sustained thermal load |
| Cloud-first публикация и executable marketplace | automatic WiGLE/WDGWars upload, public unreviewed app/script store | меньше one-click sharing/discovery; 1.0 остаётся offline-first и supply-chain controlled, reviewed optional clients возможны позже |
| Generic LAN client/toolbox | port/service scanners, SSH/Telnet, VPN, DNS sinkhole, SMB/SNMP utilities | уже как pocket computer; яснее navigation, test matrix и identity продукта |
| Games/pets/clocks/QR/media/printer utilities | Doom/Ghostchi/Brucegotchi, clocks, music, QR toys, printer/Chromecast tools | меньше novelty; flash/RAM/menu остаются основным jobs |
| Ранняя широкая board matrix | десятки ESP32 targets | меньше аудитория на старте; глубже ESP32-DIV probe, HIL и conflict safety |

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
