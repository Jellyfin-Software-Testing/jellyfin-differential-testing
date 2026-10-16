#!/usr/bin/env python3
"""G2-15: Differential testing of Favorite user state transitions and persistence."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.user_data_model import FavoriteAction, FavoriteState, UserDataTestModel
from scripts.G1_06_setup_and_verify import JellyfinClient, Server, SetupError

DEFAULT_ITEM_NAME = "01 - Reference Tone"
DEFAULT_ITEM_TYPE = "Audio"
DEFAULT_REPORT = ROOT / "docs" / "evidence" / "G2-15-user-state-favorites.json"


def find_seed_item(
    client: JellyfinClient,
    name: str = DEFAULT_ITEM_NAME,
    item_type: str = DEFAULT_ITEM_TYPE,
) -> dict[str, str]:
    """Resolve exactly one matching item independently on the client instance."""
    if not client.user_id:
        raise SetupError(f"{client.server.label}: no authenticated admin user")

    params = {
        "UserId": client.user_id,
        "IncludeItemTypes": item_type,
        "Recursive": "true",
    }
    data = client.json("GET", "/Items", authenticate=True, params=params)
    items = data.get("Items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SetupError(f"{client.server.label}: invalid /Items response")

    matches = [
        item for item in items
        if isinstance(item, dict) and item.get("Name") == name and item.get("Type") == item_type
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("Id"), str):
        raise SetupError(
            f"{client.server.label}: expected exactly one seed item ({name}, {item_type}), found {len(matches)}"
        )

    matched = matches[0]
    return {
        "Id": matched["Id"],
        "Name": matched.get("Name", name),
        "Type": matched.get("Type", item_type),
    }


def favorite_request(
    client: JellyfinClient,
    action: FavoriteAction,
    user_id: str,
    item_id: str,
) -> dict[str, Any]:
    """Execute versioned Favorite POST/DELETE and validate response invariants."""
    if client.server.label.startswith("v10.8") or "10.8" in client.server.label:
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

    ok, error = UserDataTestModel.verify_action_invariants(
        action, response.status_code, body, item_id
    )
    if not ok:
        raise SetupError(f"{client.server.label}: {action.value} invariant failed: {error}")

    return {"status_code": response.status_code, "body": body}


def read_state(client: JellyfinClient, user_id: str, item_id: str) -> dict[str, bool]:
    """Read UserData.IsFavorite and favorite collection membership for user and item."""
    if client.server.label.startswith("v10.8") or "10.8" in client.server.label:
        item = client.json("GET", f"/Users/{user_id}/Items/{item_id}", authenticate=True)
    else:
        item = client.json("GET", f"/Items/{item_id}", authenticate=True, params={"userId": user_id})

    collection = client.json(
        "GET",
        "/Items",
        authenticate=True,
        params={"userId": user_id, "ids": item_id, "isFavorite": "true"},
    )
    if not isinstance(item, dict) or not isinstance(collection, dict):
        raise SetupError(f"{client.server.label}: invalid item or collection response")

    user_data = item.get("UserData")
    if not isinstance(user_data, dict):
        raise SetupError(f"{client.server.label}: item response missing UserData")

    is_favorite = bool(user_data.get("IsFavorite"))

    items = collection.get("Items")
    if not isinstance(items, list):
        raise SetupError(f"{client.server.label}: collection response missing Items list")

    in_favorites = any(
        UserDataTestModel.is_same_guid(i.get("Id"), item_id)
        for i in items
        if isinstance(i, dict)
    )

    return {"is_favorite": is_favorite, "in_favorites": in_favorites}


def run_instance(client: JellyfinClient, user_id: str, seed: dict[str, str]) -> dict[str, Any]:
    """Run the favorite lifecycle on a single server instance with finally restoration."""
    item_id = seed["Id"]
    instance_record: dict[str, Any] = {
        "server": client.server.label,
        "seed_id": item_id,
        "original_state": None,
        "normalize_initial": None,
        "steps": {},
        "cleanup": {"status": "skipped"},
        "success": False,
        "error": None,
    }

    baseline_is_fav: bool | None = None

    try:
        # Precondition: read initial state
        initial_state = read_state(client, user_id, item_id)
        instance_record["original_state"] = initial_state

        if initial_state["is_favorite"] != initial_state["in_favorites"]:
            raise SetupError(
                f"{client.server.label}: inconsistent initial state "
                f"(IsFavorite={initial_state['is_favorite']}, in_favorites={initial_state['in_favorites']})"
            )

        baseline_is_fav = initial_state["is_favorite"]

        # If initially favorited, normalize to unfavorited
        if baseline_is_fav:
            favorite_request(client, FavoriteAction.UNMARK_FAVORITE, user_id, item_id)
            norm_state = read_state(client, user_id, item_id)
            if norm_state["is_favorite"] or norm_state["in_favorites"]:
                raise SetupError(f"{client.server.label}: failed to normalize initial state to unfavorited")
            instance_record["normalize_initial"] = {
                "action": "DELETE",
                "status": "passed",
                "state_after": norm_state,
            }
        else:
            instance_record["normalize_initial"] = {"skipped": True, "status": "passed"}

        # Official main flow:
        # 1. post_favorite
        post_resp = favorite_request(client, FavoriteAction.MARK_FAVORITE, user_id, item_id)
        instance_record["steps"]["post_favorite"] = {
            "status": "passed",
            "status_code": post_resp["status_code"],
            "body": post_resp["body"],
        }

        # 2. verify_favorite
        fav_state = read_state(client, user_id, item_id)
        if not (fav_state["is_favorite"] and fav_state["in_favorites"]):
            raise SetupError(f"{client.server.label}: verify_favorite failed: {fav_state}")
        instance_record["steps"]["verify_favorite"] = {
            "status": "passed",
            "is_favorite": fav_state["is_favorite"],
            "in_favorites": fav_state["in_favorites"],
        }

        # 3. delete_favorite
        del_resp = favorite_request(client, FavoriteAction.UNMARK_FAVORITE, user_id, item_id)
        instance_record["steps"]["delete_favorite"] = {
            "status": "passed",
            "status_code": del_resp["status_code"],
            "body": del_resp["body"],
        }

        # 4. verify_unfavorite
        unfav_state = read_state(client, user_id, item_id)
        if unfav_state["is_favorite"] or unfav_state["in_favorites"]:
            raise SetupError(f"{client.server.label}: verify_unfavorite failed: {unfav_state}")
        instance_record["steps"]["verify_unfavorite"] = {
            "status": "passed",
            "is_favorite": unfav_state["is_favorite"],
            "in_favorites": unfav_state["in_favorites"],
        }

        instance_record["success"] = True

    except Exception as exc:
        instance_record["success"] = False
        instance_record["error"] = str(exc)

    finally:
        # Restoration in finally
        if baseline_is_fav is not None:
            if hasattr(client, "cleanup_phase"):
                client.cleanup_phase = True
            try:
                curr_state = read_state(client, user_id, item_id)
                if curr_state["is_favorite"] != baseline_is_fav:
                    restore_action = (
                        FavoriteAction.MARK_FAVORITE if baseline_is_fav else FavoriteAction.UNMARK_FAVORITE
                    )
                    favorite_request(client, restore_action, user_id, item_id)
                    restored_state = read_state(client, user_id, item_id)
                    if restored_state["is_favorite"] != baseline_is_fav:
                        raise SetupError(
                            f"{client.server.label}: failed to restore baseline state to {baseline_is_fav}"
                        )
                instance_record["cleanup"] = {"status": "passed", "restored_to": baseline_is_fav}
            except Exception as clean_exc:
                instance_record["cleanup"] = {"status": "failed", "error": str(clean_exc)}
                instance_record["success"] = False
                if not instance_record["error"]:
                    instance_record["error"] = f"cleanup failure: {clean_exc}"

    return instance_record

