#!/usr/bin/env python3
"""Skip firmware gates only for a proven documentation-only change."""

import json
import os
import re
import subprocess
from pathlib import Path

DOC_TOOLS = {
    "tools/check_docs.py", "tools/readme_roadmap.py",
    "tools/export_wifi_map.py", "tools/test_wifi_map_export.py",
}


def docs_only(paths: list[str]) -> bool:
    return bool(paths) and all(
        path.startswith("docs/") or path in DOC_TOOLS or
        path in {"README.md", "README.ru.md"}
        for path in paths
    )


def changed_paths(event: dict, event_name: str) -> list[str]:
    if event_name == "pull_request":
        base = event["pull_request"]["base"]["sha"]
        head = event["pull_request"]["head"]["sha"]
        separator = "..."
    elif event_name == "push":
        base, head = event["before"], event["after"]
        separator = ".."
    else:
        return []
    for revision in (base, head):
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision == "0" * 40:
            return []
    result = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
         base + separator + head, "--"],
        check=True, stdout=subprocess.PIPE,
    )
    return [name.decode("utf-8", errors="strict")
            for name in result.stdout.split(b"\0") if name]


def main() -> None:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        minimal = docs_only(changed_paths(event, os.environ["GITHUB_EVENT_NAME"]))
    except (KeyError, ValueError, TypeError, OSError, subprocess.CalledProcessError):
        # Unknown events, missing history and parse errors require full gates.
        minimal = False
    result = "true" if minimal else "false"
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"docs_only={result}\n")
    print(f"docs_only={result}; manual/unknown changes require full gates")


if __name__ == "__main__":
    main()
