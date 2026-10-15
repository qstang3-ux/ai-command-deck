---
name: server-terminal-viewer
description: Open a local read-only AI Command Deck before user-authorized SSH server commands, showing real execution live and saving replayable terminal recordings. Use for server inspection, testing, changes, and requests to watch server terminal execution. Excludes ordinary local shell work and browser-only administration.
---

# Server terminal viewer

The user wants to watch actual terminal execution in external Chrome. Route authorized server work through the recorded PTY; never substitute manually transcribed logs.

## Start and show

Resolve `scripts/viewer.py` relative to this skill. It delegates to AI Command Deck using the Python environment recorded by the installer. If the runtime is missing, explain the installation blocker rather than silently running unrecorded server commands.

1. Check `http://127.0.0.1:8768/api/config` using a bounded request, and verify it reports AI Command Deck's `version` and `retention_days`. Reuse a healthy instance. Do not reuse an unrelated listener; choose another free loopback port if occupied.
2. If needed, run `python3 <skill-dir>/scripts/viewer.py serve --port 8768` in a persistent exec session. It binds to `127.0.0.1` only.
3. Open/reuse the viewer tab in external Google Chrome using browser tools. If extension tab creation fails, use supported native Chrome controls. Verify the viewer is visible. If Chrome cannot be controlled, provide the local URL; use the in-app browser only if the user asks.

## Execute

Use a tool PTY (`tty: true`):

```bash
python3 <skill-dir>/scripts/viewer.py run --name 'user@server · task' -- ssh user@server
```

Use server/user details actually authorized by the user. Preserve normal SSH host-key checking. Enter authorized authentication only in the SSH prompt, never in command arguments, the skill, or source files. Output is recorded, raw stdin is not; echoed commands and output can still contain secrets.

After verified login, load the definition from this skill's `scripts/command-step.sh` and send it once to the interactive SSH shell (in memory only). Then send each authorized operation through `write_stdin` as `deck_step 'actual command'`, using proper shell quoting. This prints the actual command before running it and its exit code afterward, independently of shell echo. Each step uses a child Bash: combine dependent operations as `cd /path && command`, since cwd/environment changes do not persist between steps. Authentication input goes directly to the hidden SSH/password prompt, never through `deck_step`. Do not include secrets in command arguments: the launcher and steps deliberately display the actual command. The recorder also prints the launch command, running state, duration, and final process exit code. Existing unrecorded SSH sessions cannot be observed retroactively. Do not attach arbitrary user terminals. Viewing authorization does not authorize extra server tests, changes, credential searches, or contacting other servers. When colleagues are changing a server, coordinate before mutations or load tests.

## Review

The browser is read-only. It provides a live terminal, asciinema historical replay after completion, recording export, and a text log with search-by-session, wrapping, copy, and follow controls. Scrolling text up disables following; session reading positions are restored. Full-screen programs are shown in terminal mode; text mode is best for copying and scrolling logs (latest 500 KB). Old text-only recordings remain readable but have no timed replay.

Sessions are local in `~/.codex/terminal-viewer/sessions` with private permissions. The default retention is 7 days after session end, with startup and hourly cleanup; running sessions are retained. For explicit custom settings use `TERMINAL_VIEWER_DATA` and `TERMINAL_VIEWER_RETENTION_DAYS` consistently in both server and recorder. Exported copies are outside automatic cleanup. Never publish or upload session logs automatically.

Before first use after installation or upgrades, record a harmless local demo and verify it appears in `/api/sessions`, with `.cast` recording and live output. No server login is needed for this check.

Report actual task results and leave the viewer open. Exit idle SSH sessions normally; do not kill user operations for UI cleanup. Repository publication should include source and synthetic demos only, never real server logs or credentials.
