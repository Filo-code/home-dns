# Protected domains

One category per file: `<category>.yaml`, and the `category:` value must equal the file name. Schema and rules: [ADR 0003](../../docs/adr/0003-configuration-model.md).

> **Status:** schema implemented (A1). **Entries are added in A3 from verified sources.** Until then `validate-config` warns that the tripwire has nothing to check.

Uses:
- `validate-config` rejects any active deny rule or deny regex that would block a protected domain.
- The A2 pipeline aborts a blocklist deployment that contains one, keeps the previous working list, and alerts.

| File | Scope |
|---|---|
| `italian.yaml` | Poste Italiane, SPID, PagoPA, Agenzia delle Entrate, major Italian banks, payment infrastructure |
| `technology.yaml` | Google, Microsoft, Apple, Amazon, Steam, Xbox, Netflix, Prime Video, Disney+, YouTube, Twitch |
| `infrastructure.yaml` | Major CDNs, authentication, OS updates, certificate infrastructure (OCSP/CRL), cloud, DNS infrastructure |
