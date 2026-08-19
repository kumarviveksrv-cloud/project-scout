# Project Scout

Two engines, one goal: surface warm HR-consulting leads for a senior India-based
HR professional (12+ years) and store them in Airtable.

- **Engine A — Opportunities** (`scout.py`): searches for HR consulting job
  postings, scores each one out of 100 against a weighted rubric.
- **Engine B — Company Intelligence** (`company_runner.py`): watches startup
  funding news, checks whether each newly funded company already has an
  HR/People lead, and scores the ones that don't as outbound targets.

Both run daily via [`.github/workflows/daily_scout.yml`](.github/workflows/daily_scout.yml).

## Setup

1. **Install Python 3.14**, if not already present. Get it from
   [python.org](https://www.python.org/downloads/windows/) and tick
   *Add python.exe to PATH* during install.

2. **Install dependencies**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Fill in `.env`** — replace every placeholder with a real key. Engine B
   also needs `AIRTABLE_COMPANIES_TABLE_ID`, which doesn't exist until step 5
   creates it — leave it blank for now.

4. **Create Engine A's Airtable columns** — automatically:

   ```bash
   python setup.py --dry-run   # show what would be created
   python setup.py             # create the missing columns
   python setup.py --check     # verify the table is ready
   ```

   This needs a token with `schema.bases:read` and `schema.bases:write` on top of
   the record scopes. It is safe to re-run: existing columns are never recreated
   or retyped, and type mismatches are reported rather than "fixed" (retyping a
   populated column is destructive, so that stays your call).

   Airtable gives every new table a primary column, usually `Name`, that the API
   cannot delete. Project Scout ignores it. If you want `Title` to be the primary
   column, rename `Name` to `Title` in the Airtable UI *before* running setup.

   For reference, these are the columns it creates. The names come from
   `config.AIRTABLE_FIELDS` — rename them there if you prefer different ones.

   | Column | Airtable field type |
   | --- | --- |
   | Title | Single line text |
   | URL | URL |
   | Company | Single line text |
   | Role Title | Single line text |
   | Engagement Type | Single select |
   | Source Query | Single line text |
   | Summary | Long text |
   | Total Score | Number (integer) |
   | Classification | Single select |
   | Role Fit | Number (integer) |
   | Consulting Fit | Number (integer) |
   | Geography Fit | Number (integer) |
   | Seniority Fit | Number (integer) |
   | Company Fit | Number (integer) |
   | Commercial Attractiveness | Number (integer) |
   | Win Probability | Number (integer) |
   | Estimated Value | Single line text |
   | Key Reasons | Long text |
   | Red Flags | Long text |
   | Recommended Action | Long text |
   | Found At | Single line text |

   Records are written with `typecast=True`, so Airtable adds missing single-select
   options on the fly. **URL** is the deduplication key and must exist.

   To create the table by hand instead, build those columns with those types and
   skip `setup.py`.

5. **Create the Companies table for Engine B** — also automatic:

   ```bash
   python company_runner.py --setup-only
   ```

   Prints the new table's ID. Put it in `.env` as `AIRTABLE_COMPANIES_TABLE_ID`.
   Same idempotency guarantee as `setup.py` — safe to re-run, never retypes an
   existing column. See the field list under **Engine B** below.

## Running

```bash
# Engine A
python scout.py                  # full run
python scout.py --dry-run        # search + score, write nothing
python scout.py --limit 5        # score only 5 hits, to sanity-check cheaply
python scout.py --json run.json  # also dump results locally
python scout.py --min-score 55   # only print MAYBE and above

# Engine B
python company_runner.py                    # full run
python company_runner.py --dry-run --limit 10  # preview 10 leads, write nothing
python company_runner.py --json run.json     # also dump results locally
```

Start both with `--dry-run --limit N`. That exercises the real APIs without
touching Airtable and costs a few cents — the console prints exactly what
would have been saved.

## Files

| File | What it does |
| --- | --- |
| `config.py` | Every setting for both engines: queries, rubrics, thresholds, column names, model, pricing |
| `database.py` | Shared Airtable layer — reads, batched writes, table/column creation via the Meta API |
| **Engine A** | |
| `setup.py` | One-time Airtable column creation for the Opportunities table |
| `search.py` | Tavily search, URL canonicalisation, in-run deduplication |
| `scorer.py` | Claude scoring via structured outputs, retries, consistency re-score, usage tracking |
| `scout.py` | Orchestrator + console report |
| **Engine B** | |
| `company_search.py` | Tavily-based funding-news search across 5 publishers; company-domain resolution |
| `company_analyzer.py` | Fetches a company's careers page and scans it for HR/People job titles |
| `company_scorer.py` | Claude extraction of company facts; fixed-formula scoring in Python |
| `company_runner.py` | Orchestrator + `--setup-only` table creation + console report |

## Engine A — scoring

Claude returns the seven component scores; Python sums them and applies the band,
so the arithmetic is never the model's problem.

| Criterion | Max |
| --- | --- |
| Role fit | 25 |
| Consulting fit | 20 |
| Geography fit | 15 |
| Seniority fit | 10 |
| Company fit | 10 |
| Commercial attractiveness | 10 |
| Win probability | 10 |

85+ PURSUE IMMEDIATELY · 70–84 STRONG · 55–69 MAYBE · 40–54 WEAK · <40 IGNORE

Tuning lives in `config.py`: `SEARCH_QUERIES` (what gets searched),
`CANDIDATE_PROFILE` (drives the scores more than anything else — edit this
first), `SCORING_CRITERIA` (weights + descriptions — the JSON schema and
system prompt are both generated from this list), `MODEL` / `EFFORT`
(currently `claude-sonnet-5` at `medium`), `SAVE_ONLY_ABOVE`.

## Engine B — how it works, and its real limitations

**Sourcing.** The brief called for scraping five news sites directly
(inc42.com, yourstory.com, entrackr.com, techinasia.com, wamda.com). Engine B
instead searches those five domains via the Tavily Search API — the same
mechanism Engine A already uses — rather than a hand-written HTML parser per
site. Several of these publishers rate-limit or block non-browser traffic
(especially from a shared GitHub Actions IP range), and a per-site scraper
breaks the moment any of the five redesigns its page; a search API absorbs
both problems. If literal HTML scraping of these exact sites is still wanted,
that's a different, larger, and more fragile implementation.

**Career-page HR-lead detection is a plain HTTP GET — no headless browser, no
JavaScript execution.** A growing share of career pages are single-page apps
or embed a Greenhouse/Lever/Ashby widget that renders client-side; a plain GET
sees an empty shell on those. `company_analyzer.py` reports that case as
**undetermined**, distinct from a confirmed **not_found** — only a confirmed
`not_found` earns the +40 "no HR lead" score. Airtable's `has_hr_lead`
checkbox collapses both non-`found` cases to `False` (matching the brief's
literal boolean), but `hr_signals` always says which one actually happened —
check that column before treating a `False` as a confirmed gap.

**Scoring is a fixed point formula, not a Claude judgment call** — see
`config.score_company()`. Claude's job is extraction (company name, sector,
stage, geography, employee count if stated) and extracting the `score_reason`
narrative; the point totals are deterministic Python arithmetic, so they can
never disagree with their own inputs the way an LLM-computed total
occasionally can.

| Criterion | Points |
| --- | --- |
| No HR lead confirmed | 40 |
| Employees 1–10 / 10–50 / 51–100 | 15 / 25 / 10 |
| Funding stage: seed or pre-series A | 20 |
| Funding stage: pre-seed or series A *(not in the original spec — see config.py)* | 12 |
| Geography: India | 15 |
| Geography: Singapore / Indonesia / UAE / Saudi Arabia | 10 |

Only companies scoring **above 50** are saved. Deduplication is by company
website domain (`company_search.domain_of()`), not by article URL or career
page URL — the same company covered by two different publishers is still one
row.

## Costs per run

**Engine A:** ~10–12 Tavily queries at advanced depth (2 credits each), plus
one Claude call per unique new result (a consistency-check retry adds a
second call for that one record). Deduplication against Airtable means repeat
runs only pay for genuinely new hits.

**Engine B:** ~5 Tavily queries per run for the funding-news search, plus one
Claude extraction call per lead, plus one extra Tavily call per lead whose
article didn't link its own website (domain resolution), plus 1–4 plain HTTP
requests per lead for the careers-page check (free, but real network calls to
third-party sites — keep `SCORING_WORKERS` modest so this doesn't hammer
anyone's server).

Both engines print an **API USAGE** block at the end of every run with the
real token counts from that run and the cost at list price — not an estimate.
