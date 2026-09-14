# Telegram Alerts

> **Status:** implemented and tested offline (A6). No real Telegram message has ever been sent
> from this project — real activation (`notifier.kind: telegram` plus real bot credentials) is a
> separate, explicit owner decision, not before Stage C3.

Bot setup, alert severities, cooldown, deduplication, incident state and recovery notifications.

## What it does

Turns A5 incidents into Italian-language Telegram messages, routed by severity
(🔴 CRITICO / 🟠 AVVISO / ℹ️ INFO) from `config/telegram/alerts.yaml`'s event→severity catalog,
with two independent anti-spam layers: A5's own per-check cooldown, plus A6's global
`cooldown_seconds`/`rate_limit_per_hour` across every outgoing message. See
[specs/a6-telegram-alerting.md](specs/a6-telegram-alerting.md).

## Why it exists

CLAUDE.md §29–31: reliable, non-spammy, secret-safe alerting with a recovery notification.

## Dependencies

A5 (incidents/alert events), `httpx` for the real HTTP call (unused unless
`notifier.kind: telegram`).

## Configuration

- `config/telegram/alerts.yaml` — severity catalog, `anti_spam` policy.
- Secrets `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — **environment variables only**, never in
  YAML; see `.env.example`.
- Notifier choice — `notifier.kind` in the app profile: `mock` (tests, records in memory),
  `file` (local JSONL outbox for manual review) or `telegram` (real send).

## Installation

Nothing to install for `mock`/`file`. To ever send for real: create a bot via
[@BotFather](https://t.me/BotFather), get its token and your chat id, then export
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` before running with `notifier.kind: telegram`.

## Operation

```bash
home-dns notify test            # dry-run: builds and would-send one INFO test message
home-dns notify test --apply    # actually sends, through whichever notifier is configured
```

With the default `mock`/`file` notifier, `--apply` still never reaches Telegram — it only
changes whether the mock records the message / the file notifier writes it to disk.

## Troubleshooting

- **`sent=False` on a dry run** — expected, not an error; nothing was meant to send.
- **A real send fails after `--apply`** — check `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are set
  and the bot has been added to the target chat. `TelegramNotifier` retries a transient failure
  with backoff and never raises to the caller; a persistent failure just returns `sent=False`.

## Recovery

No Telegram-side state to recover. Local anti-spam state lives as JSON under `data_dir/notify/`;
deleting it resets cooldown/rate-limit history only.

## Rollback

Set `notifier.kind` back to `mock` or `file`.

## Security implications

The bot token can send messages to your chat — treat a leaked token like a leaked password
(revoke it via @BotFather). `TelegramNotifier` never logs it or includes it in an exception
message or `repr()`.
