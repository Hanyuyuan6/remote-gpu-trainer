# Delivering — artifact & data completeness reconciliation (organize before you disclose)

`scripts/reconcile.py` proves every reported **number** matches its authoritative source; `scripts/verify_local.py
--expect N` proves the **checkpoints you pulled** load and count out. Neither proves the thing that breaks a
delivery just as often: that the **artifact chain behind every result row is complete and correct** — the ckpt,
the split it was scored on, the *input data* needed to re-derive it, and the figure source all present and
consistent. That reconciliation is the **organize** step of DELIVER, and it runs **before** the per-number
delivery gate (`delivery-gate.md`): you cannot honestly disclose a number's provenance while the artifacts
under it are missing.

## Cleanup ≠ organization

Deleting regenerable byproducts (eval montages, caches, logs) is **hygiene**. Organization is **reconciling the
artifact set to the single source of truth** (the results table / `EVIDENCE.json`) and *naming every gap*. A
repo can be spotless and still be un-shippable because a third of its results have no local ckpt and no local
input data. Do the reconciliation first; hygiene is the easy part that comes after — and doing hygiene *as if it
were* organization is the trap this file exists to break.

## The reconciliation — one pass over the results table

Enumerate the **full expected grid** of runs (every dataset × method × rate × seed × noise the paper claims),
then for **each** cell that carries a reported number, confirm the chain — don't sample, enumerate:

```
[ ] CKPT    — a checkpoint exists locally, OR it's on the pull-before-teardown manifest.
              "only on the remote, unlisted" is a silent hole one teardown away from gone.
[ ] SPLIT   — the number was scored on the split it CLAIMS (test, not val/train). Read the result
              json's split field / source path; never assume from the filename.
[ ] INPUTS  — everything needed to RE-DERIVE it is present: the raw data AND any DERIVED input the
              method consumes (e.g. the reconstructed images a reconstruct-then-segment baseline
              trains on). A row whose number exists but whose input data is absent is NOT locally
              reproducible — number-complete, artifact-incomplete.
[ ] VIZ/FIG — if a figure or qualitative panel is claimed for this cell, its source (per-figure
              data.json / prediction montage) is present.
[ ] UNIFORM — if an output is expected PER-UNIT of a class (every ckpt → an eval + a montage), it is
              present for EVERY unit, in ONE schema. "Only K of N existed upstream" is a reason to
              GENERATE the other N−K, not to ship K and log a gap — naming a gap is the floor, not the
              finish, when the gap is cheaply closable with a tool you already have.
```

**Generate to close, don't just annotate.** The reconciliation's job is not only to *find* holes but to *close* the
ones you can. If the missing per-unit output is producible (`evaluate.py --save_vis_dir`, a re-render script) and
you hold the inputs, **generate it** until the class is uniform — then re-check that the count actually reached N/N.
A store where 23 of 70 ckpts have a montage and the rest are bare is not "organized with a documented gap"; it is
un-uniform, and the fix was one loop away.

**Follow the dependency chain when you generate.** Closing a per-unit gap can require first regenerating a *derived
input* the output depends on (a reconstruct-then-segment eval's montage needs the rate-specific reconstructed images;
they may not exist locally). Regenerate the whole chain — and the regenerated input is now a **canonical, kept,
git-ignored** artifact (co-located with its siblings, named in the manifest), not a throwaway you delete after. A
gap you "closed" by generating into a temp dir you then rm is a gap that reopens the next time anyone re-runs.

**Reproduce-to-verify after you regenerate.** A regenerated number is only trustworthy if it *matches the
authoritative source* it should — diff every regenerated `metric` against its results-table row / figure `data.json`
(exact, not "close"). All-match confirms two things at once: the pipeline is deterministic AND the store is sound.
A silent mismatch here is either an environment drift or a stale "authoritative" value — both are findings, not
noise to smooth over.

Every broken link is a **disclosure**, not a silent pass: *"row X: number present, ckpt only on remote"*;
*"cs_mnist / cs_wbc reconstructions absent → the TA-CS rows are not locally reproducible"*; *"recon baseline ran
on mnist+wbc but not carvana"*. **Number-complete ≠ artifact-complete**: every row can be on the test split
(numbers done) while the inputs and per-config viz are partial. Reconcile **both** layers, and write the gaps
down where the next person will see them.

## Nine traps this catches (each has shipped a broken or un-reproducible delivery)

1. **"Don't-touch" ≠ "don't-look".** A user-owned `figures/` tree can hide the *real* per-checkpoint eval
   output (tens of thousands of files), partial reconstruction data, AND a deletable browse subset in one
   folder. Inventory it before you call it off-limits *or* call it clean — a dir you refuse to open is a dir
   you cannot vouch for.
2. **Dedup by content, not by name.** The same predict/eval script copy-scattered across `_rev/`,
   `_phys_quant/`, `scripts/` — `md5sum` them; byte-identical copies are redundancy a filename scan misses,
   and a shared-logic file edited in one place and not the other is a silent divergence.
3. **Never delete a "regenerable byproduct" before proving it isn't the primary source.** A `*_browse` /
   `*_浏览` / `*_subset` copy can look like the main artifact; trace which file the results/figures actually
   *consume*, then delete the copy, never the source. Getting this right by luck is not getting it right.
4. **Completeness is per-cell, not per-family.** "recon baselines ran" / "TA trained" hides that the grid has
   holes — one dataset missing, one recon set absent, one split train-only. Build the full expected grid and
   diff every cell against what exists; a family that "ran" can be 60% populated.
5. **Timestamps are provenance.** N checkpoints written one minute apart is a **bulk copy** (an archival pull),
   not N trainings; a dated archive dir (`_ckpts_<date>/`) held apart from the live output dir is
   **intentional** — it protects the core sweep from being overwritten by later runs — not clutter to
   "consolidate". Read `mtime` before you infer how an artifact was produced.
6. **The pull-before-teardown manifest is an OUTPUT of this reconciliation, not a guess.** What to `scp` back
   before you stop the meter = exactly the artifacts the completeness diff shows exist **only remotely** (sweep
   ckpts, derived input data, full eval_vis). Order is fixed: **reconcile → pull the only-remote set →
   `verify_local.py --expect N` → only then tear down.** Teardown before verify-green is how a paper's rate
   curve becomes unreproducible forever.
7. **The single source of truth stays the anchor.** Organize *around* the results table / `EVIDENCE.json`;
   everything else is a regenerable byproduct — but "regenerable" must be **true** (the regen script *and its
   inputs* both present and runnable), or it is a hole wearing a "safe to delete" label.
8. **"Regenerable" decides long-term keep/drop — NEVER whether to rescue before teardown.** The moment a box is
   about to be stopped or destroyed, pull *every* only-remote output — ckpts, eval results, eval_vis, recon
   outputs, logs — **regardless of whether it can be regenerated.** Regenerating costs GPU-hours and money and is
   often not bit-identical; a dead instance regenerates nothing. *"It's regenerable, skip the pull"* is the exact
   rationalization that tears down a box having abandoned real results. **Rescue first, decide keep/drop later, on
   your own disk.** Corollary — **remote state is volatile**: if one artifact class has *already* vanished between
   two of your own queries (a `checkpoints/` that listed 40 dirs an hour ago now `du`-ing to `0`), treat every
   remaining output as on borrowed time and pull it *now*, before you organize anything.
9. **Consolidate to ONE canonical store per artifact class; co-locate each result's eval with its ckpt.** Three
   checkpoint folders with three naming schemes (`checkpoints/<n>/best.pth` + `_ckpts_<date>/<n>_best.pth` +
   `_ckpts_remote/<n>/best.pth`) is **not organized — it is three piles.** Organizing means: similar artifacts in
   **one** store under **one** naming; each checkpoint's eval **co-located with it or indexed to it** (a
   `ckpt_path` column on the results table) so *"where is this ckpt's eval"* is never a scavenger hunt; and
   redundant / stale / superseded copies (old-naming `*_cardisjoint`, a `_m512` that just re-runs the default seed)
   **deleted, not stacked.** A dated *archive* held apart is fine (trap 5); *N live stores of the same class* is
   drift waiting to happen. "Put a new folder next to the old ones" is the anti-pattern this trap names. **"One
   store" also means one SCHEMA and one source per fact:** if `eval_test.json` means three different things across
   the store (a real eval, an older eval missing the paper's primary metric, a per-ckpt copy of the results-table
   rows), the filename lies. Regenerate the odd ones out to the single canonical schema, and keep table-level
   secondary data (e.g. the whole noise sweep) in its ONE source (the results CSV) — never fanned out into per-unit
   bundle files that duplicate it and rot independently.

## Where this sits

`data-architecture.md` = the on-disk tree; **this file** = proving that tree is *complete and consistent with
the results table* before delivery; `delivery-gate.md` = the per-number disclosure that this reconciliation
makes trustworthy. Run it whenever you tidy an experiment repo, assemble a replication package, or decide what
to save before a remote teardown — the three moments where "it looks organized" most often hides "a third of it
is missing".
