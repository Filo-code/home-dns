# Policies (planned)

> **Status: not written.** Filled in Phase 10.

Each group from `config/groups/groups.yaml` gets a policy definition: which lists apply, allowlist exceptions, and the reason for each exception.

Hard rules from CLAUDE.md, whatever the policy:
- **YouTube:** never block `googlevideo.com` or YouTube/Google video infrastructure (§25).
- **Twitch:** never block streaming, chat, authentication or CDN (§26).
- **Social networks:** keep fully functional; block only safe ad/tracking/malicious infrastructure (§24).
