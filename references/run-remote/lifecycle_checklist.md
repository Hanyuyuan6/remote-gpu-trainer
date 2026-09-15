# Lifecycle Checklist — the 6-phase runbook as a per-platform checklist

Purpose: a platform-parameterized, copy-pasteable checkbox runbook for one remote-GPU job, Phase 0
(environment audit) through Phase 5 (aggregate + verify + teardown). Substrate is delegated to **your
platform profile** (`profiles/<platform>.md`, 8-section schema in `profiles/_schema.md`) — this file never
hardcodes a mount, verb, or proxy. Each phase ends in the runnable check from `SKILL.md`.

`grep -in <keyword> references/run-remote/lifecycle_checklist.md` to jump.

## Table of contents
- Phase −1 — one-time setup (skip if reused)
- Phase 0 — environment audit
- Phase 1 — SSH + credentials
- Phase 2 — wrapper + CPU-smoke gate
- Phase 3 — detached launch
- Phase 4 — durable monitoring
- Phase 5 — aggregate + verify + teardown
- Cost-saving teardown table
- Failure handling (inline, any phase)

> **How to use:** pick the profile FIRST (`SKILL.md` → "Pick your platform profile"). Wherever a step
> says *profile data mount* / *profile durable mount* / *profile meter-stop verb* / *profile detach
> primitive*, read the literal value out of that profile's STORAGE / TEARDOWN / DAEMON sections. Skip any
> phase already done. Universal gotchas referenced by id live in `references/run-remote/gotchas_universal.md` — not
> restated here.

---

## Phase −1 — One-time setup *(skip if reused from a past project)*

- [ ] **First contact — surface the profile's "Surface to the user" block** to the user: the platform's non-obvious **conveniences** (one-click SSH-key registration, GPU-availability notifications, built-in panels) and its **danger clocks** (auto-release/auto-delete timers, stop-still-bills, low-balance purge). Don't assume they know — the danger clocks cost data or money (principle #10).
- [ ] Local SSH keypair exists (`~/.ssh/id_ed25519`); public key registered with the platform.
- [ ] `~/.ssh/config` alias per instance, with keepalive (`ServerAliveInterval`/`ServerAliveCountMax`) — see `references/run-remote/ssh_transport.md`.
- [ ] Durable storage provisioned per profile (shared FS / network volume / persistent disk), sized for
  manifest-bound datasets + closed exports + transfer-trust records. Mutable checkpoints are budgeted on
  the profile data mount, not multiplied into the shared archive.
- [ ] Reusable image/snapshot saved with the project's env + code, IF the profile supports it (saves repeated cold-build time × N instances).
- [ ] `.gitattributes` sets `*.sh text eol=lf` so Windows-authored scripts don't ship CRLF (gotcha U26).

> **verify:** `ssh <alias> 'echo reachable'` returns `reachable` and the durable mount appears in the profile's survival matrix.

---

## Phase 0 — Environment audit

- [ ] Bind the run root from the platform profile. AutoDL is exact:
  `/root/autodl-tmp/<project>/{cache,active,export/.partial,export/<run-id>,quarantine}`. Confirm that
  `export/.partial` and `export` are on the same filesystem so closeout can use atomic rename
  (`references/run-remote/artifact-layout.md`).
- [ ] Read the profile's STORAGE survival-matrix: know which tier survives *stop* vs *destroy* (principle #4). Write checkpoints to the tier that survives the intended *profile meter-stop verb*.
- [ ] Read the profile's region/DC-lock: if a shared/network volume is region-scoped, confirm all instances share that region BEFORE launch.
- [ ] Measure live, do not assume: `df -h && df -i <profile data mount>` (inodes die before bytes — principle #5), cgroup `cat /sys/fs/cgroup/memory.max`, `nvidia-smi`.
- [ ] `du -sh` the real space hogs on the actual mount (symlinked caches hide — principle #5), not the dir assumed.
- [ ] Pre-compute the checkpoint disk budget: `ckpt_size × N + scratch`; confirm it fits the *profile data mount* cap.
- [ ] Pre-compute the export inode budget: required top-level/test files plus
  `Σ_test min(100, N_test) × conditions × applicable task roles` visualization PNGs.
  Shared storage must not receive cache, the whole active tree, epoch-checkpoint piles, full tracker state,
  or general log trees.

> **verify:** `nvidia-smi` shows the expected GPU and `df -i <profile data mount>` is not near 100%.

---

## Phase 1 — SSH + credentials

- [ ] Set the SSH alias/env per the profile's NETWORK section; note the SSH flavor (a proxied/basic SSH may not `scp`/`rsync` — direct-TCP required; ports may change on restart).
- [ ] Use the prebuilt image/base AS the env — do NOT `conda create` on a rental (throwaway-instance exception: the image IS the env).
- [ ] Push secrets via **stdin, never onto a shared/durable FS** (a shared FS is multi-project) — pattern in `references/run-remote/ssh_transport.md`. Reference creds by env-var NAME / file path, never inline a key.
- [ ] If the profile sits behind the GFW, wire the China-mirror endpoint now (`references/run-remote/china-network.md`); validate the speed test on the SAME route the real transfer uses (principle #7).

> **verify:** `ssh <alias> 'python -c "import torch;print(torch.cuda.is_available())"'` prints `True`.

---

## Phase 2 — Wrapper + CPU-smoke gate

- [ ] Mint one unique `<run-id>`. Bind source/config/dataset/split identities and hashes into the run
  contract before launch; never use an unnamed checkout, a cache path, or floating data directory as
  scientific identity.
- [ ] Build an idempotent `run_one` / `run_queue` from `scripts/` (`run_one.sh.template`,
  `run_queue.sh.template`), parameterized from the profile. Its mutable output must resolve inside
  `active/<run-id>`; cache resolves to the profile's `cache/`. A legacy `DURABLE_DIR/final_ckpts` copy is
  staging, not a closed export, and must never target `export/<run-id>`.
- [ ] Wrappers are resumable: load-latest-on-startup unconditionally so the identical launch command resumes, not restarts (principle #8).
- [ ] Bound checkpoint retention to the selection best + resume anchor (`save_top_k <= 3` by default).
- [ ] Build the per-cell queue/config files with one isolated write path per cell (no shared mutable output — parallel ablation needs this; `references/run-remote/parallel_ablation.md`).
- [ ] **Run the cheap CPU smoke LOCALLY, BEFORE renting** — 1–2 batches, logger disabled, tiny shapes; it kills import/config/shape/scale bugs for ~free (principle #2). Smoke *content* → **references/verifying/methodology.md** (REQUIRED).

> **verify:** smoke exits 0 on 2 batches with the logger disabled, no Traceback.

---

## Phase 3 — Detached launch

- [ ] Launch via the *profile detach primitive* (tmux / `sbatch` / k8s Job / commit) — survives an SSH drop; confirm whether it also survives an instance restart (profile DAEMON section).
- [ ] Push code/data with a resumable transfer (`rsync --partial` or `timeout`+resume loop — principle #7),
  verify them against the bound source/data identities, then launch. Never edit a script under a live
  run—version filenames (principle #6).
- [ ] Probe briefly: log head + process alive + no traceback, then **hand control back**. Never a blocking foreground `sleep` (foreground Bash hard-caps at 600 s on Claude Code; other hosts have their own turn limit — `monitoring_patterns.md` §7).

> **verify:** within 60 s, the detach session is alive and the first log line shows the expected step/epoch.

---

## Phase 4 — Durable monitoring

- [ ] For anything over ~1–2 h, deploy the **four-layer architecture** (`references/run-remote/monitoring_patterns.md`): on-box self-completion chain + session patrol loop + event sentinels + recovery handbook. A session-bound watcher alone dies with the session (principle #3).
- [ ] Use `run_in_background` (no duration cap, notifies on exit; a Claude Code primitive — other hosts map per `monitoring_patterns.md` §7) for long waits; never foreground-poll. NEVER an unquoted `|` inside a poll-regex — it reads stdin and hangs forever.
- [ ] Watch `df -i` trend (not just `df -h`), cgroup memory %, new FINISHED/ERROR/Traceback markers, and fast-finish (< ~50% expected duration → probable failure).
- [ ] Reconcile each watcher against the job's REAL process/artifact (`tmux ls`/`squeue`/`pgrep` + output `mtime`) — a watcher's own state is a claim, not ground truth (principle #3). Tear a watcher down when its job is superseded.
- [ ] Classify each failure → its fixed remediation (see Failure handling below); **never blind-retry**.

> **verify:** the patrol reports a status line even when nothing changed (proves it's alive, not silently dead).

---

## Phase 5 — Aggregate + verify + teardown

- [ ] Build the complete candidate under `export/.partial/<run-id>`. Require `run.json`, `config.yaml`,
  `train.csv`, `best.pth`, and for every declared test
  `test/<test-id>/{metrics.json,results.parquet,vis/}`; allow only a frozen optional `last.pth`. For every
  declared software test, require complete declared conditions × task-native roles × K coverage
  at `test/<test-id>/vis/<condition-id>/<task-native-role>/<sample-id>.png`, where
  K = `min(100, N_test)`. Do not add `latest.pth`, redundant
  `COMPLETE.json`/`MANIFEST.json` status sentinels, dataset bytes, top-level `config/`/`results/`/`vis/`,
  caches, general logs, full tracker state, or a default montage.
- [ ] Bind each versioned per-test-set `selection_id` and its one manifest path/hash in `run.json`. Preserve
  schema-2 `all`/`fixed_model_blind` under `_trust/selections/`. For schema 3, accept a safe project-relative
  manifest only when it binds MNIST test K=512 clean float32, the exact ranking model/config/checkpoint, and
  the complete unrounded reconstruction-PSNR source hash/population; enforce descending PSNR, sample-ID tie
  order, K=`min(100,N_test)`, and one ordered roster across all methods, conditions, and three tasks. Keep
  full-test metrics full-population, restrict the ranked roster to qualitative examples, and give no-GT
  tests a separate explicit non-PSNR roster. Do not embed a second manifest or legacy visualization index.
- [ ] Never place real capture/hardware results inside software `export/<run-id>`. If this compute produced
  hardware output, hand capture/decode/model-run bindings to `research-artifact-hygiene` or build an
  independent `export/.partial/hardware/<hardware-run-id>` capsule containing `run.json` plus mandatory
  `test/<test-id>/{metrics.json,results.parquet,vis/...}`. Its `run.json` references capture/decode/model-run
  identities and `best.pth` hash; it contains no copied weights. The linked model run must have the same task.
  Ground-truth-available tests use full-test metrics and complete task roles. Tests with explicit
  `ground_truth_status=unavailable_no_machine_readable_gt` pair it with
  `metric_applicability=not_applicable`, finite-forward rows, and prediction-only roles; they never fabricate
  ground truth or accuracy/AP/IoU. Validate and atomically rename the capsule to
  `export/hardware/<hardware-run-id>` with complete applicable conditions × roles × K vis coverage.
- [ ] Do not repack an established project-native `checkpoints/<legacy-id>` tree merely to pass this phase.
  Route it to `supervise-research-closeout` for read-only legacy acceptance, and apply this export contract
  only to newly closed outputs.
- [ ] Validate the capsule contract owned by `research-artifact-hygiene`, including safe checkpoint load,
  exact canonical keys and required paths/visual coverage. `run.json` must contain no redundant full-file
  roster. After remote custody is verified, the author tree may retain a thin logical `runs/<run-id>` whose
  checkpoint/results records carry URI, SHA-256, bytes, provider, mutability, verification date, and
  independent consumer evidence; it need not retain a Mac `.pth`.
  If the destination does not exist, atomically rename `export/.partial/<run-id>` to `export/<run-id>` on
  the same filesystem.
- [ ] On any closeout failure, preserve the failed partial under `quarantine/<run-id>--<attempt-id>` with
  the failure reason. Never overwrite a sealed export and never delete the failed attempt without explicit
  authorization.
- [ ] For every shared-filesystem, local, Hugging Face, or other durable replica, stop here and invoke the
  generic `mirror-research-artifacts` skill on validated `export/<run-id>`. It owns destination/privacy
  checks, the external frozen manifest and live exact-roster/byte/hash validation, transfer,
  remote/readback verification, and restore evidence. That manifest stays outside the canonical run. Never mirror
  `active/` as a whole or pass the project root, `cache/`, or `export/.partial/` as the source.
- [ ] Only when the declared consumer is local or the user requests a materialized local copy, build the pull manifest: write an explicit UTF-8 expected-roster file
  from the sealed `export/<run-id>` (one result path per line, never embedded in canonical `run.json`),
  then run `scripts/aggregate_to_fs.sh` with `RUN_ID` and `EXPECTED_ROSTER_FILE` — it checked-syncs every
  required file into the durable root and builds `PULL_MANIFEST.json`. A count alone is not completeness
  evidence, and the mirror workflow does NOT produce this manifest — its custody manifest is a separate,
  additional layer over the same sealed export.
- [ ] For that local-delivery branch, pull with `scripts/download_loop.sh` (or the manifest-bound transport selected above); it always lets
  rsync compare/resume and never skips a directory because it is merely large.
- [ ] Otherwise restore/read back from the canonical remote directly into an independent temporary consumer
  location, which may be another rented node. Verify every roster entry/byte/SHA-256 there, safely load the
  checkpoint, and recompute every reported metric from the full prediction population. Persist the compact
  consumer evidence in the thin logical record. `PULL_VERIFIED.json` is one local transport receipt and is
  not a universal custody requirement.
- [ ] Record disclosable run facts for the paper: CLI overrides, source/data/split identities, tracker
  summary URL, acceptance id, and custody status. A tracker URL is provenance, not the result bundle.
- [ ] ONLY THEN perform the *profile meter-stop verb*, AFTER explicit user approval of the specific cost-affecting action.

> **verify:** a closed `export/<run-id>` or thin logical run binds the canonical remote URI and provider
> mutability to exact bytes/SHA-256 plus independent consumer readback, safe load, and full-prediction metric
> recomputation *before* destructive teardown. A mirror/upload status alone is not a substitute.

> **Iron Law — teardown gate:** NO `stop` / `release` / `terminate` / `destroy` / file-delete until
> checkpoints match an explicit remote roster + SHA-256 manifest, have been restored/read back into an
> **independent temporary consumer and verified by safe load plus full-prediction metric recomputation**,
> AND the user has explicitly approved the
> cost-affecting action. "It looked done in the log" is not evidence (principle #3). On most platforms the
> meter-stopping verb is **irreversible** (deletes the disk) — confirmation matters *more*, not less. The
> general form may be reinforced by a separate verification-before-completion companion when installed;
> the bundled manifest gate remains mandatory and self-contained.

---

## Cost-saving teardown table

The verb that stops the meter, what each preserves, and irreversibility — bind the platform-specific verb
from the profile's TEARDOWN section. **The biggest portability trap: "stop" rarely stops the meter, and
the action that does is usually irreversible** (principle #4/#9).

| Action | Stops GPU meter? | What survives | Reversible? |
|---|---|---|---|
| **stop / 关机 (power-off)** | Sometimes — depends on profile (AutoDL: yes, keeps disk; RunPod/vast: still bills storage 1–2×) | Disk tier per profile survival-matrix | Yes — instance restartable |
| **release idle instance** | Yes | Only the durable/shared mount (data disk gone) | No — instance + container disk destroyed |
| **terminate** | Yes | Only a network/persistent volume, if one was mounted | **No — irreversible**, disk deleted |
| **destroy** | Yes | Nothing on the box | **No — irreversible**, total loss |
| **delete durable files (keep subscription)** | Storage trickle only | Subscription survives for new data | No — those files gone |
| **cancel durable storage subscription** | Storage cost only | Nothing | **No — irreversible**, all durable data lost |

**Default conservative plan:** stop/release the GPU instance first (immediate $ saving, low risk once
artifacts pass independent-consumer restore and semantic verification). Keep durable storage 1–3 months
until the paper is submitted. Cancel the durable subscription LAST, only after that verification and the
user's explicit approval.

---

## Failure handling *(inline, any phase)*

Categorize before reacting; retry the **identical** config — hand-patching one run destroys comparability
(principle #7; **references/verifying/methodology.md** owns is-it-a-bug-or-real).

- [ ] **Probabilistic** (epoch-1 stall, transient `wandb.init` blip, spot preemption): queue a retry with the SAME config, no safeguards. Resume works because of checkpoint-load (principle #8).
- [ ] **Disk pressure/full** (>=90%, below frozen floor, `iostream`, inode/full): stop new writers; audit the resolved mount and live writers; reclaim only allowlisted proven-regenerable task scratch with a receipt; mirror valuable portable outputs and restore/semantic-verify before cleanup eligibility; remeasure. If still short, report exact shortfall, expansion target and restart requirement. Never silently shrink the experiment or delete active/unknown/research-bearing paths (principle #9). Then retry once only when the root cause is closed.
- [ ] **Real bug** (CUDA OOM, code error, all-zero metric): stop, investigate code — do NOT retry blindly.

> Symptom → root cause → fix for each, plus the full catalog: `references/run-remote/gotchas_universal.md`
> (`grep -in <keyword> references/run-remote/gotchas_universal.md` to jump).
