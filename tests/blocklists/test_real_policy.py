"""Real HaGeZi lists against the committed A3 policy (Internet required; excluded from `make test`).

    uv run pytest -m network tests/blocklists

Read-only: downloads into a temporary directory, never activates anything.
"""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

from home_dns.config.filtering import load_filtering_config
from home_dns.core.blocklists import BlockEntry, find_tripwire_hits, parse_list
from home_dns.core.policy import PolicyEngine
from home_dns.pipeline.fetch import USER_AGENT

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.network
def test_real_lists_do_not_trip_protected_domains_or_break_compatibility() -> None:
    now = datetime.now(UTC)
    config = load_filtering_config(REPO / "config", now=now).config
    catalog = yaml.safe_load((REPO / "tests" / "data" / "compatibility.yaml").read_text())
    client = httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT})
    lists: dict[str, frozenset[BlockEntry]] = {}
    for source in config.sources:
        text = client.get(str(source.urls.primary)).raise_for_status().text
        entries = parse_list(text, source.format).entries
        hits = find_tripwire_hits(entries, config.protected_domains())
        assert hits == [], (source.id, hits[:10])
        lists[source.id] = entries

    engine = PolicyEngine(config, lists, now=now)
    for group in (g.id for g in config.groups):
        for service in catalog["services"]:
            for domain in service["required"]:
                decision = engine.decide(group, domain)
                assert not decision.blocked, (group, service["name"], domain, decision.detail)
