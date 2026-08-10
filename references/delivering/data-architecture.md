# Delivering — legacy/non-canonical publication synthesis guidance

This reference preserves publication-synthesis ideas from the older DELIVER layer. It does **not** own the
project or run directory layout. `research-artifact-hygiene` owns the canonical artifact architecture; its
current deep-learning layout and validators override every directory example anywhere under
`references/delivering/`.

Use this file only to turn already accepted canonical evidence into figures, tables, and claim mappings.
Never use it to invent a second run root, checkpoint namespace, qualitative tree, selection pointer, or
workshop portal.

## Canonical inputs (read-only here)

Software evidence arrives as immutable canonical runs:

```text
runs/<run-id>/
  run.json
  config.yaml
  train.csv
  best.pth
  last.pth?                         # optional frozen checkpoint
  test/<test-id>/
    metrics.json
    results.parquet
    vis/<condition-id>/<task-native-role>/<sample-id>.png
```

Every declared software test has complete declared
conditions × task-native roles × K visualization coverage. K and the immutable roster come from the
selection manifest bound by path/hash in `run.json`; no visualization index or selected symlink is added.
Dataset and split bytes remain outside the run and are referenced by immutable identities/hashes.

Hardware evidence remains separate and contains no duplicate weights:

```text
hardware/captures/<capture-id>/...
hardware/decodes/<decode-id>/...     # only when promotion is justified
hardware/runs/<hardware-run-id>/
  run.json
  test/<test-id>/
    metrics.json
    results.parquet
    vis/<condition-id>/<task-native-role>/<sample-id>.png
```

The hardware `run.json` binds the capture/decode identities, same-task model-run identity and `best.pth`
hash. This legacy publication layer consumes those records; it never copies weights into `hardware/`. A
declared no-machine-readable-GT test uses finite-forward rows and prediction/overlay visuals with metrics
marked not applicable; it never manufactures a ground-truth role or GT-derived scalar.

## Flat figure and table workshops

Publication synthesis writes only the canonical flat workshops:

```text
figures/<figure-id>/
  figure.json                      # provenance, build command, QA and final-output hashes
  data.csv                         # data figure, full precision
  source.pptx                      # non-data diagram or qualitative montage
  build.py
  final.*

tables/<table-id>/
  table.json                       # provenance, build command, QA and final-output hashes
  data.csv
  build.py
  final.*
```

Choose `data.csv` for a quantitative artifact and `source.pptx` for a non-data diagram or derived qualitative
montage; do not add empty placeholders for both. `figure.json`/`table.json` is the single contract and binds
root-level source hashes, `build.py`, QA results, provenance and every `final.*` hash.

There are no nested `source/`, `output/`, `qa/`, draft, or cache directories. A workshop has no README
portal and no separate `.provenance` sidecar. A qualitative montage cites existing canonical atomic PNG
paths/hashes and never replaces their full per-test roster.

## P1 synthesis flow

1. Select accepted canonical run/hardware test IDs without mutating them or introducing a `selected` link.
2. Read aggregates from `test/<test-id>/metrics.json` and full-precision rows from
   `test/<test-id>/results.parquet`; never transcribe console or tracker values.
3. Read qualitative inputs only from the canonical
   `test/<test-id>/vis/<condition-id>/<task-native-role>/<sample-id>.png` roster.
4. Generate root-level workshop inputs and `final.*` deterministically with `build.py`.
5. Record claim/evidence references, build command, hashes, parse/render/editability QA and output hashes in
   the workshop JSON. Project claims/trust records stay in the canonical `_trust` layout owned by
   `research-artifact-hygiene`.
6. Re-open the finished artifact and verify pixels/content before treating the synthesis as deliverable.

This keeps P1's evidence/presentation boundary: immutable `runs/` and `hardware/runs/` are evidence;
`figures/` and `tables/` are derived presentation workshops. A presentation failure never edits its evidence.

## Explicitly rejected legacy paths

Reject `results/<exp-id>/runs/<run-id>` as a second run root. Reject
`checkpoints/{best,last}`, `qualitative/`, and `selected -> runs/<run-id>` inside publication synthesis.
Reject figure `README.md`, nested `output/`, and standalone `<figure-id>.provenance` layouts. They are
historical concepts, not aliases or migration targets for canonical artifacts.

Re-running mints a new canonical `runs/<run-id>`; selection decisions are recorded through canonical trust
records and claim mappings, never by repointing a filesystem symlink. `best.pth` and optional frozen
`last.pth` remain root-level within the immutable run.

## Boundary with the rest of the legacy DELIVER group

All files under `references/delivering/` are legacy/non-canonical publication synthesis guidance. Their
principles may help with generated-not-transcribed reporting, disclosure, figure QA and claim reconciliation,
but any directory name, manifest name or retention example in them is advisory history only. When it differs
from `research-artifact-hygiene`, follow the latter and its machine validators.
