# Delivering — figures (one folder per figure, the provenance sidecar, the pixel gate)

This is **P7** made concrete (`references/delivering/principles.md`): every figure is *traceable* along
`results.json → source_data.csv → figure`, carries a `<fig>.provenance` sidecar pointing back to
`EVIDENCE.json`, and is **re-opened at the pixel level** after rendering — because **a figure that *saved*
is not a figure that's *correct*.** The figure's place in the directory tree is in
`references/delivering/data-architecture.md`; this file owns the *convention*, the *sidecar*, and the *gate*.

To jump: `grep -n '^## ' references/delivering/figures.md`.

---

## One folder per figure (script + source_data + output co-located)

A figure is **not** a free-floating PNG produced in a notebook nobody can find again. Each figure is a
self-contained folder under `figures/` (project-level and cross-`exp-id`, because one figure usually pulls
several experiments):

```
figures/
  _style.py                    SHARED at the figures/ root — one place for fonts, palette, sizes, rcParams.
  <fig-name>/
    README.md                  What the figure shows · which claim it backs · how to rebuild · gotchas.
    _build_<x>.py              Assembles source_data.csv FROM the relevant results.json(s). The P2 step:
                               it READS evidence, it does not transcribe numbers by hand.
    source_data.csv            The exact tabular data the figure is drawn from (the chain's MIDDLE link).
    script.py                  The plotting script — imports _style, reads source_data.csv, writes output/.
    output/                    The rendered figure(s): <fig-name>.pdf / .png (vector for the paper, png to
                               eyeball at the pixel gate below).
    <fig-name>.provenance      Sidecar → back-links to EVIDENCE.json + the source results.json(s).
```

Three properties this layout buys:

- **The chain is inspectable.** `results.json` → (`_build_*.py`) → `source_data.csv` → (`script.py`) →
  `output/`. Every bar, point, and error whisker has a row in `source_data.csv`, and that row was *computed
  from* a `results.json` by a tracked script — never typed in. This is **P2** (generated, not transcribed)
  at the figure level: the figure cannot disagree with the evidence because it holds no independent copy.
- **`_style.py` is shared, not copy-pasted.** Fonts, color palette, font sizes, and `rcParams` live once at
  the `figures/` root so every figure is visually consistent and a style fix lands everywhere at once.
- **The figure is rebuildable in isolation.** `cd figures/<fig-name> && python _build_*.py && python
  script.py` regenerates it from the evidence layer — which is exactly the per-figure leg of the **P5**
  one-command repro chain (`references/delivering/principles.md`).

> **Sovereignty boundary:** *which* qualitative samples a figure showcases is the **user's** choice
> (**P6 dropped**, `references/delivering/principles.md`). This convention guarantees the showcased samples
> are genuine outputs of the named run (via the sidecar + the `qualitative/` tree) and that the rendering
> is correct (the gate below) — it does not pick the samples.

---

## The `<fig>.provenance` sidecar (the back-link)

The sidecar answers "where did this figure come from?" — pointing **back to `EVIDENCE.json`** (which claim
this figure substantiates) and **to the specific `results.json`(s)** it was built from. It closes the loop:
`EVIDENCE.json`'s claim points *forward* to the figure (its `figure` field,
`references/delivering/evidence-manifest-schema.md`), and the sidecar points *back* to the claim — a
two-way binding, so neither a figure nor a claim can silently lose its counterpart.

### Filled example (valid JSON)

```json
{
  "figure": "figures/aux-ablation-bar",
  "supports_claims": ["C2-aux-ablation"],
  "built_from": [
    {
      "exp_id": "ours-full",
      "run": "selected",
      "results_json": "results/ours-full/selected/results.json",
      "metric": "PSNR",
      "split": "test"
    },
    {
      "exp_id": "ours-no-aux",
      "run": "selected",
      "results_json": "results/ours-no-aux/selected/results.json",
      "metric": "PSNR",
      "split": "test"
    }
  ],
  "source_data": "figures/aux-ablation-bar/source_data.csv",
  "build": "python _build_bar.py && python script.py",
  "rendered": ["output/aux-ablation-bar.pdf", "output/aux-ablation-bar.png"],
  "disclosure": "Bar for 'w/o aux' is single-seed (no error whisker); see EVIDENCE.json claim C2-aux-ablation.",
  "pixel_check": {"passed": true, "checked": "2026-06-21", "notes": "axes full-range (not truncated); CJK n/a; whiskers shown where seeds>1"}
}
```

- `supports_claims` + `built_from` make the figure's evidence basis explicit and machine-checkable against
  `EVIDENCE.json`.
- `disclosure` carries the audit→disclose caveat that must be visible wherever the figure appears (here:
  one bar is single-seed, so it has **no error whisker** — disclosed, not hidden, and *not* a reason to
  block the figure; **P8**, `references/delivering/principles.md`).
- `pixel_check` records that the gate below actually ran (a `passed:false` is itself a disclosure-worthy
  state, not a silent failure).

---

## The pixel gate — a saved figure is not a correct figure (P7, `references/verifying/methodology.md` §10)

**`savefig` returning cleanly means the file *exists*, not that it's *readable* or *honest*.** The exit code
is a log line (`references/verifying/methodology.md` principle 4: trust the artifact, not the claim); the
**loaded image** is the artifact. After every render, **re-open the PNG and look at the pixels** — by eye,
or programmatically, or both.

### What silently breaks while passing every code check

| Failure | What you see on re-open | Why the code didn't catch it |
|---|---|---|
| **Tofu glyphs** | `□□□` boxes where CJK / Unicode / a math symbol should be | the font lacked the glyph; matplotlib renders a replacement box and `savefig` succeeds |
| **Clipped labels / titles** | axis label or title cut off past the canvas edge | `bbox_inches` / layout didn't reserve room; the file still wrote |
| **Overlapping panels** | subplots / legends colliding | tight-layout failed silently on a crowded grid |
| **Truncated y-axis** | a bar/line gap that looks huge | y-axis doesn't start at the natural baseline — *renders perfectly while misrepresenting* the effect |
| **Misleading axis transform** | a log axis flattening the very effect, or a mean-only bar over n=3 | the plot is technically valid but visually dishonest |
| **Empty / wrong data** | a blank panel, or the wrong series | `source_data.csv` was stale/empty; the axes drew anyway |

The last two rows are where an honest rendering bug shades into the **integrity** territory of
`references/verifying/methodology.md` §10 / the integrity spectrum: a **truncated y-axis** or a
**mean-only bar hiding the spread over n=3** *renders flawlessly* and yet exaggerates or misrepresents — so
the pixel gate is not only a rendering check, it is the last place to catch a figure that lies while looking
perfect. (Disclose the variance, don't truncate the axis to manufacture a gap.)

### By chart type — the data-correctness check beyond the universal ones

The tofu / clipping / empty-data checks above are universal; each chart type then has its own way to
misrepresent the numbers while rendering cleanly:

| Chart type | The type-specific check |
|---|---|
| **Table** | numbers **generated** from `results.json`, not hand-typed (**P2**), and `scripts/reconcile.py` confirms each cell vs `EVIDENCE.json`; consistent decimals / sig-figs + units; report `mean±std` (and `n`), not a bare point; **bold "best" only when the gap clears the error bar** |
| **Bar** | value axis starts at the **natural baseline (0** for a non-negative metric); error whiskers where seeds>1 (else disclose single-seed); don't reorder bars to flatter; equal bar widths |
| **Line / curve** | x **monotonic**, no silent interpolation across missing points; **log axis only if disclosed** (it flattens the very effect); show a CI **band**, not a lone mean line; identical x-range across compared curves |
| **Scatter / box / violin** | show the **distribution**, not one summary dot; equal axis scales when comparing; state `n` |

Each cell is *data*-correctness (does the geometry honestly represent the numbers) — distinct from the
*rendering* failures (tofu / clipping) above. A bar with a truncated baseline, or a table with a hand-typed
cell, passes every render check and still lies.

### How to run the gate

- **Eyeball the rendered PNG** at full size — don't trust the thumbnail. On a remote box, **dump the PNG and
  pull it down to view locally** (`references/run-remote/ssh_transport.md`); don't try to judge a figure over
  a terminal.
- **Programmatic guards** that catch the common silent failures cheaply:
  - **Tofu**: render with a font that has the needed glyphs; assert no missing-glyph warning was emitted
    (matplotlib logs one), or check the rasterized region isn't a row of identical replacement boxes.
  - **Clipping**: render with `bbox_inches="tight"` *and* re-open to confirm the label pixels are inside the
    image bounds (a non-blank margin where the label should be).
  - **Truncated axis**: assert the value axis includes the natural baseline (e.g. `ylim[0] == 0` for a bar
    chart of a non-negative metric) unless a non-zero baseline is *deliberate and disclosed*.
  - **Empty data**: assert `source_data.csv` has the expected non-zero row count before plotting (ties to
    the "check the produced `n`" rule, `references/verifying/methodology.md` §7).
- **Record the result in the sidecar's `pixel_check`** so "I looked" is itself an artifact, not a memory.

> This gate is `references/verifying/methodology.md` §10 applied at delivery — that section owns the *why*
> (the war-stories: CJK tofu, the truncated y-axis exaggerating a gap, the figure that renders while
> misrepresenting). This file owns *running it as the last step before a figure ships*. Whether a figure was
> even *written* (vs only scalars logged) is the typed-tracker-API check of
> `references/verifying/methodology.md` §12 — a grep over event files "confirms" a figure that was never
> written; ask the tracker for the artifact *type*.

---

## The figure leg of the delivery gate

A figure clears its part of the **P8** disclosure gate (`references/delivering/delivery-gate.md`) when:

1. it lives in its own folder with `script.py` + `_build_*.py` + `source_data.csv` co-located (traceable);
2. its `source_data.csv` was **generated** from the named `results.json`(s), not hand-typed (**P2**);
3. its `<fig>.provenance` sidecar back-links to an `EVIDENCE.json` claim and the source `results.json`(s);
4. the **pixel gate ran** — the rendered PNG was re-opened, checked for tofu / clipping / truncated axes /
   empty data, and the result recorded in `pixel_check`;
5. any caveat (single-seed bar, non-zero axis baseline, split status) is in the sidecar's `disclosure` and
   **rides with the figure wherever it appears** — surfaced, not hidden, and **never** used to block the
   figure from shipping.
