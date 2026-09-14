# Troubleshooting

> **Status:** covers Stage A (offline, development-machine) symptoms only. Stage B/C/D
> (real Pi, real network, real Pi-hole) troubleshooting will be added once those exist.

Symptom → diagnosis → fix guides with real commands.

## What it does

A single place to look up a known symptom before digging into the code or config by hand.

## Why it exists

CLAUDE.md §44: practical "how do I fix X" instructions, not just architecture docs.

## Dependencies

Assumes `make setup` has already run once.

## Configuration

Nothing to configure here.

## Installation

Nothing to install here.

## Operation — symptom → diagnosis → fix

**`uv run home-dns ...` fails with `ModuleNotFoundError: No module named 'home_dns'`**
(TD-002) — some macOS setups hide the editable-install `.pth` file and recent Python skips it.
Use the `make` targets instead (they set `PYTHONPATH=src` explicitly), or run
`chflags nohidden .venv/lib/python3.11/site-packages/*.pth`.

**`home-dns validate-config` reports `Result: NOT READY`** — read the printed table: each row
names the exact setting and why (`missing_required`, `missing_audit`, a placeholder token).
`<<REQUIRED:...>>` means you must supply a value; `<<AUDIT:...>>` means it can only be resolved
after the Stage B Raspberry Pi/network audits — that one is expected to stay unresolved until
then.

**`home-dns serve` refuses to start: "no dashboard admin user"** — the dashboard always
requires at least one admin account. Run:
```bash
home-dns auth set-password --username admin --role admin
```

**Dashboard login works but every mutation (rename a device, change a group) returns 403**
— the CSRF token is missing or stale. The frontend handles this automatically (one refresh, one
retry); if you're calling the API directly, re-fetch `GET /api/v1/auth/session` for a fresh
`csrf_token` and send it as `X-CSRF-Token`.

**Login returns 429** — 5 failed attempts within 15 minutes locks that username *and* that
client IP; wait, or restart the dev server (lockout state is in memory, not persisted).

**`make gen-types` / `make check-types` hangs or fails** — it starts a throwaway backend on
port 8099; if a previous run's process leaked, find and stop it:
```bash
lsof -ti tcp:8099 | xargs kill
```

**`npm install` in `dashboard/frontend/` reports an ERESOLVE conflict** — this should not
happen after A8 (the conflicting tool, `openapi-typescript`, was moved to its own
`scripts/codegen/` package). If it recurs, check nothing was added back to
`dashboard/frontend/package.json` that needs TypeScript 5 (TD-013).

**A blocklist source shows `kept_previous` repeatedly** — the pipeline is refusing to activate
a new download (failed fetch, stale content, or a sanity-limit anomaly). Run
`home-dns blocklists update --source <id>` (without `--apply`) to see which pipeline stage
rejected it, without changing anything.

## Recovery

See [restore.md](restore.md) for restoring from a backup.

## Rollback

See [maintenance.md](maintenance.md) for the safe-update/rollback process, and
`home-dns blocklists rollback <source> --apply` for reverting one blocklist source to its
previous artifact.

## Security implications

None of the fixes above require weakening a security control (disabling CSRF, widening a bind
address, etc.) — if a fix under consideration would do that, it is the wrong fix; open an issue
instead of working around it.
