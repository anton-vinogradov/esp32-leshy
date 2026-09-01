#!/usr/bin/env python3
"""Bounded offline verification of explicitly owned Wi-Fi evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable


REPORT_SCHEMA = "leshy.owned_wifi_evidence_verification.v1"
CHECKPOINT_SCHEMA = "leshy.owned_wifi_evidence_checkpoint.v1"
MAX_EVIDENCE_BYTES = 65_536
MAX_RECORDS = 16
MAX_CORPUS_BYTES = 64 * 1024 * 1024
MAX_CANDIDATE_BYTES = 63
MAX_BUDGET_CANDIDATES = 1_000_000
MAX_BUDGET_SECONDS = 3_600.0


class VerificationError(ValueError):
    """The evidence, corpus, checkpoint, or requested run is invalid."""


@dataclass(frozen=True)
class Hc22000Record:
    kind: str
    verifier: bytes
    access_point: bytes
    station: bytes
    ssid: bytes
    authenticator_nonce: bytes = b""
    eapol: bytes = b""
    message_pair: int = 0


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _hex(value: str, name: str, exact_bytes: int | None = None,
         maximum_bytes: int | None = None) -> bytes:
    _require(len(value) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]*", value)
             is not None, f"{name} is not hexadecimal")
    decoded = bytes.fromhex(value)
    if exact_bytes is not None:
        _require(len(decoded) == exact_bytes,
                 f"{name} must be exactly {exact_bytes} bytes")
    if maximum_bytes is not None:
        _require(len(decoded) <= maximum_bytes,
                 f"{name} exceeds {maximum_bytes} bytes")
    return decoded


def parse_record(line: str) -> Hc22000Record:
    fields = line.split("*")
    _require(len(fields) == 9 and fields[0] == "WPA",
             "record is not canonical hc22000")
    kind = fields[1]
    _require(kind in ("01", "02"), "unsupported hc22000 record kind")
    access_point = _hex(fields[3], "access point", exact_bytes=6)
    station = _hex(fields[4], "station", exact_bytes=6)
    ssid = _hex(fields[5], "SSID", maximum_bytes=32)
    _require(bool(ssid), "SSID must not be empty")
    if kind == "01":
        _require(fields[6:] == ["", "", ""],
                 "PMKID record has unexpected trailing fields")
        return Hc22000Record(
            kind=kind,
            verifier=_hex(fields[2], "PMKID", exact_bytes=16),
            access_point=access_point,
            station=station,
            ssid=ssid,
        )

    authenticator_nonce = _hex(
        fields[6], "authenticator nonce", exact_bytes=32)
    eapol = _hex(fields[7], "EAPOL", maximum_bytes=512)
    _require(len(eapol) >= 99, "EAPOL record is too short")
    _require(int.from_bytes(eapol[2:4], "big") + 4 == len(eapol),
             "EAPOL length field differs from the record")
    _require(eapol[81:97] == bytes(16),
             "canonical EAPOL record must have a zeroed MIC field")
    _require(re.fullmatch(r"[0-9a-fA-F]{2}", fields[8]) is not None,
             "message pair must be one byte")
    return Hc22000Record(
        kind=kind,
        verifier=_hex(fields[2], "MIC", exact_bytes=16),
        access_point=access_point,
        station=station,
        ssid=ssid,
        authenticator_nonce=authenticator_nonce,
        eapol=eapol,
        message_pair=int(fields[8], 16),
    )


def read_evidence(path: Path) -> tuple[list[Hc22000Record], str]:
    size = path.stat().st_size
    _require(0 < size <= MAX_EVIDENCE_BYTES,
             "evidence file is empty or exceeds the bounded size")
    raw = path.read_bytes()
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise VerificationError("evidence file is not ASCII") from error
    lines = [line for line in text.splitlines() if line]
    _require(0 < len(lines) <= MAX_RECORDS,
             "evidence must contain 1..16 non-empty records")
    return [parse_record(line) for line in lines], hashlib.sha256(raw).hexdigest()


def _pmk(passphrase: bytes, ssid: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha1", passphrase, ssid, 4096, 32)


def _ptk(pmk: bytes, record: Hc22000Record) -> bytes:
    station_nonce = record.eapol[17:49]
    context = (min(record.access_point, record.station) +
               max(record.access_point, record.station) +
               min(record.authenticator_nonce, station_nonce) +
               max(record.authenticator_nonce, station_nonce))
    label = b"Pairwise key expansion"
    output = bytearray()
    counter = 0
    while len(output) < 64:
        output.extend(hmac.new(
            pmk, label + b"\x00" + context + bytes([counter]),
            hashlib.sha1).digest())
        counter += 1
    return bytes(output[:64])


def verify_candidate(record: Hc22000Record, candidate: bytes) -> bool:
    _require(8 <= len(candidate) <= MAX_CANDIDATE_BYTES,
             "candidate must contain 8..63 bytes")
    pmk = _pmk(candidate, record.ssid)
    if record.kind == "01":
        calculated = hmac.new(
            pmk, b"PMK Name" + record.access_point + record.station,
            hashlib.sha1).digest()[:16]
        return hmac.compare_digest(calculated, record.verifier)

    key_info = int.from_bytes(record.eapol[5:7], "big")
    descriptor_version = key_info & 0x07
    kck = _ptk(pmk, record)[:16]
    if descriptor_version == 1:
        calculated = hmac.new(kck, record.eapol, hashlib.md5).digest()
    elif descriptor_version == 2:
        calculated = hmac.new(kck, record.eapol, hashlib.sha1).digest()[:16]
    else:
        raise VerificationError(
            f"unsupported EAPOL key descriptor version {descriptor_version}")
    return hmac.compare_digest(calculated, record.verifier)


def _sha256_file(path: Path, maximum: int) -> tuple[str, int]:
    size = path.stat().st_size
    _require(0 < size <= maximum,
             "corpus is empty or exceeds the bounded size")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest(), size


def _candidate_lines(source: BinaryIO) -> Iterable[tuple[int, bytes]]:
    for rank, raw in enumerate(source, start=1):
        candidate = raw.rstrip(b"\r\n")
        _require(len(raw) <= MAX_CANDIDATE_BYTES + 2,
                 f"corpus candidate {rank} exceeds 63 bytes")
        _require(b"\x00" not in candidate,
                 f"corpus candidate {rank} contains NUL")
        yield rank, candidate


def _checkpoint_identity(evidence_sha256: str, corpus_sha256: str,
                         corpus_id: str, corpus_version: str) -> dict[str, Any]:
    return {
        "evidence_sha256": evidence_sha256,
        "corpus_sha256": corpus_sha256,
        "corpus_id": corpus_id,
        "corpus_version": corpus_version,
    }


def read_checkpoint(path: Path, identity: dict[str, Any]) -> int:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("checkpoint is unreadable") from error
    expected = {
        "schema", "status", "evidence_sha256", "corpus_sha256",
        "corpus_id", "corpus_version", "next_rank",
        "plaintext_retained", "network_operations",
    }
    _require(isinstance(value, dict) and set(value) == expected,
             "checkpoint fields differ from the contract")
    _require(value["schema"] == CHECKPOINT_SCHEMA and
             value["status"] == "paused" and
             value["plaintext_retained"] is False and
             value["network_operations"] == 0,
             "checkpoint state is invalid")
    for key, expected_value in identity.items():
        _require(value[key] == expected_value,
                 f"checkpoint {key} differs from this run")
    next_rank = value["next_rank"]
    _require(isinstance(next_rank, int) and not isinstance(next_rank, bool) and
             next_rank >= 1, "checkpoint next_rank is invalid")
    return next_rank


def _write_json(path: Path, value: dict[str, Any], replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, sort_keys=True, indent=2) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8") as output:
            output.write(encoded)
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def _checkpoint(path: Path, identity: dict[str, Any], next_rank: int) -> None:
    _write_json(path, {
        "schema": CHECKPOINT_SCHEMA,
        "status": "paused",
        **identity,
        "next_rank": next_rank,
        "plaintext_retained": False,
        "network_operations": 0,
    }, replace=True)


def verify_corpus(*, evidence: Path, corpus: Path, corpus_id: str,
                  corpus_version: str, corpus_class: str,
                  max_candidates: int, max_seconds: float,
                  checkpoint_path: Path | None = None,
                  resume: bool = False,
                  preview_only: bool = False) -> dict[str, Any]:
    _require(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", corpus_id)
             is not None, "corpus id is invalid")
    _require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}",
                          corpus_version) is not None,
             "corpus version is invalid")
    _require(corpus_class in ("common", "vendor_default", "mixed"),
             "corpus class is invalid")
    _require(1 <= max_candidates <= MAX_BUDGET_CANDIDATES,
             "candidate budget is outside 1..1000000")
    _require(0.01 <= max_seconds <= MAX_BUDGET_SECONDS,
             "time budget is outside 0.01..3600 seconds")
    records, evidence_sha256 = read_evidence(evidence)
    corpus_sha256, corpus_bytes = _sha256_file(corpus, MAX_CORPUS_BYTES)
    identity = _checkpoint_identity(
        evidence_sha256, corpus_sha256, corpus_id, corpus_version)
    start_rank = 1
    if resume:
        _require(checkpoint_path is not None and checkpoint_path.exists(),
                 "resume requires an existing checkpoint")
        start_rank = read_checkpoint(checkpoint_path, identity)
    elif checkpoint_path is not None:
        _require(not checkpoint_path.exists(),
                 "checkpoint already exists; use --resume or another path")

    base = {
        "schema": REPORT_SCHEMA,
        "evidence": {
            "sha256": evidence_sha256,
            "records": len(records),
            "record_kinds": sorted({record.kind for record in records}),
        },
        "corpus": {
            "id": corpus_id,
            "version": corpus_version,
            "class": corpus_class,
            "sha256": corpus_sha256,
            "bytes": corpus_bytes,
        },
        "budget": {
            "max_candidates": max_candidates,
            "max_seconds": max_seconds,
            "start_rank": start_rank,
        },
        "privacy": {
            "plaintext_retained": False,
            "raw_evidence_retained": False,
            "identity_linked_leak_corpus_bundled": False,
        },
        "side_effects": {
            "network_operations": 0,
            "device_writes": 0,
            "radio_operations": 0,
        },
    }
    if preview_only:
        return {
            **base,
            "status": "preview",
            "outcome": "not_started",
            "result": {
                "candidates_examined": 0,
                "next_rank": start_rank,
                "matched_rank": None,
                "weakness_class": "not_evaluated",
                "elapsed_ms": 0,
            },
        }

    examined = 0
    next_rank = start_rank
    matched_rank: int | None = None
    outcome = "complete_no_match"
    started = time.monotonic()
    try:
        with corpus.open("rb") as source:
            for rank, candidate in _candidate_lines(source):
                if rank < start_rank:
                    continue
                elapsed = time.monotonic() - started
                if examined >= max_candidates or elapsed >= max_seconds:
                    outcome = "paused_budget"
                    next_rank = rank
                    break
                next_rank = rank + 1
                if 8 <= len(candidate) <= MAX_CANDIDATE_BYTES:
                    examined += 1
                    if all(verify_candidate(record, candidate)
                           for record in records):
                        matched_rank = rank
                        outcome = "weak_password_match"
                        break
            else:
                outcome = "complete_no_match"
    except KeyboardInterrupt:
        outcome = "paused_by_user"

    elapsed_ms = int((time.monotonic() - started) * 1000)
    paused = outcome in ("paused_budget", "paused_by_user")
    if paused:
        _require(checkpoint_path is not None,
                 "a paused run requires a checkpoint path")
        _checkpoint(checkpoint_path, identity, next_rank)
    weakness = {
        "common": "common_password",
        "vendor_default": "vendor_default_password",
        "mixed": "common_or_vendor_default_password",
    }[corpus_class] if matched_rank is not None else "not_found"
    return {
        **base,
        "status": "paused" if paused else "pass",
        "outcome": outcome,
        "result": {
            "candidates_examined": examined,
            "next_rank": next_rank,
            "matched_rank": matched_rank,
            "weakness_class": weakness,
            "elapsed_ms": elapsed_ms,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument(
        "--corpus-class", choices=("common", "vendor_default", "mixed"),
        required=True)
    parser.add_argument("--max-candidates", type=int, default=10_000)
    parser.add_argument("--max-seconds", type=float, default=30.0)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--owned-evidence-confirmed", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.preview_only and not args.owned_evidence_confirmed:
        parser.error("verification requires --owned-evidence-confirmed")
    if not args.preview_only and args.checkpoint is None:
        parser.error("verification requires --checkpoint")
    try:
        report = verify_corpus(
            evidence=args.evidence,
            corpus=args.corpus,
            corpus_id=args.corpus_id,
            corpus_version=args.corpus_version,
            corpus_class=args.corpus_class,
            max_candidates=args.max_candidates,
            max_seconds=args.max_seconds,
            checkpoint_path=args.checkpoint,
            resume=args.resume,
            preview_only=args.preview_only,
        )
        encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
        if args.report is None:
            sys.stdout.write(encoded)
        else:
            _write_json(args.report, report, replace=False)
        return 130 if report["outcome"] == "paused_by_user" else 0
    except (OSError, VerificationError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
