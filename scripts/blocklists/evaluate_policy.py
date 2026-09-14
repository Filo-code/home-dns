"""Evaluate the committed filtering policy against real blocklists (research tool, needs Internet).

Downloads (or reuses from --cache-dir) every catalogued source, then reports:
  * protected-domain tripwire hits per source (must be 0 for activation);
  * compatibility endpoints blocked for each group under its real policy (must be 0);
  * must-stay-blockable names that the policy no longer blocks for any group;
  * watch-list names blocked per source.

    PYTHONPATH=src uv run python scripts/blocklists/evaluate_policy.py \
        --cache-dir /tmp/eval > report.md

Read-only: never touches the artifact store, the Raspberry Pi or any DNS provider.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from home_dns.config.filtering import load_filtering_config
from home_dns.config.loader import default_config_dir
from home_dns.core.blocklists import BlockEntry, find_tripwire_hits, parse_list
from home_dns.core.policy import PolicyEngine
from home_dns.pipeline.fetch import USER_AGENT

CATALOG = Path(__file__).resolve().parents[2] / "tests" / "data" / "compatibility.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(UTC)
    config = load_filtering_config(default_config_dir(), now=now).config
    catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    client = httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT})

    lists: dict[str, frozenset[BlockEntry]] = {}
    print(f"# A3 policy evaluation\n\nGenerated {now.isoformat(timespec='minutes')}.\n")
    print("## Sources\n\n| source | version | last modified | entries | tripwire hits |")
    print("|---|---|---|--:|--:|")
    protected = config.protected_domains()
    for source in config.sources:
        cached = args.cache_dir / f"{source.id}.txt"
        if not cached.is_file():
            args.cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(client.get(str(source.urls.primary)).raise_for_status().content)
        parsed = parse_list(cached.read_text(encoding="utf-8"), source.format)
        lists[source.id] = parsed.entries
        hits = find_tripwire_hits(parsed.entries, protected)
        print(
            f"| `{source.id}` | {parsed.header.version} | {parsed.header.last_modified} | "
            f"{len(parsed.entries):,} | {len(hits)} |"
        )
        for hit in hits[:20]:
            print(f"|  | hit | {hit.entry.domain} → {hit.protected_domain} ({hit.relation}) | | |")

    engine = PolicyEngine(config, lists, now=now)
    groups = [g.id for g in config.groups]
    print(f"\nProtected domains: {len(protected)}\n")
    print("## Compatibility endpoints blocked per group\n")
    print("| group | policy lists | required endpoints | blocked |")
    print("|---|---|--:|--:|")
    failures = 0
    for group in groups:
        required = [
            d
            for s in catalog["services"]
            for d in s["required"]
            if s["groups"] == ["*"] or group in s["groups"]
        ]
        blocked = [d for d in required if engine.decide(group, d).blocked]
        failures += len(blocked)
        print(
            f"| {group} | {', '.join(engine.sources_for(group))} | {len(required)} | "
            f"{len(blocked)}{': ' + ', '.join(blocked) if blocked else ''} |"
        )

    print("\n## Must-stay-blockable names (blocked by at least one group's real lists?)\n")
    print("| name | protected? | blocked for groups |")
    print("|---|:-:|---|")
    for name in catalog["must_stay_blockable"]:
        decisions = {g: engine.decide(g, name) for g in groups}
        protected_hit = any(d.reason.value == "protected" for d in decisions.values())
        blocked_for = [g for g, d in decisions.items() if d.blocked]
        groups_text = ", ".join(blocked_for) or "— (not listed upstream)"
        print(f"| {name} | {'YES' if protected_hit else 'no'} | {groups_text} |")

    print("\n## Watch list (not protected)\n")
    print("| name | " + " | ".join(lists) + " |")
    print("|---|" + ":-:|" * len(lists))
    for name in catalog["watch"]:
        row = []
        for source_id in lists:
            labels = name.split(".")
            listed = any(
                BlockEntry(".".join(labels[i:]), True) in lists[source_id]
                for i in range(len(labels) - 1)
            )
            row.append("blocked" if listed else "·")
        print(f"| {name} | " + " | ".join(row) + " |")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
