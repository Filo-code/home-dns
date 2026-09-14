# Protected domains

One category per file: `<category>.yaml`, and the `category:` value must equal the file name. Schema and rules: [ADR 0003](../../docs/adr/0003-configuration-model.md).

> **Status (A3):** 293 verified entries. Strategy and evidence: [design §4](../../docs/specs/a3-filtering-policy.md) and the [evaluation report](../../docs/research/2026-09-14-a3-policy-evaluation.md).

Uses:
- `validate-config` rejects any active deny rule or deny regex that would block a protected domain.
- The A2 pipeline aborts a blocklist deployment that contains one, keeps the previous working list, and alerts.

| File | Scope |
|---|---|
| `italian.yaml` | Poste Italiane, SPID, PagoPA, Agenzia delle Entrate, INPS, IO, CIE |
| `banking.yaml` | Intesa Sanpaolo, UniCredit, Banco BPM, BPER, MPS, Mediolanum, Fineco, Sella, Credem, Crédit Agricole, Nexi, PayPal, Stripe |
| `technology.yaml` | Google, Microsoft, Apple, Amazon |
| `gaming.yaml` | Steam, Xbox network, Microsoft Store, PlayStation Network |
| `streaming.yaml` | Netflix, YouTube, Prime Video, Disney+, DAZN, Twitch |
| `social.yaml` | Instagram, Facebook, TikTok, X, Reddit, Telegram, WhatsApp, Discord, Snapchat |
| `infrastructure.yaml` | DNS root/TLD, certificates (OCSP/CRL), time, OS updates, connectivity checks, project supply chain, multi-tenant apex guards |

**Adding an entry:**
- Use `include_subdomains: true` only for a namespace used exclusively by one service, and only after `scripts/blocklists/evaluate_policy.py` shows no listed names inside it.
- Otherwise protect the exact apex and the essential hosts.
- Never protect tenants of shared platforms.
