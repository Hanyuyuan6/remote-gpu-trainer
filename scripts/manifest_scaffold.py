#!/usr/bin/env python3
"""Create an empty canonical software-run directory scaffold.

The scaffold follows the artifact layout owned by ``research-artifact-hygiene``::

    runs/<run-id>/test/<test-id>/vis/<condition-id>/<task-native-role>/

It creates directories only. It never invents ``run.json``, metrics, checkpoints,
selection records, sample images, or a second result root. A scaffold is therefore
an active workspace, not an accepted or immutable run capsule.

Example:
    python manifest_scaffold.py --root . --run-id recon-seed-7 \
      --test-id set-a --condition-id rate-1_8-adc-8 \
      --task-role reconstruction
"""
from __future__ import annotations

import argparse
import re
import sys
from itertools import product
from pathlib import Path


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def checked_ids(values: list[str], label: str) -> list[str]:
    """Reject path-like or ambiguous identifiers before constructing paths."""
    bad = [value for value in values if not SAFE_ID.fullmatch(value)]
    if bad:
        raise ValueError(f"{label} must use only letters, digits, dot, underscore, and hyphen")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")
    return values


def build_dirs(
    root: Path,
    run_id: str,
    test_ids: list[str],
    condition_ids: list[str],
    task_roles: list[str],
) -> list[Path]:
    run_root = root / "runs" / run_id
    leaves = [
        run_root / "test" / test_id / "vis" / condition_id / task_role
        for test_id, condition_id, task_role in product(test_ids, condition_ids, task_roles)
    ]
    return [run_root, *leaves]


def render(root: Path, run_id: str, test_ids: list[str], condition_ids: list[str], task_roles: list[str]) -> str:
    lines = [f"{root / 'runs' / run_id}/", "  test/"]
    for test_id in test_ids:
        lines.extend((f"    {test_id}/", "      vis/"))
        for condition_id in condition_ids:
            lines.append(f"        {condition_id}/")
            lines.extend(f"          {task_role}/" for task_role in task_roles)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an empty canonical runs/<run-id> directory scaffold.")
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--run-id", required=True, help="new immutable run identity")
    parser.add_argument("--test-id", action="append", required=True, help="declared test identity; repeat as needed")
    parser.add_argument(
        "--condition-id", action="append", required=True, help="declared visualization condition; repeat as needed"
    )
    parser.add_argument(
        "--task-role", action="append", required=True, help="task-native visualization role; repeat as needed"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the scaffold without creating it")
    args = parser.parse_args()

    try:
        run_id = checked_ids([args.run_id], "run-id")[0]
        test_ids = checked_ids(args.test_id, "test-id")
        condition_ids = checked_ids(args.condition_id, "condition-id")
        task_roles = checked_ids(args.task_role, "task-role")
    except ValueError as exc:
        parser.error(str(exc))

    root = Path(args.root)
    run_root = root / "runs" / run_id
    tree = render(root, run_id, test_ids, condition_ids, task_roles)
    if args.dry_run:
        print("DRY RUN -- no files or directories were created.\n")
        print(tree)
        return 0
    if run_root.exists():
        print(f"ERROR: {run_root} already exists; refusing to merge into an existing run.", file=sys.stderr)
        return 1

    try:
        for directory in build_dirs(root, run_id, test_ids, condition_ids, task_roles):
            directory.mkdir(parents=True, exist_ok=False if directory == run_root else True)
    except OSError as exc:
        print(f"ERROR: failed to create scaffold: {exc}", file=sys.stderr)
        return 1

    print(tree)
    print("Scaffold only: populate and validate every canonical file before sealing this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
