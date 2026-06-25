#!/usr/bin/env python3
"""Cross-document number-drift checker -- the single owner of cross-document reconciliation (references/verifying/methodology.md section 14).

The whole delivering principle (references/delivering/principles.md, P1/P2/P8): every number in a paper / thesis /
slide / README / CSV is a deterministic function of the immutable evidence layer. EVIDENCE.json
holds the AUTHORITATIVE scalar for each reported metric. The moment a human re-types a number
into prose, it can drift. This script greps the presentation-layer docs and reports every
reported value that diverges from its authoritative source in EVIDENCE.json, so the cross-doc
reconciliation in the delivery gate (P8) is mechanical, not a proofreading ritual.

It REPORTS drift; it does not edit anything. Pure stdlib, no network, no third-party deps.

How a reported number is associated with an authoritative metric
----------------------------------------------------------------
For each authoritative claim, an "anchor" is the metric's human keyword -- the last
alphanumeric token of the metric key (e.g. metric `psnr_set5` -> anchor `psnr`), plus any
explicit `aliases` listed on the claim. Within a configurable character window after an anchor
occurrence in the doc, every numeric token is compared to the authoritative value. A token that
differs (beyond a small float tolerance) is a drift. A token equal to the authoritative value is
clean. This is deliberately a lightweight heuristic, not a parser: it catches the common
transcription drift (31.42 mis-typed as 31.50 / 31.41) without trying to understand arbitrary
prose. Tune sensitivity with --window; raise/lower equality strictness with --rtol / --atol.

EVIDENCE.json shape (only the fields this tool needs; see evidence-manifest-schema):
    {
      "claims": [
        {
          "id": "C1",
          "aliases": ["PSNR/Set5"],          # optional, claim-level
          "evidence": [
            {"metric": "psnr_set5", "value": 31.42, ...},   # the AUTHORITATIVE scalar lives here
            {"metric": "psnr_set5", "value": 31.42, ...}     # (multiple supporting rows allowed)
          ]
        }
      ]
    }
The authoritative scalar is NESTED under claims[].evidence[].value (not claims[].value); the metric
keyword that anchors the doc scan is read from each evidence row's `metric` (falling back to the
claim's `metric` if present), plus any `aliases` on the evidence row OR the claim.

Usage:
    python reconcile.py --evidence EVIDENCE.json --docs paper.md thesis.md README.md results.csv
    python reconcile.py --evidence EVIDENCE.json --docs paper.md --window 80 --rtol 1e-3

Exit code:
    0 = no drift found across all docs.
    1 = at least one drift, or a usage / load error (missing EVIDENCE.json, no scalar claims,
        a doc path that does not exist).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# A numeric token: optional sign, digits with optional decimal part, optional exponent,
# or a bare ".5"-style fraction. Percent sign (if present) is captured so we can strip it.
_NUM = re.compile(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?%?")


@dataclass
class Drift:
    """One reported value that diverges from its authoritative source."""

    doc: str          # document path where the divergent number was found
    line: int         # 1-based line number
    metric: str       # authoritative metric key from EVIDENCE.json
    authoritative: float
    reported: float
    context: str      # the snippet of text the number was read from (trimmed)


@dataclass
class _Claim:
    metric: str
    value: float
    anchors: list[str]   # lowercased keywords that, when seen, gate a nearby-number check


def _load_claims(evidence_path: Path) -> list[_Claim]:
    """Read EVIDENCE.json and return the scalar evidence rows (metric + authoritative value + anchors).

    The authoritative scalar is NESTED: each claim carries an `evidence[]` list, and each evidence
    row holds the `metric` + `value` that documents must match (see evidence-manifest-schema). We
    iterate every claim's `evidence[]` and emit one `_Claim` per scalar evidence row. The anchor
    metric/aliases are taken from the evidence row, falling back to the parent claim for either
    field. Evidence rows without a numeric `value` (or whose metric is non-scalar) are skipped;
    this pass is only about reported scalars. Method-name reconciliation is a separate concern.
    """
    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    raw_claims = data.get("claims", [])
    if not isinstance(raw_claims, list):
        raise ValueError("EVIDENCE.json: 'claims' must be a list")

    out: list[_Claim] = []
    for c in raw_claims:
        if not isinstance(c, dict):
            continue
        evidence = c.get("evidence", [])
        if not isinstance(evidence, list):
            continue
        # claim-level fallbacks for the doc anchor (metric/aliases may live on the claim)
        claim_metric = c.get("metric")
        claim_aliases = c.get("aliases", []) or []
        for ev in evidence:
            if not isinstance(ev, dict):
                continue
            metric = ev.get("metric", claim_metric)
            value = ev.get("value")
            if metric is None or value is None:
                continue
            try:
                fval = float(value)
            except (TypeError, ValueError):
                continue  # value is non-numeric (e.g. a method name) -> not a scalar claim

            anchors: list[str] = []
            # The anchor is the MEASURE keyword -- the leading alphabetic token of the metric key
            # (`psnr_set5` -> `psnr`). We deliberately do NOT anchor on a trailing dataset qualifier
            # (`set5`): a dataset name legitimately appears in clean prose, and a digit inside it
            # ("Set5") is not a reported metric value. Anchoring on the measure keeps the gate tight.
            parts = [p for p in re.split(r"[^0-9A-Za-z]+", str(metric)) if p]
            # prefer the first token that contains a letter (skip a leading numeric, unusual but safe)
            lead = next((p for p in parts if any(ch.isalpha() for ch in p)), parts[0] if parts else str(metric))
            anchors.append(lead.lower())
            # explicit aliases on the evidence row AND/OR the parent claim (kept whole, lowercased)
            for a in list(ev.get("aliases", []) or []) + list(claim_aliases):
                anchors.append(str(a).lower())
            # de-dup, preserve order
            seen: set[str] = set()
            anchors = [a for a in anchors if not (a in seen or seen.add(a))]
            out.append(_Claim(metric=str(metric), value=fval, anchors=anchors))
    return out


def _parse_num(tok: str) -> float | None:
    """Parse a numeric token, treating a trailing '%' as a literal-character match (not /100).

    We compare the *written* number to the *written* authoritative value; converting percent
    would create false 'matches'. So '31.50%' parses to 31.50 here and only matches an
    authoritative 31.50.
    """
    t = tok[:-1] if tok.endswith("%") else tok
    try:
        return float(t)
    except ValueError:
        return None


def _values_equal(a: float, b: float, rtol: float, atol: float) -> bool:
    return math.isclose(a, b, rel_tol=rtol, abs_tol=atol)


def reconcile(
    evidence_path: str | Path,
    docs: list[str | Path],
    *,
    window: int = 60,
    rtol: float = 1e-9,
    atol: float = 0.0,
) -> list[Drift]:
    """Return every reported value in `docs` that diverges from EVIDENCE.json's authoritative value.

    For each scalar claim, scan each doc line; wherever an anchor keyword appears, inspect the
    numeric tokens within `window` characters after it. A number that does not equal the
    authoritative value (within rtol/atol) is recorded as a Drift. A number equal to it is clean.
    """
    evidence_path = Path(evidence_path)
    claims = _load_claims(evidence_path)
    drifts: list[Drift] = []

    for doc in docs:
        doc = Path(doc)
        text = doc.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            for claim in claims:
                for anchor in claim.anchors:
                    start = 0
                    while True:
                        idx = low.find(anchor, start)
                        if idx == -1:
                            break
                        start = idx + len(anchor)
                        seg = line[idx : idx + len(anchor) + window]
                        for m in _NUM.finditer(seg):
                            # Skip a number glued to a letter ("Set5", "v2", "H264"): it is part
                            # of an identifier/dataset name, not a reported metric value. A real
                            # value is preceded by whitespace or a separator (= : ( , ~), not [A-Za-z].
                            if m.start() > 0 and seg[m.start() - 1].isalpha():
                                continue
                            val = _parse_num(m.group(0))
                            if val is None:
                                continue
                            if not _values_equal(val, claim.value, rtol, atol):
                                drifts.append(
                                    Drift(
                                        doc=str(doc),
                                        line=lineno,
                                        metric=claim.metric,
                                        authoritative=claim.value,
                                        reported=val,
                                        context=seg.strip()[:120],
                                    )
                                )
    return drifts


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Report reported values that diverge from EVIDENCE.json's authoritative source.",
    )
    ap.add_argument("--evidence", required=True, help="path to EVIDENCE.json (project single source of truth)")
    ap.add_argument(
        "--docs",
        required=True,
        nargs="+",
        help="presentation-layer docs to scan (paper.md thesis.md slides.md README.md results.csv ...)",
    )
    ap.add_argument(
        "--window",
        type=int,
        default=60,
        help="chars after an anchor keyword to scan for the reported number (default: 60)",
    )
    ap.add_argument("--rtol", type=float, default=1e-9, help="relative tolerance for equality (default: 1e-9)")
    ap.add_argument("--atol", type=float, default=0.0, help="absolute tolerance for equality (default: 0.0)")
    a = ap.parse_args()

    evidence_path = Path(a.evidence)
    if not evidence_path.exists():
        print(f"ERROR: evidence file not found: {evidence_path}")
        return 1

    missing = [d for d in a.docs if not Path(d).exists()]
    if missing:
        for d in missing:
            print(f"ERROR: doc not found: {d}")
        return 1

    try:
        claims = _load_claims(evidence_path)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: could not read claims from {evidence_path}: {e}")
        return 1
    if not claims:
        print(f"ERROR: no scalar claims (metric + numeric value) found in {evidence_path} -- nothing to reconcile.")
        return 1

    drifts = reconcile(evidence_path, list(a.docs), window=a.window, rtol=a.rtol, atol=a.atol)

    print(f"Reconciled {len(a.docs)} doc(s) against {len(claims)} authoritative scalar(s) in {evidence_path}.")
    if not drifts:
        print("No drift: every reported value matches its authoritative source.")
        return 0

    print(f"\n{len(drifts)} DRIFT(S) -- reported value diverges from EVIDENCE.json authoritative value:")
    for d in drifts:
        print(
            f"  {d.doc}:{d.line}  metric '{d.metric}': reported {d.reported} != authoritative {d.authoritative}"
        )
        print(f"      context: {d.context}")
    print("\nFix at the source (regenerate the doc from the evidence layer), not by hand-editing the number.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
