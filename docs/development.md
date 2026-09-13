# Development

> **Scope: Stage A (offline).** Everything here runs on the development machine. Nothing touches the Raspberry Pi, the router or the home network.

## Requirements

| Tool | Version | Why |
|---|---|---|
| uv | ≥ 0.11 | Python environment and lock (`uv.lock`) |
| Python | 3.11 (installed by uv if missing) | minimum supported version |
| Node.js / npm | Node 24, npm 11 (development only) | frontend build and tests |
| GNU make | any | task runner |

## Setup and daily commands

```bash
make setup                 # once (needs Internet): uv sync --locked + npm ci
make test                  # Python + frontend tests, offline
make lint                  # ruff, ruff format --check, mypy --strict, tsc
make check                 # lint + test + validate-config (development) + frontend build
make validate-config                                   # development profile
make validate-config ENV=production PROFILE=config/app/production.example.yaml
make serve-mock            # API on 127.0.0.1:8080 with the mock provider
make build-web             # static files in dashboard/frontend/dist/
```

Health check while `make serve-mock` runs:

```bash
curl -s http://127.0.0.1:8080/api/v1/health
```

## Code layout and boundaries

| Package | Responsibility | Must not import |
|---|---|---|
| `home_dns.core` | pure domain models and logic | any other home_dns package, frameworks, I/O libraries |
| `home_dns.config` | settings schema, profile loading, placeholders, readiness | providers, storage, api, bootstrap, cli |
| `home_dns.providers` | `DnsProvider` interface + implementations | config, storage, api |
| `home_dns.storage` | the only place that uses SQLite | config, providers, api |
| `home_dns.api` | FastAPI HTTP layer | concrete providers, bootstrap, cli, sqlite3 |
| `home_dns.bootstrap` | composition root (config → readiness → provider) | api, cli |
| `home_dns.cli` | `home-dns` command | — |

These rules are enforced by `tests/architecture/test_boundaries.py`. Full specification: [specs/a0-foundations.md](specs/a0-foundations.md).

## Configuration

- **Profiles:** `config/app/development.yaml` is committed and fully runnable offline. `config/app/production.example.yaml` is committed and contains placeholders only. `config/app/production.yaml` exists only on the Pi and is git-ignored.
- **Precedence:** `HOME_DNS_*` environment variables > profile file > model defaults. Nested keys use `__`, e.g. `HOME_DNS_API__PORT=8081`.
- **Selectors:**
  - `HOME_DNS_ENV` (`development` | `production`, default `development`)
  - `HOME_DNS_CONFIG_DIR` (default `./config`)
- **Secrets:**
  - Environment variables only, e.g. `HOME_DNS_PIHOLE_APP_PASSWORD`.
  - Secret-like keys in any YAML under `config/` make loading fail.
  - The application never reads `.env`. To use one locally: `set -a; source .env; set +a`.

### Placeholders

| Token | Meaning |
|---|---|
| `<<REQUIRED:name>>` | a value the owner must supply |
| `<<AUDIT:name>>` | a value known only after the Raspberry Pi / Fastweb Seven audits |

- **Where they are allowed:** only fields typed `Deferred[...]` accept them.
- **Typos fail:** a malformed token, e.g. `<<TODO>>`, is a load error.
- **Readiness statuses:** `ready`, `optional_unset`, `dev_only`, `missing_required`, `missing_audit`, `inactive_placeholder`, `advisory`.
  - Production refuses to start with any `dev_only` or `missing_*` value.
  - Development refuses active placeholders.

### `home-dns validate-config` exit codes

| Code | Meaning |
|---|---|
| 0 | ready for the selected environment |
| 1 | not ready (or warnings with `--strict`) |
| 2 | configuration cannot be loaded: syntax, schema, malformed placeholder, secret in file, environment mismatch |

## Testing rules

- **Tests run offline.** `tests/conftest.py` blocks every non-loopback socket connection. Tests that genuinely need the Internet (e.g. real blocklist downloads in A2) must be marked `@pytest.mark.network`; they are excluded by default. Run them with `uv run pytest -m network`.
- **`HOME_DNS_*` variables are cleared for every test.** Use `monkeypatch.setenv` inside a test.
- **Temporary data only.** Write to `tmp_path`; never to the repository.
- **Documentation-only network values** in fixtures and code: `192.0.2.0/24`, `2001:db8::/32`, MAC `00:00:5e:00:53:xx`, hostnames under `.example`. `tests/architecture/test_no_real_network_values.py` enforces this for `src/`, `config/` and `dashboard/frontend/src/`.
- **Provider contract.** Every `DnsProvider` implementation must pass `tests/contract/` unchanged. Register new providers in `tests/contract/conftest.py`.
- **Coverage.** Python line coverage must stay ≥ 90 %.

## Conventions

- **Dry-run by default.** Functions that mutate persistent state take a keyword-only `dry_run: bool = True` and return a report. CLI commands that mutate state require `--apply`.
- **Languages.** Code, identifiers, logs and technical docs: English. Dashboard UI and Telegram messages: Italian.
- **Decisions.** Important decisions get an ADR in `docs/adr/`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ERROR: Python environment missing. Run 'make setup' first.` | `make setup` |
| `uv sync --locked` fails with "lockfile needs to be updated" | a dependency changed in `pyproject.toml`; run `uv lock`, review the diff, commit `uv.lock` |
| `NetworkAccessBlockedError` in a test | the code under test tried to reach the network; inject a fake, or mark the test `network` if Internet is truly required |
| `ModuleNotFoundError: No module named 'home_dns'` when running `uv run home-dns` by hand | macOS flagged the editable-install `.pth` file as hidden and Python skipped it. Use the `make` targets (they set `PYTHONPATH=src`), or run `chflags nohidden .venv/lib/python3.11/site-packages/*.pth` |
| `configuration error: ... profile declares environment` | the profile file's `environment:` key does not match `--env` / `HOME_DNS_ENV` |
