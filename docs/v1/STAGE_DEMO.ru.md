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
| DEMO-S2 | Независимая платформа и UX/UI baseline | boot → capability Home → Diagnostics → disabled reason → Back | clean target, real hardware probe, единые Actions, базовый visual system, zero leaked leases |
| DEMO-S3 | Первая сохраняемая Survey Session | Start passive Wi-Fi → List → Detail → Stop → reboot → Library → export | первый реальный end-to-end product workflow и atomic persistent storage |
| DEMO-S4 | Cross-radio passive Session | несколько совместимых receivers → timeline/radar → degradation → reopen/export | общая модель Observation, scheduler/duty cycle и 8-hour passive stability |
| DEMO-S5 | Полнота штатного hardware | probe каждого present module → observe/capture → Library → inspect/export; approved replay отдельно | аппаратный паритет, optional/degraded behavior и recovery/power safety |
| DEMO-S6 | Targets, compare и companion | baseline Session → повторный проход → diff/Target evidence → local companion export | главные продуктовые отличия и одна Action/schema boundary |
| DEMO-S7 | Safe Lab и SDK | saved Capture → Lab confirm → bounded TX → timeout/panic; sample extension | feature-complete 1.0, физический stop и расширяемость без обхода policy |
| DEMO-S8 | Release candidate | install/update → mixed field workflow → interrupted update/write → rollback/recovery | release-complete binary, provenance, endurance и recovery |

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
