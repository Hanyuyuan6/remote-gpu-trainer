#!/usr/bin/env python3
"""Verify a producer artifact manifest and optionally safe-load checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import sys
import time


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected JSON object")
    return value


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe relative path in manifest: {value!r}")
    return path


def resolve_under_root(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"manifest path escapes root through a symlink: {relative!r}") from exc
    return candidate


def expected_size(record: dict, relative: str) -> int:
    for key in ("size_bytes", "bytes", "size"):
        if key in record:
            value = record[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{relative}: invalid {key}")
            return value
    raise ValueError(f"{relative}: no size field")


def inspect_checkpoint(path: Path, allow_numpy_metadata: bool) -> dict:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required when --checkpoint is used") from exc

    safe_types: list[object] = []
    safe_type_names: list[str] = []
    if allow_numpy_metadata:
        try:
            import numpy as np
            from numpy.core.multiarray import scalar as numpy_scalar
        except ImportError as exc:
            raise RuntimeError("NumPy is required for --allow-numpy-metadata") from exc
        safe_types = [numpy_scalar, np.dtype, type(np.dtype(np.float64))]
        safe_type_names = [
            "numpy.core.multiarray.scalar",
            "numpy.dtype",
            type(np.dtype(np.float64)).__qualname__,
        ]

    if safe_types:
        with torch.serialization.safe_globals(safe_types):
            value = torch.load(path, map_location="cpu", weights_only=True)
    else:
        value = torch.load(path, map_location="cpu", weights_only=True)

    tensor_count = 0
    tensor_numel = 0
    nonfinite = []
    stack = [("root", value)]
    visited: set[int] = set()
    while stack:
        label, item = stack.pop()
        if isinstance(item, torch.Tensor):
            tensor_count += 1
            tensor_numel += item.numel()
            if (item.is_floating_point() or item.is_complex()) and not torch.isfinite(item).all():
                nonfinite.append(label)
            continue
        if isinstance(item, dict):
            identity = id(item)
            if identity in visited:
                continue
            visited.add(identity)
            stack.extend((f"{label}.{key}", child) for key, child in item.items())
        elif isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in visited:
                continue
            visited.add(identity)
            stack.extend((f"{label}[{index}]", child) for index, child in enumerate(item))
    if tensor_count == 0:
        raise RuntimeError(f"{path}: checkpoint contains no tensors")
    if nonfinite:
        raise RuntimeError(f"{path}: non-finite tensors: {nonfinite[:10]}")
    return {
        "sha256": sha256_file(path),
        "safe_weights_only_load": True,
        "safe_globals": safe_type_names,
        "tensor_count": tensor_count,
        "tensor_numel": tensor_numel,
        "torch": torch.__version__,
    }


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--required", action="append", default=[])
    parser.add_argument("--checkpoint", action="append", default=[])
    parser.add_argument("--allow-numpy-metadata", action="store_true")
    parser.add_argument("--independent-node", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    started = time.time()
    root = args.root.resolve()
    independent_node = args.independent_node.strip()
    if not independent_node:
        raise ValueError("--independent-node must be non-empty")
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    manifest_path = manifest_path.resolve()
    manifest = read_object(manifest_path)
    records = manifest.get("files")
    if not isinstance(records, dict) or not records:
        raise RuntimeError("manifest.files must be a non-empty object")
    producer_node = manifest.get("producer_node") or manifest.get("node") or manifest.get("host")
    if producer_node is not None and str(producer_node).strip() == independent_node:
        raise RuntimeError("independent verifier node must differ from the producer node")

    normalized: dict[str, dict] = {}
    for raw_relative, record in records.items():
        relative = safe_relative(str(raw_relative)).as_posix()
        if relative in normalized:
            raise RuntimeError(f"duplicate normalized path: {relative}")
        if not isinstance(record, dict):
            raise TypeError(f"{relative}: file record must be an object")
        normalized[relative] = record

    required = {safe_relative(item).as_posix() for item in args.required}
    missing_from_manifest = sorted(required - set(normalized))
    if missing_from_manifest:
        raise RuntimeError(f"required files absent from manifest: {missing_from_manifest}")

    verified: dict[str, dict] = {}
    for relative, record in sorted(normalized.items()):
        path = resolve_under_root(root, relative)
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        expected = expected_size(record, relative)
        digest = sha256_file(path)
        wanted = record.get("sha256")
        if not isinstance(wanted, str) or len(wanted) != 64:
            raise ValueError(f"{relative}: invalid sha256")
        if size != expected or digest.lower() != wanted.lower():
            raise RuntimeError(f"hash/size mismatch: {relative}")
        verified[relative] = {"size_bytes": size, "sha256": digest}

    checkpoint_results: dict[str, dict] = {}
    for raw_relative in args.checkpoint:
        relative = safe_relative(raw_relative).as_posix()
        if relative not in normalized:
            raise RuntimeError(f"checkpoint absent from manifest: {relative}")
        checkpoint_results[relative] = inspect_checkpoint(
            resolve_under_root(root, relative), args.allow_numpy_metadata
        )

    payload = {
        "schema": "artifact-bundle-independent-acceptance-v1",
        "status": "accepted",
        "artifact_id": manifest.get("artifact_id") or manifest.get("job_id") or manifest.get("cell_id"),
        "producer_node": producer_node,
        "independent_node": independent_node,
        "manifest_sha256": sha256_file(manifest_path),
        "verified_files": verified,
        "checkpoints": checkpoint_results,
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "elapsed_seconds": time.time() - started,
        },
        "boundary": (
            "This acceptance proves manifest-bound file identity and optional weights_only checkpoint "
            "integrity. It does not prove metric semantics or rerun inference."
        ),
    }
    atomic_json(args.out.resolve(), payload)
    print(
        f"ARTIFACT_ACCEPTED id={payload['artifact_id']} files={len(verified)} "
        f"checkpoints={len(checkpoint_results)} manifest_sha256={payload['manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
