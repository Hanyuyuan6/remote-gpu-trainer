#!/usr/bin/env python3
"""Tests for reconcile.py -- the cross-document number-drift checker (references/verifying/methodology.md section 14).

Contract under test:
  reconcile reads the AUTHORITATIVE scalar values out of EVIDENCE.json (the project-level
  single source of truth) and greps a list of presentation-layer docs (paper / thesis / slides
  / README / CSV) for every place a metric is reported. Any reported value that diverges from
  its authoritative source is a "drift". A doc that quotes the authoritative value exactly is
  clean (0 drift).

Run:
    python -m pytest scripts/test_reconcile.py -v
    # or, with no pytest installed:
    python scripts/test_reconcile.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Import the module under test from the same directory, regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reconcile  # noqa: E402


def _write_evidence(d: Path, claims: list[dict]) -> Path:
    """Write a minimal EVIDENCE.json with the given claim records, return its path."""
    evidence = {
        "schema": "remote-gpu-trainer/EVIDENCE/v1",
        "project": "drift-test",
        "claims": claims,
    }
    p = d / "EVIDENCE.json"
    p.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return p


class TestReconcile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        # One authoritative claim whose scalar is NESTED under evidence[] (the real schema):
        # metric "psnr_set5" with authoritative value 31.42.
        self.evidence = _write_evidence(
            self.dir,
            [
                {
                    "id": "C1",
                    "statement": "Our method's PSNR on Set5.",
                    "paper_anchor": "Table 2, row 1",
                    "repo_implementation": "src/eval.py:88",
                    "evidence": [
                        {
                            "exp_id": "baseline",
                            "run": "selected",
                            "metric": "psnr_set5",
                            "value": 31.42,
                            "split": "test",
                            "results_json": "results/baseline/selected/results.json",
                        }
                    ],
                }
            ],
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_drift_detected(self) -> None:
        """A doc reporting 31.50 against authoritative 31.42 yields exactly one drift."""
        paper = self.dir / "paper.md"
        paper.write_text(
            "Our method reaches a PSNR of 31.50 on Set5, a clear improvement.\n",
            encoding="utf-8",
        )

        drifts = reconcile.reconcile(self.evidence, [paper])

        self.assertEqual(len(drifts), 1, f"expected exactly 1 drift, got {drifts!r}")
        d = drifts[0]
        self.assertEqual(d.metric, "psnr_set5")
        self.assertEqual(d.authoritative, 31.42)
        self.assertEqual(d.reported, 31.50)
        self.assertEqual(Path(d.doc), paper)

    def test_correct_value_no_drift(self) -> None:
        """A doc quoting the authoritative 31.42 exactly yields zero drift."""
        readme = self.dir / "README.md"
        readme.write_text(
            "We report PSNR 31.42 on Set5 (see EVIDENCE.json, claim C1).\n",
            encoding="utf-8",
        )

        drifts = reconcile.reconcile(self.evidence, [readme])

        self.assertEqual(len(drifts), 0, f"expected 0 drift, got {drifts!r}")

    def test_clean_and_dirty_doc_together(self) -> None:
        """Mixed input: only the doc with the wrong value is flagged."""
        good = self.dir / "README.md"
        good.write_text("PSNR 31.42 on Set5.\n", encoding="utf-8")
        bad = self.dir / "paper.md"
        bad.write_text("PSNR 31.50 on Set5.\n", encoding="utf-8")

        drifts = reconcile.reconcile(self.evidence, [good, bad])

        self.assertEqual(len(drifts), 1)
        self.assertEqual(Path(drifts[0].doc), bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
