"""Real Pi-hole v6 provider — talks to the actual Pi-hole v6 REST API over HTTP.

Every endpoint, field name and status code used here was ground-truthed against a real,
installed Pi-hole v6 instance (Core 6.4.3 / Web 6.6 / FTL 6.7) via its own served OpenAPI
docs (``/api/docs/specs/*.yaml``) and live responses — see
docs/audits/2026-09-15-pihole-v6-provider.md for the endpoint reference this file follows.
Nothing here is guessed from Pi-hole v5 documentation.

Two real gaps, both intentional and documented rather than worked around:

* ``deploy_blocklist`` manages individual domains via ``/api/domains`` (bulk add/delete). This
  is correct for the DnsProvider contract (a handful of validated ``BlockEntry`` objects) and
  for small denylist/allowlist-style deployments, but is NOT how the real, ~355k-domain HaGeZi
  sources were loaded in the Stage C lab — that used Pi-hole's adlist-URL + ``pihole -g``
  mechanism directly (see the Stage C lab report). A safety cap refuses oversized deployments
  through this method rather than silently hammering gravity with hundreds of thousands of
  individual API calls.
* Per-client ``blocked_queries`` in ``list_clients`` costs one extra ``/api/queries`` request
  per client (Pi-hole's client/device endpoints do not carry a per-client blocked count).
  Nothing in this codebase reads that field today; it is populated for contract fidelity and
  future consumers, not because it is load-bearing now.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any
from urllib.parse import quote

import httpx

from home_dns.core.blocklists import BlockEntry
from home_dns.core.models import (
    BlocklistDeployment,
    DnsClient,
    DnsSummary,
    DomainLookup,
    HealthStatus,
    ProviderHealth,
    QueryFilter,
    QueryLogEntry,
    QueryOutcome,
    QueryPage,
    SystemMetrics,
)
from home_dns.providers.base import DnsProvider, ProviderError, ProviderUnavailableError

logger = logging.getLogger(__name__)

_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
_SESSION_SAFETY_MARGIN_SECONDS = 30
_MAX_PAGE = 1000
_FETCH_CHUNK = 1000
_MAX_DOMAIN_API_ENTRIES = 5000
_DOMAIN_POST_CHUNK = 500
_COMMENT_PREFIX = "home-dns:"

# Pi-hole's 19 query statuses collapsed onto QueryOutcome; UNKNOWN/IN_PROGRESS/DBBUSY fall
# through to OTHER via .get()'s default.
_STATUS_TO_OUTCOME: dict[str, QueryOutcome] = {
    "GRAVITY": QueryOutcome.BLOCKED,
    "REGEX": QueryOutcome.BLOCKED,
    "DENYLIST": QueryOutcome.BLOCKED,
    "EXTERNAL_BLOCKED_IP": QueryOutcome.BLOCKED,
    "EXTERNAL_BLOCKED_NULL": QueryOutcome.BLOCKED,
    "EXTERNAL_BLOCKED_NXRA": QueryOutcome.BLOCKED,
    "EXTERNAL_BLOCKED_EDE15": QueryOutcome.BLOCKED,
    "GRAVITY_CNAME": QueryOutcome.BLOCKED,
    "REGEX_CNAME": QueryOutcome.BLOCKED,
    "DENYLIST_CNAME": QueryOutcome.BLOCKED,
    "SPECIAL_DOMAIN": QueryOutcome.BLOCKED,
    "CACHE": QueryOutcome.CACHED,
    "CACHE_STALE": QueryOutcome.CACHED,
    "FORWARDED": QueryOutcome.FORWARDED,
    "RETRIED": QueryOutcome.FORWARDED,
    "RETRIED_DNSSEC": QueryOutcome.FORWARDED,
}


class AuthenticationError(ProviderError):
    """Pi-hole rejected the configured admin password, or a session could not be renewed."""


class MalformedResponseError(ProviderError):
    """Pi-hole returned a response this provider does not know how to parse."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _subdomain_regex(domain: str) -> str:
    escaped = re.escape(domain)
    return rf"(^|\.){escaped}$"


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class PiholeV6Provider(DnsProvider):
    def __init__(
        self,
        *,
        base_url: str,
        password: str,
        request_timeout_seconds: float = 5.0,
        verify_tls: bool = True,
        source_urls: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._password = password
        self._source_urls = dict(source_urls or {})
        self._url_to_source = {url: source for source, url in self._source_urls.items()}
        self._now = now
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=request_timeout_seconds, verify=verify_tls
        )
        self._sid: str | None = None
        self._sid_expires_at: float = 0.0
        self._list_id_to_source_cache: dict[int, str] | None = None

    @property
    def name(self) -> str:
        return "pihole_v6"

    # ------------------------------------------------------------------------------ session

    def _authenticate(self) -> str:
        try:
            response = self._client.post("/api/auth", json={"password": self._password})
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError("pihole auth request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"pihole auth request failed: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 500:
            raise ProviderUnavailableError(f"pihole auth returned HTTP {response.status_code}")
        try:
            session = response.json()["session"]
        except (ValueError, KeyError) as exc:
            raise MalformedResponseError("pihole auth response missing 'session'") from exc
        if not session.get("valid"):
            # Never include the password itself in the exception message.
            raise AuthenticationError("pihole rejected the configured admin password")
        raw_sid = session.get("sid")
        if not raw_sid:
            raise MalformedResponseError("pihole auth response missing 'sid'")
        sid = str(raw_sid)
        validity = session.get("validity") or 0
        self._sid = sid
        self._sid_expires_at = time.monotonic() + max(validity - _SESSION_SAFETY_MARGIN_SECONDS, 0)
        return sid

    def _session_id(self) -> str:
        if self._sid is None or time.monotonic() >= self._sid_expires_at:
            return self._authenticate()
        return self._sid

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        _retry_auth: bool = True,
    ) -> dict[str, Any]:
        sid = self._session_id()
        try:
            response = self._client.request(
                method, path, params=params, json=json, headers={"X-FTL-SID": sid}
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"pihole request timed out: {path}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"pihole request failed ({type(exc).__name__}): {path}"
            ) from exc
        if response.status_code in (401, 403):
            if _retry_auth:
                self._sid = None
                return self._request(method, path, params=params, json=json, _retry_auth=False)
            raise AuthenticationError(f"pihole rejected the session for {path}")
        if response.status_code == 404:
            return {}
        if response.status_code == 429:
            raise ProviderUnavailableError(f"pihole rate-limited {path}")
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"pihole returned HTTP {response.status_code} for {path}"
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"pihole returned HTTP {response.status_code} for {path}: {response.text[:200]}"
            )
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise MalformedResponseError(f"pihole returned non-JSON for {path}") from exc
        if not isinstance(data, dict):
            raise MalformedResponseError(f"pihole returned a non-object body for {path}")
        return data

    # ------------------------------------------------------------------------------ health

    def health(self) -> ProviderHealth:
        try:
            self._request("GET", "/api/info/ftl")
        except AuthenticationError as exc:
            return ProviderHealth(status=HealthStatus.DOWN, detail=f"authentication failed: {exc}")
        except ProviderError as exc:
            return ProviderHealth(status=HealthStatus.DOWN, detail=str(exc))
        return ProviderHealth(status=HealthStatus.OK, detail="pihole_v6 reachable")

    # ------------------------------------------------------------------------------ summary

    def get_summary(self) -> DnsSummary:
        data = self._request("GET", "/api/stats/summary")
        try:
            queries = data["queries"]
            status = queries["status"]
            cached = int(status.get("CACHE", 0)) + int(status.get("CACHE_STALE", 0))
            return DnsSummary(
                total_queries=int(queries["total"]),
                blocked_queries=int(queries["blocked"]),
                cached_queries=cached,
                unique_clients=int(data["clients"]["total"]),
                collected_at=self._now(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedResponseError(
                "pihole /api/stats/summary had an unexpected shape"
            ) from exc

    # ------------------------------------------------------------------------------ clients

    def list_clients(self) -> list[DnsClient]:
        data = self._request("GET", "/api/network/devices")
        devices = data.get("devices")
        if devices is None:
            raise MalformedResponseError("pihole /api/network/devices missing 'devices'")
        clients: list[DnsClient] = []
        for device in devices:
            ipv4: list[IPv4Address] = []
            ipv6: list[IPv6Address] = []
            hostname = None
            for entry in device.get("ips", []):
                try:
                    addr = ip_address(entry["ip"])
                except ValueError:
                    continue
                if isinstance(addr, IPv4Address):
                    ipv4.append(addr)
                else:
                    ipv6.append(addr)
                if hostname is None and entry.get("name"):
                    hostname = entry["name"]
            if not ipv4 and not ipv6:
                continue
            raw_mac = device.get("hwaddr")
            mac = raw_mac.lower() if raw_mac and _MAC_RE.fullmatch(raw_mac.lower()) else None
            first_seen = datetime.fromtimestamp(device["firstSeen"], UTC)
            last_seen = datetime.fromtimestamp(
                max(device.get("lastQuery") or 0, device["firstSeen"]), UTC
            )
            total = int(device.get("numQueries") or 0)
            primary_address = ipv4[0] if ipv4 else ipv6[0]
            blocked = self._blocked_count_for(primary_address) if total else 0
            client_id = mac or str(primary_address)
            clients.append(
                DnsClient(
                    client_id=client_id,
                    ipv4_addresses=tuple(ipv4),
                    ipv6_addresses=tuple(ipv6),
                    mac=mac,
                    hostname=hostname,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    total_queries=total,
                    blocked_queries=min(blocked, total),
                )
            )
        return sorted(clients, key=lambda c: c.client_id)

    def _blocked_count_for(self, address: object) -> int:
        try:
            data = self._request(
                "GET",
                "/api/queries",
                params={"client_ip": str(address), "status": "GRAVITY", "length": 1},
            )
            return int(data.get("recordsFiltered", 0))
        except ProviderError:
            logger.warning("pihole: could not read blocked-query count for %s", address)
            return 0

    # -------------------------------------------------------------------- blocklist deployment

    def deploy_blocklist(
        self, source_id: str, entries: frozenset[BlockEntry], *, dry_run: bool = True
    ) -> BlocklistDeployment:
        if len(entries) > _MAX_DOMAIN_API_ENTRIES:
            raise ProviderError(
                f"{len(entries)} entries exceeds the {_MAX_DOMAIN_API_ENTRIES}-entry safety cap "
                "for per-domain deployment via /api/domains; a full-size source (e.g. a HaGeZi "
                "list) must go through Pi-hole's adlist-URL + gravity mechanism, not this method"
            )
        if dry_run:
            return BlocklistDeployment(
                source_id=source_id, entries=len(entries), dry_run=True, applied=False
            )
        comment = f"{_COMMENT_PREFIX}{source_id}"
        self._replace_domain_entries(comment, entries)
        return BlocklistDeployment(
            source_id=source_id, entries=len(entries), dry_run=False, applied=True
        )

    def _replace_domain_entries(self, comment: str, entries: frozenset[BlockEntry]) -> None:
        existing = self._request("GET", "/api/domains/deny").get("domains", [])
        to_delete = [
            {"item": item["domain"], "type": "deny", "kind": item["kind"]}
            for item in existing
            if item.get("comment") == comment
        ]
        if to_delete:
            self._request("POST", "/api/domains:batchDelete", json=to_delete)
        exact = [e.domain for e in entries if not e.include_subdomains]
        regex = [_subdomain_regex(e.domain) for e in entries if e.include_subdomains]
        for chunk in _chunks(exact, _DOMAIN_POST_CHUNK):
            self._request(
                "POST",
                "/api/domains/deny/exact",
                json={"domain": chunk, "comment": comment, "enabled": True},
            )
        for chunk in _chunks(regex, _DOMAIN_POST_CHUNK):
            self._request(
                "POST",
                "/api/domains/deny/regex",
                json={"domain": chunk, "comment": comment, "enabled": True},
            )

    # ------------------------------------------------------------------------------- lookup

    def lookup_domain(self, domain: str) -> DomainLookup:
        data = self._request(
            "GET", f"/api/search/{quote(domain, safe='')}", params={"partial": "false", "N": 20}
        )
        search = data.get("search", {})
        matched: set[str] = set()
        for item in search.get("gravity", []):
            if item.get("type") == "block" and item.get("enabled", True):
                address = item.get("address", "")
                matched.add(self._url_to_source.get(address, address))
        for item in search.get("domains", []):
            if item.get("type") == "deny" and item.get("enabled", True):
                comment = item.get("comment") or ""
                if comment.startswith(_COMMENT_PREFIX):
                    matched.add(comment.removeprefix(_COMMENT_PREFIX))
                else:
                    matched.add("pihole-deny")
        return DomainLookup(
            domain=domain, blocked=bool(matched), matched_sources=tuple(sorted(matched))
        )

    # ----------------------------------------------------------------------------- query log

    def query_log(
        self, query: QueryFilter, *, limit: int = 100, cursor: str | None = None
    ) -> QueryPage:
        if not 1 <= limit <= _MAX_PAGE:
            raise ValueError(f"limit must be 1..{_MAX_PAGE}")
        start = 0
        if cursor is not None:
            if not cursor.isdecimal():
                raise ValueError(f"invalid cursor {cursor!r}")
            start = int(cursor)

        params: dict[str, Any] = {
            "from": query.since.timestamp(),
            "until": query.until.timestamp(),
        }
        if query.client_address is not None:
            params["client_ip"] = str(query.client_address)
        if query.domain is not None:
            params["domain"] = query.domain

        found: list[QueryLogEntry] = []
        offset = start
        total_matching: int | None = None
        while len(found) < limit:
            if total_matching is not None and offset >= total_matching:
                break
            data = self._request(
                "GET", "/api/queries", params={**params, "start": offset, "length": _FETCH_CHUNK}
            )
            raw = data.get("queries")
            if raw is None:
                raise MalformedResponseError("pihole /api/queries missing 'queries'")
            try:
                total_matching = int(data["recordsFiltered"])
            except (KeyError, TypeError, ValueError) as exc:
                raise MalformedResponseError(
                    "pihole /api/queries missing 'recordsFiltered'"
                ) from exc
            if not raw:
                break
            for item in raw:
                offset += 1
                try:
                    entry = self._to_entry(item)
                except (KeyError, TypeError, ValueError) as exc:
                    raise MalformedResponseError(
                        f"pihole /api/queries returned a malformed entry: {exc}"
                    ) from exc
                if query.outcome is None or entry.outcome is query.outcome:
                    found.append(entry)
                if len(found) >= limit:
                    break

        page = tuple(found[:limit])
        exhausted = total_matching is not None and offset >= total_matching
        next_cursor = None if exhausted else str(offset)
        return QueryPage(entries=page, next_cursor=next_cursor)

    def _to_entry(self, item: dict[str, Any]) -> QueryLogEntry:
        status = str(item.get("status", "UNKNOWN"))
        outcome = _STATUS_TO_OUTCOME.get(status, QueryOutcome.OTHER)
        blocked_by = None
        if outcome is QueryOutcome.BLOCKED:
            list_id = item.get("list_id")
            blocked_by = (
                self._source_for_list_id(list_id)
                if isinstance(list_id, int) and list_id > 0
                else status.lower()
            )
        client = item["client"]
        if not isinstance(client, dict):
            raise MalformedResponseError("pihole query entry has a non-object 'client'")
        reply = item.get("reply") or {}
        if not isinstance(reply, dict):
            raise MalformedResponseError("pihole query entry has a non-object 'reply'")
        latency = reply.get("time")
        latency_ms = round(float(latency) * 1000, 3) if isinstance(latency, int | float) else None
        return QueryLogEntry(
            id=int(item["id"]),
            time=datetime.fromtimestamp(float(item["time"]), UTC),
            client_address=ip_address(client["ip"]),
            domain=str(item["domain"]),
            query_type=str(item.get("type", "A")),
            outcome=outcome,
            blocked_by=blocked_by,
            latency_ms=latency_ms,
        )

    def _source_for_list_id(self, list_id: int) -> str:
        if self._list_id_to_source_cache is None:
            self._list_id_to_source_cache = {}
            try:
                lists = self._request("GET", "/api/lists").get("lists", [])
                for entry in lists:
                    source = self._url_to_source.get(entry.get("address", ""))
                    if source and isinstance(entry.get("id"), int):
                        self._list_id_to_source_cache[entry["id"]] = source
            except ProviderError:
                logger.warning("pihole: could not resolve list_id -> source mapping")
        return self._list_id_to_source_cache.get(list_id, f"list:{list_id}")

    # ------------------------------------------------------------------------- system metrics

    def system_metrics(self) -> SystemMetrics:
        data = self._request("GET", "/api/info/system")
        try:
            system = data["system"]
            ram = system["memory"]["ram"]
            cpu = system["cpu"]
        except (KeyError, TypeError) as exc:
            raise MalformedResponseError("pihole /api/info/system had an unexpected shape") from exc
        temperature: float | None = None
        try:
            sensors = self._request("GET", "/api/info/sensors").get("sensors", {})
            temperature = sensors.get("cpu_temp")
        except ProviderError:
            logger.warning("pihole: could not read /api/info/sensors; temperature unavailable")
        return SystemMetrics(
            uptime_seconds=int(system["uptime"]),
            cpu_percent=min(max(float(cpu["%cpu"]), 0.0), 100.0),
            load_1m=float(cpu["load"]["raw"][0]),
            memory_total_bytes=int(ram["total"]) * 1024,
            memory_used_bytes=int(ram["used"]) * 1024,
            temperature_celsius=temperature,
            collected_at=self._now(),
        )
