# ADR 0006: Telegram Alerting

| Field | Value |
|---|---|
| **Status** | Accepted |
| Date | 2026-09-14 |
| Decision owner | Project owner (message language and anti-spam defaults approved 2026-09-14) |
| Related | [A5 design](../specs/a5-monitoring.md) (incidents this phase notifies about) · [A6 design](../specs/a6-telegram-alerting.md) · [CLAUDE.md §29-31](../../CLAUDE.MD) |

## Context

CLAUDE.md §29-32 requires reliable, non-spammy, secret-safe Telegram notifications with severity
routing, anti-spam (cooldown, rate limiting, deduplication, recovery notifications) and safe
secret handling. A5 already decides *when* something is wrong and *when it has recovered*, firing
each exactly once; nothing yet turns that into an actual message, and nothing yet exists to send
one safely.

## Decision

1. **A new `notify` package**, structured exactly like `providers`: a `Notifier` ABC
   (`notify.base`) plus three implementations receiving only plain values (never configuration
   objects) — `MockNotifier` (in-memory, tests), `FileNotifier` (local JSONL outbox, manual
   review) and `TelegramNotifier` (real HTTP via an injectable `httpx.Client`).
2. **`core.notify` stays pure**, mirroring `core.monitoring`'s split: severity-catalog lookup,
   Italian message formatting (owner decision, 2026-09-14 — a one-time pick baked into the
   template, not a runtime setting), and a total `should_send()` anti-spam decision function.
3. **Two independent anti-spam layers**, not one: A5's `IncidentPolicy.cooldown_seconds` (per-check
   reminder debounce, already built) and a new `AntiSpamPolicy` (`cooldown_seconds=300`,
   `rate_limit_per_hour=20`, owner-approved 2026-09-14) applied by the Notifier layer to every
   outgoing message regardless of source — a global backstop, not a replacement.
4. **`TelegramNotifier` reuses A5's `BackoffPolicy`/`RestartBudget`** for retry (a smaller, purely
   synchronous instance — `max_attempts=3`, up to ~5s total — since `send()` blocks a single CLI
   invocation, unlike A5's cross-process check-restart budget). A 4xx is never retried; the budget
   exhausting returns `sent=False` rather than raising, so a Telegram outage never crashes the
   monitored system.
5. **Secrets are environment-only.** `SecretSettings` gains `telegram_bot_token` /
   `telegram_chat_id`, read only from unprefixed `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (never
   `HOME_DNS_`-prefixed, matching `alerts.yaml`'s own long-standing comment) and never from a
   profile file. An optional `config.secrets_file.load_env_file()` supports a systemd-style
   `EnvironmentFile` for deployments that want one, refusing to read anything group- or
   other-readable before opening it. The token is never logged or included in `repr()`.
6. **`config.telegram`** becomes a real schema-owning loader for `config/telegram/alerts.yaml`
   (severities + anti-spam), following A1/A4/A5's exact loader pattern — the file is no longer
   only generically scanned.
7. **`NotifierSettings.kind` defaults to `mock`**, unlike `dns_provider.kind` (which has no
   default): sending a Telegram message is never a safe accidental default, but it also never
   crashes anything to leave it unset, so existing profile files need no changes.
8. **One CLI command**, dry-run by default: `home-dns notify test [--apply]`. No real Telegram
   call happens from this session — that remains the owner's separate, explicit choice.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A background sender thread/queue | Nothing yet schedules checks continuously in this offline phase; a synchronous `send()` per alert is simpler and sufficient until a scheduler exists |
| English messages | Plan explicitly left this to the owner; Italian chosen this session |
| One shared cooldown for both A5 and the Notifier | Conflates two different questions — "is this check still broken" (A5, per-check) vs "have we sent too many messages lately" (A6, global) — kept as two policies |
| `dns_provider`-style required `notifier.kind` | Would force every existing profile file (repo and every test fixture) to add a new required section for no safety benefit, since `mock` is always a safe default |

## Consequences

- Every alert A5 (or a future check) raises can be routed, formatted and sent through one
  consistent path, without any concrete check knowing about Telegram at all.
- Anti-spam state (`storage/notify.py`) persists under `data_dir`, surviving process restarts,
  matching A5's own persistence rule.
- Swapping to a real Telegram bot later is a configuration change (`notifier.kind: telegram` plus
  the two environment variables) — no code change.
- Nothing in A6 required a Pi, network or production change; `TelegramNotifier` was exercised only
  against `httpx.MockTransport` in tests.
