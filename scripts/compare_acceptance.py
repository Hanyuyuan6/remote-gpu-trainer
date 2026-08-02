#!/usr/bin/env python3
"""Compare independent artifact acceptances while ignoring verifier/runtime identity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != "accepted":
        raise RuntimeError(f"{path}: not an accepted object")
    return value


def scientific_core(value: dict) -> dict:
    checkpoints = {}
    for path, row in (value.get("checkpoints") or {}).items():
        checkpoints[path] = {
            key: row.get(key)
            for key in (
                "sha256",
                "safe_weights_only_load",
                "safe_globals",
                "tensor_count",
                "tensor_numel",
            )
        }
    return {
        "schema": value.get("schema"),
        "status": value.get("status"),
        "artifact_id": value.get("artifact_id"),
        "producer_node": value.get("producer_node"),
        "manifest_sha256": value.get("manifest_sha256"),
        "verified_files": value.get("verified_files"),
        "checkpoints": checkpoints,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args()
    left_raw = read(args.left)
    right_raw = read(args.right)
    left_node = str(left_raw.get("independent_node") or "").strip()
    right_node = str(right_raw.get("independent_node") or "").strip()
    producer_node = str(left_raw.get("producer_node") or "").strip()
    independence_problems = []
    if not left_node or not right_node:
        independence_problems.append("both acceptances must name an independent_node")
    if left_node == right_node:
        independence_problems.append("acceptances must come from distinct verifier nodes")
    if producer_node and producer_node in {left_node, right_node}:
        independence_problems.append("a verifier node matches the producer node")
    if independence_problems:
        print("ACCEPTANCE_INDEPENDENCE_FAILED " + "; ".join(independence_problems))
        return 2
    left = scientific_core(left_raw)
    right = scientific_core(right_raw)
    if left != right:
        left_text = json.dumps(left, indent=2, sort_keys=True).splitlines()
        right_text = json.dumps(right, indent=2, sort_keys=True).splitlines()
        import difflib
        print("\n".join(difflib.unified_diff(left_text, right_text, fromfile=str(args.left), tofile=str(args.right))))
        return 2
    print(
        f"ACCEPTANCE_MATCH id={left['artifact_id']} files={len(left.get('verified_files') or {})} "
        f"checkpoints={len(left.get('checkpoints') or {})}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
