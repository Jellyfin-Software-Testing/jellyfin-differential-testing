#!/usr/bin/env python3
"""Prepare the isolated, metadata-populated G2-14 movie library."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
FILTER_LIBRARY_NAME = "Differential Seed Filters"
FILTER_LIBRARY_PATH = "/media/seed-filter-movies"
FILTER_LIBRARY_OPTIONS = {
    "EnablePhotos": False,
    "EnableRealtimeMonitor": False,
    "EnableChapterImageExtraction": False,
}
FILTER_LIBRARY = {
    "name": FILTER_LIBRARY_NAME,
    "collectionType": "movies",
    "paths": [FILTER_LIBRARY_PATH],
    "options": FILTER_LIBRARY_OPTIONS,
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.G1_06_setup_and_verify import JellyfinClient, Server, SetupError


def _validate_filter_library(library: object, client: JellyfinClient) -> dict[str, Any]:
    if not isinstance(library, dict):
        raise SetupError(f"{client.server.label}: invalid filter library response")
    if library.get("CollectionType") != "movies":
        raise SetupError(f"{client.server.label}: filter library must be movies")
    locations = library.get("Locations")
    if locations != [FILTER_LIBRARY_PATH]:
        raise SetupError(
            f"{client.server.label}: filter library has different locations: "
            f"{locations}"
        )
    item_id = library.get("ItemId")
    if not isinstance(item_id, str) or not item_id.strip():
        raise SetupError(f"{client.server.label}: filter library has invalid ItemId")
    return library


def get_or_create_filter_library(client: JellyfinClient) -> dict[str, Any]:
    """Create or validate the dedicated movie library used by G2-14."""
    manifest = {"library": FILTER_LIBRARY}
    library = client.get_or_create_library(manifest)
    return _validate_filter_library(library, client)


def wait_for_filter_seed(
    client: JellyfinClient, library_id: str, deadline: float
) -> None:
    if not client.user_id:
        raise SetupError(f"{client.server.label}: user authentication is required")
    while time.monotonic() < deadline:
        result = client.json(
            "GET",
            "/Items",
            authenticate=True,
            params={
                "ParentId": library_id,
                "UserId": client.user_id,
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("Items"), list):
            raise SetupError(f"{client.server.label}: invalid filter seed item response")
        if result["Items"]:
            return
        time.sleep(0.5)
    raise SetupError(f"{client.server.label}: timed out waiting for G2-14 movie seed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v108-url", default="http://localhost:8096")
    parser.add_argument("--v109-url", default="http://localhost:8097")
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--password", default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456")
    )
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--ready-timeout", type=float, default=180)
    args = parser.parse_args()

    try:
        clients = (
            JellyfinClient(Server("v10.8.13", args.v108_url), args.timeout),
            JellyfinClient(Server("v10.9.0", args.v109_url), args.timeout),
        )
        deadline = time.monotonic() + args.ready_timeout
        for client in clients:
            client.wait_until_healthy(deadline)
            client.authenticate(args.username, args.password)
        libraries = [get_or_create_filter_library(client) for client in clients]
        for client in clients:
            client.refresh_library()
        for client, library in zip(clients, libraries):
            wait_for_filter_seed(client, library["ItemId"], deadline)
    except (SetupError, requests.RequestException, OSError, ValueError) as exc:
        print(f"G2-14 seed setup failed: {exc}", file=sys.stderr)
        return 1

    print("G2-14 seed setup ready on both Jellyfin instances.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
