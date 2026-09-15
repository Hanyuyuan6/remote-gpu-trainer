# Delivering — legacy/non-canonical publication synthesis guidance

The former DELIVER layer (principles, data-architecture, evidence-manifest schema, figures, delivery
gate, completeness reconciliation) is retired and compressed into this single file. It is optional
synthesis guidance for turning **already accepted** canonical evidence into figures, tables, and claim
mappings — never an artifact-layout specification. `research-artifact-hygiene` owns the canonical
layout, schemas, and validators; wherever this legacy text differs, follow it and its machine
validators. The old DELIVER manifest examples are retired and **NON_CANONICAL_DO_NOT_EXECUTE**; never
use them to invent a second run root, checkpoint namespace, qualitative tree, selection pointer, or
workshop portal.

## Key points (compressed)

- **Generate, do not transcribe.** Tables and plots read accepted machine artifacts — aggregates from
  `test/<test-id>/metrics.json`, full-precision rows from `test/<test-id>/results.parquet`, qualitative
  inputs only from the canonical `vis/<condition-id>/<task-native-role>/<sample-id>.png` roster — never
  console text, tracker summaries, screenshots, or recollection. Recompute aggregates from
  `results.parquet` and compare with `metrics.json` at declared precision.
- **Evidence is immutable.** Re-evaluation mints a new run or verification record; a failed
  presentation build never edits, renames, duplicates, selects, or repairs its evidence.
- **Workshops.** Build `figures/<figure-id>` / `tables/<table-id>` deterministically with `build.py`
  after verifying input hashes; choose `data.csv` for a quantitative artifact or `source.pptx` for a
  diagram/montage, not empty placeholders for both; re-open every `final.*` before treating the
  synthesis as deliverable. A qualitative montage cites existing canonical atomic PNG paths/hashes and
  never replaces mandatory coverage.
- **No-GT hardware figures.** When a hardware test declares metrics not applicable because no
  machine-readable ground truth exists, a figure may show finite-forward predictions/overlays but may
  not derive or label accuracy, AP, IoU, or a ground-truth comparison — never manufacture a
  ground-truth role or GT-derived scalar.
- **Reconciliation.** Enumerate every claim, table cell, figure panel, and qualitative example; resolve
  each to its canonical `runs/<run-id>/test/<test-id>` or `hardware/runs/<hardware-run-id>/test/<test-id>`
  source; confirm metric name, direction, split, N, seed/determinism declaration, protocol, selection
  path/hash, checkpoint hash, and source rows. Use precise states (`planned_not_started`, `launched`,
  `trained`, `evaluated`, `hash_verified`, `pull_verified`, `paper_supported`); a later state requires
  its own evidence and is never inferred from an earlier one. Absent, partial, failed, and unverified
  work stays explicit.
- **Transport inventory is external.** Do not duplicate the mirror boundary's roster/byte/hash
  inventory in canonical `run.json` (scientific bindings only) or in presentation metadata.

## Delivery gate (retained verbatim)

- Every reported scalar resolves to an accepted software or hardware run, declared test, metric, split,
  selection binding, and immutable source hash.
- Each software capsule has root-level `run.json`, `config.yaml`, `train.csv`, `best.pth`, optional frozen
  `last.pth`, and one or more complete `test/<test-id>` directories.
- Every declared test has `metrics.json`, `results.parquet`, and mandatory complete
  `vis/<condition-id>/<applicable-task-role>/<sample-id>.png` coverage. Explicit no-machine-readable-GT
  hardware tests mark metrics not applicable, preserve finite-forward rows, and forbid invented ground truth.
- The roster is bound by a versioned `selection_id`; schema 2 keeps its original model-blind semantics.
  Schema 3 is an explicitly approved main-model reconstruction-PSNR Top 100 for qualitative examples only,
  with its exact MNIST test K=512 clean float32 protocol, model/config/checkpoint hashes, complete unrounded
  score source and population, descending-score/sample-ID-tie order, and one ordered roster reused across
  methods, conditions, and reconstruction/segmentation/detection. It cannot support typical, overall,
  fairness, or unbiased-comparison claims. K = min(100, N_test); full-test metrics remain full-population,
  and no-GT data uses a separate explicit roster without PSNR.
- Real-capture outputs live only in `hardware/runs/<hardware-run-id>`, bind capture/decode/model-run and
  checkpoint hash, and duplicate no weights.
- Each `figures/<figure-id>` and `tables/<table-id>` workshop is flat, deterministic, and has one JSON
  contract covering inputs, build command, QA, provenance, and final hashes.
- Numeric source data retains full precision; display rounding occurs only at render time.
- Rendered outputs have been reopened and inspected; parse/render/editability checks are recorded.
- Claims distinguish completed, independently verified, pulled/hash-verified, paper-supported, and planned
  work. Missing or failed evidence is disclosed rather than imputed.
- Historical project-native checkpoint identities may be cited only through a validated
  `supervise-research-closeout` legacy acceptance record with declared gaps; that bridge is not canonical
  capsule acceptance and does not force a closeout-time rerun.
- The exact-roster/byte inventory is external to `run.json` and is frozen/validated by the generic mirror
  boundary.

Any failed item blocks publication synthesis but does not authorize changing, deleting, or overwriting the
underlying evidence.

## Explicitly rejected legacy paths (retained verbatim)

Reject `results/<exp-id>/runs/<run-id>` as a second run root. Reject
`checkpoints/{best,last}`, `qualitative/`, and `selected -> runs/<run-id>` inside publication synthesis.
Reject figure `README.md`, nested `output/`, and standalone `<figure-id>.provenance` layouts. They are
historical concepts, not aliases or migration targets for canonical artifacts.

Re-running mints a new canonical `runs/<run-id>`; selection decisions are recorded through canonical trust
records and claim mappings, never by repointing a filesystem symlink. `best.pth` and optional frozen
`last.pth` remain root-level within the immutable run.
