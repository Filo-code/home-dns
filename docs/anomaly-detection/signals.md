# DNS anomaly detection — signals

Six things `src/home_dns/core/anomaly.py` looks at, all deterministic, all over a small per-device window (`config/anomaly-detection/anomaly-detection.yaml`'s `window_minutes`), none of them machine learning.

## A. NXDOMAIN burst (`nxdomain_burst`)

Counts queries in the last `nxdomain_burst_window_minutes` whose provider-reported `reply_type == "NXDOMAIN"` (a genuine "this domain does not exist" answer, distinct from a Pi-hole block — see `blocked_by`). Fires when the count reaches `nxdomain_burst_count`.

**Why it might matter:** malware using algorithmically generated domain names typically tries many names that don't resolve before hitting a live one.

**Real limitation:** `MockDnsProvider` never sets `reply_type`, so this signal only fires against real Pi-hole data (`PiholeV6Provider`), not in mock/dev-rehearsal mode. This is documented, not hidden.

## B. Query-rate spike (`query_rate_spike`)

Compares the query count in the most recent `query_rate_baseline_minutes` against the count in the *preceding* window of the same length. Fires when `recent >= older * query_rate_spike_multiplier`. If there's no older window yet (a brand-new device), it never fires — there's nothing to compare against, and guessing would be a false positive by construction.

## C. Repeated-domain beaconing (`beaconing`)

For each domain queried at least `beaconing_min_repeats` times in the window, computes the intervals between consecutive queries to that domain and checks how far the *worst* interval deviates from the mean. Fires if that deviation is within `beaconing_interval_tolerance_seconds` — i.e. the queries are suspiciously regular, not just frequent.

**Why "worst deviation" rather than average deviation:** a single irregular gap should be enough to call a pattern "not clockwork," which average-based measures can mask.

## D. High-entropy/random-looking domains (`high_entropy_domain`)

A **heuristic only** — explicitly not a DGA/malware detector, and it will both miss real threats and flag legitimate infrastructure. It looks at the first label of a queried domain (before the first dot) and combines:

- Shannon entropy (bits per character) of the label, compared against `entropy_threshold`.
- Vowel ratio among the label's letters — real words have vowels; random tokens tend not to.
- A minimum label length (`entropy_min_label_length`) — short labels are excluded outright, since entropy is a meaningless measure on 2-3 characters.

A label only counts as "high entropy" if it clears the entropy threshold **and** has a low vowel ratio (under 30%) — entropy alone over-fires on legitimate hash-like CDN/tracking hostnames, which is exactly the false-positive risk this combination is meant to reduce (though it does not eliminate it).

## E. Repeated resolution failures (`repeated_failures`)

Counts queries in the last `failure_burst_window_minutes` whose `reply_type` is `SERVFAIL`, `REFUSED`, or `NOTIMP` — genuine resolution failures, not a normal NXDOMAIN and not a Pi-hole block. Fires at `failure_burst_count`. Same `MockDnsProvider` limitation as signal A applies.

## F. Combined anomaly score

Not a machine-learning probability. Each signal that fires contributes a **fixed, documented weight** (`SIGNAL_WEIGHT` in `core/anomaly.py`):

| Signal | Weight |
|---|--:|
| `nxdomain_burst` | 30 |
| `repeated_failures` | 30 |
| `query_rate_spike` | 25 |
| `beaconing` | 20 |
| `high_entropy_domain` | 15 |

The weights sum (capped at 100) into a `score`, mapped to a severity band:

| Score | Severity |
|---|---|
| 0–29 | `low` |
| 30–59 | `medium` |
| 60+ | `high` |

Every `Anomaly` also carries a deterministic `reason` sentence built from a fixed signal→label mapping (e.g. `"NXDOMAIN rate and query frequency significantly exceed this device's recent baseline"`) — always naming exactly which signals fired, never a vague "suspicious activity" claim.

## Example

```
ANOMALY:
  device_id = 7
  severity  = medium
  signals   = [nxdomain_burst, query_rate_spike]
  score     = 55
  reason    = "NXDOMAIN rate and query frequency significantly exceed this
               device's recent baseline"
```

## Device-group sensitivity

Thresholds are per device-group (`config/anomaly-detection/anomaly-detection.yaml`'s `default` + `overrides`), not hard-coded in `core/anomaly.py`:

- **PC / GAMING** — more permissive (higher counts, higher multipliers) since these devices legitimately generate bursty, varied traffic.
- **MOBILE / DEFAULT** — the shipped `default` thresholds (medium sensitivity).
- **SMART-TV / XBOX** — deliberately conservative: higher counts to trigger, tighter beaconing tolerance (so regular update/telemetry heartbeats don't look like beaconing), higher entropy threshold (so hash-like streaming/CDN hostnames aren't flagged).

Any group not listed in `overrides` falls back to `default` automatically — a new or renamed group is never silently undetected, it just gets the medium profile until someone tunes it.
