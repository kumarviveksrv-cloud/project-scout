"""Tavily search layer for Project Scout.

Runs every configured query, normalises the results into a flat shape, and
de-duplicates by URL within the run. Deduplication against Airtable happens
later, in scout.py.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from tavily import TavilyClient

import config

_AGGREGATOR_RE = re.compile("|".join(config.AGGREGATOR_URL_PATTERNS), re.IGNORECASE)


def is_blocked_domain(domain: str) -> bool:
    """True if the domain, or any parent of it, is on the block list.

    Matches subdomains so 'uk.indeed.com' is caught by 'indeed.com'.
    """
    domain = domain.lower().removeprefix("www.")
    return any(
        domain == blocked or domain.endswith("." + blocked)
        for blocked in config.BLOCKED_DOMAINS
    )


def is_aggregator_url(url: str) -> bool:
    """True if the URL looks like a search-results or browse page.

    Only the path and query are tested - a domain that happens to contain a
    pattern should not disqualify a specific listing hosted on it.
    """
    parsed = urlparse(url)
    # Append the query only when there is one - an unconditional "?" would
    # break every end-anchored pattern, e.g. "/jobs/?$" against "/jobs?".
    target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return bool(_AGGREGATOR_RE.search(target))


@dataclass
class RawOpportunity:
    """One search hit, before Claude has looked at it."""

    title: str
    url: str
    snippet: str
    source_query: str
    published_date: str = ""
    tavily_score: float = 0.0

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")

    def as_prompt_block(self) -> str:
        """The text Claude actually scores."""
        lines = [
            f"Title: {self.title or '(no title)'}",
            f"URL: {self.url}",
            f"Domain: {self.domain}",
            f"Found via search query: {self.source_query}",
        ]
        if self.published_date:
            lines.append(f"Published date: {self.published_date}")
        lines.append("")
        lines.append("Page excerpt:")
        lines.append(self.snippet or "(no excerpt available)")
        return "\n".join(lines)


@dataclass
class SearchReport:
    """What one full search sweep produced."""

    opportunities: list[RawOpportunity] = field(default_factory=list)
    queries_run: int = 0
    raw_results: int = 0
    dropped_duplicate: int = 0
    dropped_blocked: int = 0
    dropped_aggregator: int = 0
    dropped_thin: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def canonical_url(url: str) -> str:
    """Normalise a URL so trivial variants dedupe against each other.

    Lowercases scheme and host, strips 'www.', drops query strings and
    fragments, and removes a trailing slash.
    """
    if not url:
        return ""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


class TavilySearcher:
    """Thin wrapper over the Tavily client with Project Scout's defaults."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or config.TAVILY_API_KEY
        if not key:
            raise ValueError("TAVILY_API_KEY is not set. Check your .env file.")
        self.client = TavilyClient(api_key=key)

    def _search_one(self, query: str) -> list[dict]:
        params: dict = {
            "query": query,
            "search_depth": config.TAVILY_SEARCH_DEPTH,
            "topic": config.TAVILY_TOPIC,
            "max_results": config.TAVILY_MAX_RESULTS,
            "include_answer": config.TAVILY_INCLUDE_ANSWER,
            "include_raw_content": config.TAVILY_INCLUDE_RAW_CONTENT,
            # Server-side exclusion. Tavily has a dedicated parameter for this;
            # a "-site:x.com" operator inside the query string would just be
            # tokenised as search text and dilute the query.
            "exclude_domains": sorted(config.BLOCKED_DOMAINS),
        }
        if config.TAVILY_TOPIC == "news":
            params["days"] = config.TAVILY_DAYS

        response = self.client.search(**params)
        return response.get("results", []) or []

    def run(self, queries: list[str] | None = None, verbose: bool = True) -> SearchReport:
        """Run every query and return the de-duplicated, filtered results."""
        queries = queries if queries is not None else config.SEARCH_QUERIES
        report = SearchReport()
        seen: set[str] = set()

        for query in queries:
            full_query = f"{query} {config.QUERY_SUFFIX}".strip()
            if verbose:
                print(f"  searching: {full_query}")

            try:
                results = self._search_one(full_query)
            except Exception as exc:  # network, auth, quota - keep the sweep alive
                report.errors.append((full_query, f"{type(exc).__name__}: {exc}"))
                if verbose:
                    print(f"    ! failed: {type(exc).__name__}: {exc}")
                continue
            finally:
                report.queries_run += 1

            report.raw_results += len(results)
            kept = 0

            for item in results:
                url = canonical_url(item.get("url", ""))
                if not url:
                    continue

                if url in seen:
                    report.dropped_duplicate += 1
                    continue

                if is_blocked_domain(urlparse(url).netloc):
                    report.dropped_blocked += 1
                    continue

                if is_aggregator_url(url):
                    report.dropped_aggregator += 1
                    continue

                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or "").strip()
                if len(f"{title} {snippet}".strip()) < config.MIN_SNIPPET_CHARS:
                    report.dropped_thin += 1
                    continue

                seen.add(url)
                kept += 1
                report.opportunities.append(
                    RawOpportunity(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_query=query,
                        published_date=(item.get("published_date") or "").strip(),
                        tavily_score=float(item.get("score") or 0.0),
                    )
                )

            if verbose:
                print(f"    {len(results)} results, {kept} new")

            # Be a good citizen with the API.
            time.sleep(0.4)

        return report
