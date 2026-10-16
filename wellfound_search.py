"""HR-job search layer for Engine C (Career Signal).

Searches Wellfound, job boards, and tech company career pages for active HR /
People / Culture job postings at early-stage startups. Each hit is a warm
outbound signal: a company actively recruiting an HR leader is almost
certainly underserved on the HR infrastructure side and may welcome fractional
help to fill the gap while the search continues (or to inform what kind of
leader they actually need).

The search strategy is Tavily's general-topic search scoped to Wellfound and
a curated list of startup-friendly job boards. Unlike Engine B (which uses
the "news" topic), general-topic is right here: we want live job postings,
not articles about the HR hiring market.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from tavily import TavilyClient

import config
from search import canonical_url


@dataclass
class RawJobLead:
    """One HR job posting result, before Claude has read it."""

    title: str
    url: str
    snippet: str
    source_domain: str
    source_query: str

    def as_prompt_block(self) -> str:
        lines = [
            f"Job posting title: {self.title or '(no title)'}",
            f"URL: {self.url}",
            f"Source: {self.source_domain}",
            "",
            "Listing excerpt:",
            self.snippet or "(no excerpt available)",
        ]
        return "\n".join(lines)


@dataclass
class JobSearchReport:
    leads: list[RawJobLead] = field(default_factory=list)
    queries_run: int = 0
    raw_results: int = 0
    dropped_duplicate: int = 0
    dropped_thin: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def domain_of(url: str) -> str:
    """The bare registrable-ish host: lowercased, no 'www.', no path."""
    if not url:
        return ""
    host = urlparse(url if "://" in url else f"https://{url}").netloc
    return host.lower().removeprefix("www.")


class HRJobSearcher:
    """Searches Wellfound and startup job boards for active HR postings."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or config.TAVILY_API_KEY
        if not key:
            raise ValueError("TAVILY_API_KEY is not set. Check your .env file.")
        self.client = TavilyClient(api_key=key)

    def _search_one(self, query: str) -> list[dict]:
        kwargs: dict = dict(
            query=query,
            search_depth=config.WELLFOUND_TAVILY_SEARCH_DEPTH,
            topic="general",  # general indexes live job postings; news indexes articles
            max_results=config.WELLFOUND_TAVILY_MAX_RESULTS,
            include_answer=False,
            include_raw_content=False,
        )
        if config.WELLFOUND_SOURCE_DOMAINS:
            kwargs["include_domains"] = config.WELLFOUND_SOURCE_DOMAINS
        response = self.client.search(**kwargs)
        return response.get("results", []) or []

    def run(
        self,
        queries: list[str] | None = None,
        verbose: bool = True,
    ) -> JobSearchReport:
        queries = queries if queries is not None else config.WELLFOUND_SEARCH_QUERIES
        report = JobSearchReport()
        seen: set[str] = set()

        for query in queries:
            if verbose:
                print(f"  searching: {query}")
            try:
                results = self._search_one(query)
            except Exception as exc:
                report.errors.append((query, f"{type(exc).__name__}: {exc}"))
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

                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or "").strip()
                if len(f"{title} {snippet}".strip()) < config.WELLFOUND_MIN_SNIPPET_CHARS:
                    report.dropped_thin += 1
                    continue

                seen.add(url)
                kept += 1
                report.leads.append(
                    RawJobLead(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_domain=domain_of(url),
                        source_query=query,
                    )
                )

            if verbose:
                print(f"    {len(results)} results, {kept} new")
            time.sleep(0.4)

        return report
