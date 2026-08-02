#!/usr/bin/env python3
"""Build a fail-closed manifest for a remote result bundle.

The manifest is created on the durable remote filesystem before the final pull.
It binds a run id to an exact file roster, byte sizes, and SHA-256 digests.  The
local verifier refuses teardown when the roster or any digest differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "remote-gpu-trainer/PULL/v1"
MANIFEST_NAME = "PULL_MANIFEST.json"
VERIFICATION_NAME = "PULL_VERIFIED.json"
SAFE_DIR_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    root: Path,
    run_id: str,
    expected_dirs: list[str],
    output: Path | None = None,
) -> dict:
    root = root.resolve()
    output = (output or root / MANIFEST_NAME).resolve()
    if not root.is_dir():
        raise ValueError(f"result root is not a directory: {root}")
    if not run_id.strip():
        raise ValueError("run id must be non-empty")
    if output.parent != root:
        raise ValueError("manifest must be written directly inside the result root")

    if not expected_dirs:
        raise ValueError("expected roster must name at least one result directory")
    if len(set(expected_dirs)) != len(expected_dirs):
        raise ValueError("expected roster contains duplicate directory names")
    for name in expected_dirs:
        if not SAFE_DIR_RE.fullmatch(name):
            raise ValueError(f"unsafe result directory in expected roster: {name!r}")

    top_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if not top_dirs:
        raise ValueError(f"no result directories found in {root}")
    actual_names = [path.name for path in top_dirs]
    if set(actual_names) != set(expected_dirs):
        missing = sorted(set(expected_dirs) - set(actual_names))
        unexpected = sorted(set(actual_names) - set(expected_dirs))
        raise ValueError(f"result roster mismatch; missing={missing}, unexpected={unexpected}")

    files: list[dict] = []
    for directory in top_dirs:
        if not SAFE_DIR_RE.fullmatch(directory.name):
            raise ValueError(
                f"unsafe result directory name {directory.name!r}; use letters, digits, dot, underscore, or hyphen"
            )
        for required in ("best.pth", "best_metrics.json"):
            if not (directory / required).is_file():
                raise ValueError(f"{directory.name} is incomplete: missing {required}")

        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symlink is not permitted in a teardown bundle: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            files.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )

    if not files:
        raise ValueError(f"no files found in {root}")

    return {
        "schema": SCHEMA,
        "run_id": run_id.strip(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "top_level_dirs": [path.name for path in top_dirs],
        "files": files,
        "totals": {
            "files": len(files),
            "bytes": sum(item["bytes"] for item in files),
        },
    }


def write_manifest(
    root: Path,
    run_id: str,
    expected_dirs: list[str],
    output: Path | None = None,
) -> Path:
    root = root.resolve()
    output = (output or root / MANIFEST_NAME).resolve()
    manifest = build_manifest(root, run_id, expected_dirs, output)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Durable result root containing one directory per run/cell")
    parser.add_argument("--run-id", required=True, help="Immutable sweep or delivery identifier")
    parser.add_argument(
        "--expected-roster",
        required=True,
        type=Path,
        help="UTF-8 file with one expected result directory per line; blank lines and # comments are ignored",
    )
    parser.add_argument("--output", type=Path, default=None, help="Defaults to <root>/PULL_MANIFEST.json")
    args = parser.parse_args()
    try:
        expected_dirs = [
            line.strip()
            for line in args.expected_roster.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        output = write_manifest(args.root, args.run_id, expected_dirs, args.output)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"WROTE {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
