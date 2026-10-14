#!/usr/bin/env python3
"""G2-14 Items Filters Differential Runner.

Compares /Items/Filters Genres, Years, and OfficialRatings across Jellyfin
v10.8.13 and v10.9.0 with strict validation and coverage reporting.
"""

from __future__ import annotations

from typing import Any, Union

from scripts.G1_06_setup_and_verify import SetupError

FILTER_FIELDS: tuple[str, ...] = ("Genres", "Years", "OfficialRatings")
NormalizedFilters = dict[str, tuple[str, Union[list[str], list[int], None]]]


def normalize_filter_response(payload: object, server_label: str) -> NormalizedFilters:
    """Validate and normalize /Items/Filters payload into explicit state tuples."""
    if not isinstance(payload, dict):
        raise SetupError(
            f"Expected dict response for /Items/Filters on {server_label}, got {type(payload).__name__}"
        )

    normalized: NormalizedFilters = {}
    for field in FILTER_FIELDS:
        if field not in payload:
            normalized[field] = ("missing", None)
        elif payload[field] is None:
            normalized[field] = ("null", None)
        elif not isinstance(payload[field], list):
            raise SetupError(
                f"Expected list or null for field {field} on {server_label}, got {type(payload[field]).__name__}"
            )
        else:
            raw_list = payload[field]
            if field in ("Genres", "OfficialRatings"):
                for item in raw_list:
                    if not isinstance(item, str):
                        raise SetupError(
                            f"Expected string items in {field} on {server_label}, found {type(item).__name__}"
                        )
            elif field == "Years":
                for item in raw_list:
                    if type(item) is not int:
                        raise SetupError(
                            f"Expected int items in Years on {server_label}, found {type(item).__name__}"
                        )
            normalized[field] = ("values", sorted(raw_list))

    return normalized


def compare_filter_values(
    v108: NormalizedFilters, v109: NormalizedFilters
) -> list[str]:
    """Return field names with mismatches in state or values."""
    differences: list[str] = []
    for field in FILTER_FIELDS:
        if v108.get(field) != v109.get(field):
            differences.append(field)
    return differences


def limited_coverage_fields(results: dict[str, NormalizedFilters]) -> list[str]:
    """Return fields that lack non-empty values on one or both servers."""
    limited: list[str] = []
    for field in FILTER_FIELDS:
        for server_label, server_filters in results.items():
            state, values = server_filters.get(field, ("missing", None))
            if state != "values" or not values:
                limited.append(field)
                break
    return limited
