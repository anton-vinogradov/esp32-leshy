#!/usr/bin/env python3
"""Fail-closed source contract for the on-device Targets product slice."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    entry = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text()
    catalog = (ROOT / "firmware/leshy1/src/domain/apps/AppCatalog.cpp").read_text()
    strings = (ROOT / "firmware/leshy1/src/ui/UiStrings.def").read_text()
    controller = (ROOT / "firmware/leshy1/src/apps/targets/TargetsController.cpp").read_text()
    comparison = (ROOT / "firmware/leshy1/src/domain/targets/TargetComparison.cpp").read_text()
    comparison_header = (ROOT / "firmware/leshy1/src/domain/targets/TargetComparison.h").read_text()
    comparison_service = (ROOT / "firmware/leshy1/src/services/targets/TargetComparisonService.h").read_text()

    require(failures,
            '"targets", "TARGETS"' in catalog and
            '"saved identities / compare visits"' in catalog and
            "Resource::Storage" in catalog and "Resource::RadioSpi" in catalog,
            "Targets must be a real saved-session Home product with exact leases")
    require(failures,
            "TargetsProductRuntime* targetsProductRuntime = nullptr" in entry and
            "new (std::nothrow) TargetsProductRuntime" in entry and
            "delete targetsProductRuntime" in entry and
            "TargetsWorkspace targets" not in entry,
            "Targets workspace must have foreground-only bounded lifetime")
    require(failures,
            "new (std::nothrow) domain::targets::TargetCatalog" in controller and
            "delete scratch" in controller and
            "TargetCatalog scratch" not in controller,
            "large admission scratch must be transient, checked and released")
    require(failures,
            "compareTargetSessionsInto(" in comparison and
            "new (std::nothrow) ComparisonScratch" in comparison and
            "std::unique_ptr<ComparisonScratch>" in comparison and
            "TargetComparisonResult compareTargetSessions(" not in
                comparison_header and
            "executeInto(" in comparison_service and
            "workspace_.comparison = comparison.execute" not in controller,
            "on-device comparison must use caller-owned result storage and "
            "checked/released heap scratch, never a multi-KiB value return")
    require(failures,
            "openWifiVisitProduct()" in entry and
            "WifiProductView::Visit" in entry and
            "UiTextId::WifiMenuVisit" in entry and
            "wifiProductSelection == 3" in entry,
            "final Wi-Fi menu must expose a public persistent Visit path")
    require(failures,
            "filesystem.beginReadOnly()" in entry and
            "recoverSessionPair(" in entry and
            "loadProductFingerprint(" in entry and
            "fingerprint_mismatch" in entry and
            "targetsBlockedWriteAttempts" in entry,
            "persistent Target reads must be exact-CID, read-only and observable")
    require(failures,
            'std::strcmp(command, "targets.state")' in entry and
            "leshy.targets.product.v1" in entry and
            r'\"write_enabled\":false' in entry,
            "Targets needs a machine-readable release-test state")
    require(failures,
            "renderTargetsPage" in entry and
            "renderTargetListRow" in entry and
            "targetsFirstVisible" in entry and
            "TouchTargetLayout::HomeRows" in entry and
            "controller.openSelected()" in entry,
            "Targets list/detail/compare must share keypad and touch navigation")
    require(failures,
            "selectedIsCompare() ? TargetsView::Compare" in controller and
            "entryCount()" in controller and
            "selectStrongestIdentities" in controller and
            "sourceIdentityCount_ > filter.size" in controller,
            "Compare visits must be reachable as the first ordinary list entry")
    for text_id in ("TargetsCompareVisits", "TargetsLimitedTitleFormat", "TargetsEmpty",
                    "TargetsLoadFailed", "TargetsDetail", "TargetsCompare"):
        require(failures, f"LESHY_UI_TEXT({text_id}," in strings,
                f"bilingual UI string missing: {text_id}")
    for forbidden in ("esp_wifi_80211_tx", "STX", "SFTX", "tone("):
        require(failures, forbidden not in controller,
                f"Targets controller contains forbidden active path: {forbidden}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets product contract passed: read-only exact-CID sessions, "
          "bounded lifecycle, list/detail/compare, keypad/touch, state probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
