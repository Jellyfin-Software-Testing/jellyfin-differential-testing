"""
Test Suite cho ItemsTestModel (API /Items - Jira Task G1-10)
"""

import pytest
from models.g1_10_items_model import ItemsTestModel


def test_input_partitions():
    """Kiểm tra các Input Partitions đã được định nghĩa đầy đủ."""
    partitions = ItemsTestModel.get_input_partitions()
    assert "includeItemTypes" in partitions
    assert "sortBy" in partitions
    assert "userId" in partitions
    assert len(partitions["includeItemTypes"]) > 0


def test_boundary_values():
    """Kiểm tra danh sách Boundary Values."""
    boundaries = ItemsTestModel.get_boundary_values()
    assert isinstance(boundaries, list)
    assert len(boundaries) > 0
    # Kiểm tra có trường hợp limit = 0 và limit = -1
    limits = [b.get("limit") for b in boundaries if "limit" in b]
    assert 0 in limits
    assert -1 in limits


def test_null_or_missing_params():
    """Kiểm tra danh sách Null / Missing Params."""
    null_cases = ItemsTestModel.get_null_or_missing_params()
    assert isinstance(null_cases, list)
    assert {} in null_cases


@pytest.mark.parametrize(
    "request_params, response_data, expected_valid",
    [
        # Case 1: Response hợp lệ, thỏa mãn len(Items) <= limit
        ({"limit": 2}, {"Items": [{"Id": "1"}, {"Id": "2"}], "TotalRecordCount": 10}, True),
        # Case 2: Vi phạm limit invariant (len(Items) > limit)
        ({"limit": 1}, {"Items": [{"Id": "1"}, {"Id": "2"}], "TotalRecordCount": 10}, False),
        # Case 3: Vi phạm TotalRecordCount không âm
        ({}, {"Items": [], "TotalRecordCount": -5}, False),
        # Case 4: Vi phạm Type Filter Invariant
        (
            {"includeItemTypes": ["Movie"]},
            {"Items": [{"Id": "1", "Type": "Series"}], "TotalRecordCount": 1},
            False,
        ),
    ],
)
def test_verify_invariants(request_params, response_data, expected_valid):
    """Kiểm tra logic hàm verify_invariants."""
    is_valid, _ = ItemsTestModel.verify_invariants(request_params, response_data)
    assert is_valid == expected_valid