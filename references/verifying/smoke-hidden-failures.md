# Failures a short smoke hides — extend, read the loss, verify samples

A green smoke (`isfinite(loss)`, a checkpoint, a metric printed) routinely hides three
distinct outcomes that only separate once you **extend the run** and **read the loss
value, not just the metric**. Abstracted from real cases.

## 1. Extend training to separate undertraining from a real bug

A short smoke (~10 optimiser steps) drives hard-to-train architectures (deep unrolled
nets, transformers, diffusion, multi-rate, from-scratch detectors) to near-random
output. A low/odd metric there is a **hypothesis**, not a verdict. Re-run the SAME config
for ~10–50× more steps **into a separate log dir** and read the trajectory:

| Trajectory under more steps | Verdict |
|---|---|
| metric climbs ~monotonically (e.g. recon PSNR 1→20 dB, 11→18 dB) | **undertraining** — not a bug; the smoke was too short |
| metric flatlines at chance / a degenerate value | likely a bug (or a dead proxy — see the main skill) |
| **loss value diverges to ±∞ or goes negative** | **math bug in the loss** (see §2) |
| metric *decreases* with more steps while loss misbehaves | instability or loss/metric mismatch — inspect the loss math |

Real endpoints from one session: a 7-stage unrolled-transformer reconstructor read
3.3→1.1 dB over a 10-step smoke (looked like divergence) but climbed to **20 dB** at 120
steps — pure undertraining; a multi-rate net stuck at ~11 dB climbed to **18 dB** at 100
steps. Neither was a bug. **Do not conclude "diverging/broken" from a smoke-length run.**

## 2. Read the LOSS VALUE — a loss that explodes or goes negative is a math bug

The metric can look merely "bad" while the **loss value** screams. A bounded-below loss
trending to **−1e16** (or going negative) is an invalid-math bug, not slow learning.
Checklist when a loss is unbounded/negative:

- **Out-of-range targets.** `binary_cross_entropy_with_logits(pred, target)` needs
  `target ∈ [0,1]`. A per-pixel/sample weighting applied by **scaling the target**
  (`target * w`, `w ≥ 1`) pushes targets > 1 → BCE unbounded below → loss → −∞ and the
  model "minimises" garbage. Fix: weight the **per-element loss** (`(w * bce_map).mean()`),
  never the target. (Real case: an uncertainty-weighted seg loss did `BCE(pred*s,
  target*s)`; seg miou *fell* 0.27→0.17; after the fix miou climbed to 0.90.)
- Sign errors; `log` of a non-positive; a term being maximised instead of minimised.

Verify a loss fix in isolation BEFORE retraining: feed random `pred`/`target` plus an
**extreme weight** (to trigger the old blow-up) and assert the loss is finite and ≥ its
theoretical floor.

## 3. Generative / diffusion: a low training loss does NOT mean good samples

For diffusion (and most generative models) the training objective (e.g. ε-prediction
MSE) can be **low while sampled outputs are garbage**. Always score the **sampled
output**, never the training loss alone. Real case: ε-loss 0.04 (excellent) with full-T
sampled PSNR of **3–5 dB** — worse than the conditioning input.

No-retrain diagnostic — **denoise a REAL `x_t`**: take a clean `x0`, form `x_t =
q_sample(x0, t, ε)`, predict `ε̂`, reconstruct `x̂0 = (x_t − √(1−ᾱ_t)·ε̂)/√ᾱ_t` at a
ladder of `t`. Good `x̂0` from a real `x_t` but bad sampling-from-noise ⇒
trajectory/starting-point/data-range issue; bad even from a real `x_t` ⇒ the predictor is
degenerate (a sampler fix won't help).

Common sampler/training bugs:
- **Data range.** DDPM assumes data in **[−1,1]**, not [0,1]. Training on [0,1] then
  sampling from `N(0,I)` can diverge. Scale data to [−1,1] for the diffusion (and back).
- **No x0 clamp / thresholding.** Ancestral iterates drift off the data manifold the
  predictor saw → divergence. Drive each step from a **clamped** `x̂0` (static
  thresholding) plus the `ᾱ_prev` posterior.
- **Respacing.** With `num_steps < T`, using the single-step `α_t` for a strided jump
  under-denoises. Use the `ᾱ_t`/`ᾱ_prev` (DDIM/respaced) update — correct for any stride.
- **EMA warmup.** Eval/sampling usually prefer an EMA copy of the weights. A fixed high
  decay (e.g. 0.9999) leaves the EMA ≈ init over a short run (`0.9999^1200 ≈ 0.89`), so
  the EMA predicts near-randomly while the **main** model is fine. Real case: EMA ε-MSE
  0.89 vs main 0.02; EMA samples 3–5 dB, main ~8 dB — fixed by a step-aware warmup
  `decay_t = min(decay, (1+step)/(10+step))`, which brought the EMA ε-MSE to 0.04
  (matching main). Always load the MAIN weights and the EMA **separately** and compare
  before blaming the model/sampler.

## 4. Decode / post-processing scale check (structured outputs)

Before concluding a detection/keypoint/structured model "learned nothing," verify the
**decoder produces correct-SCALE outputs**: among the decoded candidates, does one match
the GT *size* (e.g. a predicted box ≈ the GT box's w/h)? If yes, the decode is fine and a
~0 metric on a toy dataset is **undertraining** (detection from scratch needs many
steps). Only blame the decode when it cannot produce a correct-scale output at all (a
true scale/stride/anchor bug).

## 5. Resource safety — heavy models run on the GPU instance, never the local dev box

Constructing / forwarding / training / **sampling** a real (non-tiny) model on the local
workstation CPU can exhaust its RAM (a 128² diffusion model OOM'd a 128 GB box). The
local dev box is for **static checks only**: `py_compile`, `ruff`, `pytest` with tiny
fixtures. Run every model construction / forward / training / sampling / eval on the
**GPU instance**. Before launching there, check free GPU memory (`nvidia-smi`); a big
model plus a concurrent job OOMs — drop the batch size and set
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.

## 6. A re-run can load a STALE artifact — verify you loaded the RIGHT one

Re-training into a checkpoint dir that still holds an earlier run's checkpoints, with a
`keep_top_N`-by-epoch-number prune, can keep the OLD (higher-epoch) checkpoints and prune
your fresh (lower-epoch) ones — so `sorted(glob('epoch_*.pth'))[-1]` loads the **stale**
one, and a "the fix didn't work" verdict is actually testing the unfixed model. **Tell:** a
metric **byte-identical across two runs** (same seed → same near-random state is the
giveaway — e.g. an EMA ε-MSE of exactly 0.8941 twice). Clear the checkpoint dir before
re-running, or assert the loaded ckpt's epoch/timestamp is the new one. This is the
"trust the artifact you loaded" invariant one level deeper: also trust it is the artifact
you *think* you loaded.
