# dashboard/

Custom, responsive (desktop / iPad / mobile), **LAN-only** web dashboard (CLAUDE.md §35–§40). UI language: **Italian**.

> **Status:** backend API ready on mock data (A7, [ADR 0005](../docs/adr/0005-backend-dashboard.md)). The frontend is still the A0 skeleton; the real pages come in A8. Nothing is deployed.

| Path | Purpose |
|---|---|
| `frontend/` | TypeScript + React + Vite app. Built on the development machine; only `frontend/dist/` static files are deployed. Node.js is **not** needed on the Pi |

The backend lives in the Python package **`src/home_dns/api/`**, not here ([ADR 0002](../docs/adr/0002-software-stack.md)). Shared TypeScript types will be generated from the backend OpenAPI schema (`/api/openapi.json`, development only) in A8.

```bash
make test-web     # Vitest
make build-web    # static build into frontend/dist/
```

Fixed constraints:
- **Official API only.** Data comes from the backend, which talks to the DNS provider through `DnsProvider`, never from Pi-hole's internal databases.
- **Never exposed** to the Internet.
- **Polling.** The backend polls the provider and stores its own historical rollups.
- **Device identity is owned by the backend** (names, groups, IP↔MAC correlation), per ADR 0001 T4.
