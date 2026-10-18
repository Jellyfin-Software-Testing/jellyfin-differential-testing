"""G2-23A replay tests use fake transports; no Docker server is needed."""

from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from normalizer import SemanticNormalizer
from normalizer.G2_07_diff_engine import DiffCategory, DiffItem
from scripts.G2_23A_replay import (
    ReplayEnvironmentError,
    configuration_snapshot,
    main,
    observe_differences,
    replay_record,
    seed_snapshot,
    signature_from_diff,
    summarize_attempts,
)
from scripts.G2_23A_replay_record import ReplayRecordError, make_record


@pytest.fixture
def environment():
    return {
        "expected_versions": {"baseline": "10.8.13", "candidate": "10.9.0"},
        "seed_manifest_sha256": "a" * 64,
        "normalization_rules_sha256": "b" * 64,
        "initial_state_evidence_sha256": "c" * 64,
        "seed_state_sha256": "d" * 64,
    }


@pytest.fixture
def signature():
    return {
        "category": "VALUE_MISMATCH",
        "path": "$.Version",
        "v1_sha256": "e" * 64,
        "v2_sha256": "f" * 64,
    }


@pytest.fixture
def record(environment, signature):
    return make_record(
        "G2-23A-synthetic-version", 42,
        {"method": "GET", "path": "/System/Info/Public", "params": {}, "json_body": None},
        environment, signature,
    )


def test_seed_snapshot_matches_manifest_without_server_ids():
    manifest = {
        "library": {
            "name": "Differential Seed Music", "collectionType": "music",
            "paths": ["/media/seed-music"],
        },
        "files": [{"relativePath": "seed-music/01 - Reference Tone.wav", "durationSeconds": 1}],
    }
    folders = [{
        "Name": "Differential Seed Music", "CollectionType": "music",
        "Locations": ["/media/seed-music"], "ItemId": "server-specific-id",
    }]
    items = [{
        "Id": "another-id", "Name": "01 - Reference Tone",
        "Type": "Audio", "RunTimeTicks": 10_000_000,
    }]

    snapshot = seed_snapshot(manifest, folders, items, "v10.8")
    assert snapshot["items"] == [{
        "Name": "01 - Reference Tone", "Type": "Audio",
        "RunTimeTicks": 10_000_000,
    }]
    assert "server-specific-id" not in json.dumps(snapshot)

    with pytest.raises(ReplayEnvironmentError, match="duration changed"):
        seed_snapshot(manifest, folders, [{**items[0], "RunTimeTicks": 1}], "v10.8")
    with pytest.raises(ReplayEnvironmentError, match="expected one seed item"):
        seed_snapshot(manifest, folders, items + [items[0]], "v10.8")


def test_configuration_snapshot_rejects_changed_g1_settings():
    manifest = {"startup": {
        "serverName": "Jellyfin Differential Test", "uiCulture": "en-US",
        "metadataCountryCode": "US", "preferredMetadataLanguage": "en",
    }}
    config = {
        "ServerName": "Jellyfin Differential Test", "UICulture": "en-US",
        "MetadataCountryCode": "US", "PreferredMetadataLanguage": "en",
    }
    assert configuration_snapshot(manifest, config, "v10.8")["ServerName"] == config["ServerName"]
    with pytest.raises(ReplayEnvironmentError, match="configuration changed"):
        configuration_snapshot(manifest, {**config, "ServerName": "other"}, "v10.8")


def test_signature_hashes_values_without_exposing_them():
    diff = DiffItem(DiffCategory.VALUE_MISMATCH, "$.Version", "secret-a", "secret-b", "changed")
    signature = signature_from_diff(diff)
    assert signature["category"] == "VALUE_MISMATCH"
    assert signature["path"] == "$.Version"
    assert len(signature["v1_sha256"]) == 64
    assert "secret-a" not in json.dumps(signature)


def test_observe_uses_server_specific_user_ids_and_normalizes_item_ids():
    class FakeResponse:
        status_code = 200

        def __init__(self, item_id):
            self.payload = {
                "Items": [{
                    "Id": item_id, "Name": "01 - Reference Tone",
                    "Type": "Audio", "RunTimeTicks": 10_000_000,
                }],
                "TotalRecordCount": 1,
            }
            self.content = json.dumps(self.payload).encode()

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, user_id, item_id):
            self.user_id = user_id
            self.item_id = item_id
            self.params = None

        def request(self, method, path, **kwargs):
            assert (method, path) == ("GET", "/Items")
            self.params = kwargs["params"]
            return FakeResponse(self.item_id)

    clients = (FakeClient("admin-108", "item-108"), FakeClient("admin-109", "item-109"))
    request = {
        "method": "GET", "path": "/Items",
        "params": {"UserId": "$AUTH_USER", "IncludeItemTypes": "Audio"},
        "json_body": None,
    }
    rules = Path(__file__).resolve().parents[1] / "config" / "normalization-rules.json"
    assert observe_differences(clients, request, SemanticNormalizer.from_file(rules)) == []
    assert clients[0].params["UserId"] == "admin-108"
    assert clients[1].params["UserId"] == "admin-109"


def test_rate_excludes_invalid_runs_and_requires_same_signature(record, signature):
    observed = iter([[signature], [], [signature], [signature]])
    probes = iter([
        record["environment"], record["environment"], record["environment"],
        {**record["environment"], "seed_state_sha256": "0" * 64},
        record["environment"],
    ])
    report = replay_record(
        record, 5, probe=lambda: next(probes), observe=lambda _: next(observed),
    )
    assert (report["reproduced"], report["not_reproduced"], report["invalid"]) == (3, 1, 1)
    assert report["valid_runs"] == 4
    assert report["failure_reproduction_rate"] == 0.75
    assert [run["outcome"] for run in report["attempts"]] == [
        "reproduced", "not_reproduced", "reproduced", "invalid", "reproduced",
    ]


def test_different_value_at_same_path_is_not_reproduced(record, signature):
    different = {**signature, "v2_sha256": "0" * 64}
    report = replay_record(
        record, 1, probe=lambda: record["environment"], observe=lambda _: [different],
    )
    assert report["failure_reproduction_rate"] == 0.0
    assert report["not_reproduced"] == 1


def test_no_valid_runs_has_no_numeric_rate(record):
    def fail_probe():
        raise ReplayEnvironmentError("Environment fingerprint mismatch")

    report = replay_record(record, 2, probe=fail_probe, observe=lambda _: [])
    assert report["invalid"] == 2
    assert report["valid_runs"] == 0
    assert report["failure_reproduction_rate"] is None
    assert summarize_attempts(report["attempts"])["attempts_requested"] == 2


def test_mutation_cannot_replay_without_reset_hook(record):
    mutation = make_record(
        record["test_id"], record["seed"],
        {"method": "POST", "path": "/Items", "params": {}, "json_body": {}},
        record["environment"], record["failure_signature"],
    )
    with pytest.raises(ReplayRecordError, match="state reset hook"):
        replay_record(mutation, 2, probe=lambda: mutation["environment"], observe=lambda _: [])

    resets = []
    report = replay_record(
        mutation, 2, probe=lambda: mutation["environment"],
        observe=lambda _: [], reset_state=lambda: resets.append(True),
    )
    assert len(resets) == 2
    assert report["not_reproduced"] == 2


def test_replay_rejects_missing_live_fingerprint(record):
    missing = deepcopy(record)
    del missing["environment"]["seed_state_sha256"]
    with pytest.raises(ReplayRecordError, match="Live seed state fingerprint"):
        replay_record(missing, 1, probe=lambda: {}, observe=lambda _: [])


def test_capture_and_replay_cli_with_fake_observations(
    tmp_path, monkeypatch, environment, signature,
):
    import scripts.G2_23A_replay as runner

    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "method": "GET", "path": "/System/Info/Public", "params": {}, "json_body": None,
    }), encoding="utf-8")
    record_path = tmp_path / "record.json"
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(runner, "_clients", lambda _: (object(), object()))
    monkeypatch.setattr(runner, "probe_environment", lambda _: environment)
    monkeypatch.setattr(runner, "observe_differences", lambda *_: [signature])

    assert main([
        "capture", "--test-id", "G2-23A-synthetic-version", "--seed", "42",
        "--request-file", str(request_file), "--record", str(record_path),
    ]) == 0
    assert main([
        "replay", "--record", str(record_path), "--runs", "3", "--report", str(report_path),
    ]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["failure_reproduction_rate"] == 1.0
    assert report["reproduced"] == 3
    assert report["seed"] == 42
    assert "AccessToken" not in report_path.read_text(encoding="utf-8")


def test_runner_help_starts_from_repository_root():
    runner = Path(__file__).resolve().parents[1] / "scripts" / "G2_23A_replay.py"
    result = subprocess.run(
        [sys.executable, str(runner), "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "capture" in result.stdout
    assert "replay" in result.stdout
