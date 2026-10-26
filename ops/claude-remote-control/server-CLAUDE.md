# This machine: the Hetzner server (code only)

You are running on a cloud server as the unprivileged user `sam`, reached from the Claude phone app.

- The repos in ~/repos are **code-only clones**. Their data, virtual environments and packages live on the laptop on purpose.
- **Do not install packages** (no `uv sync`, `pip install`, `apt`, `npm install`) and **do not run** tests, scripts, notebooks or builds. When something should be run, say exactly what to run on the laptop.
- Do not copy data onto this server or ask for it to be copied.
- Work on a branch, commit, push it and open a pull request. Never push to `main`; the owner merges and tests on the laptop.
- Stay inside the repo this session was started in. Do not edit other folders in ~/repos.
- Managing sessions: `rc list`, `rc on <repo>`, `rc off <repo>` (see `rc help`). `rc off` on this session's own repo ends this conversation.
