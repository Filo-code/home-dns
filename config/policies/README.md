# Policies

`policies.yaml` defines which blocklist sources each policy uses. Each group in `config/groups/groups.yaml` points at exactly one policy. Schema: [ADR 0003](../../docs/adr/0003-configuration-model.md).

> **Provisional:** `standard` = Multi PRO + TIF Mini, `conservative` = TIF Mini only. A3 reviews these assignments with table-driven tests before anything is deployed.

Hard rules from CLAUDE.md, whatever the policy:
- **YouTube:** never block `googlevideo.com` or YouTube/Google video infrastructure (§25).
- **Twitch:** never block streaming, chat, authentication or CDN (§26).
- **Social networks:** keep fully functional; block only safe ad/tracking/malicious infrastructure (§24).
