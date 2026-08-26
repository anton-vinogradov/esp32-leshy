#!/usr/bin/env bash
# One-command local candidate gate: host checks, build, one flash, full board UI/RF HIL.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
firmware_dir="$repo_dir/firmware/leshy1"
export PLATFORMIO_CORE_DIR="${LESHY_PLATFORMIO_CORE_DIR:-$repo_dir/work/platformio-core/leshy1}"
pio_bin="${PIO_BIN:-$HOME/.platformio/penv/bin/pio}"
python_bin="${HIL_PYTHON:-$HOME/.platformio/penv/bin/python}"
expected_cid="${LESHY_BOARD_CID:-FE343253440000002000000055019CB7}"
port=""
output=""

while (($#)); do
    case "$1" in
        --port)
            port="$2"
            shift 2
            ;;
        --output)
            output="$2"
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$port" ]]; then
    shopt -s nullglob
    candidate_ports=(/dev/cu.usbmodem*)
    shopt -u nullglob
    if ((${#candidate_ports[@]} != 1)); then
        echo "expected exactly one /dev/cu.usbmodem* device, found ${#candidate_ports[@]}" >&2
        exit 2
    fi
    port="${candidate_ports[0]}"
fi
if [[ ! -e "$port" ]]; then
    echo "serial port does not exist: $port" >&2
    exit 2
fi
if [[ ! -x "$pio_bin" || ! -x "$python_bin" ]]; then
    echo "PlatformIO runtime is unavailable; set PIO_BIN/HIL_PYTHON" >&2
    exit 2
fi

cd "$repo_dir"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "tracked worktree changes must be committed before a candidate gate" >&2
    exit 2
fi
source_commit="$(git rev-parse HEAD)"
short_commit="$(git rev-parse --short=7 HEAD)"
version="$(sed -n 's/.*LESHY1_VERSION=\\"\([^"[:space:]]*\)\\".*/\1/p' "$firmware_dir/platformio.ini")"
if [[ -z "$version" ]]; then
    echo "could not read LESHY1_VERSION" >&2
    exit 2
fi
if [[ -z "$output" ]]; then
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    output="$repo_dir/work/outputs/product-home-${version}-${short_commit}-${stamp}"
fi
if [[ -e "$output" ]]; then
    echo "output already exists: $output" >&2
    exit 2
fi

echo "[1/5] host and retained-evidence checks"
"$repo_dir/tools/test.sh"
echo "[2/5] EN/RU source-of-truth documentation checks"
"$python_bin" "$repo_dir/tools/check_docs.py"
echo "[3/5] reproducible firmware build"
"$pio_bin" run --project-dir "$firmware_dir"
firmware="$firmware_dir/.pio/build/esp32-div-v2-clean/firmware.bin"
if [[ ! -f "$firmware" ]]; then
    echo "build did not produce $firmware" >&2
    exit 2
fi
echo "[4/5] single flash and automatic physical-board workflow"
"$python_bin" "$repo_dir/tools/run_1x_product_home_hil.py" \
    --port "$port" \
    --firmware "$firmware" \
    --expected-version "$version" \
    --expected-cid "$expected_cid" \
    --source-commit "$source_commit" \
    --output "$output" \
    --flash
echo "[5/5] independent artifact and result verification"
"$python_bin" "$repo_dir/tools/check_product_home_run.py" \
    --run "$output" \
    --expected-version "$version" \
    --expected-cid "$expected_cid" \
    --source-commit "$source_commit"

echo "candidate gate PASS: $output"
