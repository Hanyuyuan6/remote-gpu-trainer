# Delivering — the principles (the WHY behind a defensible deliverable)

**The core insight: the entire deliverable — every number, figure, and table that ships — is a
*deterministic function* of one immutable, versioned evidence layer.** Provenance and cross-document
consistency are locked by **mechanism**, not by a human remembering to update three documents after a
fix. This is the upstream cousin of `references/verifying/methodology.md` §14 (cross-document number
reconciliation): verifying *catches* a stale number after it drifts; delivering makes drift *physically
impossible* by generating the presentation layer from the evidence layer instead of transcribing into it.

This file is the *why*. The mechanics live next to it:
- the directory layout that makes it real → `references/delivering/data-architecture.md`
- the two manifest schemas (`EVIDENCE.json` + `provenance.json`) → `references/delivering/evidence-manifest-schema.md`
- the one-folder-per-figure convention + the pixel gate → `references/delivering/figures.md`
- the pre-ship disclosure gate → `references/delivering/delivery-gate.md`

To jump: `grep -n '^## ' references/delivering/principles.md`.

---

## Two stances that run through all eight principles

**【User sovereignty — disclose once, then stop】** Research judgment belongs to the user: how many seeds,
which qualitative samples to show, whether an `aux` channel even exists, whether to spend submission-grade
effort now or stay in exploration mode. **The skill organizes the evidence and surfaces each tradeoff
exactly once — it does not mandate, and it does not nag.** Concretely: if the user has declared a
single-seed budget, state the limitation *one time* ("this number is one seed; it has no variance band, so
a delta inside run-to-run noise can't be distinguished from signal") and then **move on** — do not re-raise
multi-seed at every subsequent number. The mechanism (manifests, generated tables, content-addressing) is
non-negotiable plumbing; what the *science* should be is the user's call.

**【Audit → disclose, never enforce / block】** The skill is an honest auditor, not a gate guard. **What is
mandatory is *disclosure*, not the *fix*.** When an integrity issue surfaces — no disjoint validation split,
a leak between train and test, the test split touched during selection, a number that can't be re-derived —
it **must be surfaced alongside the conclusion it affects; it cannot be hidden.** But the skill does **not**
refuse to render the figure, block the export, or withhold the table. This is
`references/verifying/methodology.md`'s rule applied to delivery: **"disclose it, or don't claim it."** The
user, fully informed, decides whether to ship, caveat, or fix. (See `references/delivering/delivery-gate.md`
for how this becomes a concrete pre-ship checklist that *discloses* rather than *halts*.)

These two are not in tension. Sovereignty says *you* choose the science; audit-then-disclose says the skill
will never let a known problem ship *silently* under your name. The skill removes the failure mode where a
number is wrong and nobody said so — it does not remove your authority over the experiment.

---

## The eight principles, tiered

Three tiers, so a user knows what to wire on day one versus what to flip on near submission:

- **CORE** — wire from the first real result. Cheap, and each prevents a class of silent error that is
  expensive to unwind later (a transcribed number that went stale; an overwritten run you can't reproduce;
  a figure with a rendering bug nobody caught).
- **进阶 · 投稿期开 (advanced, flip on near submission)** — full power costs setup effort and pays off when
  the result is going *out the door* (a reviewer, a thesis committee, a public repo). In exploration, the
  CORE four are enough; don't pay this tax early. **YAGNI applies to provenance too.**
- **DROPPED** — deliberately not in scope; the decision belongs to the user, not the skill.

| # | Principle | Tier |
|---|---|---|
| **P1** | Evidence layer / presentation layer cleanly separated | **CORE** |
| **P2** | Numbers **generated**, not **transcribed** (LaTeX macro / `\input` from `results.json`) | **CORE** |
| **P3** | Content-addressed + append-only immutable provenance | **CORE** |
| **P4** | Data / split versioned, hash-pinned | 进阶 · 投稿期开 |
| **P5** | One-command repro from a clean clone | 进阶 · 投稿期开 |
| **P6** | Fixed showcase samples | **DROPPED** (sample selection is the user's) |
| **P7** | Figure-chain traceability + pixel re-open gate | **CORE** |
| **P8** | Delivery = **disclosure** gate (NOT blocking) | **CORE** |

---

## P1 【CORE】 — Evidence layer / presentation layer cleanly separated

**The presentation layer (figures, tables, the PDF) contains *zero* hand-typed numbers; 100 % of them are
generated from the evidence layer** (the metrics JSON, the checkpoint-eval output). A number that a human
typed into a `.tex` table or a slide is a number that *will* go stale the moment the underlying result is
re-run, and nothing will tell you it drifted.

The two layers, and the rule between them:

| Layer | What lives here | Mutability |
|---|---|---|
| **Evidence** | `results.json`, `provenance.json`, `checkpoints/`, split id files, the raw eval output | **Immutable** once written (P3) — the source of truth |
| **Presentation** | `\input` tables, generated figures, the compiled PDF, slides, README numbers | **Disposable** — regenerated from evidence on demand |

The directional rule: **evidence flows *into* presentation, never the reverse.** You never edit a number in
the presentation layer; you fix it in the experiment, re-run into a new evidence record (P3), and
regenerate. If you find yourself hand-correcting a figure caption's number, the architecture has been
violated — that number had no generator. The whole of P2/P7 is the *machinery* that enforces P1; P1 is the
*principle* they serve.

## P2 【CORE】 — Numbers are GENERATED, not TRANSCRIBED

**The strongest form of cross-document consistency: make a stale number physically impossible.** A LaTeX
macro or an auto-generated `\input` table reads its value from `results.json` at *build* time — so the
compiled paper *cannot* disagree with the evidence, because it never held an independent copy to disagree
with. This is the terminal form of `references/verifying/methodology.md` §14: §14 *detects* drift by
grepping every document against the source; P2 *eliminates* the drift by giving every document exactly one
shared source it reads live.

Concretely:
- A build step reads `results/<exp>/runs/<sel>/results.json` and emits `\newcommand{\mainPSNR}{31.42}`
  into a generated `macros.tex`, or emits a full `\begin{tabular}…\end{tabular}` into `table_main.tex`.
- The paper says `\mainPSNR` / `\input{table_main}` — never the literal `31.42`.
- Re-run the experiment → regenerate → the number updates *everywhere it appears at once*, including
  abstract, results table, and conclusion, because they all dereference the same macro.

The payoff is exactly the failure mode §14 chronicles — "a corrected number still surviving in the slides,"
"a README citing the old compression ratio long after the code moved on." Under P2 there is no second copy
to leave stale. **The generator script is itself a tracked artifact** (it lives with the figure or in the
build, not in someone's shell history), so "how was this table produced?" always has a file answer.

> **Sovereignty note:** P2 governs *transcription*, not *what's true*. If the user reports a single-seed
> number, the generated macro emits that single-seed number — and the disclosure ("one seed, no variance
> band") rides *with* it (P8), stated once. P2 guarantees the paper and the slides show the *same* number;
> it does not silently inflate a thin result into something it isn't.

## P3 【CORE】 — Content-addressed + append-only immutable provenance

**Every produced artifact is addressed by `hash(config + code-git-sha + data-hash + seed + env-lock +
hardware)`; a re-run goes into a *new* run directory and never overwrites the old one.** This is
`references/verifying/methodology.md` §3's "never mutate the original artifact while investigating," made
structural rather than a remembered discipline. The directory law is in
`references/delivering/data-architecture.md`: `results/<exp-id>/runs/<run-id>/` is **append-only** — a
re-run mints a fresh `<run-id>`; a `selected` pointer (a symlink) names which run is the current chosen one.

Why content-addressing and append-only are the same idea from two sides:
- **Content-addressing** answers "are these two numbers from the same conditions?" — if two runs share the
  provenance hash, they were produced under identical config/code/data/seed/env/hardware; if the hashes
  differ, *something* differed and any comparison between them is confounded (the §1 Probe-1 check, made
  automatic). The hash *is* the comparability certificate.
- **Append-only** answers "can I get the old number back?" — yes, because re-running never destroyed it.
  This is what makes the verifying-side rule "back up the original FIRST before you re-run" (§3) unnecessary
  *by construction*: there is nothing to back up because nothing is overwritten.

The `provenance.json` schema (the hash inputs + the tracker run-id back-link) is defined in
`references/delivering/evidence-manifest-schema.md`. Pairs with the lifecycle-aware checkpoint policy: which
checkpoints a run keeps (`best` for selection, `last` for resume) is set by that policy, not duplicated here.

## P4 【进阶 · 投稿期开】 — Data / split versioned, hash-pinned

**Record split membership + a checksum in the manifest, so leakage is machine-checkable and the exact data
is recoverable.** When this is wired, the leakage probes of `references/verifying/methodology.md` §4 stop
being a manual audit and become an assertion the manifest can run: cross-split id intersection must be
empty; the recorded data-hash must match what's on disk; a `fit`-time transform must have seen train ids
only.

Why it's **进阶, not CORE**: the value is highest when (a) the dataset is *not* a fixed public benchmark
with canonical splits, and (b) the result is going out for review where a skeptic must be able to reproduce
the *exact* partition. When the dataset is a frozen standard split everyone uses, the marginal value of
hashing it is lower — the field already agrees on what `test` is. Flip P4 on as submission nears, or
immediately if you're constructing custom splits (where the case-insensitive-FS / re-split leakage of §4 is
a live hazard).

> **Audit-then-disclose still applies even when P4 is off.** Not hashing the split does **not** excuse
> hiding a known leak. The split must be a first-class, *audited* object regardless of tier
> (`references/delivering/data-architecture.md`: `splits/{train,val,test}.ids`); P4 only adds the
> *machine-checkable* hash on top of the always-required *disclosure*. Train / val / test must be
> separated and audited; if the audit finds a problem, it is disclosed — never enforced, never hidden.

## P5 【进阶 · 投稿期开】 — One-command repro from a clean clone

**A single `repro.sh` / `make paper` pins the environment → pins the checkpoint-eval → regenerates the
metrics → the tables → the figures, runnable from a fresh `git clone` on a clean machine.** This is the
operational test of `references/verifying/methodology.md` principle 6 / §13: *could a skeptic reproduce this
exact number from your released code + data + config?* If the answer requires the author's machine, their
shell history, or an undocumented manual step, **it is not yet a result** — it's an artifact that happened
to be produced once.

The chain `repro.sh` drives is exactly the P1→P2→P7 pipeline run end-to-end:
`env-lock → checkpoint eval → results.json → generated tables (P2) → figures (P7)`. Because P1–P3 already
made every downstream artifact a deterministic function of the evidence layer, P5 is mostly *wiring
together generators that already exist*, not new work — which is why it's cheap to flip on *if* P1–P3 were
respected from the start, and painful to retrofit if they weren't.

Why **进阶**: in exploration you re-run from your own working tree constantly; the clean-clone guarantee
buys nothing until the work is going *out*. Flip it on for submission / public release / thesis archival.

> **Submission-tier externalization (optional — the public-release hop).** P5 makes the result reproducible
> *on your box*; one hop more makes it *reviewer-citable* — deposit the immutable evidence layer
> (`EVIDENCE.json` + the `results.json` / `provenance.json` / `splits/` it maps) to a public archive
> (Zenodo / figshare) for a **DOI**, and generate a **Data / Code Availability statement** from it. The
> depositable artifact is already built; the deposit *craft* (repository choice, accession, DataCite, FAIR)
> belongs to the **`nature-data`** companion (`references/companions.md`). Flip on at true public release only.

## P6 【DROPPED】 — Fixed showcase samples

**Deliberately out of scope.** *Which* qualitative examples to display in a figure — the showcase set — is
a **research-presentation judgment that belongs to the user**, not a mechanism the skill should fix or
standardize. Pinning a canonical showcase set risks (a) the skill silently choosing what the paper
foregrounds, and (b) sliding toward cherry-picking dressed up as "the standard samples."

What the skill *does* own is the *plumbing* around qualitative output, not its *selection*: the
`qualitative/<task>/<dataset>/{image,gt,pred[,aux]}/` tree is **derived and prunable**
(`references/delivering/data-architecture.md`), and the **figure that displays chosen samples is traceable**
back to the runs it drew from (P7). The user picks the samples; the skill guarantees the picked samples are
real outputs of the named run and that the figure rendering them is correct. Selection stays human;
provenance stays mechanical.

## P7 【CORE】 — Figure-chain traceability + pixel re-open gate

**Every figure is traceable along the chain `results.json → source_data.csv → figure`, carries a
`.provenance` sidecar, and is *re-opened at the pixel level* after rendering.** Two distinct guarantees in
one principle:

1. **Traceability (the chain + the sidecar).** A figure is not a free-floating PNG someone made in a
   notebook; it lives in a one-folder-per-figure layout (`README` + `script.py` + `_build_*.py` +
   `source_data.csv` + `output/`) and a `<fig>.provenance` sidecar records which `EVIDENCE.json` claim and
   which `results.json`(s) it was built from. So "where did this bar come from?" always resolves to a
   specific run. Full convention → `references/delivering/figures.md`.
2. **The pixel gate (a saved figure is not a correct figure).** This is
   `references/verifying/methodology.md` §10 applied at delivery: `savefig` returning cleanly means the
   *file exists*, not that it's *readable or honest*. After rendering, **re-open the PNG and look** — for
   tofu glyphs (`□`) where CJK/Unicode failed, axis labels clipped past the canvas, overlapping panels, a
   truncated y-axis that exaggerates a gap, or a log axis that flattens the very effect. The exit code of
   `savefig` is a log line (`references/verifying/methodology.md` principle 4); the loaded image is the
   artifact. The mechanics of the gate → `references/delivering/figures.md`.

## P8 【CORE】 — Delivery = a DISCLOSURE gate, NOT a blocking gate

**Before any number or figure ships, it should be: verified (`references/verifying/methodology.md` ran on
it), present in `EVIDENCE.json`, regenerable (P2/P5), and cross-document-reconciled (§14) — and its
split / leakage status disclosed *alongside the number itself*.** This is the **audit → disclose** stance
made into a concrete pre-ship pass.

The word **disclosure** is load-bearing, and it is the difference between this skill and a CI gate: the gate
**surfaces** the status of every shipping number; it does **not** refuse to let the user ship. If a number
comes from a split with a known leak, or from a single seed, or can't currently be re-derived, the gate's
job is to **say so, attached to that number**, so the claim travels with its own caveat — never to silently
pass it off as clean, and never to block the user from making an informed decision to ship anyway. Aligns
with **"disclose it, or don't claim it"**: the user may legitimately choose to claim it *with* the
disclosure, or not claim it — what the gate forecloses is claiming it *while hiding* the caveat.

The concrete checklist (what "disclosed alongside" looks like per number) →
`references/delivering/delivery-gate.md`.

---

## How the eight fit together (one mechanism, read top-down)

```
        EVIDENCE LAYER (immutable, append-only — P3)
        results.json · provenance.json · splits/*.ids · checkpoints/
                 │   content-addressed by hash(config+code+data+seed+env+hw)
                 │
   P1: a clean wall — presentation NEVER writes back into evidence
                 │
                 ▼
        PRESENTATION LAYER (disposable, regenerated)
        ├─ P2: tables/macros GENERATED from results.json  (no transcription)
        ├─ P7: figures built results.json → source_data.csv → png, pixel-checked
        └─ (P4 hash-pins the split · P5 regenerates the whole chain in one command)
                 │
                 ▼
        P8: DISCLOSURE GATE — every shipping number carries
            {verified · in EVIDENCE.json · regenerable · reconciled · split/leak status}
            …surfaced, not enforced. The user decides; the skill never hides.
```

The CORE four (P1, P2, P3, P7) plus the P8 disclosure gate are the load-bearing spine — wire them from the
first real number. P4 and P5 are the submission-time hardening. P6 stays with the user. And every step obeys
the two stances: **the user owns the science (sovereignty), and the skill will never let a known problem
ship silently (audit → disclose).**
