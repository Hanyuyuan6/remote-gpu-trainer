---
platform: local              # YOUR machine — a workstation/desktop/laptop you OWN, not a rental
kind: workstation            # workstation | laptop — non-rented, persistent, no meter
meter_stop_verb: n/a         # NOT rented: there is no billing meter to stop (contrast every other profile)
meter_stop_irreversible: n/a # nothing to tear down; the box is yours and persists
detach_primitive: tmux       # tmux | nohup (bare) — sever the run from the terminal (run-local/launch.md)
spot_available: false        # you own it: no preemption, no eviction, no spot bid
spot_grace: n/a              # the only "interruption" is a reboot/sleep/crash you control
shared_fs: false             # one (or a few) local disk(s) you own; no cross-instance network FS
inode_cap: host-dependent    # measure with df -i on your own filesystem; ext4/xfs/ntfs differ
free_egress: true            # your own internet; no platform egress charge (your ISP cap still applies)
china_mirror_needed: host-dependent  # only if YOUR connection sits behind the GFW
host_driver_cuda_max: host-dependent # your installed driver — nvidia-smi top-right
local_nvme: host-dependent   # whatever disk you bought
---

# Profile: LOCAL — your own workstation / desktop / laptop (NON-rented)

One-line purpose: the profile for training on a machine **you own and keep**. It is the mirror image of every
other profile here: **there is no meter, no teardown clock, no eviction** — so the cost-and-survival sections
that dominate the rental profiles mostly *collapse to n/a*. What does **not** relax is the rest of the
discipline: the same env hygiene, the same resource awareness, the same artifact/checkpoint care, and the same
"state the seed" rule a rental demands.

> **Surface to the user up front:** ✅ No danger clock here — a forgotten local run costs **electricity, not a
> 24/7 cloud invoice**, and nothing destroys your disk. The flip side: **you are the entire substrate** — your
> own scheduler, janitor, and the box that competes with your desktop/IDE for RAM and VRAM. The risks move
> from *money* to *resource contention and your own machine's stability*.

Read this whole file before the first local run, then jump to the matching `references/run-local/` doc for the
mechanics. **Universal gotchas are NOT restated here** — see `references/run-remote/gotchas_universal.md`.

**Table of contents** (`grep -in '<keyword>' profiles/local.md` to jump):
- 8-field schema for a machine you own (sections 1–8), with the rental-only sections marked **n/a**

The one load-bearing idea: **the env/resource/artifact discipline is identical to a rental; only the
billing-and-teardown machinery is absent.** Don't let "it's my own box" erode the env hygiene or the seed
hygiene — those failures cost the same whether or not a meter is running.

---

## 1. LAUNCH

- **Entry point:** a local shell — no SSH, no console, no platform API. You are already on the box.
- **Env contract — the one rule that does NOT relax:** on a machine you keep, **never run a train/install in
  conda `base`.** Enumerate (`conda env list`), pick the project env (or ask), and confirm the interpreter
  (`python -c "import sys; print(sys.executable)"`) is under `…/envs/<proj>/` before the real command. Full
  rules, fully inlined → **REQUIRED:** `references/run-local/env-hygiene.md`. This is the opposite of a rental,
  where the prebuilt `base`/image *is* the env — here `base` must stay pristine.
- **Launch + detach:** confirm the GPU is visible, pin the card, then detach from the terminal so closing the
  shell / sleeping the laptop doesn't kill the run → `references/run-local/launch.md`:
  ```bash
  python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"   # gate
  tmux new -s train   # or: nohup env CUDA_VISIBLE_DEVICES=0 python -u train.py </dev/null >run.log 2>&1 &
  ```
- **Multi-GPU on the box:** `torchrun --standalone --nnodes=1 --nproc-per-node=<#gpus>` →
  `references/run-local/multi-gpu.md`. Multiple instances? That's `run-remote/multinode.md`, not this profile.
- **State the seed/determinism in the run itself** — no platform does it for you (**REQUIRED:**
  `references/verifying/methodology.md`).

→ **verify:** the launch interpreter prints `True` for CUDA and the env path is under your project env.

## 2. STORAGE MODEL  *(survival matrix — but nothing reclaims your disk)*

You own the disk(s); there is **no STOP/DESTROY a platform performs** and no automatic reclamation. The
survival matrix is therefore trivial — everything "survives" until *you* delete it — but the **resource**
caution is real: *measure, never assume* your free space and inodes with `df -h && df -i <mount>` on your own
filesystem (ext4/xfs/ntfs/apfs caps differ; do not assume any rental constant).

| Tier | Path | Survives a reboot? | Survives until... | Cap |
|---|---|---|---|---|
| Local disk(s) you own | `/`, `~`, any mounted drive | **yes** | you delete it / the drive fails | host-dependent — `df -h`/`df -i` |
| External / NAS (if you use one) | mount point | yes | the drive/share is detached | host-dependent |

The local subtlety: there is **no "pull results to local before teardown" step** — the results are *already*
local; that whole rental ritual disappears. What remains is ordinary disk hygiene: a training run fills inodes
before bytes, and the byte-hog often hides in `~/.cache/huggingface` — prune by value (`du -sh
~/.cache/huggingface/hub/models--* | sort -rh`), keep tiny eval JSONs, drop large periodic checkpoints. Back
up anything irreplaceable yourself: a disk you own has **no platform snapshot** to fall back on.

## 3. NETWORK

- **Egress:** your own internet — no platform egress charge (your ISP's cap/speed still bound you). Download
  weights/datasets directly; there is no fatter "on-box pipe" to prefer because the box *is* local.
- **China mirror:** only if **your** connection sits behind the GFW — then `export
  HF_ENDPOINT=https://hf-mirror.com` (detail: `references/run-remote/china-network.md`); otherwise irrelevant.
- **Port exposure:** services are already on localhost — TensorBoard is just `tensorboard --logdir runs/`
  then open `http://localhost:6006`. No SSH tunnel, no console port-forward.

## 4. SPOT / INTERRUPTION + RESUME  *(no eviction — but reboots/crashes still happen)*

There is **no spot model, no preemption, no eviction** — you own the box, so nothing reclaims it mid-run. The
only interruptions are ones you control or your machine causes: a **reboot** (OS update, you restart it), a
**laptop sleep/shutdown**, a **crash/power loss**, or your own `Ctrl-C`.

Resume discipline still applies — checkpoint full state (model + optimizer + scheduler + epoch/step + RNG +
dataloader position) atomically (`tmp`→`fsync`→`os.rename`) on a periodic timer, and load-latest
unconditionally on startup so the **same launch command** resumes. `tmux`/`nohup` survive an SSH-style
disconnect and a laptop **sleep**, but **not** a host **reboot** — after a reboot, relaunch and let idempotent
resume continue. Cadence formula + atomic-write pattern → `references/run-remote/spot-resilience.md` (the
mechanics are platform-agnostic; only the *trigger* differs — your reboot instead of a spot eviction).

## 5. TEARDOWN / BILLING  *(n/a — there is no meter)*

**Not applicable: you are not renting.** This is the section that dominates every other profile and **vanishes
here.** There is no `stop` vs `terminate` vs `destroy`, no irreversible disk-wipe-on-teardown, no per-hour
cost trap, no "forgotten box bills 24/7." The only standing cost of leaving a run going is **electricity** and
your machine's wear — real, but not a billing meter you must race.

What replaces the teardown ritual is mundane cleanup on **your** terms: when a run is done, free the GPU (kill
leftover `python` so a zombie doesn't pin VRAM for the next run → `references/run-local/local-oom.md` O3) and
prune scratch checkpoints. There is no Iron Law "verify-before-teardown" here because **nothing is being torn
down** — the artifacts are already on your disk. (If you ever rent a box to offload a job, that *run* follows
the matching rental profile's teardown law, not this one.)

## 6. DAEMON TOOL

- **`tmux`** is the detach primitive: `tmux new -s train` → run inside → `Ctrl-b d` to detach; `tmux attach -t
  train` to reattach; `tmux ls` to reconcile a watcher against the real session. Survives a terminal close and
  a laptop **sleep**; does **not** survive a host **reboot** — relaunch after one.
- **Fallback** when tmux isn't installed: `nohup <cmd> </dev/null >run.log 2>&1 &` then `disown` — always
  redirect stdin from `/dev/null` so a backgrounded job never blocks/stops reading the terminal.
- **No native queue — you are the scheduler.** A local box has no job manager: nothing stops two runs sharing
  one GPU and both crawling/OOM-ing. Serialize with a resumable queue, or pin each run to a distinct card with
  `CUDA_VISIBLE_DEVICES=<n>`; check `nvidia-smi` for an existing holder before every launch. Detach + alive
  probe + "don't foreground-wait" → `references/run-local/launch.md`.

## 7. TOP GOTCHAS  (platform-pinned; universal → `references/run-remote/gotchas_universal.md`)

- **LOC1 — Training in conda `base` rots the whole machine.** Symptom: a `pip install` for one project
  silently downgrades a library another project needs, or conda itself gets wedged. → Root cause: `base` is the
  env conda runs from; packages added to it are shared globally with no isolation and no clean rollback — and
  on a machine you **keep**, that damage is permanent (unlike a throwaway rental where `base` is the right
  place to run). → Fix: one named env per project; pass the `references/run-local/env-hygiene.md` gate
  (enumerate → pick → confirm `sys.executable`) before any install/train.
- **LOC2 — Heavy DL static-checked on the dev box OOMs the workstation.** Symptom: instantiating the full
  model / running a `forward` / sampling loop locally to "quickly check it" freezes the desktop or OOMs. →
  Root cause: a dev laptop/desktop is sized for *editing code*, not *executing DL compute*; a model needing a
  40–80 GB card cannot forward on an 8–16 GB consumer GPU. → Fix: **heavy DL constructs/forwards/sampling go on
  the GPU; the local dev box does static checks only** (lint, type-check, a toy 2-layer CPU smoke). Full rule +
  the split table → `references/run-local/local-oom.md` O4.
- **LOC3 — A run that fit yesterday OOMs today (the desktop ate the headroom).** Symptom: same config, now
  VRAM- or host-RAM-OOMs. → Root cause: no isolation — a leftover zombie `python` pins VRAM, or the
  browser/IDE/desktop GUI now hold the system RAM the run needs. → Fix: reclaim first (`nvidia-smi` / `fuser -v
  /dev/nvidia*` to find a VRAM holder; `free -h` and close apps for host-RAM) before blaming the model →
  `references/run-local/local-oom.md` O1/O3.
- **LOC4 — A reboot / laptop shutdown silently orphans the run (`tmux` doesn't survive it).** Symptom: a
  detached job is gone after an OS update reboot or a laptop shutdown; idle GPU, no session. → Root cause:
  `tmux`/`nohup` survive an SSH drop and a *sleep* but **not** a host reboot — every session dies. → Fix: make
  resume idempotent (§4) so the *same* launch command continues from the last checkpoint; a laptop that sleeps
  is fine (tmux survives sleep), a shutdown/reboot needs the relaunch.
- **LOC5 — A second run silently halves throughput by oversubscribing the GPU.** Symptom: two runs on the
  "same idle card" both crawl, or the second OOMs on a card that looked free. → Root cause: no scheduler —
  nothing prevents two processes sharing one GPU; they contend for VRAM and SM time. → Fix: you *are* the
  scheduler — serialize, or pin each run to a distinct card with `CUDA_VISIBLE_DEVICES`; check `nvidia-smi` for
  a holder before launching (zombie holders → U11).
- **LOC6 — CRLF breaks `.sh` if you author on Windows.** Symptom: `bash: $'\r': command not found` running a
  script you edited in a Windows editor (relevant since this profile is "your own box," often Windows). → Root
  cause: Windows editors write CRLF line endings. → Fix: `.gitattributes` with `*.sh text eol=lf`; unblock an
  affected file with `sed -i 's/\r$//' run.sh`.

### Local debugging (your own box — no console needed, you're on it)

- **Is the run alive or orphaned?** `tmux ls; pgrep -af <train-script> | head` — empty after a vanished log ⇒
  reboot/shutdown killed the session (LOC4).
- **Why did it die?** `dmesg 2>/dev/null | grep -iE 'killed process|out of memory|Xid' | tail; uptime` — OOM
  line ⇒ host-RAM kill (`references/run-local/local-oom.md` O1); clean dmesg + low uptime ⇒ a reboot (LOC4).
- **GPU health + who holds it:** `nvidia-smi`; a holder it can't attribute ⇒ `fuser -v /dev/nvidia*` (zombie,
  U11). Read SM clock/power over raw `GPU-Util` (a liar, U21).
- **Disk before it bites:** `df -h <mount>; df -i <mount>` — inodes hit 100% before bytes (U7); the byte-hog
  often hides in `~/.cache/huggingface`.

## 8. SCRIPT OVERRIDES

Values to parameterize the `scripts/` templates for your own box:

```
DATA_DIR=$HOME/proj         (working dir / data on your local disk)
DURABLE_DIR=$HOME/proj      (durable = your own disk; it IS local — no "pull to local" step, but back up irreplaceables yourself)
PROXY_HOOK=                 (none; set HF_ENDPOINT=https://hf-mirror.com only if YOUR connection is behind the GFW)
CRED_FILE=~/.netrc          (on your local disk; reference tokens by env-var name, never inline a key)
SCRATCH=*.latest.pth and periodic checkpoints  (prune on success; keep best + tiny eval JSONs)
HF_HOME=$HOME/proj/.hf      (redirect off ~/.cache so the model cache lands on the data disk you chose)
DETACH=tmux                 (the swappable plug — tmux or nohup; no sbatch/Job/commit here)
```

There is no teardown verb to wire in (§5 is n/a) and no platform proxy — the only knobs that matter are the
ones that keep artifacts on the disk you intend and the env pinned to your project, not `base`.
