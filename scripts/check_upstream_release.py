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


def releases() -> list[dict[str, str]]:
    out = run([
        GH,
        "release",
        "list",
        "--repo",
        REPO,
        "--limit",
        "100",
        "--json",
        "tagName,isDraft,isPrerelease",
    ], check=False)
    if not out:
        return []
    try:
        rows = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse gh release list JSON: {exc}: {out[:300]}") from exc
    return [row for row in rows if row.get("tagName") and not row.get("isDraft") and not row.get("isPrerelease")]


def local_increment_number(base_tag: str, tag: str) -> int | None:
    pattern = re.compile(rf"^{re.escape(base_tag)}\.(\d+)$")
    m = pattern.match(tag)
    return int(m.group(1)) if m else None


def latest_released_for_base(base_tag: str, existing_tags: set[str]) -> str:
    latest_tag = base_tag
    latest_num = 0
    for tag in existing_tags:
        number = local_increment_number(base_tag, tag)
        if number is not None and number > latest_num:
            latest_num = number
            latest_tag = tag
    return latest_tag


def next_local_increment(base_tag: str, existing_tags: set[str]) -> str:
    current = 0
    for tag in existing_tags:
        number = local_increment_number(base_tag, tag)
        if number is not None:
            current = max(current, number)
    return f"{base_tag}.{current + 1}"


def release_commit(tag: str) -> str | None:
    run(["git", "fetch", "origin", "tag", tag], check=False)
    resolved = run(["git", "rev-parse", f"refs/tags/{tag}^{{commit}}"], check=False)
    if resolved:
        return resolved
    out = run([GH, "release", "view", tag, "--repo", REPO, "--json", "targetCommitish"], check=False)
    if not out:
        return None
    try:
        target = json.loads(out).get("targetCommitish")
    except json.JSONDecodeError:
        return None
    if not target:
        return None
    resolved = run(["git", "rev-parse", target], check=False)
    return resolved or target


def local_main_has_unreleased_commits(latest_release_tag: str) -> bool:
    run(["git", "fetch", "origin", "main", "--tags"], check=False)
    head = run(["git", "rev-parse", "origin/main"], check=False) or run(["git", "rev-parse", "HEAD"])
    released = release_commit(latest_release_tag)
    if not released:
        return False
    if head == released:
        return False
    merge_base = run(["git", "merge-base", released, head], check=False)
    return merge_base == released


def main() -> int:
    tags = upstream_tags()
    if not tags:
        print("ERROR: no upstream tags found", file=sys.stderr)
        return 2
    rows = releases()
    existing = {row["tagName"] for row in rows}
    latest_upstream = tags[-1]
    workspace = str(Path(__file__).resolve().parents[1])

    if latest_upstream not in existing:
        prev = None
        for candidate in reversed(tags[:-1]):
            if candidate in existing:
                prev = candidate
                break
        unreleased = tags[tags.index(prev) + 1 :] if prev else tags
        payload = {
            "mode": "upstream_sync",
            "upstream": UPSTREAM,
            "repo": REPO,
            "upstream_tag": latest_upstream,
            "release_tag": latest_upstream,
            "previous_released_tag": prev,
            "unreleased_upstream_tags_after_previous": unreleased,
            "workspace": workspace,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    latest_base_release = latest_released_for_base(latest_upstream, existing)
    if local_main_has_unreleased_commits(latest_base_release):
        release_tag = next_local_increment(latest_upstream, existing)
        payload = {
            "mode": "local_increment",
            "upstream": UPSTREAM,
            "repo": REPO,
            "upstream_tag": latest_upstream,
            "release_tag": release_tag,
            "previous_released_tag": latest_base_release,
            "workspace": workspace,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
