#!/usr/bin/env python3
"""Fail-closed source contract for the CAP-050 product workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"FAIL: field survey product contract missing {label}")


def main() -> None:
    entry = ENTRY.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")

    require(entry, '#include "apps/survey/FieldSurveyTracker.h"', "tracker")
    require(entry, "FieldSurveyTracker fieldSurveyTracker;", "bounded state")
    require(
        entry,
        "captureFieldSurveyPrevious(librarySession);",
        "explicit retained baseline capture",
    )
    require(
        entry,
        "? FieldSurveyTracker::kSessionId",
        "field-visit session identity",
    )
    if entry.count("completeFieldSurveyVisit(surveySession);") != 3:
        raise SystemExit(
            "FAIL: field survey result must cover normal/paused commit and HIL negative"
        )
    require(
        entry,
        "fieldSurveyTracker.toggleComparePrevious();",
        "previous/first-visit selection",
    )
    require(entry, "FieldSurveyCatalog fieldSurveyScratch;", "shared scratch")
    require(entry, "releaseFieldSurveyScratch(scratch);", "scratch restore")
    require(
        entry,
        "result.status == FieldSurveyVisitStatus::Incomplete",
        "fail-closed result",
    )
    require(
        entry,
        "survey.field-visit.test-incomplete once",
        "physical incomplete-session negative",
    )
    require(strings, "FieldSurveyCompare", "comparison label")
    require(strings, "FieldSurveyNewSeenFormat", "revisit summary")
    require(strings, "FieldSurveyNoComparison", "incomplete disclosure")
    print("field survey product contract passed")


if __name__ == "__main__":
    main()
