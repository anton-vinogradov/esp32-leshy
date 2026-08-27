#!/usr/bin/env python3
"""Fail closed unless sticky esp-netif memory is admitted by Targets."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
SERVICE = (
    ROOT / "firmware/leshy1/src/platform/arduino/"
    "ArduinoCompanionWebService.cpp"
)
PLATFORMIO = ROOT / "firmware/leshy1/platformio.ini"


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    try:
        entry = ENTRY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        platformio = PLATFORMIO.read_text(encoding="utf-8")
    except OSError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    require(
        'LESHY1_VERSION=\\"0.197.0-survey-bounded-ble\\"'
        in platformio,
        "current bounded-BLE version is missing", failures)
    require("const esp_err_t error = esp_netif_deinit();" not in service,
            "unsupported esp_netif_deinit must not be called", failures)
    require("process-lifetime" in service and
            "sticky core" in service,
            "sticky network-core contract is undocumented", failures)

    helper = entry.find("bool admitTargetsWithStickyNetworkCore()")
    loader = entry.find("bool loadTargetsProduct(const AppMenuItem& item)")
    release = entry.find("void releaseTargetsProduct()")
    require(helper >= 0 and loader > helper and release >= 0,
            "post-Web admission/release functions are missing", failures)
    if helper >= 0 and loader > helper:
        helper_body = entry[helper:loader]
        require("arduinoCompanionWebService.networkCoreReady()" in helper_body,
                "admission does not detect sticky network core", failures)
        require("suspendProductSurveyWorkerForWebCompanion()" in helper_body,
                "admission does not reclaim the idle worker", failures)
        load_prefix = entry[loader:entry.find("if (item.simulated)", loader)]
        require("releaseTargetsProduct();" in load_prefix and
                "admitTargetsWithStickyNetworkCore()" in load_prefix,
                "Targets does not admit sticky-core memory before loading",
                failures)
        require(load_prefix.find("releaseTargetsProduct();") <
                load_prefix.find("admitTargetsWithStickyNetworkCore()"),
                "Targets admission runs before prior foreground cleanup",
                failures)
        require('post_web_memory_admission_failed' in load_prefix,
                "failed post-Web admission is not visible", failures)
        load_body = entry[loader:entry.find(
            "bool rebuildTargetsProductFromCatalog", loader)]
        require("targetStateWorkspace = acquireTargetsStoreCodecWorkspace();"
                in load_body,
                "post-Web load still allocates a second target codec",
                failures)
        require("new (std::nothrow)\n"
                "                    leshy1::storage::"
                "TargetDecisionStateStoreWorkspace();" not in load_body,
                "post-Web load still heap-allocates the target codec",
                failures)
        require(load_body.count(
                    "releaseTargetsStoreCodecWorkspace(targetStateWorkspace);")
                >= 4,
                "post-Web load does not release the shared codec on every "
                "terminal path", failures)
        require("acquireTargetsAdmissionScratch()" in entry and
                "controller.loadWithAdmissionScratch(" in entry and
                "releaseTargetsAdmissionScratch(scratch);" in entry,
                "post-Web admission still heap-allocates its scratch catalog",
                failures)
    if release >= 0:
        release_body = entry[release:entry.find(
            "bool finishTargetsProductAllocation", release)]
        require("restoreProductSurveyWorkerAfterWebCompanion()" in release_body,
                "Targets teardown does not restore the idle worker", failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "post-Web memory contract passed: unsupported netif deinit avoided; "
        "Targets admits sticky-core memory and reuses static codec/scratch RAM"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
