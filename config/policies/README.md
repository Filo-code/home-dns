# Policies

`policies.yaml` defines which blocklist sources each policy uses. Each group in `config/groups/groups.yaml` points at exactly one policy. Schema: [ADR 0003](../../docs/adr/0003-configuration-model.md).

> **Decided in A3 ([ADR 0009](../../docs/adr/0009-filtering-policy.md)):** `standard` (DEFAULT, PC, MOBILE) = Multi PRO + TIF Mini · `gaming` (GAMING) = Multi NORMAL + TIF Mini · `smart-tv` (SMART-TV) and `console` (XBOX) = Multi LIGHT + TIF Mini.

Hard rules from CLAUDE.md, whatever the policy:
- **YouTube:** never block `googlevideo.com` or YouTube/Google video infrastructure (§25).
- **Twitch:** never block streaming, chat, authentication or CDN (§26).
- **Social networks:** keep fully functional; block only safe ad/tracking/malicious infrastructure (§24).
