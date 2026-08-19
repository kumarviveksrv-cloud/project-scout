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

_PLACEHOLDER_MARKERS = ("xxxx", "XXXX", "your_", "your ", "<", ">", "REPLACE_ME")


def missing_credentials() -> list[str]:
    """Names of env vars that are empty or still hold the .env template value."""
    required = {
        "TAVILY_API_KEY": TAVILY_API_KEY,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "AIRTABLE_TOKEN": AIRTABLE_TOKEN,
        "AIRTABLE_BASE_ID": AIRTABLE_BASE_ID,
        "AIRTABLE_TABLE_ID": AIRTABLE_TABLE_ID,
    }
    bad = []
    for name, value in required.items():
        if not value.strip():
            bad.append(name)
        elif any(marker in value for marker in _PLACEHOLDER_MARKERS):
            bad.append(name)
    return bad


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
TAVILY_TOPIC = "news"  # "general" or "news"
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

MODEL = "claude-sonnet-5"
# Claude Sonnet 5 thinks by default (adaptive thinking), and max_tokens caps
# thinking + response together. Leave headroom or responses truncate mid-answer.
MAX_TOKENS = 8000
EFFORT = "medium"  # low | medium | high | xhigh | max
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

# --------------------------------------------------------------------------
# Console output
# --------------------------------------------------------------------------

TOP_N_TO_PRINT = 15
CONSOLE_WIDTH = 78
