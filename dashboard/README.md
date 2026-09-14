# dashboard/

Custom, responsive (desktop / iPad / mobile), **LAN-only** web dashboard (CLAUDE.md §35–§40). UI language: **Italian**.

> **Status:** implemented (A8). The dashboard (Login, Panoramica, Dispositivi, Dettaglio dispositivo, Sicurezza, Sistema, Avvisi, Registro query) runs against the mock provider; served by the backend itself in production ([ADR 0010](../docs/adr/0010-frontend-hosting.md)). Nothing is deployed to a real Pi.

| Path | Purpose |
|---|---|
| `frontend/` | TypeScript + React + Vite app. Built on the development machine; only `frontend/dist/` static files are deployed. Node.js is **not** needed on the Pi |

The backend lives in the Python package **`src/home_dns/api/`**, not here ([ADR 0002](../docs/adr/0002-software-stack.md)). Shared TypeScript types are generated from the backend's live OpenAPI schema, never hand-written — see `frontend/src/api/types.generated.ts`.

```bash
make test-web       # Vitest
make build-web      # static build into frontend/dist/
make gen-types      # regenerate frontend/src/api/types.generated.ts from the dev API
make check-types    # fail if the committed generated types are stale
make serve-static   # build the frontend and serve it + the API from one process (A8 rehearsal)
```

Fixed constraints:
- **Official API only.** Data comes from the backend, which talks to the DNS provider through `DnsProvider`, never from Pi-hole's internal databases.
- **Never exposed** to the Internet.
- **Polling.** The backend polls the provider and stores its own historical rollups.
- **Device identity is owned by the backend** (names, groups, IP↔MAC correlation), per ADR 0001 T4.
- **Same-origin only**: the frontend never calls a different host than the one that served it, in development (via the Vite dev-server proxy) or in production (same process, ADR 0010). No CORS.
