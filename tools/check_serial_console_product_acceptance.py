#!/usr/bin/env python3
"""Static product-wiring gate for CAP-053 Serial Console."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
BOARD = ROOT / "firmware/leshy1/src/boards/esp32_div_v2/BoardProfile.h"
UI = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
CONTROLLER = ROOT / "firmware/leshy1/src/ui/UiController.cpp"


def require(text: str, token: str, label: str) -> None:
    if token not in text:
        raise SystemExit(f"FAIL: missing {label}: {token}")


def main() -> int:
    entry = ENTRY.read_text(encoding="utf-8")
    board = BOARD.read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")

    require(entry, "ArduinoSerialConsoleEndpoint\n    serialConsoleEndpoint(Serial1);",
            "dedicated UART1 endpoint")
    require(entry, "handleActionsCliCommand(reply, command)",
            "shared Actions CLI route")
    require(entry, "serviceSerialConsoleAction();", "bounded loop service")
    require(entry, "kSerialConsolePage = 13", "product page")
    require(entry,
            "kPowerPage, 5, kConnectivityPage, kDeviceLockPage,",
            "Device menu route")
    require(entry, "kSerialConsolePage, kAboutPage,",
            "Serial Console Device route")
    require(entry, "serialConsoleActionDispatcher.invoke(",
            "typed dispatcher execution")
    require(entry, "serialConsoleEndpoint.cancel();", "cleanup path")
    require(entry, "serialConsoleLiveLine.size()", "bounded live preview")
    require(entry, "SerialConsoleConflictSafe", "fail-closed stock UI")
    require(board, "kExternalMux56UartDeclared = false",
            "stock profile UART exclusion")
    require(board, "kRfShieldDeclared = true", "stock RF declaration")
    require(ui, "DeviceSerialConsole", "Device menu label")
    require(ui, "SERIAL NOT STARTED / PINS UNTOUCHED",
            "truthful conflict copy")
    require(controller, 'case 13: return "serial_console";',
            "HIL-visible page name")

    if "serialConsoleEndpoint(Serial0)" in entry:
        raise SystemExit("FAIL: Serial Console must not consume diagnostic UART0")
    print("Serial Console product acceptance passed: Device route, stock mux "
          "conflict, typed execution, bounded UART1 and cleanup are wired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
