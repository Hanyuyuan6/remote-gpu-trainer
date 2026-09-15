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
    for marker in (
        "Start with the outcome, not a package",
        "Consequence-based assurance",
        "references/run-remote/control-economy.md",
        "A UI spinner is not a watcher",
        "Load only the resource named by the current route",
        "independent temporary consumer",
        "full prediction population",
        "resident Mac `.pth`",
    ):
        assert marker in entry, f"missing compact-entrypoint marker: {marker}"

    control = (ROOT / "references" / "run-remote" / "control-economy.md").read_text(encoding="utf-8")
    for marker in (
        "one initial package plus one successor",
        "storage-pressure recovery ladder",
        "Postcheck the identity that actually ran",
        "Retire provisional prohibitions",
        "independently restored temporary",
        "full-prediction semantic re-derivation",
    ):
        assert marker in control, f"missing on-demand control marker: {marker}"

    lifecycle = (ROOT / "references" / "run-remote" / "lifecycle_checklist.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "not a universal custody requirement",
        "canonical remote URI",
        "full-prediction metric recomputation",
    ):
        assert marker in lifecycle, f"missing remote-thin teardown marker: {marker}"
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
    for marker in (
        "Product names are not durability evidence",
        "L3 is a notification adapter, never the source of truth",
        "unknown defaults fail to L1 + L4, not to an active spinner",
    ):
        assert marker in monitoring, f"missing durability truth marker: {marker}"

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
