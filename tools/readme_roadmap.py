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
        status_labels={"done": "complete", "active": "in progress", "planned": "later"},
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
        status_labels={"done": "готово", "active": "в работе", "planned": "дальше"},
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
    unknown = sorted(set(states.values()) - {"done", "active", "planned"})
    if unknown:
        raise ValueError(f"{path}: unsupported stage states {unknown}")
    active = [stage for stage, state in states.items() if state == "active"]
    if len(active) != 1:
        raise ValueError(f"{path}: expected one active stage, got {active}")
    return states


def render(config: LanguageConfig) -> str:
    names = parse_stage_names(config.delivery_plan)
    states = parse_stage_states(config.status)
    active = next(stage for stage in EXPECTED_STAGES if states[stage] == "active")
    done = sum(state == "done" for state in states.values())
    icon = {"done": "✅", "active": "🟡", "planned": "⬜"}

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
