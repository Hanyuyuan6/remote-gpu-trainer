# Delivering — the manifest schemas (`EVIDENCE.json` + `provenance.json`)

The two source-of-truth records the data architecture (`references/delivering/data-architecture.md`) places
on disk. **`EVIDENCE.json` is project-level** (the claims↔evidence map); **`provenance.json` is run-level**
(the birth certificate of one run). This file defines both and gives a filled, *valid-JSON* example of each.

To jump: `grep -n '^## ' references/delivering/evidence-manifest-schema.md`.

---

## `EVIDENCE.json` — the project-level claims↔evidence map

**Purpose.** One machine-readable place that answers: *every claim the paper makes — what evidence backs it,
where in the paper it appears, and where in the repo it's implemented?* It is the spine of the **P8**
disclosure gate (`references/delivering/principles.md`) and the authoritative value source that
`scripts/reconcile.py` greps the rest of the corpus against (`references/verifying/methodology.md` §14).

**Each claim binds three directions:**
- **down → evidence** — the `exp-id` + `metric` (and `figure`) that substantiate the claim, pointing at the
  `selected` run's `results.json`.
- **up → paper anchor** — where the claim is asserted (section / table / figure label), so the gate can
  check the paper number against the evidence number.
- **across → repo implementation** — the `file:line` where the claimed mechanism actually lives, so a
  "we do X" claim is tied to the code that does X (the *evidence-or-it-didn't-happen* discipline for
  implementation claims).

### Field reference

| Field | Meaning |
|---|---|
| `project` | Short project id. |
| `authoritative_source` | The rule: every reported number's truth value = the `results.json` its claim points to (not any document's copy). |
| `claims[]` | The list of claims. |
| `claims[].id` | Stable claim id (referenced by figure `.provenance` sidecars). |
| `claims[].statement` | The claim in words. |
| `claims[].evidence[]` | Supporting records: `exp_id`, `run` (usually `selected`), `metric` name, `value`, `split`, `n`, `variance`, and the `results_json` path. |
| `claims[].evidence[].figure` | (optional) the figure folder that visualizes this evidence. |
| `claims[].paper_anchor` | Where the claim appears (e.g. `"Sec 4.2, Table 2, row Ours-full"`). |
| `claims[].repo_implementation` | `file:line` where the claimed mechanism is implemented. |
| `claims[].disclosure` | (optional) the audit→disclose caveat that must ride with this number (single-seed, split status, leakage finding). **Surfaced, never used to block.** |

### Filled example (valid JSON)

```json
{
  "project": "ours-superres",
  "authoritative_source": "Each reported number's truth value is the results.json its claim points to; documents must match it, never the reverse.",
  "schema_version": "1.0",
  "claims": [
    {
      "id": "C1-main-psnr",
      "statement": "Our full model improves PSNR over the baseline on the test split.",
      "evidence": [
        {
          "exp_id": "ours-full",
          "run": "selected",
          "metric": "PSNR",
          "direction": "higher_is_better",
          "value": 31.42,
          "split": "test",
          "n": 100,
          "variance": {"type": "std", "value": 0.08, "seeds": 3},
          "results_json": "results/ours-full/selected/results.json",
          "figure": "figures/main-comparison"
        },
        {
          "exp_id": "baseline",
          "run": "selected",
          "metric": "PSNR",
          "direction": "higher_is_better",
          "value": 29.95,
          "split": "test",
          "n": 100,
          "variance": {"type": "std", "value": 0.11, "seeds": 3},
          "results_json": "results/baseline/selected/results.json"
        }
      ],
      "paper_anchor": "Sec 4.2, Table 2, rows Baseline vs Ours-full",
      "repo_implementation": "src/models/ours.py:142",
      "disclosure": null
    },
    {
      "id": "C2-aux-ablation",
      "statement": "Removing the auxiliary head costs 0.6 dB PSNR, showing the aux branch contributes.",
      "evidence": [
        {
          "exp_id": "ours-no-aux",
          "run": "selected",
          "metric": "PSNR",
          "direction": "higher_is_better",
          "value": 30.81,
          "split": "test",
          "n": 100,
          "variance": {"type": "std", "value": 0.10, "seeds": 1},
          "results_json": "results/ours-no-aux/selected/results.json",
          "figure": "figures/aux-ablation-bar"
        }
      ],
      "paper_anchor": "Sec 4.3, Table 3, row w/o aux",
      "repo_implementation": "src/models/ours.py:88",
      "disclosure": "Single seed (seeds=1): no variance band, so a delta inside run-to-run noise cannot be distinguished from signal. Stated once here; surfaced with the number at delivery."
    }
  ]
}
```

> Note the two `disclosure` values: `C1` has a 3-seed band and nothing to flag (`null`); `C2` is single-seed
> and carries its caveat. The delivery gate (`references/delivering/delivery-gate.md`) reads `disclosure`
> and ensures it travels *with* the number — it does **not** drop or block `C2` for being single-seed; the
> user chose one seed, and that choice is disclosed once, not nagged.

---

## `provenance.json` — the run-level birth certificate

**Purpose.** Make **P3**'s content-addressing concrete for one run: record the inputs whose hash addresses
the artifact — `hash(config + code-git-sha + data-hash + seed + env-lock + hardware)` — plus the **tracker
run-id** back-link (so a superseded run is recoverable from the tracker even under the light disk tier,
`references/delivering/data-architecture.md`). Two runs with the same `provenance_hash` were produced under
identical conditions, so a comparison between them is *not* confounded; differing hashes flag that something
changed (the §1 Probe-1 comparability check, made automatic).

### Field reference

| Field | Meaning |
|---|---|
| `exp_id` / `run_id` | Which experiment, which append-only run. |
| `provenance_hash` | The content address: `hash` over the six inputs below. `hash_inputs` lists them so the hash is recomputable. |
| `hash_inputs.config` | Path + hash of `config.resolved.yaml` (the frozen resolved config, not the CLI string). |
| `hash_inputs.code_git_sha` | The commit the run was built from (+ a `dirty` flag — an uncommitted tree is not reproducible). |
| `hash_inputs.data_hash` | Hash of the dataset/version used (ties to `split_manifest.json`; the §4 leakage-audit anchor under P4). |
| `hash_inputs.seed` | Seed(s) + the determinism flags that were set. |
| `hash_inputs.env_lock` | The environment lock (path + hash of `requirements.txt` / `environment.yml` / lockfile). |
| `hash_inputs.hardware` | GPU model / count / driver / CUDA — the hardware the number was produced on. |
| `tracker` | `{backend, entity, project, run_id, url}` — the back-link the light tier relies on. |
| `created` | ISO-8601 timestamp. |

### Filled example (valid JSON)

```json
{
  "exp_id": "ours-full",
  "run_id": "2026-06-20T14-03-11Z-a1b2c3",
  "provenance_hash": "sha256:9f2c4e7a8b1d6038f5c2a90e4b7d1c83a6e0f29d4c5b8a17e3f60d9b2c1a4e7f",
  "hash_inputs": {
    "config": {
      "path": "results/ours-full/runs/2026-06-20T14-03-11Z-a1b2c3/config.resolved.yaml",
      "sha256": "sha256:3a1f0b9c2d4e6857a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f6071"
    },
    "code_git_sha": {"commit": "e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f6071", "dirty": false},
    "data_hash": {
      "dataset": "div2k-x4",
      "sha256": "sha256:7c8d9e0f1a2b3c4d5e6f70819a2b3c4d5e6f7081923a4b5c6d7e8f9011223344",
      "split_manifest": "results/ours-full/splits/split_manifest.json"
    },
    "seed": {"value": 1234, "determinism_flags": ["torch.use_deterministic_algorithms(True)", "cudnn.benchmark=False"]},
    "env_lock": {
      "path": "env/requirements.lock.txt",
      "sha256": "sha256:1122334455667788990011223344556677889900aabbccddeeff001122334455"
    },
    "hardware": {"gpu": "NVIDIA RTX 4090", "count": 1, "driver": "550.54.15", "cuda": "12.4"}
  },
  "tracker": {
    "backend": "wandb",
    "entity": "my-lab",
    "project": "ours-superres",
    "run_id": "wandb-run-7h3k9q2x",
    "url": "https://wandb.ai/my-lab/ours-superres/runs/7h3k9q2x"
  },
  "created": "2026-06-20T14:03:11Z"
}
```

---

## How the two compose (the trace from a paper claim to its conditions)

```
EVIDENCE.json  claim C1  ──evidence──►  results/ours-full/selected/results.json   (the number: 31.42, test, n=100, ±0.08)
                                              │
        selected ─► runs/<run-id>/  ──────────┤
                                              ▼
                              provenance.json  (provenance_hash over config+code+data+seed+env+hw
                                                + tracker run-id back-link)
```

A reviewer's question "where does the 31.42 come from, and under what conditions?" resolves mechanically:
`EVIDENCE.json` → the `results.json` (the value, split, n, variance) → the same run's `provenance.json` (the
hash certifying config/code/data/seed/env/hardware, and the tracker link). No document holds an independent
copy of 31.42 to go stale — the paper dereferences it through a generated macro (**P2**,
`references/delivering/principles.md`), and `scripts/reconcile.py` audits that every other mention matches
this source (§14).

---

## Authoring notes

- **Keep both files plain JSON** (no comments) so they parse anywhere; put human notes in a sibling
  `README.md` or in the `statement` / `disclosure` strings.
- **`disclosure` is for the audit→disclose stance**, not enforcement — a populated `disclosure` means "this
  caveat must ride with the number"; it never means "block this number." The delivery gate surfaces it
  (`references/delivering/delivery-gate.md`); the user decides.
- **Hashes are illustrative** in the examples above (truncated/synthetic digests). Use your real hash
  function (sha256 is fine) over the *canonicalized* inputs so the address is stable across machines.
- **A `dirty: true` git tree is a disclosure-worthy fact** — a number produced from an uncommitted working
  tree is not cleanly reproducible (`references/verifying/methodology.md` §13); record it and surface it.
