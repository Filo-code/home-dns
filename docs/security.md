# Security

> **Status:** ongoing reference, kept current as the system grows. A point-in-time review of
> everything built through Stage A is in
> [audits/2026-09-14-a9-security-review.md](audits/2026-09-14-a9-security-review.md) (A9).
> Nothing described here is installed or deployed to a real Pi yet.

Threat model, secret management, API exposure, hardening, patching.

## Known so far

Pi-hole web/API (once installed, Stage C) must be LAN-only and restricted to trusted hosts
(ADR 0001 T7). Secrets are never committed — see `.env.example`.

## What it does

Security is layered by stage, not a single component:

- **Secrets** (`config/secrets_file.py`, `SecretSettings`): read only from environment variables,
  never from a committed YAML file; an `EnvironmentFile` loader refuses a group/other-readable
  file before reading a byte.
- **Blocklist tripwire** (A2): a protected-domain scan aborts a deployment outright if a critical
  domain (bank, government identity service, OS update infrastructure, …) would be blocked.
- **Dashboard auth** (A7): scrypt-hashed passwords, server-side sessions (`HttpOnly`,
  `SameSite=Strict`, `Secure` in production), per-session CSRF tokens, login rate limiting,
  role-based data exposure (viewer vs admin).
- **LAN-only by construction** (A0/A7): the settings schema rejects a public `api.bind_host`;
  no `CORSMiddleware` exists anywhere in the app.
- **Frontend hosting** (A8/ADR 0010): a path-aware Content-Security-Policy, no inline
  script/style, no secrets in the built bundle or in `localStorage`.

## Why it exists

CLAUDE.md §55 (final rule): the system must be safe to run unattended, 24/7, on a home network.

## Dependencies

Every A-stage phase contributes to this; see the point-in-time review linked above for the full
cross-reference.

## Configuration

There is no single "security config file" — see each phase's own doc
([telegram-alerts.md](telegram-alerts.md), [blocklists.md](blocklists.md),
[protected-domains.md](protected-domains.md)) for its specific settings.

## Installation

Nothing to install for the software itself. Stage B/C will need: SSH key-based access to the Pi,
a firewall review, and Pi-hole/Unbound's own hardening — not yet performed.

## Operation

`make lint` runs `ruff` with the `S` (bandit-equivalent) ruleset on every change;
`npm audit` is checked before adding any frontend dependency (currently 0 known vulnerabilities
in both `dashboard/frontend/` and the isolated `scripts/codegen/` tool).

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for CLI/dashboard-specific symptoms
(login lockout, CSRF errors, startup refusals).

## Recovery

A compromised or lost secret (Telegram token, dashboard password) is rotated, not "recovered":
generate a new bot token via @BotFather, or `home-dns auth set-password` for a dashboard account
(this also revokes that user's existing sessions).

## Rollback

Not applicable at the software level — see [maintenance.md](maintenance.md) for the safe-update/
rollback process, and [backups.md](backups.md)/[restore.md](restore.md) for data-level recovery.

## Security implications

This document *is* the security-implications summary; see the linked point-in-time review for
findings, accepted risks (with their technical-debt IDs) and what remains for Stage B/C/D.
