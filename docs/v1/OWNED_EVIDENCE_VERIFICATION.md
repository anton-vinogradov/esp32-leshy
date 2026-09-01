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

The supported WPA2 PMKID/EAPOL user journey and its physical
export-to-verification chain complete `WF-11`. Wider `FUNC-61` remains active for
WPA3/key-version-3 handling and other owned evidence families.

## Safe workflow

1. On the DIV, select **Wi-Fi → Networks → your network → Check my password** for a
   network you own or are authorized to test. Follow the explanation, record the
   bounded authentication evidence, then save and export it from **Saved records**.
2. Prepare a local, reviewed list of common or router-default passwords. Keep it
   outside the repository.
3. Use the primary task-first journey. It explains the authorization boundary,
   previews the exact limits, creates the checkpoint automatically and prints a
   plain-language result:

   ```sh
   python3 tools/check_my_wifi_password.py \
     --evidence owned.hc22000 --corpus common.txt \
     --list-kind common --max-candidates 10000 --max-seconds 30
   ```

   If it pauses, rerun the same command with `--resume`. Changed evidence or corpus
   invalidates the checkpoint. `--preview-only` validates inputs without evaluating
   any password.

4. The lower-level verifier remains available for automation and advanced use:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --preview-only
   ```

5. Run it with explicit ownership confirmation, finite budgets and a durable checkpoint:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --max-candidates 10000 --max-seconds 30 \
     --checkpoint verification.checkpoint.json \
     --owned-evidence-confirmed --report verification.report.json
   ```

6. If the result is `paused`, rerun the same command with `--resume`. Any changed
   evidence, corpus or corpus metadata invalidates the checkpoint.

`weak_password_match` means only that one corpus candidate reproduces every supplied
record. The durable report intentionally does not reveal it. Change the network
credential through the router's normal administration path and recapture to verify
remediation. `complete_no_match` is not proof that the password is strong; it only
rules out the exact finite local list that was checked.

## Acceptance

The focused delta is `tools/test.sh --only owned-wifi-evidence`. It checks Leshy's
canonical export, the task-first journey, the official Hashcat mode-22000 PMKID
reference vector, WPA*01 and WPA*02 positives/negatives, strict parsing,
privacy-safe reporting, bounded checkpoint/resume and the no-network/no-device/no-radio
source contract. The retained [physical acceptance](../../tests/hil/evidence/board-01-owned-wifi-password-check-1.0.0-dev.369.json)
additionally binds exact candidate hashes/CID, task-first device navigation, atomic
save, cold reopen, canonical export, physical negative control, public positive
control and final cleanup without retaining raw evidence or network identity.
