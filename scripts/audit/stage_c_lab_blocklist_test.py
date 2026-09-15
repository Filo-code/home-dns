#!/usr/bin/env python3
"""Stage C lab-only DNS blocklist coverage test.

Read-only: sends DNS queries (via `dig`) at one explicitly named resolver and
reports what came back. Makes no configuration changes, sends no HTTP
requests, visits no sites. Belongs in scripts/audit/ per scripts/README.md's
"Read-only. Never change the system" rule.

This is a lab verification tool for the real Pi-hole v6 instance installed
during Stage C. It is NOT part of the production A2 blocklist pipeline
(home_dns.core.blocklists / pipeline/blocklists.py) and does not replace it.
See docs/audits/2026-09-15-stage-c-pihole-lab.md for how this lab-loading
method differs from the eventual production path
(PiholeV6Provider.deploy_blocklist()).

Usage:
    python scripts/audit/stage_c_lab_blocklist_test.py --resolver 192.168.1.121
    python scripts/audit/stage_c_lab_blocklist_test.py --resolver 127.0.0.1 --json-out out.json
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTECTED_DOMAINS_DIR = REPO_ROOT / "config" / "protected-domains"

# Domains expected to be BLOCKED by the two lists loaded in this lab
# (HaGeZi Multi PRO id=2, HaGeZi TIF Mini id=3 — see config/blocklists/sources.yaml).
# Each entry was confirmed present, verbatim, in the actual downloaded list content
# on the Pi (/etc/pihole/listsCache/list.{2,3}.latest.domains) on 2026-09-15 —
# not guessed. No entry here is a live malicious site; these are DNS names only,
# queried at the A/AAAA level, never fetched over HTTP.
SHOULD_BLOCK: dict[str, list[str]] = {
    "advertising": [
        "googlesyndication.com",
        "ad.ae.doubleclick.net",
        "appvast.adsafeprotected.com",
    ],
    "trackers": [
        "scorecardresearch.com",
        "quantserve.com",
        "hotjar.com",
        "mixpanel.com",
    ],
    "telemetry": [
        "ccg-telemetry.01republic.io",
        "analytics.004gmbh.de",
    ],
    "malware-phishing": [
        "malware.kingbillydrinks.co.uk",
        "allegrolokalnie.0-230-23.rest",
    ],
}


@dataclass
class QueryResult:
    domain: str
    category: str
    expected_block: bool
    status: str
    answers: list[str]
    latency_ms: float
    outcome: str  # blocked_expected | allowed_expected | unexpected_blocked | unexpected_allowed | dns_error
    control_status: str | None = None
    control_answers: list[str] | None = None


def load_protected_domains() -> dict[str, list[str]]:
    """Read config/protected-domains/*.yaml — the project's canonical allow set."""
    by_category: dict[str, list[str]] = {}
    for path in sorted(PROTECTED_DOMAINS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        category = data["category"]
        by_category[category] = [entry["domain"] for entry in data["domains"]]
    return by_category


def dig(domain: str, resolver: str, port: int, timeout: float) -> tuple[str, list[str], float]:
    """Run `dig` once against the given resolver. Returns (status, answers, latency_ms)."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [
                "dig",
                f"@{resolver}",
                "-p",
                str(port),
                domain,
                "A",
                "+time=" + str(int(timeout)),
                "+tries=1",
                "+noall",
                "+answer",
                "+comments",
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", [], (time.monotonic() - start) * 1000

    latency_ms = (time.monotonic() - start) * 1000
    status = "UNKNOWN"
    for line in proc.stdout.splitlines():
        if line.startswith(";; ->>HEADER<<-") and "status:" in line:
            status = line.split("status:")[1].split(",")[0].strip()
            break

    # dig right-pads/aligns columns with a mix of tabs and spaces depending on
    # name length, so split on whitespace rather than matching literal "\tA\t"
    # (a naive substring match silently drops A records on long CNAME chains).
    answers = []
    for line in proc.stdout.splitlines():
        if not line or line.startswith(";"):
            continue
        fields = line.split()
        if len(fields) >= 5 and fields[3] == "A":
            answers.append(fields[4])
    return status, answers, latency_ms


def _is_blocked(status: str, answers: list[str]) -> bool:
    is_null = all(a in {"0.0.0.0", "::"} for a in answers) if answers else False
    return status == "NXDOMAIN" or is_null or (status == "NOERROR" and not answers)


def classify(
    status: str,
    answers: list[str],
    expected_block: bool,
    control_status: str | None = None,
    control_answers: list[str] | None = None,
) -> str:
    if status in {"TIMEOUT", "SERVFAIL", "UNKNOWN"}:
        return "dns_error"
    blocked = _is_blocked(status, answers)
    if blocked and expected_block:
        return "blocked_expected"
    if not blocked and not expected_block:
        return "allowed_expected"
    if not blocked and expected_block:
        return "unexpected_allowed"
    # blocked and not expected_block: looks like an over-block. Before calling it
    # that, rule out "this apex simply has no A record at all" (e.g. an NS-only
    # zone like root-servers.net, or a CDN parent zone with no A record of its
    # own) by checking the SAME query against an unfiltered control resolver.
    if control_status is not None:
        if _is_blocked(control_status, control_answers or []):
            return "no_a_record_upstream"
    return "unexpected_blocked"


def run(resolver: str, port: int, timeout: float, control_resolver: str | None) -> list[QueryResult]:
    results: list[QueryResult] = []

    for category, domains in SHOULD_BLOCK.items():
        for domain in domains:
            status, answers, latency_ms = dig(domain, resolver, port, timeout)
            outcome = classify(status, answers, expected_block=True)
            results.append(QueryResult(domain, category, True, status, answers, round(latency_ms, 1), outcome))

    for category, domains in load_protected_domains().items():
        for domain in domains:
            status, answers, latency_ms = dig(domain, resolver, port, timeout)
            control_status: str | None = None
            control_answers: list[str] | None = None
            # Only spend a second query when the first result looks blocked —
            # most protected domains resolve fine and need no control check.
            if control_resolver and _is_blocked(status, answers):
                control_status, control_answers, _ = dig(domain, control_resolver, port, timeout)
            outcome = classify(status, answers, expected_block=False, control_status=control_status, control_answers=control_answers)
            results.append(
                QueryResult(
                    domain, category, False, status, answers, round(latency_ms, 1), outcome,
                    control_status=control_status, control_answers=control_answers,
                )
            )

    return results


def summarize(results: list[QueryResult]) -> dict[str, int]:
    summary = {
        "total": len(results),
        "blocked_expected": 0,
        "allowed_expected": 0,
        "unexpected_blocked": 0,
        "unexpected_allowed": 0,
        "no_a_record_upstream": 0,
        "dns_error": 0,
    }
    for r in results:
        summary[r.outcome] += 1
    return summary


def print_human(results: list[QueryResult], summary: dict[str, int]) -> None:
    width = max(len(r.domain) for r in results)
    for r in results:
        flag = "!!" if r.outcome.startswith("unexpected") or r.outcome == "dns_error" else "  "
        print(f"{flag} {r.domain:<{width}}  [{r.category:<16}]  {r.outcome:<18}  {r.status:<9}  {r.latency_ms:>6.1f}ms")
    print()
    print("Summary:", json.dumps(summary, indent=2))
    if summary["unexpected_blocked"]:
        print("\nCRITICAL: protected domain(s) were blocked — see unexpected_blocked rows above.")
    if summary["dns_error"]:
        print(f"\nWARNING: {summary['dns_error']} quer(y/ies) failed to resolve at all (timeout/SERVFAIL).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolver", required=True, help="Resolver IP to query (e.g. the Pi's LAN address or 127.0.0.1). Not hard-coded on purpose.")
    parser.add_argument("--port", type=int, default=53)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument(
        "--control-resolver",
        default=None,
        help="Unfiltered resolver (e.g. the router) to re-check apparent blocks against, "
        "so an apex domain with no A record upstream isn't misreported as an over-block.",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--text-out", type=Path, default=None)
    args = parser.parse_args()

    results = run(args.resolver, args.port, args.timeout, args.control_resolver)
    summary = summarize(results)

    if args.json_out:
        payload = {"resolver": args.resolver, "port": args.port, "summary": summary, "results": [asdict(r) for r in results]}
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"JSON written to {args.json_out}")

    if args.text_out:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_human(results, summary)
        args.text_out.write_text(buf.getvalue(), encoding="utf-8")
        print(f"Text report written to {args.text_out}")

    print_human(results, summary)

    return 1 if (summary["unexpected_blocked"] or summary["dns_error"]) else 0


if __name__ == "__main__":
    sys.exit(main())
