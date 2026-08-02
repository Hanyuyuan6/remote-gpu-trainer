# Multi-node production matrix acceptance

Use this protocol when several rented nodes write independent jobs to one durable/shared result root.
Keep scheduler state, training state, scientific acceptance, and evidence mirroring separate.

## State taxonomy

| State | Meaning | Counts as complete? |
|---|---|---:|
| active claim (`attempt >= 1`) | a worker owns a live attempt | no |
| reversible scope blocker (`attempt == 0`) | intentionally excluded by a locked scope | no |
| failed attempt | preserved diagnostic artifact | no |
| producer complete | atomic bundle and producer manifest exist | not yet |
| independently accepted | different node verifies hashes and safe checkpoint load | integrity complete |
| independently evaluated | raw inputs + checkpoint recompute metrics | scientific metric complete |

Never infer one state from another. An empty tmux does not prove failure; an exit code does not prove a
bundle; a producer marker does not prove independent acceptance.

## Patrol order

1. Read tmux/session inventory, process command lines, GPU processes/utilization, disk bytes/inodes.
2. Read complete markers, live `attempt >= 1` claims, `attempt == 0` blockers, and failed-attempt paths.
3. Reconcile claims with processes and atomic bundles; never treat blockers as conflicts.
4. For each new producer bundle, run producer verification and then independent acceptance on another
   authorized node before reporting it.
5. Pull only small evidence records after their remote hashes are fixed; verify the local copy.
6. Rebuild and compare local/remote evidence indexes after any interrupted transfer.

Run post-evaluation only when training GPUs are idle unless contention is explicitly accepted.

## Artifact contract

Publish a run through staging→verification→atomic rename. The producer manifest must bind:

- artifact/job ID, producer node, status, commit/config/data/split identifiers;
- every expected file's relative path, byte size, and SHA-256;
- checkpoint role and epoch/selection metric;
- metric protocol identity, not only the metric name;
- control-script hash and environment provenance when available.

Never overwrite an accepted directory with a retry. Quarantine partial or rejected attempts under a
unique failure path with logs and environment evidence.

## Independent acceptance

On a node other than the producer:

```bash
python scripts/verify_artifact_bundle.py \
  --root /durable/results/job-42 \
  --manifest producer_manifest.json \
  --required complete.json --required checkpoint/best.pth \
  --checkpoint checkpoint/best.pth \
  --independent-node verifier-b \
  --out acceptance-verifier-b.json
```

The verifier must recompute every size/hash and load checkpoints with `weights_only=True`. If trusted
legacy checkpoints require NumPy scalar/dtype metadata, use `--allow-numpy-metadata`; this adds only the
three named NumPy metadata types and never falls back to unrestricted pickle.

Run the same acceptance on another node when cross-node determinism matters, then compare:

```bash
python scripts/compare_acceptance.py acceptance-a.json acceptance-b.json
```

The comparison intentionally ignores verifier-node/runtime identity and compares the manifest, verified
files, and checkpoint tensor summaries. It still does not replace fresh metric recomputation.

## Retry discipline

- SSH/DNS/banner/SCP timeout: retry at most the declared bound; switch to another authorized shared-disk
  entry point if needed; keep strict host-key verification and accept only hash-identical copies.
- Scheduler/tmux disappearance: resume only after proving no matching process, no conflicting live claim,
  fixed commit/plan/roster, and full preflight.
- Transient infrastructure training failure: preserve evidence and retry the original immutable job at
  most once if policy permits.
- Deterministic code/data/config error, OOM, NaN, hash mismatch, metric anomaly: do not blind-retry.

## Control plane vs science plane

Label controller bugs, evaluator path mistakes, missing `no_grad()`, transfer failures, and interpreter
PATH differences as control-plane failures. They become paper/repository defects only when the defect is
shown to exist in the audited source or protocol. Preserve rejected control outputs but never publish
them as scientific results.
