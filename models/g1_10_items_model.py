"""
Test Model cho nhóm API /Items
Task Jira: G1-10
"""
from typing import Any, Dict, List, Optional, Tuple


class ItemsTestModel:
    """Định nghĩa Data Partitions, Boundaries, Invariants cho API /Items."""

    @staticmethod
    def get_input_partitions() -> Dict[str, List[Any]]:
        """1. Phân vùng tương đương cho các tham số đầu vào."""
        return {
            "userId": [
                "3282f186c3824f228d48e0293112c3f8",  # Valid User GUID
                "00000000000000000000000000000000",  # Non-existent GUID
                "invalid-guid-format",               # Malformed GUID
            ],
            "parentId": [
                "00000000000000000000000000000000",  # Root / Non-existent Parent
                "12345678123412341234123412341234",  # Specific Parent GUID
            ],
            "includeItemTypes": [
                ["Movie"],
                ["Series"],
                ["Folder"],
                ["Audio"],
                ["Movie", "Series"],                  # Multi-type
                ["InvalidType"],                     # Unknown Type
            ],
            "sortBy": [
                ["SortName"],
                ["DateCreated"],
                ["Random"],
                ["InvalidSortField"],                 # Invalid Sort
            ],
            "sortOrder": [["Ascending"], ["Descending"]],
            "isFavorite": [True, False],
            "searchTerm": ["a", "Test", "NonExistentName123456"],
        }

    @staticmethod
    def get_boundary_values() -> List[Dict[str, Any]]:
        """2. Giá trị biên cho phân trang và chuỗi tìm kiếm."""
        return [
            # Boundary cho Limit
            {"limit": -1},                           # Dưới biên âm
            {"limit": 0},                            # Biên dưới (0)
            {"limit": 1},                            # Minimum valid limit
            {"limit": 100},                          # Medium valid limit
            {"limit": 2147483647},                   # Int32 Max limit
            
            # Boundary cho StartIndex
            {"startIndex": -1},                      # Dưới biên âm
            {"startIndex": 0},                       # Biên đầu tiên
            {"startIndex": 1},                       # Index 1
            {"startIndex": 2147483647},              # Int32 Max index
            
            # Kết hợp biên StartIndex & Limit
            {"startIndex": 0, "limit": 0},
            {"startIndex": 0, "limit": 1},
            {"startIndex": 10, "limit": 5},
            
            # Boundary cho SearchTerm
            {"searchTerm": ""},                      # Rỗng (0 ký tự)
            {"searchTerm": "a"},                     # 1 ký tự
            {"searchTerm": "a" * 255},               # Chuỗi dài (255 ký tự)
        ]

    @staticmethod
    def get_null_or_missing_params() -> List[Dict[str, Any]]:
        """3. Các trường hợp khuyết thiếu hoặc mang giá trị Null/Empty."""
        return [
            {},                                      # Rỗng toàn bộ params
            {"userId": None},                        # Null UserId
            {"parentId": None},                      # Null ParentId
            {"searchTerm": None},                    # Null SearchTerm
            {"searchTerm": ""},                      # Empty String SearchTerm
            {"searchTerm": "   "},                   # Whitespace SearchTerm
            {"includeItemTypes": None},              # Null ItemTypes
            {"sortBy": None},                        # Null SortBy
            {"limit": None, "startIndex": None},     # Null Pagination
        ]

    @staticmethod
    def verify_invariants(
        request_params: Dict[str, Any], response_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        4. Kiểm tra các quy tắc bất biến (Expected Invariants).
        
        Returns:
            Tuple[bool, Optional[str]]: (True/False, Lý do thất bại nếu có)
        """
        if not isinstance(response_data, dict):
            return False, "Response payload phải là một dict JSON"

        # Check Schema căn bản
        if "Items" not in response_data:
            return False, "Response thiếu trường 'Items'"
            
        items = response_data.get("Items", [])
        if not isinstance(items, list):
            return False, "Trường 'Items' phải là một danh sách (list)"

        total_count = response_data.get("TotalRecordCount")
        if total_count is not None:
            if not isinstance(total_count, int) or total_count < 0:
                return False, f"TotalRecordCount ({total_count}) phải là số nguyên không âm"

        # Invariant 1: Pagination Invariant (len(Items) <= limit)
        limit = request_params.get("limit")
        if limit is not None and isinstance(limit, int) and limit >= 0:
            if len(items) > limit:
                return False, f"Số lượng items ({len(items)}) vượt quá Limit ({limit})"

        # Invariant 2: StartIndex Invariant
        start_index = request_params.get("startIndex")
        if (
            start_index is not None 
            and isinstance(start_index, int) 
            and total_count is not None
            and start_index >= total_count 
            and total_count > 0
        ):
            if len(items) != 0:
                return False, f"Items phải rỗng khi startIndex ({start_index}) >= totalCount ({total_count})"

        # Invariant 3: Type Filter Invariant
        include_types = request_params.get("includeItemTypes")
        if include_types and isinstance(include_types, list) and len(include_types) > 0:
            # Loại bỏ các type không hợp lệ khi verify
            valid_requested_types = set(include_types)
            for item in items:
                item_type = item.get("Type")
                if item_type and item_type not in valid_requested_types:
                    return False, f"Item type '{item_type}' không thuộc bộ lọc {include_types}"

        # Invariant 4: Item Schema Invariant (mói item phải có trường Id cơ bản)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                return False, f"Item tại vị trí {idx} không phải là dict"
            if "Id" not in item:
                return False, f"Item tại vị trí {idx} thiếu trường bắt buộc 'Id'"

        return True, None