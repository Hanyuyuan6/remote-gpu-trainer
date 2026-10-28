#!/usr/bin/env python3
"""Pre-launch audit: normalization at the data's real scale, and a throughput budget.

A green CPU rehearsal proves the code runs. It does not prove that a normalization layer sees the
signal, or that the rented GPU will be fed. Two checks close that gap before a long paid run:

  inputs  on one real batch, before renting (in the rehearsal, audit_model also hooks every
          normalization layer): each layer's input spread against its eps, and the raw input's
          finiteness, scale, DC share and range. Catches a LayerNorm whose eps outweighs inputs
          measured in physical units (volts, amperes), and a min-max range set by one zero-order
          coefficient instead of the signal.
  speed   in the first minutes on the node: the share of each step spent waiting for data,
          samples/s, and the projected hours and cost of the planned steps.

Library use, inside the project's own rehearsal (torch is imported only by audit_model):
    sys.path.insert(0, "<skill>/scripts"); import preflight_audit as pa
    found = pa.audit_model(model, batch) + pa.audit_inputs(batch)
    waits, steps = pa.time_steps(loader, train_step, n=50, sync=torch.cuda.synchronize)
    found += pa.audit_speed(waits, steps, batch_size=B, planned_steps=N, price_per_hour=P, budget=C)
    raise SystemExit(pa.report(found))
CLI on saved numbers, no torch needed:
    python3 preflight_audit.py inputs --npy batch.npy
    python3 preflight_audit.py speed --timings timings.json --batch-size 64 --planned-steps 100000 \
        --price-per-hour 2 --budget 100             # timings.json: {"wait_s": [...], "step_s": [...]}
Exit codes: 0 no FAIL (WARN lines may remain), 1 at least one FAIL, 2 unusable input.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

# Spread/eps thresholds. A layer divides by sqrt(spread + eps), so its output shrinks by
# 1 - sqrt(r / (r + 1)) at r = spread/eps: 29 % at r = 1, 4.7 % at r = 10, 0.5 % at r = 100.
EPS_FAIL = 10.0
EPS_WARN = 100.0
EPS_WARN_ROW_SHARE = 0.10  # WARN when more than this share of rows sits below EPS_FAIL
# Raw-input bands. Networks are initialised for inputs of order 0.1-1; outside [0.01, 10] the first
# layers start far from their tuned operating range (raw 0-255 images, sub-millivolt readouts).
RMS_BAND = (1e-2, 1e1)
DC_SHARE_WARN = 0.9      # mean^2 / mean-square: the offset carries > 90 % of the energy
RANGE_RATIO_WARN = 3.0   # (max - min) / (p99 - p1): a Gaussian sample of 16k values gives ~1.7
# Data-wait share of wall time per step. Above 0.2 the GPU idles a fifth of the paid time.
WAIT_WARN = 0.2
WAIT_FAIL = 0.5

# Matched anywhere in the class name, so LlamaRMSNorm, FusedLayerNorm and SyncBatchNorm count too.
NORM_KINDS = (("LayerNorm", "layer"), ("RMSNorm", "rms"), ("GroupNorm", "group"),
              ("BatchNorm", "batch"), ("InstanceNorm", "instance"))


def finding(level: str, code: str, where: str, message: str) -> dict:
    return {"level": level, "code": code, "where": where, "message": message}


def as_array(x) -> np.ndarray:
    if hasattr(x, "detach"):
        x = x.detach().float().cpu().numpy()
    return np.asarray(x, dtype=np.float64)


def spread_rows(kind: str, x, *, normalized_dims: int = 1, groups: int | None = None) -> np.ndarray:
    """The per-row quantity a normalization divides by before adding eps.

    layer: variance over the last `normalized_dims` axes; rms: mean square over them; group:
    variance within each channel group of an (N, C, ...) input; batch: per-channel variance over
    every other axis; instance: per-sample, per-channel variance over the spatial axes.
    """
    x = as_array(x)
    if kind in ("layer", "rms"):
        rows = x.reshape(-1, int(np.prod(x.shape[x.ndim - normalized_dims:])))
        return rows.var(axis=1) if kind == "layer" else np.mean(rows * rows, axis=1)
    if kind == "group":
        if not groups or x.shape[1] % groups:
            raise ValueError(f"{groups} groups do not divide {x.shape[1]} channels")
        return x.reshape(x.shape[0], groups, -1).var(axis=2).ravel()
    if kind == "batch":
        return np.moveaxis(x, 1, 0).reshape(x.shape[1], -1).var(axis=1)
    if kind == "instance":
        return x.reshape(x.shape[0] * x.shape[1], -1).var(axis=1)
    raise ValueError(f"unknown normalization kind {kind!r}")


def judge_layer(where: str, spread, eps: float) -> list[dict]:
    spread = as_array(spread)
    if not np.isfinite(spread).all():
        return [finding("FAIL", "NONFINITE", where,
                        f"{int((~np.isfinite(spread)).sum())} non-finite spreads: this layer's input is not finite")]
    ratio = spread / float(eps)
    median = float(np.median(ratio))
    low = float(np.mean(ratio < EPS_FAIL))
    fix = ("rescale the data upstream to order 0.1-1 (for example divide each sample by its RMS) "
           "rather than trusting this layer to do it")
    if median < EPS_FAIL:
        return [finding("FAIL", "EPS_DOMINATED", where,
                        f"median input spread is {median:.3g}x eps={eps:g}; eps sets the output "
                        f"scale, not the data. {fix}")]
    if median < EPS_WARN or low > EPS_WARN_ROW_SHARE:
        return [finding("WARN", "EPS_CLOSE", where,
                        f"median spread {median:.3g}x eps, {low:.0%} of rows below {EPS_FAIL:g}x")]
    return []


def audit_inputs(x, where: str = "input") -> list[dict]:
    """Finiteness, scale, DC share and range of a raw batch (first axis = samples)."""
    x = as_array(x)
    if x.ndim == 0 or x.shape[0] == 0:
        return [finding("FAIL", "EMPTY", where, "no samples")]
    if not np.isfinite(x).all():
        return [finding("FAIL", "NONFINITE", where,
                        f"{int((~np.isfinite(x)).sum())} non-finite values; fix the loader before anything else")]
    rows = x.reshape(x.shape[0], -1)
    mean_square = np.mean(rows * rows, axis=1)
    rms = np.sqrt(mean_square)
    found = []
    median_rms = float(np.median(rms))
    if not RMS_BAND[0] <= median_rms <= RMS_BAND[1]:
        found.append(finding("WARN", "SCALE", where,
                             f"median per-sample RMS {median_rms:.3g} is outside {RMS_BAND[0]:g}-{RMS_BAND[1]:g}; "
                             "inputs of order 0.1-1 are what the initialisation and every eps assume"))
    live = mean_square > 0
    if live.any():
        dc_share = float(np.median(rows.mean(axis=1)[live] ** 2 / mean_square[live]))
        if dc_share > DC_SHARE_WARN:
            found.append(finding("WARN", "DC_DOMINATED", where,
                                 f"the per-sample offset carries {dc_share:.1%} of the energy; an RMS or "
                                 "min-max scale of this input mostly measures the offset"))
    spread = np.percentile(rows, 99, axis=1) - np.percentile(rows, 1, axis=1)
    usable = spread > 0
    if usable.any() and rows.shape[1] >= 100:
        ratio = float(np.median((rows.max(axis=1) - rows.min(axis=1))[usable] / spread[usable]))
        if ratio > RANGE_RATIO_WARN:
            found.append(finding("WARN", "RANGE_SET_BY_FEW", where,
                                 f"max-min is {ratio:.3g}x the 1-99 % spread: a few coordinates (a zero-order "
                                 "or DC coefficient, hot pixels) set any min-max scale, and a perturbation ratio "
                                 "measured after that scaling reflects them, not the signal-to-noise ratio"))
    if (rows.std(axis=1) == 0).any():
        found.append(finding("WARN", "CONSTANT_SAMPLE", where,
                             f"{int((rows.std(axis=1) == 0).sum())} constant samples; per-sample scaling divides by zero"))
    return found


def norm_kind(module) -> str | None:
    name = type(module).__name__
    return next((kind for marker, kind in NORM_KINDS if marker in name), None)


def audit_model(model, batch, *, forward=None) -> list[dict]:
    """Hook every torch normalization module, run one no-grad forward, judge the spread of every
    call against eps (a module shared by several heads or steps is judged on each input it sees).

    The model keeps its mode, so a training-mode BatchNorm is judged on the batch statistics it
    would use; buffers (running statistics) and the RNG are restored afterwards, so the audit does
    not change the run it checks. Functional calls (F.layer_norm inside a custom block) are
    invisible here: audit those inputs with judge_layer(name, spread_rows(kind, x), eps) at the call site.
    """
    import torch

    seen: list[tuple[str, np.ndarray, float]] = []
    hooks = []
    for name, module in model.named_modules():
        kind = norm_kind(module)
        if kind is None:
            continue
        if kind == "layer" and hasattr(module, "variance_epsilon"):
            kind = "rms"  # Hugging Face T5LayerNorm and its kin divide by the mean square, as RMSNorm does

        def hook(mod, args, name=name or type(module).__name__, kind=kind):
            x = args[0]
            eps = getattr(mod, "eps", getattr(mod, "variance_epsilon", None))
            if eps is None:  # torch RMSNorm(eps=None): machine eps of its compute type, float32 for half inputs
                eps = torch.finfo(torch.float32 if x.dtype in (torch.float16, torch.bfloat16) else x.dtype).eps
            shape = tuple(getattr(mod, "normalized_shape", ()) or ())
            if (kind in ("layer", "rms") and len(shape) == 1 and x.ndim >= 3
                    and x.shape[-1] != shape[0] and x.shape[1] == shape[0]):
                x = x.movedim(1, -1)  # channels-first variants (LayerNorm2d) normalize over dim 1
            if kind == "batch" and not mod.training and getattr(mod, "running_var", None) is not None:
                spread = as_array(mod.running_var)
            else:
                spread = spread_rows(kind, x, normalized_dims=len(shape or (1,)),
                                     groups=getattr(mod, "num_groups", None))
            seen.append((name, spread, float(eps)))

        hooks.append(module.register_forward_pre_hook(hook))
    saved = [(buffer, buffer.detach().clone()) for buffer in model.buffers()]
    try:
        with torch.no_grad(), torch.random.fork_rng():
            (forward or model)(batch)
    finally:
        for handle in hooks:
            handle.remove()
        with torch.no_grad():
            for buffer, copy in saved:
                buffer.copy_(copy)
    if not seen:
        return [finding("WARN", "NO_NORM_LAYERS", "model",
                        "no normalization module ran; check functional normalization by hand")]
    found, calls = [], {}
    for name, spread, eps in seen:
        calls[name] = calls.get(name, 0) + 1
        found += judge_layer(name if calls[name] == 1 else f"{name} (call {calls[name]})", spread, eps)
    return found


def time_steps(batches, step, *, n: int = 50, warmup: int = 5, sync=None) -> tuple[list[float], list[float]]:
    """Wall time waiting for each batch and inside each step, after `warmup` untimed steps.

    Pass sync=torch.cuda.synchronize: without it a step returns once its kernels are queued and the
    GPU time is booked against the next data wait.
    """
    waits: list[float] = []
    steps: list[float] = []
    iterator = iter(batches)
    for index in range(warmup + n):
        started = time.perf_counter()
        batch = next(iterator)
        fetched = time.perf_counter()
        step(batch)
        if sync is not None:
            sync()
        done = time.perf_counter()
        if index >= warmup:
            waits.append(fetched - started)
            steps.append(done - fetched)
    return waits, steps


def audit_speed(waits, steps, *, batch_size: int | None = None, planned_steps: int | None = None,
                price_per_hour: float | None = None, budget: float | None = None) -> list[dict]:
    waits, steps = as_array(waits), as_array(steps)
    if waits.size == 0 or waits.size != steps.size or (waits < 0).any() or (steps < 0).any():
        return [finding("FAIL", "BAD_TIMINGS", "speed", "need equal, non-empty, non-negative wait and step lists")]
    per_step = float(waits.mean() + steps.mean())
    share = float(waits.sum() / (waits.sum() + steps.sum())) if per_step > 0 else 0.0
    found = []
    rate = f"{batch_size / per_step:.1f} samples/s, " if batch_size else ""
    found.append(finding("INFO", "RATE", "speed", f"{rate}{per_step * 1000:.1f} ms/step, data wait {share:.0%}"))
    if share > WAIT_WARN:
        found.append(finding("FAIL" if share > WAIT_FAIL else "WARN", "DATA_BOUND", "speed",
                             f"{share:.0%} of each step waits for data; the GPU idles that share of the paid "
                             "time. Raise num_workers, pin_memory, cache or pre-decode the data, or move the "
                             "transform to the GPU before the long run"))
    if planned_steps:
        hours = planned_steps * per_step / 3600
        cost = f", about {hours * price_per_hour:.2f} at {price_per_hour:g}/h" if price_per_hour else ""
        found.append(finding("INFO", "PROJECTION", "speed", f"{planned_steps} steps take {hours:.2f} h{cost}"))
        if budget is not None and price_per_hour and hours * price_per_hour > budget:
            found.append(finding("FAIL", "OVER_BUDGET", "speed",
                                 f"projected {hours * price_per_hour:.2f} exceeds the budget {budget:g}; "
                                 "speed the step up or shrink the plan before launching"))
    return found


def report(found: list[dict], stream=None, as_json: bool = False) -> int:
    stream = stream or sys.stdout
    if as_json:
        print(json.dumps(found, indent=1), file=stream)
    else:
        for item in found:
            print(f"{item['level']:4} {item['code']} [{item['where']}] {item['message']}", file=stream)
    fails = sum(item["level"] == "FAIL" for item in found)
    warns = sum(item["level"] == "WARN" for item in found)
    if not as_json:
        print(f"PREFLIGHT {'FAIL' if fails else 'PASS'} fail={fails} warn={warns}", file=stream)
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    inputs = sub.add_parser("inputs", help="audit a saved raw batch (.npy, first axis = samples)")
    inputs.add_argument("--npy", type=Path, required=True)
    speed = sub.add_parser("speed", help="audit saved per-step timings")
    speed.add_argument("--timings", type=Path, required=True)
    speed.add_argument("--batch-size", type=int)
    speed.add_argument("--planned-steps", type=int)
    speed.add_argument("--price-per-hour", type=float)
    speed.add_argument("--budget", type=float)
    for each in (inputs, speed):
        each.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "inputs":
            found = audit_inputs(np.load(args.npy, allow_pickle=False), where=args.npy.name)
        else:
            data = json.loads(args.timings.read_text(encoding="utf-8"))
            found = audit_speed(data["wait_s"], data["step_s"], batch_size=args.batch_size,
                                planned_steps=args.planned_steps, price_per_hour=args.price_per_hour,
                                budget=args.budget)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"preflight_audit: {error}", file=sys.stderr)
        return 2
    return report(found, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
