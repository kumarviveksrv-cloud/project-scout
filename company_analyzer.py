"""Career-page HR-lead detector for Engine B (Company Intelligence).

Fetches a company's public careers page with a plain HTTP GET and searches
it for HR/People job titles. There is no headless browser here and no
JavaScript execution - see config.py's HR_TITLE_KEYWORDS comment. That means
this module distinguishes three outcomes, not two:

  - found:         an HR/People title was seen on a page we could read
  - not_found:      the page loaded and was searched, and nothing matched
  - undetermined:  we could not load or make sense of a careers page at all

Only `not_found` is a confident "no HR lead" - `undetermined` must never be
scored as if it were. Airtable's `has_hr_lead` checkbox collapses `found` to
True and both other states to False (matching the brief's literal
true/false spec); the nuance lives in `hr_signals`, a text field, and in
company_scorer.py's scoring, which only awards the +40 for `not_found`.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config
from search import is_blocked_domain

HEADERS = {"User-Agent": config.HTTP_USER_AGENT}


@dataclass
class CareerPageResult:
    status: str  # "found" | "not_found" | "undetermined"
    has_hr_lead: bool  # Airtable's literal boolean - see module docstring
    hr_signals: str  # human-readable explanation, always populated
    career_page_url: str = ""
    matched_keywords: list[str] | None = None

    @property
    def confidently_no_hr_lead(self) -> bool:
        """Only this - not `not has_hr_lead` - should feed scoring's +40."""
        return self.status == "not_found"


def _get(url: str) -> requests.Response | None:
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=config.HTTP_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except requests.RequestException:
        return None
    if response.status_code >= 400:
        return None
    return response


def _find_career_link(homepage_html: str, base_url: str) -> str:
    """The first careers/jobs link on the page, skipping links out to a
    generic job board (LinkedIn, Indeed, ...) rather than the company's own
    listings. Scanning a generic job-search results page for HR keywords
    produced a real false positive in testing - the page's own boilerplate
    text ("...connecting people...") matched a keyword with nothing to do
    with the company being checked."""
    soup = BeautifulSoup(homepage_html, "html.parser")
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip().lower()
        href = a["href"].lower()
        if not any(hint in text or hint in href for hint in config.CAREER_LINK_TEXT_HINTS):
            continue
        absolute = urljoin(base_url, a["href"])
        if is_blocked_domain(urlparse(absolute).netloc):
            continue
        return absolute
    return ""


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[: config.HTTP_MAX_CONTENT_CHARS]


def _looks_like_empty_shell(text: str) -> bool:
    """A page a JS framework was going to fill in but a plain GET never
    triggered - typically very little text and a handful of the same app
    boilerplate words. Not a precise test, just a cheap smell check so we
    don't confidently report "not_found" against an unrendered shell."""
    return len(text) < 200


def _scan_for_hr_keywords(text: str) -> list[str]:
    lower = text.lower()
    return sorted({kw for kw in config.HR_TITLE_KEYWORDS if kw in lower})


def check_company(domain: str, verbose: bool = False) -> CareerPageResult:
    """Fetch `domain`'s careers page (if findable) and scan it for HR titles."""
    if not domain:
        return CareerPageResult(
            status="undetermined",
            has_hr_lead=False,
            hr_signals="No company domain was resolved, so no careers page could be checked.",
        )

    base_url = f"https://{domain}"
    homepage = _get(base_url)
    if homepage is None:
        homepage = _get(f"http://{domain}")
    if homepage is None:
        return CareerPageResult(
            status="undetermined",
            has_hr_lead=False,
            hr_signals=f"Could not load {base_url} (timeout, DNS failure, or non-2xx status).",
        )

    career_url = _find_career_link(homepage.text, homepage.url)

    career_page = _get(career_url) if career_url else None
    if career_page is None:
        # Try the common path guesses before giving up.
        parsed = urlparse(homepage.url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        for guess in config.CAREER_PATH_GUESSES:
            candidate = urljoin(root, guess)
            page = _get(candidate)
            if page is not None:
                career_page = page
                career_url = candidate
                break

    if career_page is None:
        return CareerPageResult(
            status="undetermined",
            has_hr_lead=False,
            hr_signals=(
                f"Loaded {base_url} but could not find or load a careers/jobs page "
                "(no matching link, and none of the common /careers, /jobs paths worked)."
            ),
        )

    text = _page_text(career_page.text)
    if _looks_like_empty_shell(text):
        return CareerPageResult(
            status="undetermined",
            has_hr_lead=False,
            career_page_url=career_url,
            hr_signals=(
                f"Loaded {career_url} but the page returned almost no text - likely a "
                "JavaScript-rendered page this plain-HTTP check cannot see into. "
                "Manual check recommended."
            ),
        )

    matches = _scan_for_hr_keywords(text)
    if matches:
        return CareerPageResult(
            status="found",
            has_hr_lead=True,
            career_page_url=career_url,
            matched_keywords=matches,
            hr_signals=f"Found HR-related terms on {career_url}: {', '.join(matches)}.",
        )

    return CareerPageResult(
        status="not_found",
        has_hr_lead=False,
        career_page_url=career_url,
        hr_signals=(
            f"Loaded {career_url} and searched its visible text ({len(text):,} chars) "
            "for HR/People job titles - none found."
        ),
    )
