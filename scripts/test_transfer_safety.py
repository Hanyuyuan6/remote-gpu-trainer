#!/usr/bin/env python3
"""Regression tests for the fail-closed remote pull/teardown chain."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module("build_pull_manifest", "build_pull_manifest.py")
verifier = load_module("verify_local", "verify_local.py")


class TransferSafetyTests(unittest.TestCase):
    def make_bundle(self, root: Path, names=("baseline", "ablation")) -> list[str]:
        for index, name in enumerate(names):
            directory = root / name
            directory.mkdir(parents=True)
            (directory / "best.pth").write_bytes(f"checkpoint-{index}".encode())
            (directory / "best_metrics.json").write_text(
                json.dumps({"epoch": index + 1, "psnr": 30.0 + index}),
                encoding="utf-8",
            )
        return list(names)

    def test_exact_manifest_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = self.make_bundle(root)
            manifest_path = builder.write_manifest(root, "sweep-001", names)
            manifest, errors = verifier.validate_manifest(root.resolve(), manifest_path.resolve())
            self.assertEqual([], errors)
            self.assertEqual("sweep-001", manifest["run_id"])
            self.assertEqual(4, manifest["totals"]["files"])

    def test_partial_or_tampered_pull_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = self.make_bundle(root)
            manifest_path = builder.write_manifest(root, "sweep-002", names)
            (root / "baseline" / "best.pth").write_bytes(b"tampered")
            _manifest, errors = verifier.validate_manifest(root.resolve(), manifest_path.resolve())
            self.assertTrue(any("mismatch" in error for error in errors), errors)

    def test_stale_extra_file_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = self.make_bundle(root)
            manifest_path = builder.write_manifest(root, "sweep-003", names)
            (root / "baseline" / "old-result.json").write_text("{}", encoding="utf-8")
            _manifest, errors = verifier.validate_manifest(root.resolve(), manifest_path.resolve())
            self.assertTrue(any("unexpected local file" in error for error in errors), errors)

    def test_empty_bundle_and_wrong_roster_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "no result directories"):
                builder.build_manifest(root, "sweep-004", ["baseline"])
            self.make_bundle(root, ("baseline",))
            with self.assertRaisesRegex(ValueError, "roster mismatch"):
                builder.build_manifest(root, "sweep-004", ["baseline", "missing"])


if __name__ == "__main__":
    unittest.main()
