# Launching & detaching a local single-GPU run — nohup / tmux, log + alive probe, don't block

Start one training run on a workstation you own, **detach it from the terminal** so closing the shell
doesn't kill it, send its output to a file you can tail, and confirm it is alive **without blocking on it**.
This file owns *making a local run start, survive the shell, and be observable*; whether the resulting number
is correct is `references/verifying/methodology.md`, and fitting a model that OOMs is
`references/run-local/local-oom.md`.

To jump: `grep -in '<keyword>' references/run-local/launch.md` (e.g. `nohup`, `tmux`, `disown`, `tail`,
`pgrep`, `alive`, `CUDA_VISIBLE`, `stdbuf`).

## Table of contents

- **Pre-flight** — L1 env confirmed + GPU visible · L2 pick the card
- **Detach** — L3 tmux (interactive) · L4 nohup (headless) · L5 redirect stdin from /dev/null
- **Observe without blocking** — L6 log to a file + tail · L7 the alive probe (process + GPU + log mtime) · L8 don't foreground-wait
- **Pointers** — multi-GPU → multi-gpu.md · OOM → local-oom.md · resume spine → ../run-remote/spot-resilience.md

---

## Pre-flight

### L1 — Confirm the env and that the GPU is actually visible (before launching)

**Symptom**: the run starts, then either imports the wrong torch / installs into `base`, or silently trains
on **CPU** at ~100× slowdown because CUDA wasn't visible to the process.

**Root cause**: two independent pre-flight failures — the active env may be `base`/wrong (env hygiene), and a
process can run fine while seeing zero GPUs (wrong `CUDA_VISIBLE_DEVICES`, a driver/toolkit mismatch).

**Fix**: pass the env gate (`references/run-local/env-hygiene.md`), then prove the GPU is reachable from the
**same** interpreter you'll launch with:
```bash
python -c "import sys,torch; print(sys.executable); print(torch.cuda.is_available(), torch.cuda.device_count())"
# .../envs/myproj/bin/python   True   1     <- env right AND ≥1 GPU visible  → proceed
# ...                          False  0     <- CPU-only: fix env/driver before a long run
```
`torch.cuda.is_available() == True` with a non-zero device count is the gate. A `False` here means a long run
would waste hours on CPU — stop and fix first.

### L2 — Pick the card explicitly on a multi-GPU box (`CUDA_VISIBLE_DEVICES`)

**Symptom**: a single-GPU run lands on a card another job is already using, and both crawl or one OOMs; or it
defaults to GPU 0 which you wanted to keep free.

**Root cause**: a local box has **no scheduler** — nothing stops two processes sharing one card. Without
pinning, a run grabs GPU 0 by default and can collide with an existing holder.

**Fix**: pin the run to a specific, free card and check for an existing holder first:
```bash
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv   # find a free card
CUDA_VISIBLE_DEVICES=1 python train.py ...                              # pin to GPU 1
```
The process sees only the listed device(s) as `cuda:0…`. For a true single-GPU run, list exactly one index.
(Splitting *one* job across several cards is `references/run-local/multi-gpu.md`, not this.)

---

## Detach — sever the run from the terminal

A foreground `python train.py` dies the moment the shell closes, the laptop sleeps, or SSH drops — its parent
is the terminal, and the hang-up sends SIGHUP. Pick **one** detach primitive before a long run, not after it
is already orphaned.

### L3 — `tmux`: detach when you want to reattach an interactive view

**Symptom**: you want to watch the run live sometimes but also walk away and close the laptop without killing
it.

**Root cause**: a plain shell job is tied to the terminal; you need a session that outlives the connection
yet can be re-entered.

**Fix**: run inside `tmux` and detach:
```bash
tmux new -s train          # new session
#   (inside) conda activate myproj && CUDA_VISIBLE_DEVICES=1 python train.py | tee run.log
#   Ctrl-b then d          # detach — the run keeps going
tmux attach -t train       # reattach later
tmux ls                    # reconcile a watcher against the real session
```
`tmux` survives an SSH drop and a closed terminal. It does **not** survive a host **reboot** — after a reboot
the session is gone and the run must be relaunched (make resume idempotent, L-pointers). On a desktop you keep
on, reboot is rare; on a laptop that sleeps, sleep is fine (tmux survives it) but a shutdown is not.

### L4 — `nohup`: detach headless (no session to reattach)

**Symptom**: you just want the run going in the background and don't need an interactive view — or `tmux`
isn't installed.

**Root cause**: same SIGHUP problem; you need the job immune to hang-up without a session manager.

**Fix**: `nohup … &` then `disown`, with **all three streams redirected** (L5):
```bash
nohup env CUDA_VISIBLE_DEVICES=1 python -u train.py ... </dev/null >run.log 2>&1 &
disown                      # detach from the shell's job table so exit doesn't HUP it
echo $!                     # the PID — record it for the alive probe (L7)
```
`nohup` ignores SIGHUP; `disown` removes the job from the shell so logging out doesn't signal it. `python -u`
(or `stdbuf -oL`) is important — see L6.

### L5 — Redirect **stdin** from `/dev/null`, not just stdout/stderr

**Symptom**: a backgrounded run mysteriously stops (SIGTTIN) the moment it tries to read input, or the shell
won't fully detach.

**Root cause**: a background job still attached to the terminal's **stdin** gets stopped when it reads from
(or the terminal is closed under) it. Redirecting only stdout/stderr leaves stdin dangling.

**Fix**: always redirect **all three**: `</dev/null >run.log 2>&1`. `</dev/null` guarantees the job never
blocks or gets stopped reading a terminal that may go away. This is why the L4 line leads with `</dev/null`.

---

## Observe without blocking

### L6 — Log to a file and tail it (and disable output buffering)

**Symptom**: `run.log` stays empty for many minutes even though the run is clearly working, so you can't tell
progress from a hang.

**Root cause**: when stdout is a **file/pipe** (not a TTY), Python and libc switch to **block buffering** —
output is held in a 4–8 KB buffer and only flushed in chunks, so an early log line can sit invisible for a
long time.

**Fix**: force line-buffering at the source, then tail the file:
```bash
python -u train.py ...            # -u = unbuffered; or: stdbuf -oL -eL python train.py
tail -f run.log                   # follow live; Ctrl-C stops tailing, NOT the run
tail -n 50 run.log                # a quick recent snapshot without following
```
`tail -f` only reads the file — interrupting it does **not** touch the training process. `tee` works too
(`python -u train.py | tee run.log`) when you want the line on screen *and* in the file.

### L7 — The alive probe: process + GPU activity + log freshness (three signals)

**Symptom**: you need to know "is it still training?" — but a live PID alone can be a hung process, and a
fresh log alone can be a process about to be reaped.

**Root cause**: any **single** signal lies. A PID exists for a deadlocked process; `GPU-Util` reads high for a
spin-wait; a log can look recent then stop. Ground truth is the **intersection** of independent signals.

**Fix**: check three cheap things, none of which blocks the run:
```bash
pgrep -af 'train.py' | head                                   # 1. process alive? (or: ps -p <PID>)
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv   # 2. GPU doing work?
ls -l --time-style=+%H:%M:%S run.log                          # 3. log mtime advancing?
```
Re-run after ~30 s: a moving log mtime **and** non-trivial GPU memory/util **and** a live PID ⇒ training. A
live PID with a **stale** log and **idle** GPU ⇒ hung or stuck on data — investigate, don't assume progress.
Read SM clock/power (`nvidia-smi dmon -s pucm`) over raw `GPU-Util` when in doubt — util% can read busy while
the kernel spins.

### L8 — Don't foreground-wait on the run (let it detach, poll instead)

**Symptom**: the launching shell (or an agent) sits **blocked** for hours holding the foreground run, unable
to do anything else, and a dropped connection then kills the job.

**Root cause**: a foreground process couples the run's lifetime to the watcher's connection and monopolizes
the shell. Blocking to "wait for it to finish" is the wrong model for a long job.

**Fix**: **detach (L3/L4) and poll (L7)**, never block in the foreground. The pattern is: launch detached →
record the PID/session → periodically run the alive probe → react to ground truth (best-ckpt mtime, the log
tail), not to a foreground wait. A dropped *poll* connection is not the run dying — re-check directly before
concluding anything. For an agent driving this, the same rule holds: kick off the detached run, then return
and check on it; do not hold the turn open waiting on training.

---

## Pointers — handled elsewhere, do not restate

- **Splitting one job across multiple local GPUs** (`torchrun`/`accelerate`, the rank env, DDP hangs) →
  `references/run-local/multi-gpu.md`.
- **OOM / VRAM / host-RAM** while launching or mid-run → `references/run-local/local-oom.md`; the full
  fit-it ladder → `references/training/oom-memory.md`.
- **Resume after a reboot / crash** (atomic checkpoint write, load-latest, idempotent relaunch) →
  `references/run-remote/spot-resilience.md` (the cadence + atomic-write pattern is platform-agnostic).
- **Is the resulting number real** (seed, determinism, collapse, delta-vs-noise) →
  `references/verifying/methodology.md`.
