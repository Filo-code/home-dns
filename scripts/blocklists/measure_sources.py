"""Measure historical versions of catalogued blocklists (research tool, needs Internet).

For each source whose fallback URL is a raw.githubusercontent.com file, list the commits that
touched it since --since, download each version, parse it with the production parser and print
per-version statistics plus update-to-update deltas as Markdown.

    PYTHONPATH=src uv run python scripts/blocklists/measure_sources.py \
        --since 2026-08-13 --cache-dir /tmp/measure > report.md

Read-only: never touches the artifact store, the Raspberry Pi or any DNS provider.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from home_dns.config.filtering import load_filtering_config
from home_dns.config.loader import default_config_dir
from home_dns.core.blocklists import compute_delta, parse_list
from home_dns.pipeline.fetch import USER_AGENT


def _github_parts(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    if parsed.hostname != "raw.githubusercontent.com":
        raise ValueError(f"not a raw GitHub URL: {url}")
    owner, repo, _branch, *path = parsed.path.strip("/").split("/")
    return owner, repo, "/".join(path)


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="ISO date, e.g. 2026-08-13")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--source", action="append")
    args = parser.parse_args()

    config = load_filtering_config(default_config_dir(), now=datetime.now(UTC)).config
    client = httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
    print(
        f"# Blocklist measurements\n\nGenerated {datetime.now(UTC).isoformat(timespec='minutes')}"
        f" from commits since {args.since}.\n"
    )

    for source in config.sources:
        if args.source and source.id not in args.source:
            continue
        owner, repo, path = _github_parts(str(source.urls.fallback))
        commits = (
            client.get(
                f"https://api.github.com/repos/{owner}/{repo}/commits",
                params={"path": path, "since": f"{args.since}T00:00:00Z", "per_page": 100},
            )
            .raise_for_status()
            .json()
        )
        versions = []
        for commit in reversed(commits):  # oldest first
            sha = commit["sha"]
            cached = args.cache_dir / source.id / f"{sha}.txt"
            if not cached.is_file():
                cached.parent.mkdir(parents=True, exist_ok=True)
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{path}"
                cached.write_bytes(client.get(raw_url).raise_for_status().content)
            body = cached.read_bytes()
            versions.append(
                (
                    commit["commit"]["committer"]["date"],
                    sha,
                    len(body),
                    parse_list(body.decode("utf-8"), source.format),
                )
            )

        print(f"## {source.name} (`{source.id}`)\n")
        print(
            "| committed | version | bytes | lines | rules | valid | invalid | dup | declared ok "
            "| added | removed | added % | removed % |"
        )
        print("|---|---|--:|--:|--:|--:|--:|--:|:-:|--:|--:|--:|--:|")
        added_ratios: list[float] = []
        removed_ratios: list[float] = []
        previous = None
        for committed, _sha, size, parsed in versions:
            delta = compute_delta(previous.entries, parsed.entries) if previous else None
            if delta:
                added_ratios.append(delta.added_ratio)
                removed_ratios.append(delta.removed_ratio)
            declared_ok = parsed.header.declared_entries == parsed.rule_lines
            cells = [
                committed[:16].replace("T", " "),
                parsed.header.version or "-",
                f"{size:,}",
                f"{parsed.total_lines:,}",
                f"{parsed.rule_lines:,}",
                f"{len(parsed.entries):,}",
                str(parsed.invalid_count),
                str(parsed.duplicate_count),
                "yes" if declared_ok else "NO",
                f"{delta.added:,}" if delta else "-",
                f"{delta.removed:,}" if delta else "-",
                f"{delta.added_ratio:.2%}" if delta else "-",
                f"{delta.removed_ratio:.2%}" if delta else "-",
            ]
            print("| " + " | ".join(cells) + " |")
            previous = parsed

        entries = [len(v[3].entries) for v in versions]
        sizes = [v[2] for v in versions]
        print(f"\n**Summary** ({len(versions)} versions)\n")
        print(
            f"- entries: min {min(entries):,} · median {int(statistics.median(entries)):,} · "
            f"max {max(entries):,}"
        )
        print(
            f"- bytes: min {min(sizes):,} · median {int(statistics.median(sizes)):,} · "
            f"max {max(sizes):,}"
        )
        if added_ratios:
            print(
                f"- added per update: median {statistics.median(added_ratios):.2%} · "
                f"p90 {_pct(added_ratios, 0.9):.2%} · max {max(added_ratios):.2%}"
            )
            print(
                f"- removed per update: median {statistics.median(removed_ratios):.2%} · "
                f"p90 {_pct(removed_ratios, 0.9):.2%} · max {max(removed_ratios):.2%}"
            )
        print(
            f"- invalid rules total: {sum(v[3].invalid_count for v in versions)} · "
            f"duplicates total: {sum(v[3].duplicate_count for v in versions)}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
