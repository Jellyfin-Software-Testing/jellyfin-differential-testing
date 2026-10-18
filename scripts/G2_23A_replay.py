#!/usr/bin/env python3
"""Capture a differential failure and measure its reproduction rate.

Only read-only GET requests are executed by this CLI. Mutating requests need a
separate state-reset strategy and are rejected rather than replayed unsafely.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizer import SemanticNormalizer
from normalizer.G2_07_diff_engine import DiffItem, SemanticDiffEngine
from scripts.G1_06_setup_and_verify import (
    JellyfinClient, Server, SetupError, load_manifest,
)
from scripts.G2_23A_replay_record import (
    ReplayRecordError, build_reference_fingerprint, canonical_sha256,
    file_sha256, generate_request, load_record, make_record, save_record,
    validate_record,
)


class ReplayEnvironmentError(RuntimeError):
    """A run cannot be counted because its environment is unsuitable."""


def configuration_snapshot(
    manifest: dict[str, Any], configuration: Any, label: str,
) -> dict[str, str]:
    """Check the G1-06 configuration fields that affect seeded API tests."""
    if not isinstance(configuration, dict):
        raise ReplayEnvironmentError(f"{label}: invalid system configuration")
    fields = {
        "ServerName": "serverName",
        "UICulture": "uiCulture",
        "MetadataCountryCode": "metadataCountryCode",
        "PreferredMetadataLanguage": "preferredMetadataLanguage",
    }
    snapshot = {field: configuration.get(field) for field in fields}
    if any(snapshot[field] != manifest["startup"][key] for field, key in fields.items()):
        raise ReplayEnvironmentError(f"{label}: G1-06 system configuration changed")
    return snapshot


def seed_snapshot(
    manifest: dict[str, Any], folders: Any, items: Any, label: str,
) -> dict[str, Any]:
    """Validate the read-only G1-06 seed library and ignore server-specific IDs."""
    library = manifest["library"]
    if not isinstance(folders, list) or not isinstance(items, list):
        raise ReplayEnvironmentError(f"{label}: invalid seed library response")
    matches = [
        folder for folder in folders
        if isinstance(folder, dict) and folder.get("Name") == library["name"]
    ]
    if len(matches) != 1:
        raise ReplayEnvironmentError(f"{label}: expected one G1-06 seed library")
    folder = matches[0]
    locations = folder.get("Locations")
    if (
        folder.get("CollectionType") != library["collectionType"]
        or not isinstance(locations, list)
        or sorted(locations) != sorted(library["paths"])
    ):
        raise ReplayEnvironmentError(f"{label}: seed library configuration changed")

    expected: list[dict[str, Any]] = []
    for specification in manifest["files"]:
        name = PurePosixPath(specification["relativePath"]).stem
        matches = [
            item for item in items
            if isinstance(item, dict) and item.get("Name") == name
            and item.get("Type") == "Audio"
        ]
        if len(matches) != 1:
            raise ReplayEnvironmentError(f"{label}: expected one seed item {name!r}")
        duration = specification["durationSeconds"] * 10_000_000
        if matches[0].get("RunTimeTicks") != duration:
            raise ReplayEnvironmentError(f"{label}: seed item {name!r} duration changed")
        expected.append({"Name": name, "Type": "Audio", "RunTimeTicks": duration})
    if len(items) != len(expected):
        raise ReplayEnvironmentError(f"{label}: unexpected items in seed library")

    return {
        "library": {
            "Name": library["name"],
            "CollectionType": library["collectionType"],
            "Locations": sorted(library["paths"]),
        },
        "items": sorted(expected, key=lambda item: item["Name"]),
    }


def probe_environment(clients: tuple[JellyfinClient, JellyfinClient]) -> dict[str, Any]:
    """Check live server versions, seed parity, and local input fingerprints."""
    if len(clients) != 2:
        raise ReplayEnvironmentError("Exactly two Jellyfin clients are required")
    reference = build_reference_fingerprint()
    manifest = load_manifest(ROOT / "data" / "dataset-manifest.json")
    parity = json.loads(
        (ROOT / "docs" / "evidence" / "G1-06-initial-state-parity.json")
        .read_text(encoding="utf-8-sig")
    )
    seed_dir = (ROOT / "data" / "seed-data").resolve()
    expected_files = {
        entry["relativePath"]: entry["sha256"]
        for entry in parity.get("seedFiles", [])
    }
    for specification in manifest["files"]:
        relative = specification["relativePath"]
        source = (seed_dir / relative).resolve()
        if (
            not source.is_relative_to(seed_dir)
            or expected_files.get(relative) != file_sha256(source)
        ):
            raise ReplayEnvironmentError(f"Seed media differs from G1-06: {relative}")

    snapshots: list[dict[str, Any]] = []
    expected_versions = ("10.8.13", "10.9.0")
    for client, version in zip(clients, expected_versions):
        info = client.json("GET", "/System/Info/Public", expected=(200,))
        if (
            not isinstance(info, dict)
            or info.get("Version") != version
            or info.get("StartupWizardCompleted") is not True
        ):
            raise ReplayEnvironmentError(
                f"{client.server.label}: wrong version or unfinished setup wizard"
            )
        if not client.user_id:
            raise ReplayEnvironmentError(f"{client.server.label}: authentication is required")
        folders = client.json("GET", "/Library/VirtualFolders", authenticate=True)
        matches = [
            folder for folder in folders
            if isinstance(folder, dict) and folder.get("Name") == manifest["library"]["name"]
        ] if isinstance(folders, list) else []
        if len(matches) != 1 or not isinstance(matches[0].get("ItemId"), str):
            raise ReplayEnvironmentError(f"{client.server.label}: missing seed library ID")
        items = client.seeded_items(matches[0]["ItemId"])
        snapshot = seed_snapshot(manifest, folders, items, client.server.label)
        configuration = client.json(
            "GET", "/System/Configuration", authenticate=True
        )
        snapshot["configuration"] = configuration_snapshot(
            manifest, configuration, client.server.label
        )
        snapshots.append(snapshot)

    if snapshots[0] != snapshots[1]:
        raise ReplayEnvironmentError("The two live seed states are not equivalent")
    reference["seed_state_sha256"] = canonical_sha256(snapshots[0])
    return reference


def resolve_user_placeholder(value: Any, user_id: str | None) -> Any:
    """Substitute each server's own admin ID without storing that ID in a record."""
    if value == "$AUTH_USER" and isinstance(value, str):
        if not user_id:
            raise ReplayEnvironmentError("Authenticated user ID is unavailable")
        return user_id
    if isinstance(value, dict):
        return {key: resolve_user_placeholder(child, user_id) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_user_placeholder(child, user_id) for child in value]
    return value


def _body(response: requests.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def _item_mapping(left: Any, right: Any) -> dict[str, str]:
    """Map unique semantic item identities; ambiguous duplicates remain visible."""
    mapping: dict[str, str] = {}
    sides: list[dict[str, list[str]]] = []
    for body in (left, right):
        identities: dict[str, list[str]] = {}
        if not isinstance(body, dict) or not isinstance(body.get("Items"), list):
            sides.append(identities)
            continue
        for item in body["Items"]:
            if not isinstance(item, dict) or not isinstance(item.get("Id"), str):
                continue
            identity = canonical_sha256({
                "Name": item.get("Name"),
                "Type": item.get("Type"),
                "RunTimeTicks": item.get("RunTimeTicks"),
            })
            identities.setdefault(identity, []).append(item["Id"])
        sides.append(identities)
    for identity in sides[0].keys() & sides[1].keys():
        if len(sides[0][identity]) == len(sides[1][identity]) == 1:
            mapping[sides[0][identity][0]] = f"item:{identity}"
            mapping[sides[1][identity][0]] = f"item:{identity}"
    return mapping


def signature_from_diff(diff: DiffItem) -> dict[str, str]:
    """Identify the same normalized difference without storing response values."""
    return {
        "category": diff.category.value,
        "path": diff.path,
        "v1_sha256": canonical_sha256(diff.v1_val),
        "v2_sha256": canonical_sha256(diff.v2_val),
    }


def observe_differences(
    clients: tuple[JellyfinClient, JellyfinClient],
    request: dict[str, Any],
    normalizer: SemanticNormalizer,
) -> list[dict[str, str]]:
    """Issue the recorded request to both servers and compare normalized data."""
    if request["method"] != "GET":
        raise ReplayRecordError("CLI replay supports GET only; mutations need a reset hook")
    responses: list[requests.Response] = []
    bodies: list[Any] = []
    for client in clients:
        params = resolve_user_placeholder(request["params"], client.user_id)
        payload = resolve_user_placeholder(request["json_body"], client.user_id)
        response = client.request(
            request["method"], request["path"], params=params, payload=payload,
            authenticate=True, expected=range(100, 600),
        )
        responses.append(response)
        bodies.append(_body(response))

    endpoint = f"{request['method']} {request['path']}"
    mapping = _item_mapping(*bodies) if endpoint == "GET /Items" else {}
    normalized = [
        normalizer.normalize(body, endpoint=endpoint, state_mapping=mapping)
        for body in bodies
    ]
    diffs = SemanticDiffEngine().compare_responses(
        v1_status=responses[0].status_code,
        v2_status=responses[1].status_code,
        v1_headers={},
        v2_headers={},
        v1_body=normalized[0],
        v2_body=normalized[1],
    )
    return sorted(
        (signature_from_diff(diff) for diff in diffs),
        key=lambda signature: (signature["category"], signature["path"]),
    )


def summarize_attempts(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Invalid attempts are excluded from the denominator, never hidden."""
    reproduced = sum(run["outcome"] == "reproduced" for run in attempts)
    not_reproduced = sum(run["outcome"] == "not_reproduced" for run in attempts)
    invalid = sum(run["outcome"] == "invalid" for run in attempts)
    valid = reproduced + not_reproduced
    return {
        "attempts_requested": len(attempts),
        "valid_runs": valid,
        "reproduced": reproduced,
        "not_reproduced": not_reproduced,
        "invalid": invalid,
        "failure_reproduction_rate": reproduced / valid if valid else None,
    }


def replay_record(
    record: dict[str, Any],
    runs: int,
    *,
    probe: Callable[[], dict[str, Any]],
    observe: Callable[[dict[str, Any]], list[dict[str, str]]],
    reset_state: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Run independently and count only matching failure signatures."""
    validate_record(record)
    if type(runs) is not int or runs < 1:
        raise ReplayRecordError("runs must be a positive integer")
    if "seed_state_sha256" not in record["environment"]:
        raise ReplayRecordError("Live seed state fingerprint is missing")
    if record["request"]["method"] != "GET" and reset_state is None:
        raise ReplayRecordError("Mutating requests require a state reset hook")

    attempts: list[dict[str, Any]] = []
    target = record["failure_signature"]
    for number in range(1, runs + 1):
        try:
            if reset_state is not None:
                reset_state()
            if probe() != record["environment"]:
                raise ReplayEnvironmentError("Environment fingerprint mismatch")
            observed = observe(record["request"])
            matched = any(
                all(signature.get(key) == value for key, value in target.items())
                for signature in observed
            )
            attempts.append({
                "number": number,
                "outcome": "reproduced" if matched else "not_reproduced",
                "observed_signatures": observed,
            })
        except ReplayEnvironmentError as exc:
            attempts.append({"number": number, "outcome": "invalid", "reason": str(exc)})

    return {
        "task": "G2-23A",
        "test_id": record["test_id"],
        "seed": record["seed"],
        "request_input_sha256": record["request_input_sha256"],
        "target_signature": target,
        **summarize_attempts(attempts),
        "attempts": attempts,
    }


def _clients(args: argparse.Namespace) -> tuple[JellyfinClient, JellyfinClient]:
    password = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456")
    clients = (
        JellyfinClient(Server("v10.8.13", args.v108_url.rstrip("/")), args.timeout),
        JellyfinClient(Server("v10.9.0", args.v109_url.rstrip("/")), args.timeout),
    )
    for client in clients:
        client.authenticate(args.username, password)
    return clients


def _write_json_once(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as target:
        json.dump(data, target, ensure_ascii=False, indent=2, sort_keys=True)
        target.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="Record an observed difference")
    capture.add_argument("--test-id", required=True)
    capture.add_argument("--seed", type=int, required=True)
    capture.add_argument("--request-file", type=Path, required=True)
    capture.add_argument("--record", type=Path, required=True)
    capture.add_argument("--target-category")
    capture.add_argument("--target-path")
    replay = subparsers.add_parser("replay", help="Measure reproduction rate")
    replay.add_argument("--record", type=Path, required=True)
    replay.add_argument("--runs", type=int, default=5)
    replay.add_argument("--report", type=Path, required=True)
    for command in (capture, replay):
        command.add_argument("--v108-url", default="http://localhost:8096")
        command.add_argument("--v109-url", default="http://localhost:8097")
        command.add_argument("--username", default="admin")
        command.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)

    try:
        record = load_record(args.record) if args.command == "replay" else None
        if args.command == "capture":
            template = json.loads(args.request_file.read_text(encoding="utf-8-sig"))
            if not isinstance(template, dict):
                raise ReplayRecordError("Request file must contain a JSON object")
            request = generate_request(template, args.seed)
            seeded_template = template if template != request else None
            # Validate credentials and request shape before any network request.
            provisional = build_reference_fingerprint()
            make_record(
                args.test_id, args.seed, request, provisional,
                {
                    "category": "PRECHECK", "path": "$",
                    "v1_sha256": "0" * 64, "v2_sha256": "0" * 64,
                },
                request_template=seeded_template,
            )
        else:
            assert record is not None
            request = record["request"]
        if request["method"] != "GET":
            raise ReplayRecordError("CLI supports GET only; mutation requires reset")

        clients = _clients(args)
        normalizer = SemanticNormalizer.from_file(
            ROOT / "config" / "normalization-rules.json"
        )

        if args.command == "capture":
            environment = probe_environment(clients)
            signatures = observe_differences(clients, request, normalizer)
            if args.target_category:
                signatures = [
                    signature for signature in signatures
                    if signature["category"] == args.target_category
                ]
            if args.target_path:
                signatures = [
                    signature for signature in signatures
                    if signature["path"] == args.target_path
                ]
            if len(signatures) != 1:
                raise ReplayRecordError(
                    f"Expected exactly one target difference, found {len(signatures)}; "
                    "use --target-category and --target-path"
                )
            record = make_record(
                args.test_id, args.seed, request, environment, signatures[0],
                request_template=seeded_template,
            )
            save_record(args.record, record)
            print(f"Captured {record['test_id']} at {args.record}")
            return 0

        assert record is not None

        def checked_probe() -> dict[str, Any]:
            try:
                return probe_environment(clients)
            except (ReplayRecordError, SetupError, requests.RequestException, OSError) as exc:
                raise ReplayEnvironmentError(type(exc).__name__) from exc

        def checked_observe(value: dict[str, Any]) -> list[dict[str, str]]:
            try:
                return observe_differences(clients, value, normalizer)
            except (SetupError, requests.RequestException) as exc:
                raise ReplayEnvironmentError(type(exc).__name__) from exc

        result = replay_record(
            record, args.runs, probe=checked_probe, observe=checked_observe
        )
        _write_json_once(args.report, result)
        rate = result["failure_reproduction_rate"]
        if rate is None:
            print(f"{record['test_id']}: no valid runs; rate unavailable")
        else:
            print(
                f"{record['test_id']}: {result['reproduced']}/{result['valid_runs']} "
                f"valid runs reproduced ({rate:.1%})"
            )
        print(f"Report: {args.report}")
        return 0 if rate is not None else 2
    except (
        ReplayRecordError, ReplayEnvironmentError, SetupError,
        requests.RequestException, OSError, ValueError,
    ) as exc:
        print(f"G2-23A failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
