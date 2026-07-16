#!/usr/bin/env python3
"""Detect whether upstream simonlin1212/a-stock-data has a newer release tag.

No output means there is nothing to do. This is intentional so scheduled jobs can
stay silent unless an update exists.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

UPSTREAM = "https://github.com/simonlin1212/a-stock-data.git"
REPO = "IBeanCN/a-stock-data-skillpack"
GH = os.environ.get("GH_BIN", "/home/agent/.local/bin/gh")


def run(cmd: list[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nSTDERR:\n{result.stderr.strip()}")
    return result.stdout.strip()


def version_key(tag: str) -> tuple[int, ...]:
    cleaned = tag.lstrip("v")
    parts = re.split(r"[.-]", cleaned)
    key: list[int] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            m = re.match(r"(\d+)", part)
            key.append(int(m.group(1)) if m else -1)
    return tuple(key)


def upstream_tags() -> list[str]:
    out = run(["git", "ls-remote", "--tags", "--refs", UPSTREAM, "v*"])
    tags = []
    for line in out.splitlines():
        if not line.strip():
            continue
        ref = line.split("refs/tags/", 1)[-1]
        if re.fullmatch(r"v\d+(?:\.\d+)*(?:[-.][0-9A-Za-z]+)?", ref):
            tags.append(ref)
    return sorted(set(tags), key=version_key)


def released_tags() -> set[str]:
    out = run([GH, "release", "list", "--repo", REPO, "--limit", "100", "--json", "tagName"], check=False)
    if not out:
        return set()
    try:
        rows = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse gh release list JSON: {exc}: {out[:300]}") from exc
    return {row.get("tagName", "") for row in rows if row.get("tagName")}


def main() -> int:
    tags = upstream_tags()
    if not tags:
        print("ERROR: no upstream tags found", file=sys.stderr)
        return 2
    existing = released_tags()
    latest = tags[-1]
    if latest in existing:
        return 0
    prev = None
    for candidate in reversed(tags[:-1]):
        if candidate in existing:
            prev = candidate
            break
    unreleased = tags[tags.index(prev) + 1 :] if prev else tags
    payload = {
        "upstream": UPSTREAM,
        "repo": REPO,
        "tag": latest,
        "previous_released_tag": prev,
        "unreleased_upstream_tags_after_previous": unreleased,
        "workspace": str(Path(__file__).resolve().parents[1]),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
