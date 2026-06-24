# Result validity — is the reported number real? (the inline floor)

**A surprising experiment number is a hypothesis, not a fact to report.** It is one of three things —
an instrumentation/config **bug**, a genuine **effect**, or stochastic **noise** — and you decide which
*before* you trust it, put it in a table, or tear down the box.

This file is the **condensed floor** so a standalone install (without the `verifying-dl-experiments`
companion) still gates a number. `remote-gpu-trainer` owns *running* the job — fast, cheap, not-crashing
(`references/training/`); this file owns *is the produced number true*. The **full methodology**
(representation-collapse playbook, signal-localization probe ladders, experiment-tracker forensics, the
academic-integrity spectrum, the worked war-stories) is the separate **`verifying-dl-experiments`**
skill — install it for depth; the gates below are the must-not-skip subset.

> Boundary, restated: `references/training/` makes the run *happen*; this makes its number *trustworthy*.
> When a number is going into a paper / slide / README / results table, run **every** gate below — not
> just the cheap one — and do it **before** teardown (a number you can't re-derive from the saved
> artifact is not a result yet).

## When to run this
- Before reporting **any** metric, ablation delta, or comparison-table cell from the run.
- A metric lands far from control/expectation and you don't know if it's real.
- Output looks constant across distinct inputs, or train-good / val-or-test-bad.
- Before teardown — confirm the headline re-derives from the saved artifact, not just a log line.

---

### V1 — Classify a surprising number: bug / effect / noise
`symptom:` a metric far from its control/expectation, about to be reported.
`probe (cheapest first):`
1. **Diff the resolved configs** of the surprising run vs its control — they must differ in **exactly
   the one variable you ablated**. Any extra unexplained delta ⇒ the gap is a misconfiguration **bug**,
   not the variable's effect. (Mirror: a *win* whose config differs in ≥2 ways at once is confounded —
   run one-axis-at-a-time intermediates before concluding "X is necessary".)
2. **Read the trajectory, not the endpoint.** Tracks the control then saturates at a lower ceiling /
   gentler slope = real effect; early-peak-then-decline, or never-improves-past-epoch-1 with a grad-norm
   spike = **instability** → retry the *identical* config (never rescue one cell with special
   lr/clip/patience — it breaks comparability), not a datapoint.
3. **Reproduce — but back up the original FIRST** (re-running overwrites it, especially under
   auto-sync). Agreement within run-to-run noise (nondeterministic kernels + reduced-precision autocast
   give a few-% band) ⇒ real & reproducible; large disagreement ⇒ stochastic, report a band or rerun.

`fix:` only report once it survives all three. Convergence/instability *debugging* itself →
`references/training/convergence-debugging.md` + `precision-stability.md`.

### V2 — Fair comparison: every method gets the same chance
`symptom:` your method vs a baseline (or vs a prior cell) — an unfair table is a confound (V1) at paper scale.
`probe / fix:` hold these identical across your method **and** every baseline; where you can't, **disclose it**:
- **Equal budget** — tuning / compute / data / epochs / augmentation. Your method fully tuned while a
  baseline is under-trained = the gap is budget, not method.
- **A re-implemented baseline must reach its published number** — else the low score is a reproduction
  artifact; fix it or mark the row cite-only, never present a crippled baseline as faithful.
- **No copied numbers across settings / splits / protocols** — re-run under your one protocol or label it.
- **Tricks apply to all or none** — TTA, ensembling, extra pretraining for your method but not baselines.
- **Match the cost axis** — a bigger model "winning" is not a result unless params / FLOPs / latency are
  reported and roughly matched (or the trade-off *is* the point and is shown).
- **Report the full benchmark, not the subset you win** — hidden losses are selective reporting.

### V3 — Leakage: probe the prepared artifacts, not the prep code
`symptom:` too-good-to-be-true number; suspiciously high val; reproduces on train but collapses on test.
`probe` (on the **PREPARED** data + pipeline **ORDER** — leakage hides from code review):

| Variant | Cheap probe |
|---|---|
| Duplicate ingestion / case-insensitive FS | per split: file count vs unique **normcase** names |
| Same sample across splits (re-split, near-dups) | cross-split name intersection, then **same-bytes hash** on colliders (name collision ≠ leakage) |
| Preprocessing `fit` on the full set (scaler / PCA / impute) | assert every `fit` saw **train only** |
| Temporal (shuffle a series before splitting) | split by time; assert `max(train.time) < min(test.time)` |
| Group / subject (same patient / scene / speaker in both) | assert `train ∩ test = ∅` on the entity key |
| Label / target leakage (a feature proxies the label) | does one feature predict the label near-perfectly? drop + re-measure |
| Selection-on-test (tune HP / pick epoch on test) | select on **val**; touch the test split **once**, at the end |
| Pretraining contamination (test sits in a foundation corpus) | n-gram / canary overlap; confirm on a private / post-cutoff set |

`fix:` real leakage is **unsalvageable by re-eval — only retraining on clean splits counts** (the old
checkpoint memorized the leaked rows: seen-recall ≫ unseen-recall is the tell).

### V4 — A green smoke is not a correct model
`symptom:` the smoke passes (`isfinite(loss)` + output shape) on code that is quantitatively wrong but numerically stable.
`probe / fix:`
- **Train ≡ eval input parity** — assert both paths feed the network the **identical** tensor: same shape
  *and scale* (`allclose`), not just finite (a normalization one path applies and the other skips is the classic).
- **De-normalize before the metric**; check ImageNet-vs-`[0,1]` and RGB/BGR; assert `model.eval()` (no
  dropout / BN-batch-stats live at eval).
- **Gradient flow after a substitution** — after one backward, count parameter tensors receiving a
  non-zero gradient; expect ~all (e.g. 64/64, not 7/64) — catches a frozen / `detach()`-ed sub-net.
- **A delegated "smoke passed, loss finite" proves even less** — re-verify scale + math yourself, don't
  trust the exit status.

### V5 — Metric & statistical integrity (a number without variance is not evidence)
`probe / fix:`
- **State the metric's DIRECTION** when comparing (PSNR / SSIM / mIoU ↑; LPIPS / NMSE / FID / loss ↓) — never assume.
- **No single-run results** — report **mean ± std over ≥3 seeds**; one (or a hand-picked best) is anecdote.
  An improvement **inside the error bars is noise** — use a paired test / CIs and report `n`.
- **Don't cherry-pick the metric variant** — report the field's standard panel (mIoU + PA, AP@[.5:.95], LPIPS).
- **Deceptively-high on sparse / imbalanced data** — PSNR / SSIM and background-averaged mIoU reward the
  trivial majority (an all-black digit ≈ 10 dB / SSIM ~0.44), and a collapsing model is rewarded *toward*
  it. Score **foreground-scoped** metrics **and render** the output; never trust a high scalar on sparse
  data without looking.
- **An operating point is not a threshold-free metric** — a threshold / decode budget chosen on test and
  reported as mAP / F1 is selection-on-test (V3).
- **Confirm a real held-out val split EXISTS** — many trainers report a per-epoch "val" computed on the
  **last training batch**; that curve validates nothing (cannot catch overfit / collapse). Report the
  decisive gap on the disjoint **TEST** split, and sanity-check the chance floor.

### V6 — Trust artifacts, not log lines; reconcile across documents
`symptom:` "done / synced / saved" log lines; one result living in paper + slides + README + CSV at once.
`probe / fix:`
- **A "saved" line is not a saved file** — confirm the artifact **exists and loads** before believing it
  (and a figure that `savefig`-ed is not a *correct* figure — re-open the PNG). `scripts/verify_local.py`
  is the load-gate.
- **One truth value per number = the artifact it is computed from** (results JSON / checkpoint eval), not
  whichever document was edited last — re-derive the headline from that artifact before trusting any copy.
- **Diff every reported number / method name / dataset size across all documents before submission** — a
  correction is not done until it lands in *all* of them (a corrected number is the one most likely still
  stale somewhere).

---

**Beyond this floor → `verifying-dl-experiments`** (separate skill): the full representation-collapse
diagnosis, signal-localization probe ladders, evaluation-artifact cost limits, experiment-tracker
forensics (`wandb_forensics.py`), checkpoint hygiene, and the academic-integrity spectrum (the QRP/FFP
tells). This file is the must-not-skip subset; that skill is the depth. Citation / attribution integrity
→ `citation-hygiene`.
