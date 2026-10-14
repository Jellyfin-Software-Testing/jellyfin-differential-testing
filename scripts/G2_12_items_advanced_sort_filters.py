#!/usr/bin/env python3
"""Run G2-12 /Items advanced sorting and pagination differential verification.

Verifies sorting and pagination independently on Jellyfin v10.8.13 and v10.9.0,
then compares the results using stable semantic keys.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.G1_06_setup_and_verify import JellyfinClient, Server, SetupError


def semantic_keys(items: list[dict[str, Any]], server_label: str) -> list[tuple[str, str]]:
    """Validate item fields and extract semantic (Name, Type) keys."""
    keys: list[tuple[str, str]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise SetupError(f"{server_label}: item at index {idx} is not an object")
        for field in ("Name", "Type", "SortName"):
            if not item.get(field):
                raise SetupError(f"{server_label}: item at index {idx} missing required field {field!r}")
        keys.append((item["Name"], item["Type"]))
    return keys


def verify_server_results(
    server_label: str,
    order: str,
    baseline: dict[str, Any],
    pages: dict[int, dict[str, Any]],
    limit: int,
) -> list[tuple[str, str]]:
    """Verify sorting and pagination invariants for a single server and return semantic keys."""
    if not isinstance(baseline, dict):
        raise SetupError(f"{server_label}: baseline is not an object")
    if baseline.get("StartIndex") != 0:
        raise SetupError(f"{server_label}: baseline StartIndex must be 0, got {baseline.get('StartIndex')}")

    baseline_items = baseline.get("Items")
    if not isinstance(baseline_items, list):
        raise SetupError(f"{server_label}: baseline missing Items list")

    total_records = baseline.get("TotalRecordCount")
    if total_records is None or len(baseline_items) != total_records:
        raise SetupError(
            f"{server_label}: baseline length ({len(baseline_items)}) != TotalRecordCount ({total_records})"
        )

    # Validate items and get semantic keys
    baseline_keys = semantic_keys(baseline_items, server_label)

    # Check order by SortName
    sort_names = [item["SortName"] for item in baseline_items]
    if order == "Ascending":
        expected_sort_names = sorted(sort_names)
    elif order == "Descending":
        expected_sort_names = sorted(sort_names, reverse=True)
    else:
        raise SetupError(f"Unknown sort order: {order}")

    if sort_names != expected_sort_names:
        raise SetupError(f"{server_label}: baseline items are not in {order} order by SortName")

    # Validate each page
    for offset, page in pages.items():
        if not isinstance(page, dict):
            raise SetupError(f"{server_label}: page at offset {offset} is not an object")
        if page.get("StartIndex") != offset:
            raise SetupError(
                f"{server_label}: page at offset {offset} returned StartIndex {page.get('StartIndex')}"
            )
        if page.get("TotalRecordCount") != total_records:
            raise SetupError(
                f"{server_label}: page TotalRecordCount mismatch: expected {total_records}, got {page.get('TotalRecordCount')}"
            )

        page_items = page.get("Items")
        if not isinstance(page_items, list):
            raise SetupError(f"{server_label}: page at offset {offset} missing Items list")
        if len(page_items) > limit:
            raise SetupError(
                f"{server_label}: page at offset {offset} length {len(page_items)} exceeds limit {limit}"
            )

        # Compare page items with baseline slice
        expected_slice = baseline_items[offset : offset + limit]
        page_keys = semantic_keys(page_items, server_label)
        expected_keys = baseline_keys[offset : offset + limit]
        if page_keys != expected_keys:
            raise SetupError(
                f"{server_label}: page at offset {offset} slice mismatch with baseline: got {page_keys}, expected {expected_keys}"
            )

    return baseline_keys


def assert_version_parity(
    v108: dict[str, list[tuple[str, str]]],
    v109: dict[str, list[tuple[str, str]]],
) -> None:
    """Compare sorted semantic key sequences between v10.8.13 and v10.9.0."""
    for order in ("Ascending", "Descending"):
        keys_108 = v108.get(order)
        keys_109 = v109.get(order)
        if keys_108 != keys_109:
            raise SetupError(
                f"Cross-version parity mismatch for {order} order:\n"
                f"v10.8.13: {keys_108}\n"
                f"v10.9.0:  {keys_109}"
            )
