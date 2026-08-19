"""Funding-news search layer for Engine B (Company Intelligence).

Searches the five configured publishers for recent funding announcements via
the Tavily Search API (see config.py's "IMPLEMENTATION NOTE" for why this is
a search API and not five hand-written HTML scrapers), then resolves each
lead's company name toward an actual website domain - the thing Engine B
ultimately dedupes and scores on.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from tavily import TavilyClient

import config
from search import canonical_url


@dataclass
class RawFundingLead:
    """One funding-news article, before Claude has read it."""

    title: str
    url: str
    snippet: str
    source_domain: str
    source_query: str
    published_date: str = ""

    def as_prompt_block(self) -> str:
        lines = [
            f"Headline: {self.title or '(no title)'}",
            f"URL: {self.url}",
            f"Publisher: {self.source_domain}",
        ]
        if self.published_date:
            lines.append(f"Published: {self.published_date}")
        lines.append("")
        lines.append("Article excerpt:")
        lines.append(self.snippet or "(no excerpt available)")
        return "\n".join(lines)


@dataclass
class CompanySearchReport:
    leads: list[RawFundingLead] = field(default_factory=list)
    queries_run: int = 0
    raw_results: int = 0
    dropped_duplicate: int = 0
    dropped_thin: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


_EMPLOYEE_RANGE_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*)\s*[-–]\s*(\d{1,3}(?:,\d{3})*)\s+employees?", re.IGNORECASE
)
_EMPLOYEE_SINGLE_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*)\+?\s+employees?", re.IGNORECASE
)


def extract_employee_count_from_text(text: str) -> int | None:
    """Best-effort employee count from a LinkedIn search snippet.

    LinkedIn company pages carry a standardized "company size" field that
    search snippets usually surface as "11-50 employees" or similar. A range
    is reported as its midpoint - a single number is still useful signal for
    the 1-10 / 10-50 / 51-100 bands even though it's an approximation.
    """
    if not text:
        return None
    range_match = _EMPLOYEE_RANGE_RE.search(text)
    if range_match:
        low = int(range_match.group(1).replace(",", ""))
        high = int(range_match.group(2).replace(",", ""))
        return (low + high) // 2
    single_match = _EMPLOYEE_SINGLE_RE.search(text)
    if single_match:
        return int(single_match.group(1).replace(",", ""))
    return None


def domain_of(url: str) -> str:
    """The bare registrable-ish host: lowercased, no 'www.', no path."""
    if not url:
        return ""
    host = urlparse(url if "://" in url else f"https://{url}").netloc
    return host.lower().removeprefix("www.")


class CompanyFundingSearcher:
    """Searches the five funding-news publishers for recent rounds."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or config.TAVILY_API_KEY
        if not key:
            raise ValueError("TAVILY_API_KEY is not set. Check your .env file.")
        self.client = TavilyClient(api_key=key)

    def _search_one(self, query: str) -> list[dict]:
        response = self.client.search(
            query=query,
            search_depth=config.COMPANY_TAVILY_SEARCH_DEPTH,
            topic="news",
            days=config.COMPANY_TAVILY_DAYS,
            max_results=config.COMPANY_TAVILY_MAX_RESULTS,
            include_answer=False,
            include_raw_content=False,
            include_domains=config.COMPANY_SOURCE_DOMAINS,
        )
        return response.get("results", []) or []

    def run(self, queries: list[str] | None = None, verbose: bool = True) -> CompanySearchReport:
        queries = queries if queries is not None else config.COMPANY_SEARCH_QUERIES
        report = CompanySearchReport()
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
                if len(f"{title} {snippet}".strip()) < config.COMPANY_MIN_SNIPPET_CHARS:
                    report.dropped_thin += 1
                    continue

                seen.add(url)
                kept += 1
                report.leads.append(
                    RawFundingLead(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_domain=domain_of(url),
                        source_query=query,
                        published_date=(item.get("published_date") or "").strip(),
                    )
                )

            if verbose:
                print(f"    {len(results)} results, {kept} new")
            time.sleep(0.4)

        return report

    def find_employee_count_via_linkedin(self, company_name: str) -> int | None:
        """One extra Tavily call, spent only on companies worth it.

        Called only from company_runner.py, and only when a lead already
        scores above COMPANY_LINKEDIN_FALLBACK_THRESHOLD on everything except
        employee count - see config.py's comment on that constant. Reads the
        search snippet's own text (a "company size" field LinkedIn exposes in
        its own metadata), not a scraped page - this is a Tavily search
        result, not a fetch of linkedin.com.
        """
        name = company_name.strip()
        if not name:
            return None
        try:
            response = self.client.search(
                query=f"{name} LinkedIn",
                search_depth="basic",
                max_results=5,
                include_answer=False,
            )
        except Exception:
            return None

        for item in response.get("results", []) or []:
            if "linkedin.com" not in domain_of(item.get("url", "")):
                continue
            count = extract_employee_count_from_text(
                f"{item.get('title', '')} {item.get('content', '')}"
            )
            if count is not None:
                return count
        return None

    def resolve_company_domain(self, company_name: str) -> str:
        """Best-effort lookup of a company's official website domain.

        Funding articles frequently name the startup without linking its
        site. This spends one extra Tavily call per company that needs it
        (company_scorer.py only calls this when extraction couldn't find a
        URL in the article text itself) rather than guessing a TLD.
        """
        name = company_name.strip()
        if not name:
            return ""
        try:
            response = self.client.search(
                query=f"{name} official website",
                search_depth="basic",
                max_results=5,
                include_answer=False,
            )
        except Exception:
            return ""

        results = response.get("results", []) or []
        blocked = config.BLOCKED_DOMAINS | set(config.COMPANY_SOURCE_DOMAINS)
        slug = re.sub(r"[^a-z0-9]", "", name.lower())

        for item in results:
            candidate = domain_of(item.get("url", ""))
            if not candidate or candidate in blocked:
                continue
            host_slug = re.sub(r"[^a-z0-9]", "", candidate.split(".")[0])
            if not slug or not host_slug:
                continue
            contained = slug in host_slug or host_slug in slug
            # Plain substring containment alone is too permissive on short
            # names: "corpus" is a substring of "corpuschristi" (an unrelated
            # US healthcare domain this genuinely matched to in testing), and
            # would match plenty of other unrelated hosts too. Require the
            # shorter string to cover most of the longer one as well, so a
            # short/common name doesn't confidently match on a coincidence.
            if not contained:
                continue
            coverage = min(len(slug), len(host_slug)) / max(len(slug), len(host_slug))
            if len(slug) >= 4 and coverage >= 0.6:
                return candidate

        # No confident match. Returning nothing here (rather than the top
        # result regardless of relevance, which is what this used to do) is
        # a deliberate precision-over-recall choice: attributing career-page
        # findings to the wrong company is worse than skipping a lead we
        # couldn't confidently resolve.
        return ""
