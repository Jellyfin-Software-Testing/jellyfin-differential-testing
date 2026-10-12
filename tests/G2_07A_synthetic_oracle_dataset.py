# tests/synthetic_oracle_dataset.py

SYNTHETIC_ORACLE_DATASET = [
    # ------------------------------------------------------------------
    # KNOWN EQUAL CASES (Kỳ vọng: Diff Engine KHÔNG phát hiện diff nào -> TN)
    # ------------------------------------------------------------------
    {
        "id": "TC_EQUAL_01",
        "description": "Identical responses",
        "expected_has_diff": False,
        "v1": {"status": 200, "headers": {"Content-Type": "application/json"}, "body": {"id": "1", "name": "Item A"}},
        "v2": {"status": 200, "headers": {"Content-Type": "application/json"}, "body": {"id": "1", "name": "Item A"}}
    },
    {
        "id": "TC_EQUAL_02",
        "description": "Ignored dynamic headers (Date/Server mismatch)",
        "expected_has_diff": False,
        "v1": {"status": 200, "headers": {"Date": "Mon, 01 Jan 2026"}, "body": {"id": "1"}},
        "v2": {"status": 200, "headers": {"Date": "Tue, 02 Jan 2026"}, "body": {"id": "1"}}
    },

    # ------------------------------------------------------------------
    # KNOWN DIFFERENCE CASES (Kỳ vọng: Diff Engine PHÁT HIỆN diff -> TP)
    # ------------------------------------------------------------------
    {
        "id": "TC_DIFF_STATUS",
        "description": "Status code mismatch (200 vs 404)",
        "expected_has_diff": True,
        "expected_category": "STATUS_CODE",
        "v1": {"status": 200, "headers": {}, "body": {"id": "1"}},
        "v2": {"status": 404, "headers": {}, "body": {"id": "1"}}
    },
    {
        "id": "TC_DIFF_TYPE",
        "description": "Type mismatch in body (string vs int)",
        "expected_has_diff": True,
        "expected_category": "TYPE_MISMATCH",
        "v1": {"status": 200, "headers": {}, "body": {"id": "123"}},
        "v2": {"status": 200, "headers": {}, "body": {"id": 123}}
    },
    {
        "id": "TC_DIFF_VALUE",
        "description": "Value mismatch in body field",
        "expected_has_diff": True,
        "expected_category": "VALUE_MISMATCH",
        "v1": {"status": 200, "headers": {}, "body": {"name": "Movie A"}},
        "v2": {"status": 200, "headers": {}, "body": {"name": "Movie B"}}
    },
    {
        "id": "TC_DIFF_MISSING",
        "description": "Missing field in V2",
        "expected_has_diff": True,
        "expected_category": "MISSING_FIELD",
        "v1": {"status": 200, "headers": {}, "body": {"id": "1", "old_param": "test"}},
        "v2": {"status": 200, "headers": {}, "body": {"id": "1"}}
    },
    {
        "id": "TC_DIFF_ADDITIONAL",
        "description": "Additional field in V2",
        "expected_has_diff": True,
        "expected_category": "ADDITIONAL_FIELD",
        "v1": {"status": 200, "headers": {}, "body": {"id": "1"}},
        "v2": {"status": 200, "headers": {}, "body": {"id": "1", "new_param": "test"}}
    },
    {
        "id": "TC_DIFF_ARRAY",
        "description": "Array length mismatch",
        "expected_has_diff": True,
        "expected_category": "ARRAY_MISMATCH",
        "v1": {"status": 200, "headers": {}, "body": {"tags": ["a", "b"]}},
        "v2": {"status": 200, "headers": {}, "body": {"tags": ["a"]}}
    }
]
