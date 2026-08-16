#!/usr/bin/env python3
"""Check a physical 1.x candidate once, then promote those exact bytes.

This is intentionally an operator command, not a daemon. ``check`` downloads a
pinned GitHub Actions runner, registers it as an ephemeral repository runner,
lets it execute one physical HIL job, and removes the temporary directory.
``publish`` accepts only a successful run whose GitHub attestations and embedded
HIL evidence bind the release files to the tested main-branch commit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = "prerelease-hil.yml"
WORKFLOW_NAME = "prerelease-hil"
WORKFLOW_PATH = ".github/workflows/prerelease-hil.yml"
RUNNER_VERSION = "2.336.0"
RUNNER_ARCHIVE = f"actions-runner-osx-arm64-{RUNNER_VERSION}.tar.gz"
RUNNER_URL = (
    f"https://github.com/actions/runner/releases/download/v{RUNNER_VERSION}/"
    f"{RUNNER_ARCHIVE}"
)
RUNNER_SHA256 = "8e8839c49b7060b6b2154f4931f815df330c27f167d53ef2239ee3dfce28b079"
RUNNER_LABELS = "leshy-hil,esp32-div-v2"
PHYSICAL_JOB = "Flash, exercise, capture, and attest board-01"
CANDIDATE_FILES = {
    "firmware.bin",
    "firmware.factory.bin",
    "firmware.elf",
    "firmware.map",
}
SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
SERIAL_PATTERNS = (
    "/dev/cu.usbmodem*",
    "/dev/cu.usbserial*",
    "/dev/cu.SLAB_USBtoUART*",
    "/dev/cu.wchusbserial*",
)


class ReleaseError(RuntimeError):
    """A checked release invariant failed."""


def run_command(
    args: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path = ROOT,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(value) for value in args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise ReleaseError(details or f"command failed with exit code {result.returncode}")
    return result


def json_command(args: Sequence[str | os.PathLike[str]], *, cwd: Path = ROOT) -> Any:
    result = run_command(args, cwd=cwd)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("command returned invalid JSON") from exc


def parse_semver(value: str) -> tuple[int, int, int, str | None, str | None]:
    match = SEMVER.fullmatch(value)
    if match is None:
        raise ReleaseError(f"invalid SemVer: {value!r}")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        match.group(4),
        match.group(5),
    )


def require_stable_release_version(value: str) -> None:
    major, _minor, _patch, prerelease, build = parse_semver(value)
    if major < 1 or prerelease is not None or build is not None:
        raise ReleaseError("publish accepts only a stable 1.x-or-newer X.Y.Z version")


def parse_run_title(title: str) -> tuple[str, str]:
    prefix = f"{WORKFLOW_NAME} / "
    if not title.startswith(prefix):
        raise ReleaseError(f"unexpected workflow title: {title!r}")
    parts = title[len(prefix) :].split(" / ")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ReleaseError(f"malformed workflow title: {title!r}")
    parse_semver(parts[0])
    return parts[0], parts[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_programs(names: Iterable[str]) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise ReleaseError(f"required programs are missing: {', '.join(missing)}")


def repository() -> str:
    return run_command(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    ).stdout.strip()


def embedded_version() -> str:
    return run_command([sys.executable, "tools/read_1x_version.py"]).stdout.strip()


def git_preflight(version: str, expected_sha: str | None = None) -> str:
    parse_semver(version)
    require_programs(("git", "gh", "python3"))
    run_command(["gh", "auth", "status"])
    if run_command(["git", "branch", "--show-current"]).stdout.strip() != "main":
        raise ReleaseError("release checks are allowed only from branch main")
    if run_command(["git", "status", "--porcelain"]).stdout.strip():
        raise ReleaseError("working tree is not clean; commit and push the candidate first")
    run_command(["git", "fetch", "--quiet", "origin", "main"])
    head = run_command(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_head = run_command(["git", "rev-parse", "origin/main"]).stdout.strip()
    if head != remote_head:
        raise ReleaseError("local HEAD does not match origin/main")
    if expected_sha is not None and head != expected_sha:
        raise ReleaseError(
            f"current HEAD {head} is not the tested workflow commit {expected_sha}"
        )
    actual_version = embedded_version()
    if actual_version != version:
        raise ReleaseError(
            f"source embeds version {actual_version!r}, requested {version!r}"
        )
    return head


def discover_serial_port(explicit: str | None = None) -> str:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise ReleaseError(f"serial port does not exist: {explicit}")
        return explicit
    candidates: set[str] = set()
    for pattern in SERIAL_PATTERNS:
        candidates.update(str(path) for path in Path("/").glob(pattern.removeprefix("/")))
    ordered = sorted(candidates)
    if not ordered:
        raise ReleaseError("no ESP32 serial port found; connect the board or pass --port")
    if len(ordered) != 1:
        raise ReleaseError(
            "several serial ports found; select one with --port: " + ", ".join(ordered)
        )
    return ordered[0]


def runner_cache_dir() -> Path:
    override = os.environ.get("LESHY_RUNNER_CACHE")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Caches" / "esp32-leshy" / "actions-runner"


def obtain_runner_archive(cache_dir: Path | None = None) -> Path:
    destination_dir = cache_dir or runner_cache_dir()
    destination_dir.mkdir(parents=True, exist_ok=True)
    archive = destination_dir / RUNNER_ARCHIVE
    if archive.is_file() and sha256_file(archive) == RUNNER_SHA256:
        print(f"Using verified runner cache: {archive}", flush=True)
        return archive

    print(f"Downloading pinned GitHub Actions runner v{RUNNER_VERSION}…", flush=True)
    temporary = destination_dir / f".{RUNNER_ARCHIVE}.{secrets.token_hex(6)}.tmp"
    try:
        request = urllib.request.Request(
            RUNNER_URL, headers={"User-Agent": "esp32-leshy-release-gate/1"}
        )
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open(
            "wb"
        ) as output:
            shutil.copyfileobj(response, output)
        actual = sha256_file(temporary)
        if actual != RUNNER_SHA256:
            raise ReleaseError(
                f"runner archive checksum mismatch: expected {RUNNER_SHA256}, got {actual}"
            )
        os.replace(temporary, archive)
    finally:
        if temporary.exists():
            temporary.unlink()
    return archive


def safe_extract_tar(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise ReleaseError(f"unsafe archive member: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ReleaseError(f"unsupported archive member: {member.name}")
        try:
            source.extractall(destination, filter="data")
        except TypeError:  # Python < 3.12
            source.extractall(destination)


def request_id() -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def dispatch_workflow(repo: str, version: str, invocation: str, port: str) -> None:
    run_command(
        [
            "gh",
            "workflow",
            "run",
            WORKFLOW,
            "--repo",
            repo,
            "--ref",
            "main",
            "--field",
            f"version={version}",
            "--field",
            f"request_id={invocation}",
            "--field",
            f"hil_port={port}",
        ]
    )


def find_dispatched_run(repo: str, title: str, head_sha: str, timeout: int = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runs = json_command(
            [
                "gh",
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                WORKFLOW,
                "--event",
                "workflow_dispatch",
                "--branch",
                "main",
                "--limit",
                "30",
                "--json",
                "databaseId,displayTitle,headSha,status,url",
            ]
        )
        for item in runs:
            if item.get("displayTitle") == title and item.get("headSha") == head_sha:
                return item
        time.sleep(2)
    raise ReleaseError("dispatched workflow did not appear in GitHub Actions")


def run_details(repo: str, run_id: int) -> dict[str, Any]:
    return json_command(
        [
            "gh",
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--json",
            (
                "conclusion,databaseId,displayTitle,event,headBranch,headSha,jobs,"
                "status,url,workflowName"
            ),
        ]
    )


def wait_for_physical_queue(repo: str, run_id: int, timeout: int = 3600) -> None:
    deadline = time.monotonic() + timeout
    last_message = 0.0
    while time.monotonic() < deadline:
        details = run_details(repo, run_id)
        jobs = {job.get("name"): job for job in details.get("jobs", [])}
        physical = jobs.get(PHYSICAL_JOB)
        if physical and physical.get("status") in {"queued", "waiting"}:
            print("Cloud build passed; physical HIL job is waiting for board-01.", flush=True)
            return
        if details.get("status") == "completed":
            raise ReleaseError(
                f"workflow completed before HIL with conclusion {details.get('conclusion')!r}"
            )
        now = time.monotonic()
        if now - last_message >= 20:
            candidate = jobs.get("Build and attest candidate", {})
            state = candidate.get("status", details.get("status", "unknown"))
            print(f"Waiting for cloud candidate build: {state}…", flush=True)
            last_message = now
        time.sleep(5)
    raise ReleaseError("timed out waiting for the physical HIL job")


def registration_token(repo: str) -> str:
    token = run_command(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{repo}/actions/runners/registration-token",
            "--jq",
            ".token",
        ]
    ).stdout.strip()
    if not token:
        raise ReleaseError("GitHub returned an empty runner registration token")
    return token


def configure_runner(runner_dir: Path, repo: str, name: str) -> None:
    token = registration_token(repo)
    run_command(
        [
            "./config.sh",
            "--url",
            f"https://github.com/{repo}",
            "--token",
            token,
            "--name",
            name,
            "--labels",
            RUNNER_LABELS,
            "--work",
            "_work",
            "--ephemeral",
            "--disableupdate",
            "--unattended",
        ],
        cwd=runner_dir,
    )


def unregister_runner(repo: str, name: str) -> None:
    result = run_command(
        ["gh", "api", f"repos/{repo}/actions/runners", "--paginate"], check=False
    )
    if result.returncode != 0:
        print("Warning: could not inspect runner registration during cleanup.", file=sys.stderr)
        return
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Warning: invalid runner-list response during cleanup.", file=sys.stderr)
        return
    for runner in payload.get("runners", []):
        if runner.get("name") == name:
            deleted = run_command(
                [
                    "gh",
                    "api",
                    "--method",
                    "DELETE",
                    f"repos/{repo}/actions/runners/{runner['id']}",
                ],
                check=False,
            )
            if deleted.returncode != 0:
                print("Warning: could not delete runner registration.", file=sys.stderr)


def stop_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def write_receipt(payload: dict[str, Any]) -> Path:
    destination = ROOT / "release-checks" / f"{payload['run_id']}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, destination)
    return destination


def check_candidate(version: str, port_arg: str | None) -> int:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ReleaseError("the pinned HIL runner currently supports macOS arm64 only")
    head_sha = git_preflight(version)
    repo = repository()
    port = discover_serial_port(port_arg)
    archive = obtain_runner_archive()
    invocation = request_id()
    title = f"{WORKFLOW_NAME} / {version} / {invocation}"
    run_id: int | None = None
    completed = False

    print(f"Board: {port}", flush=True)
    print(f"Candidate: {version} @ {head_sha}", flush=True)
    dispatch_workflow(repo, version, invocation, port)
    selected = find_dispatched_run(repo, title, head_sha)
    run_id = int(selected["databaseId"])
    print(f"GitHub run: {selected['url']}", flush=True)

    runner_name = f"leshy-hil-{invocation}"
    runner_process: subprocess.Popen[Any] | None = None
    try:
        wait_for_physical_queue(repo, run_id)
        with tempfile.TemporaryDirectory(prefix="leshy-ephemeral-runner-") as temporary:
            runner_dir = Path(temporary)
            safe_extract_tar(archive, runner_dir)
            configure_runner(runner_dir, repo, runner_name)
            print("Ephemeral runner registered for one physical job.", flush=True)
            runner_process = subprocess.Popen(
                ["./run.sh"],
                cwd=runner_dir,
                start_new_session=True,
            )
            try:
                watched = subprocess.run(
                    [
                        "gh",
                        "run",
                        "watch",
                        str(run_id),
                        "--repo",
                        repo,
                        "--exit-status",
                    ],
                    cwd=ROOT,
                )
                if watched.returncode != 0:
                    raise ReleaseError(f"release check failed; inspect GitHub run {run_id}")
                try:
                    runner_process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    stop_process(runner_process)
                details = run_details(repo, run_id)
                if (
                    details.get("status") != "completed"
                    or details.get("conclusion") != "success"
                ):
                    raise ReleaseError(f"workflow {run_id} did not complete successfully")
                completed = True
            finally:
                stop_process(runner_process)
    finally:
        stop_process(runner_process)
        unregister_runner(repo, runner_name)
        if run_id is not None and not completed:
            run_command(
                ["gh", "run", "cancel", str(run_id), "--repo", repo], check=False
            )

    receipt = write_receipt(
        {
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "head_sha": head_sha,
            "port": port,
            "repository": repo,
            "request_id": invocation,
            "run_id": run_id,
            "status": "release-ready",
            "url": selected["url"],
            "version": version,
        }
    )
    print("\nRELEASE READY", flush=True)
    print(f"Receipt: {receipt}", flush=True)
    print(f"Publish exact tested bytes: ./tools/release_1x.py publish {run_id}", flush=True)
    return 0


def verify_attestation(path: Path, repo: str, head_sha: str) -> None:
    run_command(
        [
            "gh",
            "attestation",
            "verify",
            str(path),
            "--repo",
            repo,
            "--signer-workflow",
            f"{repo}/{WORKFLOW_PATH}",
            "--source-ref",
            "refs/heads/main",
            "--source-digest",
            head_sha,
        ]
    )


def ensure_release_absent(repo: str, tag: str) -> None:
    result = run_command(
        ["gh", "api", f"repos/{repo}/releases/tags/{tag}"], check=False
    )
    if result.returncode == 0:
        raise ReleaseError(f"GitHub release {tag} already exists")
    if "404" not in result.stderr and "Not Found" not in result.stderr:
        raise ReleaseError(result.stderr.strip() or f"could not check release {tag}")
    ref = run_command(
        ["gh", "api", f"repos/{repo}/git/ref/tags/{tag}"], check=False
    )
    if ref.returncode == 0:
        raise ReleaseError(f"Git tag {tag} already exists")
    if "404" not in ref.stderr and "Not Found" not in ref.stderr:
        raise ReleaseError(ref.stderr.strip() or f"could not check tag {tag}")


def verify_downloaded_candidate(candidate: Path) -> list[Path]:
    actual = {path.name for path in candidate.iterdir() if path.is_file()}
    if actual != CANDIDATE_FILES:
        missing = sorted(CANDIDATE_FILES - actual)
        extra = sorted(actual - CANDIDATE_FILES)
        raise ReleaseError(f"unexpected candidate files; missing={missing}, extra={extra}")
    return [candidate / name for name in sorted(CANDIDATE_FILES)]


def publish_run(run_id: int) -> int:
    require_programs(("git", "gh", "python3"))
    repo = repository()
    details = run_details(repo, run_id)
    if details.get("workflowName") != WORKFLOW_NAME:
        raise ReleaseError(f"run {run_id} belongs to a different workflow")
    if details.get("event") != "workflow_dispatch" or details.get("headBranch") != "main":
        raise ReleaseError(f"run {run_id} is not a manual main-branch HIL run")
    if details.get("status") != "completed" or details.get("conclusion") != "success":
        raise ReleaseError(f"run {run_id} is not successful")
    version, _invocation = parse_run_title(str(details.get("displayTitle", "")))
    require_stable_release_version(version)
    head_sha = str(details.get("headSha", ""))
    git_preflight(version, expected_sha=head_sha)
    tag = f"v{version}"
    ensure_release_absent(repo, tag)

    with tempfile.TemporaryDirectory(prefix="leshy-release-promotion-") as temporary:
        root = Path(temporary)
        candidate = root / "candidate"
        evidence = root / "evidence"
        run_command(
            [
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                repo,
                "--name",
                "leshy1-candidate",
                "--dir",
                str(candidate),
            ]
        )
        run_command(
            [
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                repo,
                "--name",
                "leshy1-hil-evidence",
                "--dir",
                str(evidence),
            ]
        )
        candidate_files = verify_downloaded_candidate(candidate)
        evidence_archive = evidence / "hil-evidence.tar.gz"
        if not evidence_archive.is_file() or len(list(evidence.iterdir())) != 1:
            raise ReleaseError("HIL evidence artifact has unexpected contents")
        for artifact in [*candidate_files, evidence_archive]:
            verify_attestation(artifact, repo, head_sha)

        extracted = root / "verified-evidence"
        extracted.mkdir()
        safe_extract_tar(evidence_archive, extracted)
        run_command(
            [
                sys.executable,
                "tools/verify_1x_prerelease_bundle.py",
                "--bundle",
                str(extracted / "hil-bundle"),
                "--candidate",
                str(candidate / "firmware.bin"),
                "--suite-id",
                "device-smoke",
                "--suite-revision",
                "1",
                "--expected-version",
                version,
                "--allow-unsigned-local-result",
            ]
        )

        notes = (
            f"Promoted from successful physical HIL run {run_id}: {details['url']}\n\n"
            f"Tested commit: `{head_sha}`. The attached firmware and evidence are "
            "GitHub-attested outputs of that exact run."
        )
        run_command(
            [
                "gh",
                "release",
                "create",
                tag,
                *[str(path) for path in candidate_files],
                str(evidence_archive),
                "--repo",
                repo,
                "--target",
                head_sha,
                "--title",
                f"ESP32-Leshy {version}",
                "--notes",
                notes,
            ]
        )

    print(f"Published {tag} from exact HIL-approved run {run_id}.")
    print(f"{details['url']}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Physically check and promote exact ESP32-Leshy 1.x release bytes."
    )
    commands = result.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="run one on-demand physical release check")
    check.add_argument("version", help="exact SemVer embedded in firmware/leshy1")
    check.add_argument("--port", help="serial port; auto-detected when exactly one exists")
    publish = commands.add_parser("publish", help="publish a successful checked run")
    publish.add_argument("run_id", type=int, help="GitHub Actions run database ID")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "check":
            return check_candidate(args.version, args.port)
        return publish_run(args.run_id)
    except (ReleaseError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted; the workflow and ephemeral runner are being cleaned up.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
