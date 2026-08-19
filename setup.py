"""Project Scout - one-time Airtable setup.

Creates every column Project Scout writes to, using the Airtable Meta API.

    python setup.py             create any missing columns
    python setup.py --dry-run   show what would be created, change nothing
    python setup.py --check     verify the table is ready, create nothing

Safe to re-run: existing columns are left alone, never recreated or retyped.

Requires an Airtable personal access token with these scopes:
    schema.bases:read   read the current columns
    schema.bases:write  create the missing ones
    data.records:read   (needed later, by scout.py)
    data.records:write  (needed later, by scout.py)
"""

from __future__ import annotations

import argparse
import sys

from pyairtable import Api

import config

RULE = "=" * config.CONSOLE_WIDTH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Project Scout's Airtable columns")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without creating anything",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether the table is ready, create nothing",
    )
    return parser.parse_args()


def desired_columns() -> list[tuple[str, str, str, dict | None, str]]:
    """(internal_key, column_name, airtable_type, options, description) per column."""
    columns = []
    for key, column_name in config.AIRTABLE_FIELDS.items():
        spec = config.AIRTABLE_FIELD_TYPES.get(key)
        if spec is None:
            # A column was added to AIRTABLE_FIELDS without a matching type.
            print(f"  ! no field type configured for '{key}' - skipping")
            continue
        field_type, options = spec
        description = config.AIRTABLE_FIELD_DESCRIPTIONS.get(key, "")
        columns.append((key, column_name, field_type, options, description))
    return columns


def main() -> int:
    args = parse_args()

    print(f"\n{RULE}\nPROJECT SCOUT - AIRTABLE SETUP\n{RULE}")

    missing_creds = [
        name
        for name in ("AIRTABLE_TOKEN", "AIRTABLE_BASE_ID", "AIRTABLE_TABLE_ID")
        if name in config.missing_credentials()
    ]
    if missing_creds:
        print("\nMissing or placeholder values in .env:")
        for name in missing_creds:
            print(f"  - {name}")
        print("\nFill them in and run again.")
        return 1

    print(f"\n  Base:  {config.AIRTABLE_BASE_ID}")
    print(f"  Table: {config.AIRTABLE_TABLE_ID}")

    # -- connect and read the current schema -------------------------------
    try:
        api = Api(config.AIRTABLE_TOKEN)
        table = api.table(config.AIRTABLE_BASE_ID, config.AIRTABLE_TABLE_ID)
        schema = table.schema()
    except Exception as exc:
        print(f"\nCould not read the table schema: {type(exc).__name__}: {exc}")
        print("\nUsual causes:")
        print("  - the token is missing the schema.bases:read scope")
        print("  - the token has no access to this base")
        print("  - the base or table ID is wrong")
        return 1

    if not hasattr(table, "create_field"):
        print("\nThis pyairtable version cannot create fields.")
        print("Upgrade with:  pip install --upgrade 'pyairtable>=3.0.0'")
        return 1

    existing = {field.name: field for field in schema.fields}
    print(f"\n  Table name: {schema.name}")
    print(f"  Existing columns: {len(existing)}")

    # -- work out what is missing -----------------------------------------
    wanted = desired_columns()
    to_create = [c for c in wanted if c[1] not in existing]
    already_there = [c for c in wanted if c[1] in existing]

    # Flag type mismatches but never change them - retyping a populated
    # column is destructive, so that stays a human decision.
    mismatches = []
    for _, column_name, field_type, _, _ in already_there:
        actual = getattr(existing[column_name], "type", None)
        if actual and actual != field_type:
            mismatches.append((column_name, actual, field_type))

    print(f"  Already present:  {len(already_there)}")
    print(f"  To create:        {len(to_create)}")

    if mismatches:
        print("\n  Type mismatches (left as they are - change by hand if needed):")
        for column_name, actual, expected in mismatches:
            print(f"    {column_name}: is '{actual}', expected '{expected}'")

    if args.check:
        ready = not to_create
        print(f"\n{'Table is ready.' if ready else 'Table is NOT ready - run setup.py.'}")
        if to_create:
            for _, column_name, field_type, _, _ in to_create:
                print(f"  missing: {column_name} ({field_type})")
        return 0 if ready else 1

    if not to_create:
        print("\nNothing to do - every column already exists.")
        return 0

    if args.dry_run:
        print("\n  --dry-run, would create:")
        for _, column_name, field_type, _, _ in to_create:
            print(f"    + {column_name} ({field_type})")
        print("\nNothing was changed.")
        return 0

    # -- create ------------------------------------------------------------
    print("\nCreating columns:")
    created = 0
    failures: list[tuple[str, str]] = []

    for _, column_name, field_type, options, description in to_create:
        try:
            kwargs: dict = {}
            if options:
                kwargs["options"] = options
            if description:
                kwargs["description"] = description
            table.create_field(column_name, field_type, **kwargs)
            created += 1
            print(f"  + {column_name} ({field_type})")
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            failures.append((column_name, message))
            print(f"  ! {column_name} - {message}")

    print(f"\n{RULE}")
    print(f"Created {created} of {len(to_create)} columns.")

    if failures:
        print(f"\n{len(failures)} failed. If these are permission errors, the token")
        print("needs the schema.bases:write scope - regenerate it at")
        print("https://airtable.com/create/tokens and update AIRTABLE_TOKEN.")
        return 1

    # A fresh Airtable table ships with a primary column (usually 'Name') that
    # cannot be deleted via the API and that Project Scout never writes to.
    primary = schema.fields[0].name if schema.fields else ""
    if primary and primary not in config.AIRTABLE_FIELDS.values():
        print(f"\nNote: the primary column '{primary}' is unused by Project Scout.")
        print("Airtable will not let the API delete or retype a primary column.")
        print(f"Either ignore it, or rename it by hand to '{config.AIRTABLE_FIELDS['title']}'")
        print("and delete the duplicate column this script just created.")

    print("\nTable is ready. Next:  python scout.py --dry-run --limit 5")
    print(f"{RULE}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
