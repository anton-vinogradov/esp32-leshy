#!/usr/bin/env python3
"""Generate and verify the compact roadmap shown on the repository front page."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
START_MARKER = "<!-- LESHY-ROADMAP:START -->"
END_MARKER = "<!-- LESHY-ROADMAP:END -->"
PHASES_START_MARKER = "<!-- LESHY-ACTIVE-PHASES:START -->"
PHASES_END_MARKER = "<!-- LESHY-ACTIVE-PHASES:END -->"
FUNCTIONS_START_MARKER = "<!-- LESHY-FUNCTIONS:START -->"
FUNCTIONS_END_MARKER = "<!-- LESHY-FUNCTIONS:END -->"
EXPECTED_STAGES = tuple(f"S{index}" for index in range(9))


@dataclass(frozen=True)
class LanguageConfig:
    readme: Path
    delivery_plan: Path
    status: Path
    heading: str
    now_label: str
    progress: str
    source_note: str
    detailed_status: str
    stage_plan: str
    functionality_map: str
    status_labels: dict[str, str]
    snapshot_fields: tuple[tuple[str, str], ...]
    phases_heading: str
    phase_columns: tuple[str, str, str]
    functions_heading: str
    function_columns: tuple[str, str, str]


CONFIGS = (
    LanguageConfig(
        readme=ROOT / "README.md",
        delivery_plan=ROOT / "docs/v1/DELIVERY_PLAN.md",
        status=ROOT / "docs/v1/STATUS.md",
        heading="Development status and roadmap",
        now_label="Now",
        progress="Stage gates complete: {done} of {total}.",
        source_note=(
            "This front-page snapshot is generated from the authoritative 1.x "
            "documentation; CI rejects it if it drifts."
        ),
        detailed_status="live status and next evidence gate",
        stage_plan="stage outcomes and exit gates",
        functionality_map="complete functionality map",
        status_labels={
            "done": "complete", "active": "in progress",
            "blocked": "blocked", "planned": "later",
        },
        snapshot_fields=(
            ("Current phase", "Current phase"),
            ("Verified checkpoint", "Verified checkpoint"),
            ("Next evidence gate", "Next gate"),
        ),
        phases_heading="Current stage phases",
        phase_columns=("Phase", "Outcome / exit gate", "Status"),
        functions_heading="User functionality",
        function_columns=("Functionality", "Delivery stage", "Status"),
    ),
    LanguageConfig(
        readme=ROOT / "README.ru.md",
        delivery_plan=ROOT / "docs/v1/DELIVERY_PLAN.ru.md",
        status=ROOT / "docs/v1/STATUS.ru.md",
        heading="Статус разработки и роадмап",
        now_label="Сейчас",
        progress="Закрыто этапов: {done} из {total}.",
        source_note=(
            "Этот срез главной страницы генерируется из документации-точки-истины "
            "1.x; CI отклоняет рассинхрон."
        ),
        detailed_status="живой статус и ближайший evidence gate",
        stage_plan="результаты и exit gates этапов",
        functionality_map="полная карта функциональности",
        status_labels={
            "done": "готово", "active": "в работе",
            "blocked": "заблокировано", "planned": "дальше",
        },
        snapshot_fields=(
            ("Текущая фаза", "Текущая фаза"),
            ("Проверенный checkpoint", "Проверенный checkpoint"),
            ("Следующий evidence gate", "Следующий gate"),
        ),
        phases_heading="Фазы текущего этапа",
        phase_columns=("Фаза", "Результат / exit gate", "Статус"),
        functions_heading="Пользовательские возможности",
        function_columns=("Возможность", "Этап поставки", "Статус"),
    ),
)


def parse_stage_names(path: Path) -> dict[str, str]:
    matches = re.findall(
        r"^## (S\d+)\s+[—-]\s+(.+?)\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    names = dict(matches)
    if (len(matches) != len(EXPECTED_STAGES) or
            tuple(sorted(names, key=lambda stage: int(stage[1:]))) != EXPECTED_STAGES):
        raise ValueError(f"{path}: expected stage headings S0…S8, got {sorted(names)}")
    return names


def parse_stage_states(path: Path) -> dict[str, str]:
    matches = re.findall(
        r"^\| (S\d+) \| `([^`]+)` \|",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    states = dict(matches)
    if (len(matches) != len(EXPECTED_STAGES) or
            tuple(sorted(states, key=lambda stage: int(stage[1:]))) != EXPECTED_STAGES):
        raise ValueError(f"{path}: expected stage states S0…S8, got {sorted(states)}")
    unknown = sorted(
        set(states.values()) - {"done", "active", "blocked", "planned"})
    if unknown:
        raise ValueError(f"{path}: unsupported stage states {unknown}")
    active = [stage for stage, state in states.items() if state == "active"]
    if len(active) != 1:
        raise ValueError(f"{path}: expected one active stage, got {active}")
    return states


def parse_active_phases(config: LanguageConfig,
                        active_stage: str) -> list[tuple[str, str, str]]:
    text = config.status.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(PHASES_START_MARKER)}(.*?){re.escape(PHASES_END_MARKER)}",
        re.DOTALL,
    )
    blocks = pattern.findall(text)
    if len(blocks) != 1:
        raise ValueError(
            f"{config.status}: expected exactly one active-phase table")
    rows = re.findall(
        rf"^\| ({re.escape(active_stage)}\.\d+) \| (.+?) \| `([^`]+)` \|$",
        blocks[0], re.MULTILINE)
    if not rows:
        raise ValueError(f"{config.status}: active-phase table is empty")
    expected_ids = [
        f"{active_stage}.{index}" for index in range(1, len(rows) + 1)]
    actual_ids = [row[0] for row in rows]
    if actual_ids != expected_ids:
        raise ValueError(
            f"{config.status}: expected sequential phases {expected_ids}, "
            f"got {actual_ids}")
    unknown = sorted(
        {row[2] for row in rows} - {"done", "active", "blocked", "planned"})
    if unknown:
        raise ValueError(f"{config.status}: unsupported phase states {unknown}")
    active = [row[0] for row in rows if row[2] == "active"]
    if len(active) != 1:
        raise ValueError(
            f"{config.status}: expected one active phase, got {active}")
    return rows


def parse_snapshot(config: LanguageConfig,
                   active_phase: str) -> list[tuple[str, str]]:
    text = config.status.read_text(encoding="utf-8")
    snapshot: list[tuple[str, str]] = []
    for source_label, display_label in config.snapshot_fields:
        matches = re.findall(
            rf"^- \*\*{re.escape(source_label)}:\*\* (.+?)\s*$",
            text,
            re.MULTILINE,
        )
        if len(matches) != 1:
            raise ValueError(
                f"{config.status}: expected exactly one {source_label!r} field"
            )
        value = matches[0]
        if "](" in value:
            raise ValueError(
                f"{config.status}: front-page field must not contain relative links"
            )
        snapshot.append((display_label, value))
    if active_phase not in snapshot[0][1]:
        raise ValueError(
            f"{config.status}: current phase must match active {active_phase}"
        )
    return snapshot


def parse_functionality(config: LanguageConfig) -> list[tuple[str, str, str, str]]:
    text = config.status.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(FUNCTIONS_START_MARKER)}(.*?){re.escape(FUNCTIONS_END_MARKER)}",
        re.DOTALL,
    )
    blocks = pattern.findall(text)
    if len(blocks) != 1:
        raise ValueError(
            f"{config.status}: expected exactly one functionality table")
    rows = re.findall(
        r"^\| (FUNC-\d{2}) \| (.+?) \| (.+?) \| `([^`]+)` \|$",
        blocks[0], re.MULTILINE)
    if not rows:
        raise ValueError(f"{config.status}: functionality table is empty")
    expected_ids = [f"FUNC-{index:02d}" for index in range(1, len(rows) + 1)]
    actual_ids = [row[0] for row in rows]
    if actual_ids != expected_ids:
        raise ValueError(
            f"{config.status}: expected sequential functionality IDs "
            f"{expected_ids}, got {actual_ids}")
    unknown = sorted(
        {row[3] for row in rows} - {"done", "active", "blocked", "planned"})
    if unknown:
        raise ValueError(
            f"{config.status}: unsupported functionality states {unknown}")
    return rows


def render(config: LanguageConfig) -> str:
    names = parse_stage_names(config.delivery_plan)
    states = parse_stage_states(config.status)
    active = next(stage for stage in EXPECTED_STAGES if states[stage] == "active")
    phases = parse_active_phases(config, active)
    functionality = parse_functionality(config)
    active_phase = next(row[0] for row in phases if row[2] == "active")
    snapshot = parse_snapshot(config, active_phase)
    done = sum(state == "done" for state in states.values())
    icon = {"done": "✅", "active": "🟡", "blocked": "🔴", "planned": "⬜"}

    lines = [
        START_MARKER,
        f"## {config.heading}",
        "",
        f"> **{config.now_label}: {active} — {names[active]}**",
        ">",
        f"> {config.progress.format(done=done, total=len(EXPECTED_STAGES))}",
        "",
        config.source_note,
        "",
    ]
    for label, value in snapshot:
        lines.append(f"- **{label}:** {value}")
    phase, outcome, status = config.phase_columns
    lines.extend((
        "",
        f"### {config.phases_heading}",
        "",
        f"| {phase} | {outcome} | {status} |",
        "|---|---|---|",
    ))
    for phase_id, phase_outcome, phase_state in phases:
        lines.append(
            f"| {phase_id} | {phase_outcome} | "
            f"{icon[phase_state]} {config.status_labels[phase_state]} |")
    function, delivery, function_status = config.function_columns
    lines.extend((
        "",
        f"### {config.functions_heading}",
        "",
        f"| {function} | {delivery} | {function_status} |",
        "|---|---|---|",
    ))
    for _function_id, label, stage, state in functionality:
        lines.append(
            f"| {label} | {stage} | "
            f"{icon[state]} {config.status_labels[state]} |")
    lines.extend(("", "### Roadmap" if config.readme.name == "README.md"
                  else "### Роадмап", ""))
    for stage in EXPECTED_STAGES:
        state = states[stage]
        lines.append(
            f"- {icon[state]} **{stage} — {names[stage]}** · {config.status_labels[state]}"
        )
    lines.extend((
        "",
        f"[{config.detailed_status}]({config.status.relative_to(ROOT).as_posix()}) · "
        f"[{config.stage_plan}]({config.delivery_plan.relative_to(ROOT).as_posix()}) · "
        f"[{config.functionality_map}]({config.delivery_plan.relative_to(ROOT).as_posix()}#"
        + ("product-functionality-map" if config.readme.name == "README.md" else
           "карта-функциональности-продукта")
        + ")",
        END_MARKER,
    ))
    return "\n".join(lines)


def replace_block(text: str, block: str, path: Path) -> str:
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise ValueError(f"{path}: expected exactly one generated roadmap block")
    return pattern.sub(block, text)


def drift_errors() -> list[str]:
    errors: list[str] = []
    try:
        phase_shapes = []
        function_shapes = []
        for config in CONFIGS:
            states = parse_stage_states(config.status)
            active = next(
                stage for stage in EXPECTED_STAGES
                if states[stage] == "active")
            phase_shapes.append([
                (phase_id, state) for phase_id, _outcome, state
                in parse_active_phases(config, active)
            ])
            function_shapes.append([
                (function_id, stage, state)
                for function_id, _label, stage, state
                in parse_functionality(config)
            ])
        if phase_shapes[0] != phase_shapes[1]:
            errors.append(
                "EN/RU active-phase IDs or states differ in canonical STATUS")
        if function_shapes[0] != function_shapes[1]:
            errors.append(
                "EN/RU functionality IDs, stages or states differ in canonical STATUS")
    except (OSError, ValueError) as error:
        errors.append(str(error))
    for config in CONFIGS:
        try:
            current = config.readme.read_text(encoding="utf-8")
            expected = replace_block(current, render(config), config.readme)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        if current != expected:
            errors.append(
                f"{config.readme.relative_to(ROOT)} roadmap is stale; "
                "run: python3 tools/readme_roadmap.py --write"
            )
    return errors


def write_blocks() -> None:
    for config in CONFIGS:
        current = config.readme.read_text(encoding="utf-8")
        updated = replace_block(current, render(config), config.readme)
        config.readme.write_text(updated, encoding="utf-8")
        print(f"updated {config.readme.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="update both README files")
    args = parser.parse_args()
    if args.write:
        write_blocks()
        return 0

    errors = drift_errors()
    if errors:
        print("front-page roadmap check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("front-page roadmap check passed: README matches canonical STATUS/DELIVERY_PLAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
