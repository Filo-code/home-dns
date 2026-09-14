# A6 — Telegram Alerting: Design

- **Status:** implemented 2026-09-14
- **Related:** [implementation-plan.md](../implementation-plan.md) · [ADR 0006](../adr/0006-telegram-alerting.md) ·
  [A5 design](a5-monitoring.md) (`core.monitoring` incidents/alerts this phase notifies about)
- **Owner decisions (this session, 2026-09-14):** message language = Italian; anti-spam defaults
  `cooldown_seconds=300`, `rate_limit_per_hour=20` (config, not code — changeable before real
  deployment).
- **Constraints:** offline and development only. No real Telegram call happens unless the owner
  explicitly asks for the optional manual live send (plan §A6) — everything here is built and
  tested against `MockNotifier`/`FileNotifier`/a fake HTTP transport.

## 1. Scope

A5 already decides *when* something is wrong (`advance_incident`) and *when it has recovered*
(`TransitionKind.RECOVERED`), firing each exactly once. A6 decides *what to say* and *whether to
actually send it right now* — routing by severity, formatting in Italian, and a second,
notifier-level anti-spam layer (global cooldown + hourly cap) on top of A5's own per-check
debounce, then hands the text to one of three interchangeable `Notifier` implementations.

## 2. Modules

| Module | Role |
|---|---|
| `core.notify` (pure) | `Severity`, event→severity lookup, Italian message templates, `AntiSpamPolicy`/`AntiSpamState` and the pure `should_send()` decision |
| `notify.base` | `Notifier` ABC, `OutgoingMessage`, `SendResult`, `NotifierError` |
| `notify.mock` | `MockNotifier` — records sent messages in memory (tests) |
| `notify.file` | `FileNotifier` — appends to a local outbox file for manual review, dry-run by default |
| `notify.telegram` | `TelegramNotifier` — real HTTP call via injectable `httpx.Client`, bounded retry queue, token never logged |
| `storage.notify` | durable anti-spam state (last-sent time per key, hourly send timestamps), same atomic-write pattern as `storage/monitoring.py` |
| `config.telegram` | loads `config/telegram/alerts.yaml` (severities catalog, anti-spam policy, language) |
| `config.settings` | `SecretSettings` gains `telegram_bot_token` / `telegram_chat_id`, read from the environment only (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`, unprefixed — matches the file's own comment) |
| `config.secrets_file` | optional systemd-`EnvironmentFile`-style loader with a permission check (refuses group/other-readable files) |

`notify` is a new top-level package with the same boundary rules as `providers`: it must not
import `config`, `storage`, `api`, `bootstrap` or `cli`. Implementations receive plain values
(bot token as a plain `str` already resolved by the caller, chat id, base URL), never a
configuration object — the same rule `providers/base.py` already states for `DnsProvider`.

## 3. Severity routing and message formatting

`core.notify.severity_for_event(event, catalog) -> Severity` is a plain dict lookup built once
from `alerts.yaml`'s `severities` block at load time (`config.telegram`). Message text is built
from a small Italian template per severity (`🔴 CRITICO`, `🟠 AVVISO`, `ℹ️ INFO`) plus the event
name and detail string A5 already produces — no per-event template catalog, since the event names
and detail messages are already descriptive (`storage_above_90`, `2 consecutive updates kept the
previous artifact`, etc.) and duplicating 21 event-specific templates would be pure repetition for
no behavioural gain.

## 4. Anti-spam: two layers, not one

- **A5's `IncidentPolicy.cooldown_seconds`** (already built) — per-check reminder debounce, entirely
  before this phase, decides whether a *given check* is even allowed to raise a second alert while
  still open. Default 0: alert once on open, once on recovery, per CLAUDE.md §30's example.
- **A6's `AntiSpamPolicy`** (`cooldown_seconds=300`, `rate_limit_per_hour=20`) is a second,
  Notifier-level guard applied to *every* outgoing message regardless of source:
  - **Dedup/cooldown**: the same `(severity, event)` key is suppressed if sent again within
    `cooldown_seconds` — a defensive backstop in case something upstream ever calls `send()` twice
    for the same condition (a bug, a retried CLI invocation), independent of A5's own state.
  - **Rate limit**: at most `rate_limit_per_hour` messages total in the trailing 60 minutes,
    regardless of key — protects the Telegram bot/chat from being flooded if many independent
    checks fail at once (e.g. a full disk taking down several checks together).
  - Both are `null`-able in config; `null` means "no limit" (documented, not the default — the
    owner picked concrete numbers this session).

`should_send(state, key, policy, now) -> (AntiSpamState, bool)` is pure and total, mirroring
`core.monitoring.advance_incident`'s shape. Suppressed sends are never retried later — a suppressed
CRITICAL alert during a burst is not lost information (the underlying incident is still recorded by
A5), it is simply not re-announced.

## 5. Secrets

- `SecretSettings.telegram_bot_token: SecretStr | None` and `telegram_chat_id: str | None`, read
  only from `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (not `HOME_DNS_`-prefixed, matching the
  existing comment in `alerts.yaml`) via an explicit `validation_alias`, never from a profile YAML
  file (`SecretSettings` already refuses file sources — A0's rule, unchanged).
- `config.secrets_file.load_env_file(path)` is an **optional** extra for local/systemd use: a
  plain `KEY=VALUE` reader that raises `SecretFilePermissionError` if the file is readable by
  group or others (`st_mode & 0o077`), before reading a single byte. Not wired to any default
  path — only used if a deployment chooses a systemd `EnvironmentFile=`.
- `TelegramNotifier` never logs or exceptions-with the raw token; `repr()`/`str()` of the notifier
  and every error message redact it.

## 6. Telegram outage handling

`TelegramNotifier.send()` wraps the HTTP call in A5's own `BackoffPolicy`/`RestartBudget` primitives
(reused, not reimplemented): up to `max_attempts` retries with exponential backoff on a transport
or 5xx error; a 4xx (bad token/chat id) is not retried. Once the budget is exhausted, `send()`
returns `SendResult(sent=False, ...)` rather than raising — **a Telegram failure never crashes the
monitored system**, exactly as the plan requires. There is no unbounded queue: at most one message
is in flight per `send()` call, by design — A6 does not introduce a background worker/thread in
this offline phase, since nothing yet schedules checks continuously (that arrives with a future
phase's scheduler).

## 7. CLI

One read-only-by-default addition: `home-dns notify test [--apply]`, dry-run by default, builds
whichever `Notifier` the profile selects (`mock`, `file` or `telegram`) and sends one INFO test
message. Refused in production until C3, matching every other A-stage command. This exists so the
owner can exercise the whole path (including, if they choose, the optional real Telegram send) —
it is never invoked automatically by this session.

## 8. What A6 deliberately does not do

- No background sender thread/queue — `send()` is synchronous, called once per alert.
- No new alert events — reuses A5/A4's existing `alerts.yaml` catalog unchanged.
- No real Telegram call from this session — that remains the owner's explicit, separate choice.
