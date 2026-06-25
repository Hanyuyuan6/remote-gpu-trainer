# Delivering — the delivery gate (P8: a DISCLOSURE gate, not a blocking gate)

**P8 made operational** (`references/delivering/principles.md`): before any number or figure ships, it
should be **verified · in `EVIDENCE.json` · regenerable · cross-document-reconciled**, and its
**split / leakage status disclosed *alongside the number itself*.** The word that defines this gate is
**disclosure**: it **surfaces** the status of every shipping number; it does **not** refuse to let the user
ship. This is the **audit → disclose, never enforce** stance turned into a per-number checklist.

To jump: `grep -n '^## ' references/delivering/delivery-gate.md`.

---

## The line that separates this from a CI gate

A CI gate **fails the build** and stops you. **This gate does not.** Its output is not pass/fail-and-halt;
its output is, for every shipping number, a small status record that **travels with the number** so the
claim carries its own caveat. If a number comes from a leaked split, a single seed, or can't currently be
re-derived, the gate's job is to **say so, attached to that number** — never to silently pass it off as
clean, and never to take the ship/don't-ship decision away from the user.

This is exactly `references/verifying/methodology.md`'s **"disclose it, or don't claim it."** A fully-
informed user may legitimately:
- **claim it *with* the disclosure** (e.g. ship the single-seed ablation, stating it's single-seed), or
- **not claim it** (drop the number until it's stronger), or
- **fix it first** (add seeds, re-split, re-derive) — their call.

What the gate forecloses is the *fourth* option: **claiming it while hiding the caveat.** That — and only
that — is off the table. The skill is an honest auditor, not a police checkpoint.

> Why disclosure and not enforcement: the research judgment (how many seeds, which split, whether a thin
> result is worth shipping caveated) belongs to the **user** (sovereignty,
> `references/delivering/principles.md`). Enforcing would substitute the skill's judgment for the user's.
> Disclosing preserves the user's authority while removing the one failure mode nobody wants — a wrong
> number shipping *silently* under their name.

---

## The five checks (per shipping number / figure)

Run these before a number or figure goes into a paper, table, slide, README, or rebuttal. Each produces a
**disclosure**, not a block.

### 1. Verified — `references/verifying/methodology.md` ran on it
The number survived the relevant gates: classified bug/effect/noise (§1), fair comparison if it's a
comparison (§5), leakage-probed if too-good (§4), a green smoke isn't trusted as correct (§6), and it has
**variance** and a stated **direction** (§9). A surprising number that *hasn't* been through verifying is a
**hypothesis, not a result** — disclose that it's unverified, or verify it first.
→ *Disclosure if it fails:* "this number has not passed the verifying gate (e.g. single-seed, no control-
diff)" — surfaced with the number.

### 2. In `EVIDENCE.json` — the number has a claim, an anchor, and a repo line
The number maps to a claim in `EVIDENCE.json` (`references/delivering/evidence-manifest-schema.md`) with a
**paper anchor** (where it's asserted) and a **repo-implementation `file:line`** (where the claimed
mechanism lives). A number that ships but isn't in `EVIDENCE.json` is a number with **no recorded evidence
basis** — the gate flags an unmapped number.
→ *Disclosure if it fails:* "this number is not in the evidence map" — i.e. it's an orphan claim; map it or
disclose the gap.

### 3. Regenerable — it can be re-derived, and it's *generated* not transcribed
The number is **generated** from its `results.json` (a `\input` table / macro, **P2**), and the whole chain
re-derives from a clean clone in one command (**P5** when flipped on,
`references/delivering/principles.md`). A number you cannot re-derive from released code + config + data is
**not yet a result** (`references/verifying/methodology.md` principle 6 / §13) — and a *hand-typed* number
is one that will silently go stale.
→ *Disclosure if it fails:* "this number is transcribed / not currently regenerable from the artifact" —
surfaced so a reader knows it isn't mechanically backed.

### 4. Cross-document reconciled — every copy matches the source
`scripts/reconcile.py` greps the whole corpus (paper, thesis, slides, rebuttal, README, CSV) and confirms
**every occurrence** of this number / method name / dataset size matches `EVIDENCE.json`'s authoritative
value (`references/verifying/methodology.md` §14). **A correction is not done until it lands in all of
them** — and a *corrected* number is the one most likely still stale somewhere. Under **P2** there is no
second copy to drift; reconcile audits the documents P2 doesn't yet generate (and any legacy hand-typed
mention). **Run it before each submission:** `scripts/reconcile.py` (pointed at `EVIDENCE.json` + the repo
root) prints every `file:line` whose number disagrees with the authoritative value, and exits non-zero
while any drift remains — a drift report you act on, not a blocker.
→ *Disclosure if it fails:* "this number disagrees across documents (paper says X, slides say Y)" — the
drift is surfaced and must be reconciled to the source before it can ship without the flag.

### 5. Split / leakage status disclosed alongside the number
The number's **split** (`val` / `test`), its **n**, its **variance**, and the **audit result** of the
split it came from ride *with* it. The split is a first-class audited object
(`references/delivering/data-architecture.md`): if the audit found no disjoint val split, a train/test leak,
or the **test split touched during selection** (`references/verifying/methodology.md` §4), that finding is
**surfaced with any conclusion that depends on the number.** Per the audit→disclose stance, this is
**mandatory disclosure** — and it is **not** enforcement: the gate does not block the number, it attaches
the status.
→ *Disclosure (always, not only on failure):* every shipping number states its split + n + variance; a
known leakage / selection-on-test / no-disjoint-val finding is attached verbatim.

---

## What "disclosed alongside" looks like in practice

The disclosure is not a footnote in a separate audit document the reader never opens — it **travels with the
number** at every appearance:

- in `EVIDENCE.json`, the claim's `disclosure` field (`references/delivering/evidence-manifest-schema.md`);
- in a figure's `<fig>.provenance` sidecar `disclosure` field (`references/delivering/figures.md`);
- and, where the number is *shown*, in the caption / table note / slide — e.g. "31.42 dB (test, n=100, ±0.08
  over 3 seeds)" or "30.81 dB (test, **single seed — no variance band**)".

Because the number is **generated** (**P2**), the disclosure can be generated with it — the macro that emits
the value can emit its `(split, n, variance)` annotation from the same `results.json` row, so the caveat
cannot be detached from the number by an edit.

---

## The gate as a checklist (copy-run before shipping)

For each number / figure about to ship:

```
[ ] 1. VERIFIED         — passed references/verifying/methodology.md (bug/effect/noise, fair-compare,
                          leakage, smoke≠correct, variance + direction).      else → disclose "unverified".
[ ] 2. IN EVIDENCE.json — has a claim + paper_anchor + repo_implementation file:line.
                                                                              else → disclose "unmapped".
[ ] 3. REGENERABLE      — GENERATED (P2) from results.json, re-derives in one command (P5).
                                                                              else → disclose "transcribed / not regenerable".
[ ] 4. RECONCILED       — scripts/reconcile.py: every copy across paper/thesis/slides/README/CSV matches
                          EVIDENCE.json's value (§14).                        else → disclose "cross-doc drift".
[ ] 5. SPLIT/LEAK STATUS— split + n + variance ride with the number; split audit result (§4) attached.
                                                                              ALWAYS disclosed; a finding
                                                                              (no disjoint val / leak /
                                                                              selection-on-test) is attached, not hidden.

Outcome: a DISCLOSURE record per number — NOT a block. The user, fully informed, decides:
         claim-with-disclosure · don't-claim · fix-first. The skill never hides a known problem,
         and never overrides the user's ship decision.
```

---

## Boundary — what this gate does and doesn't own

- **Owns:** assembling the per-number disclosure (the five checks) and ensuring it travels with the number;
  driving `scripts/reconcile.py` (the §14 cross-document audit lives *here*, executed once, not duplicated).
- **Does NOT own:** the *verifying methodology itself* (that's `references/verifying/methodology.md` — this
  gate *invokes* it, doesn't restate it); the *figure pixel check* (that's
  `references/delivering/figures.md` P7 — this gate *requires* it ran); choosing the *science* (seeds,
  samples, whether to ship a thin result — that's the **user's**, sovereignty).
- **Does NOT do:** block, fail-the-build, or refuse to render/export. It **discloses.** A gate that halts the
  user has stopped being an auditor and started being a policeman — which is precisely the stance
  `references/delivering/principles.md` rules out.
