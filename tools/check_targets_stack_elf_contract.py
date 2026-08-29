#!/usr/bin/env python3
"""Reject exact product ELFs with unsafe Targets loop-task stack frames."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


LIMITS = {
    "TargetsController::reset()": 512,
    # 0.155.3 proved that a 752-byte frame can trip loopTask's canary once
    # correlation review adds its callees. Preserve the previously measured
    # 416-byte product envelope instead of accepting a merely local frame.
    "TargetsController::loadBindings(": 512,
    # Enforce the complete proposal call chain that 0.155.4 reached for the
    # first time with a real cross-radio fixture. A 2,704-byte aggregate reset
    # previously inflated this review frame to 3,424 bytes and tripped the
    # loopTask canary before the proposal could be rendered.
    "buildSessionCorrelationReview(": 1024,
    "CorrelationService::propose(": 768,
    "TargetsController::loadComparisonSide(": 512,
    "TargetsController::comparisonItemBefore(": 768,
    "TargetsController::rebuildComparisonOrder()": 512,
    "resetTargetComparisonResult(": 128,
    "compareTargetSessionsInto(": 512,
    "buildSide(": 1536,
    # Opening Targets decodes persisted state on Arduino's bounded loop-task
    # stack. Each fixed-capacity record must live in its own small frame, and a
    # merge record (two complete Target snapshots) is decoded directly into an
    # invisible history slot instead of becoming a ~3 KiB local temporary.
    "decodeTargetState(": 256,
    "decodeRecord(": 256,
    "decodeCorrelationFeature(": 256,
    "decodeCorrelationProposal(": 256,
    "decodeCorrelationDecision(": 256,
    "decodeTargetMerge(": 256,
    "decodeAndRestoreTarget(": 1024,
    "decodeAndRestoreDecision(": 768,
    "decodeAndRestoreMerge(": 512,
    "TargetMergeHistory::commitPersistenceRestore()": 512,
    "validateTargetRecord(": 512,
    "validateTargetRecordCompatibility(": 256,
    # 0.163 reached the real merge for the first time and panicked in an
    # unchecked ~11-KiB local TargetCatalog rebuild.  Merge/split now validate
    # and compact/expand the retained catalog in place; cover both public
    # operations and their bounded catalog transactions in the exact ELF.
    "TargetMergeHistory::merge(": 3072,
    "TargetMergeHistory::split(": 2048,
    "TargetCatalog::replaceAndRemove(": 1024,
    "TargetCatalog::replaceAndInsert(": 768,
    "TargetCatalog::clear()": 128,
    "CorrelationDecisionLog::clear()": 128,
    "TargetMergeHistory::clear()": 128,
    "reopenTargetState(": 512,
    "loadTargetsProduct(": 1024,
    # The isolated merge/split gate is still product code: loading it nests
    # under the bounded Arduino loop task, while mutation owns an explicit
    # 12-KiB worker stack. Keep both concrete ELF frames under review.
    "loadTargetsMergeFixture(": 1536,
    "targetsStoreSupervisedCheckpoint()": 256,
    "runTargetsMergeFixtureMutationWorker(": 2048,
}


def tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    fallback = (Path.home() / ".platformio/packages/"
                "toolchain-xtensa-esp-elf/bin" / name)
    if fallback.is_file():
        return str(fallback)
    raise FileNotFoundError(name)


def stack_frames(elf: Path) -> dict[str, int]:
    disassembly = subprocess.run(
        [tool("xtensa-esp32s3-elf-objdump"), "-d", "-C", str(elf)],
        check=True, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    frames: dict[str, int] = {}
    for label, limit in LIMITS.items():
        headers = [line for line in disassembly.splitlines()
                   if line.endswith(">:") and label in line]
        if len(headers) != 1:
            raise ValueError(
                f"expected one Targets stack symbol {label!r}, found {len(headers)}")
        start = disassembly.index(headers[0])
        body = disassembly[start:start + 600]
        match = re.search(r"\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)", body)
        if match is not None:
            frame = int(match.group(1), 0)
        else:
            # Binutils can mark an otherwise valid local function as data
            # after linker relaxation. In that case `objdump -d` prints raw
            # four-byte groups even though the FUNC symbol starts with the
            # canonical three-byte Xtensa ENTRY encoding. Decode only that
            # exact opcode from the symbol address; all other cases remain
            # fail closed.
            address_match = re.match(r"([0-9a-f]+)\s+<", headers[0])
            if address_match is None:
                raise ValueError(f"stack entry not found for {label}")
            address = int(address_match.group(1), 16)
            raw = subprocess.run(
                [tool("xtensa-esp32s3-elf-objdump"), "-s",
                 f"--start-address={address:#x}",
                 f"--stop-address={address + 4:#x}", str(elf)],
                check=True, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
            octets_match = re.search(
                rf"^\s*{address:x}\s+([0-9a-f]{{8}})", raw,
                re.MULTILINE)
            if octets_match is None:
                raise ValueError(f"stack entry not found for {label}")
            octets = bytes.fromhex(octets_match.group(1))
            if len(octets) < 3 or octets[0] != 0x36 or \
                    (octets[1] & 0x0f) != 0x01:
                raise ValueError(f"stack entry not found for {label}")
            frame = ((octets[2] << 4) | (octets[1] >> 4)) << 3
        if frame > limit:
            raise ValueError(f"unsafe Targets stack frame {label}: {frame} > {limit}")
        frames[label] = frame
    return frames


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, required=True)
    args = parser.parse_args()
    try:
        frames = stack_frames(args.elf)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1
    print(json.dumps({"schema": "leshy.targets_stack_elf.v1",
                      "status": "pass", "frames": frames}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
