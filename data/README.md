# data/

Placeholder only. **Runtime data is never committed** (see `.gitignore`).

On the Raspberry Pi, runtime data (query databases, dashboard metrics, logs, backups) will live in a dedicated data directory, decided in ADR 0002 after the Raspberry Pi audit. That keeps a later microSD → USB 3 SSD migration a path change, not an application rewrite (CLAUDE.md §17).
