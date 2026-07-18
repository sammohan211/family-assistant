# Tenant site blocks for the shared Caddy

Each app hosted behind this VM's Caddy drops one `<app>.caddy` file here; the
main `Caddyfile` ends with `import sites/*.caddy`. See
`PRD_AND_ROADMAP.md` §17.10 for the topology and how to add a tenant.

The `.caddy` files are deliberately **not** committed to this repo — each
tenant app's own repo is the source of truth for its site block (e.g. the
options-helper repo's `caddy/options.Caddyfile`). Only this README is tracked,
so the directory exists on a fresh checkout for the compose bind mount
(`./sites:/etc/caddy/sites:ro`).

After changing anything in this directory on the VM:

```bash
docker exec family-assistant-caddy-1 caddy validate --config /etc/caddy/Caddyfile
docker exec family-assistant-caddy-1 caddy reload   --config /etc/caddy/Caddyfile
```

Gotcha: Caddy bind-mounts the main Caddyfile as a single file, so editors/sed
that replace the file (new inode) leave the container reading the old copy —
recreate Caddy (`docker compose -f compose.cloud.yml up -d --force-recreate
caddy`) if a reload doesn't seem to take. Files inside `sites/` are fine
because the whole directory is mounted.
