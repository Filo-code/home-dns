# A3 Policy Evaluation — 2026-09-14

> **Purpose:** evidence for the A3 protected-domain set and the per-group policy decisions ([design](../specs/a3-filtering-policy.md), [ADR 0009](../adr/0009-filtering-policy.md)).
> **Method:** real HaGeZi lists downloaded to a scratch directory on the development machine (versions of 2026-09-13), parsed with the production parser, and evaluated with the production `PolicyEngine` and tripwire. Nothing was activated; no Raspberry Pi, router or network change.
> **Reproduce:** `PYTHONPATH=src uv run python scripts/blocklists/evaluate_policy.py --cache-dir /tmp/eval` and `uv run pytest -m network tests/blocklists`.

## 1. Protected-domain verification

| Step | Result |
|---|---|
| Candidates drafted | 244 protected + 98 watch/extra names (342 unique) |
| DNS existence (Cloudflare DoH JSON) | 5 NXDOMAIN removed (e.g. `teredo.ipv6.microsoft.com`, `emdl.ws.microsoft.com` — the latter documented by Microsoft but no longer resolving) |
| Exact/wildcard blocks by 8 real lists (Light, Normal, Pro, TIF Mini, Pop-Up Ads, Fake, Gambling mini, NSFW) | **0** candidates blocked |
| Subtree candidates with listed names inside | 16 → demoted to exact + explicit essential hosts (table below) |
| Ownership: official documentation | Apple Support 101555 (Apple ID, updates, App Store, push, OCSP/CRL, time); Microsoft Learn Windows Update endpoints (`*.windowsupdate.com`, `*.update.microsoft.com`, `*.delivery.mp.microsoft.com`, `*.prod.do.dsp.mp.microsoft.com`); Microsoft Learn Xbox services authentication (`user.auth` / `xsts.auth.xboxlive.com`) |
| Ownership: official site served on the domain (final host + title) | Poste Italiane, SPID, pagoPA, Agenzia Entrate, INPS, App IO (`io.italia.it` → `ioapp.it`), Intesa Sanpaolo, UniCredit, Banco BPM, BPER, MPS, Banca Mediolanum, Fineco (`fineco.it` → `it.finecobank.com`), Banca Sella, Credem, Crédit Agricole Italia, Nexi, PayPal, Stripe, Steam, Xbox, PlayStation, Netflix, Prime Video, Disney+, DAZN, Twitch, Instagram, Facebook, TikTok, X, Reddit, Telegram, WhatsApp, Discord, Snapchat, Amazon.it |
| Ownership: referenced by the official site | `nflxext.com`, `nflximg.net`, `nflxso.net`, `ytimg.com`, `media-amazon.com`, `ssl-images-amazon.com`, `bamgrid.com`, `disney-plus.net`, `indazn.com`, `dazn-api.com`, `jtvnw.net`, `ttvnw.net`, `gql`/`passport.twitch.tv`, `cdninstagram.com`, `fbcdn.net`, `tiktokcdn.com`, `twimg.com`, `api.x.com`, `t.co`, `redditstatic.com`, `discordapp.com`, `cdn.discordapp.com`, `whatsapp.net`, `static.whatsapp.net`, `steamstatic.com`, `steamcommunity.com`, `paypalobjects.com`, `mzstatic.com`, `xboxservices.com`, `playstation.net`, `sonyentertainmentnetwork.com` |
| Ownership: reserved namespace | `*.gov.it` (Italian public administration) |
| **DNS-only** (not observable from official pages) | `googlevideo.com`, `nflxvideo.net`, `aiv-cdn.net`, `aiv-delivery.net`, `pv-cdn.net`, `dssott.com`, `twitchcdn.net`, `steamserver.net`, `steamcontent.com`, `discord.media` — flagged in each entry's `source`; confirm on real devices in Stage C/D |

### Subtree candidates demoted to exact (legitimate blocks inside)

| Namespace | Listed names inside (examples) | Now protected |
|---|---|---|
| `xboxlive.com` | `beacons.xboxlive.com` (Pro) | apex + 11 essential hosts (`user.auth`, `xsts.auth`, `title.auth`, `device.auth`, `title.mgt`, `assets1`, `xflight`, `profile`, `userpresence`, `peoplehub`, `sessiondirectory`) |
| `mp.microsoft.com` | `track.mp.microsoft.com` (Pro) | store catalog/licensing/purchase/collections/storeedge hosts; `delivery.mp.microsoft.com` and `prod.do.dsp.mp.microsoft.com` subtrees (documented) |
| `steampowered.com` | `crash.steampowered.com` (Pro) | apex + store/api/login/help |
| `media-amazon.com` | `metrics.media-amazon.com` (all) | apex + `m.media-amazon.com` |
| `playfabapi.com` | two per-title hosts (all) | apex guard only |
| `playstation.net` | `ad.playstation.net`, `eventcom.api.np.km.playstation.net` | apex + `store.playstation.com`, auth hosts |
| `aiv-cdn.net` | `*.videorolls.row.aiv-cdn.net` (Normal, Pro) | apex |
| `aiv-delivery.net` | `api.{eu-west-1,us-east-1,us-west-2}.aiv-delivery.net` (all, incl. Light) | apex — **device test in Stage C** |
| `indazn.com` | `metrics.`, `telemetry.` (all) | apex |
| `fbcdn.net` | 515 `sonar-*` / `xy`/`xz` names (Pro) | apex + `static.xx`, `scontent.xx` |
| `tiktokv.com` | 182 `log`/`ad`/`location` names (Normal, Pro) | apex + `api.tiktokv.com` |
| `redditmedia.com` | `events.`, `pixel.` (Normal, Pro) | apex |
| `telegram.org` | `promote.`, `ads.` | apex + `web.`, `core.` |
| `whatsapp.net` | `privatestats.`, `crashlogs.`, `dit.` | apex + `g.`, `mmg.`, `static.` |
| `discordapp.net` | `client-metrics.` (Pro) | apex + `media.`, `images-ext-1.` |
| `sc-cdn.net` | `ads-interfaces.` (Normal, Pro) | apex + `cf-st.`, `bolt-gcdn.` |

## 2. Final evaluation (committed configuration)

## Sources

| source | version | last modified | entries | tripwire hits |
|---|---|---|--:|--:|
| `hagezi-multi-pro` | 2026.0913.0815.00 | 2026-09-13 08:15:00+00:00 | 222,607 | 0 |
| `hagezi-tif-mini` | 2026.0913.0749.46 | 2026-09-13 07:49:00+00:00 | 177,540 | 0 |
| `hagezi-light` | 2026.0913.0814.32 | 2026-09-13 08:14:00+00:00 | 34,532 | 0 |
| `hagezi-normal` | 2026.0913.0811.02 | 2026-09-13 08:11:00+00:00 | 180,305 | 0 |

Protected domains: 293

## Compatibility endpoints blocked per group

| group | policy lists | required endpoints | blocked |
|---|---|--:|--:|
| DEFAULT | hagezi-multi-pro, hagezi-tif-mini | 240 | 0 |
| PC | hagezi-multi-pro, hagezi-tif-mini | 240 | 0 |
| GAMING | hagezi-normal, hagezi-tif-mini | 240 | 0 |
| MOBILE | hagezi-multi-pro, hagezi-tif-mini | 240 | 0 |
| SMART-TV | hagezi-light, hagezi-tif-mini | 240 | 0 |
| XBOX | hagezi-light, hagezi-tif-mini | 240 | 0 |

## Must-stay-blockable names (blocked by at least one group's real lists?)

| name | protected? | blocked for groups |
|---|:-:|---|
| beacons.xboxlive.com | no | DEFAULT, PC, MOBILE |
| track.mp.microsoft.com | no | DEFAULT, PC, MOBILE |
| crash.steampowered.com | no | DEFAULT, PC, MOBILE |
| metrics.media-amazon.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| s3-dub-ww.cf.videorolls.row.aiv-cdn.net | no | DEFAULT, PC, GAMING, MOBILE |
| metrics.indazn.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| telemetry.indazn.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| sonar-ams.xx.fbcdn.net | no | DEFAULT, PC, MOBILE |
| log.tiktokv.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| ad.tiktokv.com | no | DEFAULT, PC, GAMING, MOBILE |
| events.redditmedia.com | no | DEFAULT, PC, GAMING, MOBILE |
| pixel.redditmedia.com | no | DEFAULT, PC, GAMING, MOBILE |
| promote.telegram.org | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| ads.telegram.org | no | DEFAULT, PC, MOBILE |
| privatestats.whatsapp.net | no | DEFAULT, PC, GAMING, MOBILE |
| crashlogs.whatsapp.net | no | DEFAULT, PC, MOBILE |
| client-metrics.discordapp.net | no | DEFAULT, PC, MOBILE |
| ads-interfaces.sc-cdn.net | no | DEFAULT, PC, GAMING, MOBILE |
| ad.playstation.net | no | DEFAULT, PC, GAMING, MOBILE |
| 92ab.playfabapi.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| customerevents.netflix.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| ichnaea.netflix.com | no | DEFAULT, PC, MOBILE |
| an.facebook.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| pixel.facebook.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| analytics.tiktok.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| ads-api.twitter.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| tr.snapchat.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |
| evil-tenant.cloudfront.net | no | — (not listed upstream) |
| phishing-tenant.blob.core.windows.net | no | — (not listed upstream) |
| lure.googleusercontent.com | no | — (not listed upstream) |
| bad.storage.googleapis.com | no | — (not listed upstream) |
| telemetry.microsoft.com | no | DEFAULT, PC, MOBILE |
| samsungads.com | no | DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX |

## Watch list (not protected)

| name | hagezi-multi-pro | hagezi-tif-mini | hagezi-light | hagezi-normal |
|---|:-:|:-:|:-:|:-:|
| samsungcloudsolution.com | · | · | · | · |
| samsungotn.net | · | · | · | · |
| lgtvsdp.com | · | · | · | · |
| lgappstv.com | · | · | · | · |
| tools.l.google.com | · | · | · | · |
| epicgames.com | · | · | · | · |
| epicgames.dev | · | · | · | · |
| battle.net | · | · | · | · |
| ea.com | · | · | · | · |
| ubisoft.com | · | · | · | · |
| riotgames.com | · | · | · | · |
| easyanticheat.net | · | · | · | · |
| battleye.com | · | · | · | · |

## 3. Light vs Normal for SMART-TV and XBOX

| Finding (real lists, 2026-09-13) | Light | Normal | Pro |
|---|:-:|:-:|:-:|
| Entries | 34,532 | 180,305 | 222,607 |
| TV-vendor ad domains blocked (`samsungads.com`, `samsungadhub.com`, `lgsmartad.com`) | yes | yes | yes |
| TV-vendor core domains blocked (`samsungcloudsolution.com`, `samsungotn.net`, `lgtvsdp.com`, `lgappstv.com`) | no | no | no |
| Prime Video ad-roll hosts (`*.videorolls.row.aiv-cdn.net`) | no | **yes** | **yes** |
| Prime Video `api.*.aiv-delivery.net` | yes | yes | yes |
| Netflix logging `ichnaea.netflix.com` | no | no | **yes** |
| PlayFab per-title hosts / `ad.playstation.net` | 1 / no | 2 / yes | 2 / yes |
| Microsoft telemetry (`vortex.data`, `telemetry.microsoft.com`) | no | no | yes |
| Xbox essentials, Store, Game Pass, party/multiplayer hosts | allowed | allowed | allowed |
| Required compatibility endpoints blocked (240) | 0 | 0 | 0 |

**Decision:** SMART-TV and XBOX use **Light + TIF Mini**.
- **Light still gives real protection:** TV-vendor ad networks, trackers and telemetry, plus TIF Mini's malware and phishing coverage.
- **It avoids the Normal/Pro-only blocks** most likely to disturb playback on ad-supported streaming tiers (ad-roll hosts) and console title services.
- **GAMING PCs use Normal + TIF Mini.** No list blocks the launchers and anti-cheat checked; Normal avoids Pro-only crash-reporting blocks.

## 4. Light / Normal history and sanity-limit proposal (NOT configured — awaiting owner approval)

## HaGeZi Multi LIGHT (`hagezi-light`)

| committed | version | bytes | lines | rules | valid | invalid | dup | declared ok | added | removed | added % | removed % |
|---|---|--:|--:|--:|--:|--:|--:|:-:|--:|--:|--:|--:|
| 2026-09-01 15:58 | 2026.0901.1507.10 | 927,493 | 41,618 | 41,604 | 41,604 | 0 | 0 | yes | - | - | - | - |
| 2026-09-02 03:54 | 2026.0902.0306.23 | 926,131 | 41,552 | 41,538 | 41,538 | 0 | 0 | yes | 31 | 97 | 0.07% | 0.23% |
| 2026-09-02 08:48 | 2026.0902.0804.12 | 930,796 | 41,700 | 41,686 | 41,686 | 0 | 0 | yes | 788 | 640 | 1.90% | 1.54% |
| 2026-09-03 08:56 | 2026.0903.0810.57 | 854,639 | 37,686 | 37,672 | 37,672 | 0 | 0 | yes | 1,926 | 5,940 | 4.62% | 14.25% |
| 2026-09-04 00:53 | 2026.0903.2259.44 | 854,846 | 37,705 | 37,691 | 37,691 | 0 | 0 | yes | 61 | 42 | 0.16% | 0.11% |
| 2026-09-04 08:55 | 2026.0904.0804.39 | 854,467 | 37,662 | 37,648 | 37,648 | 0 | 0 | yes | 589 | 632 | 1.56% | 1.68% |
| 2026-09-05 00:18 | 2026.0904.2340.05 | 861,303 | 37,947 | 37,933 | 37,933 | 0 | 0 | yes | 338 | 53 | 0.90% | 0.14% |
| 2026-09-05 09:08 | 2026.0905.0822.37 | 855,972 | 37,712 | 37,698 | 37,698 | 0 | 0 | yes | 656 | 891 | 1.73% | 2.35% |
| 2026-09-05 16:03 | 2026.0905.1516.02 | 856,090 | 37,716 | 37,702 | 37,702 | 0 | 0 | yes | 41 | 37 | 0.11% | 0.10% |
| 2026-09-06 08:49 | 2026.0906.0803.18 | 845,445 | 37,195 | 37,181 | 37,181 | 0 | 0 | yes | 1,275 | 1,796 | 3.38% | 4.76% |
| 2026-09-07 08:55 | 2026.0907.0809.33 | 833,038 | 36,622 | 36,608 | 36,608 | 0 | 0 | yes | 745 | 1,318 | 2.00% | 3.54% |
| 2026-09-08 08:58 | 2026.0908.0813.45 | 843,648 | 37,129 | 37,115 | 37,115 | 0 | 0 | yes | 1,630 | 1,123 | 4.45% | 3.07% |
| 2026-09-09 09:04 | 2026.0909.0817.53 | 780,021 | 35,220 | 35,206 | 35,206 | 0 | 0 | yes | 1,947 | 3,856 | 5.25% | 10.39% |
| 2026-09-10 09:16 | 2026.0910.0832.47 | 786,425 | 35,507 | 35,493 | 35,493 | 0 | 0 | yes | 798 | 511 | 2.27% | 1.45% |
| 2026-09-11 09:05 | 2026.0911.0818.11 | 784,223 | 35,411 | 35,397 | 35,397 | 0 | 0 | yes | 665 | 761 | 1.87% | 2.14% |
| 2026-09-12 08:56 | 2026.0912.0812.52 | 781,116 | 35,294 | 35,280 | 35,280 | 0 | 0 | yes | 629 | 746 | 1.78% | 2.11% |
| 2026-09-13 08:57 | 2026.0913.0814.32 | 761,024 | 34,546 | 34,532 | 34,532 | 0 | 0 | yes | 1,008 | 1,756 | 2.86% | 4.98% |

**Summary** (17 versions)

- entries: min 34,532 · median 37,648 · max 41,686
- bytes: min 761,024 · median 854,467 · max 930,796
- added per update: median 1.89% · p90 4.62% · max 5.25%
- removed per update: median 2.13% · p90 10.39% · max 14.25%
- invalid rules total: 0 · duplicates total: 0

## HaGeZi Multi NORMAL (`hagezi-normal`)

| committed | version | bytes | lines | rules | valid | invalid | dup | declared ok | added | removed | added % | removed % |
|---|---|--:|--:|--:|--:|--:|--:|:-:|--:|--:|--:|--:|
| 2026-09-01 15:58 | 2026.0901.1503.31 | 4,292,503 | 190,385 | 190,371 | 190,371 | 0 | 0 | yes | - | - | - | - |
| 2026-09-02 03:54 | 2026.0902.0302.37 | 4,291,453 | 190,323 | 190,309 | 190,309 | 0 | 0 | yes | 213 | 275 | 0.11% | 0.14% |
| 2026-09-02 08:48 | 2026.0902.0800.34 | 4,297,275 | 190,521 | 190,507 | 190,507 | 0 | 0 | yes | 410 | 212 | 0.22% | 0.11% |
| 2026-09-03 08:56 | 2026.0903.0807.15 | 4,297,057 | 190,447 | 190,433 | 190,433 | 0 | 0 | yes | 648 | 722 | 0.34% | 0.38% |
| 2026-09-04 00:53 | 2026.0903.2256.27 | 4,295,386 | 190,413 | 190,399 | 190,399 | 0 | 0 | yes | 229 | 263 | 0.12% | 0.14% |
| 2026-09-04 08:55 | 2026.0904.0801.15 | 4,298,880 | 190,537 | 190,523 | 190,523 | 0 | 0 | yes | 391 | 267 | 0.21% | 0.14% |
| 2026-09-05 00:18 | 2026.0904.2336.31 | 4,347,785 | 192,735 | 192,721 | 192,721 | 0 | 0 | yes | 2,533 | 335 | 1.33% | 0.18% |
| 2026-09-05 09:08 | 2026.0905.0818.50 | 4,349,213 | 192,761 | 192,747 | 192,747 | 0 | 0 | yes | 464 | 438 | 0.24% | 0.23% |
| 2026-09-05 16:03 | 2026.0905.1512.23 | 4,349,050 | 192,753 | 192,739 | 192,739 | 0 | 0 | yes | 123 | 131 | 0.06% | 0.07% |
| 2026-09-06 08:49 | 2026.0906.0759.38 | 4,349,007 | 192,726 | 192,712 | 192,712 | 0 | 0 | yes | 578 | 605 | 0.30% | 0.31% |
| 2026-09-07 08:55 | 2026.0907.0805.53 | 4,329,172 | 191,653 | 191,639 | 191,639 | 0 | 0 | yes | 655 | 1,728 | 0.34% | 0.90% |
| 2026-09-08 08:58 | 2026.0908.0810.00 | 4,333,409 | 191,795 | 191,781 | 191,781 | 0 | 0 | yes | 800 | 658 | 0.42% | 0.34% |
| 2026-09-09 09:04 | 2026.0909.0814.00 | 3,975,504 | 181,431 | 181,417 | 181,417 | 0 | 0 | yes | 1,471 | 11,835 | 0.77% | 6.17% |
| 2026-09-10 09:16 | 2026.0910.0824.30 | 3,981,001 | 181,655 | 181,641 | 181,641 | 0 | 0 | yes | 776 | 552 | 0.43% | 0.30% |
| 2026-09-11 09:05 | 2026.0911.0814.43 | 3,947,063 | 180,065 | 180,051 | 180,051 | 0 | 0 | yes | 582 | 2,172 | 0.32% | 1.20% |
| 2026-09-12 08:56 | 2026.0912.0809.31 | 3,950,568 | 180,155 | 180,141 | 180,141 | 0 | 0 | yes | 677 | 587 | 0.38% | 0.33% |
| 2026-09-13 08:57 | 2026.0913.0811.02 | 3,953,233 | 180,319 | 180,305 | 180,305 | 0 | 0 | yes | 550 | 386 | 0.31% | 0.21% |

**Summary** (17 versions)

- entries: min 180,051 · median 190,433 · max 192,747
- bytes: min 3,947,063 · median 4,297,057 · max 4,349,213
- added per update: median 0.31% · p90 0.77% · max 1.33%
- removed per update: median 0.27% · p90 1.20% · max 6.17%
- invalid rules total: 0 · duplicates total: 0


Proposal, using the same method as A2: entry bounds about 20–25 % beyond the observed extremes; change ratios about 3× the largest single-version change. All values are anomaly thresholds only.

| Source | `min_entries` | `max_entries` | `max_added_ratio` | `max_removed_ratio` |
|---|--:|--:|--:|--:|
| `hagezi-light` | 27,000 | 52,000 | 0.16 | 0.45 |
| `hagezi-normal` | 145,000 | 240,000 | 0.05 | 0.20 |

- **Light is volatile:** it shrank by 14.25 % in one legitimate release. Its removal limit must therefore be wide, or normal releases would be held for review.
- **Sample size:** only 12 days of history are available (as in A2). Re-measure over ≥ 30 days before C3.
