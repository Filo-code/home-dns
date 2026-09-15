# Raspberry Pi deployment (Phase C4)

> **Status:** repository-side artifacts implemented and tested offline. **Nothing has been
> deployed to the real Raspberry Pi yet.** Architecture: [ADR 0010](../adr/0010-frontend-hosting.md)
> (frontend hosting) · [ADR 0007](../adr/0007-storage-strategy.md) (storage/paths). Pi-hole and
> Unbound are separate, already-running services (Stage C) — **this document never touches them.**

## What it does

Runs the dashboard (FastAPI API + built React frontend, one process) as a systemd service on
the Raspberry Pi, on the trusted LAN, over plain HTTP.

## Why it exists

The dashboard has so far only run as a development-mode rehearsal (`make serve-static`) on a
developer machine. C4 is the step that makes it a real, boot-persistent, rollback-capable Pi
service — without adding nginx, Docker, or any component ADR 0010 already rejected.

## Architecture

```
LAN browser
     │  http://<pi-lan-ip>:8080
     ▼
Raspberry Pi
     │
     ▼
systemd ──► home-dns-dashboard.service ──► uvicorn ──► FastAPI
                                                          │
                                              ┌───────────┴───────────┐
                                              ▼                       ▼
                                        /api/v1/*              /* (everything else)
                                        existing API      built React SPA (ADR 0010)
```

No nginx, no Caddy, no Docker, no reverse proxy — `deployment/nginx/` stays empty, matching ADR
0010. Pi-hole and Unbound run as their own independent services on the same Pi; this unit never
starts, stops, or configures them, and the dashboard's own collector talks to Pi-hole only
through its existing read-only API client (`PiholeV6Provider`), same as in development.

## Deployment layout

```
/opt/home-dns/
    releases/
        <git-commit-sha>/
            .venv/                          # uv-synced Python env for this release
            src/, config/                   # this repo's src/ and config/ (production.yaml excluded — see below)
            dashboard/frontend/dist/        # make build-web output
    current -> releases/<git-commit-sha>    # symlink, switched atomically on deploy/rollback

/srv/home-dns/                              # persistent, OUTSIDE any release — survives every
    data/                                   # deploy and rollback (ADR 0007 paths.*)
    logs/
    backups/
    tmp/

/etc/home-dns/dashboard.env                 # root:home-dns 0640, HOME_DNS_PIHOLE_APP_PASSWORD only
```

`current` is what the systemd unit and every path inside `config/app/production.yaml` point at.
Releases are immutable once deployed; only `current` moves. This is deliberately the *only*
deployment mechanism — no packaging format, no deploy tool, no second script layer.

## Systemd service

[`deployment/systemd/home-dns-dashboard.service`](../../deployment/systemd/home-dns-dashboard.service):

- `Type=simple`, runs `/opt/home-dns/current/.venv/bin/home-dns serve --env production --static-dir ...` (the existing `make serve-static` command, pointed at the production profile).
- `User=home-dns` / `Group=home-dns` — a dedicated, non-root, non-login service account (see below). Never root.
- `Restart=on-failure`, `RestartSec=5`.
- `WantedBy=multi-user.target` — starts at boot.
- `StandardOutput=journal` / `StandardError=journal` — no custom log files; the app's own
  `paths.log_dir` (rotated per ADR 0007) is the only file-based logging, unchanged from today.
- `EnvironmentFile=/etc/home-dns/dashboard.env` — the **only** place `HOME_DNS_PIHOLE_APP_PASSWORD`
  is ever set. It is never in `config/app/production.yaml` and never in the unit file itself
  (`docs/security.md`'s existing rule: secrets come from the environment, never a committed file).
- `ProtectSystem=strict` / `ProtectHome=true` / `ReadWritePaths=/srv/home-dns/*` — the service
  can write only its own persistent data/log/backup/tmp directories.

## Service user

No existing documented convention names a dashboard service user (Pi-hole's `pihole-FTL` and
Unbound run as their own service-managed identities; this is the first Home-DNS-authored one).
Create it exactly as narrowly as the unit needs — nothing more:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin home-dns
sudo mkdir -p /srv/home-dns/{data,logs,backups,tmp}
sudo chown -R home-dns:home-dns /srv/home-dns
sudo chown -R home-dns:home-dns /opt/home-dns
```

`home-dns` can: run the app, read the deployed release under `/opt/home-dns/current`, and
read/write `/srv/home-dns/*` (its SQLite DB, logs, backups, tmp). It cannot: read
`/etc/home-dns/dashboard.env` directly (root:home-dns 0640 — group-readable only; systemd itself
reads the file as root before dropping privileges to start the process, so `home-dns` never
needs interactive read access, matching `config/secrets_file.py`'s own "refuse group/other
access" rule in spirit), log in interactively, or touch Pi-hole/Unbound's own files.

## Production configuration

`config/app/production.yaml` is git-ignored (already in `.gitignore`) and lives only on the Pi,
copied from [`config/app/production.example.yaml`](../../config/app/production.example.yaml)
and filled in after the B2 (Fastweb Seven) and Pi network audits resolve the `<<AUDIT:...>>`
placeholders:

```yaml
environment: production
paths:
  data_dir: /srv/home-dns/data
  log_dir: /srv/home-dns/logs
  backup_dir: /srv/home-dns/backups
  tmp_dir: /srv/home-dns/tmp
dns_provider:
  kind: pihole_v6
  pihole_v6:
    base_url: http://<pi-lan-ip>:80        # Pi-hole's own API, same host, different port(s)
    request_timeout_seconds: 5
    verify_tls: true
api:
  bind_host: <pi-lan-ip>                    # NOT 0.0.0.0 — rejected by ApiSettings' LAN-only check anyway
  port: 8080
  cookie_secure: false                      # plain HTTP on the trusted LAN — see "HTTPS" below
  session_idle_minutes: 720
  session_absolute_hours: 168
```

`home-dns validate-config --env production --profile config/app/production.yaml` (the existing
readiness/placeholder gate — this task did not bypass or weaken it) must pass before deploying.
`api.bind_host` cannot be `0.0.0.0`: `ApiSettings`' existing LAN-only validator rejects any
non-private/non-loopback/non-link-local address, which is exactly the guarantee "bind to the
Pi's LAN address, never the wildcard" needs — no new code was required for this.

## Frontend

`make build-web` (existing target, unchanged) builds `dashboard/frontend/dist/`, which becomes
part of the release directory and is passed to `serve --static-dir`. There is no second
frontend-serving mechanism — the same `--static-dir` flag ADR 0010 already implemented is what
production uses, exactly as `make serve-static` already rehearses locally today.

## Deployment procedure

Build once, locally or in CI; deploy the built artifact — never rebuild an old release to roll
back to it.

```bash
# 1. Build (on the dev machine or CI)
make build-web
uv sync --locked
SHA=$(git rev-parse --short HEAD)

# 2. Ship the release to the Pi (rsync shown; any transfer works)
ssh pi 'mkdir -p /opt/home-dns/releases/'"$SHA"
rsync -a --exclude config/app/production.yaml \
    .venv src config dashboard/frontend/dist pyproject.toml uv.lock \
    pi:/opt/home-dns/releases/"$SHA"/
ssh pi 'ln -sfn /srv/home-dns/config-production.yaml /opt/home-dns/releases/'"$SHA"'/config/app/production.yaml'

# 3. Health check the new release BEFORE switching (its own venv against its own config,
#    a plain process — not yet the systemd-managed one)
ssh pi '/opt/home-dns/releases/'"$SHA"'/.venv/bin/home-dns validate-config \
    --env production --profile /opt/home-dns/releases/'"$SHA"'/config/app/production.yaml'

# 4. Switch `current` and restart
ssh pi 'ln -sfn /opt/home-dns/releases/'"$SHA"' /opt/home-dns/current && \
    sudo systemctl restart home-dns-dashboard'

# 5. Verify (see "Health verification" below)
ssh pi 'systemctl is-active home-dns-dashboard'
curl -f http://<pi-lan-ip>:8080/api/v1/health
```

`config/app/production.yaml` itself is not shipped per-release — step 2 symlinks each release's
config path to one persistent file under `/srv/home-dns/`, so filling it in once on the Pi is
never repeated per deploy, and it is never present inside the versioned repo tree.

## Rollback

No deployment framework — switching `current` back is the entire mechanism, and it never
rebuilds anything:

```bash
# On failure, list previous releases and switch back:
ssh pi 'ls -1 /opt/home-dns/releases/'
ssh pi 'ln -sfn /opt/home-dns/releases/<previous-sha> /opt/home-dns/current && \
    sudo systemctl restart home-dns-dashboard'
ssh pi 'systemctl is-active home-dns-dashboard'
curl -f http://<pi-lan-ip>:8080/api/v1/health
```

`/srv/home-dns/data` (the SQLite DB) is never touched by a deploy or rollback — only `current`
moves, so rolling back to an older release still reads today's data, forward-compatible schema
changes permitting (no schema migration is introduced by C4).

## Health verification

Prepared, not yet run — these are the exact commands for the Raspberry Pi once the owner
authorizes the live deployment step:

```bash
systemctl status home-dns-dashboard
journalctl -u home-dns-dashboard -n 100 --no-pager
curl -f http://<pi-lan-ip>:8080/api/v1/health
```

Then, from a second LAN device (not the Pi): load `http://<pi-lan-ip>:8080/` in a browser, log
in, and confirm the "Anomalie DNS" security-page section and normal navigation work.

Also confirm, none of which this deployment step itself changes:

- `dig @<pi-lan-ip> example.com` still resolves — Pi-hole is untouched by this unit.
- `systemctl status unbound` — still active, untouched.
- The dashboard's Overview page shows live data — proves the collector reached Pi-hole's API
  through the filled-in `dns_provider.pihole_v6.base_url`.
- `curl -i http://<pi-lan-ip>:8080/api/v1/does-not-exist` returns `404` (API/static separation —
  an unmatched API path must never fall through to the SPA's `index.html`).

## LAN access and security

- The dashboard is reachable only from the LAN — never expose it to the Internet, configure port
  forwarding, enable UPnP, or change any router setting for it.
- No additional firewall ports are opened beyond the one dashboard port; DNS (port 53) and
  Pi-hole/Unbound's own ports are unaffected.
- WireGuard remains disabled and undeployed (its config-only foundation from the prior phase is
  unrelated to and unused by this deployment).
- `api.bind_host` is the Pi's real LAN address, never `0.0.0.0` — enforced by the existing
  `ApiSettings` validator, not by anything new in this phase.

## HTTPS (deferred, intentionally)

This deployment is **plain HTTP on the trusted LAN**, matching `cookie_secure: false` — a real
trade-off, documented rather than hidden: a passive LAN observer could see session cookies in
transit. TLS termination is deliberately out of scope for C4 (ADR 0010 revisits nginx only "if
and when TLS termination is added" — that has not happened). If/when it does, `cookie_secure`
flips to `true` and the reverse-proxy question gets reopened on its own merits.

## Troubleshooting

| Symptom | Check |
|---|---|
| `systemctl status` shows `activating (auto-restart)` in a loop | `journalctl -u home-dns-dashboard` — almost always a `validate-config` failure (unfilled placeholder, bad path) surfacing at `serve` startup |
| Login works but every page after it 401s | `cookie_secure` mismatch — must be `false` for this HTTP-only deployment, or the browser silently drops the session cookie |
| `/api/v1/*` returns the SPA's `index.html` instead of 404 | Static mount registered before the API routers — should never happen given `create_app`'s fixed registration order (ADR 0010); if seen, it is a regression in `api/app.py`, not a config issue |
| Dashboard up, Overview page empty/erroring | Check `dns_provider.pihole_v6.base_url` and that Pi-hole's own web/API is reachable from `home-dns`'s network namespace (same host, so this should never be a network issue — check the Pi-hole app password in `/etc/home-dns/dashboard.env`) |

## Recovery

Restarting the unit is always safe (`Restart=on-failure` also does this automatically): the
collector reconciles from Pi-hole's own log and the SQLite watermark, and the frontend is static
files with no server-side session state beyond what's already in the DB.

## Undoing this phase

`sudo systemctl disable --now home-dns-dashboard` fully removes the dashboard's presence on the
Pi. Pi-hole and Unbound are never affected — nothing in this phase ever touched them.
