# Single-NODE multi-GPU on one box — torchrun / accelerate DDP, the env contract, the rank/hang basics

One machine, several GPUs, one job spread across them over NVLink/PCIe. This file is the **local entry
point**: get the launcher and rank env right, share a working config, and recognize the two or three failures
that bite on the first multi-GPU run. **Single box only** — the moment a job spans ≥2 instances, the inter-node
NCCL/fabric transport takes over and that lives in `references/run-remote/multinode.md` (don't duplicate it
here). The **deep** launcher reference (FSDP/ZeRO wrapping, the full HANGS toolkit, tensor parallel) is
`references/training/distributed-launch.md` — this file points there rather than restating it.

To jump: `grep -in '<keyword>' references/run-local/multi-gpu.md` (e.g. `torchrun`, `standalone`,
`local_rank`, `nproc`, `accelerate`, `port`, `hang`, `barrier`).

## Table of contents

- **Decide** — G1 do you even need multi-GPU (and which kind)
- **Launch** — G2 torchrun `--standalone` env contract · G3 accelerate launch · G4 a common single-node config
- **The first-run gotchas** — G5 bare `python` uses one GPU · G6 LOCAL_RANK binds the device · G7 effective batch ×N (LR) · G8 the rank-conditional hang
- **Pointers** — multi-NODE → ../run-remote/multinode.md · deep launcher (FSDP/ZeRO/TP, all hangs) → ../training/distributed-launch.md · OOM/sharding-to-fit → ../training/oom-memory.md

---

## Decide

### G1 — Do you need multi-GPU, and which parallelism

**Symptom**: reaching for `torchrun` to "go faster" when the model fits one card, or reaching for plain DDP
when the model doesn't fit at all.

**Root cause**: "multi-GPU" is two different needs — **more throughput** for a model that fits, vs **more
memory** for a model that doesn't. They use different strategies.

**Fix** — one-line decision (full version in `references/training/distributed-launch.md` D7):

| Situation | Use | Why |
|---|---|---|
| Model **fits** one GPU, want throughput | **DDP** via `torchrun` (or `accelerate`) | each GPU holds a full replica; simplest, fastest |
| Model **does not fit** one GPU (params+optim+grads ≈ 18 B/param) | **FSDP** / **DeepSpeed ZeRO** | shard state across cards → `../training/oom-memory.md` M9 |
| HF Trainer / ecosystem | **Accelerate** as launcher | flip a config field to pick DDP/FSDP/ZeRO |

Most single-box jobs are the first row (DDP). The sharded rows (FSDP/ZeRO wrapping policy, state-dict types,
offload) are owned by `references/training/distributed-launch.md` and `references/training/oom-memory.md` —
go there, don't re-derive them here.

---

## Launch

### G2 — `torchrun --standalone`: the single-node env contract

**Symptom**: a raw `python train.py` on a 4-GPU box uses **one** GPU; or `init_process_group` hangs forever
because `MASTER_ADDR`/`RANK` were never set.

**Root cause**: `torch.distributed` reads its topology from **environment variables**, not from the GPU
count. A bare `python` sets none of them, so the process group never forms.

**Fix**: launch through `torchrun --standalone`, which self-hosts the rendezvous on localhost and sets the
full per-process contract — no address/port to manage on one box:
```bash
torchrun --standalone --nnodes=1 --nproc-per-node=4 train.py --your-args
#         ^ self-hosted rendezvous   ^ one node      ^ one process per GPU
```
The script reads the env vars torchrun injects and binds the device by `LOCAL_RANK` (G6):

| Var | Meaning (single node) |
|---|---|
| `RANK` | global rank `0..WORLD_SIZE-1` — selects the **data shard** |
| `LOCAL_RANK` | rank within this node — bind to the **physical GPU** (`cuda:LOCAL_RANK`), never `RANK` (G6) |
| `WORLD_SIZE` | total workers = `nproc_per_node` (single node) |
| `MASTER_ADDR`/`MASTER_PORT` | localhost + a port for the c10d store (`--standalone` handles it) |

In the script: `lr = int(os.environ["LOCAL_RANK"]); torch.cuda.set_device(lr);
dist.init_process_group("nccl")` before allocating any CUDA tensor. Two co-located jobs on one box need
**disjoint GPUs and distinct ports** (`CUDA_VISIBLE_DEVICES=0,1 … --master-port=29500` vs
`CUDA_VISIBLE_DEVICES=2,3 … --master-port=29600`) — full detail in `../training/distributed-launch.md` D4.

### G3 — HF Accelerate: `accelerate launch` reads a config, not torchrun flags

**Symptom**: `accelerate launch train.py` runs single-GPU despite N cards — no config exists, or it defaulted
to one process.

**Root cause**: Accelerate wraps the same env contract (G2) but sources it from a config file
(`accelerate config` writes `default_config.yaml`) or from CLI flags; with neither it assumes one process.

**Fix**: pass the multi-GPU flags explicitly, or a checked-in YAML (reproducible, diffable):
```bash
accelerate launch --multi_gpu --num_processes=4 --mixed_precision=bf16 train.py
# or a committed config (preferred — switching DDP↔FSDP↔ZeRO becomes a one-field edit):
accelerate launch --config_file configs/acc_ddp.yaml train.py
```
The training script is unchanged across DDP/FSDP/DeepSpeed — only the config differs. FSDP/ZeRO config keys
(wrapping policy, sharding strategy) → `references/training/distributed-launch.md` D5, D12–D17.

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

---

## The first-run gotchas (single-node)

These are the handful that bite on the first multi-GPU launch. The exhaustive list (DDP `find_unused_parameters`,
uneven-inputs Join, SyncBN, the full desync-debug toolkit and Flight Recorder, FSDP/ZeRO/TP) is
`references/training/distributed-launch.md` — go there for anything past these four.

### G5 — A bare `python train.py` uses only one GPU (covered by G2)

The #1 surprise: launching with `python` not `torchrun`/`accelerate` runs **one process on one card**, no
matter how many GPUs exist — because nothing set the rank env. Fix = launch through a launcher (G2/G3).

### G6 — Bind the device by `LOCAL_RANK`, never `RANK`

**Symptom**: on one node it *looks* fine, but every process can pile onto `cuda:0` (and OOM) if the script
indexed the device by the wrong variable — a bug that only fully bites on multi-node but is wrong here too.

**Root cause**: `torch.cuda.set_device(RANK)` happens to work when `RANK==LOCAL_RANK` (single node), masking
the bug; `RANK` selects the *data shard*, `LOCAL_RANK` selects the *physical GPU*.

**Fix**: **always** `torch.cuda.set_device(int(os.environ["LOCAL_RANK"]))` before allocating CUDA tensors.
Writing it correctly now means the same script scales to multi-node unchanged
(`references/training/distributed-launch.md` D3).

### G7 — N GPUs silently make the effective batch N× larger (and the LR is now wrong)

**Symptom**: moving 1→4 GPUs makes training diverge or plateau; the loss curve is shaped differently under
"the same config."

**Root cause**: DDP keeps **per-GPU** batch size, so **effective batch = per_gpu_batch × world_size**. An LR
tuned for the 1-GPU batch is mismatched (usually under-scaled) at 4×. This is the most common silent
multi-GPU regression.

**Fix**: scale LR with the effective batch (linear-scaling rule + warmup as a baseline), and **record**
`world_size`, per-GPU batch, and effective batch with the run. **This changes the science** — a 1-GPU
baseline vs a 4-GPU run with unscaled LR is not a clean datapoint; declare it and re-check
(`references/verifying/methodology.md`). Effective-batch bookkeeping detail →
`references/training/distributed-launch.md` D11.

### G8 — The job hangs at validation / logging / checkpoint (rank-conditional collective)

**Symptom**: multi-GPU training freezes reproducibly at the **same** spot — often the first eval, a log step,
or a checkpoint save — with no traceback, GPUs pinned at 100% util but doing no real work.

**Root cause**: a distributed hang has no traceback — every rank waits in a collective for a peer that never
calls it. The classic single-node cause is a collective (a `dist.barrier()`, an `all_reduce` metric, SyncBN,
or "save/log on rank 0 only" whose path triggers a collective) placed **inside an `if rank == 0:` branch**:
rank 0 calls it, the others skip it, everyone deadlocks.

**Fix**: collectives run on **all ranks unconditionally** — gate only the *side effect*, not the collective.
Compute the metric's `all_reduce` on every rank, then `if rank == 0: log(value)`; a `barrier()` must be
reached by every rank or none; write the checkpoint from rank 0 to a temp path + atomic-rename, with a
`dist.barrier()` on **all** ranks before others read it. Audit every `if rank/local_rank == 0` block for a
hidden collective. The full hang toolkit (`TORCH_DISTRIBUTED_DEBUG=DETAIL`, `NCCL_DEBUG=INFO`,
`TORCH_NCCL_ASYNC_ERROR_HANDLING=1`, Flight Recorder, and the one-rank-diverged case) lives in
`references/training/distributed-launch.md` D19–D23.

---

## Pointers — handled elsewhere, do not restate

- **Multi-NODE (≥2 instances)** — inter-node NCCL NIC pinning, `nvidia-fabricmanager`, the 1800 s timeout
  masking a dead rank, MTU/jumbo frames, elastic restart restoring the *group* not the *state* →
  `references/run-remote/multinode.md` (**REQUIRED** the moment a job spans two boxes; this file ends where
  the wire between boxes begins).
- **Deep launcher reference** — DDP `find_unused_parameters`/Join/SyncBN, FSDP wrapping policy + sharding
  strategy + state-dict types, DeepSpeed ZeRO knobs, tensor/2-D parallel, and the complete HANGS debugging
  toolkit → `references/training/distributed-launch.md`.
- **Sharding to fit a model that OOMs** (the FSDP/ZeRO ladder in cost order, activation checkpointing,
  offload, LoRA/QLoRA) → `references/training/oom-memory.md`.
- **Detaching the multi-GPU launch from the terminal** (tmux/nohup, alive probe) →
  `references/run-local/launch.md`.
- **Is the multi-GPU number real** (LR rescaled with world size, shuffle staleness via `set_epoch`,
  SyncBN necessity) → `references/verifying/methodology.md`.
