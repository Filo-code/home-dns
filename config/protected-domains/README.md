# Protected domains (planned)

> **Status: not written.** Domain entries are added and verified in Phase 8. **No domains are committed yet**, to avoid unverified assumptions.

Purpose: before any blocklist deployment, every candidate list is scanned against these domains. **Any match aborts the deployment**, keeps the previous working list, and sends a Telegram alert (CLAUDE.md §19).

Planned categories (one file per category, one domain per line, with a comment explaining why it is protected):

| File (planned) | Scope |
|---|---|
| `italian.txt` | Poste Italiane, SPID, PagoPA, Agenzia delle Entrate, major Italian banks, payment infrastructure |
| `technology.txt` | Google, Microsoft, Apple, Amazon, Steam, Xbox, Netflix, Prime Video, Disney+, YouTube, Twitch |
| `infrastructure.txt` | Major CDNs, authentication services, OS updates, certificate infrastructure (OCSP/CRL), cloud, DNS infrastructure |
