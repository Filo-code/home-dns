# Xbox

> **Status:** policy decided and tested offline (A3). Real-console validation in Stage C/D.

## Policy

`console` = **HaGeZi Multi LIGHT + TIF Mini**.

Protected (never blocked):
- Microsoft account sign-in (`login.live.com`, `login.microsoftonline.com`, `account.microsoft.com`);
- Xbox authentication: `user.auth` and `xsts.auth.xboxlive.com` (Microsoft Learn), plus `title.auth` and `device.auth`;
- Xbox network hosts: `title.mgt`, `assets1`, `xflight`, `profile`, `userpresence`, `peoplehub` (friends and party roster), `sessiondirectory` (multiplayer/matchmaking);
- Store and Game Pass: `displaycatalog`, `licensing`, `purchase`, `collections`, `storeedgefd` (`*.mp.microsoft.com`), `gamepass.com`, `xboxservices.com`;
- downloads and updates: `*.delivery.mp.microsoft.com`, `*.prod.do.dsp.mp.microsoft.com`, `*.windowsupdate.com` (Microsoft Learn);
- PlayFab backend apex.

Blocked where listed: Microsoft telemetry and Xbox beacons, which are not needed for playing. Light does not list them; Pro does.

## Known notes

| Item | Note |
|---|---|
| Party chat NAT (Teredo) | The historical `teredo.ipv6.microsoft.com` no longer resolves; Xbox party connectivity is validated on the real console in Stage D |
| PlayFab per-title hosts | Some games' telemetry titles are listed by HaGeZi; the apex is protected, and a game-specific allow rule can be added if a title breaks |

## Troubleshooting

```bash
PYTHONPATH=src uv run --locked python -m home_dns.cli policy explain --group XBOX <domain>
```

If something breaks, use a group-scoped allow rule with `expires_at` first, as for Smart TVs.
