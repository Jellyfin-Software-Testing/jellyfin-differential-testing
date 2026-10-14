from enum import Enum
from typing import Dict, Any, Optional

class DiscrepancyCategory(str, Enum):
    DYNAMIC_NOISE = "DYNAMIC_NOISE"
    ENVIRONMENT_DIFFERENCE = "ENVIRONMENT_DIFFERENCE"
    NORMALIZATION_TOLERANCE_ISSUE = "NORMALIZATION_TOLERANCE_ISSUE"
    INTENDED_VERSION_CHANGE = "INTENDED_VERSION_CHANGE"
    API_CONTRACT_BREAKING_CHANGE = "API_CONTRACT_BREAKING_CHANGE"
    POTENTIAL_DEFECT = "POTENTIAL_DEFECT"
    CONFIRMED_DEFECT = "CONFIRMED_DEFECT"

class DiscrepancyClassifier:
    def classify(self, diff_item: Dict[str, Any], openapi_spec: Optional[Dict] = None) -> DiscrepancyCategory:
        path = diff_item.get("path", "").lower()
        msg = diff_item.get("message", "").lower()
        category = diff_item.get("category", "").upper()

        # 1. Kiểm tra Schema / Breaking Change TRƯỚC
        if category == "TYPE_MISMATCH" or "missing" in msg:
            return DiscrepancyCategory.API_CONTRACT_BREAKING_CHANGE

        # 2. Dynamic Noise (Chỉ dùng các từ khóa chính xác)
        if any(keyword in path for keyword in ["date", "time", "timestamp", "ticks", "sessionid"]):
            return DiscrepancyCategory.DYNAMIC_NOISE

        # 3. Environment Difference
        if "host" in path or "port" in path or "url" in path:
            return DiscrepancyCategory.ENVIRONMENT_DIFFERENCE

        return DiscrepancyCategory.POTENTIAL_DEFECT