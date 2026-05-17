# Desktop Setup (Omarchy + RTX 3090)

Steps to turn the desktop into the deployment host for the Family Assistant stack (Postgres + app + Ollama + Caddy). Aligned with the home-first topology in `family_assistant_prd.md` §17.2.

Order matters where noted. Anything marked **optional** can be skipped or done later.

---

## 1. Wake the box up

- Boot it, plug in network.
- `sudo pacman -Syu` to bring Omarchy / Arch fully up to date. Reboot if the kernel or NVIDIA driver updated.
- Confirm the GPU is alive: `nvidia-smi` should print driver version and the 3090. If it doesn't, fix the driver before going further — nothing downstream will work without it.

## 2. Install the runtime prerequisites

Pacman packages:

```bash
sudo pacman -S --needed git docker docker-compose nvidia-container-toolkit
```

Notes:
- Omarchy ships with `git` already in most cases — `--needed` makes that a no-op.
- The compose stack uses Docker-native GPU syntax (`deploy.resources.reservations.devices` in `compose.gpu.yml`). Docker is the simpler path here; Podman + GPU works but needs more CDI plumbing.

Enable Docker and add yourself to the `docker` group (so you don't need `sudo` for every compose command):

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in (or `newgrp docker`) for the group change to take effect.
```

Wire NVIDIA into Docker:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Smoke test GPU-in-container:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

If that prints the same `nvidia-smi` output as the host, GPU passthrough works.

## 3. Clone the repo

```bash
cd ~                              # or wherever you keep projects
git clone <repo url> family_assistant
cd family_assistant
```

(Use the SSH or HTTPS GitHub URL — same as on the laptop.)

## 4. Build `.env`

```bash
cp .env.example .env
```

Then fill in `.env`. Generate secrets locally — never commit this file (`.gitignore` already excludes it):

```bash
# POSTGRES_PASSWORD — any strong random string
openssl rand -base64 24

# SESSION_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Fill in:
- `POSTGRES_PASSWORD` — the generated value.
- `DATABASE_URL` — replace `CHANGE_ME` with the same password.
- `SESSION_SECRET` — the generated value.
- `OLLAMA_MODEL` — leave at `llama3.1:8b` for first run. With 24 GB VRAM you have headroom; you can revisit model choice later.
- `APP_HOSTNAME` and `APP_BASE_URL` — for LAN-only start, `family.local` is fine. If you go Tailscale (step 8), use the desktop's Tailscale magic-DNS name (e.g. `family.tailnet-name.ts.net`).
- `CADDY_TLS` — `internal` for home / Tailscale. (`<email>` only matters if you ever go cloud.)
- `USER1_EMAIL` / `USER1_PASSWORD_HASH` (and `USER2_*`) — leave blank for now; generate Argon2id hashes when you're ready to log in. The app starts fine without them.

## 5. Bring the stack up

```bash
docker compose -f compose.yml -f compose.gpu.yml up -d
```

Watch healthchecks settle:

```bash
docker compose ps
docker compose logs -f app
```

Expected: `postgres` healthy, `ollama` healthy after ~30s, `app` healthy once it can reach both, `caddy` running.

If `app` errors on first start, it's almost always a `.env` typo — re-check `DATABASE_URL` and `POSTGRES_PASSWORD` match.

## 6. Pull the LLM model

Ollama starts empty. Pull your model into the `ollama_data` volume (one-time, ~5 GB for `llama3.1:8b`):

```bash
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama list           # sanity check
```

(Embeddings are deferred per scope §11.8 — no need to pull `nomic-embed-text` yet.)

## 7. Run migrations + create the test DB

The app container has alembic in its venv:

```bash
docker compose exec app alembic upgrade head
```

For the test database (so you can run pytest against the same Postgres later):

```bash
docker compose exec postgres createdb -U family_assistant family_assistant_test
```

## 8. Verify end-to-end

- Health: `curl -k https://family.local/health` (or whatever `APP_HOSTNAME` resolves to). For LAN access, add `<desktop-ip> family.local` to your laptop's `/etc/hosts`. From inside the box, `docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"` bypasses Caddy entirely.
- Create login credentials so you can hit the UI. The app container has `argon2` installed, so generate the hash there:

  ```bash
  docker compose exec app python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('your-password'))"
  ```

  Paste the hash into `.env` as `USER1_PASSWORD_HASH=...`, **with every `$` doubled** (Compose treats a single `$` as a variable reference and will silently blank out parts of the hash with `WARN ... variable is not set`). Example: `$argon2id$v=19$m=...$salt$hash` becomes `$$argon2id$$v=19$$m=...$$salt$$hash`. Also fill `USER1_EMAIL` and (optionally) `USER1_NAME`. Then:

  ```bash
  docker compose restart app
  docker compose logs --tail=20 app
  ```

  No `WARN ... variable is not set` lines = hash made it through intact.
- Hit the login page in a browser and sign in with the plaintext password you chose (not the hash).
- Send an assistant command and watch `docker compose logs -f app ollama` — confirms the LLM round-trip works on the GPU.

## 9. Optional: Tailscale for remote access from the laptop

Aligned with the §17.2 home-topology decision (Tailscale, no port-forwarding through CGNAT).

```bash
sudo pacman -S tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up
```

Then on the laptop (`sudo zypper in tailscale && sudo tailscale up`), and you can reach the desktop at its tailnet hostname from anywhere.

Update `APP_HOSTNAME` / `APP_BASE_URL` in `.env` to the tailnet hostname (e.g. `family.tailnet-name.ts.net`) and `docker compose up -d` again so Caddy picks it up.

## 10. Optional: dev loop from the laptop

Two patterns, pick whichever fits the moment:

- **Laptop runs the app and tests; desktop only provides the LLM.** Set `OLLAMA_BASE_URL=http://<desktop>:11434` in the laptop's `.env`. The 14 currently-DB-needing tests still need a local Postgres on the laptop too. Most dev is fake-LLM anyway (the test suite proves this), so this is mostly for "I want a real LLM response right now."
- **Develop directly on the desktop over SSH** (VS Code Remote-SSH or similar). Simpler — one machine has Postgres + app + Ollama all sharing the compose network — but ties you to the desktop being up while coding.

---

For day-to-day operations once the stack is running (updates, logs, database, backups, model switching, common issues), see `OPERATIONS.md`.
