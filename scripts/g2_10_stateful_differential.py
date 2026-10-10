#!/usr/bin/env python3
"""Run G2-10 favorite-state sequences against Jellyfin 10.8 and 10.9.

The runner only changes favorite state for its two named test users and the
existing G1-06 admin. It never deletes users, media, libraries, or config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

from models.user_data_model import FavoriteAction, FavoriteState, UserDataTestModel
from scripts.g1_06_setup_and_verify import JellyfinClient, ROOT, Server, SetupError


DEFAULT_REPORT = ROOT / "docs" / "evidence" / "G2-10-stateful-differential.json"
DEFAULT_G1_REPORT = ROOT / "docs" / "evidence" / "G1-06-initial-state-parity.json"
DEFAULT_ITEM_NAME = "01 - Reference Tone"


def favorite_request(
    client: JellyfinClient, action: FavoriteAction, user_id: str, item_id: str
) -> dict[str, Any]:
    """Send a version-specific favorite request and retain its observable result."""
    if client.server.label.startswith("v10.8"):
        path = f"/Users/{user_id}/FavoriteItems/{item_id}"
        params = None
    else:
        path = f"/UserFavoriteItems/{item_id}"
        params = {"userId": user_id}

    response = client.request(
        action.value, path, params=params, authenticate=True, expected=(200, 204)
    )
    body: Any = None
    if response.content:
        try:
            body = response.json()
        except ValueError:
            body = response.text
    return {"status_code": response.status_code, "body": body}


def find_or_create_user(client: JellyfinClient, name: str) -> str:
    users = client.json("GET", "/Users", authenticate=True)
    if not isinstance(users, list):
        raise SetupError(f"{client.server.label}: invalid /Users response")
    matches = [user for user in users if isinstance(user, dict) and user.get("Name") == name]
    if len(matches) > 1:
        raise SetupError(f"{client.server.label}: duplicate G2-10 user {name!r}")
    if matches:
        user_id = matches[0].get("Id")
    else:
        created = client.json(
            "POST", "/Users/New", payload={"Name": name}, authenticate=True
        )
        user_id = created.get("Id") if isinstance(created, dict) else None
    if not isinstance(user_id, str) or not user_id:
        raise SetupError(f"{client.server.label}: G2-10 user {name!r} has no id")
    return user_id


def find_seed_item(client: JellyfinClient, name: str) -> str:
    if not client.user_id:
        raise SetupError(f"{client.server.label}: no authenticated admin user")
    data = client.json(
        "GET",
        "/Items",
        authenticate=True,
        params={"UserId": client.user_id, "IncludeItemTypes": "Audio", "Recursive": "true"},
    )
    items = data.get("Items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SetupError(f"{client.server.label}: invalid /Items response")
    matches = [item for item in items if isinstance(item, dict) and item.get("Name") == name]
    if len(matches) != 1 or not isinstance(matches[0].get("Id"), str):
        raise SetupError(f"{client.server.label}: expected exactly one seed item {name!r}")
    return matches[0]["Id"]


def read_state(client: JellyfinClient, user_id: str, item_id: str) -> tuple[FavoriteState, dict[str, Any], dict[str, Any]]:
    item = client.json(
        "GET", f"/Items/{item_id}", authenticate=True, params={"userId": user_id}
    )
    collection = client.json(
        "GET",
        "/Items",
        authenticate=True,
        params={"userId": user_id, "ids": item_id, "isFavorite": "true"},
    )
    if not isinstance(item, dict) or not isinstance(collection, dict):
        raise SetupError(f"{client.server.label}: invalid item-state response")
    user_data = item.get("UserData")
    is_favorite = user_data.get("IsFavorite") if isinstance(user_data, dict) else None
    if not isinstance(is_favorite, bool):
        raise SetupError(f"{client.server.label}: item response has no boolean UserData.IsFavorite")
    return (
        FavoriteState.FAVORITED if is_favorite else FavoriteState.UNFAVORITED,
        item,
        collection,
    )


def verify_state(
    client: JellyfinClient, user_id: str, item_id: str, expected: FavoriteState
) -> FavoriteState:
    actual, item, collection = read_state(client, user_id, item_id)
    ok, error = UserDataTestModel.verify_item_persistence(expected, item)
    if not ok:
        raise SetupError(f"{client.server.label}: item persistence: {error}")
    ok, error = UserDataTestModel.verify_collection_persistence(expected, item_id, collection)
    if not ok:
        raise SetupError(f"{client.server.label}: favorite collection: {error}")
    return actual


def assert_consistent_states(
    expected: dict[str, FavoriteState],
    v108: dict[str, FavoriteState],
    v109: dict[str, FavoriteState],
) -> None:
    for user, expected_state in expected.items():
        if v108.get(user) != v109.get(user):
            raise SetupError(
                f"{user}: semantic state mismatch "
                f"v10.8={v108.get(user)} v10.9={v109.get(user)}"
            )
        if v108.get(user) != expected_state:
            raise SetupError(
                f"{user}: expected {expected_state.value}, got {v108.get(user)}"
            )


def require_g1_parity(path: Path) -> None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupError(f"cannot read G1-06 evidence {path}: {exc}") from exc
    if report.get("status") != "equivalent":
        raise SetupError("G1-06 initial-state evidence is not equivalent")


def run_step(
    name: str,
    action: FavoriteAction,
    actor: str,
    expected: dict[str, FavoriteState],
    clients: list[JellyfinClient],
    user_ids: list[dict[str, str]],
    item_ids: list[str],
) -> dict[str, Any]:
    responses = [
        favorite_request(client, action, users[actor], item_id)
        for client, users, item_id in zip(clients, user_ids, item_ids)
    ]
    for client, response, item_id in zip(clients, responses, item_ids):
        ok, error = UserDataTestModel.verify_action_invariants(
            action, response["status_code"], response["body"], item_id
        )
        if not ok:
            raise SetupError(f"{client.server.label}: {name} response invariant: {error}")

    states: list[dict[str, FavoriteState]] = []
    for client, users, item_id in zip(clients, user_ids, item_ids):
        states.append(
            {
                user: verify_state(client, users[user], item_id, wanted)
                for user, wanted in expected.items()
            }
        )
    assert_consistent_states(expected, states[0], states[1])

    category = UserDataTestModel.classify_differential_discrepancy(
        responses[0], responses[1], states[0][actor], states[1][actor]
    )
    if category and category.value != "BenignStatusDrift":
        raise SetupError(f"{name}: differential discrepancy {category.value}")
    return {
        "name": name,
        "actor": actor,
        "action": action.value,
        "expected": {user: state.value for user, state in expected.items()},
        "responses": {clients[i].server.label: responses[i] for i in range(2)},
        "states": {
            clients[i].server.label: {user: state.value for user, state in states[i].items()}
            for i in range(2)
        },
        "invariants": "passed",
        "differentialCategory": category.value if category else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--g1-report", type=Path, default=DEFAULT_G1_REPORT)
    parser.add_argument("--item-name", default=DEFAULT_ITEM_NAME)
    parser.add_argument("--user-a", default="g2-10-user-a")
    parser.add_argument("--user-b", default="g2-10-user-b")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"))
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    report: dict[str, Any] = {"task": "G2-10", "status": "failed", "steps": []}
    try:
        require_g1_parity(args.g1_report)
        clients = [
            JellyfinClient(Server("v10.8.13", "http://localhost:8096"), args.timeout),
            JellyfinClient(Server("v10.9.0", "http://localhost:8097"), args.timeout),
        ]
        for client in clients:
            client.authenticate(args.username, args.password)
        item_ids = [find_seed_item(client, args.item_name) for client in clients]
        user_ids = []
        for client in clients:
            if not client.user_id:
                raise SetupError(f"{client.server.label}: admin id unavailable")
            user_ids.append(
                {
                    "admin": client.user_id,
                    "user_a": find_or_create_user(client, args.user_a),
                    "user_b": find_or_create_user(client, args.user_b),
                }
            )

        initial = {"admin": FavoriteState.UNFAVORITED, "user_a": FavoriteState.UNFAVORITED, "user_b": FavoriteState.UNFAVORITED}
        for user in initial:
            for client, users, item_id in zip(clients, user_ids, item_ids):
                favorite_request(client, FavoriteAction.UNMARK_FAVORITE, users[user], item_id)
        for client, users, item_id in zip(clients, user_ids, item_ids):
            for user, state in initial.items():
                verify_state(client, users[user], item_id, state)

        steps = [
            ("ADMIN_MARKS", FavoriteAction.MARK_FAVORITE, "admin", {**initial, "admin": FavoriteState.FAVORITED}),
            ("ADMIN_MARKS_IDEMPOTENT", FavoriteAction.MARK_FAVORITE, "admin", {**initial, "admin": FavoriteState.FAVORITED}),
            ("ADMIN_UNMARKS", FavoriteAction.UNMARK_FAVORITE, "admin", initial),
            ("ADMIN_UNMARKS_IDEMPOTENT", FavoriteAction.UNMARK_FAVORITE, "admin", initial),
            ("USER_A_MARKS", FavoriteAction.MARK_FAVORITE, "user_a", {**initial, "user_a": FavoriteState.FAVORITED}),
            ("USER_B_MARKS", FavoriteAction.MARK_FAVORITE, "user_b", {**initial, "user_a": FavoriteState.FAVORITED, "user_b": FavoriteState.FAVORITED}),
            ("USER_A_UNMARKS", FavoriteAction.UNMARK_FAVORITE, "user_a", {**initial, "user_b": FavoriteState.FAVORITED}),
            ("USER_B_UNMARKS", FavoriteAction.UNMARK_FAVORITE, "user_b", initial),
        ]
        for step in steps:
            report["steps"].append(run_step(*step, clients, user_ids, item_ids))
        report["status"] = "equivalent"
        print("G2-10 success: state invariants are equivalent after every step.")
        return 0
    except (SetupError, requests.RequestException, KeyError, OSError) as exc:
        report["error"] = str(exc)
        print(f"G2-10 failed: {exc}", file=sys.stderr)
        return 1
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
