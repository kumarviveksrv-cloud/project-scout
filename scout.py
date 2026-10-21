"""Project Scout - find and rank remote HR consulting opportunities.

    python scout.py                 full run: search, score, save to Airtable
    python scout.py --dry-run       search and score, but write nothing
    python scout.py --limit 5       score only the first 5 hits (cheap test)
    python scout.py --json out.json also dump the scored results locally

Pipeline: Tavily search -> drop URLs already in Airtable -> Claude scores each
one -> save to Airtable -> print the top opportunities.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

import config
from database import AirtableStore, SaveReport
from scorer import OpportunityScorer, ScoredOpportunity
from search import BraveSearcher

RULE = "=" * config.CONSOLE_WIDTH
THIN = "-" * config.CONSOLE_WIDTH


def header(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project Scout")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="search and score but do not write to Airtable",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="score at most N opportunities (0 = no limit)",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        default="",
        help="also write the scored results to a local JSON file",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="only print opportunities at or above this total",
    )
    return parser.parse_args()


def print_opportunity(rank: int, opportunity: ScoredOpportunity) -> None:
    capped = f" (capped from {opportunity.raw_score})" if opportunity.gate_note else ""
    print(f"\n{rank}. [{opportunity.total_score}/{config.MAX_SCORE}] "
          f"{opportunity.classification}{capped}")
    print(f"   {opportunity.role_title or opportunity.title}")
    print(f"   Company:  {opportunity.company}")
    print(f"   Type:     {opportunity.engagement_type}")
    print(f"   Value:    {opportunity.estimated_value}")
    print(f"   URL:      {opportunity.url}")

    breakdown = "  ".join(
        f"{name.split('_')[0][:4]}={opportunity.scores.get(name, 0)}/{points}"
        for name, points, _ in config.SCORING_CRITERIA
    )
    print(f"   Scores:   {breakdown}")

    if opportunity.summary:
        print(f"   {opportunity.summary}")
    for reason in opportunity.key_reasons[:3]:
        print(f"     + {reason}")
    for flag in opportunity.red_flags[:2]:
        print(f"     - {flag}")
    if opportunity.recommended_action:
        print(f"   Next:     {opportunity.recommended_action}")


def print_usage(usage) -> None:
    """Real token usage and cost-at-list-price for this run, from the API's
    own response.usage - not an estimate reconstructed after the fact."""
    print(f"\n{THIN}")
    print("API USAGE")
    print(f"  Model:            {config.MODEL}")
    print(f"  API calls:        {usage.calls}")
    print(f"  Input tokens:     {usage.input_tokens:,}")
    print(f"  Output tokens:    {usage.output_tokens:,}")
    if usage.cache_creation_input_tokens or usage.cache_read_input_tokens:
        print(f"  Cache write:      {usage.cache_creation_input_tokens:,}")
        print(f"  Cache read:       {usage.cache_read_input_tokens:,}")
    print(f"  Estimated cost:   ${usage.cost_usd:.4f} USD (list price, {config.MODEL})")


def print_summary(
    scored: list[ScoredOpportunity],
    save_report: SaveReport | None,
    min_score: int,
    usage=None,
) -> None:
    header("TOP OPPORTUNITIES")

    if not scored:
        print("\nNothing scored this run.")
        if usage is not None and usage.calls:
            print_usage(usage)
        return

    shown = [s for s in scored if s.total_score >= min_score][: config.TOP_N_TO_PRINT]
    if not shown:
        print(f"\nNothing scored at or above {min_score}.")
    for rank, opportunity in enumerate(shown, start=1):
        print_opportunity(rank, opportunity)

    print(f"\n{THIN}")
    print("BREAKDOWN")
    counts = Counter(s.classification for s in scored)
    for _, label in config.CLASSIFICATIONS:
        print(f"  {label:<20} {counts.get(label, 0):>4}")

    gated = [s for s in scored if s.gate_note]
    pursue = counts.get("PURSUE IMMEDIATELY", 0) + counts.get("STRONG", 0)
    print(f"\n  Scored this run:     {len(scored)}")
    print(f"  Worth acting on:     {pursue}")
    if gated:
        print(f"  Capped by gates:     {len(gated)} (zero win probability)")
    if scored:
        best = scored[0]
        print(f"  Highest score:       {best.total_score}/{config.MAX_SCORE} - {best.company}")
    if save_report is not None:
        print(f"  Saved to Airtable:   {save_report.created}")
        if save_report.errors:
            print(f"  Airtable errors:     {len(save_report.errors)}")

    if usage is not None:
        print_usage(usage)


def main() -> int:
    args = parse_args()

    header("PROJECT SCOUT")

    missing = config.missing_credentials()
    # In a dry run we never touch Airtable, so those three can stay unset.
    if args.dry_run:
        missing = [m for m in missing if not m.startswith("AIRTABLE")]
    if missing:
        print("\nMissing or placeholder credentials in .env:")
        for name in missing:
            print(f"  - {name}")
        print("\nFill them in and run again.")
        return 1

    # -- 1. search ---------------------------------------------------------
    header(f"SEARCHING  ({len(config.SEARCH_QUERIES)} queries)")
    try:
        searcher = BraveSearcher()
    except Exception as exc:
        print(f"\nCould not start Tavily: {exc}")
        return 1

    search_report = searcher.run()
    found = search_report.opportunities
    print(f"\n  {search_report.raw_results} raw results across "
          f"{search_report.queries_run} queries")
    print(f"  {search_report.dropped_duplicate} duplicates, "
          f"{search_report.dropped_blocked} blocked domains, "
          f"{search_report.dropped_aggregator} aggregator pages, "
          f"{search_report.dropped_thin} too thin")
    prefiltered = search_report.dropped_blocked + search_report.dropped_aggregator
    if prefiltered:
        print(f"  {prefiltered} filtered before scoring (saved {prefiltered} Claude calls)")
    print(f"  {len(found)} unique candidates")
    if search_report.errors:
        print(f"  {len(search_report.errors)} queries failed")

    if not found:
        print("\nNothing to score. Try widening config.SEARCH_QUERIES.")
        return 0

    # -- 2. dedupe against Airtable ---------------------------------------
    store: AirtableStore | None = None
    if not args.dry_run:
        header("DEDUPLICATING")
        try:
            store = AirtableStore()
            known = store.existing_urls()
        except Exception as exc:
            print(f"\nCould not read Airtable: {type(exc).__name__}: {exc}")
            print("Refusing to continue - scoring now would create duplicates.")
            print("Fix the connection, or re-run with --dry-run to score only.")
            return 1

        before = len(found)
        found = [o for o in found if o.url not in known]
        print(f"\n  {len(known)} URLs already stored")
        print(f"  {before - len(found)} already seen, {len(found)} new")

        if not found:
            print("\nNo new opportunities since the last run.")
            return 0

    if args.limit > 0:
        found = found[: args.limit]
        print(f"\n  --limit: scoring only the first {len(found)}")

    # -- 3. score ----------------------------------------------------------
    header(f"SCORING  ({len(found)} opportunities, model {config.MODEL})")
    try:
        scorer = OpportunityScorer()
    except Exception as exc:
        print(f"\nCould not start the Claude client: {exc}")
        return 1

    print()
    scoring_report = scorer.score_all(found)
    scored = scoring_report.scored

    if scoring_report.failures:
        print(f"\n  {len(scoring_report.failures)} failed to score")
    if scoring_report.refusals:
        print(f"  {len(scoring_report.refusals)} declined by the model")

    # -- 4. save -----------------------------------------------------------
    save_report: SaveReport | None = None
    if scored and store is not None:
        header("SAVING TO AIRTABLE")
        print()
        save_report = store.save_all(scored)
        if save_report.errors:
            print("\n  Some records failed to save. Check that every column in")
            print("  config.AIRTABLE_FIELDS exists in your table with that exact name.")
    elif args.dry_run:
        print("\n  --dry-run: nothing written to Airtable")

    if args.json and (scored or scoring_report.usage.calls):
        try:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "usage": scoring_report.usage.to_dict(),
                        "opportunities": [s.to_dict() for s in scored],
                    },
                    fh,
                    indent=2,
                )
            print(f"\n  Wrote {len(scored)} records + usage totals to {args.json}")
        except OSError as exc:
            print(f"\n  Could not write {args.json}: {exc}")

    # -- 5. report ---------------------------------------------------------
    print_summary(scored, save_report, args.min_score, scoring_report.usage)
    print(f"\n{RULE}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
