---
name: remote-gpu-trainer
description: |
  Use when a user runs, debugs, verifies, or ships a DL experiment on a GPU they OWN or RENT (AutoDL,
  RunPod, vast.ai, Lambda, Paperspace, 恒源云/矩池云/Featurize/揽睿星舟, bare SSH, Slurm, K8s;
  single/multi-instance). Triggers (multilingual): 本地训练/local training, 远程 GPU 训练/租卡/GPU rental,
  spot 抢占/preemption, 断点续训/resumable, 防 SSH 断线/tmux 守护, 多实例 ablation,
  关机/销毁/stop-vs-terminate billing, checkpoint 磁盘满, CUDA OOM/显存不足, loss NaN/spike/不收敛,
  overfit 单 batch, FSDP/DeepSpeed/torchrun, 多卡 hang, dataloader/数据增广 bug;
  消融结果异常/ablation looks wrong, 复现/reproducibility, 数据泄漏/leakage/test-set tuning,
  mAP=0/全零指标, 输出恒定/model-ignores-input, train-good/val-collapse, 对比不公平/unfair baseline,
  单 seed/no error bars, loss 太好/too-good-to-be-true, 跨文档对账/cross-doc drift;
  交付产物/deliverable, 唯一真源/single source of truth, best ckpt 拉回, 结果可视化/论文图脚本,
  manifest/provenance, 一键复现/repro, EVIDENCE.json. NOT for multi-cloud price-shopping + auto
  spot-recovery (SkyPilot), BYOC dev environments (dstack), or zero-ops serverless inference (Modal).
license: MIT
compatibility: |
  Any Agent-Skills (SKILL.md)-compatible agent — Claude Code, Codex, Cursor, Trae, Gemini CLI, etc.
  RUN needs a shell (+ SSH or a platform CLI/API for the remote path); scripts are bash/python. VERIFY
  and DELIVER are platform-agnostic and need only a shell + the project's results. A few durable-monitoring
  recipes assume a host background-task runner + scheduler — map them to the running agent's equivalents
  (references/run-remote/monitoring_patterns.md §7).
---

# remote-gpu-trainer — the DL Experiment Lifecycle

## Overview

One skill for the whole arc of a DL experiment: **RUN → VERIFY → DELIVER.**

- **RUN** — get a long GPU job to start, survive, and finish, then get the result off the box. On a
  machine **you own** there is no meter; on a **rented** box the core insight is that **you are a
  short-term tenant on someone else's machine** — so the job is to *detach the work, make the result
  outlive the instance, and stop the meter safely*, not to provision a cluster. Platform-specific at the
  edges (one `profiles/<platform>.md` owns every path, proxy, billing verb, and spot rule), invariant at
  the core.
- **VERIFY** — *is this number a bug, a real effect, or noise?* A surprising result is a hypothesis, not
  a fact to report. Platform-agnostic.
- **DELIVER** — organize the result so every shipped number/figure/table is a *deterministic function of
  one immutable evidence layer*; provenance and cross-document consistency are locked by mechanism, not
  by a human remembering to update three documents. Platform-agnostic.

Two stances run through VERIFY and DELIVER: **user sovereignty** (the science — seed count, which samples,
whether an `aux` channel exists — is the user's call; the skill organizes and discloses a tradeoff *once*,
then stops nagging) and **audit → disclose, not enforce** (the skill is an honest auditor, not a gate
guard — an integrity issue must surface *with the conclusion it affects*, but the skill never blocks the
user from shipping). Mantra: **"disclose it, or don't claim it."**

## Route first

1. **RUN — own the box or rent it?**
   - **Local** (a workstation/laptop you own, no meter) → `references/run-local/` and `profiles/local.md`.
   - **Rented / remote** (any metered or shared box you don't own) → `references/run-remote/`, and pick
     your **`profiles/<platform>.md`** FIRST (it owns every path/verb/proxy the phases delegate to).
2. **Then ALWAYS** → **VERIFY** the result (`references/verifying/`) → **DELIVER** it
   (`references/delivering/`). These two are platform-agnostic; they run the same whether the job trained
   locally or on a rental. Skip nothing here just because the run succeeded — a green run is not a real
   number, and a real number is not yet a clean deliverable.

> Already debugging a model that won't converge / OOMs / hangs / NaNs, regardless of where it runs? Jump
> straight to **`references/training/`** (the 8-file debug layer), then come back to VERIFY before you report.

## Operating principles (the spine)

The load-bearing invariants. One line each; the full cross-platform set (10 invariants for the remote
lifecycle) is in **`references/run-remote/principles.md`** — read it before Phase 0 of a remote run.

- **Checkpoint-to-durable + idempotent resume is the universal spine.** File-checkpoint to the durable
  location + unconditional load-latest-on-startup is the *one* mechanism that survives an SSH drop, a
  Slurm walltime kill, a K8s reschedule, a spot preemption, a Colab disconnect. The detach primitive
  (tmux / sbatch / Job) is the swappable plug; this is the invariant.
- **Trust the artifact you loaded, not a log line that claims success.** "synced / saved / done" lies
  under a silently-failed write; a watcher's own state is also a claim — reconcile it against the real
  process / artifact / pixels / bytes.
- **Cheap checks before expensive compute.** A 1–2 batch CPU smoke (logger off) kills import/config/
  shape/scale bugs for ~free, before they bill GPU-hours.
- **Cost and destructive actions are the user's call.** Never auto-release/terminate, never delete durable
  files without confirmation; if cleanup can't free space, ask to expand the disk, don't silently shrink
  the experiment.
- **Audit → disclose, not enforce.** What is mandatory is *disclosure*, not the *fix*. An integrity
  finding (no disjoint val, leakage, test touched during selection, a number you can't re-derive) must
  ride *with* the conclusion — but the skill discloses, it does not block.

## RUN — local (a box you own)

No meter, no teardown clock — the risks move from *money* to *resource contention and your machine's
stability*. The discipline that does **not** relax: env hygiene, resource awareness, artifact/checkpoint
care, and "state the seed." Start at `profiles/local.md`, then the matching doc:

- **Env hygiene** — never train/install in conda `base` on a persistent box; the 4-step gate (enumerate →
  pick the project env → confirm `sys.executable` → run) → `references/run-local/env-hygiene.md`.
- **Launch & detach** — nohup/tmux, log + alive probe, don't foreground-block → `references/run-local/launch.md`.
- **Single-node multi-GPU** — `torchrun`/`accelerate` DDP env contract, the first-run rank/hang basics →
  `references/run-local/multi-gpu.md` (multi-*node* → `references/run-remote/multinode.md`).
- **Local OOM** — the fit-it ladder on hardware you can't rent bigger → `references/run-local/local-oom.md`.

## RUN — remote (a box you rent)

**Pick your profile FIRST** — it binds every concrete path/proxy/credential/billing verb/spot rule the
phases delegate to. Mental verb model (one API across platforms; the profile binds each verb to real
commands): `up` (rent+reach) → `push` (code/data on) → `run` (detached + checkpointing) → `watch`
(durable monitor) → `pull` (results off + verify) → `down` (stop the meter).

| You're on… | Profile | Meter-stop verb (the trap) |
|---|---|---|
| AutoDL (deepest, battle-tested) | `profiles/autodl.md` | 关机 stops meter, **keeps disk** (the AutoDL exception) |
| RunPod | `profiles/runpod.md` | **terminate** (stop still bills 2×; destroys volume disk) |
| vast.ai | `profiles/vastai.md` | **destroy** (stop bills disk forever) |
| Lambda | `profiles/lambda.md` | **terminate** (no stop state) |
| Paperspace | `profiles/paperspace.md` | **destroy + release IP + delete storage** |
| 恒源云 / 矩池云 / Featurize / 揽睿星舟 | `profiles/china.md` | per-platform (data disk often bills while stopped) |
| Bare SSH / Slurm / K8s / Colab | `profiles/generic-ssh.md` | **manual** (a forgotten box bills 24/7) |

**The 6-phase lifecycle** (full per-platform checklist → `references/run-remote/lifecycle_checklist.md`):
**0** env audit (`df -i` not just `df -h`, cgroup `memory.max`, checkpoint disk budget) · **1** SSH +
credentials (the prebuilt image **is** the env — don't `conda create` on a rental; secrets via stdin) ·
**2** wrapper + **CPU-smoke gate before renting** · **3** detached launch (probe, then hand back — never
a blocking `sleep`) · **4** durable monitoring (the four-layer architecture →
`references/run-remote/monitoring_patterns.md`; a session-bound watcher dies with the session) · **5**
aggregate + verify + teardown.

> **Iron Law — teardown gate:** NO `release` / `terminate` / `destroy` / file-delete until checkpoints are
> **pulled to local AND verified by load** (`scripts/verify_local.py`), and the user has explicitly
> approved the cost-affecting action. "It looked done in the log" is not evidence. On most platforms the
> meter-stopping action is **irreversible** (deletes the disk) — confirmation matters more, not less.

Other remote references: `ssh_transport.md` (rsync/scp resumable, secrets-via-stdin, CRLF) ·
`spot-resilience.md` (preemption grace, Young/Daly cadence, atomic-write resume) · `china-network.md`
(mirrors + `HF_ENDPOINT` + the `no_proxy` trap) · `parallel_ablation.md` (fan-out independence +
reconciliation) · `multinode.md` (NCCL/fabric, advanced) · `gotchas_universal.md` (the full U1–U43 catalog
with a grep index).

## When training itself breaks (the model, not the platform)

Once the box runs, training breaks in its own ways — **local or remote, the same debug layer**
(`references/training/`, 8 files; each entry symptom → root cause → fix with cited docs). Route by symptom:

- **OOM / won't fit** (CUDA-VRAM or host-RAM, OOM-at-a-step, the fit-it ladder) → `oom-memory.md`.
- **Multi-GPU launch / HANGS** (`torchrun`/`accelerate`/`deepspeed` env contract, DDP/FSDP/ZeRO) → `distributed-launch.md`.
- **NaN / Inf / loss spikes** (fp16/bf16/tf32, AMP/GradScaler, LLM divergence) → `precision-stability.md`.
- **Too slow** (GPU- vs data- vs comms-bound, dataloader knobs, `torch.compile` traps) → `throughput-profiling.md`.
- **Resume bugs** (full-state + sharded save/resume; epoch restart, reshuffle, scaler/EMA dropped) → `checkpoint-resume.md`.
- **Per-domain gotchas** (LLM, vision det/seg, diffusion, RL, multimodal/VLM) → `by-domain.md`.
- **Runs but won't learn** (overfit-one-batch, params-not-updating, LR/schedule, loss-function footguns, freezing) → `convergence-debugging.md`.
- **Dataloader correctness** (worker-RNG aug duplication, IterableDataset sharding, RGB-vs-BGR / ÷255 / `set_epoch`) → `data-pipeline.md`.

## VERIFY — is the number real?

Before you trust or report **any** metric, ablation delta, or "it works now": classify it **bug / effect /
noise**, hold a comparison to **exactly one** changed variable, and probe leakage / fair-comparison /
variance / metric-direction. A number you can't re-derive from the saved artifact is not a result yet.
Stance: **audit → disclose** — surface an integrity issue with the conclusion, never silently pass or hard-block.

- Full methodology (the 14-section probe ladder + the 6 invariants) → `references/verifying/methodology.md`.
- Constant / degenerate output, `real == shuffle`, model-ignores-input → `references/verifying/representation-collapse.md`.
- A green smoke that hides undertraining vs a real bug; loss-low-but-samples-bad → `references/verifying/smoke-hidden-failures.md`.

> **State the metric's direction when comparing** (PSNR/SSIM/mAP ↑ better; LPIPS/NMSE/loss ↓ better) —
> never assume. Tracker forensics / pruning duplicate runs → `scripts/wandb_forensics.py`.

## DELIVER — organize → single source → figures

Make the deliverable a deterministic function of one immutable, versioned evidence layer; lock provenance
and cross-document consistency by **mechanism**, not by hand. Eight principles, tiered
(`references/delivering/principles.md`):

- **CORE (wire from the first real number)** — **P1** evidence/presentation layers cleanly separated
  (zero hand-typed numbers in the presentation layer) · **P2** numbers **generated** from `results.json`,
  not transcribed (so a stale number is *physically impossible*) · **P3** content-addressed + append-only
  immutable runs (re-run mints a new `<run-id>`, never overwrites) · **P7** figure-chain traceability
  (`results.json → source_data.csv → figure` + `.provenance` sidecar) + the **pixel re-open gate** (a
  figure that *saved* is not a figure that's *correct*) · **P8** delivery = a **disclosure** gate, not a
  blocking one.
- **Advanced (flip on near submission — YAGNI applies to provenance too)** — **P4** data/split versioned
  + hash-pinned (leakage becomes machine-checkable) · **P5** one-command repro from a clean clone
  (`scripts/repro.sh.template`).

Mechanics: the on-disk tree → `references/delivering/data-architecture.md`; the two manifest schemas →
`references/delivering/evidence-manifest-schema.md`; the one-folder-per-figure convention + pixel gate →
`references/delivering/figures.md`; the per-number disclosure checklist → `references/delivering/delivery-gate.md`.

> **`EVIDENCE.json` is the project-level single source of truth** — a machine-readable claims↔evidence map
> (each claim ← the supporting exp-id / metric / figure + a paper anchor + the repo `file:line`).
> `scripts/reconcile.py` greps the whole repo against its authoritative values to catch cross-document drift;
> `scripts/manifest_scaffold.py` stamps the structure.

## Companion skills (all OPTIONAL — this skill is standalone)

Recommended separate installs that deepen RUN / VERIFY / DELIVER; **the skill needs none of them** and works
fully standalone. One-line-each list, what each adds, and the no-companion fallback →
**`references/companions.md`**. In short: figure drawing (nature-figure / publication-chart / scipilot-figure),
experiment verification (the `experiment-verifier` agent), parallel ablation
(`superpowers:dispatching-parallel-agents`), HF transport + hosted tracker
(`huggingface-skills:hf-cli` / `huggingface-trackio`).

## Getting better over time

The skill is static, but every run can teach it a gotcha — without corrupting it. Protocol →
`references/self-improvement.md`: only sediment a **root-caused, reproduced, generalizable** gotcha (a
one-off flake is a hypothesis, not a gotcha); route user/project-specific facts to the host's memory and
generalizable ones to a proposed catalog edit; **never silently rewrite a skill file** — draft the
`symptom → root cause → fix` and let the user approve. Platform facts carry a `verified <month>` stamp —
re-verify any teardown/billing fact against current docs before betting money or data
(`scripts/check_staleness.py`).

## Bundled resources

Load only what the current phase needs (the body sections above name the individual files).

- `references/run-local/` — **own-a-box**: env-hygiene · launch · multi-gpu · local-oom.
- `references/run-remote/` — **rented-box**: principles · lifecycle_checklist · monitoring_patterns · ssh_transport · spot-resilience · china-network · parallel_ablation · multinode · gotchas_universal (U1–U43).
- `references/training/` — the **DL-training debug layer** (8 files; local/remote-agnostic) — routed above.
- `references/verifying/` — **is-the-number-real**: methodology · representation-collapse · smoke-hidden-failures.
- `references/delivering/` — **deliverable**: principles · data-architecture (+`EVIDENCE.json`) · evidence-manifest-schema · figures · delivery-gate.
- `references/companions.md` (optional skills + fallbacks) · `references/self-improvement.md` (capture-a-gotcha loop).
- `profiles/<platform>.md` — per-platform substrate (7 rental profiles + `local.md`; `_schema.md` = the fields).
- `scripts/` — wrappers (`run_one`/`run_queue`), monitors (`mem_monitor`, `gpu_health`, `health_patrol.sh.template`),
  transfer (`download_loop`, `aggregate_to_fs`, `setup-china-mirrors`), `verify_local.py`, delivering
  (`manifest_scaffold.py`, `reconcile.py`, `repro.sh.template`), `wandb_forensics.py`, `check_staleness.py`.
- `examples/autodl_sweep/` — one runnable worked case · `evals/` — the regression harness.
