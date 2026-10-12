"""Focused unit tests for the G2-07 semantic diff engine."""

import pytest

from normalizer.G2_07_diff_engine import DiffCategory, SemanticDiffEngine


@pytest.fixture
def engine():
    return SemanticDiffEngine()


def compare(engine, *, v1_status=200, v2_status=200, v1_headers=None,
            v2_headers=None, v1_body=None, v2_body=None, ignore_headers=None):
    return engine.compare_responses(
        v1_status=v1_status,
        v2_status=v2_status,
        v1_headers={} if v1_headers is None else v1_headers,
        v2_headers={} if v2_headers is None else v2_headers,
        v1_body=v1_body,
        v2_body=v2_body,
        ignore_headers=ignore_headers,
    )


def test_identical_nested_responses_have_no_differences(engine):
    body = {"Items": [{"Id": "one", "Tags": ["music", None]}]}
    assert compare(engine, v1_body=body, v2_body=body) == []


def test_status_code_difference_has_precise_values(engine):
    diffs = compare(engine, v1_status=200, v2_status=404)
    assert len(diffs) == 1
    assert diffs[0].to_dict() == {
        "category": "STATUS_CODE",
        "path": "status_code",
        "v1_value": 200,
        "v2_value": 404,
        "message": "Status code mismatch: 200 vs 404",
    }


@pytest.mark.parametrize(
    ("v1_headers", "v2_headers", "path", "v1_value", "v2_value"),
    [
        ({"X-Feature": "old"}, {}, "headers.X-Feature", "old", None),
        ({}, {"X-Feature": "new"}, "headers.X-Feature", None, "new"),
        ({"X-Feature": "old"}, {"X-Feature": "new"},
         "headers.X-Feature", "old", "new"),
    ],
    ids=["removed", "added", "changed"],
)
def test_header_differences_are_bidirectional(
    engine, v1_headers, v2_headers, path, v1_value, v2_value,
):
    diffs = compare(engine, v1_headers=v1_headers, v2_headers=v2_headers)
    assert len(diffs) == 1
    assert diffs[0].category is DiffCategory.HEADER
    assert (diffs[0].path, diffs[0].v1_val, diffs[0].v2_val) == (
        path, v1_value, v2_value,
    )


def test_header_names_are_case_insensitive(engine):
    assert compare(
        engine,
        v1_headers={"Content-Type": "application/json"},
        v2_headers={"content-type": "application/json"},
    ) == []


def test_default_dynamic_headers_are_ignored_on_both_sides(engine):
    assert compare(
        engine,
        v1_headers={"Date": "yesterday", "SERVER": "v10.8"},
        v2_headers={"date": "today", "Transfer-Encoding": "chunked"},
    ) == []


def test_explicit_ignored_headers_replace_defaults(engine):
    diffs = compare(
        engine,
        v1_headers={"Date": "yesterday", "X-Trace": "a"},
        v2_headers={"Date": "today", "x-trace": "b"},
        ignore_headers=["X-TRACE"],
    )
    assert [(diff.category, diff.path) for diff in diffs] == [
        (DiffCategory.HEADER, "headers.Date"),
    ]


def test_empty_ignore_list_compares_default_dynamic_headers(engine):
    diffs = compare(
        engine,
        v1_headers={"Date": "yesterday"},
        v2_headers={"Date": "today"},
        ignore_headers=[],
    )
    assert [(diff.category, diff.path) for diff in diffs] == [
        (DiffCategory.HEADER, "headers.Date"),
    ]


@pytest.mark.parametrize(
    ("v1_body", "v2_body", "category", "path", "v1_value", "v2_value"),
    [
        ({"User": {"Old": 1}}, {"User": {}},
         DiffCategory.MISSING_FIELD, "$.User.Old", 1, None),
        ({"User": {}}, {"User": {"New": 2}},
         DiffCategory.ADDITIONAL_FIELD, "$.User.New", None, 2),
        ({"Count": "1"}, {"Count": 1},
         DiffCategory.TYPE_MISMATCH, "$.Count", "str", "int"),
        ({"Enabled": True}, {"Enabled": 1},
         DiffCategory.TYPE_MISMATCH, "$.Enabled", "bool", "int"),
        ({"Name": "old"}, {"Name": "new"},
         DiffCategory.VALUE_MISMATCH, "$.Name", "old", "new"),
        ({"Items": [1]}, {"Items": [1, 2]},
         DiffCategory.ARRAY_MISMATCH, "$.Items", 1, 2),
        ({"Items": [{"Name": "old"}]}, {"Items": [{"Name": "new"}]},
         DiffCategory.VALUE_MISMATCH, "$.Items[0].Name", "old", "new"),
        (None, {}, DiffCategory.TYPE_MISMATCH, "$", "NoneType", "dict"),
    ],
    ids=["missing", "additional", "type", "bool-vs-int", "value",
         "array-length", "nested-array-value", "root-type"],
)
def test_body_difference_has_precise_category_path_and_values(
    engine, v1_body, v2_body, category, path, v1_value, v2_value,
):
    diffs = compare(engine, v1_body=v1_body, v2_body=v2_body)
    assert len(diffs) == 1
    assert (diffs[0].category, diffs[0].path, diffs[0].v1_val, diffs[0].v2_val) == (
        category, path, v1_value, v2_value,
    )


def test_array_length_and_shared_element_differences_are_both_reported(engine):
    diffs = compare(engine, v1_body=["old", "extra"], v2_body=["new"])
    assert {(diff.category, diff.path) for diff in diffs} == {
        (DiffCategory.ARRAY_MISMATCH, "$"),
        (DiffCategory.VALUE_MISMATCH, "$[0]"),
    }


def test_missing_field_is_distinct_from_present_null(engine):
    diffs = compare(engine, v1_body={"Value": None}, v2_body={})
    assert len(diffs) == 1
    assert diffs[0].category is DiffCategory.MISSING_FIELD
    assert diffs[0].path == "$.Value"


def test_body_key_order_does_not_create_a_difference(engine):
    assert compare(
        engine,
        v1_body={"first": 1, "second": 2},
        v2_body={"second": 2, "first": 1},
    ) == []
