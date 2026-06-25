# Local workstation OOM — VRAM and host-RAM on a box you own, and what NOT to run locally

OOM on a personal/lab workstation has the **same mechanics** as on a rental (where the VRAM goes, reading the
trace, VRAM-vs-host-RAM), plus two local-only realities: you often share the box with a desktop/IDE eating
RAM, and there's a strong temptation to "just check it locally" on a machine far weaker than the training
target. This file covers the local specifics and the **rule about where heavy DL belongs**; the full fit-it
ladder (batch → grad-accum → bf16 → checkpointing → sharding → offload → LoRA) is
`references/training/oom-memory.md` — cross-reference it, don't restate it.

To jump: `grep -in '<keyword>' references/run-local/local-oom.md` (e.g. `host-ram`, `killed`, `workers`,
`shared`, `static`, `ladder`, `desktop`).

## Table of contents

- **Which OOM is it** — O1 VRAM OOM vs host-RAM `Killed` (the local confound: the desktop is also using RAM)
- **The local fit-it path** — O2 the ladder lives elsewhere · O3 close the other GPU consumers first
- **The rule** — O4 heavy DL goes on the GPU; the local dev box does **static checks only**
- **Pointers** — full OOM ladder + tools → ../training/oom-memory.md · multi-GPU sharding → multi-gpu.md

---

## Which OOM is it

### O1 — VRAM OOM is not host-RAM OOM (and locally, your desktop is also eating RAM)

**Symptom**: a run dies one of two ways — (a) a Python `torch.OutOfMemoryError: CUDA out of memory` traceback,
or (b) a bare `Killed` / **exit 137** with **no traceback**. They have **opposite** fixes, and on a local box
the host-RAM case is easy to misread because your browser, IDE, and desktop environment are *also* consuming
RAM the training process now has to share.

**Root cause**:
- **(a) VRAM exhaustion** — the model + activations don't fit the **GPU**. Fixed by the VRAM ladder
  (`references/training/oom-memory.md`).
- **(b) host-RAM exhaustion** — the OS killed the process for using too much **system RAM**, almost always
  `num_workers × a big in-RAM object` (a dataset materialized in each dataloader worker). On a shared
  workstation the headroom is smaller than you think because the GUI/IDE already hold several GB.

**Fix**: confirm **which** before changing anything — do not shrink the model to "fix" a host-RAM kill:
```bash
# VRAM: the Python traceback says "CUDA out of memory" → VRAM ladder (oom-memory.md)
# host-RAM: bare "Killed" / exit 137, no traceback → check the kernel log:
dmesg 2>/dev/null | grep -iE 'killed process|out of memory' | tail   # non-empty ⇒ host-RAM kill
free -h                                                              # how much system RAM is actually free
```
A non-empty `dmesg` OOM line ⇒ **host-RAM**: lower `num_workers`, stop materializing the dataset in every
worker (use lazy/memory-mapped loading), and **close the other RAM consumers** (O3) — *not* a smaller batch.
A CUDA traceback ⇒ **VRAM**: take the ladder (O2). The detailed mechanics of both, plus the
`memory_summary()` / snapshot tooling, are in `references/training/oom-memory.md` (M3, and the host-RAM
pointer to its U9 gotcha).

---

## The local fit-it path

### O2 — The fit-it ladder lives in oom-memory.md (don't re-derive it here)

**Symptom**: VRAM OOM on the local card and you're tempted to jump straight to the heaviest fix (sharding,
offload) or to ad-hoc `empty_cache()` calls.

**Root cause**: the fixes have a **cost order** — the cheapest ones don't touch the science, the expensive
ones do — and applying them out of order wastes effort or silently changes the experiment.

**Fix**: climb the cost-ordered ladder **top-down, stop when it fits** — the full rungs, exact flags, and
per-rung reasoning live in `references/training/oom-memory.md` M4; every "changes the science" rung (seq-len /
resolution change, LoRA capacity change) is a re-verify trigger (`references/verifying/methodology.md`). The
one local-only fact: on a single local card the **FSDP / ZeRO sharding** rung is unavailable, so failing to
fit through the single-card rungs (1–6 and 8) is the signal to move the job to a bigger / multi-GPU rental,
not to keep forcing the local box.

### O3 — Free the local GPU/RAM before blaming the model (close the other consumers)

**Symptom**: a run that fit yesterday OOMs today on the same config; `nvidia-smi` shows VRAM already partly
used before your run starts, or `free -h` shows little free RAM.

**Root cause**: a local box has **no scheduler and no isolation** — a previous crashed run can leave a
**zombie holding VRAM**, another notebook/process can be on the card, and the desktop GUI/browser/IDE eat
host RAM. The model didn't grow; the free headroom shrank.

**Fix**: reclaim the resources, then retry the unchanged config before touching the ladder:
```bash
nvidia-smi                              # who holds VRAM? a leftover python from a crashed run?
fuser -v /dev/nvidia*                   # find a holder nvidia-smi can't attribute (zombie → kill its PID)
free -h                                 # close browser/IDE if host RAM is the squeeze (O1 host-RAM case)
```
Kill a leftover `python` from a crashed previous run (it can pin GBs of VRAM the new run then can't get);
close heavy desktop apps if the failure is host-RAM. Only after the card/RAM is genuinely free do you
conclude the *model* doesn't fit and climb the O2 ladder. (Zombie-VRAM detail →
`references/run-remote/gotchas_universal.md` U11.)

---

## The rule

### O4 — Heavy DL goes on the GPU; the local dev box is for STATIC checks only

**Symptom**: running a real model construct / a `forward` pass / a sampling or generation loop **on the local
development machine** to "quickly check it works" — and it OOMs the workstation, freezes the desktop, or
takes forever, because the dev box is far weaker than the training target.

**Root cause**: a development laptop/desktop is sized for *editing code*, not for *executing DL compute*. A
model that needs a 40–80 GB datacenter card cannot instantiate, forward, or sample on an 8–16 GB consumer
GPU (or CPU) — attempting it doesn't "test" anything except whether the dev box falls over. Heavy DL
constructs (building the full model, running a forward/backward, sampling/decoding, a real eval pass) **must
execute on the GPU sized for them**; the local dev box should only do work that doesn't allocate the model.

**Fix** — split the work by where it belongs:

| On the **local dev box** (cheap, no model allocation) | On the **GPU target** (the workstation's real GPU, or a rental) |
|---|---|
| Static checks: lint, type-check, import-graph, a `python -c "import train"` smoke | Building the full model / `forward` / `backward` |
| Tiny CPU unit tests on shape/logic with a **toy** stub (1–2 layers, batch 1) | Any real **sampling / generation / decoding** loop |
| Config parsing, dataset *index* checks, dry-run argument validation | A real **eval / validation** pass on the dataset |
| Reading logs, plotting metrics already produced | Throughput / memory profiling of the actual model |

Run the **cheap CPU smoke locally** (does it import, parse args, build a toy 2-layer version, take one step on
a batch of 1?), then run the **heavy DL on the GPU** — your workstation's real GPU if it's big enough (launch
via `references/run-local/launch.md`), otherwise a rental (the `run-remote/` lifecycle). Static-checking heavy
DL on the wrong machine either OOMs the dev box or reproduces a bug that was only ever going to appear on the
real hardware — neither is a useful test. Once it runs on the right machine, the bug-vs-real-effect call is
`references/verifying/methodology.md`.

---

## Pointers — handled elsewhere, do not restate

- **The full VRAM + host-RAM fit-it ladder** with reasoning, exact flags, the per-step OOM cases (first
  backward, eval, longest batch, step-2 optimizer alloc), and the `memory_summary()` / snapshot-visualizer
  tooling → `references/training/oom-memory.md`.
- **Host-RAM cgroup-OOM** (`Killed` / exit 137, `num_workers × big tensor`) and **zombie-VRAM on an "empty"
  GPU** → `references/run-remote/gotchas_universal.md` U9 / U11.
- **Sharding a model that won't fit one card across multiple local GPUs** →
  `references/run-local/multi-gpu.md` (then `references/training/oom-memory.md` M9 for the FSDP/ZeRO stages).
- **Launching / detaching / the alive probe** for the local run → `references/run-local/launch.md`.
- **Is the post-fit number real** (precision swap, seq-len change, LoRA-vs-full) →
  `references/verifying/methodology.md`.
