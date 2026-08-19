"""Airtable storage layer for Project Scout.

Shared by both engines: hand back the keys already stored so a runner can
skip them, and write new records in Airtable-sized batches. Engine A dedupes
by exact canonicalised URL; Engine B dedupes by company website domain -
both go through the same `existing_keys()` / `save_records()` pair with a
different `normalize` function, rather than two copies of this logic.

Column names for Engine A live in config.AIRTABLE_FIELDS, for Engine B in
config.COMPANY_AIRTABLE_FIELDS - rename them there to match your base rather
than editing this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pyairtable import Api

import config
from search import canonical_url
from scorer import ScoredOpportunity


def _identity(value: str) -> str:
    return value


@dataclass
class SaveReport:
    created: int = 0
    skipped_below_threshold: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class TableSetupResult:
    table_id: str
    created: bool  # False if the table already existed and was reused
    fields_created: list[str] = field(default_factory=list)
    fields_failed: list[tuple[str, str]] = field(default_factory=list)


class AirtableStore:
    def __init__(
        self,
        token: str | None = None,
        base_id: str | None = None,
        table_id: str | None = None,
    ) -> None:
        self.token = token or config.AIRTABLE_TOKEN
        self.base_id = base_id or config.AIRTABLE_BASE_ID
        table_id = table_id or config.AIRTABLE_TABLE_ID

        if not (self.token and self.base_id and table_id):
            raise ValueError(
                "AIRTABLE_TOKEN, AIRTABLE_BASE_ID and a table ID must all be "
                "set. Check your .env file."
            )

        self.api = Api(self.token)
        self.table = self.api.table(self.base_id, table_id)

    # -- reads -------------------------------------------------------------

    def existing_keys(
        self, field_name: str, normalize: Callable[[str], str] = _identity
    ) -> set[str]:
        """Every value already in `field_name`, passed through `normalize`.

        Raises on failure. Silently returning an empty set here would
        duplicate the whole table on the next run, so the caller must
        decide what to do.
        """
        keys: set[str] = set()
        for record in self.table.all(fields=[field_name]):
            value = record.get("fields", {}).get(field_name)
            if value:
                keys.add(normalize(str(value)))
        return keys

    def existing_urls(self) -> set[str]:
        """Engine A convenience wrapper: existing_keys() canonicalised as URLs."""
        return self.existing_keys(config.AIRTABLE_URL_FIELD, normalize=canonical_url)

    # -- writes ------------------------------------------------------------

    def save_records(self, records: list[dict], verbose: bool = True) -> SaveReport:
        """Write pre-mapped Airtable field dicts in batches. No filtering -
        callers decide what qualifies for saving before calling this."""
        report = SaveReport()
        if not records:
            return report

        size = config.AIRTABLE_BATCH_SIZE
        for start in range(0, len(records), size):
            batch = records[start : start + size]
            try:
                # typecast lets Airtable coerce strings into single-select and
                # date columns instead of rejecting the whole batch.
                created = self.table.batch_create(batch, typecast=True)
                report.created += len(created)
                if verbose:
                    print(f"  saved {report.created}/{len(records)}")
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                report.errors.append(message)
                if verbose:
                    print(f"  ! batch starting at {start} failed - {message}")

        return report

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
        """Engine A convenience wrapper: filter by SAVE_ONLY_ABOVE, then save_records()."""
        to_write = []
        skipped = 0
        for opportunity in opportunities:
            if opportunity.total_score < config.SAVE_ONLY_ABOVE:
                skipped += 1
                continue
            to_write.append(self._to_fields(opportunity))

        report = self.save_records(to_write, verbose=verbose)
        report.skipped_below_threshold = skipped
        return report

    # -- schema setup --------------------------------------------------------

    @classmethod
    def ensure_table(
        cls,
        table_name: str,
        field_types: dict[str, tuple[str, dict | None]],
        field_names: dict[str, str],
        field_descriptions: dict[str, str] | None = None,
        token: str | None = None,
        base_id: str | None = None,
        verbose: bool = True,
    ) -> TableSetupResult:
        """Create `table_name` in the base if it doesn't already exist, then
        create any of its columns that are missing. Idempotent and additive -
        an existing table or column is never renamed, retyped, or dropped.
        """
        token = token or config.AIRTABLE_TOKEN
        base_id = base_id or config.AIRTABLE_BASE_ID
        if not (token and base_id):
            raise ValueError("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must both be set.")

        field_descriptions = field_descriptions or {}
        api = Api(token)
        base = api.base(base_id)
        schema = base.schema()

        existing_table = next((t for t in schema.tables if t.name == table_name), None)

        def build_field_spec(key: str) -> dict:
            column_name = field_names[key]
            field_type, options = field_types[key]
            spec = {"name": column_name, "type": field_type}
            if options:
                spec["options"] = options
            description = field_descriptions.get(key)
            if description:
                spec["description"] = description
            return spec

        if existing_table is None:
            field_specs = [build_field_spec(key) for key in field_names]
            table = base.create_table(table_name, field_specs)
            if verbose:
                print(f"  created table '{table_name}' with {len(field_specs)} columns")
            return TableSetupResult(
                table_id=table.id, created=True, fields_created=list(field_names)
            )

        # Table exists - fill in any columns it's missing, like setup.py does
        # for the Opportunities table.
        table = base.table(existing_table.id)
        current_columns = {f.name for f in existing_table.fields}
        created_fields: list[str] = []
        failed_fields: list[tuple[str, str]] = []

        for key, column_name in field_names.items():
            if column_name in current_columns:
                continue
            field_type, options = field_types[key]
            try:
                kwargs = {}
                if options:
                    kwargs["options"] = options
                description = field_descriptions.get(key)
                if description:
                    kwargs["description"] = description
                table.create_field(column_name, field_type, **kwargs)
                created_fields.append(column_name)
                if verbose:
                    print(f"  + {column_name} ({field_type})")
            except Exception as exc:
                failed_fields.append((column_name, f"{type(exc).__name__}: {exc}"))
                if verbose:
                    print(f"  ! {column_name} - {type(exc).__name__}: {exc}")

        if verbose and not created_fields and not failed_fields:
            print(f"  table '{table_name}' already has every column")

        return TableSetupResult(
            table_id=existing_table.id,
            created=False,
            fields_created=created_fields,
            fields_failed=failed_fields,
        )
