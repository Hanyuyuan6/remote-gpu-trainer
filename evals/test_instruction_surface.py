#!/usr/bin/env python3
"""Regression for a small entrypoint and honest monitor durability claims."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    entry = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    entry_bytes = len(entry.encode("utf-8"))
    entry_lines = len(entry.splitlines())
    assert entry_bytes <= 16_384, f"remote-gpu-trainer entrypoint grew to {entry_bytes} bytes"
    assert entry_lines <= 180, f"remote-gpu-trainer entrypoint grew to {entry_lines} lines"

    # Only retired false claims are pinned, so rewording the live text never fails this check.
    control = (ROOT / "references" / "run-remote" / "control-economy.md").read_text(encoding="utf-8")
    lifecycle = (ROOT / "references" / "run-remote" / "lifecycle_checklist.md").read_text(
        encoding="utf-8"
    )
    normative = "\n".join((entry, control, lifecycle, (ROOT / "references" / "run-remote" / "principles.md").read_text(encoding="utf-8")))
    for forbidden in (
        "are pulled to local AND verified by load",
        "every reported result re-reads from the local copy",
    ):
        assert forbidden not in normative, f"stale universal local-residency gate returned: {forbidden}"

    monitoring = (ROOT / "references" / "run-remote" / "monitoring_patterns.md").read_text(encoding="utf-8")
    for forbidden in (
        "auto-re-invokes across idle/teardown",
        "PRIMARY wake: poll the real condition",
        "task chip remains visible after the process is gone. One layer",
    ):
        assert forbidden not in monitoring, f"stale durability promise returned: {forbidden}"

    cases = [
        json.loads(line)
        for line in (ROOT / "evals" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    routed = sum(
        "references/run-remote/control-economy.md" in case.get("expect_files", []) for case in cases
    )
    assert routed >= 16, f"only {routed} control-economy regressions follow the new route"
    print(f"REMOTE_INSTRUCTION_SURFACE_OK bytes={entry_bytes} lines={entry_lines} routed={routed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
