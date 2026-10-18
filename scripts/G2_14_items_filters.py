#!/usr/bin/env python3
"""G2-14 Items Filters Differential Runner.

Compares /Items/Filters Genres, Years, and OfficialRatings across Jellyfin
v10.8.13 and v10.9.0 with strict validation and coverage reporting.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence, Union

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.G1_06_setup_and_verify import JellyfinClient, Server, SetupError

DEFAULT_REPORT = ROOT / "docs" / "evidence" / "G2-14-filters-differential.json"
FILTER_LIBRARY_NAME = "Differential Seed Filters"
FILTER_FIELDS: tuple[str, ...] = ("Genres", "Years", "OfficialRatings")
# Full coverage requires the deterministic sample values specified by G2-14.
SEED_FILTER_SENTINELS: dict[str, str | int] = {
    "Genres": "Drama",
    "Years": 2020,
    "OfficialRatings": "PG-13",
}
NormalizedFilters = dict[str, tuple[str, Union[list[str], list[int], None]]]


def normalize_filter_response(
    payload: object, server_label: str
) -> NormalizedFilters:
    """Validate and normalize filters into explicit state tuples."""
    if not isinstance(payload, dict):
        raise SetupError(
            f"Expected dict response for /Items/Filters on {server_label}, "
            f"got {type(payload).__name__}"
        )

    normalized: NormalizedFilters = {}
    for field in FILTER_FIELDS:
        if field not in payload:
            normalized[field] = ("missing", None)
        elif payload[field] is None:
            normalized[field] = ("null", None)
        elif not isinstance(payload[field], list):
            raise SetupError(
                f"Expected list or null for field {field} on {server_label}, "
                f"got {type(payload[field]).__name__}"
            )
        else:
            raw_list = payload[field]
            if field in ("Genres", "OfficialRatings"):
                for item in raw_list:
                    if not isinstance(item, str):
                        raise SetupError(
                            "Expected string items in "
                            f"{field} on {server_label}, "
                            f"found {type(item).__name__}"
                        )
            elif field == "Years":
                for item in raw_list:
                    if type(item) is not int:
                        raise SetupError(
                            f"Expected int items in Years on {server_label}, "
                            f"found {type(item).__name__}"
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


def limited_coverage_fields(
    results: dict[str, NormalizedFilters]
) -> list[str]:
    """Return fields missing expected seed values on either server."""
    limited: list[str] = []
    for field in FILTER_FIELDS:
        for server_filters in results.values():
            state, values = server_filters.get(field, ("missing", None))
            if (
                state != "values"
                or not values
                or SEED_FILTER_SENTINELS[field] not in values
            ):
                limited.append(field)
                break
    return limited


def resolve_seed_library(
    client: JellyfinClient, library_name: str = FILTER_LIBRARY_NAME
) -> str:
    """Resolve the named library's ItemId from /Library/VirtualFolders."""
    if hasattr(client, "json"):
        folders = client.json(
            "GET", "/Library/VirtualFolders", authenticate=True
        )
    else:
        res = client.request(
            "GET", "/Library/VirtualFolders", authenticate=True
        )
        folders = res.json() if hasattr(res, "json") else res

    if not isinstance(folders, list):
        raise SetupError(
            f"Expected list from /Library/VirtualFolders on "
            f"{client.server.label}, got {type(folders).__name__}"
        )

    matches = [
        folder
        for folder in folders
        if isinstance(folder, dict) and folder.get("Name") == library_name
    ]
    if not matches:
        raise SetupError(
            f"Library '{library_name}' not found on {client.server.label}"
        )
    if len(matches) > 1:
        raise SetupError(
            f"Found multiple matching libraries named '{library_name}' "
            f"on {client.server.label}"
        )

    folder = matches[0]
    item_id = folder.get("ItemId")
    if not item_id or not isinstance(item_id, str) or not item_id.strip():
        raise SetupError(
            f"Invalid or missing ItemId for library '{library_name}' "
            f"on {client.server.label}"
        )
    return item_id


def run_differential_filters(
    clients: tuple[JellyfinClient, JellyfinClient] | Sequence[JellyfinClient],
    library_name: str = FILTER_LIBRARY_NAME,
) -> dict[str, Any]:
    """Compare /Items/Filters for the resolved seed library on both clients."""
    if len(clients) != 2:
        raise SetupError(
            "run_differential_filters requires exactly 2 clients, "
            f"got {len(clients)}"
        )
    if clients[0].server.label == clients[1].server.label:
        raise SetupError(
            "run_differential_filters requires clients with distinct server "
            f"labels, got duplicate '{clients[0].server.label}'"
        )

    normalized_results: dict[str, NormalizedFilters] = {}
    formatted_results: dict[str, dict[str, Any]] = {}

    for client in clients:
        label = client.server.label
        if not client.user_id:
            raise SetupError(
                f"Client {label} is not authenticated (missing user_id)"
            )
        parent_id = resolve_seed_library(client, library_name)
        params = {"UserId": client.user_id, "ParentId": parent_id}
        if hasattr(client, "json"):
            raw_filters = client.json(
                "GET", "/Items/Filters", authenticate=True, params=params
            )
        else:
            res = client.request(
                "GET", "/Items/Filters", authenticate=True, params=params
            )
            raw_filters = res.json() if hasattr(res, "json") else res

        norm = normalize_filter_response(raw_filters, label)
        normalized_results[label] = norm

        server_output: dict[str, Any] = {}
        for field in FILTER_FIELDS:
            state, vals = norm[field]
            if state == "missing":
                server_output[field] = {"state": "missing"}
            elif state == "null":
                server_output[field] = {"state": "null"}
            else:
                server_output[field] = {"state": "values", "values": vals}
        formatted_results[label] = server_output

    c1, c2 = clients[0], clients[1]
    differences = compare_filter_values(
        normalized_results[c1.server.label],
        normalized_results[c2.server.label],
    )
    limited = limited_coverage_fields(normalized_results)

    parity = "equivalent" if not differences else "different"
    coverage = "limited" if limited else "full"

    if parity == "equivalent":
        status = "equivalent" if coverage == "full" else "limited_coverage"
    else:
        status = "different"

    return {
        "task": "G2-14",
        "status": status,
        "parity": parity,
        "coverage": coverage,
        "limitedFields": limited,
        "differences": differences,
        "results": formatted_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--v108-url",
        default="http://localhost:8096",
        help="Jellyfin v10.8 URL",
    )
    parser.add_argument(
        "--v109-url",
        default="http://localhost:8097",
        help="Jellyfin v10.9 URL",
    )
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument(
        "--password",
        default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"),
        help="Admin password",
    )
    parser.add_argument(
        "--timeout", type=float, default=10, help="Request timeout in seconds"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write the evidence report",
    )
    parser.add_argument(
        "--library-name",
        default=FILTER_LIBRARY_NAME,
        help="Seed library to query (use Differential Seed Music for empty case)",
    )
    args = parser.parse_args()

    report: dict[str, Any] = {
        "task": "G2-14",
        "status": "failed",
        "parity": "not_run",
        "coverage": "not_evaluated",
    }
    exit_code = 1

    try:
        clients = (
            JellyfinClient(Server("v10.8.13", args.v108_url), args.timeout),
            JellyfinClient(Server("v10.9.0", args.v109_url), args.timeout),
        )
        for client in clients:
            client.authenticate(args.username, args.password)

        report = run_differential_filters(clients, args.library_name)
        if report["status"] == "equivalent":
            print("G2-14 success: filter parity matches with full coverage.")
            exit_code = 0
        elif report["status"] == "limited_coverage":
            print(
                "G2-14 partial: filter parity matches across versions, "
                "but coverage is limited "
                "(unpopulated fields: "
                f"{', '.join(report.get('limitedFields', []))})."
            )
            exit_code = 2
        else:
            print(
                "G2-14 mismatch: filter differences detected: "
                f"{report.get('differences')}",
                file=sys.stderr,
            )
            exit_code = 1
    except (
        SetupError,
        requests.RequestException,
        KeyError,
        ValueError,
        OSError,
    ) as exc:
        report["error"] = str(exc)
        print(f"G2-14 failed: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
