# Developing ESP32-Leshy

Everything you need to build, flash, run and release the firmware. Русская версия — [DEVELOPING.ru.md](DEVELOPING.ru.md).

Hardware: **ESP32-DIV v2** (ESP32-S3 + CP2102 USB-serial). Toolchain: **PlatformIO**
(`pio` lives at `~/.platformio/penv/bin/pio`, it is not on `PATH`).

---

## One-click in CLion

The repo ships shared run configurations (`.idea/runConfigurations/*.xml`). After
**VCS → Update Project** they appear in the run dropdown (top-right); pick one and
press the green ▶ (or `⌘R`). Each wraps a small script in `tools/` that sets `PATH`
and the working directory for you.

| Button | Script | What it does |
|--------|--------|--------------|
| **Build** | `tools/build.sh` | Compile only (`pio run`). |
| **Deploy to device** | `tools/deploy.sh` | Build + flash over USB. **Upload only** — the serial port is released the instant flashing ends. |
| **Monitor (serial)** | `tools/monitor.sh` | Serial monitor at 115200. Holds the port until you stop it (red ■). |
| **Release (tag + CI)** | `tools/release.sh` | Tag `HEAD` and push → CI builds and publishes (see [Releasing](#releasing)). |

One-time, for code completion / navigation (does not affect the buttons):

```bash
~/.platformio/penv/bin/pio project init --ide clion
```

## From the command line

The scripts are usable straight from a terminal, and so are the raw commands:

```bash
tools/build.sh        # or: pio run
tools/deploy.sh       # or: pio run -t upload
tools/monitor.sh      # or: pio device monitor -b 115200
```

## Everyday loop

1. Edit code.
2. **Deploy to device** (`⌘R`) — flashes, port is free again.
3. **Monitor (serial)** when you want logs.

Only one program can own the serial port at a time. **Stop the Monitor (■) before
re-flashing or using the web installer** — otherwise the next connect fails with a
busy / “Failed to initialize” error.

## Serial remote commands

Type these into the Monitor to drive the device over USB:

- **Navigation:** `u` `d` `l` `r` (up/down/left/right), `o` (OK/select), `menu` (home).
- **Wi-Fi / BLE:** `s` or `scan`, `ble`, `hidden`, `conn`, `deauth`.
- **Spectrum / airtime:** `chan`, `air`, `nrf` (NRF24 2.4 GHz), `cc` (CC1101 Sub-GHz).
- **Update / legal:** `ota`, `legal`.
- **Settings:** `leds`, `ledbr` (LED brightness), `bl` (screen backlight).
- **Diagnostics / dev:** `stat` (heap/status), `nrfdiag`, `otafail`, `legalreset`.

## Flashing a fresh board (web installer)

For a board without the toolchain, use the browser installer:
**https://anton-vinogradov.github.io/esp32-leshy/** (Chrome / Edge / Opera, over https).

The ESP32-DIV routes flashing through a CP2102, whose auto-reset is unreliable from
Web Serial — so you must enter download mode by hand. Buttons on the board:
**BOOT — top-left, RESET — top-right** (the third, bottom-right, is power).

1. **Hold BOOT and keep holding it.**
2. Click **Install**, pick port `cu.usbserial-0001`.
3. **Release BOOT only once the progress bar starts moving.**

If it still won’t connect, add a RESET tap while BOOT is held (BOOT → RESET → release
RESET, keep BOOT down), then Install. For your own board you don’t need any of this —
**Deploy to device** resets and flashes on its own.

## Releasing

`tools/release.sh` (or the **Release** button) tags `HEAD` and pushes the tag:

```bash
tools/release.sh          # auto-bumps the patch: v0.4.2 -> v0.4.3
tools/release.sh v0.5.0   # explicit version for a minor/major
```

CI (`.github/workflows/release.yml`) then bakes the version into `src/core/version.h`,
builds, and publishes a GitHub release with two assets:

- `firmware.bin` — OTA image (devices fetch it via **Settings → Update**).
- `firmware.factory.bin` — full image for the web installer.

The Pages workflow refreshes the installer site with the newest factory image.

## Hardware quick reference

- **MCU:** ESP32-S3. **USB-serial:** CP2102 → `/dev/cu.usbserial-0001`.
- **Radios (FSPI, SCK 12 / MISO 13 / MOSI 11):** 3× NRF24 (2.4 GHz) + CC1101 (Sub-GHz).
- **Display:** ILI9341 on HSPI. **Backlight:** GPIO7 (PWM). **Status LEDs:** GPIO1, 4× WS2812.

More detail lives in `platformio.ini` and the source under `src/`.
