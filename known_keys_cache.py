"""Local JSON cache for known Airtable keys (URLs, domains).

Saves and loads a dict of {cache_key: [list_of_values]} from a JSON file.
In GitHub Actions the file is persisted between runs via actions/cache —
see daily_scout.yml. Locally it accumulates in .known_keys_cache.json.

This eliminates the Airtable read calls that were hitting the free-tier
monthly API quota on every single run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

# Resolved once at import; can be overridden via env var for testing.
CACHE_PATH = Path(os.environ.get("KNOWN_KEYS_CACHE_PATH", ".known_keys_cache.json"))


def _load_raw() -> dict[str, list[str]]:
    """Read the cache file. Returns empty dict if missing or corrupt."""
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_raw(data: dict[str, list[str]]) -> None:
    CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load(cache_key: str, normalize: Callable[[str], str] | None = None) -> set[str]:
    """Return the set of known values for `cache_key`.

    `normalize` is applied to each stored value so the in-memory set matches
    whatever normalisation the caller uses (e.g. canonical_url, domain_of).
    """
    raw = _load_raw().get(cache_key, [])
    if normalize:
        return {normalize(v) for v in raw if v}
    return set(raw)


def update(cache_key: str, new_values: list[str]) -> None:
    """Merge `new_values` into the cache for `cache_key` and write to disk.

    Existing values are preserved; duplicates are silently dropped.
    """
    if not new_values:
        return
    data = _load_raw()
    existing = set(data.get(cache_key, []))
    existing.update(v for v in new_values if v)
    data[cache_key] = sorted(existing)
    _save_raw(data)


def size(cache_key: str) -> int:
    return len(_load_raw().get(cache_key, []))
