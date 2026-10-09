from enum import Enum
from typing import Any, Dict, List, Optional

class DiffCategory(str, Enum):
    STATUS_CODE = "STATUS_CODE"
    HEADER = "HEADER"
    SCHEMA = "SCHEMA"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    ARRAY_MISMATCH = "ARRAY_MISMATCH"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    MISSING_FIELD = "MISSING_FIELD"
    ADDITIONAL_FIELD = "ADDITIONAL_FIELD"

class DiffItem:
    def __init__(self, category: DiffCategory, path: str, v1_val: Any, v2_val: Any, message: str):
        self.category = category
        self.path = path
        self.v1_val = v1_val
        self.v2_val = v2_val
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "path": self.path,
            "v1_value": self.v1_val,
            "v2_value": self.v2_val,
            "message": self.message
        }

class SemanticDiffEngine:
    def compare_responses(
        self,
        v1_status: int,
        v2_status: int,
        v1_headers: Dict[str, str],
        v2_headers: Dict[str, str],
        v1_body: Any,
        v2_body: Any,
        ignore_headers: Optional[List[str]] = None
    ) -> List[DiffItem]:
        diffs: List[DiffItem] = []
        
        # 1. Compare Status Code
        if v1_status != v2_status:
            diffs.append(DiffItem(
                DiffCategory.STATUS_CODE,
                "status_code",
                v1_status,
                v2_status,
                f"Status code mismatch: {v1_status} vs {v2_status}"
            ))

        # 2. Compare Headers
        ignore = [h.lower() for h in (ignore_headers or ["date", "server", "transfer-encoding"])]
        for k, v in v1_headers.items():
            if k.lower() in ignore:
                continue
            if k not in v2_headers:
                diffs.append(DiffItem(
                    DiffCategory.HEADER,
                    f"headers.{k}",
                    v,
                    None,
                    f"Header '{k}' missing in v2"
                ))
            elif v2_headers[k] != v:
                diffs.append(DiffItem(
                    DiffCategory.HEADER,
                    f"headers.{k}",
                    v,
                    v2_headers[k],
                    f"Header '{k}' value mismatch"
                ))

        # 3. Compare Body recursively
        self._compare_body("$", v1_body, v2_body, diffs)
        return diffs

    def _compare_body(self, path: str, v1: Any, v2: Any, diffs: List[DiffItem]):
        if type(v1) != type(v2):
            diffs.append(DiffItem(
                DiffCategory.TYPE_MISMATCH,
                path,
                type(v1).__name__,
                type(v2).__name__,
                f"Type mismatch at {path}: {type(v1).__name__} vs {type(v2).__name__}"
            ))
            return

        if isinstance(v1, dict):
            keys1, keys2 = set(v1.keys()), set(v2.keys())
            for k in keys1 - keys2:
                diffs.append(DiffItem(
                    DiffCategory.MISSING_FIELD,
                    f"{path}.{k}",
                    v1[k],
                    None,
                    f"Field '{k}' missing in v2"
                ))
            for k in keys2 - keys1:
                diffs.append(DiffItem(
                    DiffCategory.ADDITIONAL_FIELD,
                    f"{path}.{k}",
                    None,
                    v2[k],
                    f"Field '{k}' added in v2"
                ))
            for k in keys1 & keys2:
                self._compare_body(f"{path}.{k}", v1[k], v2[k], diffs)

        elif isinstance(v1, list):
            if len(v1) != len(v2):
                diffs.append(DiffItem(
                    DiffCategory.ARRAY_MISMATCH,
                    path,
                    len(v1),
                    len(v2),
                    f"Array length mismatch at {path}: {len(v1)} vs {len(v2)}"
                ))
            for idx, (item1, item2) in enumerate(zip(v1, v2)):
                self._compare_body(f"{path}[{idx}]", item1, item2, diffs)

        else:
            if v1 != v2:
                diffs.append(DiffItem(
                    DiffCategory.VALUE_MISMATCH,
                    path,
                    v1,
                    v2,
                    f"Value mismatch at {path}: '{v1}' vs '{v2}'"
                ))