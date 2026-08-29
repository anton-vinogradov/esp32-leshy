#!/usr/bin/env python3
"""Fail-closed source contract for the CAP-050 product workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
NATIVE = ROOT / "firmware/leshy1/src/apps/survey/FieldSurveyNativeCsv.cpp"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"FAIL: field survey product contract missing {label}")


def main() -> None:
    entry = ENTRY.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")
    native = NATIVE.read_text(encoding="utf-8")

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
    require(
        entry,
        "shouldAutoPauseFieldVisit(",
        "single-pass field visit policy",
    )
    require(
        entry,
        "productSurveyWorkerFieldVisit =",
        "explicit worker visit mode",
    )
    require(strings, "FieldSurveyCompare", "comparison label")
    require(strings, "FieldSurveyNewSeenFormat", "revisit summary")
    require(strings, "FieldSurveyNoComparison", "incomplete disclosure")
    require(entry, "openCurrentFieldSurveyExport();", "result-to-Library route")
    require(
        entry,
        "library.field-survey.export.native",
        "bounded native Library export command",
    )
    require(
        entry,
        "library.field-survey.export.wigle",
        "bounded WiGLE Library export command",
    )
    require(entry, "formatFieldSurveyWigleMetadata(", "WiGLE 1.6 stream")
    require(entry, "trustedSurveyContext()", "persisted trusted context")
    require(entry, "trusted_utc\\\":%s", "truthful UTC state")
    require(entry, "trusted_location\\\":%s", "truthful location state")
    require(entry, "upload_ready\\\":%s", "derived upload readiness")
    require(entry, "gps_nmea", "explicit trusted source")
    require(native, "entity_kind,identity,label", "native evidence columns")
    require(native, "first_seen_monotonic_us", "native first-seen evidence")
    require(native, "latest_rssi_dbm", "native latest signal evidence")
    require(strings, "FieldSurveyNativeReady", "native-ready label")
    require(strings, "FieldSurveyWigleLocal", "local WiGLE disclosure")
    print("field survey product contract passed")


if __name__ == "__main__":
    main()
