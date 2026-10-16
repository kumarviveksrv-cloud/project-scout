"""Project Scout - all tunable settings in one place.

Nothing here touches the network. Import it from anywhere.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID", "")
# RESEND_API_KEY is intentionally NOT in the required set below - only
# digest.py needs it, and scout.py/company_runner.py/contact_finder.py
# shouldn't refuse to run just because email isn't configured yet.
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

_PLACEHOLDER_MARKERS = ("xxxx", "XXXX", "your_", "your ", "<", ">", "REPLACE_ME")


def is_placeholder(value: str) -> bool:
    """True if `value` is empty or still looks like a template value."""
    return not value.strip() or any(marker in value for marker in _PLACEHOLDER_MARKERS)


def missing_credentials() -> list[str]:
    """Names of env vars that are empty or still hold the .env template value."""
    required = {
        "TAVILY_API_KEY": TAVILY_API_KEY,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "AIRTABLE_TOKEN": AIRTABLE_TOKEN,
        "AIRTABLE_BASE_ID": AIRTABLE_BASE_ID,
        "AIRTABLE_TABLE_ID": AIRTABLE_TABLE_ID,
    }
    return [name for name, value in required.items() if is_placeholder(value)]


# --------------------------------------------------------------------------
# Who we are scouting for
# --------------------------------------------------------------------------

CANDIDATE_PROFILE = """\
Senior HR professional based in India (IST, UTC+5:30), 12+ years of experience.

Core expertise:
- Organisational development (OD) and organisation design
- Performance management systems (PMS) - design, rollout and calibration
- Learning and development (L&D) - capability frameworks and programme design
- Compensation design - banding, benchmarking, pay structures, incentive plans
- Change management - restructures, integrations, ways-of-working transitions
- Talent acquisition - senior and niche hiring, hiring process design

Target engagements:
- Fractional CHRO
- HR consultant (project or retainer)
- People operations consultant
- HR advisory, org design and HR transformation work

Preferred sectors, strongest fit first:
- Startups and scale-ups
- SaaS
- AI
- Fintech
- HRTech

Geography:
- Global remote. The engagement must be genuinely deliverable from India.
- Works asynchronously with clients across the US, UK, EU, Middle East,
  Singapore and Australia, with several hours of daily overlap available.
- On-site-only, relocation-required, or engagements restricted to holders of
  local work authorisation are not viable.

Commercials:
- Target rate USD 50-150 per hour, or an equivalent project or retainer fee.
- Anything materially below USD 50/hour is not commercially attractive.
- Anything at or above roughly USD 120/hour, or a substantial multi-month
  retainer, is a strong commercial signal.

Availability:
- Part-time, fractional, advisory and contract engagements.
- Can run more than one engagement concurrently.

Not looking for:
- Permanent full-time in-house employment
- Junior or mid-level HR generalist, recruiter or coordinator work
- Contingent headhunting / recruiting-agency placement work
- Unpaid, equity-only or gig-marketplace race-to-the-bottom work
"""

# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

# Demand-signal phrasing: written the way a client describes a need, not the
# way a candidate searches for a job. Job-search phrasing ("fractional CHRO
# jobs") returns job-board landing pages; "seeking a fractional CHRO" returns
# posts by people who actually want one.
SEARCH_QUERIES: list[str] = [
    "seeking fractional CHRO remote",
    "seeking fractional CHRO remote India",
    "looking for HR consultant remote contract",
    "need people operations consultant remote",
    "hiring fractional HR advisor globally",
    "startup seeking fractional people operations leader",
    "looking for organizational design consultant remote",
    "seeking HR transformation consultant remote engagement",
    "need compensation design consultant remote",
    "seeking performance management consultant remote",
    "looking for L and D consultant remote contract",
    "hiring interim HR leader remote engagement",
]

# Appended to every query. Empty because recency is handled by TAVILY_DAYS and
# the queries already carry the intent - a suffix here just dilutes them.
QUERY_SUFFIX = ""

TAVILY_SEARCH_DEPTH = "advanced"  # "basic" (1 credit) or "advanced" (2 credits)
TAVILY_TOPIC = "general"  # "general" or "news"
# NOTE: "general" does not support the `days` recency filter - Tavily ignores
# it. Recency for Engine A is implicitly handled by the queries themselves
# ("seeking", "looking for", "hiring") which match active posts rather than
# articles about the market.
TAVILY_MAX_RESULTS = 10  # per query
TAVILY_DAYS = 30  # recency window; only applied when TAVILY_TOPIC == "news"
TAVILY_INCLUDE_ANSWER = False
TAVILY_INCLUDE_RAW_CONTENT = False

# Domains that never carry a real engagement lead: job-board aggregators,
# recruitment agencies and social platforms. Matched on the domain itself and
# any subdomain, so "uk.indeed.com" is caught by "indeed.com".
#
# These are passed to Tavily as exclude_domains so they are filtered server
# side, and re-checked locally in case anything slips through.
BLOCKED_DOMAINS: set[str] = {
    # Job-board aggregators
    "indeed.com",
    "linkedin.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "monster.com",
    "reed.co.uk",
    "totaljobs.com",
    "simplyhired.com",
    "careerbuilder.com",
    "naukri.com",
    # Recruitment agencies
    "roberthalf.com",
    # Social and reference
    "youtube.com",
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "tiktok.com",
    "reddit.com",
    "quora.com",
    "wikipedia.org",
    "amazon.com",
    "coursera.org",
    "udemy.com",
}

# URL shapes that mark a search-results or browse page rather than one
# engagement. These catch aggregators we have not named above - a specific
# listing like /jobs/12345 passes, a listing index like /jobs does not.
AGGREGATOR_URL_PATTERNS: list[str] = [
    r"[?&]q=",  # ...?q=fractional+chro
    r"/q-[^/]*-jobs",  # /q-fractional-chro-jobs.html
    r"-jobs\.html?$",  # /fractional-chro-jobs.html
    r"/jobs/?$",  # /jobs
    r"/jobs-in-",  # /jobs-in-london
    r"/job-search",
    r"/browse",
    r"/search/?$",
    r"/careers/?$",
    r"/insights?/",  # rate-benchmark and blog content
    r"/blog/",
]

# Drop a result whose title + snippet is shorter than this - nothing to score.
MIN_SNIPPET_CHARS = 80

# --------------------------------------------------------------------------
# Scoring (Claude)
# --------------------------------------------------------------------------

MODEL = "claude-haiku-4-5"
# Claude Haiku 4-5 does not support extended thinking; effort must be "low".
# max_tokens only needs to cover the structured JSON response itself.
MAX_TOKENS = 4000
EFFORT = "low"  # low | medium | high | xhigh | max
SCORING_WORKERS = 4  # parallel scoring requests
SCORING_MAX_RETRIES = 3

# USD per million tokens, at standard list price (platform.claude.com/docs/en/pricing).
# The Messages API reports token counts, not dollar amounts, so an exact cost
# report needs this table kept current. Some models carry a lower introductory
# price for a limited window; this table holds the standing list price rather
# than a promo, so a reported cost can be a slight overestimate during a promo
# window and is otherwise accurate.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # model id: (input $ / MTok, output $ / MTok)
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost at standard list price for a token count on `model`.

    Returns 0.0 for a model not in MODEL_PRICING rather than raising - a
    missing price entry should degrade the cost report, not break scoring.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return 0.0
    input_price, output_price = pricing
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


# Models that accept the `effort` parameter in output_config. Haiku-class
# models do not support extended thinking and reject `effort` outright.
_EFFORT_SUPPORTED_MODELS: frozenset[str] = frozenset({
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
})


def make_output_config(schema: dict) -> dict:
    """Build the output_config dict for a messages.create() call.

    Includes `effort` only for models that support it.  Haiku 4-5 (and any
    future non-thinking model) will receive only the format key.
    """
    cfg: dict = {"format": {"type": "json_schema", "schema": schema}}
    if MODEL in _EFFORT_SUPPORTED_MODELS:
        cfg["effort"] = EFFORT
    return cfg


# (field name, max points, what the criterion measures)
SCORING_CRITERIA: list[tuple[str, int, str]] = [
    (
        "role_fit",
        25,
        "Does the work match senior HR consulting? Full marks for fractional CHRO, "
        "HR strategy or advisory, people-operations leadership, or work squarely in "
        "the candidate's specialisms: organisational development and design, "
        "performance management systems, learning and development, compensation "
        "design, change management, or senior talent acquisition. Mid marks for "
        "adjacent HR work outside those specialisms. Low marks for "
        "recruiting-coordinator work, HR software sales, generic listicles, or "
        "anything that is not actually HR work.",
    ),
    (
        "consulting_fit",
        20,
        "Is this fractional, contract, interim, retainer or project-based advisory "
        "work? Full marks for an explicitly fractional or consulting engagement. "
        "Zero to low marks for a permanent full-time employee role.",
    ),
    (
        "geography_fit",
        15,
        "Can someone sitting in India actually deliver this remotely? Full marks for "
        "remote-anywhere, remote-global, or India-based work. Mid marks for remote "
        "with a few hours of required time-zone overlap. Zero for on-site-only, "
        "relocation-required, or work-authorisation-restricted engagements.",
    ),
    (
        "seniority_fit",
        10,
        "Does the engagement value 12+ years of experience and head-of or CHRO-level "
        "judgement? Full marks for executive or advisory scope. Low marks for junior "
        "or purely execution-level work.",
    ),
    (
        "company_fit",
        10,
        "Preference, strongest first: startups and scale-ups, SaaS, AI, fintech, "
        "HRTech. Mid marks for other technology or professional-services clients. "
        "Low marks for sectors with poor remote-consulting fit, or where the client "
        "type cannot be identified at all.",
    ),
    (
        "commercial_attractiveness",
        10,
        "Estimated pay or project value against the candidate's target band of "
        "USD 50-150 per hour, or an equivalent project or retainer fee. Full marks "
        "for a stated rate at or above roughly USD 120/hour, a substantial "
        "multi-month retainer, or a well-funded client likely to pay at the top of "
        "the band. Mid marks for the middle of the band, or for a well-resourced "
        "client with no stated rate. Low marks for anything materially below "
        "USD 50/hour, token budgets, unpaid or equity-only work, or gig-marketplace "
        "race-to-the-bottom pricing.",
    ),
    (
        "win_probability",
        10,
        "Realistic chance of actually landing this. Weigh whether the posting looks "
        "live and recent, whether there is a direct way to apply or contact someone, "
        "how much competition is likely, and whether the requirements are attainable. "
        "Low marks for stale content, aggregator spam, or engagements that plainly "
        "require credentials the candidate does not have.",
    ),
]

MAX_SCORE = sum(points for _, points, _ in SCORING_CRITERIA)  # 100

# Ordered high -> low. First matching floor wins.
CLASSIFICATIONS: list[tuple[int, str]] = [
    (85, "PURSUE IMMEDIATELY"),
    (70, "STRONG"),
    (55, "MAYBE"),
    (40, "WEAK"),
    (0, "IGNORE"),
]


def classify(total: int) -> str:
    """Map a 0-100 total onto a classification band."""
    for floor, label in CLASSIFICATIONS:
        if total >= floor:
            return label
    return "IGNORE"


def band_floor(label: str) -> int:
    """The lowest total that still bands as `label`."""
    for floor, band in CLASSIFICATIONS:
        if band == label:
            return floor
    raise KeyError(f"No classification band named {label!r}")


# --------------------------------------------------------------------------
# Score gates
# --------------------------------------------------------------------------
#
# A gate is a structural disqualifier: something that makes an opportunity
# unwinnable no matter how well it scores on the other criteria. Weighting
# cannot express this, because a criterion worth 10 points can always be
# outvoted by the other 90 - a closed listing that is otherwise a perfect
# match still lands in STRONG. A cap is the honest fix.

# Win probability of 0 means the model judged the engagement impossible to
# land - closed, expired, or requiring credentials the candidate lacks.
# Such a listing is capped below the STRONG floor.
GATE_ON_ZERO_WIN_PROBABILITY = True

# A page that is not an actual engagement - a job board, a listicle, an agency
# marketing page - is never worth acting on, whatever the criteria say about
# the topic it discusses. Capped into IGNORE.
GATE_ON_NOT_REAL_OPPORTUNITY = True

# A payload that fails scorer.py's structural consistency check twice (e.g.
# every criterion scored at its exact maximum, or a score that contradicts
# its own summary) cannot be trusted enough to rank as STRONG, whatever the
# individual numbers say.
GATE_ON_CONSISTENCY_FAILURE = True


def apply_score_gates(
    scores: dict[str, int],
    total: int,
    is_real_opportunity: bool = True,
    consistency_failed: bool = False,
) -> tuple[int, str]:
    """Cap a total for structural disqualifiers.

    Returns the (possibly reduced) total and a note explaining any cap, or an
    empty string when no gate fired. Gates are checked strongest first, and
    only the strongest one that fires is reported.
    """
    if GATE_ON_NOT_REAL_OPPORTUNITY and not is_real_opportunity:
        cap = band_floor("WEAK") - 1
        if total > cap:
            return cap, (
                f"Score capped from {total} to {cap}: this is not an actual "
                "engagement (job board, listicle or marketing page), so it cannot "
                "rank above IGNORE."
            )
        return total, ""

    if GATE_ON_CONSISTENCY_FAILURE and consistency_failed:
        cap = band_floor("STRONG") - 1
        if total > cap:
            return cap, (
                f"Score capped from {total} to {cap}: this result failed an "
                "automated consistency check on both the original and a corrective "
                "re-score, so it cannot rank as STRONG however well it scores "
                "elsewhere. Verify it by hand before acting on it."
            )
        return total, ""

    if GATE_ON_ZERO_WIN_PROBABILITY and scores.get("win_probability", 1) == 0:
        cap = band_floor("STRONG") - 1
        if total > cap:
            return cap, (
                f"Score capped from {total} to {cap}: win probability is 0, so this "
                "cannot rank as STRONG however well it scores elsewhere."
            )
    return total, ""


ENGAGEMENT_TYPES = [
    "Fractional CHRO",
    "Fractional HR",
    "HR Consulting Project",
    "People Ops Consulting",
    "HR Advisory",
    "HR Transformation",
    "Org Design",
    "People Strategy",
    "Interim HR",
    "Contract HR",
    "Other",
    "Not an opportunity",
]

# --------------------------------------------------------------------------
# Airtable
# --------------------------------------------------------------------------

# Left side is our internal key, right side is the column name in your table.
# Rename the right-hand values to match your base; nothing else has to change.
AIRTABLE_FIELDS: dict[str, str] = {
    "title": "Title",
    "url": "URL",
    "company": "Company",
    "role_title": "Role Title",
    "engagement_type": "Engagement Type",
    "source_query": "Source Query",
    "summary": "Summary",
    "total_score": "Total Score",
    "classification": "Classification",
    "role_fit": "Role Fit",
    "consulting_fit": "Consulting Fit",
    "geography_fit": "Geography Fit",
    "seniority_fit": "Seniority Fit",
    "company_fit": "Company Fit",
    "commercial_attractiveness": "Commercial Attractiveness",
    "win_probability": "Win Probability",
    "estimated_value": "Estimated Value",
    "key_reasons": "Key Reasons",
    "red_flags": "Red Flags",
    "recommended_action": "Recommended Action",
    "found_at": "Found At",
}

# Airtable field type for each internal key. Used by setup.py to create the
# columns; ignored at runtime. Format is (airtable_type, options_or_None).
# Field type reference: https://airtable.com/developers/web/api/field-model
AIRTABLE_FIELD_TYPES: dict[str, tuple[str, dict | None]] = {
    "title": ("singleLineText", None),
    "url": ("url", None),
    "company": ("singleLineText", None),
    "role_title": ("singleLineText", None),
    "engagement_type": (
        "singleSelect",
        {"choices": [{"name": name} for name in ENGAGEMENT_TYPES]},
    ),
    "source_query": ("singleLineText", None),
    "summary": ("multilineText", None),
    "total_score": ("number", {"precision": 0}),
    "classification": (
        "singleSelect",
        {"choices": [{"name": label} for _, label in CLASSIFICATIONS]},
    ),
    "role_fit": ("number", {"precision": 0}),
    "consulting_fit": ("number", {"precision": 0}),
    "geography_fit": ("number", {"precision": 0}),
    "seniority_fit": ("number", {"precision": 0}),
    "company_fit": ("number", {"precision": 0}),
    "commercial_attractiveness": ("number", {"precision": 0}),
    "win_probability": ("number", {"precision": 0}),
    "estimated_value": ("singleLineText", None),
    "key_reasons": ("multilineText", None),
    "red_flags": ("multilineText", None),
    "recommended_action": ("multilineText", None),
    # Kept as text rather than dateTime so the ISO timestamp round-trips
    # without depending on Airtable's date parsing.
    "found_at": ("singleLineText", None),
}

# Short help text written onto each created column.
AIRTABLE_FIELD_DESCRIPTIONS: dict[str, str] = {
    "url": "Deduplication key. Project Scout skips URLs already stored here.",
    "total_score": f"Sum of the seven criteria, out of {MAX_SCORE}.",
    "classification": "Band derived from Total Score.",
    "found_at": "UTC ISO 8601 timestamp of the run that found this.",
}

# The URL column drives deduplication. It must exist in the table.
AIRTABLE_URL_FIELD = AIRTABLE_FIELDS["url"]

# Airtable caps batch writes at 10 records per request.
AIRTABLE_BATCH_SIZE = 10

# Save any scored opportunity at or above this total. 0 saves everything.
SAVE_ONLY_ABOVE = 0

# ==========================================================================
# ENGINE B: Company Intelligence
# ==========================================================================
#
# A different shape of scouting: instead of searching for consulting job
# postings, this engine watches funding-news sites for newly funded
# startups, then checks whether each one already has an HR/People leader.
# A freshly funded company with no HR lead yet is a warm outbound target for
# fractional HR work - that is what company_score measures.

# --------------------------------------------------------------------------
# Sourcing
# --------------------------------------------------------------------------
#
# IMPLEMENTATION NOTE - scraping vs. search API: the brief describes this as
# "scraping" the five sites directly. Engine B instead reuses the same
# Tavily Search API Engine A already uses, scoped to these five domains via
# `include_domains`, rather than hand-writing an HTML parser per site. Two
# reasons: several of these publishers rate-limit or block non-browser
# traffic (especially from a shared GitHub Actions IP range), and a per-site
# scraper breaks silently the next time any of the five redesigns its page -
# a search API absorbs that. If true HTML scraping of these exact sites is
# still wanted despite the fragility, that is a different, larger
# implementation and worth a separate conversation about the tradeoffs.
COMPANY_SOURCE_DOMAINS: list[str] = [
    # --- India ---
    "inc42.com",
    "yourstory.com",
    "entrackr.com",
    "vccircle.com",
    "economictimes.indiatimes.com",
    "livemint.com",
    # --- SEA / Middle East ---
    "techinasia.com",
    "dealstreetasia.com",
    "wamda.com",
    "magnitt.com",
    # --- Global early-stage ---
    "techcrunch.com",
    "producthunt.com",
]

COMPANY_SEARCH_QUERIES: list[str] = [
    # India-specific — matches headline phrasing on inc42, yourstory, entrackr,
    # vccircle, ET Startups and Mint.
    "seed funding round India startup",
    "pre-seed funding raised India startup",
    "series A funding India startup",
    "raises seed round India",
    "raises pre-seed India",
    "secures seed funding India",
    "seed round startup India 2026",
    # SEA / Middle East — matches techinasia, dealstreetasia, wamda, magnitt.
    "seed round raised startup Singapore",
    "startup raises funding Singapore 2026",
    "seed funding startup UAE",
    "funding raised startup Saudi Arabia",
    "seed round startup Southeast Asia",
    # Global early-stage — matches TechCrunch Startups tag and ProductHunt launches.
    "raises seed round startup",
    "raises pre-seed round",
    "raises series A startup",
    "secures funding round startup",
    "pre-seed funding startup 2026",
    "seed funding startup 2026",
]

COMPANY_TAVILY_SEARCH_DEPTH = "advanced"
COMPANY_TAVILY_MAX_RESULTS = 10
COMPANY_TAVILY_DAYS = 14  # widened from 7: Tavily's news index can lag 3-5 days,
# so a 7-day window was regularly returning 0 results for many queries.
COMPANY_MIN_SNIPPET_CHARS = 80

# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------

COMPANY_TARGET_GEOGRAPHIES = [
    "India",
    "Singapore",
    "Indonesia",
    "UAE",
    "Saudi Arabia",
    "Malaysia",
    "Vietnam",
    "Philippines",
]
COMPANY_ALLOWED_FUNDING_STAGES = ["pre-seed", "seed", "pre-series a", "series a"]
COMPANY_MAX_EMPLOYEES_SECONDARY = 100  # anything above this is filtered out entirely

# --------------------------------------------------------------------------
# Career-page HR-lead detection
# --------------------------------------------------------------------------
#
# HONEST LIMITATION: company_analyzer.py fetches a company's public careers
# page with a plain HTTP GET - there is no headless browser and no
# JavaScript execution. A growing share of career pages are single-page
# apps, or embed a Greenhouse/Lever/Ashby widget that renders client-side;
# a plain GET sees an empty shell on those. When that happens the result is
# reported as *undetermined*, never as a confirmed "no HR lead" - conflating
# the two would quietly wreck the scoring, since "undetermined" is common
# and "confirmed absent" is the entire point of the +40 score. See
# CareerPageResult in company_analyzer.py.
HR_TITLE_KEYWORDS: list[str] = [
    "hr", "people", "chro", "chief people officer", "chief people",
    "head of hr", "head of people", "hr manager", "people operations",
    "people ops", "human resources", "vp of people", "vp people",
    "director of people", "hrbp", "hr business partner", "talent partner",
]

CAREER_LINK_TEXT_HINTS = [
    "career", "careers", "job", "jobs", "join us", "join our team",
    "we're hiring", "hiring", "open roles", "open positions", "work with us",
]
CAREER_PATH_GUESSES = [
    "/careers", "/careers/", "/jobs", "/jobs/", "/join-us",
    "/about/careers", "/company/careers", "/about-us/careers",
]

HTTP_USER_AGENT = "Mozilla/5.0 (compatible; ProjectScoutBot/1.0; company research)"
HTTP_TIMEOUT_SECONDS = 10
HTTP_MAX_CONTENT_CHARS = 200_000  # cap what we parse from any one page

# --------------------------------------------------------------------------
# Scoring - a fixed point formula, not a Claude rubric
# --------------------------------------------------------------------------
#
# Unlike Engine A (where "how good a fit" is a judgment call), every one of
# these four criteria is a fact Python can check directly once Claude has
# extracted the structured fields and company_analyzer.py has checked the
# careers page. Doing the arithmetic in Python means the total can never
# disagree with its own inputs the way an LLM-computed score occasionally
# can (see scorer.py's consistency-check comment for the failure this
# avoids). Claude's job in Engine B is extraction and the score_reason
# narrative, not the point total.
# HR-lead scoring is graded, not a single confirmed/not-confirmed boolean.
# A live run showed why the binary version failed in practice: the
# companies Engine B targets (pre-seed/seed, 1-50 people) are exactly the
# companies least likely to have a discoverable careers page at all, so
# "we couldn't check" and "confirmed no HR" ended up scored identically
# (0), and almost nothing this engine is built to find ever cleared the
# save threshold. Four tiers, worst to best signal:
COMPANY_SCORE_HR_CONFIRMED_PRESENT = 0    # careers page loaded and searched - an HR/People role WAS found
COMPANY_SCORE_HR_DOMAIN_UNRESOLVED = 5    # domain unresolved, homepage unreachable, or an unparseable page - no real signal either way
COMPANY_SCORE_HR_NO_CAREERS_PAGE = 20     # homepage loads, no careers page found anywhere - a soft positive signal
COMPANY_SCORE_HR_CONFIRMED_ABSENT = 30    # careers page loaded and searched - no HR/People role found (best signal)

COMPANY_SCORE_EMPLOYEES_1_10 = 15
COMPANY_SCORE_EMPLOYEES_10_50 = 25
COMPANY_SCORE_EMPLOYEES_51_100 = 10
# Funding articles very often just don't state headcount - that's normal,
# not a red flag, so unstated no longer scores the same as "outside every
# band" (0). It scores below every *known* band, on the theory that a
# verified number should always beat a guess.
COMPANY_SCORE_EMPLOYEES_UNSTATED = 10
COMPANY_SCORE_STAGE_SEED_OR_PRESERIES_A = 20
# Not specified in the original brief, which only scored seed/pre-series A
# explicitly. Pre-seed and Series A are still in-scope per the filtering
# criteria, so they get partial credit here rather than zero - change this
# if you want them weighted differently.
COMPANY_SCORE_STAGE_OTHER_ALLOWED = 12
COMPANY_SCORE_GEOGRAPHY_INDIA = 15
COMPANY_SCORE_GEOGRAPHY_OTHER_TARGET = 10

# 30 (hr, confirmed absent) + 25 (employees) + 20 (stage) + 15 (geography).
# Dropped from 100 when the HR-lead ceiling dropped from 40 to 30 above -
# the other three criteria's weights are unchanged from the original brief,
# so the achievable maximum is honestly 90, not 100. COMPANY_SAVE_ONLY_ABOVE
# was NOT rescaled to match - it's still the original 50, which is now a
# proportionally higher bar (55.6% of max, not 50%) than before. Rescale it
# too if that wasn't the intent.
COMPANY_MAX_SCORE = 90

COMPANY_SAVE_ONLY_ABOVE = 50

# LinkedIn employee-count fallback: only worth the extra Tavily call when the
# company already looks promising on the criteria that don't need it. Gate is
# the sum of hr_lead + funding_stage + geography (employee_count excluded,
# since that's the very thing being decided) - see company_runner.py. Because
# hr_lead now grades as high as 30 on its own (previously 40-or-0), this gate
# fires considerably more often than it used to - a company with just a
# "no careers page found" signal (20) plus best-case stage and geography
# (20+15=35) already clears 40 without hr_lead needing to be at its ceiling.
COMPANY_LINKEDIN_FALLBACK_THRESHOLD = 40


def score_company(
    *,
    hr_lead_points: int,
    employee_count: int | None,
    funding_stage: str,
    geography: str,
) -> tuple[int, dict[str, int]]:
    """The fixed-formula company_score, plus the per-criterion breakdown.

    `hr_lead_points` comes directly from company_analyzer.CareerPageResult -
    it is already the graded score for whichever of the four HR-lead tiers
    applied, not a boolean this function re-derives a score from.
    """
    breakdown: dict[str, int] = {"hr_lead": hr_lead_points}

    if employee_count is None:
        breakdown["employee_count"] = COMPANY_SCORE_EMPLOYEES_UNSTATED
    elif 1 <= employee_count <= 10:
        breakdown["employee_count"] = COMPANY_SCORE_EMPLOYEES_1_10
    elif 11 <= employee_count <= 50:
        breakdown["employee_count"] = COMPANY_SCORE_EMPLOYEES_10_50
    elif 51 <= employee_count <= COMPANY_MAX_EMPLOYEES_SECONDARY:
        breakdown["employee_count"] = COMPANY_SCORE_EMPLOYEES_51_100
    else:
        breakdown["employee_count"] = 0

    stage = (funding_stage or "").strip().lower()
    if stage in ("seed", "pre-series a"):
        breakdown["funding_stage"] = COMPANY_SCORE_STAGE_SEED_OR_PRESERIES_A
    elif stage in COMPANY_ALLOWED_FUNDING_STAGES:  # pre-seed, series a
        breakdown["funding_stage"] = COMPANY_SCORE_STAGE_OTHER_ALLOWED
    else:
        breakdown["funding_stage"] = 0

    geo = (geography or "").strip().lower()
    if geo == "india":
        breakdown["geography"] = COMPANY_SCORE_GEOGRAPHY_INDIA
    elif geo in (g.lower() for g in COMPANY_TARGET_GEOGRAPHIES):
        breakdown["geography"] = COMPANY_SCORE_GEOGRAPHY_OTHER_TARGET
    else:
        breakdown["geography"] = 0

    return sum(breakdown.values()), breakdown


# --------------------------------------------------------------------------
# Airtable - a second table in the same base
# --------------------------------------------------------------------------

COMPANY_AIRTABLE_TABLE_NAME = "Companies"
# Populated after setup.py (or company_runner.py's own setup step) creates
# the table and prints its ID - put that ID here or in AIRTABLE_COMPANIES_TABLE_ID
# in .env. Table IDs are not secrets; they identify a table, not a credential.
AIRTABLE_COMPANIES_TABLE_ID = os.getenv("AIRTABLE_COMPANIES_TABLE_ID", "")

# Field names are used as-is - Airtable column names, not display labels to
# translate. Kept snake_case to match the spec exactly.
COMPANY_AIRTABLE_FIELDS: dict[str, str] = {
    "company_name": "company_name",
    "sector": "sector",
    "funding_stage": "funding_stage",
    "funding_amount": "funding_amount",
    "employee_count": "employee_count",
    "geography": "geography",
    "career_page_url": "career_page_url",
    "has_hr_lead": "has_hr_lead",
    "hr_signals": "hr_signals",
    "company_score": "company_score",
    "score_reason": "score_reason",
    "funding_source": "funding_source",
    "date_funded": "date_funded",
    "status": "status",
    "date_added": "date_added",
}

COMPANY_STATUS_VALUES = ["new", "reviewing", "targeted", "contacted", "won"]

COMPANY_AIRTABLE_FIELD_TYPES: dict[str, tuple[str, dict | None]] = {
    "company_name": ("singleLineText", None),
    "sector": ("singleLineText", None),
    "funding_stage": ("singleLineText", None),
    "funding_amount": ("singleLineText", None),
    "employee_count": ("number", {"precision": 0}),
    "geography": ("singleLineText", None),
    "career_page_url": ("url", None),
    "has_hr_lead": ("checkbox", {"icon": "check", "color": "greenBright"}),
    "hr_signals": ("multilineText", None),
    "company_score": ("number", {"precision": 0}),
    "score_reason": ("multilineText", None),
    "funding_source": ("singleLineText", None),
    "date_funded": ("date", {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}}),
    "status": (
        "singleSelect",
        {"choices": [{"name": s} for s in COMPANY_STATUS_VALUES]},
    ),
    "date_added": ("date", {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}}),
}

COMPANY_AIRTABLE_FIELD_DESCRIPTIONS: dict[str, str] = {
    "career_page_url": "Deduplication is by website domain, not this field - see company_search.py.",
    "has_hr_lead": "True only if company_analyzer.py found an HR/People title on the careers page.",
    "hr_signals": "What was found or why the check was inconclusive (e.g. JS-rendered page).",
    "company_score": f"Fixed-formula score out of {COMPANY_MAX_SCORE} - see config.score_company().",
    "status": "Manual triage field. The pipeline always inserts 'new'; update it yourself.",
}

COMPANY_AIRTABLE_DEDUPE_FIELD = COMPANY_AIRTABLE_FIELDS["career_page_url"]

# ==========================================================================
# ENGINE C: Career Signal (wellfound_runner.py)
# ==========================================================================
#
# Instead of watching funding news, this engine watches job boards for
# early-stage startups actively posting HR/People leadership roles. A company
# searching for a Head of People or VP People is the warmest possible outbound
# target: they've diagnosed the HR gap, approved budget, and haven't filled it.
# The pitch: fractional HR while the permanent search continues.

# --------------------------------------------------------------------------
# Sourcing
# --------------------------------------------------------------------------

WELLFOUND_SOURCE_DOMAINS: list[str] = [
    # Startup-first job boards where stage/funding context is often stated
    "wellfound.com",           # formerly AngelList Talent - best startup signal
    "workatastartup.com",      # YC's job board - well-funded, early-stage bias
    # Broad job boards that index startup postings
    "lever.co",                # ATS used by many startups - postings are public
    "ashbyhq.com",             # ATS used by Series A/B startups
    "greenhouse.io",           # ATS used by growth-stage startups
    # Regional startup boards
    "iimjobs.com",             # India HR/leadership roles
    "foundit.in",              # India startup jobs (formerly Monster India)
]

WELLFOUND_SEARCH_QUERIES: list[str] = [
    # Wellfound / AngelList-specific queries
    "head of people startup wellfound",
    "VP people early stage startup wellfound",
    "HR manager seed stage startup wellfound",
    "people operations lead startup wellfound India",
    "chief people officer startup wellfound",
    # YC / top-tier startup boards
    "head of people startup YC hiring",
    "VP people operations startup hiring India remote",
    # Generic startup HR leadership
    "head of people early stage startup hiring",
    "HR manager seed stage startup hiring",
    "people operations lead series A startup hiring",
    "chief people officer startup hiring",
    "VP people culture startup hiring remote",
    "first HR hire startup head of people",
    # India/SEA-specific
    "head of people startup India hiring",
    "HR lead startup India seed series A",
    "people operations startup Singapore hiring",
    "HR manager startup UAE hiring",
]

WELLFOUND_TAVILY_SEARCH_DEPTH = "advanced"
WELLFOUND_TAVILY_MAX_RESULTS = 10
WELLFOUND_MIN_SNIPPET_CHARS = 80

# --------------------------------------------------------------------------
# Scoring - fixed-formula (same philosophy as Engine B)
# --------------------------------------------------------------------------
#
# Five criteria, all computable from Claude's extracted facts:
#   hr_role_seniority  - how senior/impactful is the HR gap?
#   employee_count     - smallest companies are the warmest targets
#   funding_stage      - seed/series A = actively investing in growth
#   geography          - India and target geographies get preference
#   sector             - startup-first sectors score higher

# Role seniority: the more senior the gap, the bigger the fractional opportunity
WELLFOUND_SCORE_ROLE_CHRO_VP = 30          # CHRO, CPO, VP People/Culture
WELLFOUND_SCORE_ROLE_HEAD_DIRECTOR = 25    # Head of People, Director of People
WELLFOUND_SCORE_ROLE_MANAGER = 20          # HR Manager (as first hire), People Ops Lead
WELLFOUND_SCORE_ROLE_OTHER_HR = 10         # Any other HR role that passed the filter

# Employee count: smaller = warmer (less likely to have informal HR coverage)
WELLFOUND_SCORE_EMPLOYEES_1_10 = 20
WELLFOUND_SCORE_EMPLOYEES_10_50 = 25       # sweet spot: big enough to feel the pain
WELLFOUND_SCORE_EMPLOYEES_51_100 = 15
WELLFOUND_SCORE_EMPLOYEES_UNSTATED = 12    # still useful, just less certain

# Funding stage
WELLFOUND_SCORE_STAGE_SEED_PRESERIES_A = 20
WELLFOUND_SCORE_STAGE_OTHER_ALLOWED = 12   # pre-seed or series a
WELLFOUND_SCORE_STAGE_UNSTATED = 5         # present on job board = probably funded

# Geography (same weights as Engine B for consistency)
WELLFOUND_SCORE_GEOGRAPHY_INDIA = 15
WELLFOUND_SCORE_GEOGRAPHY_OTHER_TARGET = 10
WELLFOUND_SCORE_GEOGRAPHY_REMOTE = 8       # globally remote = accessible but less certain
WELLFOUND_SCORE_GEOGRAPHY_UNKNOWN = 3      # still counts if other criteria are strong

# Sector preference
WELLFOUND_SCORE_SECTOR_TOP = 10            # SaaS, AI, Fintech, HRTech, startup
WELLFOUND_SCORE_SECTOR_MID = 6             # tech-adjacent, professional services
WELLFOUND_SCORE_SECTOR_OTHER = 2           # any other

# 30 (role) + 25 (employees) + 20 (stage) + 15 (geography) + 10 (sector) = 100
WELLFOUND_MAX_SCORE = 100
WELLFOUND_SAVE_ONLY_ABOVE = 50

_WELLFOUND_TOP_SECTORS = frozenset({
    "saas", "ai", "artificial intelligence", "fintech", "hrtech", "hr tech",
    "hr technology", "startup", "tech", "technology", "software",
})
_WELLFOUND_MID_SECTORS = frozenset({
    "e-commerce", "ecommerce", "marketplace", "edtech", "healthtech",
    "proptech", "legaltech", "professional services", "consulting",
})


def score_hr_job(
    *,
    role_title: str,
    employee_count: int | None,
    funding_stage: str,
    geography: str,
    sector: str,
) -> tuple[int, dict[str, int]]:
    """Fixed-formula score for an Engine C job lead.

    Returns (total, breakdown_dict). All arithmetic - no model judgment here.
    """
    breakdown: dict[str, int] = {}

    # --- HR role seniority ---
    title_lower = (role_title or "").strip().lower()
    if any(kw in title_lower for kw in ("chro", "chief people", "vp people", "vp of people",
                                         "vp culture", "vice president people")):
        breakdown["hr_role_seniority"] = WELLFOUND_SCORE_ROLE_CHRO_VP
    elif any(kw in title_lower for kw in ("head of people", "director of people",
                                            "head of hr", "director of hr",
                                            "director people", "people director")):
        breakdown["hr_role_seniority"] = WELLFOUND_SCORE_ROLE_HEAD_DIRECTOR
    elif any(kw in title_lower for kw in ("hr manager", "people manager",
                                            "people operations lead", "people ops lead",
                                            "chief of staff")):
        breakdown["hr_role_seniority"] = WELLFOUND_SCORE_ROLE_MANAGER
    else:
        breakdown["hr_role_seniority"] = WELLFOUND_SCORE_ROLE_OTHER_HR

    # --- Employee count ---
    if employee_count is None:
        breakdown["employee_count"] = WELLFOUND_SCORE_EMPLOYEES_UNSTATED
    elif 1 <= employee_count <= 10:
        breakdown["employee_count"] = WELLFOUND_SCORE_EMPLOYEES_1_10
    elif 11 <= employee_count <= 50:
        breakdown["employee_count"] = WELLFOUND_SCORE_EMPLOYEES_10_50
    elif 51 <= employee_count <= COMPANY_MAX_EMPLOYEES_SECONDARY:
        breakdown["employee_count"] = WELLFOUND_SCORE_EMPLOYEES_51_100
    else:
        breakdown["employee_count"] = 0

    # --- Funding stage ---
    stage = (funding_stage or "").strip().lower()
    if stage in ("seed", "pre-series a"):
        breakdown["funding_stage"] = WELLFOUND_SCORE_STAGE_SEED_PRESERIES_A
    elif stage in ("pre-seed", "series a"):
        breakdown["funding_stage"] = WELLFOUND_SCORE_STAGE_OTHER_ALLOWED
    elif not stage:
        breakdown["funding_stage"] = WELLFOUND_SCORE_STAGE_UNSTATED
    else:
        breakdown["funding_stage"] = 0

    # --- Geography ---
    geo = (geography or "").strip().lower()
    if geo == "india":
        breakdown["geography"] = WELLFOUND_SCORE_GEOGRAPHY_INDIA
    elif geo in (g.lower() for g in COMPANY_TARGET_GEOGRAPHIES):
        breakdown["geography"] = WELLFOUND_SCORE_GEOGRAPHY_OTHER_TARGET
    elif geo in ("remote", "global", "global remote", "worldwide"):
        breakdown["geography"] = WELLFOUND_SCORE_GEOGRAPHY_REMOTE
    elif not geo:
        breakdown["geography"] = WELLFOUND_SCORE_GEOGRAPHY_UNKNOWN
    else:
        breakdown["geography"] = 0

    # --- Sector ---
    sector_lower = (sector or "").strip().lower()
    if any(s in sector_lower for s in _WELLFOUND_TOP_SECTORS):
        breakdown["sector"] = WELLFOUND_SCORE_SECTOR_TOP
    elif any(s in sector_lower for s in _WELLFOUND_MID_SECTORS):
        breakdown["sector"] = WELLFOUND_SCORE_SECTOR_MID
    elif sector_lower:
        breakdown["sector"] = WELLFOUND_SCORE_SECTOR_OTHER
    else:
        breakdown["sector"] = 0

    return sum(breakdown.values()), breakdown


# --------------------------------------------------------------------------
# Airtable - a third table in the same base
# --------------------------------------------------------------------------

WELLFOUND_AIRTABLE_TABLE_NAME = "JobLeads"
AIRTABLE_JOBLEADS_TABLE_ID = os.getenv("AIRTABLE_JOBLEADS_TABLE_ID", "")

WELLFOUND_STATUS_VALUES = ["new", "reviewing", "targeted", "contacted", "won"]

WELLFOUND_AIRTABLE_FIELDS: dict[str, str] = {
    "company_name": "company_name",
    "role_title": "role_title",
    "sector": "sector",
    "funding_stage": "funding_stage",
    "employee_count": "employee_count",
    "geography": "geography",
    "company_domain": "company_domain",
    "is_remote_eligible": "is_remote_eligible",
    "job_score": "job_score",
    "score_reason": "score_reason",
    "source_domain": "source_domain",
    "lead_url": "lead_url",
    "status": "status",
    "date_added": "date_added",
}

WELLFOUND_AIRTABLE_FIELD_TYPES: dict[str, tuple[str, dict | None]] = {
    "company_name": ("singleLineText", None),
    "role_title": ("singleLineText", None),
    "sector": ("singleLineText", None),
    "funding_stage": ("singleLineText", None),
    "employee_count": ("number", {"precision": 0}),
    "geography": ("singleLineText", None),
    "company_domain": ("singleLineText", None),
    "is_remote_eligible": ("checkbox", {"icon": "check", "color": "greenBright"}),
    "job_score": ("number", {"precision": 0}),
    "score_reason": ("multilineText", None),
    "source_domain": ("singleLineText", None),
    "lead_url": ("url", None),
    "status": (
        "singleSelect",
        {"choices": [{"name": s} for s in WELLFOUND_STATUS_VALUES]},
    ),
    "date_added": ("date", {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}}),
}

WELLFOUND_AIRTABLE_FIELD_DESCRIPTIONS: dict[str, str] = {
    "company_domain": "Deduplication key. Engine C skips domains already in this table or in Companies (Engine B).",
    "is_remote_eligible": "True if the role can be filled by someone working remotely from India.",
    "job_score": f"Fixed-formula score out of {WELLFOUND_MAX_SCORE} - see config.score_hr_job().",
    "status": "Manual triage field. The pipeline always inserts 'new'; update it yourself.",
    "lead_url": "Direct URL to the job posting. Check this first - postings disappear fast.",
}

# ==========================================================================
# FEATURE: Contact Finder (contact_finder.py)
# ==========================================================================
#
# Runs after Engine B. Finds a founder/CEO for any Companies row that's
# still status == "new" and scored well enough to be worth outreach.
#
# Never-hallucinate-a-URL is enforced structurally, not just by instruction:
# Claude is shown candidate search results with the URL withheld (title and
# snippet text only) and picks which numbered candidate is the real match:
# the URL that ends up saved is read from the original Tavily result by
# that index, never generated by the model. A URL Claude never sees cannot
# appear, correctly or otherwise, in what it writes.
CONTACT_MIN_SCORE = 60
CONTACT_TRIGGER_STATUS = "new"
CONTACT_SEARCH_QUERY_TEMPLATE = "{company_name} founder CEO LinkedIn"
CONTACT_TAVILY_MAX_RESULTS = 8

COMPANY_CONTACT_FIELDS: dict[str, str] = {
    "founder_name": "founder_name",
    "founder_title": "founder_title",
    "founder_linkedin_url": "founder_linkedin_url",
}
COMPANY_CONTACT_FIELD_TYPES: dict[str, tuple[str, dict | None]] = {
    "founder_name": ("singleLineText", None),
    "founder_title": ("singleLineText", None),
    "founder_linkedin_url": ("url", None),
}
COMPANY_CONTACT_FIELD_DESCRIPTIONS: dict[str, str] = {
    "founder_linkedin_url": (
        "Sourced verbatim from a Tavily search result URL, never model-generated. "
        "Only linkedin.com/in/ URLs are accepted."
    ),
}

# ==========================================================================
# FEATURE: Daily Email Digest (digest.py)
# ==========================================================================
#
# NOTE ON RESEND: this project has no prior Resend configuration - there is
# no record of it anywhere in this codebase before this feature was added.
# RESEND_API_KEY is a placeholder in .env like every other credential here;
# fill in a real key before this can actually send. RESEND_FROM_EMAIL must
# also be a sender identity/domain verified in that Resend account, or every
# send attempt returns a 403 regardless of the API key being valid.
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "info@virorah.com")
DIGEST_TO_EMAIL = "kumarvivek.srv@gmail.com"
DIGEST_TOP_N_OPPORTUNITIES = 5
DIGEST_COMPANY_MIN_SCORE = 60

# --------------------------------------------------------------------------
# Console output
# --------------------------------------------------------------------------

TOP_N_TO_PRINT = 15
CONSOLE_WIDTH = 78
