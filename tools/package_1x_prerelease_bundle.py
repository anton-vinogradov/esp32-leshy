#!/usr/bin/env python3
"""Create a deterministic archive for GitHub Artifact Attestation."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tarfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def package_bundle(bundle: Path, output: Path) -> dict[str, object]:
    if not bundle.is_dir():
        raise ValueError(f"bundle directory not found: {bundle}")
    if output.exists():
        raise ValueError(f"output must not exist: {output}")
    try:
        output.resolve().relative_to(bundle.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("output archive must be outside the bundle directory")

    files = sorted(path for path in bundle.rglob("*") if path.is_file())
    unsupported = sorted(
        path for path in bundle.rglob("*")
        if path.is_symlink() or (not path.is_file() and not path.is_dir())
    )
    if unsupported:
        raise ValueError(f"bundle contains unsupported entries: {unsupported}")
    if not files:
        raise ValueError("bundle contains no files")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as raw_output:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw_output, compresslevel=9, mtime=0
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for path in files:
                    relative = path.relative_to(bundle).as_posix()
                    stat = path.stat()
                    info = tarfile.TarInfo(f"hil-bundle/{relative}")
                    info.size = stat.st_size
                    info.mode = 0o644
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    with path.open("rb") as source:
                        archive.addfile(info, source)

    return {
        "schema": "leshy.prerelease.package.v1",
        "archive": str(output.resolve()),
        "sha256": sha256_file(output),
        "files": len(files),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = package_bundle(args.bundle.resolve(), args.output.resolve())
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
