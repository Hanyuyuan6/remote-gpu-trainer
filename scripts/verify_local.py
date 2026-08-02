#!/usr/bin/env python3
"""Verify integrity and remote provenance of downloaded checkpoint directories.

For each <name>/ in the target dir, check:
  - best.pth exists
  - best.pth loads cleanly via torch.load
  - best.pth contains a weights key ('model_state_dict' / 'model' / 'state_dict')
  - best_metrics.json exists and is valid JSON
  - reports best epoch + main metric per ablation

The default teardown gate requires ``PULL_MANIFEST.json`` in the result root.
That manifest binds an immutable run id to the exact remote roster, sizes, and
SHA-256 digests.  Success writes ``PULL_VERIFIED.json`` beside the data.

Usage:
    python verify_local.py <path_to_final_ckpts_dir> [--manifest PATH] [--expect N] [--list-metrics]

Exit code:
    0 = all OK
    1 = at least one error, an empty input dir, or a dir count != --expect
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_SCHEMA = "remote-gpu-trainer/PULL/v1"
MANIFEST_NAME = "PULL_MANIFEST.json"
VERIFICATION_NAME = "PULL_VERIFIED.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(root: Path, manifest_path: Path) -> tuple[dict | None, list[str]]:
    """Validate schema, exact roster, sizes, and digests before loading checkpoints."""
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"manifest unreadable: {exc}"]

    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append(f"manifest schema must be {MANIFEST_SCHEMA!r}")
    if not isinstance(manifest.get("run_id"), str) or not manifest["run_id"].strip():
        errors.append("manifest run_id must be a non-empty string")

    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        errors.append("manifest files must be a non-empty list")
        return manifest, errors

    expected: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"manifest files[{index}] is not an object")
            continue
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
            errors.append(f"manifest files[{index}] has an unsafe path")
            continue
        normalized = Path(relative).as_posix()
        if normalized in expected:
            errors.append(f"manifest contains duplicate path: {normalized}")
            continue
        expected[normalized] = entry

    ignored = {manifest_path.resolve(), (root / VERIFICATION_NAME).resolve()}
    actual = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path.resolve() not in ignored and not path.name.endswith(".tmp")
    }
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    errors.extend(f"manifest file missing locally: {path}" for path in missing)
    errors.extend(f"unexpected local file not in remote manifest: {path}" for path in unexpected)

    for relative in sorted(set(expected) & set(actual)):
        entry = expected[relative]
        path = actual[relative]
        expected_size = entry.get("bytes")
        expected_hash = entry.get("sha256")
        if not isinstance(expected_size, int) or expected_size < 0:
            errors.append(f"manifest has invalid byte size for {relative}")
            continue
        if path.stat().st_size != expected_size:
            errors.append(
                f"size mismatch for {relative}: expected {expected_size}, found {path.stat().st_size}"
            )
            continue
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            errors.append(f"manifest has invalid sha256 for {relative}")
            continue
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash.lower():
            errors.append(f"sha256 mismatch for {relative}")

    return manifest, errors


def write_verification(root: Path, manifest_path: Path, manifest: dict) -> Path:
    marker = root / VERIFICATION_NAME
    payload = {
        "schema": "remote-gpu-trainer/PULL-VERIFIED/v1",
        "run_id": manifest["run_id"],
        "manifest_sha256": sha256_file(manifest_path),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": len(manifest["files"]),
        "bytes": sum(item["bytes"] for item in manifest["files"]),
    }
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, marker)
    return marker


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt_dir", help="Directory containing ablation subdirs (each with best.pth + best_metrics.json)")
    ap.add_argument("--list-metrics", action="store_true", help="Print per-ablation epoch + main metric")
    ap.add_argument("--expect", type=int, default=None,
                    help="Assert exactly N ablation subdirs are present -- guards a teardown gate against a partial/empty pull")
    ap.add_argument("--allow-pickle", action="store_true",
                    help="Permit the weights_only=False fallback (executes pickle) for checkpoints you trust -- "
                         "needed only when a checkpoint pickles non-tensor objects (e.g. an args Namespace); OFF by default")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="Remote manifest path; defaults to <ckpt_dir>/PULL_MANIFEST.json and is mandatory")
    args = ap.parse_args()

    root = Path(args.ckpt_dir)
    if not root.exists():
        print(f"ERROR: {root} does not exist")
        return 1
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory")
        return 1

    manifest_path = (args.manifest or root / MANIFEST_NAME).resolve()
    if not manifest_path.is_file():
        print(f"ERROR: required remote manifest not found: {manifest_path}")
        return 1
    manifest, manifest_errors = validate_manifest(root.resolve(), manifest_path)
    if manifest_errors:
        print("ERROR: remote-to-local manifest verification failed")
        for error in manifest_errors[:50]:
            print(f"  - {error}")
        return 1

    # Structural checks BEFORE importing torch: an empty (or short) input must fail
    # LOUDLY here -- never silently print "OK: 0/0" and return success, which would let
    # a Phase-5 teardown gate destroy the rented disk having verified nothing
    # (principle #3: trust the artifact, not a success line; the teardown Iron Law).
    dirs = sorted([d for d in root.iterdir() if d.is_dir()])
    if not dirs:
        print(f"ERROR: no ablation subdirectories found in {root} -- refusing to report success on an empty input")
        return 1
    if args.expect is not None and len(dirs) != args.expect:
        print(f"ERROR: expected {args.expect} ablation dirs but found {len(dirs)} in {root} -- partial/incomplete pull")
        return 1

    try:
        import torch
    except ImportError:
        print("ERROR: torch not installed in this environment")
        return 1

    print(f"Found {len(dirs)} ablation dirs in {root}")
    print()

    ok = 0
    errors: list[tuple[str, str]] = []
    metrics_rows: list[tuple[str, int, str]] = []
    total_size_bytes = 0

    for d in dirs:
        name = d.name
        pth = d / "best.pth"
        metrics_path = d / "best_metrics.json"

        if not pth.exists():
            errors.append((name, "missing best.pth"))
            continue
        if not metrics_path.exists():
            errors.append((name, "missing best_metrics.json"))
            continue

        # Load safe-by-default: weights_only=True refuses to execute pickle, so a poisoned or
        # compromised remote checkpoint cannot run code on the operator's machine. The unsafe
        # weights_only=False path (which DOES execute pickle) is OPT-IN via --allow-pickle: an attacker
        # who controls the remote file could otherwise craft one that fails the safe load to FORCE the
        # fallback, so auto-falling-back would defeat the gate. Pass --allow-pickle ONLY for your own ckpts.
        try:
            ckpt = torch.load(pth, map_location="cpu", weights_only=True)
        except Exception as e_safe:
            if not args.allow_pickle:
                errors.append((name, f"safe load (weights_only=True) failed: {str(e_safe)[:70]} "
                                     "-- re-run with --allow-pickle if this is your own checkpoint"))
                continue
            try:
                print(
                    f"  [warn] {name}: weights_only=True failed; --allow-pickle set, retrying "
                    "weights_only=False (executes pickle -- trust this file)"
                )
                ckpt = torch.load(pth, map_location="cpu", weights_only=False)
            except Exception as e:
                errors.append((name, f"torch.load failed: {str(e)[:100]}"))
                continue

        if not isinstance(ckpt, dict) or not any(k in ckpt for k in ("model_state_dict", "model", "state_dict")):
            errors.append((name, "no model/model_state_dict/state_dict key in checkpoint"))
            continue

        try:
            with open(metrics_path) as f:
                m = json.load(f)
        except Exception as e:
            errors.append((name, f"best_metrics.json invalid: {str(e)[:80]}"))
            continue

        epoch = m.get("epoch", "?")
        if epoch is None:  # {"epoch": null} → .get returns None (not the default); guard the :3 format. `or` would wrongly eat epoch 0.
            epoch = "?"
        # Pick main metric (PSNR for recon, mAP50 for det, dice for seg, fall back to loss)
        main_metric_key = next(
            (k for k in ["psnr", "mAP50", "dice"] if k in m),
            "loss",
        )
        main_metric_val = m.get(main_metric_key, "?")
        metrics_rows.append((name, epoch, f"{main_metric_key}={main_metric_val}"))

        total_size_bytes += pth.stat().st_size
        ok += 1

    print(f"OK: {ok}/{len(dirs)}")
    print(f"Errors: {len(errors)}")
    for name, err in errors[:20]:
        print(f"  - {name}: {err}")
    print(f"Total best.pth size: {total_size_bytes / 1e9:.1f} GB")

    if args.list_metrics:
        print()
        print("=== Per-ablation metrics ===")
        for name, epoch, metric in metrics_rows:
            print(f"  {name:40s} epoch={epoch:3} {metric}")

    if errors:
        return 1

    marker = write_verification(root.resolve(), manifest_path, manifest or {})
    print(f"PULL VERIFIED: {marker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
