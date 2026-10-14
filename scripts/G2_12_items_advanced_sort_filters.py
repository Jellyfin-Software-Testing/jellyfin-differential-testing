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
    if len(baseline_items) < 2:
        raise SetupError(
            f"{server_label}: expected at least 2 items in baseline for sorting and pagination, got {len(baseline_items)}"
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
        if order not in v108 or order not in v109:
            raise SetupError(f"Missing sort order {order!r} in parity results")
        keys_108 = v108[order]
        keys_109 = v109[order]
        if keys_108 != keys_109:
            raise SetupError(
                f"Cross-version parity mismatch for {order} order:\n"
                f"v10.8.13: {keys_108}\n"
                f"v10.9.0:  {keys_109}"
            )


def locate_seed_library(client: JellyfinClient, library_name: str = "Differential Seed Music") -> str:
    """Locate the seed music library by name and return its ItemId."""
    libraries = client.json("GET", "/Library/VirtualFolders", authenticate=True)
    if not isinstance(libraries, list):
        raise SetupError(f"{client.server.label}: invalid /Library/VirtualFolders response")
    matches = [lib for lib in libraries if isinstance(lib, dict) and lib.get("Name") == library_name]
    if len(matches) != 1 or not matches[0].get("ItemId"):
        raise SetupError(f"{client.server.label}: seed library {library_name!r} not found or missing ItemId")
    return matches[0]["ItemId"]


def run_differential_sorting(
    clients: list[JellyfinClient],
    library_name: str = "Differential Seed Music",
    page_limit: int = 1,
    page_offsets: tuple[int, ...] = (0, 1),
) -> dict[str, Any]:
    """Execute sorting and pagination differential verification across servers."""
    if len(clients) < 2:
        raise SetupError("Differential verification requires at least two servers")
    results_per_server: dict[str, dict[str, list[tuple[str, str]]]] = {}

    for client in clients:
        label = client.server.label
        if not client.user_id:
            raise SetupError(f"{label}: client has no authenticated user_id")
        parent_id = locate_seed_library(client, library_name)
        server_results: dict[str, list[tuple[str, str]]] = {}

        for order in ("Ascending", "Descending"):
            base_params: dict[str, Any] = {
                "UserId": client.user_id,
                "ParentId": parent_id,
                "Recursive": "true",
                "IncludeItemTypes": "Audio",
                "SortBy": "SortName",
                "SortOrder": order,
                "Fields": "SortName",
            }

            # Unpaginated sorted baseline: StartIndex=0, Limit omitted
            baseline = client.json(
                "GET",
                "/Items",
                authenticate=True,
                params={**base_params, "StartIndex": 0},
            )

            # Paginated queries: Limit=page_limit, StartIndex=offset
            pages: dict[int, dict[str, Any]] = {}
            for offset in page_offsets:
                pages[offset] = client.json(
                    "GET",
                    "/Items",
                    authenticate=True,
                    params={**base_params, "Limit": page_limit, "StartIndex": offset},
                )

            server_results[order] = verify_server_results(label, order, baseline, pages, page_limit)

        results_per_server[label] = server_results

    if len(clients) >= 2:
        assert_version_parity(results_per_server[clients[0].server.label], results_per_server[clients[1].server.label])

    return {
        "task": "G2-12",
        "status": "equivalent",
        "results": {
            label: {order: [{"Name": n, "Type": t} for n, t in keys] for order, keys in res.items()}
            for label, res in results_per_server.items()
        },
    }


def main() -> int:
    import argparse
    import json
    import os
    import requests

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v108-url", default="http://localhost:8096", help="Jellyfin v10.8 URL")
    parser.add_argument("--v109-url", default="http://localhost:8097", help="Jellyfin v10.9 URL")
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument(
        "--password",
        default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"),
        help="Admin password",
    )
    parser.add_argument("--timeout", type=float, default=10, help="Request timeout in seconds")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "evidence" / "G2-12-sorting-differential.json")
    args = parser.parse_args()

    report: dict[str, Any] = {"task": "G2-12", "status": "failed"}
    try:
        clients = [
            JellyfinClient(Server("v10.8.13", args.v108_url), args.timeout),
            JellyfinClient(Server("v10.9.0", args.v109_url), args.timeout),
        ]
        for client in clients:
            client.authenticate(args.username, args.password)

        report = run_differential_sorting(clients)
        print("G2-12 success: sorting and pagination invariants match across versions.")
        return 0
    except (SetupError, requests.RequestException, KeyError, OSError) as exc:
        report["error"] = str(exc)
        print(f"G2-12 failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
