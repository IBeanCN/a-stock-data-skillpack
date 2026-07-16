#!/usr/bin/env python3
"""Build a clean release zip containing only the installable skill package."""
from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path

INCLUDE_FILES = [
    "SKILL.md",
    "README.md",
    "LICENSE",
    "requirements.txt",
    "scripts/a_stock_client.py",
    "scripts/validate_env.py",
    "scripts/smoke_test_endpoints.py",
]
INCLUDE_DIRS = ["references"]

EXCLUDE_NAMES = {
    "__pycache__",
    ".DS_Store",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def should_include(path: Path) -> bool:
    return not any(part in EXCLUDE_NAMES for part in path.parts) and path.suffix not in EXCLUDE_SUFFIXES


def add_file(zf: zipfile.ZipFile, root: Path, file_path: Path, prefix: str) -> None:
    rel = file_path.relative_to(root)
    if should_include(rel):
        zf.write(file_path, Path(prefix) / rel)


def build_zip(root: Path, output: Path, prefix: str) -> Path:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in INCLUDE_FILES:
            path = root / item
            if not path.is_file():
                raise FileNotFoundError(f"required file missing: {item}")
            add_file(zf, root, path, prefix)
        for item in INCLUDE_DIRS:
            directory = root / item
            if not directory.is_dir():
                raise FileNotFoundError(f"required directory missing: {item}")
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    add_file(zf, root, path, prefix)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v3.4.0")
    parser.add_argument("--output-dir", default="dist", help="Directory for generated zip")
    parser.add_argument("--prefix", default=None, help="Top-level directory name inside zip")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    safe_tag = args.tag.replace(os.sep, "-")
    prefix = args.prefix or f"a-stock-data-skillpack-{safe_tag}"
    output = Path(args.output_dir) / f"a-stock-data-skillpack-{safe_tag}.zip"
    built = build_zip(root, output, prefix)
    print(built)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
