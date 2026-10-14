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
