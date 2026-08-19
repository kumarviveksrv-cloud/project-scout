# Project Scout

Finds remote HR consulting opportunities for a senior India-based HR professional
(12+ years), scores each one out of 100 with Claude, and stores the results in
Airtable.

## Setup

1. **Install Python 3.10+** — it is not currently installed on this machine.
   Get it from [python.org](https://www.python.org/downloads/windows/) and tick
   *Add python.exe to PATH* during install.

2. **Install dependencies**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Fill in `.env`** — replace every placeholder with a real key.

4. **Create the Airtable columns** — automatically:

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

## Running

```bash
python scout.py                  # full run
python scout.py --dry-run        # search + score, write nothing
python scout.py --limit 5        # score only 5 hits, to sanity-check cheaply
python scout.py --json run.json  # also dump results locally
python scout.py --min-score 55   # only print MAYBE and above
```

Start with `--dry-run --limit 5`. That exercises Tavily and Claude without
touching Airtable and costs a few cents.

## Files

| File | What it does |
| --- | --- |
| `setup.py` | One-time Airtable column creation via the Meta API |
| `config.py` | Every setting: queries, rubric, thresholds, column names, model |
| `search.py` | Tavily search, URL canonicalisation, in-run deduplication |
| `scorer.py` | Claude scoring via structured outputs, retries, classification |
| `database.py` | Airtable reads (existing URLs) and batched writes |
| `scout.py` | Orchestrator + console report |

## Scoring

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

## Tuning

Everything worth changing is in `config.py`:

- `SEARCH_QUERIES` / `QUERY_SUFFIX` — what gets searched
- `CANDIDATE_PROFILE` — the profile Claude scores against; edit this first, it
  drives the scores more than anything else
- `SCORING_CRITERIA` — weights and criterion descriptions; the JSON schema and
  the system prompt are both generated from this list
- `MODEL` / `EFFORT` — `claude-opus-5` at `medium` effort. Drop to `low` for a
  cheaper, faster sweep
- `SAVE_ONLY_ABOVE` — set to e.g. `40` to stop storing obvious noise

## Costs per run

Roughly: 10 Tavily queries at advanced depth (2 credits each), plus one Claude
call per unique new result. Deduplication against Airtable means repeat runs only
pay to score genuinely new hits.
