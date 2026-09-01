#!/usr/bin/env python3
"""Tests for bounded owned Wi-Fi evidence verification."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

import owned_wifi_evidence_verifier as verifier


SSID = b"Owned-Fixture"
AP = bytes.fromhex("6466b38ec3fc")
STATION = bytes.fromhex("225edc49b7aa")
ANONCE = bytes(range(32))
SNONCE = bytes(range(32, 64))
PASSPHRASE = b"correct-horse"
HASHCAT_REFERENCE_PMKID = (
    "WPA*01*4d4fe7aac3a2cecab195321ceb99a7d0*fc690c158264*"
    "f4747f87f9f4*686173686361742d6573736964***"
)


def pmk(passphrase: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha1", passphrase, SSID, 4096, 32)


def ptk(passphrase: bytes) -> bytes:
    context = (min(AP, STATION) + max(AP, STATION) +
               min(ANONCE, SNONCE) + max(ANONCE, SNONCE))
    output = bytearray()
    for counter in range(4):
        output.extend(hmac.new(
            pmk(passphrase),
            b"Pairwise key expansion\x00" + context + bytes([counter]),
            hashlib.sha1).digest())
    return bytes(output[:64])


def wpa02(passphrase: bytes = PASSPHRASE) -> str:
    eapol = bytearray(99)
    eapol[0:4] = bytes((1, 3, 0, 95))
    eapol[4] = 2
    eapol[5:7] = (0x010A).to_bytes(2, "big")
    eapol[16] = 1
    eapol[17:49] = SNONCE
    mic = hmac.new(ptk(passphrase)[:16], eapol, hashlib.sha1).digest()[:16]
    return "*".join((
        "WPA", "02", mic.hex(), AP.hex(), STATION.hex(), SSID.hex(),
        ANONCE.hex(), eapol.hex(), "00"))


def wpa01(passphrase: bytes = PASSPHRASE) -> str:
    pmkid = hmac.new(
        pmk(passphrase), b"PMK Name" + AP + STATION,
        hashlib.sha1).digest()[:16]
    return "*".join((
        "WPA", "01", pmkid.hex(), AP.hex(), STATION.hex(), SSID.hex(),
        "", "", ""))


class OwnedWifiEvidenceVerifierTests(unittest.TestCase):
    def test_official_hashcat_mode_22000_reference_vector(self) -> None:
        record = verifier.parse_record(HASHCAT_REFERENCE_PMKID)
        self.assertTrue(verifier.verify_candidate(record, b"hashcat!"))
        self.assertFalse(verifier.verify_candidate(record, b"hashcat?"))

    def test_wpa01_and_wpa02_verify_without_external_engine(self) -> None:
        records = [verifier.parse_record(wpa01()),
                   verifier.parse_record(wpa02())]
        for record in records:
            self.assertTrue(verifier.verify_candidate(record, PASSPHRASE))
            self.assertFalse(verifier.verify_candidate(record, b"wrong-pass"))

    def test_strict_parser_rejects_malformed_and_noncanonical_records(self) \
            -> None:
        cases = [
            "raw",
            wpa02().replace("WPA*02", "WPA*03", 1),
            wpa02().replace(AP.hex(), "00", 1),
            wpa02().replace("00", "xyz", 1),
        ]
        record = verifier.parse_record(wpa02())
        nonzero_mic_eapol = bytearray(record.eapol)
        nonzero_mic_eapol[81] = 1
        fields = wpa02().split("*")
        fields[7] = nonzero_mic_eapol.hex()
        cases.append("*".join(fields))
        for value in cases:
            with self.subTest(value=value[:32]):
                with self.assertRaises(verifier.VerificationError):
                    verifier.parse_record(value)

    def test_match_report_retains_rank_and_provenance_not_plaintext(self) \
            -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "owned.hc22000"
            corpus = root / "common.txt"
            evidence.write_text(wpa02() + "\n", encoding="ascii")
            corpus.write_bytes(b"password1\n" + PASSPHRASE + b"\nthirdpass\n")
            report = verifier.verify_corpus(
                evidence=evidence,
                corpus=corpus,
                corpus_id="curated-common",
                corpus_version="2026.09",
                corpus_class="common",
                max_candidates=10,
                max_seconds=10.0,
            )
            self.assertEqual("weak_password_match", report["outcome"])
            self.assertEqual(2, report["result"]["matched_rank"])
            self.assertEqual("common_password",
                             report["result"]["weakness_class"])
            encoded = json.dumps(report)
            self.assertNotIn(PASSPHRASE.decode("ascii"), encoded)
            self.assertFalse(report["privacy"]["plaintext_retained"])
            self.assertEqual(0, report["side_effects"]["network_operations"])

    def test_budget_checkpoint_and_resume_are_bound_to_exact_inputs(self) \
            -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "owned.hc22000"
            corpus = root / "vendor.txt"
            checkpoint = root / "checkpoint.json"
            evidence.write_text(wpa01() + "\n", encoding="ascii")
            corpus.write_bytes(b"password1\n" + PASSPHRASE + b"\n")
            first = verifier.verify_corpus(
                evidence=evidence,
                corpus=corpus,
                corpus_id="vendor-defaults",
                corpus_version="1",
                corpus_class="vendor_default",
                max_candidates=1,
                max_seconds=10.0,
                checkpoint_path=checkpoint,
            )
            self.assertEqual("paused_budget", first["outcome"])
            self.assertEqual(2, first["result"]["next_rank"])
            resumed = verifier.verify_corpus(
                evidence=evidence,
                corpus=corpus,
                corpus_id="vendor-defaults",
                corpus_version="1",
                corpus_class="vendor_default",
                max_candidates=1,
                max_seconds=10.0,
                checkpoint_path=checkpoint,
                resume=True,
            )
            self.assertEqual("weak_password_match", resumed["outcome"])
            self.assertEqual(2, resumed["result"]["matched_rank"])
            changed = json.loads(checkpoint.read_text(encoding="utf-8"))
            changed["corpus_sha256"] = "0" * 64
            checkpoint.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_corpus(
                    evidence=evidence,
                    corpus=corpus,
                    corpus_id="vendor-defaults",
                    corpus_version="1",
                    corpus_class="vendor_default",
                    max_candidates=1,
                    max_seconds=10.0,
                    checkpoint_path=checkpoint,
                    resume=True,
                )

    def test_preview_validates_inputs_without_testing_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "owned.hc22000"
            corpus = root / "mixed.txt"
            evidence.write_text(wpa02() + "\n", encoding="ascii")
            corpus.write_bytes(PASSPHRASE + b"\n")
            report = verifier.verify_corpus(
                evidence=evidence,
                corpus=corpus,
                corpus_id="mixed-safe",
                corpus_version="v1",
                corpus_class="mixed",
                max_candidates=1,
                max_seconds=1.0,
                preview_only=True,
            )
            self.assertEqual("preview", report["status"])
            self.assertEqual("not_started", report["outcome"])
            self.assertEqual(0, report["result"]["candidates_examined"])


if __name__ == "__main__":
    unittest.main()
