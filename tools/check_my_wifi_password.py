#!/usr/bin/env python3
"""Task-first offline check of an owned Wi-Fi network password."""

from __future__ import annotations

import argparse
import json
import locale
import re
import sys
from pathlib import Path
from typing import Any

import owned_wifi_evidence_verifier as verifier


TEXT = {
    "en": {
        "title": "CHECK MY WI-FI PASSWORD",
        "evidence_prompt": "Path to the Wi-Fi check file exported by Leshy: ",
        "corpus_prompt": "Path to your local password list: ",
        "kind_prompt": (
            "What does the local list contain?\n"
            "  1 — common passwords\n"
            "  2 — router/vendor defaults\n"
            "  3 — both\n"
            "Choose 1, 2, or 3: "
        ),
        "purpose": (
            "This checks whether your captured network proof matches one entry "
            "in the local list."
        ),
        "not_claim": (
            "No match does not prove that the password is strong; it only rules "
            "out the checked list."
        ),
        "file": "Leshy file",
        "list": "Local list",
        "records": "usable proofs",
        "limit": "Run limit",
        "limit_value": "{candidates} passwords or {seconds:g} seconds",
        "privacy": (
            "Offline only: no network, radio, device write, or password is added "
            "to the report."
        ),
        "authorization": (
            "Continue only for your own network or one you are explicitly "
            "authorized to test. Type YES to continue: "
        ),
        "cancelled": "Cancelled without starting the check.",
        "checking": "Checking the local list. Press Ctrl-C to pause safely…",
        "match": (
            "RESULT: A weak or default password was found in the selected local "
            "list. Change it in the router and repeat the check."
        ),
        "no_match": (
            "RESULT: No match was found in the checked part of the local list. "
            "This is not proof that the password is strong."
        ),
        "paused": (
            "PAUSED: progress was saved. Run the same command with --resume to "
            "continue from the checkpoint."
        ),
        "report": "Privacy-safe report",
        "preview": "Preview complete. No passwords were checked.",
        "error": "Cannot run the check",
    },
    "ru": {
        "title": "ПРОВЕРКА ПАРОЛЯ МОЕЙ WI-FI СЕТИ",
        "evidence_prompt": "Путь к файлу проверки, экспортированному Лешим: ",
        "corpus_prompt": "Путь к вашему локальному списку паролей: ",
        "kind_prompt": (
            "Что содержит локальный список?\n"
            "  1 — распространённые пароли\n"
            "  2 — заводские пароли роутеров\n"
            "  3 — оба вида\n"
            "Выберите 1, 2 или 3: "
        ),
        "purpose": (
            "Проверка покажет, совпадает ли доказательство вашей сети с одной "
            "из записей локального списка."
        ),
        "not_claim": (
            "Отсутствие совпадения не доказывает надёжность пароля — оно "
            "исключает только проверенную часть выбранного списка."
        ),
        "file": "Файл Лешего",
        "list": "Локальный список",
        "records": "пригодных доказательств",
        "limit": "Ограничение запуска",
        "limit_value": "{candidates} паролей или {seconds:g} секунд",
        "privacy": (
            "Только offline: без сети, радио и записи на устройство; пароль не "
            "попадёт в отчёт."
        ),
        "authorization": (
            "Продолжайте только для своей сети или сети с явным разрешением. "
            "Введите ДА для запуска: "
        ),
        "cancelled": "Проверка отменена до запуска.",
        "checking": (
            "Проверяю локальный список. Ctrl-C безопасно приостановит работу…"
        ),
        "match": (
            "РЕЗУЛЬТАТ: в выбранном локальном списке найден слабый или заводской "
            "пароль. Измените его в настройках роутера и повторите проверку."
        ),
        "no_match": (
            "РЕЗУЛЬТАТ: в проверенной части локального списка совпадений нет. "
            "Это не доказывает надёжность пароля."
        ),
        "paused": (
            "ПАУЗА: прогресс сохранён. Запустите ту же команду с --resume, чтобы "
            "продолжить с контрольной точки."
        ),
        "report": "Приватный отчёт",
        "preview": "Предпросмотр завершён. Пароли не проверялись.",
        "error": "Не удалось выполнить проверку",
    },
}

KINDS = {"1": "common", "2": "vendor_default", "3": "mixed"}


def _language(requested: str) -> str:
    if requested in TEXT:
        return requested
    current = locale.getlocale()[0] or ""
    return "ru" if current.lower().startswith("ru") else "en"


def _path(value: Path | None, prompt: str) -> Path:
    if value is not None:
        return value.expanduser()
    entered = input(prompt).strip()
    if not entered:
        raise verifier.VerificationError("file path is required")
    return Path(entered).expanduser()


def _kind(value: str | None, prompt: str) -> str:
    if value is not None:
        return value
    selected = input(prompt).strip()
    if selected not in KINDS:
        raise verifier.VerificationError("choose local list type 1, 2, or 3")
    return KINDS[selected]


def _corpus_identity(path: Path) -> tuple[str, str]:
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    if not slug:
        slug = "local-list"
    # The verifier adds the exact content SHA-256 to both reports and
    # checkpoints.  Keep the human label stable without reading an unbounded
    # file before the verifier enforces its 64 MiB input limit.
    return f"local-{slug[:48]}", "local-v1"


def _output_paths(directory: Path, evidence_sha256: str,
                  corpus_sha256: str) -> tuple[Path, Path]:
    run_id = f"{evidence_sha256[:8]}-{corpus_sha256[:8]}"
    return (
        directory / f"wifi-password-check-{run_id}.json",
        directory / f"wifi-password-check-{run_id}.checkpoint.json",
    )


def _print_preview(text: dict[str, str], evidence: Path, corpus: Path,
                   preview: dict[str, Any], max_candidates: int,
                   max_seconds: float) -> None:
    print(f"\n{text['title']}\n")
    print(text["purpose"])
    print(text["not_claim"])
    print()
    print(f"{text['file']}: {evidence.name}")
    print(f"  {text['records']}: {preview['evidence']['records']}")
    print(f"{text['list']}: {corpus.name}")
    print(f"{text['limit']}: " + text["limit_value"].format(
        candidates=max_candidates, seconds=max_seconds))
    print(text["privacy"])


def _write_report(path: Path, report: dict[str, Any]) -> None:
    verifier._write_json(path, report, replace=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether evidence from your own Wi-Fi matches a local list "
            "of common or router-default passwords."
        ))
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument(
        "--list-kind", choices=("common", "vendor_default", "mixed"))
    parser.add_argument("--language", choices=("auto", "en", "ru"),
                        default="auto")
    parser.add_argument("--max-candidates", type=int, default=10_000)
    parser.add_argument("--max-seconds", type=float, default=30.0)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--yes-i-am-authorized", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    language = _language(args.language)
    text = TEXT[language]
    try:
        evidence = _path(args.evidence, text["evidence_prompt"])
        corpus = _path(args.corpus, text["corpus_prompt"])
        corpus_class = _kind(args.list_kind, text["kind_prompt"])
        corpus_id, corpus_version = _corpus_identity(corpus)
        preview = verifier.verify_corpus(
            evidence=evidence,
            corpus=corpus,
            corpus_id=corpus_id,
            corpus_version=corpus_version,
            corpus_class=corpus_class,
            max_candidates=args.max_candidates,
            max_seconds=args.max_seconds,
            preview_only=True,
        )
        _print_preview(text, evidence, corpus, preview,
                       args.max_candidates, args.max_seconds)
        if args.preview_only:
            print(f"\n{text['preview']}")
            return 0

        if not args.yes_i_am_authorized:
            answer = input(f"\n{text['authorization']}").strip().upper()
            accepted = answer == ("ДА" if language == "ru" else "YES")
            if not accepted:
                print(text["cancelled"])
                return 2

        output_directory = (args.output_directory or
                            evidence.parent / "leshy-results").expanduser()
        report_path, checkpoint_path = _output_paths(
            output_directory,
            preview["evidence"]["sha256"],
            preview["corpus"]["sha256"])
        if args.resume and not checkpoint_path.is_file():
            raise verifier.VerificationError(
                "saved progress for these exact files was not found")
        if not args.resume and checkpoint_path.exists():
            raise verifier.VerificationError(
                "saved progress already exists; use --resume")

        print(f"\n{text['checking']}")
        report = verifier.verify_corpus(
            evidence=evidence,
            corpus=corpus,
            corpus_id=corpus_id,
            corpus_version=corpus_version,
            corpus_class=corpus_class,
            max_candidates=args.max_candidates,
            max_seconds=args.max_seconds,
            checkpoint_path=checkpoint_path,
            resume=args.resume,
        )
        _write_report(report_path, report)
        if report["outcome"] == "weak_password_match":
            print(f"\n{text['match']}")
        elif report["outcome"] == "complete_no_match":
            print(f"\n{text['no_match']}")
        else:
            print(f"\n{text['paused']}")
        print(f"{text['report']}: {report_path}")
        if report["status"] == "pass" and checkpoint_path.exists():
            checkpoint_path.unlink()
        return 130 if report["outcome"] == "paused_by_user" else 0
    except (OSError, verifier.VerificationError) as error:
        print(f"{text['error']}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
