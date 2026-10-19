# remote-gpu-trainer

[![evals](https://github.com/Hanyuyuan6/remote-gpu-trainer/actions/workflows/evals.yml/badge.svg)](https://github.com/Hanyuyuan6/remote-gpu-trainer/actions/workflows/evals.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Train on rented GPUs with your coding agent, without losing checkpoints or paying for idle machines.**

English · [中文简介](#中文简介)

Renting a GPU is the easy part. The costly surprises come later: a teardown that deletes the only copy of your checkpoints, a "stopped" machine that keeps billing, a job that looks busy but went wrong hours ago.

remote-gpu-trainer is an [Agent Skill](https://agentskills.io) for Claude Code, Codex and other coding agents. It lets your agent launch, monitor, resume and stop training on AutoDL, RunPod, vast.ai, Lambda, Paperspace, four other Chinese GPU clouds or any machine you can SSH into, and bring back checkpoints that are verified, not just copied.

## What it prevents

- **Losing checkpoints at teardown.** Releasing an AutoDL instance or terminating a RunPod Pod deletes its disk. The agent releases nothing until every file has been read back somewhere independent, hashed, loaded and re-scored, and you have said yes.
- **Paying for idle machines.** A stopped RunPod Pod bills its volume at twice the running rate, a stopped vast.ai instance bills its disk indefinitely, and `sudo shutdown` on Lambda leaves the meter running. The skill knows which action actually stops each meter.
- **Silent timers.** AutoDL releases a stopped instance after 15 days, data disk included, and RunPod and vast.ai can delete instances and storage when your balance runs out. The agent tells you about these the first time you use a platform.
- **Runs that look alive but are not learning.** A live process and a scrolling log are not health. Status reports compare the metric with a reference run at the same epoch and say how old the data is.
- **OOM, NaN, hangs and all-zero metrics.** OOM on step 2, NaN after a precision change, one crashed rank hanging the rest, a resume that restarts at epoch 0, a starved GPU, mAP stuck at zero while the loss falls: each is looked up by symptom, with its root cause and fix.
- **Numbers that are not real.** Before a result is reported, the agent states the seed, changes one variable at a time, checks for leakage and decides whether a gap is a bug, a real effect or noise.

## Install

**Let your agent do it.** Paste this into Claude Code, Codex, Cursor, Gemini CLI or GitHub Copilot:

```text
Install the remote-gpu-trainer agent skill. Read
https://raw.githubusercontent.com/Hanyuyuan6/remote-gpu-trainer/main/README.md
and follow its "For AI agents" section for this host. Then tell me
where you installed it and how you confirmed it loaded.
```

**Or clone it yourself.** For Claude Code:

```sh
git clone https://github.com/Hanyuyuan6/remote-gpu-trainer.git \
  ~/.claude/skills/remote-gpu-trainer
```

For Codex, Cursor, Gemini CLI or GitHub Copilot:

```sh
git clone https://github.com/Hanyuyuan6/remote-gpu-trainer.git \
  ~/.agents/skills/remote-gpu-trainer
```

To update, run `git -C ~/.claude/skills/remote-gpu-trainer pull --ff-only`, or the same with the `~/.agents/skills` path.

To check that it works, ask your agent: *"On AutoDL, what happens to my data disk if I shut the instance down, and what if I release it?"* The right answer: shutting down (关机) keeps the disk, but a stopped instance is released automatically after 15 days; releasing (释放) deletes the disk, and only `/root/autodl-fs` survives.

## Use it

Ask in plain language; the skill loads when the task matches. For example:

- "Train `configs/base.yaml` on my AutoDL instance, watch it, and pull the best checkpoint back when it finishes."
- "My RunPod spot Pod was interrupted at epoch 12. Resume it without losing progress."
- "Run these four ablations in parallel on four vast.ai instances."
- "The loss went NaN after I switched to bf16. Find out why."
- "I'm done on Lambda. Pull everything back, verify it, and tell me what `terminate` will delete."

To call it by name, type `/remote-gpu-trainer` in Claude Code or `$remote-gpu-trainer` in Codex.

## How it works

remote-gpu-trainer is a skill, not a CLI or an SDK: a `SKILL.md` your agent loads, plus reference docs and script templates it opens only when a step needs them. It works over SSH and, where a platform has one, its CLI or API; there is no service to host.

1. **Learn the platform first.** The agent reads one platform profile and tells you its conveniences and danger clocks, such as AutoDL's one-click SSH key setup and its 15-day release timer.
2. **Rehearse before renting.** The exact launch command runs locally on CPU with tiny data, through every stage switch, save, validation, test and export, so a broken script fails before the meter starts.
3. **Launch so it survives.** The job runs detached in a fresh run directory and checkpoints atomically to storage that outlives the instance. The same command resumes from the latest checkpoint.
4. **Monitor without a chat open.** The job completes on the box by itself. One bounded watcher per run wakes the agent only when something material changes.
5. **Verify before anything is destroyed.** Checkpoints are read back somewhere independent and checked by file list, size, SHA-256, safe load and recomputed metrics.
6. **Stop the meter, with your approval.** Shutdown and release are separate decisions, and the agent uses the action that actually stops billing on that platform.

The same discipline continues after the run. A green run is not a trustworthy result: the agent states seeds and determinism settings, changes one variable per comparison, probes leakage, fairness and variance, and treats a matching hash, a safe load and a fresh evaluation as three separate proofs. Each finished run closes into an immutable `export/<run-id>`, and `scripts/reconcile.py` flags any number in your paper, slides or README that has drifted from the evidence file.

## Platforms

| Platform | What stops the meter | Watch out for |
|---|---|---|
| AutoDL | Shut down (关机) stops GPU billing and keeps the disks | A stopped instance is released after 15 days; release (释放) deletes the data disk |
| RunPod | `terminate`; only a Network Volume survives | A stopped Pod bills its volume at 2× and may restart with zero GPUs |
| vast.ai | `destroy`, which deletes everything | A stopped instance bills its disk indefinitely; bandwidth bills in every state |
| Lambda | `terminate`, which wipes the local NVMe | No stop state; `sudo shutdown` keeps billing; NFS bills until deleted |
| Paperspace | Shutting down stops compute only | Storage, public IPs and snapshots bill until destroyed |
| Gpushare (恒源云), Matpool (矩池云), Featurize, LanRui (揽睿星舟) | Differs per platform | Gpushare releases a stopped instance after 10 days; LanRui bills the data disk while stopped |
| Any SSH machine | You, by hand | Nothing reclaims a forgotten machine; it bills around the clock |

The SSH profile also covers Slurm, Kubernetes and Colab or Kaggle as short differences, and a machine you own gets its own profile: no meter, same discipline. Each fact carries the date it was verified, and the agent re-checks the provider's current docs before any irreversible step.

## For AI agents

This section is for the coding agent doing the install. Work through the steps in order, then report back to the user. If you are a person, the prompt under [Install](#install) is all you need.

### 1. Find your skills directory

You usually know which host you are. If not, check the environment: Claude Code sets `CLAUDECODE=1` and Gemini CLI sets `GEMINI_CLI=1` in the shells they start. Otherwise, ask the user.

| Host | User skills directory | Source |
|---|---|---|
| Claude Code | `~/.claude/skills/` | [docs](https://code.claude.com/docs/en/skills) |
| OpenAI Codex | `~/.agents/skills/` | [docs](https://learn.chatgpt.com/docs/build-skills) |
| Cursor | `~/.agents/skills/` | [docs](https://cursor.com/docs/skills) |
| Gemini CLI | `~/.agents/skills/` | [docs](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md) |
| GitHub Copilot | `~/.agents/skills/` | [docs](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) |

Hosts that share a directory need only one copy. Cursor and VS Code also read `~/.claude/skills/`, so a Claude Code install covers them too. At user level, Claude Code reads only `~/.claude/skills/` and Codex only `~/.agents/skills/`, so if the user runs both, install into both. For any other host, use the user-level skills directory from its own docs. Cloud agents, such as Claude Code cloud sessions and Cursor Cloud Agents, do not read these local folders.

### 2. Install or update

Set `SKILLS_DIR` from the table, then run this block. It clones on the first run and fast-forwards on later runs, so it is safe to repeat.

```sh
SKILLS_DIR="$HOME/.agents/skills"
if [ -d "$SKILLS_DIR/remote-gpu-trainer/.git" ]; then
  git -C "$SKILLS_DIR/remote-gpu-trainer" pull --ff-only
else
  git clone https://github.com/Hanyuyuan6/remote-gpu-trainer.git \
    "$SKILLS_DIR/remote-gpu-trainer"
fi
```

- For Claude Code, set `SKILLS_DIR="$HOME/.claude/skills"`.
- Keep the folder name exactly `remote-gpu-trainer`. The Agent Skills spec requires it to match the skill's `name`.
- If a non-empty folder of that name exists but is not a git clone, `git clone` stops with an error. Ask the user before replacing that folder.
- Without git, download `https://github.com/Hanyuyuan6/remote-gpu-trainer/archive/refs/heads/main.tar.gz`, extract it into the skills directory, and rename `remote-gpu-trainer-main` to `remote-gpu-trainer`.
- Do not edit the installed copy. Project facts belong in the project's own instructions or memory, and a proposed fix goes to the user first, then upstream as a pull request.

### 3. Confirm it loaded

Run the bundled check. It needs only Python 3 and reads files without changing anything:

```sh
python3 "$HOME/.agents/skills/remote-gpu-trainer/evals/run_evals.py"
```

For Claude Code, use the `~/.claude/skills` path. The check should exit with status 0 and print `N/N cases reachable` with both numbers equal. Then confirm that the host itself sees the skill:

- **Claude Code**: run `/skills` and look for `remote-gpu-trainer`. If `~/.claude/skills/` did not exist when the session started, run `/reload-skills` first.
- **Codex**: type `$` or `/skills` and look for `remote-gpu-trainer`. If it is missing, restart Codex.
- **Gemini CLI**: run `/skills list`, and `/skills reload` if the skill is missing.
- **VS Code**: type `/skills` in chat to open the skills menu.
- **Cursor and other hosts**: look in the host's skill list, and restart the host if the skill is missing.

Tell the user the install path and the commit, from `git -C <install path> rev-parse --short HEAD`.

### 4. Read in this order

1. `SKILL.md`: the mission, the consequence levels and the resource router.
2. Exactly one `profiles/<platform>.md`, for the machine the user trains on. On first contact with that platform, tell the user what its "Surface to the user" block lists.
3. On a rented machine, `references/run-remote/principles.md`, then only the current phase of `references/run-remote/lifecycle_checklist.md`. On a machine the user owns, the matching file under `references/run-local/`.

Load nothing else up front. When a problem appears, follow the router in `SKILL.md` to one reference. When a node is rented, heavy compute, such as training, inference or `torchrun`, runs on that node; on the user's machine, run only the CPU rehearsal and static checks.

### 5. Hard rules

1. **Never destroy data before the checkpoints are safe.** Release, terminate, destroy, delete, overwrite, and any stop that wipes a disk (a RunPod container disk, for one) all wait until you have read the checkpoints back into an independent location (the user's machine or another node) and checked the exact file list, sizes and SHA-256, a safe load, and every reported metric recomputed. Then ask the user and wait for an explicit yes.
2. **Ask before spending money or doing anything irreversible.** That covers renting or resizing, any new paid scope and deleting data. Shutdown and release are separate decisions. Re-check the provider's current docs before a billing or teardown action.
3. **Keep secrets out of sight.** Never put a key or token in a command, a log, a shared disk, a cloud sandbox or this repository. Refer to it by its environment-variable name or file path, and move it to the box through stdin.
4. **Trust artifacts, not log lines.** A "done" line, a green spinner or a running process is not evidence. Check the files, hashes and metrics.

## What's inside

```text
remote-gpu-trainer/
├── SKILL.md          entry point and router
├── profiles/         one file per platform
├── references/
│   ├── run-remote/   lifecycle, monitoring, transfer, 44 gotchas
│   ├── run-local/    a machine you own
│   ├── training/     184 entries: OOM, NaN, hangs, resume, speed
│   ├── verifying/    is the number real?
│   └── delivering/   figures and tables from one evidence layer
├── scripts/          launch, health, transfer and verify tools
└── evals/            49 scenarios checked in CI
```

Every profile has the same eight sections, from launch and storage survival to teardown and billing, so a platform you have never used reads like one you know. Every money-affecting fact carries a `verified YYYY-MM` stamp.

A few of the scripts:

- `gpu_health.sh` catches a dead or throttling GPU (Xid 48 or 79, crushed clocks) before you pay for hours on it.
- `download_loop.sh` pulls directory by directory with `rsync --partial`, so a dropped connection resumes instead of starting over.
- `build_pull_manifest.py` and `verify_local.py` bind a pull to an exact file list with SHA-256, then load each checkpoint safely, with `weights_only=True` by default. `verify_local.py` needs PyTorch.
- `reconcile.py` reports numbers that have drifted from the evidence file, and `check_staleness.py` lists platform facts whose `verified` stamp is more than six months old.
- `run_one.sh.template` wraps a launch, with an optional dead-man timer that powers off a forgotten AutoDL instance.

### Companion skills

The skill is self-contained. Where a separate skill deepens a step, it names one: [superpowers](https://github.com/obra/superpowers) for verification before completion and parallel dispatch, and [Hugging Face skills](https://github.com/huggingface/skills) for the `hf` CLI and Trackio. It also mentions two of the author's skills that are not published here, `research-artifact-hygiene` and `mirror-research-artifacts`. All of them are optional: without one, the agent does the equivalent step with its own tools.

## Verification status

Only the AutoDL profile comes from the author's hands-on use. The other rental profiles are built from official documentation and community reports, plus gotchas that contributors hit on live runs. The skill re-checks the provider's current docs before any irreversible step, and `scripts/check_staleness.py` lists every `verified` stamp older than six months.

CI runs 49 structural scenarios on every push and pull request to `main`; each checks that the answer to a realistic problem is still where the skill says it is. On 2026-09-15 the maintainer also gave 15 of them to fresh Claude Opus 5 subagents, starting from `SKILL.md`: all 15 reached a correct, specific answer within two hops. These are author-run smoke tests, not a benchmark; the runs are in [`evals/RESULTS.md`](evals/RESULTS.md).

## When not to use it

- **Multi-cloud price-shopping and automatic spot failover.** Use SkyPilot or dstack for that, then this skill to make your code resume correctly, so their recovery lands on real progress.
- **Replacing your launcher.** It drives `torchrun`, `accelerate` and DeepSpeed; it does not replace them.
- **Long-term archives.** It closes each run into a validated export. Durable mirrors and restores belong to a separate tool.

## Contributing

Issues and pull requests are welcome, and outside contributions have been merged: [PR #6](https://github.com/Hanyuyuan6/remote-gpu-trainer/pull/6) by [@hector25](https://github.com/hector25) added teardown and billing gotchas for RunPod, vast.ai and Lambda. The issue templates cover bugs, new gotchas, new platform profiles and platform-fact corrections.

A new gotcha needs a known root cause, a reproduction or a clearly mechanistic explanation, and a reason other users would hit it too. Write it as symptom → root cause → fix, with a source; the full bar is in [`references/self-improvement.md`](references/self-improvement.md). Add a scenario to [`evals/cases.jsonl`](evals/cases.jsonl) and run `python3 evals/run_evals.py` before you open the pull request. Keep every example generic: no real project names, hostnames, IPs, ports or keys.

## Security

Report vulnerabilities privately through **Security → Advisories → Report a vulnerability** on this repository, not in a public issue, and never include a live secret. Details are in [SECURITY.md](https://github.com/Hanyuyuan6/remote-gpu-trainer/blob/main/SECURITY.md).

## Disclaimer

remote-gpu-trainer is an independent community project. It is not affiliated with, endorsed by or sponsored by AutoDL, RunPod, vast.ai, Lambda, Paperspace, DigitalOcean or any other platform named here; product names are used only to identify them. Platform facts were correct on their `verified` date, and platforms change prices, billing actions and limits, so check the current official docs before you rely on a billing or teardown fact. The software is provided as is, under the MIT License, without warranty.

## 中文简介

remote-gpu-trainer 是一个 Agent Skill：让 Claude Code、Codex 等编程 agent 在租用的 GPU 上启动、监控、续训和停止训练，并把校验过的 checkpoint 取回本地或另一台节点。支持 AutoDL、恒源云、矩池云、Featurize、揽睿星舟、RunPod、vast.ai、Lambda、Paperspace，以及任何能 SSH 登录的机器。

它主要解决这些问题：

- **释放 = 删数据**：释放实例会连数据盘一起删除，没拉回的 checkpoint 就没了。释放前，agent 会把 checkpoint 读回到独立位置，核对文件清单、大小和 SHA-256，加载并重算指标，再等你确认。
- **关机 ≠ 安全停放**：AutoDL 关机 15 天后自动释放，只有 `/root/autodl-fs` 能保留；RunPod、vast.ai 停机后磁盘照样计费。
- **看着在跑，其实没在学**：进程还在、日志在刷，不等于训练正常；状态汇报会对照参考 run 在同一 epoch 的指标。
- **OOM、NaN、卡死、指标全零**：按症状查原因和修法，训练排障条目共 184 条。
- **国内网络**：AutoDL 的 `network_turbo` 学术加速、HF 镜像、Xet 大文件下载不走镜像等问题，都有现成的处理步骤。

安装：Claude Code 克隆到 `~/.claude/skills/remote-gpu-trainer`；Codex、Cursor、Gemini CLI、GitHub Copilot 克隆到 `~/.agents/skills/remote-gpu-trainer`。命令见 [Install](#install)；也可以把那段提示词贴给你的 agent，让它按 [For AI agents](#for-ai-agents) 一节自己装好。

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Yuyuan Han.

## Citing

A link back is plenty. For a formal reference:

```bibtex
@software{han_remote_gpu_trainer_2026,
  author = {Han, Yuyuan},
  title  = {remote-gpu-trainer: an Agent Skill for the DL experiment lifecycle on owned or rented GPUs},
  year   = {2026},
  url    = {https://github.com/Hanyuyuan6/remote-gpu-trainer}
}
```
