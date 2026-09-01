# Owned evidence verification

*Read in: **English** · [Русский](OWNED_EVIDENCE_VERIFICATION.ru.md)*

This is the computer-side, offline part of `CAP-061`. It answers one bounded user
question: **does authentication evidence captured from my own Wi-Fi match a local
curated common-password or vendor-default corpus?** It is not a general-purpose
cracker and does not operate a radio, join a network, or modify the DIV.

## Current accepted boundary

- input is 1…16 strict canonical `hc22000` `WPA*01` PMKID or `WPA*02` EAPOL records;
- the user explicitly confirms ownership before execution;
- the corpus is local, identified by an ID, version, class and SHA-256;
- one run is bounded to 1,000,000 candidates, 3,600 seconds and a 64 MiB corpus;
- every real run has a checkpoint bound to the exact evidence and corpus hashes;
- reports contain only match rank, weakness class, corpus provenance and input
  hashes—never the matching plaintext, raw evidence, SSID, BSSID or station ID;
- no corpus ships with Leshy, especially no identity-linked leak collection;
- EAPOL descriptor versions 1 and 2 are supported; other versions fail closed.

This host foundation does not complete `FUNC-61`: user-facing companion integration,
WPA3/key-version-3 handling, physical export-to-verification evidence, and other
owned evidence families remain open.

## Safe workflow

1. On the DIV, select **Wi-Fi → Check my network → Capture authentication** for a
   network you own or are authorized to test, then export the validated `hc22000`.
2. Prepare a local, reviewed corpus. Keep it outside the repository.
3. Preview validation without evaluating a candidate:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --preview-only
   ```

4. Run with explicit ownership confirmation, finite budgets and a durable checkpoint:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --max-candidates 10000 --max-seconds 30 \
     --checkpoint verification.checkpoint.json \
     --owned-evidence-confirmed --report verification.report.json
   ```

5. If the result is `paused`, rerun the same command with `--resume`. Any changed
   evidence, corpus or corpus metadata invalidates the checkpoint.

`weak_password_match` means only that one corpus candidate reproduces every supplied
record. The report intentionally does not reveal it. Change the network credential
through the router's normal administration path and recapture to verify remediation.

## Acceptance

The focused delta is `tools/test.sh --only owned-wifi-evidence`. It checks Leshy's
canonical export, the official Hashcat mode-22000 PMKID reference vector, WPA*01 and
WPA*02 positives/negatives, strict parsing, privacy-safe reporting, bounded
checkpoint/resume and the no-network/no-device/no-radio source contract.
