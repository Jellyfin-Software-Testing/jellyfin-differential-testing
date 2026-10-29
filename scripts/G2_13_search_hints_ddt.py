#!/usr/bin/env python3
"""Run manifest-driven differential tests for Jellyfin Search Hints."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizer.G2_07_diff_engine import SemanticDiffEngine
from normalizer.semantic_normalizer import SemanticNormalizer
from scripts.G1_06_setup_and_verify import SetupError


@dataclass(frozen=True)
class ResponseSnapshot:
    status_code: int
    headers: Mapping[str, str]
    body: Any
    error: str | None = None


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SetupError(f"manifest {path}: root must be an object")
    return data


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def validate_search_hint_cases(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_cases = manifest.get("searchHintCases")
    if not isinstance(raw_cases, list):
        raise SetupError("manifest.searchHintCases must be a list")
    if not raw_cases:
        raise SetupError("manifest.searchHintCases must not be empty")

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise SetupError(f"manifest.searchHintCases[{index}] must be an object")
        case_id = raw_case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise SetupError(f"manifest.searchHintCases[{index}].id must be non-empty")
        if case_id in seen:
            raise SetupError(f"duplicate search hint case id: {case_id}")
        seen.add(case_id)
        params = raw_case.get("params")
        if not isinstance(params, dict):
            raise SetupError(f"manifest.searchHintCases[{index}].params must be an object")
        for key, value in params.items():
            if not isinstance(key, str):
                raise SetupError(f"manifest.searchHintCases[{index}].params keys must be strings")
            if not _is_scalar(value) and not (
                isinstance(value, list) and all(_is_scalar(item) for item in value)
            ):
                raise SetupError(
                    f"manifest.searchHintCases[{index}].params.{key} must be scalar or list of scalars"
                )
        validated.append({"id": case_id, "params": dict(params)})
    return validated


def parse_response(response: Any) -> Any:
    content_type = next(
        (value for key, value in response.headers.items() if key.lower() == "content-type"),
        "",
    ).lower()
    if "json" not in content_type:
        return response.text
    try:
        return response.json()
    except (ValueError, TypeError) as exc:
        raise SetupError(f"invalid JSON response: {exc}") from exc


def compare_case(
    case: Mapping[str, Any],
    v108: ResponseSnapshot,
    v109: ResponseSnapshot,
    normalizer: SemanticNormalizer,
) -> list[dict[str, Any]]:
    body_v108 = normalizer.normalize(v108.body, "GET /Search/Hints")
    body_v109 = normalizer.normalize(v109.body, "GET /Search/Hints")
    diffs = SemanticDiffEngine().compare_responses(
        v1_status=v108.status_code,
        v2_status=v109.status_code,
        v1_headers=dict(v108.headers),
        v2_headers=dict(v109.headers),
        v1_body=body_v108,
        v2_body=body_v109,
    )
    return [diff.to_dict() for diff in diffs]


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def request_case(client: Any, case: Mapping[str, Any]) -> ResponseSnapshot:
    response = client.request(
        "GET",
        "/Search/Hints",
        params=dict(case["params"]),
        authenticate=True,
        expected=tuple(range(200, 600)),
    )
    headers = dict(response.headers)
    try:
        body = parse_response(response)
    except SetupError as exc:
        return ResponseSnapshot(response.status_code, headers, response.text, str(exc))
    return ResponseSnapshot(response.status_code, headers, body)


def require_g1_parity(path: Path) -> None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"cannot read G1-06 evidence {path}: {exc}") from exc
    if not isinstance(report, dict):
        raise SetupError("G1-06 evidence root must be an object")
    if report.get("status") != "equivalent":
        raise SetupError("G1-06 initial-state evidence is not equivalent")


def _snapshot_dict(
    snapshot: ResponseSnapshot, normalizer: SemanticNormalizer
) -> dict[str, Any]:
    return {
        "status_code": snapshot.status_code,
        "headers": dict(snapshot.headers),
        "body": normalizer.normalize(snapshot.body, "GET /Search/Hints"),
        **({"error": snapshot.error} if snapshot.error else {}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G2-13 Search Hints differential test")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "dataset-manifest.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "evidence" / "G2-13-search-hints-ddt.json")
    parser.add_argument("--g1-report", type=Path, default=ROOT / "docs" / "evidence" / "G1-06-initial-state-parity.json")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"))
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)

    report: dict[str, Any] = {"task": "G2-13", "status": "failed", "cases": []}
    try:
        cases = validate_search_hint_cases(load_manifest(args.manifest))
        require_g1_parity(args.g1_report)
        from scripts.G1_06_setup_and_verify import JellyfinClient, Server

        clients = [
            JellyfinClient(Server("v10.8.13", "http://localhost:8096"), args.timeout),
            JellyfinClient(Server("v10.9.0", "http://localhost:8097"), args.timeout),
        ]
        for client in clients:
            client.authenticate(args.username, args.password)
        normalizer = SemanticNormalizer.from_file(ROOT / "config" / "normalization-rules.json")
        for case in cases:
            snapshots: list[ResponseSnapshot] = []
            try:
                for client in clients:
                    snapshot = request_case(client, case)
                    snapshots.append(snapshot)
                    if snapshot.error:
                        raise SetupError(snapshot.error)
            except (SetupError, requests.RequestException, OSError, ValueError) as exc:
                entry: dict[str, Any] = {"id": case["id"], "params": case["params"], "error": str(exc)}
                if snapshots:
                    entry["v108"] = _snapshot_dict(snapshots[0], normalizer)
                if len(snapshots) > 1:
                    entry["v109"] = _snapshot_dict(snapshots[1], normalizer)
                report["cases"].append(entry)
                raise
            entry = {
                "id": case["id"],
                "params": case["params"],
                "v108": _snapshot_dict(snapshots[0], normalizer),
                "v109": _snapshot_dict(snapshots[1], normalizer),
                "diffs": [],
            }
            report["cases"].append(entry)
            allowed_statuses = {200, 400, 500} if case["id"] in {"empty-term", "missing-term"} else {200}
            unexpected = [
                snapshot.status_code
                for snapshot in snapshots
                if snapshot.status_code not in allowed_statuses
            ]
            if unexpected:
                entry["error"] = f"unexpected HTTP status: {unexpected}"
                raise SetupError(entry["error"])
            try:
                entry["diffs"] = compare_case(case, snapshots[0], snapshots[1], normalizer)
            except (SetupError, ValueError) as exc:
                entry["error"] = str(exc)
                raise
        report["status"] = "equivalent" if all(not case["diffs"] for case in report["cases"]) else "failed"
        return 0 if report["status"] == "equivalent" else 1
    except (SetupError, requests.RequestException, OSError, ValueError) as exc:
        report["error"] = str(exc)
        return 1
    finally:
        write_report(args.report, report)


if __name__ == "__main__":
    raise SystemExit(main())
