# Agentic navigation results (Tier 2)

Each row: a **fresh agent** was given the skill root and one scenario `prompt` from
[`cases.jsonl`](cases.jsonl), told to read `SKILL.md` first and then open files **only through the routing
SKILL.md documents** (no grep, no tree search), and graded on whether it reached a correct, specific answer
covering the scenario's `must_cover` points within ~2 hops of `SKILL.md`.

**How to weight this.** The runs were made by the maintainer, as Claude Opus 5 subagents dispatched from a
Claude Code session, one run per scenario, on the canonical prompt wording — author-run smoke evals, not a
neutral benchmark, not a multi-model sweep, and no paraphrased or adversarial prompts. They prove **routing and
retrieval inside the skill**, not the truth of platform facts on a live box (only the AutoDL profile is
hands-on; see the README's Verification status).

## Results — 2026-09-15 (current hub)

| Scenario | Verdict | Hops | Path observed (after SKILL.md) | Entries cited |
|---|---|---|---|---|
| convergence-frozen-resnet | **PASS** | 1 | Resource router → `references/training/convergence-debugging.md` | O1, O2, O17, O18, O6 (+O7, O12, O14, O22, O23) |
| data-worker-rng-dup | **PASS** | 1 | Resource router → `references/training/data-pipeline.md` | DP1 (+DP14) |
| oom-on-step-2 | **PASS** | 1 | Resource router → `references/training/oom-memory.md` | M17 (+M2, M18, M19, M12, M5, M8, M3; O11) |
| nccl-one-rank-hang | **PASS** | 1 | Resource router → `references/training/distributed-launch.md` | D19–D23, D9 (+M16, MN1–MN4) |
| diffusion-loss-low-samples-bad | **PASS** | 2 | Resource router → `references/training/by-domain.md` → `references/verifying/methodology.md` | DF1–DF8, C16; methodology §1, §6, §9 |
| nan-loss-spike-bf16 | **PASS** | 1 | Resource router → `references/training/precision-stability.md` | P8, P9, P11, P12, P13, P14, P15–P18 |
| resume-epoch-reset | **PASS** | 1 | Resource router → `references/training/checkpoint-resume.md` | C12, C14, C1, C3, C2, C9–C11, C13, C15, C16 |
| throughput-gpu-starved | **PASS** | 1 | Resource router → `references/training/throughput-profiling.md` | T1–T8, T18, T18b, T19 (+U8, U9, U21, U23, U24, U25, U40) |
| runpod-spot-resume-teardown | **PASS** | 2 | RUN step 1 → `profiles/runpod.md` §4/§5 → `references/run-remote/spot-resilience.md` | RP1–RP4, RP6–RP8, RP11, RP13, RP14; spot §1–§5 |
| vastai-teardown-billing | **PASS** | 1 | RUN step 1 → `profiles/vastai.md` §2/§5/§8 | VAST1, VAST2, VAST3, VAST8, VAST9, VAST12, VAST15 |
| autodl-inode-disk-full | **PASS** | 1 | RUN step 1 → `profiles/autodl.md` §2 | AD4, AD5 |
| china-hf-download-stall | **PASS** | 2 | RUN step 1 → `profiles/china.md` §3 → `references/run-remote/china-network.md` | china-network §1–§5, GS2 |
| lambda-stop-vs-terminate | **PASS** | 1 | RUN step 1 → `profiles/lambda.md` §2/§3/§5 | LAM1, LAM2, LAM3, LAM6, LAM10, LAM14 |
| autodl-first-contact-15day | **PASS** | 1 | RUN step 1 → `profiles/autodl.md` (surface block, §5) | AD-DANGER, AD1, AD2, AD3, AD4, AD6, AD7, AD9 |
| result-validity-report-gate | **PASS** | 1 | VERIFY → `references/verifying/methodology.md` | §1, §4, §5, §6, §7, §9, §11–§14; SKILL.md custody section |

**Summary: 15/15 scenarios routed correctly**, each to a correct, specific answer within ≤2 hops (12 in one
hop). The Tier-1 structural check (`run_evals.py`) runs the full
49-case `cases.jsonl` and is the authoritative regression line; the 34 cases without a row here are
structural-only guards unless their `agentic` field records a run.

## Known gaps

- Single run per scenario, one model family; no Haiku/Sonnet/Opus sweep and no paraphrased prompts.
- No live-platform validation of the facts the agent retrieves.
- An earlier 15/15 run (2026-06) was recorded against the pre-2026-08 hub layout and is superseded by the
  table above.
