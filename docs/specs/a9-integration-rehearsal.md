# A9 — Offline Integration Rehearsal

- **Status:** done 2026-09-14
- **Related:** [implementation-plan.md](../implementation-plan.md) §A9 ·
  [audits/2026-09-14-a9-security-review.md](../audits/2026-09-14-a9-security-review.md) ·
  `tests/integration/test_a9_rehearsal.py`
- **Constraints:** offline, development machine only. No real Pi, no real Pi-hole, no real
  Telegram send, no network change. This phase produces no application code — it verifies and
  documents what A0–A8 already built.

## 1. Scope

A9 is the capstone of Stage A: prove the whole offline system actually connects end to end, run
the full test suite, review coverage and security, bring documentation up to date, and produce a
"ready for Stage B" checklist. Per the plan, its only exit criterion is: **all suites green, and
the only unresolved placeholders are the ones marked `audit-required`.**

## 2. End-to-end rehearsal

`tests/integration/test_a9_rehearsal.py::test_a9_full_offline_rehearsal` drives the real CLI
entry point (`home_dns.cli.main`, the same one a user runs by hand) — not internal functions in
isolation — through the full chain, with only the physical/external inputs (HTTP fetch, disk
usage, Telegram transport) replaced by injected fakes, exactly like the rest of the suite:

```text
1. validate-config                          -> READY
2. blocklists status                        -> no artifact yet
3. blocklists update --apply (scripted      -> pipeline validates, tripwire-scans, activates;
   fetcher, no real network)                   the mock DNS provider accepts the deployment
4. blocklists status                        -> artifact now current
5. policy explain --group DEFAULT <domain>  -> blocked, via the just-activated list
6. storage status / backup --apply / verify -> all pass against a fake healthy disk
7. monitoring status --apply x2 (fake        -> incident state machine reaches INCIDENT
   95%-full disk)                              (incident_after=2, real state machine)
8. notify test (mock notifier)              -> would-send formatted, dry-run confirmed
9. dashboard backend, built with the exact  -> /api/v1/overview shows open_incidents=1,
   on-disk state steps 1-8 just produced       /api/v1/alerts lists the live "storage" incident
10. collector poll x2 + flush               -> /api/v1/devices returns the provider's 16 clients
11. a third monitoring status (fake healthy  -> incident recovers; a fresh dashboard build shows
    disk)                                       /api/v1/alerts empty again
```

This is the first test in the repository that exercises **pipeline → mock provider → monitoring
→ dashboard backend → dashboard API** as one continuous, real on-disk sequence, rather than each
piece being tested against its own isolated fixtures (which the rest of the suite already does
thoroughly). It runs as part of `make test`/`pytest`, so it stays a permanent regression check,
not a one-off manual exercise.

**Deliberately not rehearsed:** a real Telegram send (never done by this project; a separate,
explicit owner decision no earlier than C3) and a real blocklist download over the Internet
(excluded by the `network` pytest marker; A2's real-source tests already cover that path
separately, opt-in via `pytest -m network`).

## 3. Full test run

```text
pytest:  1123 passed, 2 deselected (network-marked)   — 97.78% coverage (gate: 90%)
vitest:   116 passed                                   (dashboard/frontend/)
ruff, ruff format --check, mypy --strict, tsc          — all clean
npm audit (dashboard/frontend/, scripts/codegen/)       — 0 known vulnerabilities
```

## 4. Coverage review

97.78% overall; every module is above the 90% gate. The two lowest-covered modules were read
directly rather than just trusted:

- `storage/tempfiles.py` (84%): uncovered lines are defensive branches for a symlink escaping
  the temp directory and a `stat()` racing a file's removal mid-sweep — genuine edge cases, not
  untested real logic.
- `storage/disk.py` (89%): the uncovered branch is the "walk up to the nearest existing ancestor"
  fallback in `SystemDiskUsage.get()`, only reachable when `data_dir` has literally never been
  created — exercised implicitly by the OS on a real filesystem, awkward to force in a unit test.

No coverage gap found that hides an actual untested decision.

## 5. Security review

Full review: [audits/2026-09-14-a9-security-review.md](../audits/2026-09-14-a9-security-review.md).
Summary: no critical or high-severity finding; no committed secret; one new low-severity item
(**TD-016**, no automated Python dependency-vulnerability scan) added to the technical-debt
register; existing accepted trade-offs (TD-011–TD-014) re-confirmed, unchanged.

## 6. Documentation pass

- `docs/implementation-plan.md`: A5–A9 now carry the same "✅ done, see ..." marker A0–A4 already
  had (they were implemented but the plan document itself hadn't been updated to say so).
- Filled in five previously-placeholder docs whose underlying feature already exists and is
  stable: [devices.md](../devices.md), [monitoring.md](../monitoring.md),
  [telegram-alerts.md](../telegram-alerts.md), [security.md](../security.md),
  [troubleshooting.md](../troubleshooting.md) — each rewritten from the real, built system, not
  aspirationally.
- **Deliberately left as placeholders:** `installation.md`, `networking.md`, `dns.md`,
  `ipv4.md`, `ipv6.md`, `dns-bypass.md`, and `architecture.md`'s remaining sections. Each depends
  on facts Stage B/C haven't produced yet (real Pi OS details, real Fastweb Box Seven behaviour,
  real Pi-hole install steps) — writing them now would mean inventing content CLAUDE.md §55
  explicitly says not to pretend. They stay `_TODO (Phase N)_`, honestly, until that phase.
- ADR index, CHANGELOG and technical-debt register cross-checked against what's actually merged;
  no stale or missing entries found beyond what's listed above.

## 7. Ready for Stage B checklist

| Item | Status |
|---|---|
| All A0–A9 phases implemented, tested, committed | ✅ |
| Full test suite green (backend + frontend) | ✅ 1123 + 116 passed |
| Coverage above gate, reviewed for hidden gaps | ✅ 97.78%, reviewed |
| Security review performed, no unresolved critical/high finding | ✅ see §5 |
| No secret committed anywhere in the repository | ✅ verified |
| Documentation reflects the real, built system | ✅ see §6 |
| Only remaining unresolved placeholders are config `<<AUDIT:...>>` tokens | ✅ only in `config/app/production.example.yaml`, exactly the ones ADR 0001's gates G1–G5 are meant to resolve |
| ADR 0001 gates G1–G6 | ⏳ still pending — **this is Stage B's job, not A9's** |
| Real Raspberry Pi touched | ❌ not touched (by design) |
| Real network/router/DHCP touched | ❌ not touched (by design) |
| Real Pi-hole installed or contacted | ❌ not done (by design) |
| Real Telegram message sent | ❌ not done (owner decision, deferred to C3) |

## 8. Exit

All suites green; the only unresolved placeholders are `<<AUDIT:...>>` tokens in
`config/app/production.example.yaml`, which exist precisely because they require the Stage B
audits. **Stage A is complete. Ready to begin Stage B (B1: Raspberry Pi audit) whenever SSH
access to the Pi is available — see ADR 0001 gate G1.**
