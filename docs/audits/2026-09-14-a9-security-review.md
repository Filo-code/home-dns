# A9 Security Review (Stage A, offline)

- **Date:** 2026-09-14
- **Scope:** everything built through A8 (`src/home_dns/`, `dashboard/frontend/`,
  `scripts/`, `config/`). Read-only review; nothing in the running system was modified.
- **Method:** manual review against the actual code, cross-checked against `ruff` (S/bandit
  ruleset), `mypy --strict`, `npm audit` (both `dashboard/frontend/` and `scripts/codegen/`),
  and a repo-wide grep for committed secret patterns.
- **Not in scope:** anything requiring a real Raspberry Pi, real Pi-hole, or real network
  (Stage B/C/D) — those get their own audits when they exist.

## 1. Automated checks (run 2026-09-14)

| Check | Result |
|---|---|
| `ruff check` (includes `S` bandit-equivalent rules) | 0 findings |
| `mypy --strict` | 0 findings, 54 source files |
| `npm audit` — `dashboard/frontend/` | 0 known vulnerabilities |
| `npm audit` — `scripts/codegen/` | 0 known vulnerabilities |
| Repo grep for private-key headers / inline `password:`/`token:` literals | 0 matches outside docs/tests fixtures |
| `pytest` (1123 backend, 116 frontend) | all green |

## 2. Secrets management

- `SecretSettings` reads `HOME_DNS_PIHOLE_APP_PASSWORD`, `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID` from environment variables only; its `settings_customise_sources` explicitly
  excludes file sources, so a secret can never be supplied via a committed YAML profile even by
  mistake (`src/home_dns/config/settings.py`).
- `config/secrets_file.py`'s optional `EnvironmentFile` loader refuses a group/other-readable
  file (`st_mode & 0o077`) before reading a single byte.
- `.gitignore` excludes `.env`, `config/app/production.yaml`, and `.local/` (dev database,
  session state, temp files). Verified: `git status` shows no secret-shaped file tracked.
- `TelegramNotifier` never logs, exceptions-with, or `repr()`s the bot token
  (`src/home_dns/notify/telegram.py`) — checked by reading the module directly, not just by
  test coverage.
- **Finding (none, verified):** no committed secret, real credential, or private key anywhere in
  the repository or its history touched this session.

## 3. Dashboard authentication (A7)

- Passwords: `hashlib.scrypt`, N=2¹⁷ (OWASP minimum), 16-byte salt, parameters stored with the
  hash. A 12-character minimum is enforced before hashing.
- Login timing: an unknown username is verified against a precomputed dummy hash, so the
  response time for "unknown user" and "wrong password" is not distinguishable by timing.
- Sessions: 32-byte random token; only its SHA-256 digest is stored (`storage/dashboard.py`), so
  a stolen database backup cannot be replayed as a live session. Cookie is `HttpOnly`,
  `SameSite=Strict`, `Secure` by default (`ApiSettings.cookie_secure` defaults `True`; the
  committed development profile explicitly opts out for plain-HTTP loopback only).
- CSRF: a per-session token required on every unsafe method, compared with `hmac.compare_digest`
  (constant-time).
- Rate limiting: 5 failures / 15 min, keyed by client IP *and* username (TD-011: in-memory, reset
  by a restart; accepted for a LAN-only household dashboard with a 12-character minimum).
- Role separation: `viewer` never receives domain-level data (query log, top domains, MAC
  addresses) — verified both server-side (`views.py` route dependencies) and client-side (A8
  never issues the request for a non-admin role).

## 4. Network exposure

- `ApiSettings.bind_host` is schema-validated to be loopback/private/link-local/unspecified only
  — a public IP fails config validation before the process starts
  (`src/home_dns/config/settings.py`).
- No `CORSMiddleware` anywhere in the app; the frontend is always same-origin (same process,
  ADR 0010), so there is no legitimate cross-origin caller to allow-list in the first place.
- Content-Security-Policy is path-aware: `default-src 'none'` for `/api/v1/*` (JSON only,
  verified there is nothing for a CSP to protect there beyond defence-in-depth), and a real
  `default-src 'self'` policy for the frontend, checked against the actual `vite build` output
  (no inline script/style exists, so no exception was needed).
- Security headers (`Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`) apply to every response.
- The static-file SPA fallback route explicitly rejects any path segment equal to `..` before
  touching the filesystem, in addition to Starlette's own (already-safe) `StaticFiles` lookup for
  the `/assets` mount — verified by an automated test that plants a file outside `static_dir` and
  confirms it is never served.

## 5. Blocklist / DNS-filtering safety (A2/A3)

- Every deployment goes through the protected-domain tripwire before activation; a match aborts
  the deployment and keeps the previous artifact (`src/home_dns/pipeline/blocklists.py`).
- Artifacts are written atomically (temp file → `fsync` → `os.replace`), so an interrupted write
  can never leave a half-written list active.
- No `dangerouslySetInnerHTML` anywhere in the frontend (grepped directly): domain names, which
  are attacker-influenced strings by nature, are always rendered as escaped JSX text.

## 6. Dependency posture

- Python: dependencies pinned via `uv.lock`; no separate `pip-audit`/`safety` tool is wired in —
  **new finding, recorded as TD-016 below**.
- Frontend: `dashboard/frontend/` has exactly two runtime dependencies (`react`, `react-dom`);
  `scripts/codegen/` (dev-only codegen tool, isolated from the shipped app) is the only consumer
  of `openapi-typescript`. Both `npm audit` clean at review time.

## 7. Findings summary

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | No automated Python dependency-vulnerability scan in `make lint`/`make check` | Low | New: **TD-016** |
| 2 | Login lockout state is in-memory, resets on restart, shared per-IP across usernames | Low, accepted | Existing **TD-011**, unchanged |
| 3 | Device activity endpoint scans at most 2 000 provider entries per request | Informational | Existing **TD-012**, unchanged |
| 4 | `openapi-typescript` incompatible with TypeScript 7 (isolated, not shipped) | Informational | Existing **TD-013**, unchanged |
| 5 | DNS service status is one aggregate signal, not per-component (Pi-hole vs Unbound) | Informational | Existing **TD-014**, unchanged |

No critical or high-severity findings. No secret, credential, or private key found committed
anywhere in the repository.

## 8. New technical debt from this review

**TD-016** (added to `docs/technical-debt.md`): no automated Python dependency-vulnerability scan
is wired into `make lint`/`make check` (only `ruff`'s static-analysis rules and `mypy` run
today). Low severity at this scale (few, well-known dependencies: FastAPI, Pydantic, httpx,
uvicorn, PyYAML), but worth adding before Stage C, when the same host also runs Pi-hole.
Reassess: before Stage C, or when a Python CVE affecting a direct dependency is disclosed.

## 9. Conclusion

Nothing found here blocks proceeding to Stage B (read-only Raspberry Pi/network audit). The
LAN-only, same-origin, no-CORS, tripwire-protected design holds up under this review; the
accepted trade-offs (TD-011 through TD-014) were owner-approved at the time they were introduced
and remain reasonable for a household-scale, offline-developed system that has not yet touched
real hardware or a real network.
