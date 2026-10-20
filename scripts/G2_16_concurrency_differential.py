#!/usr/bin/env python3
"""G2-16: Concurrency differential testing of user favorite state on Jellyfin 10.8 and 10.9."""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.user_data_model import FavoriteAction, FavoriteState, UserDataTestModel
from scripts.G1_06_setup_and_verify import JellyfinClient, Server, SetupError
from scripts.G2_15_user_state_favorites import favorite_request, read_state, write_report

DEFAULT_REPORT = ROOT / "docs" / "evidence" / "G2-16-concurrency-differential.json"
DEFAULT_MANIFEST = ROOT / "data" / "dataset-manifest.json"
CONCURRENCY_LEVELS = (10, 20, 50, 100)
BARRIER_TIMEOUT_SECONDS = 30.0


def find_common_seed_items(
    clients: Sequence[JellyfinClient],
    manifest: dict[str, Any],
    item_type: str = "Audio",
) -> dict[str, list[dict[str, str]]]:
    """Find unique (Name, Type) seed items common to all clients, capped at 100."""
    library_name = manifest.get("library", {}).get("name")
    if not library_name:
        raise SetupError("Manifest missing library name")

    server_items: dict[str, dict[tuple[str, str], dict[str, str]]] = {}

    for client in clients:
        label = client.server.label
        vf_list = client.json("GET", "/Library/VirtualFolders", authenticate=True)
        if not isinstance(vf_list, list):
            raise SetupError(f"{label}: invalid /Library/VirtualFolders response")

        matching_vf = [f for f in vf_list if isinstance(f, dict) and f.get("Name") == library_name]
        if len(matching_vf) != 1 or not matching_vf[0].get("ItemId"):
            raise SetupError(
                f"{label}: expected exactly one virtual folder named '{library_name}', found {len(matching_vf)}"
            )

        lib_item_id = str(matching_vf[0]["ItemId"])

        items_by_key: dict[tuple[str, str], dict[str, str]] = {}
        start_index = 0
        limit = 50

        while True:
            params: dict[str, Any] = {
                "ParentId": lib_item_id,
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "StartIndex": start_index,
                "Limit": limit,
            }
            if client.user_id:
                params["UserId"] = client.user_id

            data = client.json("GET", "/Items", authenticate=True, params=params)
            if not isinstance(data, dict) or not isinstance(data.get("Items"), list):
                raise SetupError(f"{label}: invalid /Items response")

            page = data["Items"]
            for item in page:
                if not isinstance(item, dict):
                    continue
                iid = item.get("Id")
                name = item.get("Name")
                itype = item.get("Type")
                if not (isinstance(iid, str) and isinstance(name, str) and isinstance(itype, str)):
                    continue

                key = (name, itype)
                if key in items_by_key:
                    raise SetupError(f"{label}: duplicate seed item key {key}")

                items_by_key[key] = {
                    "Id": iid,
                    "Name": name,
                    "Type": itype,
                }

            total_count = data.get("TotalRecordCount")
            if not page:
                break
            if isinstance(total_count, int):
                if (start_index + len(page)) >= total_count:
                    break
            elif len(page) < limit:
                break
            start_index += len(page)

        server_items[label] = items_by_key

    # Common keys across all clients
    client_labels = [c.server.label for c in clients]
    if not client_labels:
        return {}

    common_keys = set(server_items[client_labels[0]].keys())
    for label in client_labels[1:]:
        common_keys.intersection_update(server_items[label].keys())

    # Sort stably and cap at 100
    sorted_common = sorted(common_keys, key=lambda k: (k[0], k[1]))[:100]

    result: dict[str, list[dict[str, str]]] = {}
    for label in client_labels:
        result[label] = [server_items[label][k] for k in sorted_common]

    return result


def _make_worker_client(client: JellyfinClient) -> tuple[Any, Any]:
    """Create a worker-local client instance with an isolated HTTP session."""
    if hasattr(client, "create_worker"):
        w = client.create_worker()
        return w, getattr(w, "session", None)
    if isinstance(client, JellyfinClient):
        worker = JellyfinClient(client.server, client.timeout)
        worker.token = client.token
        worker.user_id = client.user_id
        return worker, worker.session
    # Fallback for fake client test doubles
    return client, getattr(client, "session", None)


def _execute_worker_favorite(
    client: Any,
    session: Any,
    action: FavoriteAction,
    user_id: str,
    item_id: str,
    item_name: str,
    barrier: threading.Barrier,
) -> dict[str, Any]:
    """Wait on synchronized barrier, execute favorite mutation, and close session."""
    try:
        try:
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        except threading.BrokenBarrierError as bbe:
            return {
                "item_id": item_id,
                "item_name": item_name,
                "status": "failed",
                "response": None,
                "error": f"Barrier broken: {bbe}",
            }
        except Exception as be:
            return {
                "item_id": item_id,
                "item_name": item_name,
                "status": "failed",
                "response": None,
                "error": f"Barrier wait failed: {be}",
            }

        try:
            resp = favorite_request(client, action, user_id, item_id)
            return {
                "item_id": item_id,
                "item_name": item_name,
                "status": "passed",
                "response": resp,
                "error": None,
            }
        except Exception as req_exc:
            return {
                "item_id": item_id,
                "item_name": item_name,
                "status": "failed",
                "response": None,
                "error": str(req_exc),
            }
    finally:
        if session is not None and hasattr(session, "close"):
            try:
                session.close()
            except Exception:
                pass


def run_concurrent_batch(
    clients: Sequence[JellyfinClient],
    items_by_server: dict[str, list[dict[str, str]]],
    action: FavoriteAction,
    concurrency: int,
) -> dict[str, Any]:
    """Execute exactly concurrency requests per server synchronized at a thread barrier."""
    total_workers = len(clients) * concurrency
    barrier = threading.Barrier(total_workers)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=total_workers)

    results_by_server: dict[str, dict[str, list[dict[str, Any] | None]]] = {
        client.server.label: {"requests": [None] * concurrency} for client in clients
    }
    futures: dict[tuple[str, int], tuple[concurrent.futures.Future[dict[str, Any]], str, str]] = {}

    setup_error: str | None = None

    try:
        for client in clients:
            label = client.server.label
            server_items = items_by_server.get(label, [])
            user_id = client.user_id or ""

            for idx in range(concurrency):
                if idx >= len(server_items):
                    raise SetupError(
                        f"{label}: not enough items for concurrency {concurrency} (available: {len(server_items)})"
                    )
                item = server_items[idx]
                item_id = item["Id"]
                item_name = item["Name"]

                worker_client, worker_session = _make_worker_client(client)
                fut = pool.submit(
                    _execute_worker_favorite,
                    worker_client,
                    worker_session,
                    action,
                    user_id,
                    item_id,
                    item_name,
                    barrier,
                )
                futures[(label, idx)] = (fut, item_id, item_name)
    except Exception as exc:
        setup_error = str(exc)
        barrier.abort()

    # Collect all submitted futures
    for (label, idx), (fut, item_id, item_name) in futures.items():
        try:
            res = fut.result()
            results_by_server[label]["requests"][idx] = res
        except Exception as fut_exc:
            results_by_server[label]["requests"][idx] = {
                "item_id": item_id,
                "item_name": item_name,
                "status": "failed",
                "response": None,
                "error": str(fut_exc),
            }

    # Fill in any slots that were never submitted
    for client in clients:
        label = client.server.label
        server_items = items_by_server.get(label, [])
        for idx in range(concurrency):
            if results_by_server[label]["requests"][idx] is None:
                item = server_items[idx] if idx < len(server_items) else {"Id": f"unsubmitted-{idx}", "Name": "unknown"}
                results_by_server[label]["requests"][idx] = {
                    "item_id": item["Id"],
                    "item_name": item["Name"],
                    "status": "failed",
                    "response": None,
                    "error": f"Worker setup/submit failed: {setup_error}",
                }

    pool.shutdown(wait=True)
    return {"servers": results_by_server}


def run_case(
    clients: Sequence[JellyfinClient],
    items_by_server: dict[str, list[dict[str, str]]],
    action: FavoriteAction,
    concurrency: int,
) -> dict[str, Any]:
    """Execute a single concurrent test case across all servers with full state lifecycle."""
    case_record: dict[str, Any] = {
        "action": action.name,
        "concurrency": concurrency,
        "status": "failed",
        "parity": False,
        "error": None,
        "servers": {
            client.server.label: {
                "requests": [],
                "items": {},
            }
            for client in clients
        },
    }

    writes_attempted = False
    snapshots: dict[str, dict[str, dict[str, bool]]] = {client.server.label: {} for client in clients}
    targets_by_server: dict[str, list[dict[str, str]]] = {
        client.server.label: items_by_server.get(client.server.label, [])[:concurrency]
        for client in clients
    }

    try:
        # Phase 1: Snapshot and preflight check
        for client in clients:
            label = client.server.label
            targets = targets_by_server[label]
            user_id = client.user_id or ""

            if len(targets) < concurrency:
                raise SetupError(
                    f"{label}: insufficient items for concurrency {concurrency} (found {len(targets)})"
                )

            for item in targets:
                item_id = item["Id"]
                orig_state = read_state(client, user_id, item_id)
                snapshots[label][item_id] = orig_state
                case_record["servers"][label]["items"][item_id] = {
                    "original": orig_state,
                    "final": None,
                    "verification_error": None,
                    "cleanup": "not_needed",
                    "cleanup_state": None,
                    "cleanup_error": None,
                }
                if orig_state["is_favorite"] != orig_state["in_favorites"]:
                    raise SetupError(
                        f"{label}: preflight favorite state inconsistent for {item['Name']} ({item_id}): "
                        f"IsFavorite={orig_state['is_favorite']}, in_favorites={orig_state['in_favorites']}"
                    )

        # Precondition check passed; writes will now be attempted
        writes_attempted = True

        # Phase 2: Precondition normalization
        # MARK_FAVORITE requires targets to start unfavorited (False)
        # UNMARK_FAVORITE requires targets to start favorited (True)
        target_precondition = (action == FavoriteAction.UNMARK_FAVORITE)
        norm_action = FavoriteAction.MARK_FAVORITE if target_precondition else FavoriteAction.UNMARK_FAVORITE

        for client in clients:
            label = client.server.label
            targets = targets_by_server[label]
            user_id = client.user_id or ""

            for item in targets:
                item_id = item["Id"]
                curr = read_state(client, user_id, item_id)
                if curr["is_favorite"] != target_precondition or curr["in_favorites"] != target_precondition:
                    favorite_request(client, norm_action, user_id, item_id)
                    verified = read_state(client, user_id, item_id)
                    if (
                        verified["is_favorite"] != target_precondition
                        or verified["in_favorites"] != target_precondition
                    ):
                        raise SetupError(
                            f"{label}: failed to normalize precondition for {item['Name']} ({item_id}) to {target_precondition}"
                        )

        # Phase 3: Synchronized batch execution
        batch_result = run_concurrent_batch(clients, targets_by_server, action, concurrency)
        for client in clients:
            label = client.server.label
            case_record["servers"][label]["requests"] = batch_result["servers"][label]["requests"]

        # Phase 4: Post-batch verification
        expected_final = (action == FavoriteAction.MARK_FAVORITE)
        verification_errors: list[str] = []

        for client in clients:
            label = client.server.label
            targets = targets_by_server[label]
            user_id = client.user_id or ""

            for item in targets:
                item_id = item["Id"]
                item_record = case_record["servers"][label]["items"][item_id]
                try:
                    final_state = read_state(client, user_id, item_id)
                except Exception as exc:
                    item_record["verification_error"] = str(exc)
                    verification_errors.append(f"{label} {item['Name']} ({item_id}): {exc}")
                    continue

                case_record["servers"][label]["items"][item_id]["final"] = final_state

                if (
                    final_state["is_favorite"] != expected_final
                    or final_state["in_favorites"] != expected_final
                ):
                    verification_errors.append(
                        f"{label} {item['Name']} ({item_id}): unexpected state {final_state}"
                    )

        if verification_errors:
            case_record["error"] = (
                "Post-batch state verification failed: " + "; ".join(verification_errors)
            )

    except Exception as exc:
        case_record["error"] = str(exc)

    finally:
        # Phase 5: Restoration
        if writes_attempted:
            cleanup_errors = []
            for client in clients:
                label = client.server.label
                targets = targets_by_server[label]
                user_id = client.user_id or ""

                for item in targets:
                    item_id = item["Id"]
                    orig_state = snapshots[label].get(item_id)
                    if orig_state is None:
                        continue

                    orig_fav = orig_state["is_favorite"]
                    restore_action = (
                        FavoriteAction.MARK_FAVORITE if orig_fav else FavoriteAction.UNMARK_FAVORITE
                    )
                    restore_error: str | None = None
                    cleanup_state: dict[str, bool] | None = None

                    try:
                        favorite_request(client, restore_action, user_id, item_id)
                    except Exception as rest_exc:
                        restore_error = str(rest_exc)

                    # Read back even if restore request failed
                    try:
                        cleanup_state = read_state(client, user_id, item_id)
                    except Exception as read_exc:
                        err_msg = f"read_state failed: {read_exc}"
                        restore_error = f"{restore_error}; {err_msg}" if restore_error else err_msg

                    if (
                        restore_error is None
                        and cleanup_state is not None
                        and cleanup_state.get("is_favorite") == orig_fav
                        and cleanup_state.get("in_favorites") == orig_fav
                    ):
                        cleanup_status = "passed"
                    else:
                        cleanup_status = "failed"
                        if not restore_error:
                            restore_error = (
                                f"Restored state mismatch: expected {orig_fav}, got {cleanup_state}"
                            )
                        cleanup_errors.append(f"{label} {item_id}: {restore_error}")

                    case_record["servers"][label]["items"][item_id]["cleanup"] = cleanup_status
                    case_record["servers"][label]["items"][item_id]["cleanup_state"] = cleanup_state
                    case_record["servers"][label]["items"][item_id]["cleanup_error"] = restore_error

            if cleanup_errors:
                cleanup_msg = f"Cleanup failed on {len(cleanup_errors)} item(s): {'; '.join(cleanup_errors)}"
                if case_record["error"]:
                    case_record["error"] = f"{case_record['error']}; {cleanup_msg}"
                else:
                    case_record["error"] = cleanup_msg

    # Phase 6: Parity and overall status
    labels = [c.server.label for c in clients]
    parity_ok = True

    # Parity check: all servers must have matched final states
    if len(labels) >= 2:
        base_label = labels[0]
        base_targets = targets_by_server[base_label]
        for idx in range(concurrency):
            if idx >= len(base_targets):
                parity_ok = False
                break
            base_item_id = base_targets[idx]["Id"]
            base_final = case_record["servers"][base_label]["items"].get(base_item_id, {}).get("final")

            for other_label in labels[1:]:
                other_targets = targets_by_server[other_label]
                if idx >= len(other_targets):
                    parity_ok = False
                    break
                other_item_id = other_targets[idx]["Id"]
                other_final = case_record["servers"][other_label]["items"].get(other_item_id, {}).get("final")
                if base_final is None or other_final is None or base_final != other_final:
                    parity_ok = False
                    break
            if not parity_ok:
                break
    else:
        parity_ok = True

    case_record["parity"] = parity_ok

    # Check request outcomes
    all_requests_passed = True
    for label in labels:
        reqs = case_record["servers"][label]["requests"]
        if not reqs or any(r.get("status") != "passed" for r in reqs):
            all_requests_passed = False
            break

    # Check cleanup outcomes
    all_cleanups_passed = True
    if writes_attempted:
        for label in labels:
            items = case_record["servers"][label]["items"]
            if any(info.get("cleanup") != "passed" for info in items.values()):
                all_cleanups_passed = False
                break

    if not all_requests_passed and not case_record["error"]:
        case_record["error"] = "One or more concurrent batch requests failed"
    elif not parity_ok and not case_record["error"]:
        case_record["error"] = "Differential parity mismatch across server versions"
    elif writes_attempted and not all_cleanups_passed and not case_record["error"]:
        case_record["error"] = "One or more items failed cleanup"

    if (
        case_record["error"] is None
        and parity_ok
        and all_requests_passed
        and (not writes_attempted or all_cleanups_passed)
    ):
        case_record["status"] = "passed"
    else:
        case_record["status"] = "failed"

    return case_record


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for G2-16 concurrency differential runner."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v108-url", default=os.environ.get("JELLYFIN_V108_URL", "http://localhost:8096"))
    parser.add_argument("--v109-url", default=os.environ.get("JELLYFIN_V109_URL", "http://localhost:8097"))
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"))
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)

    args = parser.parse_args(argv)

    report_data: dict[str, Any] = {
        "task": "G2-16",
        "status": "failed",
        "parity": False,
        "cases": [],
        "error": None,
    }

    clients = [
        JellyfinClient(Server("v10.8.13", args.v108_url), args.timeout),
        JellyfinClient(Server("v10.9.0", args.v109_url), args.timeout),
    ]

    try:
        if not args.manifest.exists():
            raise SetupError(f"Dataset manifest not found: {args.manifest}")

        with open(args.manifest, encoding="utf-8") as f:
            manifest = json.load(f)

        # Authenticate all clients
        for client in clients:
            client.authenticate(args.username, args.password)

        # Discover common items
        common_items = find_common_seed_items(clients, manifest, item_type="Audio")
        server_labels = [c.server.label for c in clients]
        available_count = min(len(common_items.get(lbl, [])) for lbl in server_labels) if server_labels else 0

        # Run each level and each action
        for level in CONCURRENCY_LEVELS:
            for action in (FavoriteAction.MARK_FAVORITE, FavoriteAction.UNMARK_FAVORITE):
                if available_count < level:
                    report_data["cases"].append({
                        "action": action.name,
                        "concurrency": level,
                        "status": "skipped_insufficient_items",
                        "parity": None,
                        "matched_item_names": [],
                        "server_labels": server_labels,
                        "error": (
                            f"Insufficient common seed items for level {level}: "
                            f"available {available_count}, required {level}"
                        ),
                        "servers": {lbl: {"requests": [], "items": {}} for lbl in server_labels},
                    })
                else:
                    matched_names = [it["Name"] for it in common_items[server_labels[0]][:level]]
                    case_res = run_case(clients, common_items, action, level)
                    case_res["matched_item_names"] = matched_names
                    case_res["server_labels"] = server_labels
                    report_data["cases"].append(case_res)

        # Evaluate overall parity and status
        total_cases = len(CONCURRENCY_LEVELS) * 2
        cases_passed = sum(1 for c in report_data["cases"] if c.get("status") == "passed")
        all_parity = all(c.get("parity") is True for c in report_data["cases"])

        report_data["parity"] = all_parity
        if cases_passed == total_cases and all_parity:
            report_data["status"] = "passed"
        else:
            report_data["status"] = "failed"

    except Exception as exc:
        report_data["status"] = "failed"
        report_data["error"] = str(exc)

    try:
        write_report(args.report, report_data)
    except Exception as write_err:
        print(f"Error: Failed to write report to {args.report}: {write_err}", file=sys.stderr)
        return 1

    return 0 if report_data["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())



