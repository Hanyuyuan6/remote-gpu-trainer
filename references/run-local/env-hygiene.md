# Conda / venv hygiene on the LOCAL persistent machine — never train or install in `base`

The one rule this file enforces: **on a workstation you own and keep, a DL train/install command runs in a
named, project-pinned environment — never in conda `base`.** `base` is the interpreter that powers conda
itself; treating it as a project env is how a single `pip install` ABI-rots every other project on the box.
This file is self-contained — it states the rules, not a pointer to some external policy.

To jump: `grep -in '<keyword>' references/run-local/env-hygiene.md` (e.g. `base`, `enumerate`, `activate`,
`executable`, `rental`, `create`).

## Table of contents

- **The rule** — E1 why not `base` · E2 the 4-step gate before any real command
- **Doing it** — E3 enumerate envs · E4 pick the project env (or ask) · E5 confirm activation · E6 no env → create one
- **The exception** — E7 remote / ephemeral rentals: `base` is fine there
- **Pointers** — launch/detach → launch.md · the seed/determinism contract → ../verifying/methodology.md

---

## The rule

### E1 — Why `base` is off-limits on a machine you keep

**Symptom**: months in, `conda base` has accreted torch, a CUDA build, three frameworks' pinned deps, and a
new `pip install` for project B downgrades a library project A silently depended on — now both break, and
`conda` itself (which lives in `base`) is one bad solve away from being unusable.

**Root cause**: `base` is the environment conda *runs from*. Every package you add to it is shared by conda's
own tooling and by every project that "just used base." There is no isolation, so dependency conflicts are
global and there is no clean rollback — you cannot delete and recreate `base` the way you can a project env.

**Fix**: keep `base` pristine (conda + a launcher, nothing project-specific). Every project gets its **own**
named env. This is a hard rule **only on the persistent local box** — the throwaway-rental exception is E7.

### E2 — The gate: four steps before any train / install / inference command

Before running anything that **mutates state** — `pip install` / `conda install`, a training launch, an
inference/eval job, a data-processing job that imports the framework — pass this gate **in order**:

| # | Step | Command | Pass condition |
|---|---|---|---|
| 1 | **Enumerate** the envs that exist | `conda env list` | you can see the candidates (E3) |
| 2 | **Pick** the project env — or ask | match by project name / framework stack (E4) | exactly one env chosen, not `base` |
| 3 | **Confirm** you are actually in it | `python -c "import sys; print(sys.executable)"` | path is under the chosen env, not `base` (E5) |
| 4 | **Run** the real command | `pip install …` / `python train.py …` | only after 1–3 |

Read-only probes are **exempt** — a `python -c "import torch; print(torch.__version__)"`, a `pip list`, a
`nvidia-smi` mutate nothing, so they do not need the env decision. The gate exists for commands that
**install or compute**, not for inspection.

> If step 2 is ambiguous (several plausible envs, or none obviously the project's), **ask the human which
> env** — do not silently fall back to `base`. Falling back to `base` is the exact failure this file exists
> to prevent.

---

## Doing it

### E3 — Enumerate: list every env first (`conda env list`)

**Symptom**: you assume an env name and `conda activate proj` errors `EnvironmentNameNotFound`, or worse,
you run in whatever was already active (often `base`) without checking.

**Root cause**: the active env at shell start is whatever the user's profile left active — frequently `base`.
Guessing the env name skips the one cheap check that tells you what actually exists.

**Fix**: list them, then choose from the list:
```bash
conda env list          # '*' marks the currently-active env
# # conda environments:
# #
# base                  *  /home/u/miniconda3            <- pristine; do NOT train here
# myproj                   /home/u/miniconda3/envs/myproj
# other-proj               /home/u/miniconda3/envs/other-proj
```
The `*` on `base` is the warning sign: you are *in* base right now and must switch before the real command.
(`venv`/`virtualenv` users: the analog is `ls .venv*/` and checking `$VIRTUAL_ENV`.)

### E4 — Pick the project env (and when to ask instead)

**Symptom**: two envs look plausible (`myproj` and `myproj-cu121`), or none clearly belongs to this project,
and a wrong pick installs into the wrong place or trains against the wrong CUDA build.

**Root cause**: env naming is a human convention, not something the tool resolves for you. The right env is
identified by **matching signals**, not by picking the first hit.

**Fix**: pick the env whose identity matches the project — in priority order:
1. **Name match** — an env named after the repo / project (`myproj`, `<repo>-env`, `<repo>-cu121`).
2. **Stack match** — the env carrying the PyTorch/CUDA (or JAX/TF) build the project's `requirements.txt` /
   `environment.yml` pins (`conda list -n <env> torch`).
3. **A project-shipped spec** — if the repo has `environment.yml` / `requirements.txt`, the env created from
   *that* is authoritative (and if it doesn't exist yet, E6).

If after these signals the choice is still ambiguous — **ask the human**. A wrong env is a costly, sometimes
hard-to-undo mistake (polluted env, wrong-CUDA build, silent downgrade); asking is cheap. Never resolve the
ambiguity by defaulting to `base`.

### E5 — Confirm activation BEFORE the real command (`sys.executable`)

**Symptom**: `conda activate myproj` printed nothing alarming, but the training run imports the wrong torch /
can't find a dep / writes packages into `base` — because activation didn't actually take (a non-interactive
shell without `conda init`, a stale shell, a typo'd name that silently no-op'd).

**Root cause**: `conda activate` can fail to switch the *active interpreter* in a fresh / non-interactive /
unsourced shell, leaving you in `base` while you believe you're in the project env. The prompt label is not
proof.

**Fix**: verify the **interpreter path**, not the prompt, right before the real command:
```bash
conda activate myproj
python -c "import sys; print(sys.executable)"
# /home/u/miniconda3/envs/myproj/bin/python   <- under envs/myproj  �→ proceed
# /home/u/miniconda3/bin/python               <- this is BASE       ✗ stop, re-activate
```
The path must sit under `…/envs/<the-env-you-chose>/`. If it points at the conda root (`…/miniconda3/bin/`),
you are in `base` — do **not** run the install/train; fix activation first (`conda init <shell>` once, open a
new shell, re-activate). `conda env list`'s `*` is a second confirmation. Only when the path is right do you
run step 4.

### E6 — No suitable env exists → create one, don't borrow `base`

**Symptom**: the project has no matching env, and the path of least resistance is "just use base."

**Root cause**: `base` is *there* and already has some packages, so it's tempting — but installing the
project's stack into it is exactly E1's failure mode.

**Fix**: create a dedicated env (propose the command and the Python version; confirm before running on a
machine you keep), then activate and re-run the E2 gate:
```bash
conda create -n myproj python=3.11      # pick the version the project needs
conda activate myproj
python -c "import sys; print(sys.executable)"   # E5 check
pip install -r requirements.txt          # or: conda env create -f environment.yml
```
If the repo ships `environment.yml`, prefer `conda env create -f environment.yml` (it names and pins the env
in one step). One env per project, pinned — never the shared `base`.

---

## The exception

### E7 — Remote / ephemeral RENTAL: running in `base` is fine (and usually correct)

**Symptom**: applying the "never base" rule on a throwaway cloud GPU box (AutoDL / RunPod / vast.ai / Lambda
/ a Slurm allocation / a fresh container) and burning metered time building a fresh env that the instance
will destroy at teardown anyway.

**Root cause**: the "never base" rule exists to prevent **ABI rot on a persistent machine you keep**. That
hazard does not exist on an instance that is **destroyed after use** — there is no "next project" on that box
to break. The image's prebuilt `base` (or the platform's default env) is the expected, lowest-friction place
to run, and it already has a matched CUDA/PyTorch stack.

**Fix**: on a remote / ephemeral / rented instance, **use the prebuilt `base` (or the image's default env)** —
do **not** `conda create` a fresh env unless the project ships its own `environment.yml` / `requirements.txt`
that genuinely warrants one. The decision flips on a single axis:

| Machine | `base` for train/install? | Why |
|---|---|---|
| **Local persistent box** (your workstation) | **No** — named project env (E1–E6) | ABI rot is permanent; conda lives in base |
| **Remote / ephemeral rental** (cloud GPU, Slurm node, fresh container) | **Yes** — the prebuilt base/default IS the env | box is destroyed at teardown; no rot to accrue |

The rest of the discipline (resource awareness, artifact/checkpoint handling, stating the seed) still applies
on a rental — only the *env-isolation* requirement is relaxed, because the isolation a fresh env buys is
already provided by the instance's disposability.

---

## Pointers — handled elsewhere, do not restate

- **Launching & detaching** the run once the env is confirmed → `references/run-local/launch.md`.
- **Single-node multi-GPU** (`torchrun`/`accelerate` env contract) → `references/run-local/multi-gpu.md`.
- **Stating the seed / determinism** the run itself must record (no env manager does it for you) →
  `references/verifying/methodology.md`.
- **Per-platform env contract on a rental** (what the prebuilt base ships, "the image IS the env") → the
  matching `profiles/<platform>.md`.
