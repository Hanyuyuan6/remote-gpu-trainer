# Evals — does the skill route to the right answer?

A skill is only as good as an agent's ability to *find and apply* the right entry under a real problem.
[`cases.jsonl`](cases.jsonl) holds realistic scenarios across all three phases (remote operations on every
platform family, the training-debug layer, verification, and closeout). Two tiers test them.

## Tier 1 — structural reachability (CI, no API key)

```bash
python evals/run_evals.py        # exits non-zero if any case regresses
```

For each scenario it asserts the answer is **present, at the documented location, with its entry ids and
keywords intact**: every `expect_files` exists, every `expect_ids` is still a `### <ID>` header there, every
`expect_grep` term is still in the text, and every `reject_each_grep` term is absent from its
`reject_each_files`. It then runs [`test_instruction_surface.py`](test_instruction_surface.py), which caps
`SKILL.md` at 16 KB / 180 lines and pins the load-bearing sentences of the entrypoint and the monitoring,
custody, and control-economy references. This is a **drift guard**: it catches a renamed or removed entry, a
moved section, a deleted file, or a fact rewritten away from its key term. It proves neither that an agent
*navigates* there (Tier 2) nor that a platform fact is true on a live box (see the README's Verification
status). The GitHub workflow runs it together with `scripts/test_reconcile.py` and the advisory
`scripts/check_staleness.py`.

## Tier 2 — agentic navigation

Give a **fresh agent** the skill and one scenario's `prompt`, let it navigate **from SKILL.md only**
(following the documented routing, not blind grep), and grade whether it reaches a correct, specific answer
covering the case's `must_cover` points within ~2 hops. Each case records its last such run in `agentic`; the
collected runs are in [`RESULTS.md`](RESULTS.md). To re-run with any agent or harness: load the skill, paste a
case `prompt`, and grade against `expect_files` / `expect_ids` / `must_cover`.

## Adding a case

Append one JSON object per line to `cases.jsonl`:

```json
{"id": "kebab-id", "prompt": "the user's situation, verbatim-ish",
 "expect_files": ["references/training/<file>.md"], "expect_ids": ["O7"],
 "expect_grep": ["lr finder"], "must_cover": "the key points a correct answer must hit",
 "agentic": "PASS/FAIL (date): the navigation path observed"}
```

Use `expect_ids` for the catalogs with `### O7 / DP1 / M17 …` headers and `expect_grep` for section-structured
files such as profiles. Then run `python evals/run_evals.py`.
