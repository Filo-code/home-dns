"""Orchestration of multi-step jobs (blocklist updates).

Receives plain core models and injected I/O (fetcher, artifact store, test provider).
Never imports config or concrete providers.
"""
