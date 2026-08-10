# Figures - legacy/non-canonical publication synthesis guidance

This optional reference explains how to derive publication figures from accepted artifacts. It does not
define run storage. `research-artifact-hygiene` remains authoritative for artifact layout and validation.

## Flat workshop

Use one flat workshop per figure:

```text
figures/<figure-id>/
  figure.json
  data.csv          # quantitative figure; omit for a non-data figure
  source.pptx       # diagram or montage source; omit for a data figure
  build.py
  final.*
```

Do not add nested source, output, QA, draft, or cache directories. Do not add a README portal or a separate
provenance sidecar. `figure.json` is the single contract for canonical input identities/hashes, the build
command, render/editability QA, and all final-output hashes.

## Inputs

Quantitative figures read full-precision rows from
`runs/<run-id>/test/<test-id>/results.parquet` and confirm aggregates against `metrics.json`. Hardware figures
read the equivalent test artifacts from `hardware/runs/<hardware-run-id>`. If a hardware test declares
metrics not applicable because no machine-readable ground truth exists, a figure may show finite-forward
predictions/overlays but may not derive or label accuracy, AP, IoU, or a ground-truth comparison.

Qualitative figures cite atomic PNG paths and hashes from the chosen capsule:

```text
test/<test-id>/vis/<condition-id>/<task-native-role>/<sample-id>.png
```

The montage is derived presentation, never a replacement for mandatory conditions x applicable task roles x K
coverage. The sample roster is the fixed `selection_id` bound by the run, with K = min(100, N_test); never
rank examples by model performance.

## Build and acceptance

1. Resolve only accepted canonical run and test identities.
2. Verify input hashes before rendering.
3. Generate `data.csv` mechanically when the artifact is quantitative; retain full precision.
4. Run `build.py` deterministically and record the command/environment in `figure.json`.
5. Re-open every `final.*`; verify labels, units, legends, ordering, crop, fonts, and editability.
6. Record the final hashes and QA result. A failed figure build never mutates its evidence.
