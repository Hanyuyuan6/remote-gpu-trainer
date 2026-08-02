#!/usr/bin/env python3
"""Regression checks for manifest-bound independent artifact acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify_artifact_bundle.py"
COMPARE = ROOT / "scripts" / "compare_acceptance.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="artifact_bundle_eval_") as raw:
        root = Path(raw)
        (root / "metrics.json").write_text('{"score": 1}\n', encoding="utf-8")
        manifest = {
            "schema": "test-producer-v1",
            "artifact_id": "cell-1",
            "producer_node": "node-a",
            "files": {
                "metrics.json": {
                    "size_bytes": (root / "metrics.json").stat().st_size,
                    "sha256": sha(root / "metrics.json"),
                }
            },
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        outputs = []
        for node in ("node-b", "node-c"):
            out = root / f"accept-{node}.json"
            proc = subprocess.run(
                [sys.executable, str(VERIFY), "--root", str(root), "--manifest", "manifest.json", "--required", "metrics.json", "--independent-node", node, "--out", str(out)],
                text=True,
                capture_output=True,
            )
            assert proc.returncode == 0, proc.stdout + proc.stderr
            outputs.append(out)
        proc = subprocess.run([sys.executable, str(COMPARE), str(outputs[0]), str(outputs[1])], text=True, capture_output=True)
        assert proc.returncode == 0 and "ACCEPTANCE_MATCH" in proc.stdout, proc.stdout + proc.stderr
        proc = subprocess.run([sys.executable, str(COMPARE), str(outputs[0]), str(outputs[0])], text=True, capture_output=True)
        assert proc.returncode != 0 and "ACCEPTANCE_INDEPENDENCE_FAILED" in proc.stdout

        proc = subprocess.run(
            [sys.executable, str(VERIFY), "--root", str(root), "--manifest", "manifest.json", "--independent-node", "node-a", "--out", str(root / "same-node.json")],
            text=True,
            capture_output=True,
        )
        assert proc.returncode != 0

        (root / "metrics.json").write_text('{"score": 2}\n', encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(VERIFY), "--root", str(root), "--manifest", "manifest.json", "--independent-node", "node-d", "--out", str(root / "bad.json")],
            text=True,
            capture_output=True,
        )
        assert proc.returncode != 0
    print("ARTIFACT_BUNDLE_EVAL_OK accepted=2 crossnode_match=1 independence_rejected=2 corruption_rejected=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
