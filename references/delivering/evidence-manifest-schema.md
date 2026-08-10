# Evidence mapping - legacy/non-canonical publication synthesis guidance

The former DELIVER evidence schema is retired and **NON_CANONICAL_DO_NOT_EXECUTE**. Do not copy its old
manifest examples or use them to create another artifact namespace. `research-artifact-hygiene` owns the
current schemas and validators.

## Current boundary

Canonical `run.json` stores scientific bindings only: run identity, protocol/dataset/split identities,
selection path/hash, checkpoint identity/hash, and declared tests. It must not duplicate an exact file
roster, file sizes, or hashes for every payload.

Each declared software test owns:

```text
runs/<run-id>/test/<test-id>/
  metrics.json
  results.parquet
  vis/<condition-id>/<task-native-role>/<sample-id>.png
```

Hardware claims point instead to a separate `hardware/runs/<hardware-run-id>` capsule that binds the
capture/decode/model-run identities and checkpoint hash without copying weights.

An external frozen mirror manifest plus live exact-roster validation owns transport inventory and byte
integrity. Publication claim mappings may cite canonical run/test/metric identities and hashes, but must not
embed a second payload inventory or override canonical validators.

For figures and tables, use the single root-level `figure.json` or `table.json` contract in its flat
workshop. That contract records input references, build command, QA, provenance, and final-output hashes;
it does not become a run manifest.
