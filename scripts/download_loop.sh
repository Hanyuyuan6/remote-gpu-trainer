#!/usr/bin/env bash
# Per-dir resumable download loop — robust to mid-transfer connection drops.
#
# Each dir is pulled in its own session, so one network blip never loses the rest.
# Re-running always lets rsync compare and resume; size is never treated as proof
# of completeness. A single `scp -r` of a huge tree dies
# on any blip and does NOT resume — see references/run-remote/gotchas_universal.md (transfer
# resets). This uses rsync --partial, which resumes a half-pulled dir in place.
#
# Usage (override any var from the environment):
#   LOCAL_TARGET=/path/to/local/final_ckpts \
#   REMOTE_ALIAS=my-gpu-1 \
#   REMOTE_PATH=/durable/final_ckpts \
#     bash download_loop.sh
#
# The remote bundle MUST contain PULL_MANIFEST.json, created with
# build_pull_manifest.py after final aggregation. This script finishes by running
# verify_local.py; only its PULL_VERIFIED.json marker can satisfy the teardown gate.
set -uo pipefail

LOCAL_TARGET="${LOCAL_TARGET:-/path/to/local/final_ckpts}"
REMOTE_ALIAS="${REMOTE_ALIAS:-my-gpu-1}"
REMOTE_PATH="${REMOTE_PATH:-/root/autodl-fs/final_ckpts}"   # override from your profile (durable mount)
PY="${PY:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY_SCRIPT="${VERIFY_SCRIPT:-$SCRIPT_DIR/verify_local.py}"
MANIFEST_NAME="PULL_MANIFEST.json"

mkdir -p "$LOCAL_TARGET"
cd "$LOCAL_TARGET" || exit 1

echo "Fetching immutable pull manifest from $REMOTE_ALIAS:$REMOTE_PATH ..."
incoming="$LOCAL_TARGET/$MANIFEST_NAME.incoming"
if ! rsync -az --partial -e 'ssh -o ConnectTimeout=15 -o ServerAliveInterval=60 -o ServerAliveCountMax=120' \
    "$REMOTE_ALIAS:$REMOTE_PATH/$MANIFEST_NAME" "$incoming"; then
    echo "ERROR: remote manifest is missing or unreachable; run build_pull_manifest.py after final aggregation." >&2
    exit 1
fi
mv -f "$incoming" "$LOCAL_TARGET/$MANIFEST_NAME"

dirs_output=$("$PY" - "$LOCAL_TARGET/$MANIFEST_NAME" <<'PY'
import json, re, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
dirs = manifest.get("top_level_dirs")
if manifest.get("schema") != "remote-gpu-trainer/PULL/v1" or not isinstance(dirs, list):
    raise SystemExit("invalid pull manifest schema or top_level_dirs")
for name in dirs:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise SystemExit(f"unsafe result directory in manifest: {name!r}")
    print(name)
PY
)
parse_rc=$?
if [ "$parse_rc" -ne 0 ]; then
    echo "ERROR: local pull manifest failed validation." >&2
    exit 1
fi
if [ -z "$dirs_output" ]; then remote_dirs=(); else mapfile -t remote_dirs <<< "$dirs_output"; fi
n_total=${#remote_dirs[@]}
echo "Manifest declares $n_total remote dirs"
if [ "$n_total" -eq 0 ]; then
    echo "ERROR: manifest declares no result directories; refusing an empty teardown pull." >&2
    exit 1
fi

ok=0; fail=0
for d in "${remote_dirs[@]}"; do
    [ -n "$d" ] || continue
    echo "SYNCING $d (rsync verifies size/mtime and resumes partial files) ..."
    mkdir -p "$d"
    if rsync -az --partial -e 'ssh -o ConnectTimeout=15 -o ServerAliveInterval=60 -o ServerAliveCountMax=120' \
        "$REMOTE_ALIAS:$REMOTE_PATH/$d/" "$d/" ; then
        echo "OK $d"; ok=$((ok+1))
    else
        echo "FAIL $d"; fail=$((fail+1))
    fi
done

echo
echo "=== Transfer done ===  OK: $ok  FAIL: $fail  (of $n_total expected)"
echo "Local dirs now: $(find . -mindepth 1 -maxdepth 1 -type d | wc -l)"
[ "$fail" -eq 0 ] || { echo "Re-run to retry the failed dirs (resumable)."; exit 1; }

echo "Running exact-roster/hash/checkpoint verification ..."
"$PY" "$VERIFY_SCRIPT" "$LOCAL_TARGET" --manifest "$LOCAL_TARGET/$MANIFEST_NAME"
