# Protected Domains

> **Status:** 293 verified entries (A3). Files: `config/protected-domains/*.yaml`. Strategy: [design §4](specs/a3-filtering-policy.md#4-protected-domain-strategy). Evidence: [evaluation](research/2026-09-14-a3-policy-evaluation.md).

## What it does

Protected domains are enforced at three independent layers:

1. **Configuration:** `validate-config` rejects any deny rule or deny regex that would block a protected domain.
2. **Deployment:** the A2 pipeline tripwire aborts a blocklist update that contains a protected domain, or a wildcard covering one. The previous list stays active and a critical alert is raised. `--accept-anomalies` cannot bypass it.
3. **Query time:** the policy engine allows protected domains before any rule or list. Pi-hole will get equivalent allowlist entries (C2).

## Tiers

| Tier | Setting | When |
|---|---|---|
| Subtree | `include_subdomains: true` | The namespace is used only by one service **and** no evaluated list contains a name inside it |
| Exact | `include_subdomains: false` | Brand apexes and essential hosts, where upstream lists legitimately block telemetry subdomains |
| Apex guard | `include_subdomains: false` on a multi-tenant platform apex | Catch "block the whole platform"; tenants stay filterable |

## How to add or change an entry

1. **Verify ownership.** Use official documentation, the official site served on the domain, or a domain referenced by the official site. Record it in `source`.
2. **Choose the tier** with evidence:
   ```bash
   PYTHONPATH=src uv run --locked python scripts/blocklists/evaluate_policy.py --cache-dir /tmp/eval
   ```
3. **Validate and test:**
   ```bash
   make validate-config
   make test
   uv run --locked pytest -m network tests/blocklists
   ```
4. **Add required endpoints** to `tests/data/compatibility.yaml` when the entry protects a service.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| `would block protected domain X` in validate-config | A manual deny rule or regex conflicts with protection; fix the rule |
| `blocked_by_tripwire` in `blocklists update` | An upstream list contains a protected domain. Do **not** remove protection to get past it without investigating; report upstream or re-evaluate the tier |
