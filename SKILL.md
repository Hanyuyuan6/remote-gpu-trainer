---
name: "remote-gpu-trainer"
description: >-
  交付可验证的远程 GPU 运行状态、selection-best checkpoint 和拉回结果，适用于 AutoDL、vast.ai、RunPod、Lambda 或 Paperspace 的启动、调试、监控、续训、多开并行、停止及 OOM/NaN/全零指标排查；常见请求：训练卡住；释放实例会销毁机器及数据盘，绝不等同于关机。长期镜像与恢复交给 mirror-research-artifacts。
license: MIT
metadata:
  last-model-review: "2026-08-16 outcome-first and context-economy refactor; incident details moved out of the entrypoint, session/UI monitoring claims corrected, and assurance classified by consequence"
---

# Remote GPU Trainer

## Mission

Move one experiment through **RUN → VERIFY → DELIVER** with the least control work that safely advances the
user's outcome. This is the compute/control layer and owns one compute attempt. When the task spans several runs, nodes, independent
side-effect lanes, or paper-wide closeout, route scheduling and state projection to
`research-artifact-hygiene` (closeout ledger; 原 supervise-research-closeout 已并入); do not duplicate a second controller here.

## Start with the outcome, not a package

Before tools, write a compact internal decision:

1. desired result and current verified state;
2. exact next executable action;
3. consequence level below;
4. stop condition and where the result will live.

Do not preload incident catalogues, every platform profile, or a whole project SSoT. Pick one profile and one
phase reference. Keep large evidence out of model context: verify identity/schema, parse task-relevant fields,
and retain paths/hashes as an evidence index.

## Consequence-based assurance

Classify the next consequence, not the noun used in a handoff:

| Level | Examples | Required assurance |
|---|---|---|
| **L0 observe** | read-only probe, log/metadata parse, offline plan, same-scope pre-execution repair | no new gate or receipt; preserve host identity and observational behavior |
| **L1 reversible local** | fresh local staging, deterministic test, non-overwriting config generation | one relevant check and ordinary rollback |
| **L2 remote/costly non-destructive** | launch to a fresh path, pull, mirror, shutdown that preserves disk | one action-specific preflight, one compact receipt, one independent postcheck |
| **L3 irreversible/scientific authority** | release/terminate that destroys storage, deletion, overwrite, new paid scope, protocol change, metric or paper promotion | current explicit scoped authority plus an independent consequence check |

One consequence gets one assurance chain. Reuse accepted immutable evidence; never nest generic approval
packages or make a reviewer re-approve read-only diagnosis. Execution permission is not task authority, but an
already authorized bounded outcome carries through non-overwriting diagnosis, tests, parsing, hashes, and
same-scope repair. Re-ask only when cost, irreversibility, protocol, publication, or target scope actually changes.

**A gate may only fail closed when passing it would make a reported number wrong.**
Before writing or honouring one, name the claim it protects. Split leakage, checkpoint/config
mismatch, metric-definition drift, selection-on-test: fail closed. Missing paperwork, an absent
manifest, an unavailable validator, a receipt that cannot be regenerated on this machine: warn,
record the gap in the artifact, and PROCEED. A red gate that cannot make any number wrong is
costing GPU hours and calendar days to protect a filing cabinet. When a gate blocks and the
substantive evidence is already in hand by another route, say so in one line and continue on
that route — do not idle a paid node waiting for a human to adjudicate paperwork.

For a routine probe, launch, pull, or shutdown, use the maintained primitive. After one failed package and one
successor, stop version churn: repair the primitive, use a minimal operator-visible command, or report one
blocker. A protocol-preserving scientific source successor is not a renamed control package: keep frozen bytes
immutable, bind one minimal successor to a fresh run identity, and test the changed behavior through the real
consumer.

Detailed action economics, authority retirement, capacity semantics, and exact-chain regression live in
`references/run-remote/control-economy.md`. Load it only for remote mutation, custody, storage recovery, or
teardown—not for local debugging or metric interpretation.

## RUN

### Local machine

- Never train, infer, or install deep-learning packages in conda `base` on a persistent machine. Enumerate,
  select the project environment, confirm `sys.executable`, then run. Details:
  `references/run-local/env-hygiene.md`.
- Route launch, multi-GPU, and local OOM to the matching file under `references/run-local/`.

### Rented or shared machine

0. Browser-boot timeouts → `profiles/autodl.md` §Browser boot; local heavy ops not via ssh are
   machine-asked by a local guard — go remote; erroneous local downloads clean before Stop.
1. Read exactly one `profiles/<platform>.md`; it owns paths, proxy, billing, stop, destruction semantics and the instance-naming rule (rename every box `<project>-<purpose>-<date>` on creation).
2. Read `references/run-remote/principles.md`, then the current phase in
   `references/run-remote/lifecycle_checklist.md`.
3. Bind source/config/data identities and run a cheap CPU or one-batch smoke before paid compute.
4. Execute producer → serializer → actual parser/runner → target shell/OS. Mocks may suppress external side
   effects, never real parsing, paths, quoting, ancestry, time, or exit propagation.
5. Launch detached into a fresh `active/<run-id>` and checkpoint to durable storage with idempotent resume.
6. Close only validated work into `export/<run-id>`; quarantine failures. Never mirror mutable `active/`.
7. Prove every fail-closed input EXISTS before renting, not after booting. Enumerate what the runner refuses
   to start without (per-checkpoint resolved config, dataset bundle provenance, prepared manifest) and locate
   each on the mirror, locally, and on the node. 2026-08-18: a pilot booted, then found all three absent
   everywhere; rebuilding them was unpaid local work. A smoke test proves the box runs, not that the run has inputs.
8. Independent runs get their own box, in parallel -- a serial queue on one machine is a choice, and it has been
   corrected in three separate sessions. One writer per GPU still holds: parallel means more machines, never two
   writers on one. Say which runs are independent before asking whether to serialize.
9. The local machine's bandwidth is scarce and is not on the critical path. Move artifacts remote<->remote
   (mirror <-> node); never route a transfer through the laptop because that is the shell you happen to be typing in.

Storage pressure is an active recovery problem, not a permanent blocker. Treat percentage as warning and
`required bytes + margin` on the resolved device as the action threshold. Stop new writers, protect
active/unknown/checkpoint/result/paper-bearing paths, reclaim only proven-regenerable task-local scratch under an
exact allowlist, mirror valuable portable artifacts when appropriate, then remeasure. If the floor still fails,
report the exact shortfall, expansion target, restart requirement, and do not silently shrink the science.


## Monitor without burning model turns

The remote job must finish without an active chat. Put correctness on the box: detached process, checkpoint,
bounded self-completion chain, and explicit artifact/marker. A UI spinner is not a watcher, and a session-bound
background process is not restart-durable merely because its task chip remains visible.

- Keep exactly one watcher for one live run. It exits on a material event or a bounded timeout.
- Prefer on-box self-completion and an OS- or product-owned durable watcher whose restart behavior is verified.
- Wake the model only for a material delta, terminal state, blocker, new authority, or agreed sparse cadence.
- After restart, compaction, or transport loss, re-probe process/session/artifact truth before trusting UI state.
- Silence or a log string is historical evidence, not current liveness.

Read `references/run-remote/monitoring_patterns.md` before creating a monitor. It contains the durability truth
table, one-watcher lifecycle, bounded polling, and recovery procedure.

## Pull, shutdown, and release are different consequences

Before destructive teardown, require exact roster/bytes/SHA-256 and an actual restore/readback from the
canonical remote into an independent temporary consumer location. On that consumer, safely load the
checkpoint and recompute every reported metric from the full prediction population. The consumer may be
another remote node; a resident Mac `.pth` and local `PULL_VERIFIED.json` are not universal requirements.
Keep a thin logical record with URI, SHA-256, bytes, provider, mutability, verification date, and the bound
consumer evidence. Current explicit authority still determines the provider action.

- **Shutdown** may stop compute while preserving provider disks; it does not imply release.
- **Release/terminate/destroy** may delete storage or continue billing differently; verify current provider facts
  from its profile and obtain current L3 authority.
- A request to make data safe enough that later release would be harmless is a custody quality bar, not release
  permission. If the user says “shut down, do not release,” finish custody, run one idle/no-writer preflight,
  shut down once, verify offline, and preserve disks.
- A stale delegated `never release` is a provisional guard, not policy. Once its risk closes and a newer direct
  user decision authorizes the exact instance consequence, retire it instead of repairing an obsolete package.

Keep evidence deletion, cache cleanup, overwrite, shutdown, and provider release as separate decisions.

## VERIFY

A green run is not a trustworthy result. Before reporting a metric or ablation delta:

- state seed and determinism settings;
- change exactly one comparison variable;
- state metric direction (PSNR/SSIM/mAP ↑; LPIPS/NMSE/loss ↓);
- classify the observation as bug, effect, or noise;
- probe leakage, fairness, variance, and saved-artifact re-derivation.

The full scientific method is `references/verifying/methodology.md`; symptom-specific routes are
`representation-collapse.md` and `smoke-hidden-failures.md`. A matching hash proves identity, a safe load proves
checkpoint structure, and a fresh evaluator proves the metric—none substitutes for another. Audit and disclose
integrity limits with the conclusion; do not silently relabel controls as paper evidence.

## DELIVER

Remote delivery ends at a validated closed export or a validated thin logical run that points to canonical
remote checkpoint/results. Canonical long-term layout belongs to
`research-artifact-hygiene`; durable/local/cloud replicas belong to `mirror-research-artifacts`; paper synthesis
uses the relevant paper/figure skill. Keep software and hardware evidence separate. This skill never invents ground truth or
GT-derived metrics; no-GT hardware retains finite-forward rows and applicable prediction/overlay visuals with
metrics declared not applicable.

Lead the user-facing result with usable artifacts and verified status, then residuals and a compact evidence
index. Receipts, failed attempts, and internal control versions stay under the trust area, not in the product
structure.

## Resource router

- local execution: `references/run-local/`
- remote lifecycle, transport, storage, monitoring, layout: `references/run-remote/`
- OOM, hangs, NaN, throughput, convergence, data pipeline, checkpoint resume: `references/training/`
- scientific result verification: `references/verifying/`
- per-platform facts: `profiles/`
- one execution attempt: this skill; multi-run/multi-node closeout: `research-artifact-hygiene` (closeout ledger)
- canonical project organization: `research-artifact-hygiene`
- durable mirroring/restoration: `mirror-research-artifacts`

Load only the resource named by the current route. A generalizable, reproduced root cause may be proposed via
`references/self-improvement.md`; project facts belong in project memory/SSoT, not this global entrypoint.
