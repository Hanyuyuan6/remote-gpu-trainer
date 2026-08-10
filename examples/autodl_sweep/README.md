# Worked example — a 3-cell ablation sweep on AutoDL

A complete, end-to-end run of the 6-phase lifecycle (SKILL.md) for the deepest profile
(`profiles/autodl.md`). Substitute your own project name, alias, and configs. Two instances run
their own queue file in parallel; this walkthrough ships `queue_1.txt` and shows one instance. **Read `profiles/autodl.md`
first** — it owns every path and verb used below.

The AutoDL `SCRIPT OVERRIDES` (profiles/autodl.md §8) that parameterize the templates:

```bash
export PROJECT_REPO_DIR=/root/myproj
export PROJECT_ROOT=/root/autodl-tmp/myproj
export DATA_DIR=$PROJECT_ROOT/active/paper-ablation-v1
export DURABLE_DIR=                       # legacy copy path disabled; close export explicitly
export PROXY_HOOK='source /etc/network_turbo'
export CRED_FILE=/root/.wandb_key
```

### Phase 0 — Environment audit
```bash
ssh autodl-1 'df -h /root/autodl-tmp /root/autodl-fs / && df -i /root/autodl-tmp/myproj && \
              { cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes; } | numfmt --to=iec 2>/dev/null; nvidia-smi'
bash scripts/gpu_health.sh 0     # run ON the box: Xid / throttle pre-flight (U22/U23)
```
Budget the disk: `ckpt_size × cells_in_queue + scratch`. **Verify:** `nvidia-smi` shows the expected
GPU; `df -i /root/autodl-tmp/myproj` is well under 100%.

### Phase 1 — SSH + credentials
```bash
# alias already in ~/.ssh/config (references/run-remote/ssh_transport.md). Push the wandb key via stdin,
# to the per-instance disk — NEVER the shared FS (U34, and AutoDL's classifier blocks it, AD-gotcha):
printf '%s\n' "$WANDB_KEY_FROM_ENV" | ssh autodl-1 'umask 077; cat > /root/.wandb_key && chmod 600 /root/.wandb_key'
```
**Verify:** `ssh autodl-1 'python -c "import torch;print(torch.cuda.is_available())"'` prints `True`.

### Phase 2 — Wrapper + CPU-smoke gate
```bash
# Parameterize the templates, drop the .template suffix, smoke locally on CPU BEFORE renting time:
cp scripts/run_one.sh.template run_one.sh && cp scripts/run_queue.sh.template run_queue.sh
python -m src.train -c configs/ablation/baseline.yaml --task reconstruction \
       --limit-batches 2 --epochs 1   # logger off; catches import/shape/scale bugs for free
```
**Verify:** the smoke exits 0 on 2 batches. (Smoke *content* → **REQUIRED:** `references/verifying/methodology.md`.)

### Phase 3 — Detached launch
```bash
# Deploy a versioned immutable wrapper with the source checkout; mutable output stays in active/<run-id>.
scp run_one.sh run_queue.sh examples/autodl_sweep/queue_1.txt autodl-1:/root/myproj/
ssh autodl-1 "RUN_ONE=/root/myproj/run_one.sh DATA_DIR=/root/autodl-tmp/myproj/active/paper-ablation-v1 \
  DURABLE_DIR= tmux new -d -s q1 'bash /root/myproj/run_queue.sh /root/myproj/queue_1.txt \
  2>&1 | tee /root/autodl-tmp/myproj/active/paper-ablation-v1/q1_master.log'"
```
**Verify within 60 s:** `ssh autodl-1 'tmux ls && tail -5 /root/autodl-tmp/myproj/active/paper-ablation-v1/q1_master.log'`
shows the session alive and a `STARTING baseline` line. Never overwrite the live wrapper (U2 / principle #6).

### Phase 4 — Durable monitoring
```bash
ssh autodl-1 'grep -hE "STARTING|FINISHED|QUEUE DONE|ERROR|Traceback" /root/autodl-tmp/myproj/active/paper-ablation-v1/q1_master.log | tail -8'
```
For a multi-hour sweep deploy the four-layer architecture (`references/run-remote/monitoring_patterns.md`): a remote
self-completion marker + a session patrol loop. Flag a FINISHED at <50% typical duration (probable
early-stop) and re-launch the **identical** config (principle #7), never a patched one. Don't blind-retry.

### Phase 5 — Aggregate + verify + teardown
Use the project's canonical closeout implementation to build
`/root/autodl-tmp/myproj/export/.partial/paper-ablation-v1`. Require `run.json`, `config.yaml`, `train.csv`,
`best.pth`, and `test/<test-id>/{metrics.json,results.parquet}`; allow a frozen optional `last.pth` and place
the required complete declared conditions × task-native roles × K visualization set only at
`test/<test-id>/vis/<condition-id>/<task-native-role>/<sample-id>.png`. This software capsule contains no
real-capture/hardware results. Bind the fixed
`_trust/selections/<selection-id>.json` path/hash in `run.json`; do not embed a legacy visualization index,
dataset bytes, or top-level config/results/vis directories. Reject every `latest.pth`. Validate full
isomorphism with local `runs/paper-ablation-v1`, then atomically rename to
`/root/autodl-tmp/myproj/export/paper-ablation-v1`; on failure move the partial to `quarantine/`.

If this run also produces hardware outputs, hand the capture/decode/model-run bindings to
`research-artifact-hygiene` or close a separate, weight-free
`export/hardware/<hardware-run-id>/{run.json,test/<test-id>/...}` capsule with mandatory full vis coverage.

Pull and independently verify that exact sealed directory before teardown. For an additional shared-FS or
Hugging Face replica, invoke `mirror-research-artifacts` on the sealed export—never sync `active/` as a whole.
Keep `run.json` limited to canonical scientific bindings; the generic mirror's external frozen manifest and
live validator carry the exact file roster, byte sizes and payload hashes.

**Verify:** the manifest-bound pull and local verifier end with `PULL VERIFIED` and write
`PULL_VERIFIED.json`; this proves the external frozen roster, every size/hash, and every checkpoint load.
**Iron Law:** only AFTER that marker exists
AND the user approves does teardown run — on AutoDL `关机` stops the meter and keeps the
disk (the reversible exception); `release` frees it irreversibly. Reconcile against the roster, not the
log (`references/run-remote/parallel_ablation.md` §6). Use a separate verification companion when installed;
otherwise the bundled manifest gate is authoritative.
