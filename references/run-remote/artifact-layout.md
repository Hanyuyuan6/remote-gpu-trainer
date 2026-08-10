# Remote run layout — mutable compute, canonical export

This skill owns the compute/control side of one run. It may create mutable state, validate a closeout, and
produce one sealed export. Project organization belongs to `research-artifact-hygiene`; every durable,
shared-filesystem, object-store, or Hugging Face copy belongs to the generic `mirror-research-artifacts`
skill. A compute profile may bind another provider's mount, but it must preserve the same state transitions.

## AutoDL binding (exact)

The AutoDL project root is exactly:

```text
/root/autodl-tmp/<project>/{cache,active,export/.partial,export/<run-id>,quarantine}
```

Expanded:

```text
/root/autodl-tmp/<project>/
├── cache/                         # regenerable downloads and framework caches
├── active/
│   └── <run-id>/                  # mutable producer workspace
│       └── latest.pth             # optional rolling resume anchor
├── export/
│   ├── .partial/
│   │   └── <run-id>/              # closeout build, never a consumer source
│   └── <run-id>/                  # sealed; isomorphic to local runs/<run-id>
└── quarantine/                    # preserved failed or suspect attempts
```

There is no `inbox/` and no nested `artifacts/` directory in this binding. Code, configuration, dataset,
and split identities are recorded in `run.json`; cached bytes are not an identity.

## `active/<run-id>` — mutable producer state

- One unique run id owns one mutable directory. Never let two jobs write the same path.
- `latest.pth` is allowed only here as a replaceable resume anchor. Write it through a temporary sibling and
  atomic rename. Retain the selection best plus the resume anchor; default `save_top_k <= 3`.
- Logs, tracker state, scratch visualizations, download caches, and interrupted intermediate files may remain
  here while compute is active. They are not automatically part of the result.
- Never sync, upload, or mirror `active/` as a whole—not to a shared filesystem and not to Hugging Face.

## `export/<run-id>` — canonical sealed run

The relative paths and semantics under remote `export/<run-id>` must be fully isomorphic to canonical local
`runs/<run-id>`. The canonical tree is exact:

```text
export/<run-id>/
├── run.json                       # scientific identity/protocol/selection/checkpoint bindings only
├── config.yaml                    # one resolved run configuration
├── train.csv                      # canonical training history
├── best.pth                       # required selection-criterion checkpoint
├── last.pth                       # optional frozen final checkpoint; never mutable after closure
└── test/
    └── <test-id>/
        ├── metrics.json
        ├── results.parquet
        └── vis/
            └── <condition-id>/
                └── <task-native-role>/
                    └── <sample-id>.png
```

`run.json`, `config.yaml`, `train.csv`, and `best.pth` are required. `last.pth` is the only optional
top-level checkpoint. Each declared software `<test-id>` must contain `metrics.json`,
`results.parquet`, and `vis/`. Visualization PNGs are required and must provide complete Cartesian coverage
of every declared condition × task-native role × the fixed K selected samples, at exactly
`test/<test-id>/vis/<condition-id>/<task-native-role>/<sample-id>.png`. There is no top-level `config/`,
`data/`, `results/`, or `vis/`, and the export contains no dataset bytes.

A software `export/<run-id>` must never contain real-capture or other hardware results. If AutoDL produces
hardware output, either hand the source identities to `research-artifact-hygiene` for assembly or close a
separate capsule:

```text
export/hardware/<hardware-run-id>/
├── run.json                       # capture/decode/model-run bindings; no weights
└── test/<test-id>/
    ├── metrics.json
    ├── results.parquet
    └── vis/<condition-id>/<task-native-role>/<sample-id>.png
```

The hardware `run.json` binds capture identity/hash, decode identity/hash, a same-task closed model-run
identity/hash, and the referenced `best.pth` hash. It never copies `best.pth`, `last.pth`, or any model
weights. Every declared hardware test follows one explicit applicability branch. Ground-truth-available tests
require complete conditions × full task-native roles × K coverage and
full-test metrics. A test without machine-readable ground truth explicitly declares
`ground_truth_status=unavailable_no_machine_readable_gt` and `metric_applicability=not_applicable`; it still
requires complete finite-forward rows and K prediction visuals (plus overlay for segmentation/detection),
but forbids ground-truth/error roles and GT-derived metrics. Never infer this branch from absent files.
Build the capsule under `export/.partial/hardware/<hardware-run-id>` and atomically rename to
`export/hardware/<hardware-run-id>`; failures go to `quarantine/hardware/<hardware-run-id>--<attempt-id>`.

Existing project-native checkpoint trees are not remote export targets. Keep their identities in place and
let `supervise-research-closeout` record a legacy acceptance bridge; only newly closed outputs use this
canonical export tree.

Closure rules:

- `best.pth` is mandatory. `last.pth` is optional and, if present, is a frozen distinct artifact.
- `latest.pth` is forbidden anywhere under a sealed export.
- AutoDL export must not add `COMPLETE.json`, `MANIFEST.json`, or similarly redundant status sentinels.
  Atomic rename plus the canonical `run.json` closure record is the completion signal.
- `run.json` contains no full-file roster, byte-size table, or payload-hash inventory. Keep it within the
  canonical scientific schema: run identity/state/task, source/config/data/split bindings, protocol/tests,
  fixed selection bindings, seed/determinism, and checkpoint selection metadata.
- Caches, general training logs, full tracker state, default montages, and unbounded per-epoch checkpoints are
  excluded unless the canonical run schema explicitly classifies one as evidence.
- A visualization selection is fixed per test set, identified by a stable `selection_id`, and contains
  exactly K = `min(100, N_test)` sample ids (or all samples when the test set is smaller). Every declared
  condition and task-native role must render all K ids. Reuse that selection across models and protocols;
  never choose a performance-ranked top 100. `run.json` binds the canonical
  selection manifest path under project `_trust/selections/<selection-id>.json` and its hash. Do not embed a
  second selection manifest or legacy visualization index inside the export.
- Re-running or changing any sealed byte mints a new run id; never overwrite `export/<run-id>`.

## Atomic closeout and quarantine

1. Build the entire software candidate under `export/.partial/<run-id>` on the same filesystem as
   `export/<run-id>`. Never place hardware results in that candidate.
2. Freeze `best.pth`; optionally freeze `last.pth`; exclude every `latest.pth`.
3. Generate canonical `run.json` with scientific identity, protocol, data/split, selection and checkpoint
   bindings only. Do not duplicate the capsule's file roster, byte sizes or payload hashes inside it.
4. Validate safe checkpoint load, JSON/schema semantics, required paths/coverage, and the isomorphism
   contract owned by `research-artifact-hygiene`.
5. Require that `export/<run-id>` does not already exist, then atomically rename the partial directory to it.
6. On any validation or rename failure, preserve the failed partial under
   `quarantine/<run-id>--<attempt-id>` with the failure reason. Never promote it and never delete it without
   explicit authorization.

Atomic rename is valid only within the same filesystem. A cross-mount copy is mirroring, not closure, and is
outside this skill.

## Handoff boundary

After closure, this skill may pull and verify the exact sealed capsule for teardown safety. Any additional
replica—local canonical storage, AutoDL shared FS, Hugging Face, or another provider—must invoke
`mirror-research-artifacts` with `export/<run-id>` as the source. That skill owns destination privacy,
an external frozen manifest with exact roster/byte/hash inventory, live exact-roster validation, transfer,
remote/readback verification, and restore evidence. The external mirror manifest never becomes a file inside
the canonical run. Never give it
`active/`, `cache/`, the project root, or `export/.partial/`.
