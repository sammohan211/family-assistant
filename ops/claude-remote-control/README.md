# Claude Remote Control on the server

Always-on Claude Code sessions on the VPS, driven from the Claude phone app. Each repo gets its own session, so switching repos means picking a different entry in the app. Nothing here touches the Family Assistant stack.

This folder is the source of truth. Edit here, merge, then run `install.sh` from the laptop.

| File | Installed to (user `sam`) |
|---|---|
| `claude-rc@.service` | `~/.config/systemd/user/claude-rc@.service` |
| `rc` | `~/.local/bin/rc` |
| `server-CLAUDE.md` | `~/.claude/CLAUDE.md` |
| `server-settings.json` | `~/.claude/settings.json` (deny rules) |

## Rules

- **Code only on the server.** Repos are plain clones of GitHub: no data, no packages, no running tests, scripts or notebooks. Claude edits, commits to a branch, pushes and opens a pull request; testing happens on the laptop. `server-CLAUDE.md` tells Claude this.
- **`sam` has no sudo and no `docker` group.** It can't reach the containers, the production database or `/root` (which holds `.env`). Admin and deploys stay with root.
- **Never push to `main`.** `~/.claude/settings.json` for `sam` denies pushes to `main` and force-pushes.
- **GitHub access** is a fine-grained token (`hetzner-claude-sam`) limited to the repos on the server: Contents and Pull requests read/write. It expires every 90 days; regenerate it on github.com and run `gh auth login --with-token` as `sam`.

## The `rc` command

Run it over SSH (`ssh family-assistant-sam .local/bin/rc list`), or ask any session to run it.

| Command | What it does |
|---|---|
| `rc list` | repos on the server and whether each is on |
| `rc on <repo>` | start its session, and start it at boot |
| `rc off <repo>` | stop it. Stopping the repo you're talking from ends that conversation. |
| `rc restart <repo>` | restart it (needed after a service-file change) |
| `rc attach <repo>` | see its screen; `Ctrl-a d` leaves it running |
| `rc add <github-name> <Folder>` | clone a repo, code only |

## Adding a repo

1. On github.com, add the repo to the token's repository access. No new login is needed on the server.
2. `rc add <github-name> <Folder>`, then `rc on <Folder>`.
3. First start only: `rc attach <Folder>`, answer `y` to "Trust …? [y/N]", then `Ctrl-a d`.

It then shows in the app as `<folder-name>-<two words>`. Each restart opens a fresh session with a new name; archive old entries in the app.

## Memory

About 385 MB per repo, because each opens one session in advance. With the stack running there's room for 3–4 repos at once; `rc off` the ones you aren't using.

## Gotchas

- **Each repo needs its own tmux server** (`tmux -L claude-<repo>`). With a shared server, the second repo's session lives inside the first repo's service, so systemd decides the second one died and keeps restarting it.
- **Restart race.** A new `claude remote-control` refuses with "This folder is already served by a terminal `claude remote-control` on this device" while the old one is still exiting (~2 s). `ExecStop` waits for Claude's pid to exit.
- **Hard crash (`kill -9`).** Claude can't sign off, so the "already served" record stays on Anthropic's side for about 2½ minutes. The service retries every 30 s and is back within ~3 minutes.
- **Keep the advance session.** With `--no-create-session-in-dir`, the repo doesn't appear in the app's session list at all.
- **Don't `pkill -f "claude remote-control"` in a one-off SSH command.** It matches the SSH shell running it and kills the connection. Use the pid from `tmux -L claude-<repo> display-message -p -t claude "#{pane_pid}"`.
- **One-off SSH commands don't have `~/.local/bin` on `PATH`.** Use `bash -lc "rc list"` or the full path.
