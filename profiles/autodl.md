---
platform: autodl
kind: ssh-rental
meter_stop_verb: 关机           # shutdown/power-off STOPS billing AND keeps /root + disks
meter_stop_irreversible: false  # the AutoDL EXCEPTION — 关机 is reversible; only 释放/release deletes
detach_primitive: tmux          # nohup fallback when tmux is not installed (often absent on fresh image)
spot_available: false           # on-demand only; no spot/bid/preemption model
spot_grace: n/a
shared_fs: true                 # /root/autodl-fs — region-locked, cross-instance within one region
inode_cap: ~200K                # hard cap on the shared FS, independent of byte capacity
free_egress: true               # no per-GB egress fee, but cross-GFW pulls need the academic proxy (see china_mirror_needed)
china_mirror_needed: true       # behind the GFW — hf-mirror / ModelScope + /etc/network_turbo
host_driver_cuda_max: image-dependent   # the prebuilt image pins torch+CUDA; do not downgrade (AD9)
local_nvme: true                # /root/autodl-tmp data disk is fast local NVMe, per-instance
---

# Profile: AutoDL

The deepest, battle-tested profile — a Chinese cgroup-isolated SSH-rental with a 3-tier storage substrate,
one fixed project run layout, and the *one* rental where the meter-stop action is non-destructive.
Fills all 8 schema sections
(`profiles/_schema.md`) at full depth. Read it before Phase 0 of
`references/run-remote/lifecycle_checklist.md`; it owns every path, proxy, billing verb and TB pin the run
phases delegate to. Universal gotchas are NOT restated here — see
`references/run-remote/gotchas_universal.md`.

> **Surface to the user up front (principle #10):** conveniences most users miss — the console has a
> **one-click "设置SSH免密登录"** (registers your key so the agent connects non-interactively), **GPU-availability
> notifications** ("订阅GPU通知"), and built-in **AutoPanel / JupyterLab / TensorBoard** tiles. ⚠️ Danger clocks
> — **关机 (stop) auto-releases the box after 15 days → the data disk is deleted** (AD-DANGER, §5); only
> `/root/autodl-fs` survives a 释放; low balance / arrears force-stop. And the TB tile is **pinned to
> `/root/tf-logs`** — write your logger there (or symlink) or the panel shows empty (AD7 / U39).

## 1. LAUNCH

**First time? (rent → reach the box).** On the AutoDL console: pick a GPU + region with stock → **创建实例**
(choose the PyTorch image — the base env ships prebuilt) → register your key once via **设置SSH免密登录**
(so the agent connects non-interactively) → copy the instance's **SSH connection string** + password from the
console → test `ssh -p <PORT> root@connect.<region>.seetacloud.com 'nvidia-smi'`. That string is your entry to
every phase below. (Console-only steps; AutoDL's UI shifts — re-check its docs if a label moved.)

**Name the box on creation.** Rename each instance in the console to `<project>-<purpose>-<yyyymmdd>`
before the first ssh, mirror that name in the `~/.ssh/config` alias and in `active/<run-id>/run.json`, and
treat an unnamed instance as not yet yours to use.

**Entry points.** Web console (创建实例) for create/release/power; per-instance SSH connection string from
the console (`ssh -p <PORT> root@connect.<region>.seetacloud.com`). No first-class platform CLI/REST for
job control — SSH is the orchestration channel. Set a stable alias per instance in `~/.ssh/config`
(`Host autodl-<proj>-<N>`, `HostName connect.<region>.seetacloud.com`, `Port <PORT>`) so every later
command is short; the port is assigned at create-time and **changes on re-create** (update the alias).
SSH/keepalive config → `references/run-remote/ssh_transport.md`.

**Env contract — the prebuilt base miniconda IS the env (AD6, §7).** The image ships the full DL stack
into **base** (`/root/miniconda3/bin/python`); there is no `/root/miniconda3/envs/<name>/`, and base is the
deliberate single-tenant project env. **Never `conda create` / `conda clone base`** on the rental — cloning
wastes ~16 GB of base packages plus the disk just freed, for zero benefit. A local "no DL in conda base"
guard applies to persistent workstations only and must exempt remote-ssh + instance base. When installing
project deps, **filter framework pins** so a `requirements.txt` does not downgrade the image's torch build
(AD9).

## 2. STORAGE MODEL  *(survival matrix — principle #4)*

Three tiers, each with a different speed / size / inode profile and a **different survival behavior**:

| Tier | Path | Speed | Size | Inode cap | Scope |
|---|---|---|---|---|---|
| System disk | `/` | medium | ~30 GB | none | per-instance |
| Data disk | `/root/autodl-tmp` | **fast NVMe** | per-plan (e.g. ~50 GB) | none | per-instance |
| Shared FS | `/root/autodl-fs` | NFS (slow, ~30 s/sync) | ~200 GB | **~200K (hard)** | **region-locked**, all instances in one region |

**Survival matrix** — the part most platforms get wrong, and where AutoDL is the **exception**:

| Tier | Survives 关机 (stop)? | Survives 释放 (release/destroy)? | Notes |
|---|---|---|---|
| `/` system | **yes** | no | AutoDL persists `/root` across power-off — UNLIKE RunPod/vast/K8s/Colab |
| `/root/autodl-tmp` data | **yes** | no | fast tier; checkpoints written here mid-run |
| `/root/autodl-fs` shared | **yes** | **yes** | the ONLY tier that survives release; region-locked |

**Use this exact per-project binding.** AutoDL compute state stays below the fast data disk:

```text
/root/autodl-tmp/<project>/{cache,active,export/.partial,export/<run-id>,quarantine}
```

The `<project>` slug and `<run-id>` come from the run contract; they are placeholders, not permission to add
another `artifacts/` level or an `inbox/`. The state semantics and atomic closeout gates are in
`references/run-remote/artifact-layout.md`.

**Where checkpoints go:** write live checkpoints to
`/root/autodl-tmp/<project>/active/<run-id>/` on the fast data disk (never the 30 GB system disk).
`latest.pth` may be the mutable resume anchor there. Retain the selection best plus that anchor, with
`save_top_k <= 3` unless the user approved another policy. The data disk survives 关机 and remains
source-of-truth while the run is open. A later 释放 still loses any open run, so close to
`export/<run-id>` and verify/pull or hand that closed capsule to `mirror-research-artifacts` before release.
Never sync `active/` as a whole to `/root/autodl-fs` or Hugging Face.

**Region/DC-lock (AD3, §7).** FS quota is region-scoped — identical `/root/autodl-fs/` paths in two regions
are different physical mounts. Create the quota in the same region as the instances; bridge regions by scp
from a chosen primary (slow), and confirm sharing with a write-one / read-other probe before relying on it.

**Inode discipline (AD4, §7).** The ~200K cap is **independent of bytes**: `df -h` can read 34% while `cp`
fails "No space left" because `df -i` is at 100%. Bound exported visualization before rendering: for each
test, `min(100, N_test) × conditions × task-native roles`, with stable atomic files only under
`test/<test-id>/vis/<condition-id>/<task-native-role>/<sample-id>.png`. This full coverage is required for
every declared test and is not an optional preview set. Hardware output follows the same coverage rule but
must close as a separate `export/hardware/<hardware-run-id>` capsule, never inside software
`export/<run-id>`. Do not add a second selection manifest, legacy visualization index, default
montage/contact sheet, or full test-render tree; full-test metrics retain the full population.
Selection-manifest and vis-coverage rules: `references/run-remote/artifact-layout.md`.
Checkpoints are inode-cheap but still retention-bounded. Monitor `df -i`, not just `df -h` (Phase 0 +
every space check). Eval-artifact sizing policy is owned by `references/verifying/methodology.md`.

**Data-disk hog (AD5, §7).** When `/root/autodl-tmp` hits 100% but `active/` looks small, the real hog is
the **HF cache symlinked onto the data disk** (`~/.cache/huggingface` → tens of GB of model blobs): keep the
cache at `/root/autodl-tmp/<project>/cache/` by redirecting `HF_HOME` explicitly (see §8). Disk is
expandable — prefer expand over silently shrinking the experiment (principle #9); present exact `rm -rf`
targets and sizes and get explicit user confirmation before any delete.

## 3. NETWORK

**Egress proxy — `source /etc/network_turbo` is MANDATORY (AD1, §7).** Put
`source /etc/network_turbo 2>/dev/null || true` at the top of every shell/wrapper that calls wandb / HF /
pip / git. It exports `http_proxy` / `https_proxy` pointing at the in-DC academic proxy
(`http://<proxy-ip>:<port>`), a `no_proxy` allow-list for domestic endpoints, and the CA bundle. Perf
delta: wandb push ~0.8 s with turbo vs >120 s timeout without — no exceptions, even a small
`wandb.summary` write can wedge for minutes.

**China mirrors (AD2, §7).** Two AutoDL-only traps compound on top of the generic mirror story: (a) HF's
**Xet CAS backend** is NOT mirror-proxied (the mirror covers the API but big `.safetensors` shards still hit
the flaky international endpoint) → `export HF_HUB_DISABLE_XET=1` (or `pip uninstall -y hf_xet`) forces the
classic LFS path the mirror does proxy; (b) `no_proxy` in network_turbo lists `modelscope.com` but **not**
`modelscope.cn` — routing a DOMESTIC source through the international-acceleration proxy SLOWS it. A stall
is not a permanent failure: wrap every download in a `timeout <s> … && break` retry loop. Mirror table,
endpoint values and the `no_proxy` ladder → `references/run-remote/china-network.md`.

**Port exposure.** AutoDL maps a single custom port (6006) for user services; the platform also exposes
JupyterLab. SSH port is the per-instance `<PORT>` and changes on re-create.

**Platform TensorBoard is pinned to `/root/tf-logs` (AD7, §7).** The image autostarts
`tensorboard --logdir /root/tf-logs --port 6007` on boot and the AutoPanel TB tile proxies straight to that
pid; the `--logdir` cannot be reconfigured from inside the container, so events written anywhere else are
invisible in the web tile no matter how correct the `SummaryWriter` setup. Local logs die with the instance
— for durable curves use a hosted tracker (`huggingface-skills:huggingface-trackio` if installed, otherwise
the project's existing hosted tracker plus the bundled `scripts/wandb_forensics.py`).

**SSH flavor.** Direct-TCP SSH on the per-instance host:port — `scp`/`rsync` work normally (no proxied-SSH
restriction). Use a per-dir resumable loop for large transfers (single-connection `scp -r` resets mid-
transfer); `rsync -avz --partial` is preferred. Transport setup and host-key verification live in
`references/run-remote/ssh_transport.md`; after a connection loss, re-probe remote truth through
`references/run-remote/monitoring_patterns.md`. A connection error alone does not establish run,
instance, or billing state.

## 4. SPOT / INTERRUPTION + RESUME  *(principle #7/#8)*

**No spot/bid/preemption model — AutoDL is on-demand.** There is no mid-run eviction, no SIGTERM grace
window to handle (`spot_grace: n/a`). The real loss vectors are: (a) **forgot to release/关机** → idle
billing (principle #1); (b) an instance **reboot** that ends a non-detached process (a vanished process is
not always OOM — enumerate reboot / OOM / SSH-HUP / manual-kill before concluding, see
`references/run-remote/gotchas_universal.md`); (c) availability — the GPU plan being sold out at create-time (build
retry-until-available, not survive-an-eviction).

**Resume hook.** The universal spine still applies (principle #8): checkpoint atomically to
`active/<run-id>/state/`, keep it bounded, and resume-from-latest unconditionally on relaunch. Promote to
the FS only as a closed export. The detach primitive (§6) makes
the *identical launch command* survive an SSH drop; checkpoint+resume makes it survive a reboot. Cadence
formula → `references/run-remote/spot-resilience.md` (the formula generalizes even without spot — it bounds
re-compute lost to a reboot).

## 5. TEARDOWN / BILLING  *(principle #9 + the Iron Law; verified 2026-06)*

**关机 (shutdown / power-off) STOPS the meter AND keeps `/root` + both disks — this is the AutoDL
EXCEPTION among rentals.** Everywhere else (RunPod wipes the container disk on stop, vast bills the disk
forever, K8s wipes the pod FS, Colab loses `/content`) a "stop" is lossy or still-billing. On AutoDL,
关机 is the **safe park**: meter off, all three tiers intact, restart later. There is also a **no-GPU /
无卡模式 mode** for cheap restart to copy files or fix the env without paying for the GPU.

| Action | Stops meter? | Keeps `/` + data disk? | Keeps FS? | Reversible? |
|---|---|---|---|---|
| 关机 (shutdown) | **yes** | **yes** | yes | **yes** — restart anytime (the AutoDL exception) |
| 无卡模式 (no-GPU) | mostly (cheap) | yes | yes | yes |
| 释放 (release/destroy) | yes | **NO** | yes | **NO — deletes `/` + data disk irreversibly** |

**Cost trap.** 关机 still bills the data-disk *storage* at a small rate while the GPU meter is off — far
cheaper than running, but not free. Only 释放 fully ends storage billing, at the cost of the data disk.
**⚠️ Auto-release clock (AD-DANGER, verified 2026-06):** a 关机 (stopped) instance is **auto-released after 15 days** (the
console shows "关机 15 天后释放") → that release deletes `/` **and the data disk**, so 关机 is safe parking
only *within* the window; for a longer pause, first close canonical `export/<run-id>`, then pull-verify it or
hand it to `mirror-research-artifacts` for a durable replica. Low balance / arrears also force-stop the
instance. **Surface this to the user up front
(principle #10)** — most users assume 关机 parks the box indefinitely.
**Teardown Iron Law — AutoDL clause.** NO 释放 and no file-delete until the teardown gate passes and the
user explicitly approves (teardown gate: `references/run-remote/lifecycle_checklist.md` Phase 5). Because
关机 is non-destructive here, the cheap safe move when unsure is to **关机 and ask**, never 释放 on a guess.
If a separate verification-before-completion skill is installed, invoke it; otherwise stop before release.
The generic `mirror-research-artifacts` workflow owns the external frozen manifest, live exact-roster
validation, and readback evidence; a local `PULL_VERIFIED.json` is one optional delivery receipt and none
belongs in canonical `run.json`.

**Container shutdown wrapper.** Some AutoDL images expose `/usr/bin/shutdown` as a short provider-owned
ASCII shell wrapper with no shebang rather than an ELF binary. An interactive shell handles `ENOEXEC` by
running such a file through `/bin/sh`, but Python `subprocess.Popen(["shutdown", "-h", "now"], shell=False)`
does not and returns `Exec format error`. Do not misclassify that as an unsafe or unavailable shutdown.
Resolve the absolute path, require a regular root-owned non-writable file, read the complete bounded body
(at most 4 KiB), record its SHA-256, and reject unknown commands or paths. For a recognized provider
wrapper whose complete effects match current authority, execute `[/bin/sh, <absolute-shutdown-path>, -h,
now]` with `shell=False`. The observed wrapper may clear `/root/.local/share/Trash` before signalling the
container; report that concrete side effect and never treat it as permission to delete research evidence.
When that cleanup is outside scope but the fully read wrapper exposes one unambiguous stop operation, execute
only that operation after binding its exact target identity (for example one stable `supervisord` PID before
one `SIGTERM`); otherwise prefer the provider console/API 关机 control or stop with the exact body as one
blocker. Do not require ELF/shebang after exact semantic acceptance, and never guess a private signal from a
partial body.

## 6. DAEMON TOOL

**tmux** is the detach primitive when present, but **tmux is often NOT installed on a fresh AutoDL image**
and `apt-get install tmux` fails when egress is down. Zero-dependency fallback:
`nohup bash run_queue.sh queue.txt </dev/null >master.log 2>&1 &` — survives an SSH drop (SIGHUP), needs
no package. Verify either with `pgrep -af <script>`. The detach survives an SSH drop; it does **not**
survive a 关机/reboot — that is what checkpoint+resume (§4) is for.

⚠️ **The AutoDL gateway has been observed killing long-lived `nohup` processes.** Treat nohup as a
*short-job* escape hatch only; for anything long-running, getting tmux installed is worth the delay. If
forced onto nohup, assume silent death: re-verify liveness (`pgrep` + log mtime) at every check-in, and
**re-arm the monitoring waiter at every report** — a missed re-arm is a silent monitoring blackout.

**Native queue: none.** AutoDL has no built-in scheduler → use the bundled `scripts/run_queue.sh.template`
(resumable queue iterator, `start_index` for resume) driving `scripts/run_one.sh.template` per cell.
**Never overwrite a script a running bash is mid-execution** (bash reads by byte-offset → re-executes
blocks; version the filename) — universal physics, see `references/run-remote/gotchas_universal.md`.

**Monitoring.** A session-bound watcher dies with the session; for multi-hour runs deploy the four-layer
durable architecture (`references/run-remote/monitoring_patterns.md`). Detect "done" by a **log marker**
(`grep -q 'QUEUE DONE' master.log`), never by `pgrep` (the waiter's own cmdline matches the pattern and
loops forever). A cloud scheduler cannot reach the rented box (no SSH key in a cloud sandbox — secret
leak); the honest recurring check is the remote self-monitor + a session loop with the local key.

## 7. TOP GOTCHAS  (AutoDL-pinned; universal ones → `references/run-remote/gotchas_universal.md`)

**AD1 — external network call hangs / wandb shows 0 runs.** *Symptom:* `wandb.init` times out at
90/120/180 s, dashboard reads 0 runs while `wandb/run-*` exist locally; HF downloads stall; pip/git glacial.
*Root cause:* instances start with **no proxy**; direct egress to wandb/HF/PyPI/GitHub is unreliable or
blocked, and wandb-core's retry logic under a flaky link can roll back already-uploaded runs. *Fix:*
`source /etc/network_turbo` at the top of **every** shell/wrapper before any external call; recover an
empty cloud project with `for d in wandb/run-*; do timeout 120 wandb sync "$d"; done`.

**AD2 — HF download stalls even with hf-mirror + turbo.** *Symptom:* `from_pretrained` /
`snapshot_download` hangs or `ConnectTimeout` on big `.safetensors` shards. *Root cause:* (a) HF's Xet CAS
backend is not mirror-proxied; (b) `no_proxy` lists `modelscope.com` not `modelscope.cn` (domestic source
forced through international proxy = slower); (c) a curl test run without turbo measures the wrong path.
*Fix:* `export HF_HUB_DISABLE_XET=1` (or `pip uninstall -y hf_xet`) with `HF_ENDPOINT=https://hf-mirror.com`,
or pull from ModelScope to a plain dir + load via local-path override; wrap in a `timeout … && break`
resume loop. Detail → `references/run-remote/china-network.md`.

**AD3 — cross-region instances cannot share FS.** *Symptom:* two instances in different regions see
identical `/root/autodl-fs/` paths but files written from one are invisible to the other. *Root cause:* FS
quota is region-scoped; each region has its own physical mount. *Fix:* create the FS quota in the same
region as the instances; bridge regions via scp from a chosen primary; verify with a write-one / read-other
probe.

**AD4 — FS write fails "No space left" while `df -h` looks fine.** *Symptom:* `cp`/`mkdir` to
`/root/autodl-fs` fails though `df -h` shows ~34%; `df -i` shows `… 0 100%`. *Root cause:* the shared FS
enforces a **hard ~200K inode cap independent of bytes**; per-sample eval visualization (many tiny files)
exhausts it. *Fix:* monitor `df -i`; export a bounded, manifest-listed sample cohort as categorized atomic
files, never a default montage or full render dump; keep mutable render work under `active/`, not the FS.
Inventory exact cleanup candidates and obtain explicit deletion authorization—quarantine is not trash.

**AD5 — data disk full; the HF cache is the hidden hog.** *Symptom:* `/root/autodl-tmp` at 100% though
`active/` looks small, and "obvious junk" looks safe to delete. *Root cause:* `~/.cache/huggingface` is
symlinked onto the data disk, so the **HF model cache** (tens of GB) is the real hog. *Fix:*
audit `du -sh ~/.cache/huggingface/hub/models--* | sort -rh`; set `HF_HOME` to a chosen data-disk dir + keep
the metric/eval JSONs (tiny evidence); present exact deletion targets + sizes for explicit user
confirmation; offer "clean vs expand the disk".

**AD6 — base IS the env; a "never use base" rule blocks every remote command.** *Symptom:* a local "don't
run DL in conda base" guard fires on `ssh autodl 'python train.py'`, but `conda env list` shows nothing and
`/root/miniconda3/envs/` is empty; poll scripts calling `python3` exit 127. *Root cause:* the image installs
the whole DL stack into **base** — base IS the single-tenant project env (no `/envs/`), and the image often
ships only `python` (no `python3`). *Fix:* train with `/root/miniconda3/bin/python`; exempt remote-ssh +
instance base from the local guard (never `conda create --clone base`); in remote scripts use the explicit
interpreter or pure shell, never bare `python3`.

**AD7 — platform TensorBoard pinned to `/root/tf-logs`; events elsewhere invisible.** *Symptom:* the
events file is non-empty and `curl http://127.0.0.1:6007/` returns 200, but the AutoPanel TB tile shows
zero runs; `/data/runs` returns `[]`. *Root cause:* the image autostarts `tensorboard --logdir
/root/tf-logs` and the tile proxies that pid; `--logdir` is hard-pinned and not reconfigurable in-container.
*Fix:* write `SummaryWriter(log_dir="/root/tf-logs/<run>")`, or `ln -sfn <your-tb> /root/tf-logs/<run>`
(the pinned TB's `--reload=5` picks it up in ~5 s); verify with `curl … /data/runs`, not `ss`. (Also:
restart the TB server to evict STALE cached tags after deleting/renaming runs.) The cross-platform "live panel silently empty" class (path/port/process mismatch on any platform) is the general form → `references/run-remote/gotchas_universal.md` U39.

**AD8 — wandb val-phase CPU memory spike to 30+ GB at epoch 1 end.** *Symptom:* at the end of epoch 1
(validation), cgroup memory jumps from ~8 GB to 30+ GB, sometimes wedging the instance. *Root cause:*
project trainers log per-sample distributions at `step==1` (e.g. LPIPS/VGG over ~2000 samples on CPU =
~30 GB activations). *Fix:* cap the val-time sample accumulator — `-o training.val_metric_sample_cap=256`
(project-specific knob; check the trainer for the equivalent). Distinct from a DataLoader-worker cgroup OOM
(universal gotcha).

**AD9 — project torch pin would DOWNGRADE the image's working build.** *Symptom:* the image ships e.g. a
new-arch-capable torch (sm_120); the project pins `torch<2.9`; a naive `pip install -r requirements.txt`
replaces it with a wheel lacking the arch's kernels → `no kernel image is available` at first forward.
*Root cause:* the image torch/CUDA build is matched to the rented GPU arch; the project pin is stale for it.
*Fix:* filter framework pins out of the remote install —
`grep -ivE '^(torch|torchvision|torchaudio)' requirements.txt > /root/req_remote.txt && pip install -r
/root/req_remote.txt` — keep the image build; smoke `torch.cuda.get_device_capability()` + a heavy import
before launch; disclose the off-band torch version with results.

### 7.x Console boot / clone / import (measured 2026-08-31 … 2026-09-09 on real nodes; sunk from a project memory 2026-09-15)

- **"Boot failed" is usually not your mistake.** The dialog 「该主机空闲GPU不足 / 主机GPU空闲数量 0 卡」 means the *host* is fully booked by other tenants. Two exits: **克隆实例** (the platform places the clone on a host with free GPUs; same region only; the source instance is untouched), or the 「无卡模式开机」 link inside that same dialog when you only need the disk (rendering, packaging, exports).
- **The clone dialog ticks the system disk only.** The project lives on the data disk, so tick 数据盘 by hand before confirming (the resulting URL carries `copy_data_disk=1`); a clone without it boots into an empty workspace.
- **Run scripts with `PYTHONPATH=<project root>`.** An editable install's `.pth` may point at a stale copy of the repo; `python -c "import src"` from the project root passes (cwd is `sys.path[0]`), while `python scripts/x.py` puts `scripts/` first and `import src.*` resolves to the stale copy → ImportError. Test under the exact condition the job runs under, not a friendlier one.

### 7.y Console API, Jupyter channel, transfers (sunk from a project ops memory 2026-09-24)

- **Drive the console through its API, not screenshots.** In the logged-in console tab, the page's own
  token (localStorage `token`, sent as the `Authorization` header; never print or store it) authorizes
  `POST /api/v1/instance` (list: status, `ssh_port`) and `POST /api/v1/instance/power_on` /
  `power_off` with `instance_uuid`. Take the SSH port from the list, not from the instance id. A no-GPU
  boot did not start through the API in four request shapes; use the row's 「无卡模式开机」 instead.
- **Never click a menu item by remembered coordinates.** The last entry of 「更多」 is 「释放实例」, which
  destroys the instance and its data disk (a near miss on 2026-09-06: the red confirmation does not
  close on Escape). Find entries by their text on a fresh read of the page.
- **When SSH is down, use the Jupyter channel from a light `/jupyter/tree` page** (the Lab page stalls
  under streaming terminal output): files through the contents API (`PUT /jupyter/api/contents/<path>`
  with the `_xsrf` cookie in `X-XSRFToken`; read back with `cache:"no-store"` plus a timestamp, or a
  cached GET looks like a failed write), Python through a kernel channel, a shell through
  `wss://…/jupyter/terminals/websocket/<n>`. A PTY line longer than 4096 bytes is silently corrupted:
  send payloads in chunks of at most about 2.4 KB.
- **Measure the line before a big pull.** Cross-border links degrade at random within a day (single
  streams from 0.26 to 5.5 MB/s; six or more parallel streams get throttled to zero; a connection
  dies after about 10 minutes or 1.5 GB). Run a 75-second speed probe: at 3 MB/s or more, pull now in
  Range segments of about 455 MB, check each segment's size, restart a failed segment from scratch
  (no `-C -`), and trust only the SHA-256 of the joined file; under 1 MB/s, shut the node down and
  wait, since idle billing costs more than a cold start. A `~/.curlrc` breaker such as 1 MB/s for
  20 s is for one stream only; with parallel streams it kills every stream in turn.
- **"Full size" is not "done".** Two writers racing on one path interleave into a full-size corrupt
  file; `pkill -f <parent>` misses a child such as `bash fetch.sh`, so kill by the real process name;
  `ps` in a PTY cuts command lines at about 80 columns, so do not count live downloads by grepping
  it. A disk at 100% looks like a network failure: `df` first.
- **macOS `/usr/bin/rsync` is openrsync** and rejects GNU options such as `--info=stats2`; use
  Homebrew's `rsync` on the Mac side.
- **Close out what you start.** The boot notice names the shutdown condition and who shuts down; a
  node waiting on the user is shut down first; "shutting down soon" is either done now or backed by a
  watcher whose first hop has been read.

## 8. SCRIPT OVERRIDES

The AutoDL mount binding. Set `<project>` and `<run-id>` from the run contract before parameterizing any
wrapper; they are placeholders, not universal path literals:

```sh
PROJECT_ID=<project>
RUN_ID=<run-id>
PROJECT_ROOT=/root/autodl-tmp/$PROJECT_ID
CACHE_ROOT=$PROJECT_ROOT/cache
ACTIVE_ROOT=$PROJECT_ROOT/active
EXPORT_ROOT=$PROJECT_ROOT/export
PARTIAL_ROOT=$EXPORT_ROOT/.partial
QUARANTINE_ROOT=$PROJECT_ROOT/quarantine
DATA_DIR=$ACTIVE_ROOT/$RUN_ID          # legacy wrapper base; creates only this run's mutable state
DURABLE_DIR=                           # do not let run_one copy a partial checkpoint tree into exports
PROXY_HOOK='source /etc/network_turbo 2>/dev/null || true'   # MANDATORY before any external call (AD1)
CRED_FILE=/root/.wandb_key            # per-instance ONLY — the FS security classifier blocks wandb keys
SCRATCH='latest.pth'                  # mutable resume anchor; active only, never export it
HF_HOME=$CACHE_ROOT/huggingface       # regenerable cache stays in the exact project layout (AD5)
HF_ENDPOINT=https://hf-mirror.com     # + HF_HUB_DISABLE_XET=1 (AD2)
DETACH=tmux                           # nohup fallback when tmux is absent (§6)
PY=/root/miniconda3/bin/python        # base IS the env — explicit interpreter, never bare python3 (AD6)
TB_LOGDIR=/root/tf-logs               # platform TB is pinned here (AD7)
```

**Credential push (AD-specific).** The FS security classifier blocks files matching wandb-key patterns —
put the key at the **per-instance** `/root/.wandb_key`, never on `/root/autodl-fs`. Stream exactly one
credential block via stdin so the secret never appears in a command; the wrapper reads it
into `WANDB_API_KEY` before launch. Secrets-via-stdin pattern → `references/run-remote/ssh_transport.md`.

**Closed-export handoff.** The bundled `run_one.sh` has a legacy `final_ckpts/` copy path; leave
`DURABLE_DIR` empty while computing. After evaluation, assemble the canonical capsule under
`$PARTIAL_ROOT/$RUN_ID`, require `run.json` + `best.pth`, allow only a frozen optional `last.pth`, exclude
`latest.pth`, and require canonical `config.yaml`, `train.csv`, and
`test/<test-id>/{metrics.json,results.parquet,vis/<condition-id>/<task-native-role>/<sample-id>.png}` paths.
Reject any declared software test whose vis tree does not cover all declared conditions × task-native roles × K
fixed samples. Validate, then atomically rename it to `$EXPORT_ROOT/$RUN_ID`. A failed candidate moves to
`$QUARANTINE_ROOT`; it never overwrites an existing export. Do not add `COMPLETE.json` or `MANIFEST.json`.
For any shared-FS, local, or Hugging Face replica, invoke `mirror-research-artifacts` on the closed export;
its external frozen manifest carries the exact file roster/bytes/hashes—never duplicate that inventory in
`run.json`. Never whole-sync `$ACTIVE_ROOT`. Until a verified export/pull exists, the active copy remains source-of-truth
and 关机—not 释放—is the conservative park action.

If the job emits real capture/hardware results, do not add them to `$EXPORT_ROOT/$RUN_ID`. Either hand their
capture/decode/model-run bindings to `research-artifact-hygiene` or build, validate and atomically close the
weight-free capsule at `$PARTIAL_ROOT/hardware/<hardware-run-id>` →
`$EXPORT_ROOT/hardware/<hardware-run-id>`; its mandatory vis has full conditions × roles × K coverage.
