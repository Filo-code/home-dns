# DNS anomaly detection — architecture

Passive, deterministic, non-ML behavioral signal detection layered on top of the existing A7 query/aggregation pipeline. Implemented in `src/home_dns/core/anomaly.py` (pure logic), `src/home_dns/config/anomaly.py` (thresholds, loaded from `config/anomaly-detection/anomaly-detection.yaml`), `src/home_dns/storage/dashboard.py` (the `anomalies` table), `src/home_dns/collector.py` (wiring), and `src/home_dns/api/views.py` (read-only endpoints). See `docs/anomaly-detection/signals.md` for what each individual signal means.

## Design goals and how they're met

1. **Completely outside the DNS critical path.** The analyzer only ever sees `QueryLogEntry` objects the collector already fetched from the provider *after* Pi-hole has answered. It makes no provider calls of its own.
2. **Never decides allow/block.** `AnomalyAnalyzer.observe()` only returns `Anomaly` events; nothing in this layer can influence what Pi-hole does with a query.
3. **Never modifies Pi-hole configuration.** No code path in `core/anomaly.py`, `config/anomaly.py`, or the collector wiring calls any provider mutation method.
4. **Fully disableable.** `config/anomaly-detection/anomaly-detection.yaml`'s `enabled: false` (the shipped default) means `cli.py` never constructs an `AnomalyAnalyzer` at all — the collector runs exactly as it did before this feature existed.
5. **Works with existing aggregated data.** The analyzer is fed from the same in-memory `QueryLogEntry` batch the collector already reads per poll; it does not add a second data source or a second polling loop.
6. **Never stores raw queries indefinitely.** The analyzer's per-device window (domains, timestamps, reply kinds) lives only in a bounded, in-memory `deque` (`AnalyzerConfig.window_minutes` / `max_entries_per_device`) — it is never written to disk. Only the small, *derived* `Anomaly` events (a handful of named signals, a score, a short sentence) are persisted, in a new `anomalies` SQLite table, with its own configurable retention (`retention_days`) applied the same way the existing rollup retention already is.
7. **Low CPU/RAM.** Detection is simple arithmetic (counts, means, a Shannon-entropy calculation) over a bounded window per device — no ML, no external services, no additional processes.
8. **All thresholds configurable.** Every number `core/anomaly.py`'s detectors use comes from `AnomalyThresholds`, loaded per device-group from YAML — nothing is a magic constant in the detection code itself.
9. **Avoids false-positive-heavy behavior for SMART-TV/XBOX.** These groups get deliberately conservative thresholds (higher counts, tighter beaconing tolerance, higher entropy threshold) — see the shipped config's `overrides` section and its comments.
10. **Explainable detections.** Every `Anomaly` carries the exact named signals that fired, a deterministic additive `score` (never presented as a probability), and a plain-language `reason` sentence built from a fixed signal→label mapping — never a black-box verdict.

## Data flow

```
Provider (Pi-hole) query_log()
        │
        ▼
Collector.poll()  ──────────────► existing Rollup aggregation (unchanged)
        │
        ▼ (device_id, QueryLogEntry) pairs, already resolved
AnomalyAnalyzer.observe()  (in-memory window per device, bounded)
        │
        ▼ Anomaly events only (small, derived)
Collector.flush()  ──► DashboardStore.flush()  ──► `anomalies` table (SQLite)
                                                          │
                                                          ▼
                                          GET /api/v1/anomalies (+ /{id}, /devices/{id}/anomalies)
                                                          │
                                                          ▼
                                        Security page, "Anomalie DNS" card (dashboard frontend)
```

If the analyzer raises for any reason, `Collector.poll()` catches it and logs a warning — the poll's normal metrics aggregation (the existing Rollup path) is completely unaffected, and no anomaly for that cycle is recorded. This was verified directly (`tests/unit/test_collector.py::test_broken_analyzer_does_not_break_the_collector`).

## Device identity and group thresholds

The analyzer receives a `device_id → group_id` map, refreshed once per poll from `DashboardStore.list_devices()` (cheap at this device count). Thresholds are looked up per group via `AnalyzerConfig.thresholds_for(group_id)`, falling back to the `DEFAULT` group's thresholds for any group without an explicit override — so a newly-created or renamed group never silently gets zero detection, it gets the medium-sensitivity default.

## Monitoring — deliberately kept separate

Anomalies are **not** infrastructure incidents. They are stored in a new `anomalies` table, distinct from the existing `incident_events` table and the `IncidentState` (`OK → SUSPECT → INCIDENT → RECOVERING`) state machine in `core/monitoring.py` — that machine is untouched by this work. An anomaly is a single, standalone, scored event, not a state with transitions. No automatic Telegram alert integration was added in this phase; the existing A6 notifier/alerting code is completely unmodified. Connecting severe anomalies to alerts is a deliberate future decision, not made here.

## What this is not

- Not a DGA/malware classifier. `looks_high_entropy()` is explicitly documented (in code and in `docs/anomaly-detection/signals.md`) as a heuristic that both under- and over-fires.
- Not a replacement for, or complement to, eBPF-based observability (see the technology-scouting review) — this stays purely at the DNS-query level, using data the app already has.
- Not wired into Telegram alerts yet, and not exposed anywhere that could influence Pi-hole's own blocking behavior.
