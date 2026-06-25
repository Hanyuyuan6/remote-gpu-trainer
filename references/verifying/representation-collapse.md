# Representation Collapse — Deep Diagnosis Playbook

Load this when a model's output is constant/degenerate across distinct inputs, or a conditioning control gives `real == shuffle`. `references/verifying/methodology.md` §8 has the abstract version; this file has the full worked ladder with the load-bearing numbers from a real diagnosis, so you can pattern-match against concrete evidence.

The running example is a `measurement → image` reconstruction/adapter net (an encoded measurement vector → structured image output), but **every check generalizes** to any "encode an input vector → produce a structured output" model.

---

## The fingerprint: output cross-sample cosine ≈ 1.0

A `measurement→X` net whose output is near-identical across *distinct* inputs is **ignoring its input**, not learning slowly. Two equivalent scalar tells:

- **Output cross-sample cosine ≈ 1.0** on a batch of distinct inputs.
- **`real == shuffle`** in a conditioning control (decode each sample against ANOTHER sample's tokens). A *bit-identical* `real == shuffle` (e.g. `0.126 == 0.126`) means the swap changed nothing ⇒ tokens are sample-invariant ⇒ collapsed. A genuine reader gives `real ≫ shuffle`; `real ≈ shuffle ≈ chance` says the same with scatter.

These are cheaper and more decisive than any loss curve.

---

## Step 1 — Check the INPUT cross-sample cosine first

Before touching the model, compute cross-sample cosine on the **raw input vectors**.

≈1.0 ⇒ the inputs are near-parallel — dominated by a sample-**INVARIANT** component (a DC / low-frequency offset), with the discriminative signal a tiny residual.

Worked numbers: an encoded measurement vector with `|x| ≈ 0.5` and per-element std only `0.0047` — yet a held-out z-scored linear probe decoded the content at **0.54** (≫ chance). So the signal *is* there; it's just buried under the invariant offset. A `Linear` on that raw vector is driven by the offset → constant output.

**Implication:** the fix is at the input, not the model (Steps 3–4). If the input cosine is *low* but the output cosine is high, the collapse is inside the model — but that is the rare case; invariant-dominated input is the common one.

## Step 2 — Diff a working sibling's input layer

If a sibling project ingests the same modality and works, **read its input layer before inventing a fix.** (Real: the working sibling reshaped the measurement and `LayerNorm`'d it at the input; the broken net fed the raw vector straight into `Linear`.) Adopt the sibling's input norm rather than theorizing a new one — and note a *per-sample* norm is also rate/distribution-robust, killing two birds with one principled change.

## Step 3 — RENDER the intermediate; don't trust the proxy

For any reconstruction / canvas / latent intermediate, **dump it and LOOK.** Load ONLY the small front module on CPU (no big frozen backbone), run a few inputs, save a `target vs output` grid.

Two proxies lied in **opposite** directions simultaneously:
- a low recon loss (`L1 → 0.05`, "great")
- a climbing cross-sample cosine ("collapsing")

The rendered image settled it in seconds: **12 distinct digits → 12 identical blobs.** The net had learned the *unconditional mean*, which minimizes mean-L1. The output cross-sample cosine (≈1.0) is the scalar version of the same check — but the image is the ground truth when proxies disagree.

## Step 4 — Fix at the INPUT, not the OUTPUT

Once the input is invariant-dominated, the collapse is **upstream**. A de-collapse objective bolted onto the OUTPUT — a recon head decoding output tokens back to the target, a diversity reg on the output — does **NOT** fix it. A learnable downstream head just *amplifies the tiny residual* of the collapsed representation to satisfy its own loss while the representation stays collapsed.

Decisive A/B (real): an output-token→image recon head left adapter cross-sample cosine at **0.997**; the SAME recon **plus per-feature INPUT standardization** dropped it to **0.80**. Standardize the input; only then does any downstream de-collapse loss have diverse features to shape.

**What counts as input normalization:**
- ✅ Per-feature z-score (train stats in persistent buffers → saved in ckpt)
- ✅ Per-sample `LayerNorm` over reshaped chunks (also distribution-robust)
- ❌ A physics / `[0,1]` *preprocessing* scalar — a global per-sample factor that does NOT remove the per-feature invariant component. Not input normalization.

## Step 5 — Train-ok / val-collapsed ⇒ per-split input-distribution mismatch

A net that de-collapses on the train split but stays collapsed on val/test usually gets a **different input distribution per split** — e.g. the val/test pipeline forces a fixed sampling rate (often the **geometric mean** of the train range) while train varies it. Dump per-split input stats (`sampling_rate`, per-feature std, cross-sample cosine), not just the model's outputs. A per-sample input norm survives this; a norm that bakes in *train* dataset statistics does not (its std is inflated by train-only variation, suppressing the signal at the val operating point).

## Step 6 — Architecture-invariant failure ⇒ stop redesigning, diff the input

When the SAME failure signature (collapse, `real==shuffle`, chance-floor metric) survives **every architecture change** — frozen vs LoRA, encoder A vs B, with vs without an aux head, reconstruction vs distillation — the cause is **upstream of the architecture**: input pipeline, normalization, or target construction. Each pivot then invents a fresh just-so story for the *same* number and burns a retrain.

The tell is the **invariance itself** — a real architectural cause would shift the signature. (Real: ~15 successive adapter redesigns each "explained" a collapse that was really one missing per-feature input standardization; once standardized, the *first, simplest* architecture de-collapsed — `adapter_cosine 0.997 → 0.80`.)

---

## Two confounders to avoid while diagnosing

**Isolating a working config's advantage (mirror of Probe 1).** When a config that WORKS differs from a failing one in **≥2 ways at once** (e.g. it routes through a pretrained ViT *and* carries a de-collapse loss), you cannot attribute the win to either — it's confounded. Run one-axis-at-a-time intermediates (each advantage alone, holding all else on the failing baseline's controlled settings) before concluding "X is necessary". (Real: the working recipe had both a ViT path and input standardization; only the standardization-alone cell isolated the true cause.)

**A dense aux loss at weight 1 can do nothing.** `reduction='mean'` divides the gradient by element count (`3·336·336` ⇒ ~`3e-6`/px at w=1), swamped by a concentrated competing loss. Scale the aux weight ~N (element count) and **verify the aux actually moves** before concluding it's ineffective.

---

## Kill-it-early rule

The de-collapse signal (output cross-sample cosine; or a tracker's unique-prediction-count / predicted-class histogram) settles within **~1 epoch**. Cosine pinned near 1.0 + predictions piling onto a single class ⇒ it will not recover. A multi-hour run to a foregone `real==shuffle` is wasted GPU — watch that signal live and early-stop in epoch 1.

---

## Quick command sketch (adapt to your model)

```python
# Output collapse fingerprint — run on a batch of DISTINCT inputs
import torch, torch.nn.functional as F
out = model(x)                       # [B, D] or flattened
out = out.flatten(1)
cos = F.cosine_similarity(out[:, None], out[None], dim=-1)   # [B, B]
offdiag = cos[~torch.eye(len(out), dtype=bool)]
print("output cross-sample cosine mean:", offdiag.mean().item())   # ≈1.0 ⇒ collapsed

# INPUT invariance check — same on the raw input vectors
xi = x.flatten(1)
cosi = F.cosine_similarity(xi[:, None], xi[None], dim=-1)
print("INPUT cross-sample cosine mean:", cosi[~torch.eye(len(xi), dtype=bool)].mean().item())
print("per-feature std:", xi.std(0).mean().item())            # tiny ⇒ invariant-dominated

# Held-out raw-input ceiling — is the signal even there?
#   fit a linear probe on 70% of (raw input -> label), score on 30%.
#   ≫ chance ⇒ signal present, model is the destroyer; ≈ chance ⇒ signal not in input.
```
