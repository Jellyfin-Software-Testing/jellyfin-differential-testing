"""Unit tests for the G2-23A record format; no live Jellyfin is required."""

from copy import deepcopy
import hashlib

import pytest

from scripts.G2_23A_replay_record import (
    ReplayRecordError,
    build_reference_fingerprint,
    file_sha256,
    generate_request,
    load_record,
    make_record,
    request_input_sha256,
    save_record,
    validate_record,
)


@pytest.fixture
def example_record(tmp_path):
    manifest = tmp_path / "manifest.json"
    rules = tmp_path / "rules.json"
    parity = tmp_path / "parity.json"
    manifest.write_text('{"files": []}', encoding="utf-8")
    rules.write_text('{"rules": []}', encoding="utf-8")
    parity.write_text('{"status": "equivalent"}', encoding="utf-8")
    environment = build_reference_fingerprint(manifest, rules, parity)
    return make_record(
        test_id="G2-23A-synthetic-example",
        seed=42,
        request={
            "method": "GET",
            "path": "/Items",
            "params": {"IncludeItemTypes": "Audio", "Limit": 2},
            "json_body": None,
        },
        environment=environment,
        failure_signature={
            "category": "VALUE_MISMATCH", "path": "$.Items[0].Name",
            "v1_sha256": "a" * 64, "v2_sha256": "b" * 64,
        },
    )


def test_save_and_load_preserve_replay_inputs(tmp_path, example_record):
    target = tmp_path / "evidence" / "replay.json"
    save_record(target, example_record)

    loaded = load_record(target)
    assert loaded == example_record
    assert loaded["seed"] == 42
    assert loaded["request"]["params"]["Limit"] == 2
    assert loaded["failure_signature"]["path"] == "$.Items[0].Name"
    assert loaded["request_input_sha256"] == request_input_sha256(
        loaded["test_id"], loaded["seed"], loaded["request"]
    )
    with pytest.raises(FileExistsError):
        save_record(target, example_record)


@pytest.mark.parametrize(
    "missing", ["test_id", "seed", "request", "environment", "failure_signature"]
)
def test_missing_required_field_is_rejected(example_record, missing):
    record = deepcopy(example_record)
    del record[missing]
    with pytest.raises(ReplayRecordError):
        validate_record(record)


@pytest.mark.parametrize("bad_field", ["Password", "X-Emby-Token", "AccessToken"])
def test_request_secrets_are_rejected(example_record, bad_field):
    record = deepcopy(example_record)
    record["request"]["params"][bad_field] = "do-not-save-this"
    with pytest.raises(ReplayRecordError, match="secret field"):
        validate_record(record)


def test_nested_body_secret_and_headers_are_rejected(example_record):
    record = deepcopy(example_record)
    record["request"]["json_body"] = {"user": {"Pw": "secret"}}
    with pytest.raises(ReplayRecordError, match="secret field"):
        validate_record(record)

    record = deepcopy(example_record)
    record["request"]["headers"] = {"Accept": "application/json"}
    with pytest.raises(ReplayRecordError, match="headers"):
        validate_record(record)


def test_file_fingerprint_changes_when_input_changes(tmp_path):
    source = tmp_path / "manifest.json"
    source.write_bytes(b"first")
    first = file_sha256(source)
    assert first == hashlib.sha256(b"first").hexdigest()
    source.write_bytes(b"second")
    assert file_sha256(source) != first


def test_reference_fingerprint_requires_equivalent_g1_report(tmp_path):
    manifest = tmp_path / "manifest.json"
    rules = tmp_path / "rules.json"
    parity = tmp_path / "parity.json"
    manifest.write_text("{}", encoding="utf-8")
    rules.write_text("{}", encoding="utf-8")
    parity.write_text('{"status": "different"}', encoding="utf-8")

    with pytest.raises(ReplayRecordError, match="equivalent"):
        build_reference_fingerprint(manifest, rules, parity)


def test_non_json_and_invalid_path_are_rejected(example_record):
    record = deepcopy(example_record)
    record["request"]["json_body"] = {"invalid": float("nan")}
    with pytest.raises(ReplayRecordError, match="valid JSON"):
        validate_record(record)

    record = deepcopy(example_record)
    record["request"]["path"] = "https://example.com/Items"
    with pytest.raises(ReplayRecordError, match="relative API path"):
        validate_record(record)


def test_boolean_schema_or_seed_is_not_an_integer(example_record):
    record = deepcopy(example_record)
    record["schema_version"] = True
    with pytest.raises(ReplayRecordError, match="schema_version"):
        validate_record(record)

    record = deepcopy(example_record)
    record["seed"] = False
    with pytest.raises(ReplayRecordError, match="seed"):
        validate_record(record)


def test_load_rejects_invalid_json(tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ReplayRecordError, match="Cannot read replay record"):
        load_record(target)


def test_seed_or_payload_tampering_is_rejected(example_record):
    changed_seed = deepcopy(example_record)
    changed_seed["seed"] = 43
    with pytest.raises(ReplayRecordError, match="changed after capture"):
        validate_record(changed_seed)

    changed_payload = deepcopy(example_record)
    changed_payload["request"]["params"]["Limit"] = 1
    with pytest.raises(ReplayRecordError, match="changed after capture"):
        validate_record(changed_payload)


def test_failure_signature_requires_exact_value_hashes(example_record):
    missing = deepcopy(example_record)
    del missing["failure_signature"]["v2_sha256"]
    with pytest.raises(ReplayRecordError, match="both value hashes"):
        validate_record(missing)

    malformed = deepcopy(example_record)
    malformed["failure_signature"]["v1_sha256"] = "not-a-sha256"
    with pytest.raises(ReplayRecordError, match="SHA-256 hex"):
        validate_record(malformed)


def test_seed_regenerates_exact_choice_payload(example_record):
    template = {
        "method": "GET", "path": "/Items",
        "params": {"Limit": {"$choice": [1, 2, 3]}},
        "json_body": None,
    }
    generated = generate_request(template, 42)
    assert generate_request(template, 42) == generated
    record = make_record(
        "G2-23A-seeded", 42, generated, example_record["environment"],
        example_record["failure_signature"], request_template=template,
    )
    validate_record(record)
    changed_template = deepcopy(record)
    changed_template["request_template"]["params"]["Limit"] = {"$choice": [99]}
    with pytest.raises(ReplayRecordError, match="Seed no longer generates"):
        validate_record(changed_template)


def test_empty_choice_is_rejected():
    with pytest.raises(ReplayRecordError, match="non-empty list"):
        generate_request({"params": {"Limit": {"$choice": []}}}, 10)
