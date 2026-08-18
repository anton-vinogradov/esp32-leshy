# ESP32-Leshy 1.x — протокол промежуточных Stage Demo

*Read in: [English](STAGE_DEMO.md) · **Русский***

Статус: **обязательный delivery gate для S2…S8**.

Тестирование не откладывается до полной прошивки. Каждый вертикальный slice проходит
host tests и применимый HIL сразу, а этап S2…S8 закрывается только воспроизводимым
Stage Demo на реальной плате. Процент готовности и отдельные unit tests demo не
заменяют.

## Общий пакет demo

Для каждого `DEMO-S*` сохраняются:

1. firmware version, commit/worktree identity, board/profile и dependency lock;
2. сценарий из Home с happy path, error/degraded path и Back/cancel;
3. автоматический serial/action trace и real-TFT captures ключевых состояний;
4. применимые host/unit/integration результаты и firmware size/RAM budgets;
5. HIL результат boot/input/resource cleanup и затронутых физических модулей;
6. известные ограничения без формулировки «готово», если gate ещё открыт;
7. ссылки `CAP-* → PR/NFR-* → WF-* → evidence` в traceability/STATUS.

Оператор нужен только для физического наблюдения, которое нельзя получить с платы
или приборов автоматически. Обычный переход по меню и TFT evidence выполняет UI
automation.

## Demo по этапам

| ID | Что демонстрируется | Минимальный сквозной путь | Что это доказывает |
|---|---|---|---|
| DEMO-S2 | Независимая платформа и UX/UI baseline | boot → capability Home → Self-Test Quick → Diagnostics/disabled reason → report → Back | clean target, real hardware probe, единые Actions, базовый visual system, user-visible automation, zero leaked leases |
| DEMO-S3 | Первая сохраняемая Survey Session | Start passive Wi-Fi → List → Detail → Stop → reboot → Library → export | первый реальный end-to-end product workflow и atomic persistent storage |
| DEMO-S4 | Cross-radio passive Session | несколько совместимых receivers → timeline/radar → degradation → reopen/export | общая модель Observation, scheduler/duty cycle и 8-hour passive stability |
| DEMO-S5 | Полнота штатного hardware | Full/Guided preflight → probe каждого present module → observe/capture → Library → inspect/export; approved replay отдельно | аппаратный паритет, optional/degraded behavior, честные N/A/blocked results и recovery/power safety |
| DEMO-S6 | Targets, compare и companion | baseline Session → повторный проход → diff/Target evidence → local companion export | главные продуктовые отличия и одна Action/schema boundary |
| DEMO-S7 | Safe Lab и SDK | saved Capture → Lab confirm → bounded TX → timeout/panic; sample extension | feature-complete 1.0, физический stop и расширяемость без обхода policy |
| DEMO-S8 | Release candidate | exact candidate → полный Self-Test plan → mixed field workflow → interrupted update/write → rollback/recovery | одинаковые on-device/release checks, independent oracle, release-complete binary, provenance, endurance и recovery |

`DEMO-S2` принят evidence `E-BUILD-060`/`E-AUTO-022`/`E-HIL-082`/`E-GATE-002`.
Exact committed candidate 0.58 выполнил 29 public Action/query steps и совпал с
девятью отдельно записанными real-TFT goldens без расхождений; Quick прошёл 8/8,
safe outputs оставались неактивны, final resource lease равен нулю. Это stage gate
S2, а не release: полный capability coverage остаётся blocked, пока S3…S7 не
зарегистрируют свои checks.

S3 progress `E-AUTO-023`/`E-HIL-083` переиспользует тот же exact candidate 0.58 и
подтверждает real passive product path через live List→Detail→Back, commit generation
65→66, cold read-only reopen, Library и JSON export. Пять TFT states визуально
проверены, final ownership равен нулю. Normal-path evidence с тех пор продвинулся
через 0.60/0.62, а exact 0.68
`E-AUTO-032`/`E-HIL-092` закрывает missing-source real-TFT path без запуска source или
store, записи bytes, изменения прежней Library 68/25, утечки lease или скрытого retry
по Select. Это всё ещё намеренно не `DEMO-S3`: открыты physical power-cut, LittleFS
parity и независимо записанные demo goldens.

## Ритм тестирования внутри этапа

- **При изменении:** быстрые host/static tests и связанные negative cases.
- **При готовности slice:** build, автоматический board smoke, TFT/action evidence и
  resource cleanup.
- **Перед gate:** полный `DEMO-S*`, regression matrix текущих возможностей и review
  открытых рисков/бюджетов.
- **S8:** два последовательных RC проходят один и тот же release packet без
  изменения критериев после результата.

Stage Demo не является маркетинговым роликом: он считается pass только если команды,
логи, бинарный hash и ожидаемые наблюдения позволяют повторить результат.
