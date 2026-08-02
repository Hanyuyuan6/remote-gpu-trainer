#!/usr/bin/env bash
# Aggregate completed ablation results from the per-instance data disk to durable storage.
# Idempotent (cp -f overwrites, so a retry result overwrites an epoch-1-failure snapshot).
#
# Override DATA_DIR / DURABLE_DIR per your platform profile (profiles/<platform>.md §8). Defaults = AutoDL.
#
# Usage: bash aggregate_to_fs.sh   (run on each instance after its queue completes)
#
# This is a SAFETY NET — run_one.sh already auto-syncs per ablation. Use it when an auto-sync failed,
# an older run_one lacked it, or as a final pass before releasing an instance.
set -uo pipefail

DATA_DIR="${DATA_DIR:-/root/autodl-tmp}"
DURABLE_DIR="${DURABLE_DIR:-/root/autodl-fs}"
PY="${PY:-python}"
RUN_ID="${RUN_ID:-}"
EXPECTED_ROSTER_FILE="${EXPECTED_ROSTER_FILE:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$RUN_ID" ]; then
    echo "ERROR: RUN_ID is required so the final pull can be bound to an immutable sweep/delivery id." >&2
    exit 1
fi
if [ -z "$EXPECTED_ROSTER_FILE" ] || [ ! -f "$EXPECTED_ROSTER_FILE" ]; then
    echo "ERROR: EXPECTED_ROSTER_FILE is required and must contain one expected result directory per line." >&2
    exit 1
fi

FS_BASE="$DURABLE_DIR/final_ckpts"
LOCAL_CKPT_BASE="$DATA_DIR/checkpoints"
LOCAL_LOG_BASE="$DATA_DIR/runs/logs"

mkdir -p "$FS_BASE"

count=0
fail=0
for d in "$LOCAL_CKPT_BASE"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d")

    # An incomplete cell is not a successful aggregation candidate.
    if [ ! -f "$d/best_metrics.json" ] || [ ! -f "$d/best.pth" ]; then
        echo "FAIL $name (missing best.pth or best_metrics.json)" >&2
        fail=$((fail+1))
        continue
    fi

    FS_DIR="$FS_BASE/$name"
    # GATE on the copy result — never echo OK unconditionally. A full / inode-exhausted durable FS
    # makes mkdir/cp fail silently; an unconditional "OK" would lie (references/run-remote/gotchas_universal.md,
    # silent-sync; principle #3). Verify best.pth landed before counting it.
    if mkdir -p "$FS_DIR" \
        && cp -f "$d/best.pth" "$FS_DIR/" \
        && cp -f "$d/best_metrics.json" "$FS_DIR/" \
        && [ -f "$FS_DIR/best.pth" ] \
        && [ -f "$FS_DIR/best_metrics.json" ]; then
        if [ -d "$d/protocol" ] && ! cp -rf "$d/protocol" "$FS_DIR/"; then
            echo "!! FAIL $name — protocol copy failed." >&2
            fail=$((fail+1))
            continue
        fi
        if [ -f "$LOCAL_LOG_BASE/$name.log" ] && ! cp -f "$LOCAL_LOG_BASE/$name.log" "$FS_DIR/"; then
            echo "!! FAIL $name — log copy failed." >&2
            fail=$((fail+1))
            continue
        fi
        echo "OK $name"
        count=$((count+1))
    else
        echo "!! FAIL $name — durable copy did not land (check 'df -i $DURABLE_DIR'). Data-disk copy is source-of-truth."
        fail=$((fail+1))
    fi
done

echo
echo "=== Aggregated $count ablations to $FS_BASE ($fail failed) ==="
echo "Total dirs on durable FS now: $(find "$FS_BASE" -mindepth 1 -maxdepth 1 -type d | wc -l)"
df -h "$FS_BASE" | tail -1
df -i "$FS_BASE" | tail -1
[ "$count" -gt 0 ] || { echo "ERROR: zero complete ablations were aggregated; refusing success." >&2; exit 1; }
[ "$fail" -eq 0 ] || exit 1

echo "Building exact remote roster/hash manifest for RUN_ID=$RUN_ID ..."
"$PY" "$SCRIPT_DIR/build_pull_manifest.py" "$FS_BASE" \
    --run-id "$RUN_ID" --expected-roster "$EXPECTED_ROSTER_FILE"
