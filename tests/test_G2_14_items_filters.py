from typing import Any

import pytest
from scripts.G1_06_setup_and_verify import SetupError
from scripts.G2_14_items_filters import (
    FILTER_FIELDS,
    compare_filter_values,
    limited_coverage_fields,
    normalize_filter_response,
)


def test_normalize_filter_response_preserves_optional_states():
    payload = {
        "Genres": None,
        "Years": [],
        # OfficialRatings is omitted (missing)
    }
    normalized = normalize_filter_response(payload, "v10.8.13")

    assert normalized["Genres"] == ("null", None)
    assert normalized["Years"] == ("values", [])
    assert normalized["OfficialRatings"] == ("missing", None)

    populated = {
        "Genres": ["Drama"],
        "Years": [2020],
        "OfficialRatings": ["PG-13"],
    }
    norm_populated = normalize_filter_response(populated, "v10.9.0")
    assert norm_populated["Genres"] == ("values", ["Drama"])
    assert norm_populated["Years"] == ("values", [2020])
    assert norm_populated["OfficialRatings"] == ("values", ["PG-13"])


def test_normalize_filter_response_sorts_without_deduping():
    payload = {
        "Genres": ["Drama", "Action", "Drama"],
        "Years": [2022, 2020, 2020],
        "OfficialRatings": ["R", "PG-13", "R"],
    }
    normalized = normalize_filter_response(payload, "v10.8.13")

    assert normalized["Genres"] == ("values", ["Action", "Drama", "Drama"])
    assert normalized["Years"] == ("values", [2020, 2020, 2022])
    assert normalized["OfficialRatings"] == ("values", ["PG-13", "R", "R"])


def test_normalize_filter_response_rejects_invalid_members():
    # Non-object response
    with pytest.raises(SetupError):
        normalize_filter_response("not-a-dict", "v10.8.13")

    # Non-list field
    with pytest.raises(SetupError):
        normalize_filter_response({"Genres": "Action"}, "v10.8.13")

    # Invalid member types (int in Genres)
    with pytest.raises(SetupError):
        normalize_filter_response({"Genres": [123]}, "v10.8.13")

    # Bool in Years (type(b) is int is false for strict int)
    with pytest.raises(SetupError):
        normalize_filter_response({"Years": [True]}, "v10.8.13")

    with pytest.raises(SetupError):
        normalize_filter_response({"Years": ["2020"]}, "v10.8.13")

    # Invalid member types in OfficialRatings
    with pytest.raises(SetupError):
        normalize_filter_response({"OfficialRatings": [None]}, "v10.8.13")


def test_compare_filter_values_distinguishes_missing_null_and_empty():
    state_missing = {
        "Genres": ("missing", None),
        "Years": ("values", [2020]),
        "OfficialRatings": ("values", ["PG-13"]),
    }
    state_null = {
        "Genres": ("null", None),
        "Years": ("values", [2020]),
        "OfficialRatings": ("values", ["PG-13"]),
    }
    state_empty = {
        "Genres": ("values", []),
        "Years": ("values", [2020]),
        "OfficialRatings": ("values", ["PG-13"]),
    }

    assert compare_filter_values(state_missing, state_null) == ["Genres"]
    assert compare_filter_values(state_null, state_empty) == ["Genres"]
    assert compare_filter_values(state_missing, state_empty) == ["Genres"]
    assert compare_filter_values(state_empty, state_empty) == []


def test_compare_filter_values_reports_field_mismatches():
    v108 = {
        "Genres": ("values", ["Action", "Comedy"]),
        "Years": ("values", [2020]),
        "OfficialRatings": ("values", ["PG-13"]),
    }
    v109_diff_values = {
        "Genres": ("values", ["Action", "Drama"]),
        "Years": ("values", [2020]),
        "OfficialRatings": ("values", ["PG-13"]),
    }
    v109_diff_case = {
        "Genres": ("values", ["action", "Comedy"]),
        "Years": ("values", [2020]),
        "OfficialRatings": ("values", ["PG-13"]),
    }
    v109_diff_dupes = {
        "Genres": ("values", ["Action", "Action", "Comedy"]),
        "Years": ("values", [2020]),
        "OfficialRatings": ("values", ["PG-13"]),
    }

    assert compare_filter_values(v108, v109_diff_values) == ["Genres"]
    assert compare_filter_values(v108, v109_diff_case) == ["Genres"]
    assert compare_filter_values(v108, v109_diff_dupes) == ["Genres"]
    assert compare_filter_values(v108, v108) == []


def test_limited_coverage_requires_values_on_both_servers():
    results = {
        "v10.8.13": {
            "Genres": ("values", ["Drama"]),
            "Years": ("values", []),
            "OfficialRatings": ("missing", None),
        },
        "v10.9.0": {
            "Genres": ("values", ["Drama"]),
            "Years": ("values", []),
            "OfficialRatings": ("null", None),
        },
    }
    limited = limited_coverage_fields(results)
    assert set(limited) == {"Years", "OfficialRatings"}

    # Even if one server has values, if the other is empty -> limited
    partial = {
        "v10.8.13": {
            "Genres": ("values", ["Drama"]),
            "Years": ("values", [2020]),
            "OfficialRatings": ("values", ["PG-13"]),
        },
        "v10.9.0": {
            "Genres": ("values", ["Drama"]),
            "Years": ("values", []),
            "OfficialRatings": ("values", ["PG-13"]),
        },
    }
    assert limited_coverage_fields(partial) == ["Years"]

    # Both populated -> empty limited list
    full = {
        "v10.8.13": {
            "Genres": ("values", ["Drama"]),
            "Years": ("values", [2020]),
            "OfficialRatings": ("values", ["PG-13"]),
        },
        "v10.9.0": {
            "Genres": ("values", ["Drama"]),
            "Years": ("values", [2020]),
            "OfficialRatings": ("values", ["PG-13"]),
        },
    }
    assert limited_coverage_fields(full) == []

import subprocess
import sys
from scripts.G1_06_setup_and_verify import Server
from scripts.G2_14_items_filters import (
    resolve_seed_library,
    run_differential_filters,
)


class FakeClient:
    def __init__(
        self,
        label: str,
        user_id: str | None,
        virtual_folders: object,
        filters_response: object,
    ) -> None:
        self.server = Server(label, f"http://{label}")
        self.user_id = user_id
        self.virtual_folders = virtual_folders
        self.filters_response = filters_response
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any = None,
        **kwargs: Any,
    ) -> Any:
        self.calls.append((method, path, params))
        if path == "/Library/VirtualFolders":
            return self.virtual_folders
        if path == "/Items/Filters":
            return self.filters_response
        raise NotImplementedError(path)

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        return self.request(method, path, **kwargs)


def test_resolve_seed_library_rejects_missing_or_ambiguous_library():
    client_empty = FakeClient("v10.8.13", "user1", [], {})
    with pytest.raises(SetupError, match="not found"):
        resolve_seed_library(client_empty, "Differential Seed Music")

    client_other = FakeClient("v10.8.13", "user1", [{"Name": "Movies", "ItemId": "123"}], {})
    with pytest.raises(SetupError, match="not found"):
        resolve_seed_library(client_other, "Differential Seed Music")

    client_ambiguous = FakeClient(
        "v10.8.13",
        "user1",
        [
            {"Name": "Differential Seed Music", "ItemId": "123"},
            {"Name": "Differential Seed Music", "ItemId": "456"},
        ],
        {},
    )
    with pytest.raises(SetupError, match="ambiguous|multiple"):
        resolve_seed_library(client_ambiguous, "Differential Seed Music")


def test_resolve_seed_library_rejects_missing_or_invalid_item_id():
    # missing ItemId
    c1 = FakeClient("v10.8.13", "u1", [{"Name": "Differential Seed Music"}], {})
    with pytest.raises(SetupError):
        resolve_seed_library(c1)

    # empty string ItemId
    c2 = FakeClient("v10.8.13", "u1", [{"Name": "Differential Seed Music", "ItemId": ""}], {})
    with pytest.raises(SetupError):
        resolve_seed_library(c2)

    # non-string ItemId
    c3 = FakeClient("v10.8.13", "u1", [{"Name": "Differential Seed Music", "ItemId": 12345}], {})
    with pytest.raises(SetupError):
        resolve_seed_library(c3)

    # valid
    c_ok = FakeClient("v10.8.13", "u1", [{"Name": "Differential Seed Music", "ItemId": "lib-abc"}], {})
    assert resolve_seed_library(c_ok) == "lib-abc"


def test_run_differential_filters_requires_two_clients():
    c1 = FakeClient("v10.8.13", "u1", [], {})
    with pytest.raises(SetupError):
        run_differential_filters((c1,))  # type: ignore


def test_run_differential_filters_rejects_duplicate_server_labels():
    c1 = FakeClient("v10.8.13", "u1", [{"Name": "Differential Seed Music", "ItemId": "lib1"}], {})
    c2 = FakeClient("v10.8.13", "u2", [{"Name": "Differential Seed Music", "ItemId": "lib2"}], {})
    with pytest.raises(SetupError, match="distinct server labels"):
        run_differential_filters((c1, c2))


def test_run_differential_filters_uses_per_instance_context():
    c1 = FakeClient(
        "v10.8.13",
        "user-v108",
        [{"Name": "Differential Seed Music", "ItemId": "lib-v108"}],
        {"Genres": ["Rock"], "Years": [2020], "OfficialRatings": ["PG"]},
    )
    c2 = FakeClient(
        "v10.9.0",
        "user-v109",
        [{"Name": "Differential Seed Music", "ItemId": "lib-v109"}],
        {"Genres": ["Rock"], "Years": [2020], "OfficialRatings": ["PG"]},
    )

    report = run_differential_filters((c1, c2))
    assert report["status"] == "equivalent"
    assert report["parity"] == "equivalent"
    assert report["coverage"] == "full"

    # Verify per-instance calls
    filter_calls_c1 = [call for call in c1.calls if call[1] == "/Items/Filters"]
    filter_calls_c2 = [call for call in c2.calls if call[1] == "/Items/Filters"]
    assert len(filter_calls_c1) == 1
    assert filter_calls_c1[0][2] == {"UserId": "user-v108", "ParentId": "lib-v108"}
    assert len(filter_calls_c2) == 1
    assert filter_calls_c2[0][2] == {"UserId": "user-v109", "ParentId": "lib-v109"}


def test_run_differential_filters_marks_empty_parity_limited():
    c1 = FakeClient(
        "v10.8.13",
        "u1",
        [{"Name": "Differential Seed Music", "ItemId": "lib1"}],
        {"Genres": [], "Years": [], "OfficialRatings": []},
    )
    c2 = FakeClient(
        "v10.9.0",
        "u2",
        [{"Name": "Differential Seed Music", "ItemId": "lib2"}],
        {"Genres": [], "Years": [], "OfficialRatings": []},
    )

    report = run_differential_filters((c1, c2))
    assert report["status"] == "limited_coverage"
    assert report["parity"] == "equivalent"
    assert report["coverage"] == "limited"
    assert set(report["limitedFields"]) == {"Genres", "Years", "OfficialRatings"}
    assert report["differences"] == []


def test_run_differential_filters_report_preserves_missing_null_empty():
    c1 = FakeClient(
        "v10.8.13",
        "u1",
        [{"Name": "Differential Seed Music", "ItemId": "lib1"}],
        {"Genres": None, "Years": []},  # OfficialRatings missing
    )
    c2 = FakeClient(
        "v10.9.0",
        "u2",
        [{"Name": "Differential Seed Music", "ItemId": "lib2"}],
        {"Genres": None, "Years": []},  # OfficialRatings missing
    )

    report = run_differential_filters((c1, c2))
    res1 = report["results"]["v10.8.13"]
    assert res1["Genres"] == {"state": "null"}
    assert res1["Years"] == {"state": "values", "values": []}
    assert res1["OfficialRatings"] == {"state": "missing"}


def test_run_differential_filters_reports_mismatches():
    c1 = FakeClient(
        "v10.8.13",
        "u1",
        [{"Name": "Differential Seed Music", "ItemId": "lib1"}],
        {"Genres": ["Action"], "Years": [2020], "OfficialRatings": ["PG"]},
    )
    c2 = FakeClient(
        "v10.9.0",
        "u2",
        [{"Name": "Differential Seed Music", "ItemId": "lib2"}],
        {"Genres": ["Comedy"], "Years": [2020], "OfficialRatings": ["PG"]},
    )

    report = run_differential_filters((c1, c2))
    assert report["status"] == "different"
    assert report["parity"] == "different"
    assert report["differences"] == ["Genres"]


def test_runner_starts_as_script():
    proc = subprocess.run(
        [sys.executable, "scripts/G2_14_items_filters.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--v108-url" in proc.stdout
    assert "--v109-url" in proc.stdout
    assert "--username" in proc.stdout
    assert "--password" in proc.stdout
    assert "--timeout" in proc.stdout
    assert "--report" in proc.stdout
