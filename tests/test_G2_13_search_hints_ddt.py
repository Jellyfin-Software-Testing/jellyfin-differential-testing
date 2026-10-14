import json
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from scripts.G2_13_search_hints_ddt import (
    ResponseSnapshot,
    compare_case,
    load_manifest,
    parse_response,
    request_case,
    _snapshot_dict,
    validate_search_hint_cases,
    write_report,
)
from scripts.G1_06_setup_and_verify import SetupError
from normalizer.semantic_normalizer import SemanticNormalizer


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "dataset-manifest.json"


def test_manifest_contains_expected_search_hint_case_classes():
    cases = validate_search_hint_cases(load_manifest(MANIFEST))
    ids = {case["id"] for case in cases}

    assert {
        "valid-reference",
        "empty-term",
        "missing-term",
        "single-character",
        "length-255",
        "length-1000",
        "unicode",
        "control-characters",
        "injection-like",
        "html-like",
    } <= ids


def test_missing_and_empty_search_terms_remain_distinct():
    cases = validate_search_hint_cases(load_manifest(MANIFEST))
    by_id = {case["id"]: case["params"] for case in cases}

    assert "searchTerm" not in by_id["missing-term"]
    assert by_id["empty-term"]["searchTerm"] == ""


def test_manifest_preserves_special_input_values():
    cases = validate_search_hint_cases(load_manifest(MANIFEST))
    by_id = {
        case["id"]: case["params"]["searchTerm"]
        for case in cases
        if "searchTerm" in case["params"]
    }

    assert any(ord(char) > 127 for char in by_id["unicode"])
    assert "\n" in by_id["control-characters"]
    assert "OR" in by_id["injection-like"]
    assert "<script>" in by_id["html-like"]
    assert len(by_id["length-255"]) == 255
    assert len(by_id["length-1000"]) == 1000


def test_manifest_validation_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"searchHintCases": [{"id": "same", "params": {}}, {"id": "same", "params": {}}]}),
        encoding="utf-8",
    )

    with pytest.raises(SetupError, match="duplicate"):
        validate_search_hint_cases(load_manifest(path))


def test_manifest_validation_rejects_empty_case_list():
    with pytest.raises(RuntimeError, match="must not be empty"):
        validate_search_hint_cases({"searchHintCases": []})


def test_g1_parity_rejects_non_object_report(tmp_path):
    from scripts.G2_13_search_hints_ddt import require_g1_parity

    path = tmp_path / "g1.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(SetupError, match="root must be an object"):
        require_g1_parity(path)


class FakeResponse:
    def __init__(self, body, content_type="application/json"):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self.text = body if isinstance(body, str) else ("invalid" if isinstance(body, Exception) else json.dumps(body))
        self.status_code = 200

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_parse_response_uses_json_or_text_content_type():
    assert parse_response(FakeResponse({"SearchHints": []})) == {"SearchHints": []}
    assert parse_response(FakeResponse("upstream", "text/plain")) == "upstream"


def test_parse_response_rejects_invalid_advertised_json():
    with pytest.raises(SetupError, match="invalid JSON"):
        parse_response(FakeResponse(ValueError("bad")))


def test_compare_case_serializes_semantic_diffs():
    normalizer = SemanticNormalizer.from_file(ROOT / "config" / "normalization-rules.json")
    diffs = compare_case(
        {"id": "case", "params": {"searchTerm": "Reference"}},
        ResponseSnapshot(200, {"Content-Type": "application/json"}, {"Count": 1}),
        ResponseSnapshot(200, {"Content-Type": "application/json"}, {"Count": 2}),
        normalizer,
    )

    assert diffs[0]["category"] == "VALUE_MISMATCH"
    assert diffs[0]["path"] == "$.Count"


def test_snapshot_report_body_is_normalized():
    class MarkerNormalizer:
        def normalize(self, body, endpoint):
            assert endpoint == "GET /Search/Hints"
            return {"normalized": body}

    saved = _snapshot_dict(ResponseSnapshot(200, {}, {"raw": True}), MarkerNormalizer())

    assert saved["body"] == {"normalized": {"raw": True}}


def test_write_report_creates_parent_and_persists_json(tmp_path):
    path = tmp_path / "nested" / "report.json"
    write_report(path, {"task": "G2-13", "status": "failed"})

    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "failed"


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return FakeResponse({"SearchHints": []})


def test_request_case_preserves_exact_query_params():
    client = FakeClient()
    snapshot = request_case(client, {"id": "missing-term", "params": {"limit": 10}})

    assert client.calls[0][0:2] == ("GET", "/Search/Hints")
    assert client.calls[0][2]["params"] == {"limit": 10}
    assert snapshot.status_code == 200


def test_request_case_preserves_all_manifest_query_values():
    for case in validate_search_hint_cases(load_manifest(MANIFEST)):
        client = FakeClient()
        request_case(client, case)
        assert client.calls[0][2]["params"] == case["params"]


def test_request_case_preserves_invalid_json_response_context():
    class InvalidJsonClient(FakeClient):
        def request(self, method, path, **kwargs):
            self.calls.append((method, path, kwargs))
            return FakeResponse(ValueError("bad"))

    snapshot = request_case(InvalidJsonClient(), {"id": "case", "params": {}})

    assert snapshot.status_code == 200
    assert snapshot.body == "invalid"
    assert "invalid JSON" in snapshot.error


def test_help_runs_without_contacting_servers():
    result = subprocess.run(
        [sys.executable, "scripts/g2_13_search_hints_ddt.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "G2-13" in result.stdout


def test_main_persists_failed_report_when_setup_fails(tmp_path):
    from scripts.G2_13_search_hints_ddt import main

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"searchHintCases": []}), encoding="utf-8")
    report = tmp_path / "report.json"
    result = main(["--manifest", str(manifest), "--g1-report", str(tmp_path / "missing.json"), "--report", str(report)])

    assert result != 0
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
    assert "error" in saved


def _live_inputs(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"searchHintCases": [{"id": "case", "params": {"searchTerm": "Reference"}}]}),
        encoding="utf-8",
    )
    g1_report = tmp_path / "g1.json"
    g1_report.write_text(json.dumps({"status": "equivalent"}), encoding="utf-8")
    return manifest, g1_report


def test_main_equivalent_fake_servers_write_success_report(tmp_path, monkeypatch):
    from scripts import G1_06_setup_and_verify as setup
    from scripts.G2_13_search_hints_ddt import main

    class FakeLiveClient(FakeClient):
        def __init__(self, server, timeout):
            super().__init__()
            self.server = server

        def authenticate(self, username, password):
            self.authenticated = (username, password)

    monkeypatch.setattr(setup, "JellyfinClient", FakeLiveClient)
    manifest, g1_report = _live_inputs(tmp_path)
    report = tmp_path / "report.json"

    result = main(["--manifest", str(manifest), "--g1-report", str(g1_report), "--report", str(report)])

    assert result == 0
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "equivalent"


def test_main_mismatch_returns_nonzero_and_persists_diff(tmp_path, monkeypatch):
    from scripts import G1_06_setup_and_verify as setup
    from scripts.G2_13_search_hints_ddt import main

    class FakeLiveClient(FakeClient):
        def __init__(self, server, timeout):
            super().__init__()
            self.server = server

        def authenticate(self, username, password):
            pass

        def request(self, method, path, **kwargs):
            self.calls.append((method, path, kwargs))
            count = 1 if self.server.label == "v10.8.13" else 2
            return FakeResponse({"Count": count})

    monkeypatch.setattr(setup, "JellyfinClient", FakeLiveClient)
    manifest, g1_report = _live_inputs(tmp_path)
    report = tmp_path / "report.json"

    result = main(["--manifest", str(manifest), "--g1-report", str(g1_report), "--report", str(report)])
    saved = json.loads(report.read_text(encoding="utf-8"))

    assert result == 1
    assert saved["status"] == "failed"
    assert saved["cases"][0]["diffs"][0]["path"] == "$.Count"


def test_main_request_failure_preserves_partial_case(tmp_path, monkeypatch):
    from scripts import G1_06_setup_and_verify as setup
    from scripts.G2_13_search_hints_ddt import main

    class FakeLiveClient(FakeClient):
        def __init__(self, server, timeout):
            super().__init__()
            self.server = server

        def authenticate(self, username, password):
            pass

        def request(self, method, path, **kwargs):
            if self.server.label == "v10.9.0":
                raise requests.ConnectionError("candidate unavailable")
            return FakeResponse({"SearchHints": []})

    monkeypatch.setattr(setup, "JellyfinClient", FakeLiveClient)
    manifest, g1_report = _live_inputs(tmp_path)
    report = tmp_path / "report.json"

    result = main(["--manifest", str(manifest), "--g1-report", str(g1_report), "--report", str(report)])
    saved = json.loads(report.read_text(encoding="utf-8"))

    assert result == 1
    assert saved["cases"][0]["v108"]["status_code"] == 200
    assert "candidate unavailable" in saved["cases"][0]["error"]


def test_main_preserves_case_evidence_when_comparison_raises(tmp_path, monkeypatch):
    from scripts import G1_06_setup_and_verify as setup
    from scripts import G2_13_search_hints_ddt as runner

    class FakeLiveClient(FakeClient):
        def __init__(self, server, timeout):
            super().__init__()
            self.server = server

        def authenticate(self, username, password):
            pass

    monkeypatch.setattr(setup, "JellyfinClient", FakeLiveClient)
    monkeypatch.setattr(runner, "compare_case", lambda *args: (_ for _ in ()).throw(ValueError("compare failed")))
    manifest, g1_report = _live_inputs(tmp_path)
    report = tmp_path / "report.json"

    assert runner.main(["--manifest", str(manifest), "--g1-report", str(g1_report), "--report", str(report)]) == 1
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["cases"][0]["v108"]["status_code"] == 200
    assert saved["cases"][0]["v109"]["status_code"] == 200
    assert "compare failed" in saved["cases"][0]["error"]


def test_main_rejects_matching_unexpected_http_statuses(tmp_path, monkeypatch):
    from scripts import G1_06_setup_and_verify as setup
    from scripts.G2_13_search_hints_ddt import main

    class FakeLiveClient(FakeClient):
        def __init__(self, server, timeout):
            super().__init__()
            self.server = server

        def authenticate(self, username, password):
            pass

        def request(self, method, path, **kwargs):
            response = FakeResponse({"error": "unauthorized"})
            response.status_code = 401
            return response

    monkeypatch.setattr(setup, "JellyfinClient", FakeLiveClient)
    manifest, g1_report = _live_inputs(tmp_path)
    report = tmp_path / "report.json"

    assert main(["--manifest", str(manifest), "--g1-report", str(g1_report), "--report", str(report)]) == 1
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["cases"][0]["v108"]["status_code"] == 401
    assert "unexpected HTTP status" in saved["cases"][0]["error"]


def test_main_rejects_matching_server_error_for_valid_term(tmp_path, monkeypatch):
    from scripts import G1_06_setup_and_verify as setup
    from scripts.G2_13_search_hints_ddt import main

    class FakeLiveClient(FakeClient):
        def __init__(self, server, timeout):
            super().__init__()
            self.server = server

        def authenticate(self, username, password):
            pass

        def request(self, method, path, **kwargs):
            response = FakeResponse({"error": "server"})
            response.status_code = 500
            return response

    monkeypatch.setattr(setup, "JellyfinClient", FakeLiveClient)
    manifest, g1_report = _live_inputs(tmp_path)
    report = tmp_path / "report.json"

    assert main(["--manifest", str(manifest), "--g1-report", str(g1_report), "--report", str(report)]) == 1
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert "unexpected HTTP status" in saved["cases"][0]["error"]
