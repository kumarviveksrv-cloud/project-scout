"""Engine C (Career Signal) - orchestrator.

    python wellfound_runner.py                 full run: search, score, save
    python wellfound_runner.py --dry-run        search and score, write nothing
    python wellfound_runner.py --limit 20       process only the first 20 leads
    python wellfound_runner.py --setup-only     create/verify the JobLeads table, then exit
    python wellfound_runner.py --json out.json  also dump results locally

What this engine does and why it is different from Engine B:

Engine B finds newly funded companies and checks whether they already have an
HR leader. Its best signal is a company with NO HR posting - a gap waiting to
be filled.

Engine C searches for companies actively posting HR leadership roles right now.
A startup actively recruiting a Head of People is:
  - Aware they need HR help (they've diagnosed the gap)
  - Not yet served (the search is open)
  - In a buying frame of mind (budget exists, problem is visible)

This makes them the warmest possible outbound target: they've already decided
to spend money on people work. The pitch writes itself - "while you search for
a permanent hire, here's how a fractional engagement gets you the urgent HR
infrastructure sorted."

Pipeline per lead: Tavily general search on job boards / Wellfound ->
Claude extracts role title, company, stage, geography, remote-eligibility ->
hard filters (is HR role, remote-eligible, employee cap) -> resolve company
domain -> dedupe by domain against Airtable (Engine B Companies table) and
in-run seen set -> fixed-formula score -> keep if > WELLFOUND_SAVE_ONLY_ABOVE
-> save to Airtable JobLeads table.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import config
from company_search import CompanyFundingSearcher, domain_of
from database import AirtableStore, SaveReport
from wellfound_scorer import (
    JobExtractor,
    JobLead,
    JobScoringReport,
    assemble_lead,
    passes_filters,
)
from wellfound_search import HRJobSearcher

RULE = "=" * config.CONSOLE_WIDTH
THIN = "-" * config.CONSOLE_WIDTH


def header(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project Scout - Engine C (Career Signal)")
    parser.add_argument("--dry-run", action="store_true", help="search and score but write nothing")
    parser.add_argument("--limit", type=int, default=0, help="process at most N leads (0 = no limit)")
    parser.add_argument("--json", metavar="PATH", default="", help="also write results to a local JSON file")
    parser.add_argument("--min-score", type=int, default=0, help="only print leads at or above this score")
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="create/verify the JobLeads table and its columns, then exit",
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


def print_lead(rank: int, lead: JobLead) -> None:
    below = "" if lead.job_score > config.WELLFOUND_SAVE_ONLY_ABOVE else "  (below save threshold)"
    print(f"\n{rank}. [{lead.job_score}/{config.WELLFOUND_MAX_SCORE}] {lead.company_name}{below}")
    print(f"   Role:        {lead.role_title or 'Unknown'}")
    print(f"   Sector:      {lead.sector or 'Unknown'}")
    print(f"   Stage:       {lead.funding_stage or 'unstated'}")
    print(f"   Geography:   {lead.geography or 'unstated'}")
    print(f"   Employees:   {lead.employee_count if lead.employee_count is not None else 'unstated'}")
    print(f"   Remote:      {'yes' if lead.is_remote_eligible else 'no'}")
    print(f"   Source:      {lead.source_domain} - {lead.lead_url}")
    print(f"   Score:       {lead.score_reason}")


def run_pipeline(
    leads: list,
    dry_run: bool,
    existing_domains: set[str],
    verbose: bool = True,
) -> JobScoringReport:
    report = JobScoringReport()
    if not leads:
        return report

    extractor = JobExtractor()
    searcher = CompanyFundingSearcher()  # reused for domain resolution only
    seen_domains: set[str] = set()

    def process(indexed):
        index, lead = indexed
        result = extractor.extract(lead)
        if result.payload is None:
            return "refused", lead, None

        payload = result.payload
        usages = [result.usage]

        ok, reason = passes_filters(payload)
        if not ok:
            return "filtered", lead, reason

        # Resolve domain - reuse Engine B's CompanyFundingSearcher.resolve_company_domain
        domain = domain_of(payload.get("company_website", "") or "")
        if not domain:
            domain = searcher.resolve_company_domain(payload.get("company_name", ""))
        # An unresolved domain keeps the lead - it's dedupe'd on company name
        # as a fallback, but the lead itself is too valuable to drop silently.

        job_lead = assemble_lead(lead, payload, usages)
        job_lead.company_domain = domain
        return "candidate", lead, job_lead

    workers = max(1, min(config.SCORING_WORKERS, len(leads)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, (outcome, lead, extra) in enumerate(
            pool.map(process, enumerate(leads)), start=1
        ):
            if outcome == "refused":
                report.refusals.append(lead.url)
                if verbose:
                    print(f"  [{done}/{len(leads)}] - declined: {lead.url}")
            elif outcome == "filtered":
                report.dropped_out_of_criteria += 1
                if verbose:
                    print(f"  [{done}/{len(leads)}] - filtered: {extra}")
            else:
                job_lead: JobLead = extra
                domain = job_lead.company_domain

                # Dedupe by domain: skip if already in this run or in Airtable
                if domain and (
                    domain in seen_domains or (not dry_run and domain in existing_domains)
                ):
                    report.dropped_out_of_criteria += 1
                    if verbose:
                        print(f"  [{done}/{len(leads)}] - duplicate domain: {domain}")
                    continue
                if domain:
                    seen_domains.add(domain)

                report.scored.append(job_lead)
                if verbose:
                    below = "" if job_lead.job_score > config.WELLFOUND_SAVE_ONLY_ABOVE else " (below save threshold)"
                    print(
                        f"  [{done}/{len(leads)}] {job_lead.job_score:>3}/{config.WELLFOUND_MAX_SCORE}  "
                        f"{job_lead.company_name} | {job_lead.role_title}{below}"
                    )

    report.scored.sort(key=lambda j: j.job_score, reverse=True)
    report.usage = extractor.usage
    return report


def main() -> int:
    args = parse_args()
    header("ENGINE C - CAREER SIGNAL")

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
        header("SETTING UP THE JOB LEADS TABLE")
        print()
        result = AirtableStore.ensure_table(
            config.WELLFOUND_AIRTABLE_TABLE_NAME,
            config.WELLFOUND_AIRTABLE_FIELD_TYPES,
            config.WELLFOUND_AIRTABLE_FIELDS,
            config.WELLFOUND_AIRTABLE_FIELD_DESCRIPTIONS,
        )
        print(f"\n  Table ID: {result.table_id}")
        if result.created:
            print("  Created new. Put this in .env as AIRTABLE_JOBLEADS_TABLE_ID=" + result.table_id)
        if result.fields_failed:
            print(f"  {len(result.fields_failed)} column(s) failed to create - see errors above.")
            return 1
        print(f"\n{RULE}\n")
        return 0

    header(f"SEARCHING  ({len(config.WELLFOUND_SEARCH_QUERIES)} queries, "
           f"{len(config.WELLFOUND_SOURCE_DOMAINS)} sources)")
    try:
        searcher = HRJobSearcher()
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
        print("\nNothing to score. Try widening config.WELLFOUND_SEARCH_QUERIES.")
        return 0

    # Pull existing company domains from BOTH Companies table (Engine B) and
    # JobLeads table (Engine C) for cross-engine deduplication. A company
    # Engine B already found doesn't need to also appear here - the Contact
    # Finder will already be targeting them.
    store: AirtableStore | None = None
    existing_domains: set[str] = set()
    table_id = config.AIRTABLE_JOBLEADS_TABLE_ID

    if not args.dry_run:
        header("PREPARING AIRTABLE")
        print()
        try:
            if not table_id:
                print("\n  No AIRTABLE_JOBLEADS_TABLE_ID set - creating/finding the table now.")
                result = AirtableStore.ensure_table(
                    config.WELLFOUND_AIRTABLE_TABLE_NAME,
                    config.WELLFOUND_AIRTABLE_FIELD_TYPES,
                    config.WELLFOUND_AIRTABLE_FIELDS,
                    config.WELLFOUND_AIRTABLE_FIELD_DESCRIPTIONS,
                )
                table_id = result.table_id
                print(f"  Table ID: {table_id} - add this to .env as AIRTABLE_JOBLEADS_TABLE_ID")
            store = AirtableStore(table_id=table_id)
            existing_domains = store.existing_keys(
                config.WELLFOUND_AIRTABLE_FIELDS["company_domain"],
                normalize=domain_of,
            )
            # Also pull in Engine B's known companies to avoid showing the same
            # company twice across engines.
            if config.AIRTABLE_COMPANIES_TABLE_ID:
                try:
                    engine_b_store = AirtableStore(table_id=config.AIRTABLE_COMPANIES_TABLE_ID)
                    engine_b_domains = engine_b_store.existing_keys(
                        config.COMPANY_AIRTABLE_FIELDS["career_page_url"],
                        normalize=domain_of,
                    )
                    cross_overlap = len(existing_domains & engine_b_domains)
                    existing_domains |= engine_b_domains
                    print(f"  {len(existing_domains)} known domains ({cross_overlap} shared with Engine B)")
                except Exception as exc:
                    print(f"  Could not load Engine B domains for cross-dedup: {exc}")
                    print(f"  {len(existing_domains)} domains from JobLeads table only")
            else:
                print(f"  {len(existing_domains)} domains from JobLeads table")
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

    print(f"\n  {scoring_report.dropped_out_of_criteria} dropped: filters or duplicate domain")
    if scoring_report.failures:
        print(f"  {len(scoring_report.failures)} failed to extract")
    if scoring_report.refusals:
        print(f"  {len(scoring_report.refusals)} declined by the model")

    save_worthy = [j for j in scored if j.job_score > config.WELLFOUND_SAVE_ONLY_ABOVE]

    save_report: SaveReport | None = None
    if save_worthy and store is not None:
        header("SAVING TO AIRTABLE")
        print()
        records = [
            {
                config.WELLFOUND_AIRTABLE_FIELDS["company_name"]: j.company_name,
                config.WELLFOUND_AIRTABLE_FIELDS["role_title"]: j.role_title,
                config.WELLFOUND_AIRTABLE_FIELDS["sector"]: j.sector,
                config.WELLFOUND_AIRTABLE_FIELDS["funding_stage"]: j.funding_stage,
                config.WELLFOUND_AIRTABLE_FIELDS["employee_count"]: j.employee_count,
                config.WELLFOUND_AIRTABLE_FIELDS["geography"]: j.geography,
                config.WELLFOUND_AIRTABLE_FIELDS["company_domain"]: j.company_domain,
                config.WELLFOUND_AIRTABLE_FIELDS["is_remote_eligible"]: j.is_remote_eligible,
                config.WELLFOUND_AIRTABLE_FIELDS["job_score"]: j.job_score,
                config.WELLFOUND_AIRTABLE_FIELDS["score_reason"]: j.score_reason,
                config.WELLFOUND_AIRTABLE_FIELDS["source_domain"]: j.source_domain,
                config.WELLFOUND_AIRTABLE_FIELDS["lead_url"]: j.lead_url,
                config.WELLFOUND_AIRTABLE_FIELDS["status"]: "new",
                config.WELLFOUND_AIRTABLE_FIELDS["date_added"]: j.date_added,
            }
            for j in save_worthy
        ]
        records = [{k: v for k, v in r.items() if v not in ("", None)} for r in records]
        save_report = store.save_records(records)
        if save_report.errors:
            print("\n  Some records failed to save. Check that every column in")
            print("  config.WELLFOUND_AIRTABLE_FIELDS exists in the JobLeads table with that exact name.")
    elif args.dry_run:
        print("\n  --dry-run: nothing written to Airtable")

    if args.json and (scored or scoring_report.usage.calls):
        try:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "usage": scoring_report.usage.to_dict(),
                        "leads": [j.to_dict() for j in scored],
                    },
                    fh,
                    indent=2,
                )
            print(f"\n  Wrote {len(scored)} leads + usage totals to {args.json}")
        except OSError as exc:
            print(f"\n  Could not write {args.json}: {exc}")

    header("RESULTS")
    if not scored:
        print("\nNo leads survived extraction and filtering this run.")
    else:
        shown = [j for j in scored if j.job_score >= args.min_score][: config.TOP_N_TO_PRINT]
        for rank, lead in enumerate(shown, start=1):
            print_lead(rank, lead)
        print(f"\n{THIN}")
        print(f"  Leads processed:      {len(leads)}")
        print(f"  Leads scored:         {len(scored)}")
        print(f"  Above save threshold: {len(save_worthy)} (>{config.WELLFOUND_SAVE_ONLY_ABOVE}/{config.WELLFOUND_MAX_SCORE})")
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
