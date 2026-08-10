---
name: "remote-gpu-trainer"
description: "Use when running, debugging, verifying, or delivering a deep-learning experiment on an owned or rented GPU, especially AutoDL or a remote SSH host; also use for Windows + Clash/Mihomo high-port SSH banner timeouts, fake-IP, or TUN routing interference. Covers launch, checkpoint/resume, detached monitoring, OOM/NaN/convergence/data-loader failures, multi-GPU hangs, ablations, result verification, pull/teardown safety, and canonical export closure. Routes durable replicas to mirror-research-artifacts. Triggers: owned/rented GPU, AutoDL, SSH, Windows Clash/Mihomo, banner timeout, fake-IP, TUN, train/debug/verify/pull/export, 远程GPU训练/租卡, 断点续训, 消融复现, checkpoint 拉回."
license: MIT
metadata:
  last-model-review: "2026-08-10 AutoDL canonical export and generic mirror handoff; preserves 2026-07 lifecycle review findings (day completed from aca1c467, which rewrote the description and added the Windows/Clash SSH gate — the bare 2026-08 form is unparseable to the staleness hook)"
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
- **Remote ownership boundary** — this skill is the **compute/control layer**: it binds inputs, runs and
  verifies compute, and closes one run into `export/<run-id>`. Long-term project organization belongs to
  `research-artifact-hygiene`; any durable/local/cloud mirror begins only at a validated export and belongs
  to the generic `mirror-research-artifacts` skill. Never mirror a mutable `active/` tree.
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
2. **Then ALWAYS** → **VERIFY** the result (`references/verifying/`). A green run is not a real number.
3. When publication synthesis is requested, optionally consult `references/delivering/` for
   **legacy/non-canonical publication synthesis guidance**. It never defines the artifact layout: canonical
   runs, hardware evidence, trust records, figures and tables belong to `research-artifact-hygiene`.

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
- **Execution permission is not task authority.** Sandbox / Full Access only controls whether a command
  can run. Keep operational authority and scientific promotion separate: once a bounded, non-overwriting
  delivery objective is authorized, same-scope diagnostics, verifier/schema version bumps, tests, hashes,
  and control-plane repairs do **not** require a fresh confirmation merely because they mint a new immutable
  ID. Re-ask for new billable compute, destructive/irreversible actions, science-protocol changes, metric
  promotion, publication, or any other material scope expansion. A standing unattended contract applies
  only after its own activation rule is satisfied.
- **Make the control plane cheap and the data plane rare.** Validate small schemas, identities, paths, and
  contract hashes before rereading multi-GB bundles. A synthetic fixture may test rejection behavior but
  may never invent the producer's positive schema; freeze a redacted real-shape fixture and prove its test
  is live. Recompute every large payload once per trust boundary—producer, independent remote acceptance,
  and local pull—not once per wrapper or verifier revision.
- **One-way run closure.** Mutable work stays under `active/<run-id>`; only a validated capsule may move
  from `export/.partial/<run-id>` to `export/<run-id>`, and failed closeouts move to `quarantine/`.
  AutoDL binds this exactly as
  `/root/autodl-tmp/<project>/{cache,active,export/.partial,export/<run-id>,quarantine}`. A closed export is
  fully isomorphic to canonical local `runs/<run-id>`: `run.json`, `config.yaml`, `train.csv`, `best.pth`,
  optional frozen `last.pth`, and `test/<test-id>/{metrics.json,results.parquet,vis/<condition-id>/<task-native-role>/<sample-id>.png}`.
  Every declared software test must include visualization coverage for all declared conditions × task-native
  roles × K fixed selected samples. Real capture/hardware results never enter this software capsule; close
  them separately as `export/hardware/<hardware-run-id>` (capture/decode/model-run bindings, no copied
  weights) or hand them to `research-artifact-hygiene`. A hardware test without machine-readable ground truth
  must declare that status and metric non-applicability; it keeps finite-forward rows and prediction/overlay
  visuals but never invents ground truth or GT-derived metrics. Caches and whole active trees never cross a
  mirror boundary. Layout and gates → `references/run-remote/artifact-layout.md`.
- **Before teardown, prove the evidence outlives the host.** Teardown is irreversible and *"I scp'd it
  back"* is just another log line. The gate is not "files copied" but **"every number I reported
  re-reads from the local copy"** — diff each claim against the pulled artifact, then write a
  provenance note *next to the data* (protocol, reference frame, caveats) so a later reader can
  retrace it without the chat log. Two traps: (1) what you did **not** pull is a decision, not an
  oversight — say which (checkpoints are usually re-derivable from config+seed *if* determinism is
  established; results are not); (2) **re-read the inventory, don't trust its prose** — a note saying
  "none of these are local" may mean *none was trained here*, not *none is stored here*; the two differ
  by everything when you are about to press destroy.
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

**Windows + Clash/Mihomo high-port SSH gate.** Use **OpenSSH direct first** with strict host-key
checking. A **Paramiko fallback** is allowed only after recorded `banner_timeout`, `fake_ip`, or
`tun_interference` evidence; it must use a DoH-selected address and Windows `IP_UNICAST_IF` on the
single socket handed to the SSH transport. Never treat authentication failure, host-key mismatch,
connection refusal, or an unexplained error as proxy evidence. Never mutate system routes, DNS,
proxy settings, or Clash/Mihomo configuration. Once fallback is authorized, you **must not report**
the host unreachable or a live refresh blocked before a bounded Paramiko single-socket attempt completes
or host identity fails closed. A **transport failure proves only transport unavailability**; it never
proves that a remote run is completed, live, failed or stalled. Full parameterized decision ladder and
offline planner → `references/run-remote/ssh_transport.md` §4A.

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
**0** env + storage-layout audit (`df -i` not just `df -h`, cgroup `memory.max`, checkpoint/inode budget) · **1** SSH +
credentials (the prebuilt image **is** the env — don't `conda create` on a rental; secrets via stdin) ·
**2** identity-bound inputs + isolated active run + **CPU-smoke gate before renting** · **3** detached launch (probe, then hand back — never
a blocking `sleep`) · **4** durable monitoring (the four-layer architecture →
`references/run-remote/monitoring_patterns.md`; a session-bound watcher dies with the session) · **5**
close `active → export`, verify/pull or hand the closed export to the generic mirror skill, then teardown.

> **Iron Law — teardown gate:** NO `release` / `terminate` / `destroy` / file-delete until the remote
> durable result root has an external immutable `PULL_MANIFEST.json` built by
> `scripts/aggregate_to_fs.sh` + `scripts/build_pull_manifest.py` from an explicit expected roster
> (never embedded in canonical `run.json`; the mirror workflow's custody manifest is an additional
> layer, not a replacement for this one),
> the pull matches that exact roster + every byte size + SHA-256, every checkpoint loads, and
> `scripts/verify_local.py` writes local `PULL_VERIFIED.json`; then the user must still explicitly
> approve the cost-affecting action. A directory count, a size heuristic, an old loadable checkpoint,
> or "it looked done in the log" is not evidence. On most platforms the
> meter-stopping action is **irreversible** (deletes the disk) — confirmation matters more, not less.

Other remote references: `ssh_transport.md` (rsync/scp resumable, secrets-via-stdin, CRLF) ·
`artifact-layout.md` (active/export/quarantine boundary, canonical capsule and atomic-close contract) ·
`spot-resilience.md` (preemption grace, Young/Daly cadence, atomic-write resume) · `china-network.md`
(mirrors + `HF_ENDPOINT` + the `no_proxy` trap) · `parallel_ablation.md` (fan-out independence +
reconciliation) · `multinode.md` (NCCL/fabric, advanced) · `production-matrix-acceptance.md`
(shared-disk multi-node patrol, producer→independent acceptance, control/science failure separation) ·
`gotchas_universal.md` (the full U1–U44 catalog with a grep index).

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
- For an atomic producer bundle, run `scripts/verify_artifact_bundle.py` on a different node; compare two
  independently produced acceptances with `scripts/compare_acceptance.py`. A hash match proves identity,
  a safe load proves checkpoint structure, and a fresh evaluator proves the metric—none substitutes for
  the others.

> **State the metric's direction when comparing** (PSNR/SSIM/mAP ↑ better; LPIPS/NMSE/loss ↓ better) —
> never assume. Tracker forensics / pruning duplicate runs → `scripts/wandb_forensics.py`.

## DELIVER — legacy/non-canonical publication synthesis guidance

On a remote rental, delivery ends at the validated closed `export/<run-id>` capsule. Do not turn the compute
host into the long-term project archive, figure workshop or mirror manager; hand canonical organization to
`research-artifact-hygiene` and replicas to `mirror-research-artifacts`.

The `references/delivering/` group is retained only for publication-synthesis principles such as
generated-not-transcribed reporting, claim reconciliation, disclosure and pixel re-open QA. **It is not an
artifact-layout authority.** Any directory/manifest example there that differs from
`research-artifact-hygiene` is legacy and non-canonical.

For synthesis, read evidence from canonical `runs/<run-id>/test/<test-id>/{metrics.json,results.parquet,vis/}`
or `hardware/runs/<hardware-run-id>/test/<test-id>/...`; never create a parallel `results/<exp-id>/runs/`
tree, checkpoint subdirectory, qualitative tree or selected symlink. Figures/tables use the canonical flat
workshops (`figure.json`/`table.json`, root-level source, `build.py`, `final.*`) rather than README portals,
nested output directories or provenance sidecars. The fixed selection roster remains the canonical
`run.json`-bound `_trust/selections` manifest; a publication montage may cite existing atomic PNGs but may
not redefine the run's visualization roster.

This skill owns one execution attempt, not project-wide closeout state. Route authorization gates, node
queues/heartbeats, legacy checkpoint acceptance, and the separate training/evaluation/pull/paper axes to
`supervise-research-closeout`; that controller must call this skill rather than duplicate its SSH or trainer logic.

Legacy synthesis navigation: `references/delivering/data-architecture.md` states the boundary and current
flat-workshop mapping; `principles.md`, `figures.md`, `delivery-gate.md` and
`completeness-reconciliation.md` provide advisory synthesis/QA checks only. None may override canonical
paths, manifests or retention rules.

## Companion skills (all OPTIONAL — this skill is standalone)

Recommended separate installs that deepen RUN / VERIFY / DELIVER; **the skill needs none of them** and works
fully standalone. One-line-each list, what each adds, and the no-companion fallback →
**`references/companions.md`**. In short: figure drawing (nature-figure),
data availability (`nature-data`), experiment verification (the `experiment-verifier` agent), parallel ablation
(`superpowers:dispatching-parallel-agents`), durable artifact mirroring
(`mirror-research-artifacts`), and — one layer above — an idea→conclusion
orchestrator (`auto-research-pipeline`: human gates + stage wiring; this skill executes, that one decides
when each stage fires and what a human signs).

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
- `references/run-remote/` — **rented-box**: principles · lifecycle_checklist · artifact-layout · monitoring_patterns · ssh_transport · spot-resilience · china-network · parallel_ablation · multinode · production-matrix-acceptance · gotchas_universal (U1–U44).
- `references/training/` — the **DL-training debug layer** (8 files; local/remote-agnostic) — routed above.
- `references/verifying/` — **is-the-number-real**: methodology · representation-collapse · smoke-hidden-failures.
- `references/delivering/` — **legacy/non-canonical publication synthesis guidance only**: advisory
  principles · canonical-boundary data-architecture · historical manifest/figure notes · delivery gate ·
  completeness reconciliation. `research-artifact-hygiene` owns every canonical path and schema.
- `references/companions.md` (optional skills + fallbacks) · `references/self-improvement.md` (capture-a-gotcha loop).
- `profiles/<platform>.md` — per-platform substrate (7 rental profiles + `local.md`; `_schema.md` = the fields).
- `scripts/` — wrappers (`run_one`/`run_queue`), monitors (`mem_monitor`, `gpu_health`, `health_patrol.sh.template`, `reap_vram_zombies.sh`),
  transfer (`download_loop`, `aggregate_to_fs`, `build_pull_manifest.py`, `setup-china-mirrors`), `verify_local.py`, delivering
  (`manifest_scaffold.py`, `reconcile.py`, `repro.sh.template`), atomic acceptance
  (`verify_artifact_bundle.py`, `compare_acceptance.py`), `wandb_forensics.py`, `check_staleness.py`.
- `examples/autodl_sweep/` — one runnable worked case · `evals/` — the regression harness.
