"""Airtable storage layer for Project Scout.

Two jobs: hand back the URLs already stored so scout.py can skip them, and
write the newly scored opportunities.

Column names live in config.AIRTABLE_FIELDS - rename them there to match your
base rather than editing this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyairtable import Api

import config
from search import canonical_url
from scorer import ScoredOpportunity


@dataclass
class SaveReport:
    created: int = 0
    skipped_below_threshold: int = 0
    errors: list[str] = field(default_factory=list)


class AirtableStore:
    def __init__(
        self,
        token: str | None = None,
        base_id: str | None = None,
        table_id: str | None = None,
    ) -> None:
        token = token or config.AIRTABLE_TOKEN
        base_id = base_id or config.AIRTABLE_BASE_ID
        table_id = table_id or config.AIRTABLE_TABLE_ID

        if not (token and base_id and table_id):
            raise ValueError(
                "AIRTABLE_TOKEN, AIRTABLE_BASE_ID and AIRTABLE_TABLE_ID must all "
                "be set. Check your .env file."
            )

        self.api = Api(token)
        self.table = self.api.table(base_id, table_id)

    # -- reads -------------------------------------------------------------

    def existing_urls(self) -> set[str]:
        """Every URL already in the table, canonicalised for comparison.

        Raises on failure. Silently returning an empty set here would duplicate
        the whole table on the next run, so the caller must decide what to do.
        """
        urls: set[str] = set()
        for record in self.table.all(fields=[config.AIRTABLE_URL_FIELD]):
            value = record.get("fields", {}).get(config.AIRTABLE_URL_FIELD)
            if value:
                urls.add(canonical_url(str(value)))
        return urls

    # -- writes ------------------------------------------------------------

    @staticmethod
    def _to_fields(opportunity: ScoredOpportunity) -> dict:
        f = config.AIRTABLE_FIELDS
        row = {
            f["title"]: opportunity.title,
            f["url"]: opportunity.url,
            f["company"]: opportunity.company,
            f["role_title"]: opportunity.role_title,
            f["engagement_type"]: opportunity.engagement_type,
            f["source_query"]: opportunity.source_query,
            f["summary"]: opportunity.summary,
            f["total_score"]: opportunity.total_score,
            f["classification"]: opportunity.classification,
            f["estimated_value"]: opportunity.estimated_value,
            f["key_reasons"]: "\n".join(f"- {r}" for r in opportunity.key_reasons),
            f["red_flags"]: "\n".join(f"- {r}" for r in opportunity.red_flags),
            f["recommended_action"]: opportunity.recommended_action,
            f["found_at"]: opportunity.found_at,
        }
        for name, value in opportunity.scores.items():
            column = f.get(name)
            if column:
                row[column] = value
        return {k: v for k, v in row.items() if v not in ("", None)}

    def save_all(
        self, opportunities: list[ScoredOpportunity], verbose: bool = True
    ) -> SaveReport:
        """Write scored opportunities in Airtable-sized batches."""
        report = SaveReport()

        to_write = []
        for opportunity in opportunities:
            if opportunity.total_score < config.SAVE_ONLY_ABOVE:
                report.skipped_below_threshold += 1
                continue
            to_write.append(self._to_fields(opportunity))

        if not to_write:
            return report

        size = config.AIRTABLE_BATCH_SIZE
        for start in range(0, len(to_write), size):
            batch = to_write[start : start + size]
            try:
                # typecast lets Airtable coerce strings into single-select and
                # date columns instead of rejecting the whole batch.
                created = self.table.batch_create(batch, typecast=True)
                report.created += len(created)
                if verbose:
                    print(f"  saved {report.created}/{len(to_write)}")
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                report.errors.append(message)
                if verbose:
                    print(f"  ! batch starting at {start} failed - {message}")

        return report
