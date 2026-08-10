# SSH Transport — keys, keepalive, resumable copy, secrets-via-stdin

Platform-agnostic SSH + file-transfer substrate for every `ssh-rental` profile (AutoDL, RunPod,
vast.ai, Lambda, Paperspace, China, bare SSH). One-time config so subsequent commands are short and
password-less, plus the copy/secret patterns that survive flaky networks and short rentals. Concrete
hosts, ports, and credential locations are **profile facts** — this file owns the *mechanism*, the
profile (`profiles/<platform>.md` §1/§3/§8) owns the *values*.

To jump: `grep -in '<keyword>' references/run-remote/ssh_transport.md` (e.g. `keepalive`, `rsync`, `stdin`, `crlf`).

## Table of contents

1. Key generation
2. Push the public key to an instance
3. `~/.ssh/config` alias + keepalive tuning
4. Verify the alias
4A. Windows + Clash/Mihomo high-port decision ladder
5. Resumable copy — rsync vs scp, and WHY rsync
6. Bulk per-dir download loop
7. Move secrets via stdin — never inline a key, never on a durable FS
8. CRLF — `.sh` authored on Windows breaks on Linux
9. Two SSH flavors — proxied/basic SSH cannot `scp`
10. Transport gotchas (Symptom → Root cause → Fix)

---

## 1. Key generation

Skip if `~/.ssh/id_ed25519` already exists.

```bash
ssh-keygen -t ed25519 -C "<label>"
# Save path: Enter for the default ~/.ssh/id_ed25519
# Passphrase: optional (Enter for none, or set one + use ssh-agent)
```

`ed25519` is shorter and more secure than RSA; every rental platform accepts both. One local key is
reused across all instances — generate once, push the **public** half (§2) to each box. The private
half (`~/.ssh/id_ed25519`, no `.pub`) never leaves the local machine and **never** goes onto a rental,
a shared FS, or a cloud agent (a cloud scheduler runs in an isolated sandbox with no access to it — and
putting a private key there is a secret leak; see `references/run-remote/monitoring_patterns.md`).

## 2. Push the public key to an instance

Copy the connection string from the platform's web console / API; it has the shape
`ssh -p <PORT> root@connect.<region>.<provider>.com`. Push the public key once:

```bash
ssh-copy-id -p <PORT> root@connect.<region>.<provider>.com
# enter the platform-provided password ONCE
```

If `ssh-copy-id` is absent (common on Windows-native shells), append the key manually:

```bash
cat ~/.ssh/id_ed25519.pub          # copy the entire line
ssh -p <PORT> root@connect.<region>.<provider>.com
# on the remote:
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<paste the public key line>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

Test: re-running the `ssh …` line should connect **without** a password prompt.

## 3. `~/.ssh/config` alias + keepalive tuning

One block per instance turns `ssh -p <PORT> root@connect.<region>.<provider>.com` into `ssh <alias>`,
and folds in the keepalive options that keep long monitoring/transfer connections from dropping.

```ssh-config
Host proj-1
    HostName connect.<region>.<provider>.com
    Port <PORT>
    User root
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 120
    TCPKeepAlive yes
    # LogLevel VERBOSE   # uncomment to debug a refused/hung connection

Host proj-2
    HostName connect.<region>.<provider>.com
    Port <PORT>
    User root
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 120
```

**Naming**: `<project>-<index>` (e.g. `proj-1`, `proj-2`) reads cleanly in a fan-out loop; avoid bare
`gpu1`. **Why the three keepalive options**:

- `ServerAliveInterval 60` — send an application-layer heartbeat every 60 s, so a NAT/idle timeout on
  the path does not silently drop a parked connection (mid-`scp`, or an open monitor).
- `ServerAliveCountMax 120` — tolerate up to 120 missed heartbeats before declaring the link dead (≈2 h
  of network instability survived). Lower it (e.g. 3) for a *bounded* monitor that should self-kill on a
  blip rather than hang — see the short-connection poll in `references/run-remote/monitoring_patterns.md`.
- `TCPKeepAlive yes` — let the OS also emit TCP-layer keepalives, catching a peer that vanishes
  ungracefully.

Ports change when a profile re-issues an instance (`ssh-rental` boxes assign a new port on
re-creation) — update the `Port` line after each create/recreate, then re-run §4.

## 4. Verify the alias

```bash
for a in proj-1 proj-2 proj-3 proj-4; do
    echo "=== $a ==="
    ssh -o ConnectTimeout=10 "$a" "hostname; date"
done
```

Each should print a distinct hostname. Then the env probe (SKILL.md Phase 1):
`ssh <alias> 'python -c "import torch;print(torch.cuda.is_available())"'`.

## 4A. Windows + Clash/Mihomo high-port decision ladder

Use this branch when a Windows client reaches an AutoDL-style high SSH port while Clash/Mihomo is
running. Keep it per-process and parameterized: hostname, port, user, identity file, DoH resolver,
selected IP, Windows interface index, timeouts, fingerprints, receipt paths and session ID all come
from the current run contract. Never paste today's NIC, address, port or key into this skill or a
reusable script.

### Decision gate: OpenSSH direct first

1. Run **OpenSSH direct first** with a session-scoped known-hosts file, `StrictHostKeyChecking=yes`,
   bounded connect/banner timeouts and verbose output captured to an evidence file. Do not start with
   Paramiko merely because Clash/Mihomo is installed.
2. If direct OpenSSH succeeds, keep it. Do not introduce a second transport.
3. Authorize a **Paramiko fallback** only when the captured evidence class is exactly one of:
   `banner_timeout` (TCP connects but the SSH identification/banner never arrives), `fake_ip` (the
   system resolver result is shown to be a Clash/Mihomo fake-IP or disagrees with a hashed DoH answer),
   or `tun_interference` (read-only route/interface evidence identifies the TUN path).
4. Refuse fallback for `auth_failed`, `host_key_mismatch`, `connection_refused`, a generic connect
   timeout, or `other_error`. Those are credential, identity, service-state or unknown failures;
   changing the Python SSH library would hide the cause rather than fix it.
5. Once step 3 authorizes fallback, you **must not report** the host unreachable or a live refresh
   blocked until a **bounded fallback attempt or host identity gate** finishes. A host-key mismatch is
   `identity_gated` and remains fail-closed. If the bounded attempt fails for another reason, report only
   `transport_unavailable`: **transport failure proves only transport unavailability**, never that a
   remote run is completed, live, failed or stalled.

The deterministic decision gate is **offline only**:

```powershell
python scripts/plan_windows_ssh_transport.py --input <evidence.json> --output <plan.json>
```

It parses already-captured evidence and emits a plan. It performs no DNS query, socket connection,
SSH authentication, route edit, proxy edit or forward-test.

For an authorized fallback the plan emits a machine-readable `reporting_gate` with
`fallback_attempt_required=true`, `premature_transport_block_forbidden=true`, and
`remote_state_inference_allowed=false`. The terminal transport verdict requires a
`bounded fallback attempt or host identity gate`; generating the offline plan is not itself that attempt.

The input carries explicit `connect_seconds` and `banner_seconds` bounds. The planner recomputes the
canonical SHA-256 of the structured OpenSSH evidence and rejects a declared digest that does not match;
each fallback class also has its own minimum evidence shape. Secret-shaped fields are rejected. This proves
the plan is bound to the supplied offline record, not that the original observation was honestly captured;
retain the source capture separately when that distinction matters.

### DoH real IP without system mutation

Query a user-selected DNS-over-HTTPS endpoint outside this script, record the response bytes/hash and
select one IPv4 answer for the current session. Bind the evidence to the logical hostname, high port,
resolver URL and observation time. The selected address is a transport destination only; SSH host-key
identity remains bound to the logical host + port and the pinned fingerprint.

The resolver URL must use HTTPS. Store the normalized answer roster in the planner input, bind it by a
recomputed canonical SHA-256, and require the selected IPv4 address to be a member of that hashed roster.

Do not call `Set-DnsClientServerAddress`, add/delete routes, change WinHTTP or environment proxies,
disable TUN, or rewrite Clash/Mihomo configuration. This is a **no system route/DNS/proxy mutation**
contract. Read-only DNS, interface and route snapshots are evidence; they are not authorization to
alter the machine.

### One Windows socket, then Paramiko

When fallback is authorized, create one IPv4 socket, apply Windows `IP_UNICAST_IF` using the current
interface index, connect that socket to the DoH-selected IP and high port, and pass that **single
connected socket** to `paramiko.Transport`. Do not let Paramiko resolve the hostname or open a second
socket, because that would discard the interface binding and re-enter the fake-IP/TUN path.

Implementation shape (values remain parameters; this is not executed by the bundled planner):

```python
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(connect_timeout_s)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_UNICAST_IF,
                struct.pack("!I", interface_index))
sock.connect((doh_selected_ip, ssh_port))
transport = paramiko.Transport(sock)  # the same connected socket
transport.start_client(timeout=banner_timeout_s)
presented_key = transport.get_remote_server_key()
# compare presented_key fingerprint with the reviewed pin/receipt BEFORE authentication
```

`IP_UNICAST_IF` is Windows-specific. Do not emulate it by changing the global route table. Close the
socket/transport on every error and create a fresh single socket for a new attempt.

### Host identity: pinning first, session TOFU only with a receipt

Require **strict host-key pinning** whenever the provider console or another authenticated channel
supplies the fingerprint. OpenSSH uses a session-specific `UserKnownHostsFile` plus
`StrictHostKeyChecking=yes`; Paramiko compares `get_remote_server_key()` to the same expected
fingerprint before authentication. Never use `AutoAddPolicy`.

If no authenticated fingerprint exists, a **session TOFU receipt** is the explicit weaker fallback.
Record session ID, logical hostname, port, DoH-selected IP, key type/fingerprint, observed time,
evidence hashes and the fact that first-contact MITM protection was unavailable. Review it once, create
the session known-hosts pin, and require exact equality on every later connection in that session. A
session TOFU receipt is not an out-of-band identity proof and must not silently become a permanent
global trust entry.

The planner requires either a pinned fingerprint + known-hosts file or the complete session receipt
fields. It validates a real 32-byte SSH SHA-256 fingerprint shape and recomputes the receipt hash after
binding session ID, logical host, port, selected IP, key type, fingerprint, observation time and direct
evidence hash. Every receipt explicitly records `first_contact_mitm_unavailable=true`; a fallback receipt
also binds the DoH response hash and selected IP. The same complete receipt gate applies to direct OpenSSH
and Paramiko fallback. Its output always declares `system_mutations: []`; `identity_file` is validated as a
single-line path, raw key material and secret-shaped input fields are rejected, and no credential value is copied.

## 5. Resumable copy — rsync vs scp, and WHY rsync

`scp` opens **one** SSH stream for the whole transfer and **cannot resume**: any blip mid-copy aborts
the entire run and a re-run starts from zero. `rsync` compares source/dest and ships only the delta, so
a re-run after a drop **continues** instead of restarting — the single most important property on a
metered box where a 130 GB pull can blip at minute 45.

**Prefer `rsync` for anything large or multi-file:**

```bash
rsync -avz --partial --inplace --progress \
    -e ssh \
    <alias>:/root/autodl-tmp/checkpoints/ /path/to/local/checkpoints/
```

- `-a` archive (recurse + preserve perms/times/symlinks), `-v` verbose, `-z` compress on the wire.
- `--partial` keeps a partially-transferred file on interruption so the next run resumes mid-file
  (without it, rsync deletes the partial and re-sends from the start).
- `--inplace` writes directly into the destination file (resume-friendly; avoids a full temp copy on a
  tight local disk). Drop it if atomic-replace of an existing dest matters more than resumability.
- Re-run the **identical** command after any failure — that *is* the resume (principle #7).

Use plain `scp` only for a **single small** file (a config, one checkpoint < ~1 GB) where resume is
moot. For a large *tree*, even `scp` users should fall back to the **per-dir loop** (§6) so one dir's
failure doesn't lose the rest. If `rsync` is missing on the remote image, `apt-get install rsync` (when
online) or use the §6 loop.

> The bulk-download stall-retry ladder (HF/ModelScope mirror swaps, `timeout … && break` loops) is a
> *download-from-the-internet* concern, not host↔host copy — that lives in `references/run-remote/china-network.md`.

### Network-durable source → node-local transport cache

When the authoritative bundle sits on a FUSE/network/shared mount, copying it directly over WAN can make
remote metadata latency the bottleneck. Use a unique **node-local transport cache** without confusing it
with a durable replica:

1. Freeze the durable source roster, bytes and SHA-256 first.
2. Copy into a new node-local staging path; reject symlinks/path escapes and re-verify the same roster and
   hashes before transport. Never move, edit or delete the durable source.
3. Keep large checkpoints as separate resumable files. For hundreds of small control/evidence files, build
   one deterministic tar from an explicit relative-path list; record empty directories separately because
   a file-only pull manifest cannot imply them.
4. Transfer the tar and checkpoints, then extract into a unique local staging root and run the normal exact
   roster/bytes/SHA gate once. The node-local cache is an acceleration layer, not a second durable copy.

Do not assume compression helps a multi-GB checkpoint—many PyTorch files are already ZIP containers and
high-entropy tensors compress poorly. Measure once; prefer resumability and one-pass hashing over speculative
compression. Likewise, `rsync -a` preserving a symlink is transport behavior, not acceptance: an evidence
contract that forbids symlinks must reject them before staging and after extraction.

## 6. Bulk per-dir download loop

For a large directory tree (many run/checkpoint dirs), wrap each dir in its **own** SSH session so a
single drop loses only that dir, and a re-run **skips already-complete dirs**:

→ `scripts/download_loop.sh` (parameterize `LOCAL_TARGET`, `REMOTE_ALIAS`, `REMOTE_PATH`).

Its shape, and why each piece matters:

- **List once, copy per-dir** — each `scp -r <alias>:<remote>/$d ./` is an independent session; one
  failure ≠ whole-transfer loss (the `scp` single-stream trap, §5).
- **Size-threshold skip** — a dir already ≥ threshold counts as complete and is skipped; a partial dir
  is removed and re-pulled. Re-running the whole script is therefore idempotent and resumable.
- **Per-dir `ConnectTimeout` + the §3 keepalive flags** on every `scp` so a hung session self-kills
  instead of blocking the loop.

## 7. Move secrets via stdin — never inline a key, never on a durable FS

Putting a credential **in a command** (`ssh host "echo 'KEY' > …"`, or `scp key.txt host:…`) leaks the
value into shell history, agent transcripts, and hook logs. Putting it on a **shared /
durable FS** is worse: the value persists for every co-tenant, and some platforms' upload classifiers
*block or corrupt* a file matching a known key pattern — so a credential written to the cross-instance
FS may silently never arrive. **Push credentials to each box's per-instance system disk, via stdin**, so
the value flows file → pipe → file and appears in no command text or output:

```bash
# stream exactly one credential block — value never appears on a command line
grep -A 2 "machine api.<provider>.com" ~/.netrc \
  | ssh <alias> 'umask 077; cat > /root/.netrc && chmod 600 /root/.netrc'
```

```bash
# or a single token, same principle (stdin in, file out, chmod 600)
printf '%s\n' "$TOKEN_FROM_ENV" \
  | ssh <alias> 'umask 077; cat > /root/.<service>_key && chmod 600 /root/.<service>_key'
```

Rules that make this safe:

- **One block, not the whole file.** Stream a single `machine …` stanza, never the entire `~/.netrc` —
  it carries unrelated machines' credentials, and security hooks (rightly) block copying the whole file.
- **Reference, never echo.** Source the token from an env var (`$TOKEN_FROM_ENV`) or a keyring; never
  paste the literal value into the command.
- **Per-instance system disk, not the shared FS.** Write to `/root/.<service>_key` (volatile but
  private), not the cross-instance durable mount. The wrapper reads it and exports the env var before
  launch (e.g. `export WANDB_API_KEY=$(cat /root/.wandb_key)`).
- **Verify by capability, not by echoing the value:**
  `ssh <alias> 'python -c "import wandb; print(wandb.Api(timeout=20).default_entity)"'`.

## 8. CRLF — `.sh` authored on Windows breaks on Linux

Symptom → Root cause → Fix:

- **Symptom**: a synced launcher does nothing (empty log); run by hand it errors `set: -: invalid
  option`, `cd: /path\r: No such file or directory`, or `syntax error near unexpected token $'do\r'` —
  every line "ends in `\r`".
- **Root cause**: Windows `core.autocrlf=true` (or `git archive` exporting with the working-tree EOL)
  writes `.sh` with CRLF; Linux `bash` treats the trailing `\r` as part of each token. (`.py` is
  unaffected — Python's universal newlines tolerate CRLF; specifically `bash`/`.sh` breaks.)
- **Fix**: add `.gitattributes` with `*.sh text eol=lf` so `git archive`/checkout always emits LF; as an
  immediate on-box unblock, `sed -i 's/\r$//' scripts/*.sh`.

Every shell script in `scripts/` ships LF and starts `#!/usr/bin/env bash` + `set -u`; keep that
contract when authoring new ones. **Never** put an unquoted `|` inside a `grep` regex in a transport or
poll script — the shell splits it into piped commands and the first reads stdin → hangs forever
(`references/run-remote/monitoring_patterns.md`). And for ad-hoc REMOTE PROBES, prefer the shortest
single-line command that answers the question: long multi-line heredocs sent over ssh have been observed
garbled in transit (an `echo "=== src ==="` printed as a literal) — when a probe's output looks scrambled,
suspect the transport before the box, and fall back to minimal one-liners.

## 9. Two SSH flavors — proxied/basic SSH cannot `scp`

Some `ssh-rental` platforms expose **two** SSH endpoints, and the difference dictates whether file
transfer works at all:

- **Direct TCP SSH** — a real TCP port to the container (the `connect.<region>.<provider>.com:<PORT>`
  shape above). Full `scp`/`rsync`/`sftp` work. This is what every transfer in this file assumes.
- **Proxied / "basic" SSH** — a relayed or web-terminal SSH (common on RunPod and vast.ai for the
  default exposed endpoint). It carries an **interactive shell only**: `scp`/`rsync`/`sftp` fail (often
  with `subsystem request failed` / a hung handshake) because the proxy doesn't forward the SFTP
  subsystem.

**Fix**: for any code/data/checkpoint transfer, use the **direct-TCP** endpoint — on RunPod expose a
TCP port (the `ssh root@<ip> -p <PORT>` form, not the proxied `ssh <pod>@ssh.runpod.io` one); on vast.ai
use the instance's direct SSH port. Each profile's §3 NETWORK names which endpoint is which and whether
ports change on restart. If only proxied SSH is available, transfer out-of-band instead (push results to
object storage / HF Hub from on-box and pull from there).

## 10. Transport gotchas (Symptom → Root cause → Fix)

Universal gotchas (disk-full, inode, OOM, silent sync) are **not** repeated here — see
`references/run-remote/gotchas_universal.md`. These are transport-specific.

**T1 — SSH exits 255 / "Connection reset" right after a `pkill`/`kill`.**
Symptom: `ssh <alias> 'pkill -9 -f src.train'` returns `Connection reset by peer`, exit 255. → Root
cause: killing the process tree disrupts the PTY chain; the SSH client receives EOF and exits — and
anything *after* the kill in that same one-liner never runs. → Fix: this is **normal**, not a failure.
Re-ssh to verify (`ssh <alias> "pgrep -af src.train | head -1 || echo CLEAN"`). Split kill and relaunch
into **two** ssh calls — never `pkill X; relaunch X` in one command, the relaunch is dropped with the
session.

**T2 — large `scp -r` drops with "Read from remote host … reset by peer" 30–60 min in.**
Symptom: a 130 GB `scp -r` aborts mid-transfer; the local tree has only the first few dirs, the rest
gone. → Root cause: one SSH stream for the whole transfer; any blip kills it and `scp` does not resume.
→ Fix: use `rsync --partial` (§5) or the per-dir loop (§6) — each dir an independent session, re-run
skips completed dirs.

**T3 — `.sh` "ends in `\r`" after a Windows→Linux sync.**
See §8 (`.gitattributes` `*.sh text eol=lf`; on-box `sed -i 's/\r$//'`).

**T4 — a credential leaks into history / a shared FS, or its FS upload silently fails.**
Symptom: a key pasted into an `ssh`/`scp` command lands in transcripts and hook logs; an scp of the key
to the shared FS "succeeds" but the file is missing or corrupt. → Root cause: the value appeared in a
command line; and some platforms' FS classifiers block/corrupt credential-shaped uploads. → Fix: §7 —
stream one block via stdin to the per-instance disk, verify by capability not by echo.

**T5 — `scp dest open "/root/x/": Failure` instantly.**
Symptom: a (often parallel/background) `scp big.tar <alias>:/root/x/` fails at once because the
destination dir doesn't exist — a sibling command meant to `mkdir` it ran later, or was blocked. → Root
cause: the transfer assumed a directory a *different* command was supposed to create (a parallel-setup
race). → Fix: make every transfer self-sufficient — create the dest in the same command:
`ssh <alias> 'mkdir -p /root/x' && scp … || retry`. Never assume a sibling created the destination.

**T6 — `Host key verification failed` after an instance is recreated.**
Symptom: same `connect.<region>.<provider>.com` host, new host key, so SSH refuses. → Root cause: the
recreated container presents a different host key on the reused hostname/port. → Fix:
stop and retain the old key/receipt as evidence. Verify the recreation and new fingerprint through
the provider console or another authenticated channel, then replace only the scoped host+port entry.
When no authenticated fingerprint exists, use the §4A session TOFU receipt and disclose its weaker
first-contact guarantee. Never delete the old key and blindly re-accept an unreviewed replacement.
