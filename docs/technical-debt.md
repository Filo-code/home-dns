# Technical Debt Register

Known, accepted compromises. Each entry has an owner decision and a trigger for reassessment.

| ID | Recorded | Item | Impact | Decision | Reassess when |
|---|---|---|---|---|---|
| TD-001 | 2026-09-13 | Starlette `StarletteDeprecationWarning`: "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead" (also an anyio `BlockingPortal` alias deprecation) | Two warnings in every test run; no functional impact | Keep the approved `httpx` dependency; do not change dependencies only to silence warnings | Next dependency maintenance/update cycle, or if a Starlette/FastAPI release removes httpx support |
| TD-002 | 2026-09-13 | Some macOS setups flag `.venv/**/*.pth` as hidden; recent Python skips them, breaking the editable install | `uv run home-dns` fails by hand; `make` targets and pytest are unaffected (explicit `PYTHONPATH=src`) | Keep the workaround documented in `docs/development.md` | If uv or CPython changes `.pth` handling |
| TD-003 | 2026-09-13 | Domain normalization uses Python's built-in `idna` codec (IDNA 2003) for non-ASCII input | Rare internationalized names may normalize differently from IDNA 2008 resolvers | A2 measurement: HaGeZi ships punycode only (84 + 197 `xn--` rules, no raw Unicode), so the codec is never used for these lists. Keep as is | A new list or manual rules with raw Unicode names |
| ~~TD-004~~ | 2026-09-13 | ~~Artifact store keeps every activated artifact~~ | — | **Resolved 2026-09-13:** retention keeps current/previous/backup and prunes atomically after the state write | — |
