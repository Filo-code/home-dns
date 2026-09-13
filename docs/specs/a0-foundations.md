# A0 — Foundations: Technical Specification

- **Status:** implemented 2026-09-13
- **Related:** [implementation-plan.md](../implementation-plan.md) · [ADR 0001](../adr/0001-dns-architecture.md) · [ADR 0002](../adr/0002-software-stack.md)

A0 builds a small, testable skeleton that later phases extend.
- It has **no domain features**: no blocklists, policies, monitoring, Telegram or dashboard pages.
- Everything runs on the development machine in offline/mock mode.

---

## 1. Directory structure

Only new or changed paths are shown. The rest of the existing scaffold is unchanged.

```text
home-dns/
├── pyproject.toml              # project metadata, dependencies, ruff/mypy/pytest config
├── uv.lock                     # exact, hashed dependency lock (committed)
├── .python-version             # 3.11 — develop on the minimum supported version
├── Makefile                    # setup / test / lint / check / validate-config / serve-mock / build-web
├── src/home_dns/
│   ├── __init__.py             # __version__
│   ├── py.typed
│   ├── core/models.py          # pure domain models (no I/O)
│   ├── config/                 # placeholders.py, settings.py, loader.py, readiness.py
│   ├── providers/              # base.py (DnsProvider), mock.py (MockDnsProvider)
│   ├── storage/sqlite.py       # open_database, Migration, apply_migrations(dry_run=True)
│   ├── api/app.py              # create_app(environment=..., provider=...)
│   ├── bootstrap.py            # composition root: settings → readiness → provider → runtime
│   └── cli.py                  # `home-dns validate-config`, `home-dns serve`
├── config/app/
│   ├── development.yaml        # committed; mock provider, local paths, loopback bind
│   └── production.example.yaml # committed; placeholders only (production.yaml is git-ignored)
├── tests/
│   ├── conftest.py             # env isolation + network guard (autouse)
│   ├── unit/                   # config, storage, cli, bootstrap
│   ├── contract/               # DnsProvider contract suite (mock now; Pi-hole v6 in C2)
│   ├── api/                    # FastAPI tests
│   └── architecture/           # import boundaries, no real network values
└── dashboard/frontend/         # Vite + React + TypeScript skeleton (Italian UI)
```

Removed: `dashboard/backend/` and `dashboard/shared/`.
- The backend is the `home_dns.api` package, because it shares models and config with pipeline, monitoring and maintenance code.
- Shared TypeScript types will be generated from the backend OpenAPI schema in A7.

## 2. Python dependencies

| Package | Kind | Why |
|---|---|---|
| fastapi | runtime | HTTP API (approved stack) |
| pydantic | runtime | models and validation |
| pydantic-settings | runtime | environment variables and secrets |
| pyyaml | runtime | YAML config files (`safe_load` only) |
| httpx | runtime | future Pi-hole/Telegram clients; FastAPI `TestClient` |
| uvicorn | runtime | ASGI server for `home-dns serve` (no `[standard]` extras) |
| pytest, pytest-cov | dev | tests and coverage |
| ruff | dev | lint + format |
| mypy, types-PyYAML | dev | static typing (`--strict` on `src/`) |

- `uv` manages the virtualenv and `uv.lock`. `requires-python = ">=3.11"`.
- How dependencies are installed on the Pi is decided in Stage C.

## 3. Frontend skeleton

- **Stack:** Vite + React + TypeScript (strict) + Vitest + Testing Library (jsdom).
- **Scope:** one `App` component with Italian text, plus one render test. No routing, API calls, charts or state management (those come in A8).
- **Build:** `npm run build` writes static files to `dashboard/frontend/dist/` (not committed). Node.js is a development/build dependency only.

## 4. Main interfaces

### 4.1 `DnsProvider` (`home_dns.providers.base`)

```python
class DnsProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def health(self) -> ProviderHealth: ...
    @abstractmethod
    def get_summary(self) -> DnsSummary: ...
    @abstractmethod
    def list_clients(self) -> list[DnsClient]: ...
```

- **Synchronous by design.** The backend polls one provider at a low rate, and FastAPI runs sync endpoints in a thread pool. Sync keeps the CLI, pipeline and tests simple.
- **Read-only in A0.** Write operations are added in A1/A2/A7 together with their models, and follow the dry-run convention (§9).
- **Errors:** implementations raise `ProviderError` or its subclass `ProviderUnavailableError`, never raw transport exceptions.

### 4.2 Core models (`home_dns.core.models`, frozen Pydantic)

| Model | Invariants |
|---|---|
| `ProviderHealth(status: ok/degraded/down, detail)` | — |
| `DnsSummary(total_queries, blocked_queries, cached_queries, unique_clients, collected_at)` | counts ≥ 0; blocked ≤ total; cached ≤ total; `collected_at` timezone-aware; `block_percentage` derived |
| `DnsClient(client_id, ipv4_addresses, ipv6_addresses, mac, hostname, first_seen, last_seen, total_queries, blocked_queries)` | `last_seen ≥ first_seen`; blocked ≤ total; MAC normalised (lower-case, colon-separated); timestamps timezone-aware |

### 4.3 `MockDnsProvider`

- **Deterministic:** same output for the same `seed` and injected clock.
- **16 sample clients**, using only documentation address space:
  - IPv4 `192.0.2.0/24` (RFC 5737)
  - IPv6 `2001:db8::/32` (RFC 3849)
  - MAC `00:00:5e:00:53:xx` (RFC 7042)
  - hostnames under `.example`
- `health_status` constructor option simulates degraded/down.
- No network, filesystem or hardware access.

### 4.4 Storage (`home_dns.storage.sqlite`)

- `open_database(path)` enables WAL, `foreign_keys=ON` and `busy_timeout`.
- `apply_migrations(conn, migrations, *, dry_run=True) -> MigrationReport`:
  - versions must be unique, contiguous and start at 1
  - each migration runs in its own transaction and is recorded in `schema_migrations`
  - dry-run reports what is pending and **leaves the database untouched**
- Repositories for real entities arrive with the first persisted data (A4/A5/A7).
- No code outside `storage` uses `sqlite3`.

### 4.5 HTTP API (`home_dns.api.app`)

- `create_app(*, environment, provider)`. A0 needs no other settings.
- `GET /api/v1/health` returns `{"status", "environment", "provider": {"name", "status"}, "version"}`.
- OpenAPI/docs endpoints are disabled in production.
- No authentication yet (A7). In A0, `serve` refuses production.

### 4.6 Composition root (`home_dns.bootstrap`)

- `build_provider(settings)`:
  - `mock` → `MockDnsProvider`
  - `pihole_v6` → `ProviderNotAvailableError` (implemented in C2)
- `build_runtime(loaded)`: evaluates readiness; raises `StartupRefusedError(report)` on any error-level finding.

## 5. Configuration and environment variables

**Precedence** (highest first):
1. `HOME_DNS_*` environment variables, nested with `__` (e.g. `HOME_DNS_API__PORT=8081`)
2. profile file `config/app/<environment>.yaml`
3. model defaults, only for values identical in every environment

**Selectors:**
- environment: `HOME_DNS_ENV` / `--env` — `development` (default) or `production`
- config directory: `HOME_DNS_CONFIG_DIR` / `--config-dir`
- specific file to validate: `--profile PATH`

**Schema (A0).** Unknown keys are rejected:

```yaml
environment: development | production     # must equal the selected environment
paths:        { data_dir, log_dir, backup_dir }   # relative paths only valid in development
dns_provider:
  kind: mock | pihole_v6
  mock:      { seed }
  pihole_v6: { base_url, request_timeout_seconds, verify_tls }
api:          { bind_host, port }
```

Settings for Telegram, storage, monitoring and policies are added by their own phases (A1–A7), not speculatively.

**Secrets:**
- **Where they come from:** environment only (pydantic-settings `SecretStr`); in production, via a systemd `EnvironmentFile`.
- **A0 secret:** `HOME_DNS_PIHOLE_APP_PASSWORD`, required only when `kind: pihole_v6`.
- **No secrets in config files:** a secret-like YAML key (`password|passwd|secret|token|api_key|apikey|private_key`) under `config/` fails loading.
- **Never shown:** values are displayed only as `set` / `missing`.
- **`.env` is not read** by the application.

## 6. Placeholder model

**Syntax:** the whole string value must be a token:
- `<<REQUIRED:dotted.name>>` — a value the owner must supply
- `<<AUDIT:dotted.name>>` — known only after the Stage B audits

**Validation rules:**
- A string containing `<<`…`>>` that does not match exactly is a **load error**, so typos cannot become silent literal values.
- Only fields typed `Deferred[T]` accept placeholders. A placeholder in any other field fails schema validation.

**Readiness classification:**

| Status | Meaning | development | production |
|---|---|---|---|
| `ready` | explicit value, valid everywhere | ok | ok |
| `optional_unset` | optional field empty | ok | ok |
| `dev_only` | `kind: mock`, relative paths | ok | **ERROR** |
| `missing_required` | `<<REQUIRED>>` in an active field, or a required secret absent | **ERROR** | **ERROR** |
| `missing_audit` | `<<AUDIT>>` in an active field | **ERROR** | **ERROR** |
| placeholder in an inactive section (e.g. `pihole_v6` while `kind: mock`) | not used by this run | INFO | INFO |

**Extra production rule:** an unspecified `api.bind_host` (`0.0.0.0` / `::`) → WARNING.

**Profile/environment mismatch** is a load error, so a development profile can never start as production.

## 7. `make` targets and `make test` criteria

| Target | Does |
|---|---|
| `make setup` | `uv sync --locked` + `npm ci` (the only target needing Internet, first time) |
| `make test` | pytest **and** Vitest |
| `make lint` | ruff check, ruff format --check, `mypy --strict src`, `tsc --noEmit` |
| `make check` | lint + test + `validate-config ENV=development` + frontend build (local CI) |
| `make validate-config ENV=…` | runs the CLI |
| `make serve-mock` | API with the development profile on loopback |
| `make build-web` | static frontend build |

`make test` must:
1. **Run offline.** An autouse guard fails any non-loopback socket connection. Internet tests are marked `network` and excluded by default.
2. **Need no Pi, Pi-hole, router or home network.**
3. **Be isolated from the developer's shell.** `HOME_DNS_*` variables are cleared for every test.
4. **Write only to pytest temporary directories.**
5. **Be deterministic:** injected clocks and fixed seeds.
6. **Exit non-zero** if any test fails, or if Python line coverage of `home_dns` is below **90 %**.
7. **Explain a missing setup:** fail with a clear message if `make setup` has not been run.

## 8. `validate-config`

```text
home-dns validate-config [--env development|production] [--config-dir DIR]
                         [--profile FILE] [--format text|json] [--strict]
```

Steps:
1. Load the profile with `yaml.safe_load`. Reject:
   - malformed placeholders
   - secret-like keys
   - an environment mismatch
2. Apply `HOME_DNS_*` overrides, then validate the schema.
3. Read secrets from the environment. Report only `set` / `missing`.
4. Evaluate readiness for the selected environment.
5. Scan the other YAML files under `config/` (domain schemas arrive in A1) for:
   - syntax errors
   - malformed placeholders
   - secret-like keys

   Placeholders found there are reported as INFO.
6. Print a text or JSON report. The command is **read-only**.

| Exit | Meaning |
|---|---|
| `0` | ready for the selected environment (warnings allowed unless `--strict`) |
| `1` | not ready: any ERROR (or WARNING with `--strict`) |
| `2` | cannot load: missing file, YAML syntax error, schema violation, malformed placeholder, secret in a file, environment mismatch |

## 9. Boundaries and conventions

| Package | Must NOT import |
|---|---|
| `core` | other `home_dns` packages; fastapi, httpx, sqlite3, yaml, uvicorn |
| `config` | providers, storage, api, bootstrap, cli; fastapi, httpx, sqlite3 |
| `providers` | config, storage, api, bootstrap, cli; fastapi, sqlite3, yaml |
| `storage` | config, providers, api, bootstrap, cli; fastapi, httpx, yaml |
| `api` | concrete providers (`providers.mock`, …), bootstrap, cli; sqlite3, yaml |
| `bootstrap` | api, cli |

- These rules are enforced by an AST-based architecture test.
- Providers receive plain values, not config objects.

**Dry-run convention:**
- Any function that mutates persistent state takes a keyword-only `dry_run: bool = True` and returns a report.
- CLI commands that mutate state default to dry-run and require `--apply`.
- In A0 the only mutating operation is `apply_migrations`.

## 10. Acceptance criteria

1. `make setup` then `make check` succeed on the Mac. Python line coverage ≥ 90 %.
2. `validate-config --env development` exits `0`.
3. `validate-config --env production --profile config/app/production.example.yaml` exits `1`, listing every placeholder plus the missing `pihole_app_password`.
4. Tests cover:
   - config loading and env override precedence
   - placeholder parsing, including malformed placeholders
   - readiness classification, development vs production
   - secret-in-YAML rejection and secret redaction
   - environment mismatch
   - CLI exit codes
   - `build_runtime` refusing production with placeholders or the mock provider
   - `pihole_v6` reported as not available until C2
   - migrations, including a dry-run that leaves the database untouched
   - the health endpoint
   - import boundaries
   - no RFC 1918 / ULA / real MAC values in `src/`, `config/` or `dashboard/frontend/src`
   - the network guard
5. The provider contract suite passes for `MockDnsProvider` and is parametrised so `PiHoleV6Provider` can be added in C2 without changing the tests.
6. The frontend builds to static files and its test passes. UI text is Italian.
7. No real IPs, MACs, hostnames or credentials, and no secrets, anywhere in the repo.
8. Docs updated: this spec, ADR 0002, `docs/development.md`, READMEs, CHANGELOG.
9. Nothing installed on or changed on the Raspberry Pi, router or network. No Pi-hole, Unbound or blocklists.
