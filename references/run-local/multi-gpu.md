# Single-NODE multi-GPU on one box — torchrun / accelerate DDP, the env contract, the rank/hang basics

One machine, several GPUs, one job over NVLink/PCIe: this file holds the committed single-node DDP config
and routes every launcher fact to `references/training/distributed-launch.md`, which owns them.

## Decide & launch

### G1 — Do you need multi-GPU, and which parallelism
DDP when the model fits and you only want throughput, FSDP/DeepSpeed ZeRO when it does not fit, Accelerate as
the launcher in the HF ecosystem → `references/training/distributed-launch.md` D7; the sharding stages
themselves → `references/training/oom-memory.md` M9.

### G2 — `torchrun --standalone`: the single-node env contract
`RANK` / `LOCAL_RANK` / `WORLD_SIZE` / `MASTER_ADDR`+`MASTER_PORT`, `--standalone` vs a shared rendezvous, and
the disjoint-GPUs-and-distinct-ports rule for two co-located jobs →
`references/training/distributed-launch.md` D1, D2, D4.

### G3 — HF Accelerate: `accelerate launch` reads a config, not torchrun flags
→ `references/training/distributed-launch.md` D5; FSDP/ZeRO config keys → D12–D17.

### G4 — A working single-node DDP config (the common case)

For the fits-on-one-card throughput case, a minimal Accelerate YAML:
```yaml
# configs/acc_ddp.yaml — single node, multi-GPU DDP
compute_environment: LOCAL_MACHINE
distributed_type: MULTI_GPU        # plain DDP (use FSDP for sharding — see distributed-launch.md)
num_machines: 1
num_processes: 4                   # = number of local GPUs
mixed_precision: bf16              # prefer bf16 on Ampere+ (no loss-scaler; fewer NaNs)
main_process_port: 29500           # bump if a second job co-locates on the box
```
Equivalent torchrun: `torchrun --standalone --nnodes=1 --nproc-per-node=4 train.py`. Set `num_processes`
(and `--nproc-per-node`) to the count of GPUs you actually pinned for this job, not the box total, if you're
sharing the machine.

## The first-run gotchas (single-node)

### G5 — A bare `python train.py` uses only one GPU
Nothing set the rank env, so one process runs on one card → `references/training/distributed-launch.md` D1.

### G6 — Bind the device by `LOCAL_RANK`, never `RANK`
→ `references/training/distributed-launch.md` D3.

### G7 — N GPUs silently make the effective batch N× larger (and the LR is now wrong)
→ `references/training/distributed-launch.md` D11. It changes the science: declare it and re-check
(`references/verifying/methodology.md`).

### G8 — The job hangs at validation / logging / checkpoint (rank-conditional collective)
→ `references/training/distributed-launch.md` D21, and the full hang toolkit
(`TORCH_DISTRIBUTED_DEBUG=DETAIL`, `NCCL_DEBUG=INFO`, `TORCH_NCCL_ASYNC_ERROR_HANDLING=1`, Flight Recorder,
the one-rank-diverged case) → D19–D23.

## Pointers — handled elsewhere

- **Multi-NODE (≥2 instances)** — inter-node NCCL NIC pinning, `nvidia-fabricmanager`, the 1800 s timeout
  masking a dead rank, MTU/jumbo frames, elastic restart restoring the *group* not the *state* →
  `references/run-remote/multinode.md` (**REQUIRED** the moment a job spans two boxes; this file ends where
  the wire between boxes begins).
- **Sharding to fit a model that OOMs** (the FSDP/ZeRO ladder in cost order, activation checkpointing,
  offload, LoRA/QLoRA) → `references/training/oom-memory.md`.
- **Detaching the multi-GPU launch from the terminal** (tmux/nohup, alive probe) →
  `references/run-local/launch.md`.
- **Is the multi-GPU number real** (LR rescaled with world size, shuffle staleness via `set_epoch`,
  SyncBN necessity) → `references/verifying/methodology.md`.
