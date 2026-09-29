"""
Test Model cho nhóm API /Items
Task Jira: G1-10
"""

from typing import Any, Dict, List, Optional


class ItemsTestModel:
    """Định nghĩa Data Partitions, Boundaries, Invariants cho API /Items."""

    @staticmethod
    def get_input_partitions() -> Dict[str, List[Any]]:
        return {
            "includeItemTypes": [["Movie"], ["Series"], ["Folder"], ["InvalidType"]],
            "sortBy": [["SortName"], ["DateCreated"], ["InvalidSort"]],
            "sortOrder": [["Ascending"], ["Descending"]],
            "isFavorite": [True, False],
        }

    @staticmethod
    def get_boundary_values() -> Dict[str, List[int]]:
        return {
            "startIndex": [-1, 0, 1, 2147483647],
            "limit": [-1, 0, 1, 50, 100, 2147483647],
        }

    @staticmethod
    def get_null_or_missing_params() -> List[Dict[str, Any]]:
        return [
            {},
            {"userId": None},
            {"searchTerm": ""},
            {"parentId": None},
        ]

    @staticmethod
    def verify_invariants(
        request_params: Dict[str, Any], response_data: Dict[str, Any]
    ) -> bool:
        if not isinstance(response_data, dict):
            return False
        items = response_data.get("Items", [])
        total_count = response_data.get("TotalRecordCount")

        if "Items" not in response_data or not isinstance(items, list):
            return False

        limit = request_params.get("limit")
        if limit is not None and isinstance(limit, int) and limit >= 0:
            if len(items) > limit:
                return False

        if total_count is not None and total_count < 0:
            return False

        return True