"""Engine B (Company Intelligence) - orchestrator.

    python company_runner.py                 full run: search, score, save
    python company_runner.py --dry-run        search and score, write nothing
    python company_runner.py --limit 10       process only the first 10 leads
    python company_runner.py --setup-only     create/verify the Companies table, then exit
    python company_runner.py --json out.json  also dump results locally

Pipeline per lead: Tavily funding-news search -> Claude extracts structured
facts -> hard filters (stage/geography/employee cap) -> resolve company
domain -> dedupe by domain (in-run, then against Airtable) -> check the
careers page for an HR/People title -> fixed-formula score -> keep if > 50
-> save.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import company_analyzer
import config
from company_scorer import (
    CompanyExtractor,
    CompanyLead,
    CompanyScoringReport,
    assemble_lead,
    passes_filters,
)
from company_search import CompanyFundingSearcher, domain_of
from database import AirtableStore, SaveReport

RULE = "=" * config.CONSOLE_WIDTH
THIN = "-" * config.CONSOLE_WIDTH


def header(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project Scout - Engine B (Company Intelligence)")
    parser.add_argument("--dry-run", action="store_true", help="search and score but write nothing")
    parser.add_argument("--limit", type=int, default=0, help="process at most N leads (0 = no limit)")
    parser.add_argument("--json", metavar="PATH", default="", help="also write results to a local JSON file")
    parser.add_argument("--min-score", type=int, default=0, help="only print companies at or above this score")
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="create/verify the Companies table and its columns, then exit",
    )
    return parser.parse_args()


def print_usage(usage) -> None:
    print(f"\n{THIN}")
    print("API USAGE")
    print(f"  Model:            {config.MODEL}")
    print(f"  API calls:        {usage.calls}")
    print(f"  Input tokens:     {usage.input_tokens:,}")
    print(f"  Output tokens:    {usage.output_tokens:,}")
    print(f"  Estimated cost:   ${usage.cost_usd:.4f} USD (list price, {config.MODEL})")


def print_company(rank: int, lead: CompanyLead) -> None:
    below = "" if lead.company_score > config.COMPANY_SAVE_ONLY_ABOVE else "  (below save threshold)"
    print(f"\n{rank}. [{lead.company_score}/{config.COMPANY_MAX_SCORE}] {lead.company_name}{below}")
    print(f"   Sector:      {lead.sector or 'Unknown'}")
    print(f"   Stage:       {lead.funding_stage or 'unstated'}  ({lead.funding_amount})")
    print(f"   Geography:   {lead.geography or 'unstated'}")
    print(f"   Employees:   {lead.employee_count if lead.employee_count is not None else 'unstated'}")
    print(f"   HR lead:     {'yes' if lead.has_hr_lead else 'no / undetermined'} - {lead.hr_signals}")
    if lead.career_page_url:
        print(f"   Careers:     {lead.career_page_url}")
    print(f"   Source:      {lead.funding_source} - {lead.lead_url}")
    print(f"   Score:       {lead.score_reason}")


def run_pipeline(
    leads: list,
    dry_run: bool,
    existing_domains: set[str],
    verbose: bool = True,
) -> CompanyScoringReport:
    report = CompanyScoringReport()
    if not leads:
        return report

    extractor = CompanyExtractor()
    searcher = CompanyFundingSearcher()
    seen_domains: set[str] = set()

    def process(indexed):
        index, lead = indexed
        result = extractor.extract(lead)
        if result.payload is None:
            return "refused", lead, None

        payload = result.payload
        usages = [result.usage]

        if not payload.get("is_real_lead"):
            return "not_real", lead, None

        ok, reason = passes_filters(payload)
        if not ok:
            return "out_of_criteria", lead, reason

        domain = domain_of(payload.get("company_website", "") or "")
        if not domain:
            domain = searcher.resolve_company_domain(payload.get("company_name", ""))
        # An unresolved domain no longer drops the lead - it's kept with a
        # blank career_page_url and no HR-lead bonus (company_analyzer.
        # check_company("") already returns exactly that "undetermined"
        # shape). Dropping these outright was hiding otherwise-promising
        # leads whose website just doesn't match their name closely enough
        # for resolve_company_domain's precision-over-recall matching.
        career = company_analyzer.check_company(domain)

        # LinkedIn employee-count fallback - only for a lead that's already
        # promising on everything else, and only when the article left the
        # headcount unstated. Cheap gate check (pure Python) before the
        # conditionally-spent extra Tavily call.
        employee_count_source = ""
        if payload.get("employee_count") is None:
            _, partial_breakdown = config.score_company(
                hr_lead_points=career.hr_lead_points,
                employee_count=None,
                funding_stage=payload.get("funding_stage", ""),
                geography=payload.get("geography", ""),
            )
            other_criteria = (
                partial_breakdown["hr_lead"]
                + partial_breakdown["funding_stage"]
                + partial_breakdown["geography"]
            )
            if other_criteria > config.COMPANY_LINKEDIN_FALLBACK_THRESHOLD:
                found = searcher.find_employee_count_via_linkedin(payload.get("company_name", ""))
                if found is not None:
                    payload["employee_count"] = found
                    employee_count_source = "LinkedIn lookup"

        company_lead = assemble_lead(lead, payload, career, usages, employee_count_source)
        company_lead.company_domain = domain
        return "candidate", lead, company_lead

    workers = max(1, min(config.SCORING_WORKERS, len(leads)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, (outcome, lead, extra) in enumerate(
            pool.map(process, enumerate(leads)), start=1
        ):
            if outcome == "refused":
                report.refusals.append(lead.url)
                if verbose:
                    print(f"  [{done}/{len(leads)}] - declined: {lead.url}")
            elif outcome == "not_real":
                report.dropped_not_real += 1
                if verbose:
                    print(f"  [{done}/{len(leads)}] - not a single-company lead: {lead.title[:50]}")
            elif outcome == "out_of_criteria":
                report.dropped_out_of_criteria += 1
                if verbose:
                    print(f"  [{done}/{len(leads)}] - filtered: {extra}")
            else:
                company_lead: CompanyLead = extra
                domain = company_lead.company_domain
                # Domain-based dedup only applies when there IS a domain -
                # an empty string must never be treated as a dedup key, or
                # every unresolved-domain lead after the first in a batch
                # would look like a duplicate of it and get silently dropped.
                if domain and (
                    domain in seen_domains or (not dry_run and domain in existing_domains)
                ):
                    report.dropped_out_of_criteria += 1
                    if verbose:
                        print(f"  [{done}/{len(leads)}] - duplicate domain: {domain}")
                    continue
                if domain:
                    seen_domains.add(domain)
                # Every fully-processed lead is kept and shown, regardless of
                # score - the >50 save threshold is applied later, only at
                # the Airtable-write step. A --limit N diagnostic run exists
                # specifically to show what was found; discarding anything
                # here would defeat that.
                report.scored.append(company_lead)
                if verbose:
                    below = "" if company_lead.company_score > config.COMPANY_SAVE_ONLY_ABOVE else " (below save threshold)"
                    print(
                        f"  [{done}/{len(leads)}] {company_lead.company_score:>3}/100  "
                        f"{company_lead.company_name}{below}"
                    )

    report.scored.sort(key=lambda c: c.company_score, reverse=True)
    report.usage = extractor.usage
    return report


def main() -> int:
    args = parse_args()
    header("ENGINE B - COMPANY INTELLIGENCE")

    required = ["ANTHROPIC_API_KEY", "TAVILY_API_KEY"]
    if not args.dry_run or args.setup_only:
        required += ["AIRTABLE_TOKEN", "AIRTABLE_BASE_ID"]
    missing = [m for m in config.missing_credentials() if m in required]
    if missing:
        print("\nMissing or placeholder credentials in .env:")
        for name in missing:
            print(f"  - {name}")
        print("\nFill them in and run again.")
        return 1

    if args.setup_only:
        header("SETTING UP THE COMPANIES TABLE")
        print()
        result = AirtableStore.ensure_table(
            config.COMPANY_AIRTABLE_TABLE_NAME,
            config.COMPANY_AIRTABLE_FIELD_TYPES,
            config.COMPANY_AIRTABLE_FIELDS,
            config.COMPANY_AIRTABLE_FIELD_DESCRIPTIONS,
        )
        print(f"\n  Table ID: {result.table_id}")
        if result.created:
            print("  Created new. Put this in .env as AIRTABLE_COMPANIES_TABLE_ID=" + result.table_id)
        if result.fields_failed:
            print(f"  {len(result.fields_failed)} column(s) failed to create - see errors above.")
            return 1
        print(f"\n{RULE}\n")
        return 0

    header(f"SEARCHING  ({len(config.COMPANY_SEARCH_QUERIES)} queries, "
           f"{len(config.COMPANY_SOURCE_DOMAINS)} sources)")
    try:
        searcher = CompanyFundingSearcher()
    except Exception as exc:
        print(f"\nCould not start Tavily: {exc}")
        return 1

    search_report = searcher.run()
    leads = search_report.leads
    print(f"\n  {search_report.raw_results} raw results across {search_report.queries_run} queries")
    print(f"  {search_report.dropped_duplicate} duplicates, {search_report.dropped_thin} too thin")
    print(f"  {len(leads)} unique leads")
    if search_report.errors:
        print(f"  {len(search_report.errors)} queries failed")

    if not leads:
        print("\nNothing to score. Try widening config.COMPANY_SEARCH_QUERIES or COMPANY_TAVILY_DAYS.")
        return 0

    store: AirtableStore | None = None
    existing_domains: set[str] = set()
    table_id = config.AIRTABLE_COMPANIES_TABLE_ID
    if not args.dry_run:
        header("PREPARING AIRTABLE")
        try:
            if not table_id:
                print("\n  No AIRTABLE_COMPANIES_TABLE_ID set - creating/finding the table now.")
                result = AirtableStore.ensure_table(
                    config.COMPANY_AIRTABLE_TABLE_NAME,
                    config.COMPANY_AIRTABLE_FIELD_TYPES,
                    config.COMPANY_AIRTABLE_FIELDS,
                    config.COMPANY_AIRTABLE_FIELD_DESCRIPTIONS,
                )
                table_id = result.table_id
                print(f"  Table ID: {table_id} - add this to .env as AIRTABLE_COMPANIES_TABLE_ID")
            store = AirtableStore(table_id=table_id)
            existing_domains = store.existing_keys(
                config.COMPANY_AIRTABLE_DEDUPE_FIELD, normalize=domain_of
            )
            print(f"\n  {len(existing_domains)} company domains already stored")
        except Exception as exc:
            print(f"\nCould not prepare Airtable: {type(exc).__name__}: {exc}")
            print("Refusing to continue - scoring now would create duplicates.")
            print("Fix the connection, or re-run with --dry-run to score only.")
            return 1

    if args.limit > 0:
        leads = leads[: args.limit]
        print(f"\n  --limit: processing only the first {len(leads)}")

    header(f"EXTRACTING + SCORING  ({len(leads)} leads, model {config.MODEL})")
    print()
    scoring_report = run_pipeline(leads, args.dry_run, existing_domains)
    scored = scoring_report.scored

    print(f"\n  {scoring_report.dropped_not_real} dropped: not a single-company funding lead")
    print(f"  {scoring_report.dropped_out_of_criteria} dropped: filters or duplicate domain")
    if scoring_report.failures:
        print(f"  {len(scoring_report.failures)} failed to extract")
    if scoring_report.refusals:
        print(f"  {len(scoring_report.refusals)} declined by the model")

    # The >50 save threshold applies here, at write time - not earlier, so
    # console/JSON output always shows everything that was actually processed.
    save_worthy = [c for c in scored if c.company_score > config.COMPANY_SAVE_ONLY_ABOVE]

    save_report: SaveReport | None = None
    if save_worthy and store is not None:
        header("SAVING TO AIRTABLE")
        print()
        records = [
            {
                config.COMPANY_AIRTABLE_FIELDS["company_name"]: c.company_name,
                config.COMPANY_AIRTABLE_FIELDS["sector"]: c.sector,
                config.COMPANY_AIRTABLE_FIELDS["funding_stage"]: c.funding_stage,
                config.COMPANY_AIRTABLE_FIELDS["funding_amount"]: c.funding_amount,
                config.COMPANY_AIRTABLE_FIELDS["employee_count"]: c.employee_count,
                config.COMPANY_AIRTABLE_FIELDS["geography"]: c.geography,
                config.COMPANY_AIRTABLE_FIELDS["career_page_url"]: c.career_page_url,
                config.COMPANY_AIRTABLE_FIELDS["has_hr_lead"]: c.has_hr_lead,
                config.COMPANY_AIRTABLE_FIELDS["hr_signals"]: c.hr_signals,
                config.COMPANY_AIRTABLE_FIELDS["company_score"]: c.company_score,
                config.COMPANY_AIRTABLE_FIELDS["score_reason"]: c.score_reason,
                config.COMPANY_AIRTABLE_FIELDS["funding_source"]: c.funding_source,
                config.COMPANY_AIRTABLE_FIELDS["date_funded"]: c.date_funded,
                config.COMPANY_AIRTABLE_FIELDS["status"]: "new",
                config.COMPANY_AIRTABLE_FIELDS["date_added"]: c.date_added,
            }
            for c in save_worthy
        ]
        records = [{k: v for k, v in r.items() if v not in ("", None)} for r in records]
        save_report = store.save_records(records)
        if save_report.errors:
            print("\n  Some records failed to save. Check that every column in")
            print("  config.COMPANY_AIRTABLE_FIELDS exists in the Companies table with that exact name.")
    elif args.dry_run:
        print("\n  --dry-run: nothing written to Airtable")

    if args.json and (scored or scoring_report.usage.calls):
        try:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "usage": scoring_report.usage.to_dict(),
                        "companies": [c.to_dict() for c in scored],
                    },
                    fh,
                    indent=2,
                )
            print(f"\n  Wrote {len(scored)} companies + usage totals to {args.json}")
        except OSError as exc:
            print(f"\n  Could not write {args.json}: {exc}")

    header("RESULTS")
    if not scored:
        print("\nNo leads survived extraction and filtering this run.")
    else:
        shown = [c for c in scored if c.company_score >= args.min_score][: config.TOP_N_TO_PRINT]
        for rank, lead in enumerate(shown, start=1):
            print_company(rank, lead)
        print(f"\n{THIN}")
        print(f"  Leads processed:      {len(leads)}")
        print(f"  Companies analyzed:   {len(scored)}")
        print(f"  Above save threshold: {len(save_worthy)} (>{config.COMPANY_SAVE_ONLY_ABOVE}/{config.COMPANY_MAX_SCORE})")
        if save_report is not None:
            print(f"  Saved to Airtable:    {save_report.created}")
            if save_report.errors:
                print(f"  Airtable errors:      {len(save_report.errors)}")

    print_usage(scoring_report.usage)
    print(f"\n{RULE}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
