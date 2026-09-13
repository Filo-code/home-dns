# ADR 0002: Software Stack and Tooling

| Field | Value |
|---|---|
| **Status** | Accepted |
| Date | 2026-09-13 |
| Decision owner | Project owner (stack approved 2026-09-13) |
| Related | [implementation-plan.md](../implementation-plan.md) §9 · [specs/a0-foundations.md](../specs/a0-foundations.md) |

## Context

- **Where it runs:** the software (blocklist pipeline, maintenance, monitoring, Telegram alerts, backend API, dashboard) runs 24/7 on a Raspberry Pi 4 with a microSD card.
- **Where it is developed:** offline on a Mac first (Stage A), before any Pi or network work.
- **DNS provider:** it must integrate with Pi-hole v6 later ([ADR 0001](0001-dns-architecture.md)) through a replaceable provider interface.

## Decision

### Backend and automation

| Concern | Choice |
|---|---|
| Language | **Python ≥ 3.11**. Development pins 3.11 (`.python-version`) so the minimum supported version is what gets tested. |
| HTTP API | **FastAPI**, served by **uvicorn** (no `[standard]` extras) |
| Models and settings | **Pydantic v2** and **pydantic-settings** |
| Configuration files | **YAML**, loaded with `yaml.safe_load` only |
| Persistence | **SQLite** via the stdlib `sqlite3`, behind `home_dns.storage`. No other package imports `sqlite3`. |
| HTTP client (Pi-hole, Telegram) | **httpx** |
| Tests | **pytest** + pytest-cov (≥ 90 % line coverage gate) |
| Quality gates | **ruff** (lint + format), **mypy --strict** on `src/` |
| Environment and lock | **uv** with a committed `uv.lock` |

### Frontend

- **Stack:** TypeScript (strict) + React + Vite, with Vitest + Testing Library.
- **Build:** done on the Mac. Only static files from `dashboard/frontend/dist/` are deployed.
- **Node.js:** not required on the Pi in production.

### Code organisation

- **One Python package, `src/home_dns/`,** shared by the backend, pipeline, monitoring and maintenance code.
  - The backend is `home_dns.api`, so the separate `dashboard/backend/` and `dashboard/shared/` directories were removed.
  - Shared TypeScript types will be generated from the OpenAPI schema (A7).
- **Package boundaries** (`core`, `config`, `providers`, `storage`, `api`, `bootstrap`, `cli`) are enforced by an automated import test.
- **`DnsProvider` is synchronous.** The backend polls one provider at a low rate, and FastAPI runs sync handlers in a thread pool. Revisit if profiling on the Pi shows thread-pool pressure.

### Languages

- **Code, identifiers, technical logs, technical docs:** English.
- **Dashboard UI and Telegram messages:** Italian.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Go (single static binary) | Smaller runtime footprint on the Pi, but the owner approved Python; Pydantic/FastAPI give faster, well-tested validation and API development |
| Node.js/TypeScript backend | Would require Node.js on the Pi in production, which was explicitly excluded |
| Standard-library-only Python (argparse + http.server) | Too much hand-written validation, security and API plumbing for a long-lived service |
| pip-tools / Poetry | uv is already installed, fast, and produces a hashed cross-platform lock |
| A separate backend package under `dashboard/backend/` | Would duplicate models and config shared with the pipeline and monitoring |

## Consequences

- **Python runtime on the Pi.** Production needs Python ≥ 3.11 there. The Pi audit (B1) confirms the OS Python version. How dependencies are installed on the Pi (uv, or a lock export for pip) is decided in Stage C.
- **Two toolchains on the Mac.** Python/uv and Node/npm. `make setup` installs both; `make check` runs every gate.
- **Adding a real DNS provider** (Pi-hole v6 in C2) needs no changes to the API, core or storage packages, only a new provider plus its registration in `bootstrap` and the contract test registry.
- **Known ecosystem notice.** In the locked versions, Starlette emits a deprecation warning recommending `httpx2` for its test client. Tests pass; re-evaluate when the lock is refreshed.
