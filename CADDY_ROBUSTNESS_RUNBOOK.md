# Shared Caddy: multi-tenant setup — migration record & handoff

**Status: DONE — executed on the VM 2026-07-12.** This file is now the handoff:
copy it into the family-assistant repo (which owns the shared Caddy) so its docs
record how tenant hosting works. The step-by-step migration procedure it replaced
is in this repo's git history (`git log -- CADDY_ROBUSTNESS_RUNBOOK.md`).

## What changed (2026-07-12)

| Thing | Before | After |
|---|---|---|
| Shared network | runtime `docker network connect` (lost on every Caddy recreate) | external `caddy_net`, created once (`docker network create caddy_net`), owned by no compose project, declared in both stacks |
| Options app container | `options-helper-app-1` on `options-helper_default` only | `options-app`, also on `caddy_net` (options repo's `compose.cloud.yml`) |
| Caddy site config | one monolithic `/root/family-assistant/Caddyfile` | main Caddyfile ends with `import sites/*.caddy`; one file per tenant in `/root/family-assistant/sites/` |
| Caddy service (family-assistant `compose.cloud.yml`) | default network, Caddyfile mount only | + `networks: [default, caddy_net]`, + `./sites:/etc/caddy/sites:ro` mount, + top-level `networks: caddy_net: external: true` |

Verified end-to-end: `docker compose -f compose.cloud.yml down caddy && ... up -d caddy`
on family-assistant no longer breaks `options.auro-family.duckdns.org` — the routing
is declarative and self-heals. A backup of the old monolithic Caddyfile is at
`/root/family-assistant/Caddyfile.bak.2026-07-12`.

## What the family-assistant repo should know as the host

- **`caddy_net` is load-bearing infrastructure.** It is an external network no stack
  owns; never remove it. Tenants reach Caddy only through it.
- **`sites/*.caddy` are tenant-owned.** Each tenant app maintains its own site file
  (options' source of truth is `caddy/options.Caddyfile` in the options-helper repo).
  The main Caddyfile only changes for cross-cutting concerns.
- **Reload after any sites/ change**, always validating first:
  ```bash
  docker exec family-assistant-caddy-1 caddy validate --config /etc/caddy/Caddyfile
  docker exec family-assistant-caddy-1 caddy reload  --config /etc/caddy/Caddyfile
  ```
- **Bare `docker compose` breaks in `/root/family-assistant`**: the global
  `COMPOSE_FILE` in `/root/.bashrc` points at the options repo's compose files.
  Always use `docker compose -f compose.cloud.yml ...` in the family-assistant dir.
- **Recreating the Caddy container is now safe** for all tenants — networks and the
  `sites/` mount are declared in compose, nothing is runtime-only.

## Adding a tenant (books., notes., …)

1. The app's compose file joins external `caddy_net` and pins its container name
   (`<app>-app`) — copy the options repo's `compose.cloud.yml` pattern. Static sites
   skip this: Caddy can `file_server` a directory mounted into the container instead.
2. Drop `/root/family-assistant/sites/<app>.caddy` with the site block (copy the
   shape of options' `caddy/options.Caddyfile`: domain, `tls {$CADDY_TLS}`, proxy to
   `<app>-app:<port>`).
3. Validate + reload (commands above). No shared-file edits, no container recreates.

## Optional later cleanup

Extract Caddy + `sites/` into a standalone `edge/` compose stack so family-assistant
becomes an ordinary tenant like the rest. Ownership nicety only — robustness does not
depend on it, since the external network already survives recreates on both sides.
