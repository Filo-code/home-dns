# dashboard/

Custom, responsive (desktop / iPad / mobile), **LAN-only** web dashboard (CLAUDE.md §35–§40).

> **Status: not started.** Technology stack not chosen. This will be decided in **ADR 0005** (Phase 14). Nothing is deployed.

Fixed constraints already decided:
- **Official API only.** Data comes from the Pi-hole API (ADR 0001), not from Pi-hole's internal databases.
- **Never exposed** to the Internet.
- **Polling.** None of the evaluated DNS servers push updates, so the backend polls and stores its own historical rollups.
- **Backend owns device identity** (names, groups, IP↔MAC correlation), because IPv6 identification in Pi-hole is unproven (ADR 0001 T4).

| Directory | Purpose |
|---|---|
| `backend/` | Authentication, Pi-hole API integration, normalization, device names, policies, historical metrics, alert engine |
| `frontend/` | Overview, Devices, Security, Performance pages |
| `shared/` | Types/contracts shared by backend and frontend |
