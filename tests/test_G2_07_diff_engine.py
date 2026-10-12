import pytest
from normalizer.G2_07_diff_engine import SemanticDiffEngine, DiffCategory
def test_semantic_diff_engine_all_categories():
    engine = SemanticDiffEngine()
    
    v1_body = {
        "id": "123",
        "name": "Movie A",
        "views": 100,
        "tags": ["action", "drama"],
        "old_field": "removed"
    }
    
    v2_body = {
        "id": 123,  # Type mismatch
        "name": "Movie B",  # Value mismatch
        "views": 100,
        "tags": ["action"],  # Array mismatch
        "new_field": "added"  # Additional field
    }

    diffs = engine.compare_responses(
        v1_status=200,
        v2_status=404,  # Status code mismatch
        v1_headers={"Content-Type": "application/json", "X-Custom": "v1"},
        v2_headers={"Content-Type": "application/json"},  # Missing header
        v1_body=v1_body,
        v2_body=v2_body
    )

    categories = {d.category for d in diffs}
    
    assert DiffCategory.STATUS_CODE in categories
    assert DiffCategory.HEADER in categories
    assert DiffCategory.TYPE_MISMATCH in categories
    assert DiffCategory.VALUE_MISMATCH in categories
    assert DiffCategory.ARRAY_MISMATCH in categories
    assert DiffCategory.MISSING_FIELD in categories
    assert DiffCategory.ADDITIONAL_FIELD in categories