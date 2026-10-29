"""Store the inputs needed to reproduce one differential-test failure.

This module records a *reference* environment fingerprint from local files.
It does not prove that the currently running Jellyfin servers match it; the
replay runner must check the live servers before making requests.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = {
    "authorization", "xembyauthorization", "xembytoken", "accesstoken",
    "apikey", "password", "passwd", "pwd", "pw", "secret", "token",
}


class ReplayRecordError(ValueError):
    """The saved replay input is incomplete, unsafe, or malformed."""


def file_sha256(path: str | Path) -> str:
    """Hash file contents rather than a machine-specific absolute path."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    """Hash JSON data with stable key order and no non-JSON float values."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_input_sha256(
    test_id: str, seed: int, request: dict[str, Any],
    request_template: dict[str, Any] | None = None,
) -> str:
    """Bind TestID, seed, and the exact request into one replay identity."""
    return canonical_sha256({
        "test_id": test_id, "seed": seed, "request": request,
        "request_template": request_template,
    })


def generate_request(template: dict[str, Any], seed: int) -> dict[str, Any]:
    """Resolve {$choice: [...]} values with a private, seeded RNG.

    The exact result is saved alongside the template, so replay can prove that
    the seed regenerates the recorded payload before any network request.
    """
    if type(seed) is not int or not isinstance(template, dict):
        raise ReplayRecordError("Request generation needs an object and integer seed")
    rng = random.Random(seed)

    def resolve(value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"$choice"}:
            choices = value["$choice"]
            if not isinstance(choices, list) or not choices:
                raise ReplayRecordError("$choice must contain a non-empty list")
            return resolve(rng.choice(choices))
        if isinstance(value, dict):
            return {key: resolve(child) for key, child in value.items()}
        if isinstance(value, list):
            return [resolve(child) for child in value]
        return value

    generated = resolve(template)
    try:
        canonical_sha256(generated)
    except (TypeError, ValueError) as exc:
        raise ReplayRecordError(f"Generated request is not valid JSON: {exc}") from exc
    return generated


def build_reference_fingerprint(
    manifest: str | Path = ROOT / "data" / "dataset-manifest.json",
    rules: str | Path = ROOT / "config" / "normalization-rules.json",
    parity_report: str | Path = ROOT / "docs" / "evidence" / "G1-06-initial-state-parity.json",
) -> dict[str, Any]:
    """Identify the versioned inputs and prior G1-06 parity evidence.

    This is not a live-server health or state check. Replay must do that later.
    """
    try:
        parity = json.loads(Path(parity_report).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ReplayRecordError(f"Cannot read G1-06 parity report: {exc}") from exc
    if not isinstance(parity, dict) or parity.get("status") != "equivalent":
        raise ReplayRecordError("G1-06 parity report must have status 'equivalent'")

    return {
        "expected_versions": {"baseline": "10.8.13", "candidate": "10.9.0"},
        "seed_manifest_sha256": file_sha256(manifest),
        "normalization_rules_sha256": file_sha256(rules),
        "initial_state_evidence_sha256": file_sha256(parity_report),
    }


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ReplayRecordError("JSON object keys must be strings")
            normalized = "".join(character for character in key.lower() if character.isalnum())
            if normalized in SECRET_KEYS or "password" in normalized or "token" in normalized:
                raise ReplayRecordError(f"Replay record must not contain secret field {key!r}")
            _reject_secret_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_keys(child)


def validate_record(record: Any) -> None:
    """Reject incomplete records and accidental credential capture."""
    if (
        not isinstance(record, dict)
        or type(record.get("schema_version")) is not int
        or record["schema_version"] != SCHEMA_VERSION
    ):
        raise ReplayRecordError("Unsupported or missing replay schema_version")
    if not isinstance(record.get("test_id"), str) or not record["test_id"].strip():
        raise ReplayRecordError("test_id must be a non-empty string")
    if type(record.get("seed")) is not int:
        raise ReplayRecordError("seed must be an integer")

    request = record.get("request")
    if not isinstance(request, dict):
        raise ReplayRecordError("request must be an object")
    if request.get("method") not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ReplayRecordError("request.method is unsupported")
    path = request.get("path")
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path.startswith("//")
        or "?" in path
    ):
        raise ReplayRecordError("request.path must be a relative API path without query string")
    if not isinstance(request.get("params"), dict) or "json_body" not in request:
        raise ReplayRecordError("request needs params object and json_body field")
    if "headers" in request:
        raise ReplayRecordError("Do not save headers; replay obtains authentication separately")

    environment = record.get("environment")
    if not isinstance(environment, dict):
        raise ReplayRecordError("environment must be an object")
    versions = environment.get("expected_versions")
    if not isinstance(versions, dict) or not all(
        isinstance(versions.get(side), str) and versions[side]
        for side in ("baseline", "candidate")
    ):
        raise ReplayRecordError("environment needs both expected server versions")
    for name in (
        "seed_manifest_sha256", "normalization_rules_sha256",
        "initial_state_evidence_sha256",
    ):
        value = environment.get(name)
        if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ReplayRecordError(f"environment.{name} must be a SHA-256 hex digest")
    live_seed_hash = environment.get("seed_state_sha256")
    if live_seed_hash is not None and (
        not isinstance(live_seed_hash, str)
        or len(live_seed_hash) != 64
        or any(character not in "0123456789abcdef" for character in live_seed_hash)
    ):
        raise ReplayRecordError("environment.seed_state_sha256 must be SHA-256 hex")

    signature = record.get("failure_signature")
    if (
        not isinstance(signature, dict)
        or set(signature) != {"category", "path", "v1_sha256", "v2_sha256"}
        or not all(
            isinstance(signature.get(key), str) and signature[key].strip()
            for key in ("category", "path")
        )
    ):
        raise ReplayRecordError(
            "failure_signature needs category, path, and both value hashes"
        )
    for side in ("v1_sha256", "v2_sha256"):
        digest = signature[side]
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ReplayRecordError(f"failure_signature.{side} must be SHA-256 hex")

    _reject_secret_keys(record)
    try:
        json.dumps(record, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReplayRecordError(f"Replay record is not valid JSON data: {exc}") from exc
    template = record.get("request_template")
    if template is not None and generate_request(template, record["seed"]) != request:
        raise ReplayRecordError("Seed no longer generates the recorded request")
    if record.get("request_input_sha256") != request_input_sha256(
        record["test_id"], record["seed"], request, template
    ):
        raise ReplayRecordError("TestID, seed, or request changed after capture")


def make_record(
    test_id: str,
    seed: int,
    request: dict[str, Any],
    environment: dict[str, Any],
    failure_signature: dict[str, str],
    *,
    request_template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a record from an observed failure; never invent its signature."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "test_id": test_id,
        "seed": seed,
        "request": request,
        "request_input_sha256": request_input_sha256(
            test_id, seed, request, request_template
        ),
        "environment": environment,
        "failure_signature": failure_signature,
    }
    if request_template is not None:
        record["request_template"] = request_template
    validate_record(record)
    return record


def save_record(path: str | Path, record: dict[str, Any]) -> None:
    """Write once so an existing failure record is not silently replaced."""
    validate_record(record)
    target = Path(path)
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as destination:
        destination.write(payload + "\n")


def load_record(path: str | Path) -> dict[str, Any]:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ReplayRecordError(f"Cannot read replay record: {exc}") from exc
    validate_record(record)
    return record
