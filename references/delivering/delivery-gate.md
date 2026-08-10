# Delivery gate - legacy/non-canonical publication synthesis guidance

This is an optional presentation gate after canonical artifact acceptance. It never changes run layout or
turns derived output into scientific evidence. `research-artifact-hygiene` validators take precedence.

## Gate

- Every reported scalar resolves to an accepted software or hardware run, declared test, metric, split,
  selection binding, and immutable source hash.
- Each software capsule has root-level `run.json`, `config.yaml`, `train.csv`, `best.pth`, optional frozen
  `last.pth`, and one or more complete `test/<test-id>` directories.
- Every declared test has `metrics.json`, `results.parquet`, and mandatory complete
  `vis/<condition-id>/<applicable-task-role>/<sample-id>.png` coverage. Explicit no-machine-readable-GT
  hardware tests mark metrics not applicable, preserve finite-forward rows, and forbid invented ground truth.
- The fixed roster is bound by `selection_id`; K = min(100, N_test), never a performance-ranked subset.
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
