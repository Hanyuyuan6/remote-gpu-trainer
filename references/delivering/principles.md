# Delivering - legacy/non-canonical publication synthesis guidance

This reference keeps useful reporting principles from the former DELIVER layer. It is optional synthesis
guidance, not an artifact-layout specification. `research-artifact-hygiene` owns the canonical layout and
validators; follow it whenever this legacy group differs.

## Principles retained

1. **Generate, do not transcribe.** Tables and plots read accepted machine artifacts, never console text or
   tracker summaries.
2. **Bind every claim.** A reported value identifies its software or hardware run, test, metric, split,
   selection record, and source hash.
3. **Keep evidence immutable.** Re-evaluation mints a new run or verification record; publication synthesis
   never edits accepted evidence.
4. **Select without test leakage.** Checkpoint selection uses the declared validation criterion and is bound
   by identity/hash. There is no mutable filesystem selection pointer.
5. **Disclose limits.** Missing seeds, failed runs, proxy data, and unverified claims remain explicit.
6. **Build deterministically.** A clean environment can rebuild flat figure/table workshops from accepted
   canonical inputs.
7. **Inspect rendered output.** Successful execution is necessary but does not replace pixel, parse, and
   editability QA.

## Canonical evidence boundary

Software evidence is read only from:

```text
runs/<run-id>/
  run.json
  config.yaml
  train.csv
  best.pth
  last.pth?
  test/<test-id>/
    metrics.json
    results.parquet
    vis/<condition-id>/<task-native-role>/<sample-id>.png
```

Every declared software test requires complete conditions x task-native roles x K visualization coverage, with
K = min(100, N_test) from the fixed selection bound by `run.json`. Software runs contain no dataset bytes
and no hardware results.

Real-capture evidence is a separate `hardware/runs/<hardware-run-id>` capsule. It binds capture/decode and
same-task model-run identities plus the selected checkpoint hash and copies no model weights. Its rows and
applicable visualization coverage remain mandatory. Metrics and ground-truth roles are mandatory only when
`ground_truth_status=available`; explicit no-machine-readable-GT tests use finite-forward rows, prediction
roles, and `metric_applicability=not_applicable` without fake accuracy/AP/IoU.

## Publication boundary

Derived presentation work belongs only in flat `figures/<figure-id>` or `tables/<table-id>` workshops. Their
single JSON contract binds inputs, build command, QA, provenance, and final-output hashes. Publication code
may consume canonical evidence but must not rename, duplicate, select, or repair it.
