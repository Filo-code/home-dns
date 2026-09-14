# Smart TV

> **Status:** policy decided and tested offline (A3). Real-device validation in Stage C/D. Brands of the three TVs are not yet known (TD-008).

## Policy

`smart-tv` = **HaGeZi Multi LIGHT + TIF Mini**, chosen over Normal after evaluating real lists ([evaluation §3](research/2026-09-14-a3-policy-evaluation.md)).

- **Blocked:** TV-vendor ad domains (`samsungads.com`, `samsungadhub.com`, `lgsmartad.com`), trackers, telemetry, malware and phishing.
- **Protected** (never blocked):
  - Netflix, YouTube (incl. `googlevideo.com`), Prime Video, Disney+, DAZN, Twitch playback/API/CDN endpoints;
  - Google Play and Android services; Apple App Store and updates;
  - connectivity checks, time and certificates.
- **Avoided compared with Normal/Pro:** Prime Video ad-roll hosts and Netflix logging.

## Known risks to check on real TVs

| Item | Why |
|---|---|
| Prime Video `api.*.aiv-delivery.net` | Blocked by every HaGeZi level (TD-006) |
| Vendor store/update domains (Samsung, LG, Android TV) | Watch list only; no list blocks them today (TD-008) |
| Casting | Chromecast discovery is local (mDNS). Setup needs Google endpoints, which are protected |

## Troubleshooting

```bash
PYTHONPATH=src uv run --locked python -m home_dns.cli policy explain --group SMART-TV <domain seen in the Pi-hole query log>
```

If a TV feature breaks because of a listed domain:
1. Add an allow rule for `groups: [SMART-TV]` with `expires_at` about 7 days out.
2. Confirm the fix.
3. Then either make it permanent with evidence, or let it expire.
