# Monitoring Patterns — durable watching of a remote GPU job

Platform-agnostic recipes for a long-running detached job on a rented box. The key distinction is between
**remote correctness**, **watcher durability**, **model notification**, and **recovery** (§3). A session-bound
watcher or UI task chip proves none of the others. Every recipe uses portable primitives — `tmux` OR `squeue`
OR `pgrep`, a marker OR artifact `mtime` — with concrete paths bound by `profiles/<platform>.md`.

To jump: `grep -in '<keyword>' references/run-remote/monitoring_patterns.md`.

## Table of contents

- §0 Monitoring physics — the four facts every recipe rests on
- §1 The robust short-connection ssh-poll template (the safe poll primitive)
- §2 Quick health probes (one round-trip each)
- §3 Monitoring architecture — four separate responsibilities (L1 self-completion · L2 durable watcher · L3 model wake adapter · L4 recovery capsule)
- §4 Stale-waiter hygiene — one waiter per live run, right lifetime
- §5 Two-leg self-completion — guaranteed results + best-effort cadence
- §6 Failure triage on the log
- §7 Monitoring across agent hosts — per-host background/loop/cron primitives + the 2 portability rules (Claude Code · Codex · Cursor · Trae · generic)

---

## §0 Monitoring physics — the four facts every recipe rests on

Verified in-session, not assumed. The whole architecture is engineered around these:

> **Tool-portability note:** treat every background/task/scheduler primitive as session-bound until its restart
> and notification behavior has been verified on the active host. Product names are not durability evidence.
> Map the responsibilities below to actual primitives; do not assume another agent host's behavior.

1. **Foreground Bash hard-caps at 600 s (10 min).** A long foreground wait/monitor is *killed* at the cap
   — so never foreground-poll a multi-hour run.
2. **A session background task may outlive a turn but may not outlive restart, compaction, or provider loss.**
   It is useful for bounded waiting only while its host lifecycle remains alive.
3. **A never-*exiting* watcher never notifies.** No exit event = no notification, ever. A persistent
   `while true` / a stray `grep` reading stdin hangs silently forever and the user reads silence as "dead
   monitor". Every watcher must have a bounded exit.
4. **An unquoted `|` inside a poll regex hangs forever.** The shell splits `grep -hE a|b|c log` into three
   piped commands; the first (`grep -hE a`, no filename) reads **stdin** → blocks → the pipeline never
   returns → the ssh never returns → the background process never exits → fact 3 fires. ALWAYS quote the
   regex AND give grep a filename.

Corollary — **trust the artifact, not the silence.** When a job "looks done," Read its output file and
re-check ground truth (`grep DONE log; tmux ls / squeue; nvidia-smi`) before claiming success. Do not
wait blindly for a notification that may never fire. This is the `references/verifying/methodology.md` (REQUIRED)
Iron Law applied to monitoring.

---

## §1 The robust short-connection ssh-poll template (the safe poll primitive)

The single most important pattern: a poll that cannot hang (fact 4) and cannot strand a half-open
connection. **Never hold one long ssh open for the whole wait** — loop locally, reconnecting each tick.

```bash
#!/usr/bin/env bash
set -u
# Short-connection poll: ssh in → check → disconnect; bounded local loop.
HOST="<alias>"                       # from profiles/<platform>.md
LOG="/path/to/run.log"               # remote log path (profile-bound)
PATTERN='QUEUE DONE|Training completed'   # QUOTED → '|' is alternation, never a pipe (fact 4)
MAX=120                               # bounded: 120 ticks × 90 s ≈ 3 h, then give up cleanly
i=0
while [ "$i" -lt "$MAX" ]; do
  # ConnectTimeout + ServerAlive bound a network blip to ~30 s instead of a multi-minute half-open hang.
  if ssh -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 "$HOST" \
       "grep -qE '$PATTERN' '$LOG'"; then          # quoted regex + a FILENAME → grep reads the file, never stdin
    echo "DONE marker found"; exit 0
  fi
  i=$((i+1)); sleep 90
done
echo "poll gave up after $MAX ticks — check ground truth manually"; exit 1
```

Non-negotiables baked in above:
- **Quoted regex + a filename** on every remote `grep` — the two independent guards against fact 4.
- **`ConnectTimeout` / `ServerAliveInterval` / `ServerAliveCountMax`** — a dropped link self-kills fast.
- **Short connection per tick, bounded local loop** — one ssh per check, a hard tick ceiling so the
  waiter always EXITS (fact 3) and therefore always notifies when backgrounded.
- **Detect "done" by a log MARKER, never by `pgrep`** of the waiter's own pattern — `pgrep -f` matches
  the waiter's own command line and the loop never ends. On a queue scheduler, `squeue -j <id>` going
  empty is the equivalent done-signal.
- **Don't hammer a flapping link; back off, and don't read "can't connect" as "the box died."** The
  ≥90 s tick above is already gentle — on a *failing* connection do NOT tighten the loop or tight-retry the
  reconnect: a reconnect storm trips `sshd MaxStartups` (unauthenticated connections over the cap are
  refused), a proxy/gateway rate-limit, or `fail2ban`, making the link *harder* to reach. Back off on a
  failed tick (exponential, capped), and once back in, judge OOM/death from real resources (`free`,
  `nvidia-smi`, the cgroup `oom_kill` counter — **U41**), never from connection refusals alone.

Run this through a verified watcher primitive or as a single foreground tick under the host's turn limit. If
the only available runner is session-bound, disclose that limitation and rely on L1 remote self-completion plus
L4 recovery. **Never foreground-poll the full wait.**

---

## §2 Quick health probes (one round-trip each)

Each is a single short ssh. Combine several into ONE round-trip for a patrol tick (§3). Detach-primitive
and paths come from the profile; the structure is identical everywhere.

> A blank live **TensorBoard tile / web panel** while these probes show a healthy run is **not** a dead
> run — it is `references/run-remote/gotchas_universal.md` **U39**: the panel reads a fixed logdir/port your logger
> didn't write to, or the TB/watcher process died (ran foreground, not under the detach primitive), or the
> port isn't exposed. Fix per the platform profile; never restart a healthy run over an empty panel.

**Is the job alive? (tmux OR squeue OR pgrep — pick the profile's primitive)**
```bash
ssh "$HOST" "tmux ls 2>/dev/null || true; squeue -u \$USER 2>/dev/null || true; pgrep -af 'train' | grep -v grep | head -3"
```

**Progress since last check** — grep the run's OWN log, not a shared master:
```bash
ssh "$HOST" "grep -nE 'Epoch [0-9]+|Training completed|Early stopping|FINISHED|QUEUE DONE' '$RUN_LOG' | tail -6"
```

> **Gotcha — crash-detect on the per-run log, never the shared master.** Symptom: a poll reports "run D
> crashed" while D trains fine. → Root cause: a `tee`'d master log concatenates every run, so grepping it
> for `Traceback|OutOfMemory` matches an EARLIER run's crash text and false-positives on a healthy later
> run. → Fix: scope crash detection to the per-run log (`<name>.log`); reserve the master-log grep for
> `DONE`/`FINISHED`/`QUEUE DONE` and progress markers. A waiter that crash-checks the wrong log spins to
> its full timeout on a phantom failure.

**Resource pressure** (cgroup mem, GPU) — thresholds are rough, profile-tunable:
```bash
ssh "$HOST" "nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader; \
  [ -f /sys/fs/cgroup/memory.current ] && numfmt --to=iec \$(cat /sys/fs/cgroup/memory.current)/\$(cat /sys/fs/cgroup/memory.max) 2>/dev/null"
```
- cgroup mem > 90% of max → OOM risk; GPU util > 60% → healthy, not data-bottlenecked.
- GPU at 0% but the step log advances ≠ idle — it is CPU-data-bound; sample util over several seconds,
  never one snapshot. (Diagnosis → `references/verifying/methodology.md`, REQUIRED.)

**Disk — the silent killer** — watch `df -i` (inodes) AND `df -h` (bytes); inodes die first on
many-small-files eval output (→ `references/run-remote/gotchas_universal.md`):
```bash
ssh "$HOST" "df -h '$DATA_MOUNT'; df -i '$DATA_MOUNT'"
```

---

## §3 Monitoring architecture — four separate responsibilities

Session-bound watchers die with their host lifecycle, remote jobs may continue without them, and stale UI chips
may remain visible after the process is gone. Split four responsibilities. Only L1 is required for execution
correctness; L2 is durable only when its owner is verified to survive the relevant restart; L3 is a notification adapter, never the source of truth;
L4 makes recovery cheap.

| Layer | Lives where | Job | Survives |
|---|---|---|---|
| **L1 self-completion chain** | ON the box (tmux / nohup / sbatch dependency) | the work sequences itself: `until grep -q 'Training completed' log; do sleep 150; done && <next stage>`; stages hand off via `touch /path/STAGE_DONE` markers | session death, network loss |
| **L2 durable watcher** | remote OS, local OS scheduler, or product-native monitor with verified restart semantics | bounded polling/alerts; exits or re-arms on material state | only the failures its owner was proven to survive |
| **L3 model wake adapter** | active agent/session notification surface | tells the model about a material L2/L1 event | no durability assumed; stale UI state is possible |
| **L4 recovery capsule** | project note/task capsule | exact first probe, marker/artifact paths, watcher identity, next action | new session recovery without replaying the charter |

### L1 — on-box self-completion chain (correctness)
The box finishes its own pipeline regardless of any watcher. Chain stages under one detach primitive and
**join them with `&&`, never `;`** so a marker only lands on success:
```bash
# tmux / nohup variant — the detach primitive is the swappable plug (sbatch dependency on Slurm)
nohup bash -c '
  set -u
  until grep -q "Training completed" /path/to/train.log; do sleep 150; done \
    && python -m eval ... \
    && touch /path/to/STAGE_DONE        # marker ONLY on a clean &&-chain
' </dev/null >/path/to/chain.log 2>&1 &
```
> **Gotcha — success-gate the chain markers.** Symptom: the downstream chain fires on a phantom
> completion. → Root cause: joining stages with `;` (or a bare `touch` after a crashing stage) stamps the
> marker even when a stage died — a live disk-full `torch.save` killed stage 3, the `;`-marker still
> landed, the next stage ran on nothing. → Fix: `&&` between every stage and the final `touch`; detect
> done by the marker, never by `pgrep` of the waiter's own pattern (fact 4 / §1).

> ⚠️ **Gotcha — never gate on a string the PAYLOAD prints; gate on an artifact, or on a marker YOUR
> wrapper writes.** The `until grep -q "Training completed" train.log` above is convenient but it trusts
> the trainee to emit its own last line. **Measured failure (2026-07-22, cost ≈12 h × 2 boxes):** two runs
> completed all 100 epochs and wrote 442 MB `best.pth` + `metrics.json` + tfevents, yet **exited without
> ever emitting that final line** (one died at teardown, one hung in DataLoader-worker join with the GPU
> idle). The gate string could never arrive, so the downstream queue waited forever — and the crash-scan
> stayed quiet because it greps `Traceback|OOM|Killed` and **a stall is not a crash: it leaves no
> signature at all.**
> - **Gate on what the work produces** (`best.pth`, a result JSON) **or on a marker your own `&&`-chain
>   touches after the command returns.** Both are under your control; the payload's stdout is not.
> - **Bound every wait**: `until [ -f "$ART" ] || [ $waited -ge $MAX ]` … then proceed-and-warn. An
>   unbounded `until` turns one bad assumption into indefinite idle billing.
> - **Gate predicate and alarm predicate must be INDEPENDENT.** In that incident the runner's gate and the
>   watcher's completion test were the *same* `grep "Training finished"` — one wrong assumption took out
>   the work **and** its alarm together. Gate on the artifact; alarm on **liveness** (L2: newest-log mtime
>   age, GPU util, trainer-process count). **If your watcher would print nothing while the box sits
>   silent-but-alive, it is not a monitor.**

> ⚠️ **Root cause behind both halves — a log is append-only history; it cannot answer "what is true
> NOW".** Two failures one hour apart, same disease, opposite symptoms:
> - waited on a string that **never arrives** (payload exited without printing its last line) → infinite wait;
> - decided "finished" from `grep -c "QUEUE COMPLETE"` over the **cumulative** runner log → once a queue
>   completed, that marker lives forever, so the same box **given fresh work still reads as done** and
>   silently drops out of monitoring.
>
> **Rule:** a log proves *something happened once*; it never proves *the current state*. Ask live things
> for live state — process/session presence (`pgrep`, `tmux ls`, `squeue`), file **mtime age**, GPU util —
> and use the log only for the **last line** (current) or for a **count you compare against a previously
> seen count** (delta), never for a bare "does this string exist anywhere".
> Working predicate: `finished = (no session AND no process) AND (last log line says complete)`;
> `dead = (no session AND no process) AND (last line does NOT say complete)`; `stalled = alive BUT newest
> log mtime older than N min`. All three are distinguishable; a cumulative grep collapses them into one.

### L2 — durable watcher (liveness)

> **This machine already has the L2 machine-liveness layer built (2026-08-20):** launchd job
> `com.example.remote-watch` runs `~/.claude/scripts/remote_watch.sh` every 10 min against
> `~/.claude/remote-watch.json` (per-target heartbeat path + max age; stale/unreachable → macOS
> notification + `~/.claude/remote-watch-alerts.log`). **Adding a run's box = editing that JSON**,
> not building a watcher. This layer answers "is the box alive"; the per-run patrol tick below
> still answers "is the RUN healthy".

Use an on-box service/cron, a local OS scheduler, or a product-native monitor only after verifying ownership,
restart behavior, cancellation, and secret boundaries. Creating OS persistence requires explicit authority. If
no durable primitive is available, do not simulate one with an active model task: rely on L1 and L4 and say that
progress will be reconciled on the next session. A watcher tick uses this checklist:
- **ONE combined ssh probe per tick** — alive-check (tmux ls / squeue / pgrep) + `*_DONE` markers + last
  epoch line + artifact `ls` + dataset file COUNTS, in a single round-trip.
- **An explicit decision table**, e.g.: ssh down → tell the user to check the console (only they see
  balance/power state); detach session missing AND no completion marker → resume from `latest` + rebuild
  the L1 chain; result CSV exists → `cat` it and report the numbers verbatim; remote file count below the
  local source → resume the transfer; everything done → delete the patrol job itself.
- **Separate cheap liveness from model output.** A durable watcher may write one local liveness line each cycle;
  wake the model only for a material delta, terminal state, blocker, new authority, or agreed sparse cadence.
- **Completeness = file COUNT against the local source** (bytes/hash when names collide), NEVER `test -d`
  — a dir created by a killed transfer passes existence checks forever.
- **Never blind-restart** — probe session/log/markers first so a patrol firing mid-run cannot
  double-launch (idempotence). Classify each outcome → a fixed remediation; never blind-retry.

> **Ready-made tick:** `scripts/health_patrol.sh.template` is this checklist as one runnable,
> read-only ssh round-trip — alive + done-count + last epoch + crash-scan + `df -h`/`df -i`, an
> escalation predicate — parameterized from the profile's §8. For a machine-owned runner, set
> `PATROL_STATE` to an absolute caller-owned state path and `PATROL_RUN_ID` to this run's stable unique ID.
> It atomically records each observation but emits only baseline, result-count/status changes, new failures,
> recovery, or completion. Epoch/disk noise and repeated failures stay in local state. In this mode exit 0
> means no new escalation, not necessarily healthy; inspect the recorded status. Missing/corrupt state or
> filter failure stays visible. Invoke a model only when stdout is nonempty; a native adapter must preserve
> event delivery/retry semantics before this can be claimed as a working notification path.
>
> Run this filter **before** the model call. A model-scheduled heartbeat or `/loop` already invokes the model;
> hiding its reply only reduces notifications. Preserve the user's agreed cadence; if the host has no pre-model
> event adapter, disclose that remaining call cost instead of inventing an OS scheduler or changing the schedule.
> Normal model reads use only the latest state/delta and evidence pointers; completion/error reads fetch just the
> affected acceptance record or traceback. Cached input still occupies context; cumulative input across calls is
> not one request's context size. Do not replay whole charters, old guardrails, or closed reviews at each tick.

### L3 — model wake adapter (latency)

Bind L2 or the on-box completion event to the host's actual notification mechanism when available. A
session-background completion can be useful, but it must not be described as restart-durable unless that exact
host behavior has been tested. After any resume, re-probe L1/L2 truth and re-arm at most one adapter. Notification
loss does not change remote state; notification success does not replace artifact verification.

### L4 — recovery handbook (continuity)
Persistent notes a brand-new session inherits from one word ("继续"): exact resume commands, the L1 chain
definition, every marker path, the "first command on reconnect." Two durable hardenings:
- **Externalize transfer/monitor state to a stable OS path** + a DONE marker file *outside* the session
  dir, so any future session resumes by reading files instead of re-uploading.
- **True restart-immunity means an OS-owned process** — on this machine it exists (the launchd
  watcher above, user-approved 2026-08-20): registering a target is a JSON edit, no new authority
  needed. Building a NEW os-level watcher elsewhere still needs the user's explicit approval first.

> **Gotcha — after a context compaction, reconcile UI task chips against the OS process table.**
> Symptom: 5 chips show "Running" for 2–6 h while zero ssh/scp processes exist and a "running" upload
> actually died at 2/10 checkpoints, silently gating the downstream eval all evening. → Root cause:
> background shells die with the old session, but their chips keep showing "Running"; the new session's
> task list is empty, so the only ground truth is a process scan. → Fix: **first action after any
> compaction is a process-scan** (e.g. `Get-CimInstance Win32_Process` matched on the remote host string,
> or `pgrep`/`ps` for ssh/scp), relaunch dead transfers with a byte-size verify, re-arm ONE fresh
> sentinel, and tell the user to clear the husks.

---

## §4 Stale-waiter hygiene — one waiter per live run, right lifetime

> **Gotcha — stale background waiters pile up.** Symptom: the Background-tasks panel shows 8+ "Running"
> wait-loops at 500–740 min elapsed, ssh-polling every ~20 s, while the GPU is idle and the experiment
> finished hours ago. → Root cause: every kill+restart of a flaky-network saga armed a NEW
> `until ssh grep MARKER; do sleep 20; done` waiter but never stopped the OLD one — its marker (in a
> superseded log) never appears, so it loops forever (fact 3). → Fix below.

- **One waiter per live run.** Superseding a run → cancel its old waiter with the current host's
  watcher/task-control capability first (Claude Code: `TaskStop` or dismiss the task chip; other hosts:
  use their actual cancellation mechanism, never assume the Claude primitive exists).
- **Match watcher lifetime to the wait.** A multi-hour wait needs a verified product/OS watcher plus a stall
  detector. Session-bound monitors may disappear on resume even when labelled persistent; after any resume,
  **check remote ground truth directly** (tmux ls / squeue, `grep DONE log`, `nvidia-smi`) before re-arming one.
- **A dropped poll connection ≠ the job dying.** A long background ssh poll gets killed by the remote's
  idle-SSH timeout while the detached training runs on independently. Re-ssh and verify the process/
  artifacts directly before concluding anything died.

---

## §5 Two-leg self-completion — guaranteed results + best-effort visibility

"I'll check periodically" is a lie unless a trigger is ARMED — between turns the assistant does not run.
Two legs, never conflated:

- **Leg 1 — remote self-completion (guaranteed, survives session/SSH death):** the L1 chain
  (`train → eval → touch marker` under one detach primitive). Detect done by a log/marker, never by
  `pgrep` of the waiter's own pattern. This guarantees RESULTS but gives no reporting cadence.
- **Leg 2 — live visibility (best-effort):** a verified L2 watcher may feed an L3 notification adapter. If the
  agent platform or session is down, no model-side notification is promised; the remote still finishes through
  Leg 1 and the next session reconciles from artifacts and the recovery capsule.

> **A cloud scheduler cannot reach a rented box.** A cloud schedule (`/schedule` / RemoteTrigger) runs in
> an isolated sandbox with its own checkout and **no access to the local SSH key or network** → it cannot
> ssh the box, and the SSH private key must **never** be placed in a cloud agent (secret-leak). The honest recurring check is the remote self-monitor + a session loop, not a cloud robot pinging
> the box. Don't promise autonomous cross-session polling that can't be delivered.

For a hosted tracker whose metrics survive teardown and can be polled as a structured monitor instead of
brittle ssh-tail, use `huggingface-skills:huggingface-trackio` if that plugin is installed (it is NOT on this machine) — poll its alerts
rather than grepping a remote log.

---

## §6 Failure triage on the log

When a probe shows trouble, pull the full traceback from the per-run log (§2) and classify — each
outcome maps to a FIXED remediation; never blind-retry:

```bash
ssh "$HOST" "grep -B2 -A20 'Traceback' '$RUN_LOG' | head -50"
```
- `basic_ios::clear: iostream error` + `unexpected pos N vs M` → **disk full during checkpoint save**;
  check `df -h`/`df -i`, prune `latest`/periodic snapshots to recover (→ `references/run-remote/gotchas_universal.md`).
- bare `Killed` / exit 137, no traceback → **cgroup OOM** (workers × big in-RAM tensor); size workers
  vs `memory.max`, not CPU count.
- `CUDA out of memory` → VRAM, usually consistent across runs (batch too big / concurrent job), rarely
  transient.
- `KeyError` / `AttributeError` → config/code mismatch; investigate code, do not retry.
- Early-stop far below baseline with a grad_norm P99 spike in epoch 1–2 → likely **probabilistic
  divergence**; whether it's a bug or a real effect, and the retry-the-identical-config rule, belong to
  `references/verifying/methodology.md` (REQUIRED) — this skill owns *running* the retry, not judging the number.
- log frozen (no new lines) but checkpoint `mtime` advances → **block-buffered stdout**, not a hang
  (`references/run-remote/gotchas_universal.md` U43; run `python -u`/`PYTHONUNBUFFERED=1`).
- `uptime`/`free` on the box look maxed but your cgroup is roomy → **noisy neighbor** on the shared host,
  not your job (`references/run-remote/gotchas_universal.md` U41; the authoritative OOM check is the `oom_kill` counter
  in `/sys/fs/cgroup/memory.events`).
- GPU SM% pinned low while a python thread-storm pegs the cores → **intra-op thread oversubscription** on a
  vCPU slice (`references/run-remote/gotchas_universal.md` U40; cap `OMP_NUM_THREADS` to the cgroup quota).

Universal gotchas (silent sync, CRLF, mid-run script overwrite, inode caps) are NOT restated here —
see `references/run-remote/gotchas_universal.md` (`grep -in '<keyword>' references/run-remote/gotchas_universal.md` to jump).

---

## §7 Monitoring across agent hosts

The four layers are host-agnostic; only **which primitive runs L2/L3** changes per host. Two rules port
the whole architecture to Codex / Cursor / Trae / any Agent-Skills host:

**Rule 1 — correctness needs no active agent.** L1 (the box self-completes + `touch`es a marker) plus the
box **pushing its own notification** at the end of the `&&`-chain — a `curl` webhook / email / a
`huggingface-skills:huggingface-trackio` alert — works on EVERY host, because it runs entirely on the
rented box. On a host with no background/scheduler primitive, this IS the monitor; the agent just pulls
results on its next turn.

**Rule 2 — a CLOUD scheduler cannot reach a rented box (§5), on ANY host.** Every host's hosted
automation runs in an isolated sandbox with no local SSH key or network, so it cannot ssh your box (and
the key must never be placed in one — secret-leak). Use cloud cron only to **re-wake the agent** or
**poll a hosted tracker**, never to probe the box. The box-reaching poll must use the host's
**local/session** runner (which holds your SSH key), or be the L1 on-box loop.

| Agent host | Session/local runner | Durable watcher | Cloud automation | Required claim |
|---|---|---|---|---|
| **Claude Code** | background task/monitor while its actual lifecycle remains alive | product monitor or OS/remote scheduler only when restart behavior is verified | hosted schedules cannot inherit local SSH secrets | never infer durability from a task chip |
| **OpenAI Codex** | local task/terminal helper on the key-holding machine | product automation/monitor or OS/remote scheduler only when scope and restart behavior match | hosted automation may re-wake or poll a hosted tracker, not assume local-key access | verify the actual thread/terminal lifecycle |
| **Other hosts** | use only documented local behavior | remote self-completion or an explicitly authorized OS/product watcher | treat cloud sandboxes as separate machines | unknown defaults fail to L1 + L4, not to an active spinner |

> **Hosts not in the table** (VS Code / Copilot, Goose, Kiro, …) take the **Generic** row until they expose a local recurring runner that holds your SSH key — until then, wire **Rule 1** (the on-box self-push) and let the agent pull on its next turn.

**Binding the layers:** L1 is unchanged everywhere. Select L2 only from capabilities verified on the current
host and target topology. L3 may reduce notification latency but never owns correctness. When only a session
runner or cloud sandbox exists, do not promise autonomous local-key polling: retain L1, a compact L4 recovery
capsule, and reconcile on the next turn.
