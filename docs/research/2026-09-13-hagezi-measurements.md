# HaGeZi Blocklist Measurements — 2026-09-13

> **Purpose:** evidence for A2 sanity limits (owner decision 2026-09-13: measure first, then propose).
> **Method:** `scripts/blocklists/measure_sources.py`. Every version of each list committed to `hagezi/dns-blocklists` since 2026-08-13 was downloaded from `raw.githubusercontent.com` at its commit and parsed with the production parser (`home_dns.core.blocklists`).
> **Caveat:** GitHub history for these files starts at 2026-09-01, so the sample covers **12 days, 17 versions per list**. Re-measure with ≥ 30 days before production activation (C3).

## Point-in-time checks (2026-09-13 19:12 UTC)

| Check | Multi PRO | TIF Mini |
|---|---|---|
| jsDelivr vs GitHub raw | byte-identical (same SHA-256) | byte-identical |
| HTTP | 200, `text/plain; charset=utf-8` on both | same |
| jsDelivr cache | `age: 32828` s, `s-maxage=43200` — content still current | same |
| Header | `Last modified`, `Version`, `Number of entries`, `Expires: 8 hours`, `Syntax: AdBlock` | same |
| Rule syntax | 100 % `\|\|domain^` (0 other forms) | same |
| Punycode rules | 84 | 197 |
| Overlap with the other list | 45,245 domains | 45,245 domains |
| Parse time (Mac, production parser) | ~0.8 s | ~0.9 s |
| Full pipeline dry-run, both lists, both mirrors (network test) | 11.7 s total | |

## HaGeZi Multi PRO (`hagezi-multi-pro`)

| committed | version | bytes | lines | rules | valid | invalid | dup | declared ok | added | removed | added % | removed % |
|---|---|--:|--:|--:|--:|--:|--:|:-:|--:|--:|--:|--:|
| 2026-09-01 15:58 | 2026.0901.1507.38 | 4,967,126 | 225,266 | 225,252 | 225,252 | 0 | 0 | yes | - | - | - | - |
| 2026-09-02 03:54 | 2026.0902.0306.55 | 4,961,704 | 224,988 | 224,974 | 224,974 | 0 | 0 | yes | 277 | 555 | 0.12% | 0.25% |
| 2026-09-02 08:48 | 2026.0902.0804.43 | 4,966,537 | 225,148 | 225,134 | 225,134 | 0 | 0 | yes | 582 | 422 | 0.26% | 0.19% |
| 2026-09-03 08:56 | 2026.0903.0811.27 | 4,955,347 | 224,563 | 224,549 | 224,549 | 0 | 0 | yes | 989 | 1,574 | 0.44% | 0.70% |
| 2026-09-04 00:53 | 2026.0903.2300.14 | 4,959,664 | 224,720 | 224,706 | 224,706 | 0 | 0 | yes | 432 | 275 | 0.19% | 0.12% |
| 2026-09-04 08:55 | 2026.0904.0805.09 | 4,954,281 | 224,456 | 224,442 | 224,442 | 0 | 0 | yes | 577 | 841 | 0.26% | 0.37% |
| 2026-09-05 00:18 | 2026.0904.2343.20 | 4,998,556 | 226,434 | 226,420 | 226,420 | 0 | 0 | yes | 2,570 | 592 | 1.15% | 0.26% |
| 2026-09-05 09:08 | 2026.0905.0823.07 | 4,971,051 | 225,223 | 225,209 | 225,209 | 0 | 0 | yes | 687 | 1,898 | 0.30% | 0.84% |
| 2026-09-05 16:03 | 2026.0905.1516.31 | 4,968,997 | 225,130 | 225,116 | 225,116 | 0 | 0 | yes | 126 | 219 | 0.06% | 0.10% |
| 2026-09-06 08:49 | 2026.0906.0803.59 | 4,960,439 | 224,811 | 224,797 | 224,797 | 0 | 0 | yes | 805 | 1,124 | 0.36% | 0.50% |
| 2026-09-07 08:55 | 2026.0907.0810.01 | 4,945,929 | 224,025 | 224,011 | 224,011 | 0 | 0 | yes | 938 | 1,724 | 0.42% | 0.77% |
| 2026-09-08 08:58 | 2026.0908.0814.14 | 4,948,384 | 224,040 | 224,026 | 224,026 | 0 | 0 | yes | 1,283 | 1,268 | 0.57% | 0.57% |
| 2026-09-09 09:04 | 2026.0909.0818.25 | 4,955,570 | 224,159 | 224,145 | 224,145 | 0 | 0 | yes | 1,673 | 1,554 | 0.75% | 0.69% |
| 2026-09-10 09:16 | 2026.0910.0833.25 | 4,952,223 | 223,948 | 223,934 | 223,934 | 0 | 0 | yes | 1,154 | 1,365 | 0.51% | 0.61% |
| 2026-09-11 09:05 | 2026.0911.0818.40 | 4,917,441 | 222,299 | 222,285 | 222,285 | 0 | 0 | yes | 892 | 2,541 | 0.40% | 1.13% |
| 2026-09-12 08:56 | 2026.0912.0813.21 | 4,923,964 | 222,525 | 222,511 | 222,511 | 0 | 0 | yes | 953 | 727 | 0.43% | 0.33% |
| 2026-09-13 08:57 | 2026.0913.0815.00 | 4,924,111 | 222,621 | 222,607 | 222,607 | 0 | 0 | yes | 801 | 705 | 0.36% | 0.32% |

**Summary** (17 versions)

- entries: min 222,285 · median 224,549 · max 226,420
- bytes: min 4,917,441 · median 4,955,570 · max 4,998,556
- added per update: median 0.38% · p90 0.75% · max 1.15%
- removed per update: median 0.44% · p90 0.84% · max 1.13%
- invalid rules total: 0 · duplicates total: 0

## HaGeZi Threat Intelligence Feeds (mini) (`hagezi-tif-mini`)

| committed | version | bytes | lines | rules | valid | invalid | dup | declared ok | added | removed | added % | removed % |
|---|---|--:|--:|--:|--:|--:|--:|:-:|--:|--:|--:|--:|
| 2026-09-01 15:58 | 2026.0901.1443.49 | 3,747,248 | 176,632 | 176,619 | 176,619 | 0 | 0 | yes | - | - | - | - |
| 2026-09-02 03:54 | 2026.0902.0243.13 | 3,739,262 | 176,258 | 176,245 | 176,245 | 0 | 0 | yes | 440 | 814 | 0.25% | 0.46% |
| 2026-09-02 08:48 | 2026.0902.0739.47 | 3,738,320 | 176,181 | 176,168 | 176,168 | 0 | 0 | yes | 562 | 639 | 0.32% | 0.36% |
| 2026-09-03 08:56 | 2026.0903.0745.51 | 3,713,631 | 175,055 | 175,042 | 175,042 | 0 | 0 | yes | 1,575 | 2,701 | 0.89% | 1.53% |
| 2026-09-04 00:53 | 2026.0903.2238.07 | 3,705,911 | 174,767 | 174,754 | 174,754 | 0 | 0 | yes | 708 | 996 | 0.40% | 0.57% |
| 2026-09-04 08:55 | 2026.0904.0741.16 | 3,697,441 | 174,370 | 174,357 | 174,357 | 0 | 0 | yes | 808 | 1,205 | 0.46% | 0.69% |
| 2026-09-05 00:18 | 2026.0904.2324.03 | 3,680,091 | 173,628 | 173,615 | 173,615 | 0 | 0 | yes | 540 | 1,282 | 0.31% | 0.74% |
| 2026-09-05 09:08 | 2026.0905.0759.08 | 3,815,677 | 180,581 | 180,568 | 180,568 | 0 | 0 | yes | 10,151 | 3,198 | 5.85% | 1.84% |
| 2026-09-05 16:03 | 2026.0905.1451.14 | 3,807,095 | 180,264 | 180,251 | 180,251 | 0 | 0 | yes | 308 | 625 | 0.17% | 0.35% |
| 2026-09-06 08:49 | 2026.0906.0741.25 | 3,779,350 | 178,922 | 178,909 | 178,909 | 0 | 0 | yes | 1,099 | 2,441 | 0.61% | 1.35% |
| 2026-09-07 08:55 | 2026.0907.0743.22 | 3,763,429 | 178,262 | 178,249 | 178,249 | 0 | 0 | yes | 2,808 | 3,468 | 1.57% | 1.94% |
| 2026-09-08 08:58 | 2026.0908.0749.13 | 3,797,358 | 179,917 | 179,904 | 179,904 | 0 | 0 | yes | 3,963 | 2,308 | 2.22% | 1.29% |
| 2026-09-09 09:04 | 2026.0909.0752.19 | 3,739,554 | 177,392 | 177,379 | 177,379 | 0 | 0 | yes | 1,558 | 4,083 | 0.87% | 2.27% |
| 2026-09-10 09:16 | 2026.0910.0800.38 | 3,726,934 | 176,813 | 176,800 | 176,800 | 0 | 0 | yes | 1,991 | 2,570 | 1.12% | 1.45% |
| 2026-09-11 09:05 | 2026.0911.0751.56 | 3,732,258 | 177,000 | 176,987 | 176,987 | 0 | 0 | yes | 2,513 | 2,326 | 1.42% | 1.32% |
| 2026-09-12 08:56 | 2026.0912.0749.59 | 3,738,072 | 177,420 | 177,407 | 177,407 | 0 | 0 | yes | 2,105 | 1,685 | 1.19% | 0.95% |
| 2026-09-13 08:57 | 2026.0913.0749.46 | 3,740,661 | 177,553 | 177,540 | 177,540 | 0 | 0 | yes | 1,250 | 1,117 | 0.70% | 0.63% |

**Summary** (17 versions)

- entries: min 173,615 · median 176,987 · max 180,568
- bytes: min 3,680,091 · median 3,739,262 · max 3,815,677
- added per update: median 0.79% · p90 2.22% · max 5.85%
- removed per update: median 1.12% · p90 1.94% · max 2.27%
- invalid rules total: 0 · duplicates total: 0

## Observations

1. **Structure.** 0 invalid rules and 0 duplicates in all 34 versions. The declared `Number of entries` equalled the parsed rule count in 34/34 versions, so a mismatch is a reliable truncation signal.
2. **Cadence.** HaGeZi published 1–3 versions per day. A 24 h update interval can therefore combine several releases into one delta.
3. **Multi PRO is stable.** Entries varied within ±1 % of the median. The per-version change never exceeded 1.15 % added / 1.13 % removed.
4. **TIF Mini is more volatile.** It had one legitimate release with **+5.85 % added** (2026-09-05 09:08). This confirms that a large change must be an *anomaly to review*, not an automatic failure.
5. **Freshness.** `Expires: 8 hours`. The freshest version was ~11 h old when downloaded. A 48 h freshness limit leaves ample headroom.

## Sanity limits (approved by the owner 2026-09-13 and configured in `config/blocklists/sources.yaml`)

These are **anomaly thresholds**. Exceeding one holds the update for review and keeps the previous artifact. Nothing is deleted or failed.

| Source | `min_entries` | `max_entries` | `max_added_ratio` | `max_removed_ratio` |
|---|--:|--:|--:|--:|
| `hagezi-multi-pro` | 180,000 | 280,000 | 0.05 | 0.05 |
| `hagezi-tif-mini` | 140,000 | 225,000 | 0.12 | 0.08 |

How the numbers were derived:
- **Entry bounds** sit about 19–25 % beyond the observed extremes (Multi PRO 222,285–226,420; TIF Mini 173,615–180,568). They catch truncated, wrong or runaway lists without reacting to normal drift.
- **Change ratios** allow about 3–4× the largest observed single-version change (Multi PRO 1.15 % / 1.13 %; TIF Mini 5.85 % / 2.27 %), because one 24 h run can span up to three releases.

Hard guards in code (reject or fail, independent of the limits above), with a proposed adjustment:

| Guard | Current default | Observed | Proposal |
|---|---|---|---|
| Invalid-rule ratio (format check) | ~~5 %~~ → **1 %** (approved) | 0.00 % | applied |
| Body size | 1 KiB – 50 MiB | 3.68 – 5.00 MB | keep |
| Declared entries = parsed rules | required when declared | 34/34 | keep |
| Freshness (`Last modified`) | 48 h (owner-approved) | ≤ ~11 h | keep |
| Future-dated header | > 15 min skew rejected | — | keep |

## Follow-up

- **Re-measure** over at least 30 days of history before production activation (C3), using `scripts/blocklists/measure_sources.py`. Propose refinements if the longer dataset warrants them.
