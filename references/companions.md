# Companion skills — all OPTIONAL (this skill is standalone)

`remote-gpu-trainer` is **fully self-contained**: every step of RUN → VERIFY → DELIVER works with nothing
but a shell and the bundled `references/` + `scripts/`. The skills below are **recommended but optional**
— each is a *separate* install that deepens one part of the lifecycle. **The skill needs none of them.**
On an agent where one isn't installed, treat its mention here as an optional cross-reference and do the
equivalent with your own tools — the *step* is what matters, not that specific skill.

## Figure drawing (DELIVER, P7)

These produce the publication-grade figure that `references/delivering/figures.md` then traces and
pixel-gates — this skill owns the *provenance + pixel-reopen*, they own the *rendering craft*. Pick one:

- **`nature-figure`** — submission-grade Nature/high-impact figure workflow (matplotlib/seaborn or
  ggplot2), multi-panel layout, SVG/PDF/TIFF export, journal QA.
- **`publication-chart-skill`** — publication-quality charts/plots from data, styling and export focused.
- **`scipilot-figure`** — scientific figure assembly/polish for manuscripts.

> Fallback with none installed: build the figure with plain matplotlib/R inside the figure's one-folder
> layout, then still run the `references/delivering/figures.md` pixel re-open gate yourself.

## Data availability (DELIVER, submission)

- **`nature-data`** — Data / Code Availability statements, repository selection (Zenodo / figshare / OSF),
  accession numbers, DataCite dataset citations, FAIR metadata. This skill builds the immutable, claim-mapped
  evidence layer; `nature-data` turns it into a public, citable deposit at submission time.

> Fallback: deposit `{EVIDENCE.json, results.json, provenance.json, splits/}` to a public archive for a DOI
> yourself, and draft the Data / Code Availability statement from `EVIDENCE.json` + `provenance.json`.

## Experiment verification (VERIFY)

- **`experiment-verifier`** (agent) — audits a result *before* it's reported: seed/determinism, metric
  direction, delta-vs-noise, collapse/smoke artifacts, proxy agreement, and ≥2-axes-changed confounds;
  returns CONFIRMED / SUSPECT / REFUTED with file-cited evidence. Pairs with `references/verifying/`.

> Fallback: run the `references/verifying/methodology.md` ladder by hand and disclose findings with the conclusion.

## Parallel ablation fan-out (RUN)

- **`superpowers:dispatching-parallel-agents`** — the independence predicate (don't fan out onto shared
  mutable state) + the mandatory post-fan-out reconciliation, for launching N ablation cells in parallel.
  Pairs with `references/run-remote/parallel_ablation.md`.

> Fallback: apply the independence + isolated-write-path rules in `parallel_ablation.md` manually, then reconcile.

## HF transport + hosted tracker (RUN / VERIFY)

- **`huggingface-skills:hf-cli`** — the transport verbs (`hf download --resume`, `hf upload-large-folder`,
  `hf cache verify`); this skill owns the China-mirror swap + stall-retry (`references/run-remote/china-network.md`).
- **`huggingface-skills:huggingface-trackio`** — a hosted tracker so metrics survive teardown; poll its
  alerts as a structured monitor instead of brittle ssh-tail. Local forensics equivalent is bundled here as
  `scripts/wandb_forensics.py`.

> Fallback: use `rsync`/`scp` resumable loops (`references/run-remote/ssh_transport.md`) for transport and
> `scripts/wandb_forensics.py` (or any tracker you already use) for run forensics.
