# Completeness reconciliation - legacy/non-canonical publication synthesis guidance

This optional check reconciles presentation claims against already accepted canonical artifacts. It is not
a run-store schema, and it must not create paths or manifests that compete with `research-artifact-hygiene`.

## Reconciliation procedure

1. Enumerate each claim, table cell, figure panel, and qualitative example in the deliverable.
2. Resolve it to a canonical software `runs/<run-id>/test/<test-id>` or independent hardware
   `hardware/runs/<hardware-run-id>/test/<test-id>` source.
3. Confirm metric name, direction, split, N, seed/determinism declaration, protocol, selection path/hash,
   checkpoint hash, and source row(s).
4. For visual evidence, confirm full declared conditions x task-native roles x K coverage, where
   K = min(100, N_test) and the fixed roster is not model-performance-ranked.
5. Recompute aggregates from `results.parquet` and compare them with `metrics.json` at declared precision.
6. Verify every flat figure/table workshop input and final-output hash; then perform render and editability
   QA.
7. Keep absent, partial, failed, and unverified work explicit. Do not fill gaps with tracker values,
   screenshots, or recollection.

## Reconciliation status

Use precise states such as `planned_not_started`, `launched`, `trained`, `evaluated`, `hash_verified`,
`pull_verified`, and `paper_supported`. A later state requires its own evidence; it is never inferred from an
earlier one.

Transport inventory is handled by the external frozen mirror manifest and exact-roster validator. Do not
duplicate that roster, byte count, or per-file hash inventory in canonical `run.json` or presentation
metadata.
