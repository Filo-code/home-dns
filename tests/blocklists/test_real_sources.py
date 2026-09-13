"""Real downloads of the approved lists (Internet required; excluded from `make test`).

    uv run pytest -m network tests/blocklists

Dry-run only: nothing is activated, nothing touches a Raspberry Pi or a DNS provider.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_dns.config.filtering import load_filtering_config
from home_dns.core.filtering import ProtectedDomain
from home_dns.pipeline.blocklists import Outcome, PipelineOptions, Stage, StageStatus, run_update
from home_dns.pipeline.fetch import HttpxFetcher
from home_dns.providers.mock import MockDnsProvider
from home_dns.storage.artifacts import ArtifactStore


@pytest.mark.network
def test_approved_sources_pass_the_pipeline_from_both_mirrors(
    repo_config_dir: Path, tmp_path: Path
) -> None:
    now = datetime.now(UTC)
    config = load_filtering_config(repo_config_dir, now=now).config
    # A protected domain that must not appear in either list, so the tripwire actually runs.
    protected = [
        ProtectedDomain(domain="googlevideo.com", reason="YouTube video", source="CLAUDE.md §25")
    ]
    for source in config.sources:
        for role in ("primary", "fallback"):
            url = source.urls.primary if role == "primary" else source.urls.fallback
            single = source.model_copy(
                update={"urls": source.urls.model_copy(update={"primary": url, "fallback": None})}
            )
            [report] = run_update(
                [single],
                protected=protected,
                fetcher=HttpxFetcher(),
                store=ArtifactStore(tmp_path / role),
                test_provider_factory=MockDnsProvider,
                options=PipelineOptions(now=now),
            )
            assert report.outcome is Outcome.WOULD_ACTIVATE, (source.id, role, report.attempts)
            tripwire = next(s for s in report.stages if s.stage is Stage.TRIPWIRE)
            assert tripwire.status is StageStatus.PASSED
            assert report.stats["invalid_rules"] == 0
