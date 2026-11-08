# Pre-flight review before a paper experiment (about 30 minutes)

Run this before the real run whose numbers go into a paper. Five checks, about six minutes each, reusing the
project's own checks. Report what was not covered; passing is not proof of scientific correctness.

1. **Data boundaries.** Read the actual split lists; check independent scenes or objects and cross-split
   content hashes (not file names); trace what preprocessing fits and model selection read. Fail: a forbidden
   object crosses splits, identical content leaks, or the test set feeds fitting or selection.
2. **One real sample end to end.** Follow sample -> measurement -> noise -> normalisation -> label -> loss;
   check units and magnitudes against a traceable source. Fail: misalignment, a hidden ground truth, a photon
   budget with no basis, or physical noise added at the wrong point.
3. **It actually learns.** On a fixed small subset, confirm gradients reach and update the parameters meant to
   train, and compare with a known-good curve. Fail: a broken gradient, frozen parameters or a wrong branch. A
   short run that has not fit yet is undecided, not a pass.
4. **Scoring is right.** Self-test the metric on ground truth, run the applicable traditional or constant
   baseline, hand-check a tiny case, and recompute from predictions saved and reloaded. Fail: metric
   definition, sample count, units or the recomputation disagree.
5. **The command that will really run.** Read back the resolved config; walk the stage switches,
   save-and-reload and validation it will use; align each condition the paper promises; confirm the heavy stages run
   on the GPU at a measured throughput (`references/training/throughput-profiling.md`). Fail: a promised
   condition (for example noise-free) is missing, the real data is replaced or shrunk, an uncounted
   operator is reported as zero compute, or a heavy stage silently runs on the CPU.

If the project-audit skill is installed, record the five checks on the rented node as the run-through page that
project-audit `references/mapping-and-walkthrough.md` W3 describes, so the device and throughput on the page are real.
