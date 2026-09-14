# ADR 0010: Frontend Hosting (Raspberry-Pi-Served Static SPA)

| Field | Value |
|---|---|
| **Status** | Accepted |
| Date | 2026-09-14 |
| Decision owner | Project owner (Raspberry-hosted dashboard clarification approved 2026-09-14) |
| Related | [A8 design](../specs/a8-frontend-dashboard.md) · [ADR 0005](0005-backend-dashboard.md) (backend/dashboard architecture) · [ADR 0002](0002-software-stack.md) (frontend stack) · CLAUDE.md §35 |

## Context

The Raspberry Pi hosts both the DNS infrastructure (Pi-hole, Unbound, C-stage) and the Home-DNS
backend/dashboard. The frontend (React/Vite, already decided in ADR 0002) is built on the
development machine; nothing changes there. What was open was **how the built static files reach
a browser on the Pi's port** in production, without Node.js, Docker, or an unnecessary second
service.

## Decision

1. **The existing FastAPI/uvicorn process serves the built frontend directly**, via
   `create_app(..., static_dir: Path | None)`. `/api/v1/*` is always registered first; the static
   mount and a same-origin SPA-fallback route are added last, so an unmatched `/api/*` path 404s
   instead of ever falling through to the SPA.
2. **No reverse proxy, no second web server, no Docker.** `deployment/nginx/` stays empty.
3. **Same-origin by construction** — the frontend calls `/api/v1/...` as relative paths; in
   development, Vite's own dev server proxies `/api` to the backend so the browser never sees a
   cross-origin request even before a build exists. **No `CORSMiddleware` is added.**
4. **`GZipMiddleware`** (Starlette's built-in, no new dependency) compresses both API and static
   responses over the LAN link.
5. **A path-aware CSP**: `/api/v1/*` keeps its existing `default-src 'none'` (JSON only); every
   other response gets `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'
   data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` —
   verified against the actual `vite build` output (no inline script/style is emitted, so no
   exception was needed).
6. **`home-dns serve --static-dir PATH`**, default `None` (today's API-only behaviour,
   unchanged). `make serve-static` builds the frontend and runs this locally for rehearsal.

## Alternatives considered

| Alternative | Why not |
|---|---|
| nginx in front (static files + reverse proxy to uvicorn) | A new service to install, harden and keep updated on the Pi; a second thing that can fail; not justified while the traffic in question is a small LAN dashboard. Revisit only if/when TLS termination is added. |
| Docker for the frontend or the whole app | Explicitly excluded by the owner; adds a container runtime to a single-purpose Pi for no capability gain here. |
| CORS instead of same-origin | Would require configuring and maintaining an allow-list, and keeps a cross-origin credentialed-request class of risk alive for no benefit — the frontend and API are deployed together on purpose. |
| `StaticFiles(html=True)`'s built-in directory/`index.html` handling for the whole SPA | Verified against the installed Starlette version: it serves `index.html` only for the literal root of a mounted directory, not for arbitrary deep client-side routes (`/devices/42`) — real SPA fallback needed a small explicit catch-all route instead. |

## Consequences

- One process, one port, one systemd unit for both DNS-adjacent API and dashboard UI — simplest
  possible operational surface for C4.
- TLS termination, if ever added, becomes nginx's or another proxy's job in front of this same
  process later; `api.cookie_secure` already exists for that transition (ADR 0005).
- The catch-all SPA route guards against path traversal explicitly (rejects any `..` path
  segment) since it is a hand-written route, not `StaticFiles`' own (already-safe) lookup.
