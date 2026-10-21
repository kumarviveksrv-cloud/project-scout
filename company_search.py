"""Funding-news search layer for Engine B (Company Intelligence).

Searches the configured publishers for recent funding announcements via
the Brave Search API (see config.py's "IMPLEMENTATION NOTE" for why this is
a search API and not hand-written HTML scrapers), then resolves each
lead's company name toward an actual website domain - the thing Engine B
ultimately dedupes and scores on.

Brave News endpoint: https://api.search.brave.com/res/v1/news/search
Brave Web endpoint:  https://api.search.brave.com/res/v1/web/search
Auth: X-Subscription-Token header (BRAVE_API_KEY in config/env).

include_domains workaround: Brave has no include_domains param, so we embed
'site:domain1 OR site:domain2' operators directly in the query string.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

import config
from search import canonical_url

_BRAVE_NEWS_URL = "https://api.search.brave.com/res/v1/news/search"
_BRAVE_WEB_URL = "https://api.search.brave.com/res/v1/web/search"


def _build_site_filter(domains: list[str]) -> str:
    """Return a 'site:a.com OR site:b.com' query clause for Brave."""
    if not domains:
        return ""
    return " OR ".join(f"site:{d}" for d in domains)


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
    """Searches the configured funding-news publishers for recent rounds."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or config.BRAVE_API_KEY
        if not key:
            raise ValueError("BRAVE_API_KEY is not set. Check your .env file.")
        self._headers = {
            "X-Subscription-Token": key,
            "Accept": "application/json",
        }
        # Build the site-filter clause once; it's the same for every query.
        self._site_filter = _build_site_filter(config.COMPANY_SOURCE_DOMAINS)

    def _search_one(self, query: str) -> list[dict]:
        # Embed site: filter into the query so results are scoped to our
        # funding-news publishers, matching Tavily's include_domains behaviour.
        full_query = f"{query} ({self._site_filter})" if self._site_filter else query
        params: dict = {
            "q": full_query,
            "count": config.COMPANY_BRAVE_MAX_RESULTS,
            "safesearch": "off",
            # Brave News freshness: "pd" = past day, "pw" = past week,
            # "pm" = past month, "py" = past year.
            "freshness": config.COMPANY_BRAVE_FRESHNESS,
        }
        resp = requests.get(
            _BRAVE_NEWS_URL,
            headers=self._headers,
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", []) or []

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
                # Brave News uses "description" for the snippet (not "content")
                snippet = (item.get("description") or "").strip()
                if len(f"{title} {snippet}".strip()) < config.COMPANY_MIN_SNIPPET_CHARS:
                    report.dropped_thin += 1
                    continue

                seen.add(url)
                kept += 1
                # Brave News provides "age" (relative) or "page_age" (ISO date)
                pub_date = (item.get("page_age") or item.get("age") or "").strip()
                report.leads.append(
                    RawFundingLead(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_domain=domain_of(url),
                        source_query=query,
                        published_date=pub_date,
                    )
                )

            if verbose:
                print(f"    {len(results)} results, {kept} new")
            time.sleep(0.4)

        return report

    def find_employee_count_via_linkedin(self, company_name: str) -> int | None:
        """One extra Brave Web call, spent only on companies worth it.

        Called only from company_runner.py, and only when a lead already
        scores above COMPANY_LINKEDIN_FALLBACK_THRESHOLD on everything except
        employee count - see config.py's comment on that constant. Reads the
        search snippet's own text (a "company size" field LinkedIn exposes in
        its own metadata), not a scraped page.
        """
        name = company_name.strip()
        if not name:
            return None
        try:
            resp = requests.get(
                _BRAVE_WEB_URL,
                headers=self._headers,
                params={"q": f"{name} LinkedIn", "count": 5, "safesearch": "off"},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("web", {}).get("results", []) or []
        except Exception:
            return None

        for item in results:
            if "linkedin.com" not in domain_of(item.get("url", "")):
                continue
            count = extract_employee_count_from_text(
                f"{item.get('title', '')} {item.get('description', '')}"
            )
            if count is not None:
                return count
        return None

    def resolve_company_domain(self, company_name: str) -> str:
        """Best-effort lookup of a company's official website domain.

        Funding articles frequently name the startup without linking its
        site. This spends one extra Brave Web call per company that needs it
        (company_scorer.py only calls this when extraction couldn't find a
        URL in the article text itself) rather than guessing a TLD.
        """
        name = company_name.strip()
        if not name:
            return ""
        try:
            resp = requests.get(
                _BRAVE_WEB_URL,
                headers=self._headers,
                params={"q": f"{name} official website", "count": 5, "safesearch": "off"},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("web", {}).get("results", []) or []
        except Exception:
            return ""
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
