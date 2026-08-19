"""Daily email digest for Project Scout - one email summarizing the day's
run from both engines, sent via the Resend API.

    python digest.py                     send today's digest for real
    python digest.py --dry-run           compose and print the email, send nothing
    python digest.py --date 2026-08-19   use a specific date instead of today (UTC)

Reads Engine A's Opportunities table (filtered on found_at) and Engine B's
Companies table (filtered on date_added) for rows stamped with the target
date - not the whole table's history. Nothing here calls Tavily or Claude;
this is a read-then-format-then-send step, so it costs nothing beyond the
Resend send itself.

NOTE ON RESEND: there is no prior Resend configuration anywhere in this
project - RESEND_API_KEY is a placeholder in .env like every other
credential here until a real key is supplied. See config.py's comment on
this feature.
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timezone

import requests

import config
from database import AirtableStore

RULE = "=" * config.CONSOLE_WIDTH
RESEND_ENDPOINT = "https://api.resend.com/emails"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project Scout - Daily Digest")
    parser.add_argument("--dry-run", action="store_true", help="compose and print the email, send nothing")
    parser.add_argument("--date", default="", help="YYYY-MM-DD, defaults to today (UTC)")
    return parser.parse_args()


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def fetch_top_opportunities(target_date: str) -> list[dict]:
    """Engine A's PURSUE IMMEDIATELY / STRONG rows found on `target_date`,
    top N by score. Returns raw Airtable field dicts (keyed by the actual
    column names in config.AIRTABLE_FIELDS)."""
    store = AirtableStore(table_id=config.AIRTABLE_TABLE_ID)
    f = config.AIRTABLE_FIELDS
    wanted = [f["title"], f["company"], f["total_score"], f["classification"], f["url"], f["found_at"]]
    rows = []
    for record in store.all_records(fields=wanted):
        fields = record.get("fields", {})
        if not str(fields.get(f["found_at"], "")).startswith(target_date):
            continue
        if fields.get(f["classification"]) not in ("PURSUE IMMEDIATELY", "STRONG"):
            continue
        rows.append(fields)
    rows.sort(key=lambda r: r.get(f["total_score"], 0), reverse=True)
    return rows[: config.DIGEST_TOP_N_OPPORTUNITIES]


def fetch_target_companies(target_date: str) -> list[dict]:
    """Every Engine B company added on `target_date` scoring at or above
    config.DIGEST_COMPANY_MIN_SCORE, highest first."""
    store = AirtableStore(table_id=config.AIRTABLE_COMPANIES_TABLE_ID)
    f = config.COMPANY_AIRTABLE_FIELDS
    contact = config.COMPANY_CONTACT_FIELDS
    wanted = [
        f["company_name"], f["company_score"], f["employee_count"], f["funding_stage"],
        f["date_added"], contact["founder_name"], contact["founder_linkedin_url"],
    ]
    rows = []
    for record in store.all_records(fields=wanted):
        fields = record.get("fields", {})
        if not str(fields.get(f["date_added"], "")).startswith(target_date):
            continue
        if (fields.get(f["company_score"]) or 0) < config.DIGEST_COMPANY_MIN_SCORE:
            continue
        rows.append(fields)
    rows.sort(key=lambda r: r.get(f["company_score"], 0), reverse=True)
    return rows


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def build_email(
    target_date: str, opportunities: list[dict], companies: list[dict]
) -> tuple[str, str, str]:
    """Returns (subject, html_body, text_body)."""
    f_a = config.AIRTABLE_FIELDS
    f_b = config.COMPANY_AIRTABLE_FIELDS
    contact = config.COMPANY_CONTACT_FIELDS

    subject = (
        f"Scout Daily Brief - {target_date} - "
        f"{len(opportunities)} opportunities, {len(companies)} companies"
    )

    text = [f"SCOUT DAILY BRIEF - {target_date}", ""]
    htm = [f"<h2>Scout Daily Brief - {_esc(target_date)}</h2>"]

    text += ["ENGINE A: TOP OPPORTUNITIES", "-" * 40]
    htm.append("<h3>Engine A: Top Opportunities</h3>")
    if not opportunities:
        text.append("(none today)")
        htm.append("<p>(none today)</p>")
    else:
        htm.append(
            "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse'>"
            "<tr><th>Title</th><th>Company</th><th>Score</th>"
            "<th>Classification</th><th>URL</th></tr>"
        )
        for o in opportunities:
            title = o.get(f_a["title"], "")
            company = o.get(f_a["company"], "")
            score = o.get(f_a["total_score"], "")
            classification = o.get(f_a["classification"], "")
            url = o.get(f_a["url"], "")
            text.append(f"{title} | {company} | {score} | {classification} | {url}")
            link = f"<a href='{_esc(url)}'>{_esc(url)}</a>" if url else ""
            htm.append(
                f"<tr><td>{_esc(title)}</td><td>{_esc(company)}</td><td>{_esc(score)}</td>"
                f"<td>{_esc(classification)}</td><td>{link}</td></tr>"
            )
        htm.append("</table>")

    text += ["", "ENGINE B: TARGET COMPANIES", "-" * 40]
    htm.append("<h3>Engine B: Target Companies</h3>")
    if not companies:
        text.append("(none today)")
        htm.append("<p>(none today)</p>")
    else:
        htm.append(
            "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse'>"
            "<tr><th>Company</th><th>Score</th><th>Employees</th><th>Funding Stage</th>"
            "<th>Founder</th><th>LinkedIn URL</th></tr>"
        )
        for c in companies:
            name = c.get(f_b["company_name"], "")
            score = c.get(f_b["company_score"], "")
            employees = c.get(f_b["employee_count"], None)
            employees_text = employees if employees is not None else "unstated"
            stage = c.get(f_b["funding_stage"], "")
            founder = c.get(contact["founder_name"], "") or "(not found)"
            founder_url = c.get(contact["founder_linkedin_url"], "")
            text.append(f"{name} | {score} | {employees_text} | {stage} | {founder} | {founder_url}")
            link = f"<a href='{_esc(founder_url)}'>{_esc(founder_url)}</a>" if founder_url else ""
            htm.append(
                f"<tr><td>{_esc(name)}</td><td>{_esc(score)}</td><td>{_esc(employees_text)}</td>"
                f"<td>{_esc(stage)}</td><td>{_esc(founder)}</td><td>{link}</td></tr>"
            )
        htm.append("</table>")

    return subject, "\n".join(htm), "\n".join(text)


def send_email(subject: str, html_body: str, text_body: str) -> None:
    if config.is_placeholder(config.RESEND_API_KEY):
        raise ValueError(
            "RESEND_API_KEY is not set. Check your .env file - see config.py's "
            "comment on this feature for why there's no default here."
        )
    response = requests.post(
        RESEND_ENDPOINT,
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": config.RESEND_FROM_EMAIL,
            "to": [config.DIGEST_TO_EMAIL],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        },
        timeout=20,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"Resend API error {response.status_code}: {response.text[:300]}")


def main() -> int:
    args = parse_args()
    target_date = args.date or today_utc()
    print(f"\n{RULE}\nDAILY DIGEST - {target_date}\n{RULE}")

    missing = [m for m in config.missing_credentials() if m in ("AIRTABLE_TOKEN", "AIRTABLE_BASE_ID")]
    if missing:
        print("\nMissing or placeholder credentials in .env:")
        for name in missing:
            print(f"  - {name}")
        return 1
    if config.is_placeholder(config.AIRTABLE_TABLE_ID) or config.is_placeholder(
        config.AIRTABLE_COMPANIES_TABLE_ID
    ):
        print("\nAIRTABLE_TABLE_ID and AIRTABLE_COMPANIES_TABLE_ID must both be set.")
        return 1

    try:
        opportunities = fetch_top_opportunities(target_date)
        companies = fetch_target_companies(target_date)
    except Exception as exc:
        print(f"\nCould not read Airtable: {type(exc).__name__}: {exc}")
        return 1

    subject, html_body, text_body = build_email(target_date, opportunities, companies)

    print(f"\nSubject: {subject}\n")
    print(text_body)

    if args.dry_run:
        print("\n--dry-run: email not sent")
        print(f"\n{RULE}\n")
        return 0

    try:
        send_email(subject, html_body, text_body)
    except Exception as exc:
        print(f"\nCould not send email: {type(exc).__name__}: {exc}")
        return 1

    print(f"\nSent to {config.DIGEST_TO_EMAIL}")
    print(f"\n{RULE}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
