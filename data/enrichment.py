"""Stage 5: enrich Stage 3 attractions from explicitly curated, official sources.

NO network requests or LLM calls. Amap results are never stored or cached here.
Only supported, manually checked facts are added. The input dict is never mutated.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from providers.config import RESOURCE_ROOT
from typing import Any
from urllib.parse import urlsplit

CURATED_PATH = RESOURCE_ROOT / "official_attractions_curated.json"
ENRICHABLE = {"address_zh", "opening_hours", "ticket_price_cny", "coordinates"}


def _date_iso(value: str) -> date:
    return date.fromisoformat(value)


def load_curated(path: Path = CURATED_PATH) -> list[dict[str, Any]]:
    """Validate local facts with per-field sources; no I/O beyond local JSON."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Curated file must contain an array")
    keys_seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Curated rows must be objects")
        key = (row["name_zh"], row["city_zh"])
        if key in keys_seen:
            raise ValueError(f"Duplicate curated attraction {key}")
        keys_seen.add(key)
        facts = row.get("verified_fields", {})
        if not facts or not isinstance(facts, dict) or not set(facts) <= ENRICHABLE:
            raise ValueError("Unrecognized or empty verified_fields")
        for name, value in facts.items():
            if value is None:
                raise ValueError(f"Verified field {name} may not be null")
            if name == "ticket_price_cny" and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            ):
                raise ValueError("ticket_price_cny must be a nonnegative number")
        sources = row.get("sources") or []
        if not sources:
            raise ValueError("Every curated fact requires a cited source")
        covered = set()
        for source in sources:
            url = urlsplit(source.get("url", ""))
            if url.scheme != "https" or not url.netloc:
                raise ValueError("Only source URLs using HTTPS are allowed")
            _date_iso(source["checked_at"])
            supported = set(source["supports"])
            if supported - facts.keys():
                raise ValueError("Source claims an absent field")
            covered |= supported
        if covered != set(facts):
            raise ValueError(f"All facts require sources; missing {set(facts)-covered}")
        for last_valid in row.get("field_valid_through", {}).values():
            _date_iso(last_valid)
    return rows


def enrich_places(
    places: list[dict[str, Any]],
    *,
    travel_date: str | None = None,
    curated: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach independently sourced facts, without making network calls.

    Match only same city plus exact Chinese place name. For provider records,
    do not replace an existing field value or persist the result to disk.
    """
    when = _date_iso(travel_date) if travel_date else None
    rows = curated if curated is not None else load_curated()
    index = {(x["city_zh"], x["name_zh"]): x for x in rows}
    result = []
    fields_filled = 0
    enriched_count = 0

    for original in places:
        item = deepcopy(original)
        key = (item.get("city_zh"), item.get("name_zh"))
        entry = index.get(key)
        item.setdefault("verified_detail_sources", [])
        item.setdefault("field_provenance", {})
        item.setdefault("field_notes", {})
        item.setdefault("needs_recheck", [])
        if entry:
            added = False
            for field, value in entry["verified_fields"].items():
                # Never overwrite existing Amap-provided or earlier verified fields.
                if item.get(field) is not None:
                    continue
                valid_through = entry.get("field_valid_through", {}).get(field)
                if valid_through and when and when > _date_iso(valid_through):
                    item["needs_recheck"].append(field)
                    continue  # avoid presenting expired hours as applicable
                sources = [s for s in entry["sources"] if field in s["supports"]]
                item[field] = deepcopy(value)
                item["field_provenance"][field] = [
                    {"provider": s["provider"], "publisher": s["publisher"],
                     "url": s["url"], "checked_at": s["checked_at"],
                     "valid_through": valid_through}
                    for s in sources
                ]
                if field in entry.get("field_notes", {}):
                    item["field_notes"][field] = entry["field_notes"][field]
                for source in sources:
                    brief = {"provider": source["provider"], "publisher": source["publisher"],
                             "url": source["url"], "checked_at": source["checked_at"]}
                    if brief not in item["verified_detail_sources"]:
                        item["verified_detail_sources"].append(brief)
                fields_filled += 1
                added = True
            if added:
                enriched_count += 1
                item["verification_status"] = "some_fields_verified_from_official_sources"
                # For demo records, show the official primary source in the
                # familiar `source` field while retaining dataset provenance.
                # For live Amap records, preserve the provider's source as-is.
                discovery = item.get("source")
                if isinstance(discovery, dict) and discovery.get("provider") == "manually_authored_demo":
                    item["discovery_source"] = discovery
                    first = item["verified_detail_sources"][0]
                    item["source"] = {
                        "provider": first["provider"],
                        "url": first["url"],
                        "retrieved_at": first["checked_at"],
                        "source_role": "verified_details_primary",
                    }
        item["missing_fields"] = [
            f for f in ("address_zh", "coordinates", "opening_hours", "ticket_price_cny")
            if item.get(f) is None
        ]
        result.append(item)
    return result, {
        "records_enriched": enriched_count,
        "fields_added_from_curated_sources": fields_filled,
        "network_calls_attempted_by_enrichment": 0,
        "llm_tokens_used_by_enrichment": 0,
        "notes": [
            "Official-source facts are manually checked snapshots, not real-time availability.",
            "Opening hours and prices may change; check the official link before booking.",
            "Unknown fields remain null; Amap data is never persisted by this module.",
        ],
    }
