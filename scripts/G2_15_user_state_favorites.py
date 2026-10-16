#!/usr/bin/env python3
"""G2-15: Differential testing of Favorite user state transitions and persistence."""

from __future__ import annotations

import json
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


MAIN_FLOW_CHECKPOINTS = ("post_favorite", "verify_favorite", "delete_favorite", "verify_unfavorite")


def compare_semantics(
    v108_instance: dict[str, Any],
    v109_instance: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Compare the 4 main-flow checkpoints between v10.8 and v10.9 instances."""
    diffs: list[str] = []
    steps_108 = v108_instance.get("steps", {})
    steps_109 = v109_instance.get("steps", {})

    for checkpoint in MAIN_FLOW_CHECKPOINTS:
        in_108 = checkpoint in steps_108
        in_109 = checkpoint in steps_109

        if not in_108 or not in_109:
            diffs.append(
                f"Missing checkpoint '{checkpoint}': present in v10.8={in_108}, v10.9={in_109}"
            )
            continue

        s108 = steps_108[checkpoint]
        s109 = steps_109[checkpoint]

        # Status comparison (passed vs failed)
        status_108 = s108.get("status")
        status_109 = s109.get("status")
        if status_108 != status_109:
            diffs.append(
                f"Checkpoint '{checkpoint}' status mismatch: v10.8={status_108}, v10.9={status_109}"
            )

        # Semantic verification step comparisons
        if "is_favorite" in s108 or "is_favorite" in s109:
            if s108.get("is_favorite") != s109.get("is_favorite"):
                diffs.append(
                    f"Checkpoint '{checkpoint}' is_favorite mismatch: "
                    f"v10.8={s108.get('is_favorite')}, v10.9={s109.get('is_favorite')}"
                )
            if s108.get("in_favorites") != s109.get("in_favorites"):
                diffs.append(
                    f"Checkpoint '{checkpoint}' in_favorites mismatch: "
                    f"v10.8={s108.get('in_favorites')}, v10.9={s109.get('in_favorites')}"
                )

    return len(diffs) == 0, diffs


def write_report(path: Path | str, report_data: dict[str, Any]) -> None:
    """Serialize the evidence report as formatted UTF-8 JSON with a trailing newline."""
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(report_data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v108-url", default=os.environ.get("JELLYFIN_V108_URL", "http://localhost:8096"))
    parser.add_argument("--v109-url", default=os.environ.get("JELLYFIN_V109_URL", "http://localhost:8097"))
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"))
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--item-name", default=DEFAULT_ITEM_NAME)
    parser.add_argument("--item-type", default=DEFAULT_ITEM_TYPE)
    parser.add_argument("--g1-report", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)

    args = parser.parse_args(argv)

    report_data: dict[str, Any] = {
        "task": "G2-15",
        "status": "failed",
        "parity": "mismatched",
        "parity_diffs": [],
        "instances": {},
        "error": None,
    }
    returncode = 1

    try:
        # Validate optional G1 report if specified
        if args.g1_report is not None:
            if not args.g1_report.exists():
                raise SetupError(f"Specified G1-06 report does not exist: {args.g1_report}")
            g1_content = json.loads(args.g1_report.read_text(encoding="utf-8"))
            if g1_content.get("status") != "equivalent":
                raise SetupError(
                    f"G1-06 sanity check failed: expected status 'equivalent', got {g1_content.get('status')!r}"
                )

        clients = [
            JellyfinClient(Server("v10.8.13", args.v108_url), args.timeout),
            JellyfinClient(Server("v10.9.0", args.v109_url), args.timeout),
        ]

        # Authenticate and run each instance, allowing a healthy peer to run if one fails
        for client in clients:
            label = client.server.label
            try:
                client.authenticate(args.username, args.password)
                seed = find_seed_item(client, args.item_name, args.item_type)
                inst_res = run_instance(client, client.user_id, seed)
                report_data["instances"][label] = inst_res
            except Exception as inst_err:
                report_data["instances"][label] = {
                    "server": label,
                    "seed_id": None,
                    "original_state": None,
                    "normalize_initial": None,
                    "steps": {},
                    "cleanup": {"status": "skipped"},
                    "success": False,
                    "error": str(inst_err),
                }

        # Compare parity across instances
        inst108 = report_data["instances"].get("v10.8.13", {})
        inst109 = report_data["instances"].get("v10.9.0", {})
        is_eq, diffs = compare_semantics(inst108, inst109)
        report_data["parity_diffs"] = diffs
        report_data["parity"] = "equivalent" if is_eq else "mismatched"

        all_success = (
            inst108.get("success") is True
            and inst109.get("success") is True
            and is_eq
        )

        if all_success:
            report_data["status"] = "passed"
            returncode = 0
        else:
            report_data["status"] = "failed"
            returncode = 1

    except Exception as exc:
        report_data["status"] = "failed"
        report_data["error"] = str(exc)
        returncode = 1

    try:
        write_report(args.report, report_data)
    except Exception as write_err:
        print(f"Error: Failed to write report to {args.report}: {write_err}", file=sys.stderr)
        return 1

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())



