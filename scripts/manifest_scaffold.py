#!/usr/bin/env python3
"""Scaffold the empty, version-controlled result-store skeleton (references/delivering/data-architecture.md).

The delivering data architecture (references/delivering/data-architecture.md) makes the whole deliverable a deterministic
function of an immutable, content-addressed evidence layer. This script lays down that layer's
empty skeleton for a project so the directories and the EVIDENCE.json single-source-of-truth
exist before any run writes into them. It creates structure only -- it never invents metrics,
runs, or figures.

Layout created (per references/delivering/data-architecture.md):

    <project>/
      EVIDENCE.json                       project-level single source of truth (stub)
      results/<exp-id>/
        runs/                             append-only run dirs land here (one per (re)run)
        splits/                           split ids + manifest (split as a first-class citizen)
        .gitkeep                          (keeps the otherwise-empty dirs in version control)
      figures/                            project-level, cross-exp-id figures (one dir per figure)

`runs/<run-id>/`, `figures/<name>/`, `qualitative/...` are filled per-run / per-figure by the
pipeline, not pre-created here. A "light vs heavy" disk policy (references/delivering/data-architecture.md) is a runtime
choice, not a scaffold concern. Pure stdlib, no third-party deps.

Usage:
    python manifest_scaffold.py --root <project> --exp-id baseline
    python manifest_scaffold.py --root . --exp-id ablation_no_aux --dry-run   # PRINT tree, create nothing

Exit code:
    0 = scaffold created (or dry-run printed) successfully.
    1 = usage / IO error, or a refusal to overwrite an existing EVIDENCE.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# EVIDENCE.json stub: the project-level machine-readable claims<->evidence ledger
# (references/delivering/evidence-manifest-schema.md). Empty `claims` -- the pipeline appends
# records, each binding a claim DOWN to its evidence (exp-id / metric / value / split), UP to a
# paper anchor, and ACROSS to the repo file:line that implements it.
EVIDENCE_STUB: dict = {
    "project": None,  # filled with the project name below
    "authoritative_source": (
        "Each reported number's truth value is the results.json its claim points to; "
        "documents must match it, never the reverse."
    ),
    "schema_version": "1.0",
    "claims": [
        # Example claim shape (delete this comment + append real claims as results land). The
        # authoritative scalar is NESTED under evidence[] -- reconcile.py reads claims[].evidence[].value
        # + metric. Full schema: references/delivering/evidence-manifest-schema.md
        # {
        #   "id": "C1-main-psnr",
        #   "statement": "Our full model improves PSNR over the baseline on the test split.",
        #   "evidence": [
        #     {
        #       "exp_id": "ours-full", "run": "selected",
        #       "metric": "PSNR", "direction": "higher_is_better",
        #       "value": 31.42, "split": "test", "n": 100,
        #       "variance": {"type": "std", "value": 0.08, "seeds": 3},
        #       "results_json": "results/ours-full/selected/results.json",
        #       "figure": "figures/main-comparison"
        #     }
        #   ],
        #   "paper_anchor": "Sec 4.2, Table 2, row Ours-full",
        #   "repo_implementation": "src/models/ours.py:142",
        #   "disclosure": null
        # }
    ],
}


def build_tree(root: Path, exp_id: str) -> tuple[list[Path], list[Path]]:
    """Return (directories, files) the scaffold consists of, without touching disk.

    Splitting plan-from-action keeps --dry-run honest: the same description is printed or created.
    """
    exp_root = root / "results" / exp_id
    dirs = [
        root,
        root / "results",
        exp_root,
        exp_root / "runs",
        exp_root / "splits",
        root / "figures",
    ]
    files = [
        root / "EVIDENCE.json",
        exp_root / "runs" / ".gitkeep",
        exp_root / "splits" / ".gitkeep",
        root / "figures" / ".gitkeep",
    ]
    return dirs, files


def render_tree(root: Path, exp_id: str) -> str:
    """ASCII rendering of the skeleton, for --dry-run."""
    return (
        f"{root}/\n"
        f"  EVIDENCE.json                 (project single source of truth -- stub)\n"
        f"  results/\n"
        f"    {exp_id}/\n"
        f"      runs/                      (append-only run dirs land here)\n"
        f"        .gitkeep\n"
        f"      splits/                    (split ids + manifest; first-class citizen)\n"
        f"        .gitkeep\n"
        f"  figures/                       (project-level, cross-exp-id; one dir per figure)\n"
        f"    .gitkeep\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create the empty result-store skeleton (references/delivering/data-architecture.md) for a project.",
    )
    ap.add_argument("--root", default=".", help="project root to scaffold under (default: cwd)")
    ap.add_argument(
        "--exp-id",
        required=True,
        help="descriptive ablation/experiment id (your checkpoints/ naming, e.g. 'baseline', 'no_aux')",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="PRINT the tree that would be created and exit -- create nothing on disk",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing EVIDENCE.json (default: refuse, to protect the source of truth)",
    )
    a = ap.parse_args()

    root = Path(a.root)
    exp_id = a.exp_id

    if a.dry_run:
        print("DRY RUN -- nothing will be created. Tree that WOULD be scaffolded:\n")
        print(render_tree(root, exp_id))
        return 0

    dirs, files = build_tree(root, exp_id)
    evidence_path = root / "EVIDENCE.json"

    if evidence_path.exists() and not a.force:
        print(
            f"ERROR: {evidence_path} already exists -- refusing to overwrite the project source of truth.\n"
            f"       Pass --force only if you are sure you want to reset it."
        )
        return 1

    try:
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.name == "EVIDENCE.json":
                stub = dict(EVIDENCE_STUB)
                stub["project"] = root.resolve().name
                f.write_text(json.dumps(stub, indent=2) + "\n", encoding="utf-8")
            else:
                # .gitkeep: create only if absent, never clobber
                if not f.exists():
                    f.write_text("", encoding="utf-8")
    except OSError as e:
        print(f"ERROR: failed to create scaffold: {e}")
        return 1

    print(f"Scaffolded result store under {root}/ for exp-id '{exp_id}':")
    print(render_tree(root, exp_id))
    print("Next: runs land in results/<exp-id>/runs/<run-id>/ (append-only); add claims to EVIDENCE.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
