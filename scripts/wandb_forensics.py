#!/usr/bin/env python3
"""wandb forensic + cleanup CLI — verify ablation results, not just read final numbers.

Run on whichever machine has the wandb key + network (often a remote GPU instance,
where the key is at /root/.wandb_key). Reads WANDB_API_KEY from env, else that file.

  python wandb_forensics.py list   --entity ENT --project PROJ [--metric best_mAP50]
  python wandb_forensics.py diff   --entity ENT --project PROJ --a NAME_A --b NAME_B
  python wandb_forensics.py curve  --entity ENT --project PROJ --run NAME_OR_ID --metric val/det/mAP50
  python wandb_forensics.py delete --entity ENT --project PROJ --run RUN_ID   # needs --yes

Two quoting traps when you paste a one-off variant of this over SSH (both bit us):
  1. f-strings cannot contain a backslash  -> build the format string outside the f-string.
  2. heredocs interpolate $ and `          -> always use  << 'PYEOF'  (single-quoted) so the
     remote shell ships the body verbatim. A bare << PYEOF mangles every $var and f-string.
Prefer scp-ing THIS file and calling it, rather than heredoc-ing python over SSH.
"""
from __future__ import annotations
import argparse, os, sys


def _api():
    import wandb
    if not os.environ.get("WANDB_API_KEY"):
        for p in ("/root/.wandb_key", os.path.expanduser("~/.wandb_key")):
            if os.path.exists(p):
                os.environ["WANDB_API_KEY"] = open(p).read().strip()
                break
    return wandb.Api()


def _runs(api, entity, project):
    return list(api.runs(f"{entity}/{project}"))


def _find(api, entity, project, name_or_id):
    """Resolve by exact run name (newest if duplicates) or by run id."""
    runs = _runs(api, entity, project)
    named = sorted([r for r in runs if r.name == name_or_id], key=lambda r: str(r.created_at))
    if named:
        return named[-1]
    for r in runs:
        if r.id == name_or_id:
            return r
    raise SystemExit(f"no run matching {name_or_id!r} in {entity}/{project}")


def cmd_list(api, a):
    runs = _runs(api, a.entity, a.project)
    runs.sort(key=lambda r: str(r.created_at))
    metric = a.metric
    print(f"{len(runs)} runs in {a.entity}/{a.project}")
    print(f"{'name':<48} {'state':<9} {'created':<20} {metric or 'metric'}")
    print("-" * 100)
    for r in runs:
        val = (r.summary.get(metric) if metric else None)
        if isinstance(val, float):
            val = round(val, 4)
        print(f"{(r.name or r.id)[:48]:<48} {r.state:<9} {str(r.created_at)[:19]:<20} {val}")


def _flat(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        else:
            out[key] = v
    return out


def cmd_diff(api, a):
    """Confirm the ONLY config delta between two runs is the intended ablation knob.
    A surprising metric with extra unexplained config deltas == likely a bug, not an effect."""
    ra, rb = _find(api, a.entity, a.project, a.a), _find(api, a.entity, a.project, a.b)
    ca, cb = _flat(ra.config), _flat(rb.config)
    keys = sorted(set(ca) | set(cb))
    print(f"A = {a.a} ({ra.id})   B = {a.b} ({rb.id})")
    print(f"{'':1} {'key':<52} {'A':<22} {'B':<22}")
    print("-" * 100)
    ndiff = 0
    for k in keys:
        va, vb = ca.get(k), cb.get(k)
        if va != vb:
            ndiff += 1
            print(f"* {k:<52} {str(va)[:21]:<22} {str(vb)[:21]:<22}")
    print(f"\n{ndiff} differing keys. Expect exactly ONE (the ablated knob). "
          f"More than one -> investigate before trusting the metric gap.")


def cmd_curve(api, a):
    """Read the trajectory, not the final number. Distinguishes a real (lower-saturating)
    ablation effect from training instability (early-peak then collapse / grad spike)."""
    r = _find(api, a.entity, a.project, a.run)
    rows = [d for d in r.scan_history(keys=["epoch", a.metric]) if d.get(a.metric) is not None]
    if not rows:
        raise SystemExit(f"no logged values for {a.metric!r} on {r.name} ({r.id})")
    best = max(rows, key=lambda d: d[a.metric])
    print(f"{r.name} ({r.id}, {r.state}) — {a.metric}: {len(rows)} eval points")
    print(f"  PEAK ep={best.get('epoch')}  {a.metric}={best[a.metric]:.4f}")
    print(f"  LAST ep={rows[-1].get('epoch')}  {a.metric}={rows[-1][a.metric]:.4f}")
    step = max(1, len(rows) // 20)
    for i in range(0, len(rows), step):
        d = rows[i]
        print(f"    ep={str(d.get('epoch')):>5}  {a.metric}={d[a.metric]:.4f}")


def cmd_delete(api, a):
    r = _find(api, a.entity, a.project, a.run)
    print(f"target: {r.name} ({r.id}) state={r.state} created={r.created_at}")
    if not a.yes:
        raise SystemExit("refusing to delete without --yes")
    r.delete(delete_artifacts=True)
    # deletion can lag server-side; confirm by re-listing
    still = [x for x in _runs(api, a.entity, a.project) if x.id == r.id]
    print("deleted" if not still else f"WARNING still present: {r.id} (retry / check UI)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("list", "diff", "curve", "delete"):
        s = sub.add_parser(name)
        s.add_argument("--entity", required=True)
        s.add_argument("--project", required=True)
        if name == "list":
            s.add_argument("--metric", default=None)
        if name == "diff":
            s.add_argument("--a", required=True); s.add_argument("--b", required=True)
        if name == "curve":
            s.add_argument("--run", required=True); s.add_argument("--metric", required=True)
        if name == "delete":
            s.add_argument("--run", required=True); s.add_argument("--yes", action="store_true")
    a = p.parse_args()
    api = _api()
    {"list": cmd_list, "diff": cmd_diff, "curve": cmd_curve, "delete": cmd_delete}[a.cmd](api, a)


if __name__ == "__main__":
    main()
