from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any
from urllib.parse import urlparse

import httpx


SEARXNG_DEFAULT_BASE_URL = "http://127.0.0.1:8888"
SEARCH_MAX_RESULTS = 5
SEARCH_SNIPPET_CHAR_CAP = 280
SEARCH_CONTEXT_CHAR_CAP = 2200
OFFICIAL_DOMAINS = (
    "huaweicloud.com",
    "support.huaweicloud.com",
    "developer.huaweicloud.com",
    "huawei.com",
    "e.huawei.com",
)
PREFERRED_DOMAINS = (
    "huaweicloud.com",
    "support.huaweicloud.com",
    "developer.huaweicloud.com",
)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    engine: str
    snippet: str


class WebSearchError(RuntimeError):
    pass


class SearXNGClient:
    def __init__(self, *, base_url: str | None = None, timeout: float = 8.0) -> None:
        self.base_url = (base_url or os.getenv("SEARXNG_BASE_URL") or SEARXNG_DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def search(self, query: str) -> list[SearchResult]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/search",
                    params={"q": query, "format": "json"},
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
        except Exception as exc:
            raise WebSearchError(f"SearXNG search failed: {exc}") from exc

        payload = response.json()
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            return []

        results: list[SearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = _clean_text(item.get("url"))
            title = _clean_text(item.get("title"))
            snippet = _clean_text(item.get("content") or item.get("snippet"))
            engines = item.get("engines")
            engine = ""
            if isinstance(engines, list) and engines:
                engine = _clean_text(engines[0])
            engine = engine or _clean_text(item.get("engine")) or "unknown"
            if not url or not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    engine=engine,
                    snippet=snippet,
                )
            )
        return results


def search_web_context(
    query: str,
    *,
    client: SearXNGClient | None = None,
    max_results: int = SEARCH_MAX_RESULTS,
    snippet_char_cap: int = SEARCH_SNIPPET_CHAR_CAP,
    total_char_cap: int = SEARCH_CONTEXT_CHAR_CAP,
) -> tuple[str, list[SearchResult]]:
    search_client = client or SearXNGClient()
    official_results = search_client.search(build_official_first_query(query))
    if _should_fallback_to_broad_search(official_results):
        fallback_results = search_client.search(query)
        merged_results = _merge_results(official_results, fallback_results)
    else:
        merged_results = official_results

    selected = _rank_results(merged_results)[:max_results]
    context = format_search_context(
        selected,
        snippet_char_cap=snippet_char_cap,
        total_char_cap=total_char_cap,
    )
    return context, selected


def build_official_first_query(query: str) -> str:
    domain_terms = " OR ".join(f"site:{domain}" for domain in OFFICIAL_DOMAINS)
    return f"{query} ({domain_terms})"


def format_search_context(
    results: list[SearchResult],
    *,
    snippet_char_cap: int = SEARCH_SNIPPET_CHAR_CAP,
    total_char_cap: int = SEARCH_CONTEXT_CHAR_CAP,
) -> str:
    if not results:
        return ""

    lines = ["Web search context:", "", "Use the following live web search evidence only as supplementary context."]
    base_text = "\n\n".join(lines)
    for index, result in enumerate(results, start=1):
        snippet = _normalize_whitespace(result.snippet)
        if len(snippet) > snippet_char_cap:
            snippet = snippet[:snippet_char_cap].rstrip() + "..."
        entry = (
            f"{index}. {result.title}\n"
            f"URL: {result.url}\n"
            f"Source: {result.engine}\n"
            f"Snippet: {snippet or '(no snippet)'}"
        )
        separator = "\n\n"
        candidate = f"{base_text}{separator}{entry}"
        if len(candidate) > total_char_cap:
            remaining_chars = total_char_cap - len(base_text) - len(separator)
            if remaining_chars <= 0:
                break
            trimmed_entry = entry[:remaining_chars].rstrip()
            if len(trimmed_entry) < len(entry) and remaining_chars > 3:
                trimmed_entry = trimmed_entry[:-3].rstrip() + "..."
            if trimmed_entry:
                lines.append(trimmed_entry)
            break
        lines.append(entry)
        base_text = candidate
    if len(lines) <= 3:
        return ""
    return "\n\n".join(lines)


def _should_fallback_to_broad_search(results: list[SearchResult]) -> bool:
    if len(results) < 2:
        return True
    official_hits = sum(1 for result in results[:3] if _is_official_domain(result.url))
    return official_hits < 2


def _rank_results(results: list[SearchResult]) -> list[SearchResult]:
    return sorted(
        results,
        key=lambda item: (
            0 if _is_preferred_domain(item.url) else 1 if _is_official_domain(item.url) else 2,
            len(item.snippet or ""),
        ),
        reverse=False,
    )


def _merge_results(primary: list[SearchResult], secondary: list[SearchResult]) -> list[SearchResult]:
    merged: list[SearchResult] = []
    seen: set[str] = set()
    for result in primary + secondary:
        key = result.url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        merged.append(result)
    return merged


def _is_preferred_domain(url: str) -> bool:
    host = _extract_host(url)
    return any(host == domain or host.endswith(f".{domain}") for domain in PREFERRED_DOMAINS)


def _is_official_domain(url: str) -> bool:
    host = _extract_host(url)
    return any(host == domain or host.endswith(f".{domain}") for domain in OFFICIAL_DOMAINS)


def _extract_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _normalize_whitespace(value)


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split()).strip()
