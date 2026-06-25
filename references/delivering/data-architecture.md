# Delivering — the data architecture (the on-disk layout that makes the principles real)

**This is the directory layout that turns `references/delivering/principles.md` from intent into
structure.** Two source-of-truth records (one project-level, one run-level), an **append-only** run history
that is never overwritten, the split promoted to a first-class audited object, derived-and-prunable
qualitative output, and one-folder-per-figure. The schemas for the two JSON manifests live in
`references/delivering/evidence-manifest-schema.md`; the figure-folder details in
`references/delivering/figures.md`. This file owns the *tree*.

To jump: `grep -n '^## ' references/delivering/data-architecture.md`.

---

## The layout

```
<project>/
  EVIDENCE.json                  Project-level single source of truth = machine-readable claims↔evidence map.
                                 Each claim ← the supporting exp-id / metric / figure + a paper anchor
                                 + the repo-implementation file:line. (schema → evidence-manifest-schema.md)

  results/<exp-id>/              exp-id = a DESCRIPTIVE ablation name (your checkpoints/ naming convention),
                                 e.g. results/baseline/, results/ours-no-aux/, results/ours-full/.
    runs/<run-id>/               APPEND-ONLY. A re-run mints a NEW <run-id>; an existing run is NEVER
                                 overwritten (P3 / verifying/methodology.md §3). <run-id> = a timestamp or
                                 the provenance hash.
      config.resolved.yaml       The FROZEN, fully-resolved config — not the one-off CLI string that
                                 launched it. (Answers "what settings produced this?" reproducibly.)
      provenance.json            hash(config + code-git-sha + data-hash + seed + env-lock + hardware)
                                 + the tracker run-id back-link. (schema → evidence-manifest-schema.md)
      checkpoints/{best, last}   best = the SELECTION checkpoint (chosen by the val metric ONLY);
                                 last = the RESUME anchor (continue / spot-preemption). Which to keep is
                                 set by the lifecycle-aware checkpoint policy (see "Checkpoint policy" below),
                                 not redefined here.
      results.json               ALL metrics. Every entry carries split ∈ {val, test} + n + variance.
                                 (This is the artifact P2 GENERATES tables from; the one truth value per number.)
      qualitative/<task>/<dataset>/{image,gt,pred[,aux]}/<id>.png
                                 [DERIVED · PRUNABLE]. The visualization core is {image, gt, pred};
                                 `aux` (e.g. an overlay, an attention map, an error map) is OPTIONAL —
                                 create it only when the task actually has one.
    selected -> runs/<run-id>    A pointer (symlink) naming the CURRENTLY-CHOSEN run for this exp-id.
                                 Re-selection re-points the symlink; the runs themselves stay append-only.
    splits/{train,val,test}.ids + split_manifest.json
                                 SPLIT IS A FIRST-CLASS OBJECT (audit → disclose). The id files list
                                 membership; split_manifest.json records provenance + (when P4 is on)
                                 checksums. train / val / test MUST be separated — audited, then disclosed,
                                 NOT enforced.

  figures/<fig-name>/            PROJECT-LEVEL and CROSS-exp-id — one figure usually pulls several
                                 experiments, so figures live at the project root, not under any one exp-id.
    README.md                    What the figure shows, how to rebuild it, which claim it supports.
    script.py                    The plotting script (co-located with its data and output).
    _build_*.py                  Step(s) that assemble source_data.csv FROM the results.json(s).
    source_data.csv              The exact tabular data the figure is drawn from (the chain's middle link).
    output/                      The rendered figure(s) (PNG/PDF/SVG).
    <fig-name>.provenance        Sidecar pointing BACK to EVIDENCE.json (which claim) + which results.json(s).
                                 (convention → figures.md)
    (_style.py shared at figures/ root)   One shared style module for all figures (fonts, palette, sizes).

  scripts/reconcile.py           Greps the whole repo and compares every reported number / name / citation
                                 against EVIDENCE.json's authoritative value — catches cross-document drift
                                 (verifying/methodology.md §14). The audit tool behind the P8 disclosure gate.
```

---

## The two sources of truth (and why there are exactly two)

| Record | Level | Answers | Owned by |
|---|---|---|---|
| `EVIDENCE.json` | **Project** | "What does the paper *claim*, and what evidence + repo code + paper location backs each claim?" | `references/delivering/evidence-manifest-schema.md` |
| `provenance.json` | **Run** | "Under exactly what config / code / data / seed / env / hardware was *this run* produced, and where is its tracker entry?" | `references/delivering/evidence-manifest-schema.md` |

`EVIDENCE.json` is the **claims↔evidence map** — it points *up* to the paper (anchors) and *across* to the
repo (implementation `file:line`), and *down* to the runs/figures that substantiate each claim. It is the
single place that answers "is every claim in the paper actually backed, and by what?" — modeled on a
claims-list table, made machine-readable. `provenance.json` is the **per-run birth certificate** — it makes
P3's content-addressing concrete (the hash) and links back to the experiment tracker.

The two compose: `EVIDENCE.json`'s evidence pointer names an `exp-id` + the `selected` run; that run's
`provenance.json` certifies the conditions; that run's `results.json` holds the number a P2 generator
emits. So a single claim in the paper traces, mechanically, all the way down to the hash of the conditions
that produced its number.

---

## Append-only is the load-bearing rule

`results/<exp-id>/runs/<run-id>/` **grows; it never mutates.** A re-run — even of the identical config —
creates a *new* `<run-id>`. Nothing in an existing run directory is ever rewritten. The consequences:

- **`selected` is a pointer, not a copy.** When you decide a different run is the chosen one, you re-point
  the `selected` symlink. The previously-selected run is still on disk (or in the tracker, light tier
  below), unchanged. This is how "which run is canonical" stays a *decision you can revise* without
  destroying the alternatives you're choosing between.
- **`best` vs `last` are orthogonal to append-only.** *Within* a run, `checkpoints/best` is the val-selected
  checkpoint and `checkpoints/last` is the resume anchor — that's the lifecycle-aware policy. *Across* runs,
  append-only means run B never clobbers run A. Don't conflate the two: pruning a periodic snapshot *inside*
  a finished run is fine; overwriting a whole run's directory is forbidden.
- **It makes "back up before re-running" unnecessary.** `references/verifying/methodology.md` §3 warns to
  copy the original before a re-run overwrites it. Under append-only there is nothing to copy — the original
  run directory is immutable, and the re-run lands somewhere new.

---

## Light tier vs heavy tier (YAGNI — don't keep history you'll never open)

P3's append-only history does **not** force you to keep every byte on local disk. Two tiers, picked by phase:

| Tier | On disk | History lives in | Use when |
|---|---|---|---|
| **Light** | only `selected/` (the chosen run's dir) | the **tracker** (e.g. wandb); `provenance.json` keeps the run-id back-link | **Exploration** — you spin up many runs, most superseded fast |
| **Heavy** | the **full `runs/` history** | on disk | **Submission / archival** — every run reproducible from local files alone |

The light tier is the disk-economy escape hatch: keep only the currently-selected run's directory on the
box, and let the experiment tracker hold the full history. The `provenance.json` of the selected run still
records the **tracker run-id**, so a superseded run is *recoverable from the tracker* even though its
directory isn't on disk. This is the same "clean by value — keep the tiny irreplaceable evidence, discard
the large reproducible scratch" discipline that governs checkpoint disk budgets; here it governs *run-
history* disk budgets. Start light in exploration; promote to heavy as a result heads for submission (which
is also when P4/P5 flip on per `references/delivering/principles.md`).

> The append-only *rule* holds in both tiers — the light tier doesn't *overwrite* superseded runs, it
> *offloads* them to the tracker. "Never overwrite" and "don't hoard every run on local disk" are
> compatible: the history is intact, just not all local.

---

## Splits are a first-class object — audited, then disclosed, never enforced

`splits/{train,val,test}.ids` + `split_manifest.json` sit at the `results/<exp-id>/` level as **a real
artifact, not an implementation detail buried in a dataloader.** Two non-negotiables and one boundary:

- **train / val / test MUST be separated.** They are audited as the split-leakage probes of
  `references/verifying/methodology.md` §4 demand: cross-split id intersection empty; no disjoint-val
  problem; the **test split touched only once, at the end** (never used for selection or HP tuning).
- **The audit result MUST be disclosed.** If the audit finds a problem — no disjoint val split, a leak
  between train and test, the test set used during selection — that finding is **surfaced with any
  conclusion that depends on the affected number** (P8). It is not hidden.
- **It is NOT enforced.** The skill does not refuse to build the figure or block the export because the
  split has an issue. **What is mandatory is the disclosure, not the fix** — the user, informed, decides.
  This is the audit-then-disclose stance of `references/delivering/principles.md`, made concrete at the
  split level.

`split_manifest.json` records the split's *provenance* (how it was constructed, the source dataset, the
seed if randomly partitioned) always; it adds per-member **checksums** when **P4** is flipped on (advanced /
submission tier), which is what turns the §4 leakage audit from a manual probe into a machine-checkable
assertion. Even with P4 off, the split stays a first-class, audited, disclosed object — P4 only adds the
hash on top of the always-required disclosure.

---

## Qualitative output is derived and prunable

`qualitative/<task>/<dataset>/{image,gt,pred[,aux]}/<id>.png`:

- **The visualization core is `{image, gt, pred}`** — the input, the ground truth, and the prediction.
  These three are what a qualitative panel almost always needs.
- **`aux` is OPTIONAL and task-dependent.** An overlay, an attention/saliency map, an error/residual map,
  an uncertainty map — create the `aux/` channel *only when the task actually produces one*. A
  classification task may have no meaningful `aux`; a segmentation task might want an error overlay. Don't
  scaffold an empty `aux/` for a task that has none.
- **It is DERIVED and PRUNABLE.** These PNGs are *regenerated* from the checkpoint + the split, not
  primary evidence — the **metric summary (`results.json`) is the irreplaceable asset; the per-sample
  images are reproducible scratch** (`references/verifying/methodology.md` §10). Prune them to reclaim disk
  (per-sample visualization scales as samples × conditions and exhausts **inodes before bytes**); regenerate
  when a figure needs them.

> **Sovereignty boundary (P6 is DROPPED):** this tree is the *plumbing* for qualitative output — *which*
> samples a figure showcases is the **user's** selection, not something the skill fixes or standardizes
> (`references/delivering/principles.md` P6). The skill guarantees the showcased samples are genuine
> outputs of the named run (traceable via the figure's `.provenance`, `references/delivering/figures.md`)
> and that the rendering is correct (P7 pixel gate) — it does not choose them.

---

## One figure = one folder, containing its own build script

`figures/<fig-name>/` is **project-level and cross-`exp-id`** — a single figure routinely pulls multiple
experiments (e.g. an ablation bar chart spanning `baseline`, `ours-no-aux`, `ours-full`), so figures cannot
live under any one `exp-id`; they live at the project root. Each figure folder is **self-contained**:
`README.md` + `script.py` + `_build_*.py` (assembles `source_data.csv` from the relevant `results.json`(s))
+ `source_data.csv` + `output/` + a `<fig-name>.provenance` sidecar, with one **shared `_style.py` at the
`figures/` root**. This co-location is what makes the P7 chain `results.json → source_data.csv → figure`
inspectable and the sidecar's back-link to `EVIDENCE.json` meaningful. The full convention, the sidecar
format, and the pixel-check gate → `references/delivering/figures.md`.

---

## Checkpoint policy (pointer — not redefined here)

`checkpoints/{best, last}` follows the **lifecycle-aware** policy, which this file references rather than
restates:

- **best** = the selection checkpoint, chosen by the **val metric only** (never test — that would be
  selection-on-test leakage, `references/verifying/methodology.md` §4).
- **last** = the resume anchor, required for continued / spot-preemptible training.
- *Which* to keep depends on lifecycle stage (running-and-resumable keeps both + prunes periodic snapshots;
  finished-and-verified keeps `best`, keeps `last` only if you'll continue). The full policy lives with the
  checkpoint-resume and spot-resilience material — don't duplicate the cadence here.

---

## How the tree enforces each principle (one-line map)

| Principle | Enforced by this tree's… |
|---|---|
| **P1** evidence/presentation split | `results/…` (evidence) vs `figures/…/output` + generated tables (presentation) — a hard directory wall |
| **P2** generated not transcribed | `figures/<f>/_build_*.py` + a build step reading `results.json` → generated tables/macros |
| **P3** content-addressed, append-only | `runs/<run-id>/provenance.json` (the hash) + `runs/` never overwritten + `selected` pointer |
| **P4** split hash-pinned | `splits/…ids` + `split_manifest.json` checksums (when flipped on) |
| **P5** one-command repro | `scripts/repro.sh.template` drives env-lock → ckpt-eval → `results.json` → tables → figures |
| **P7** figure-chain + pixel gate | `figures/<f>/` co-located chain + `<f>.provenance` + the re-open check (`figures.md`) |
| **P8** disclosure gate | `EVIDENCE.json` (every claim mapped) + `scripts/reconcile.py` (drift audit) → disclose, don't block |
