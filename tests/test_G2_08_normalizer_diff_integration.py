"""Synthetic response pairs exercise the Normalizer -> DiffEngine contract."""

from pathlib import Path

import pytest

from normalizer import SemanticNormalizer
from normalizer.G2_07_diff_engine import DiffCategory, SemanticDiffEngine


RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "normalization-rules.json"
AUTH_ENDPOINT = "POST /Users/AuthenticateByName"
ITEMS_ENDPOINT = "GET /Items"


@pytest.fixture(scope="module")
def normalizer():
    return SemanticNormalizer.from_file(RULES_PATH)


def compare_normalized(normalizer, endpoint, v108, v109, state_mapping=None):
    old_body = normalizer.normalize(
        v108, endpoint=endpoint, state_mapping=state_mapping,
    )
    new_body = normalizer.normalize(
        v109, endpoint=endpoint, state_mapping=state_mapping,
    )
    return SemanticDiffEngine().compare_responses(
        v1_status=200,
        v2_status=200,
        v1_headers={},
        v2_headers={},
        v1_body=old_body,
        v2_body=new_body,
    )


def test_authentication_tokens_and_mapped_ids_do_not_create_false_diffs(normalizer):
    v108 = {"AccessToken": "token-108", "User": {"Id": "id-108", "Name": "admin"}}
    v109 = {"AccessToken": "token-109", "User": {"Id": "id-109", "Name": "admin"}}
    state_mapping = {"id-108": "user:admin", "id-109": "user:admin"}

    assert compare_normalized(
        normalizer, AUTH_ENDPOINT, v108, v109, state_mapping,
    ) == []
    assert v108["AccessToken"] == "token-108"
    assert v109["User"]["Id"] == "id-109"


def test_real_authentication_difference_survives_normalization(normalizer):
    v108 = {"AccessToken": "token-108", "User": {"Id": "id-108", "Name": "admin"}}
    v109 = {"AccessToken": "token-109", "User": {"Id": "id-109", "Name": "guest"}}
    state_mapping = {"id-108": "user:admin", "id-109": "user:admin"}

    diffs = compare_normalized(normalizer, AUTH_ENDPOINT, v108, v109, state_mapping)
    assert [(item.category, item.path, item.v1_val, item.v2_val) for item in diffs] == [
        (DiffCategory.VALUE_MISMATCH, "$.User.Name", "admin", "guest"),
    ]


def test_authentication_rules_do_not_apply_to_other_endpoints(normalizer):
    diffs = compare_normalized(
        normalizer,
        ITEMS_ENDPOINT,
        {"AccessToken": "token-108"},
        {"AccessToken": "token-109"},
    )
    assert [(item.category, item.path) for item in diffs] == [
        (DiffCategory.VALUE_MISMATCH, "$.AccessToken"),
    ]


def test_masking_preserves_a_token_type_defect(normalizer):
    diffs = compare_normalized(
        normalizer,
        AUTH_ENDPOINT,
        {"AccessToken": "token-108"},
        {"AccessToken": None},
    )
    assert [(item.category, item.path) for item in diffs] == [
        (DiffCategory.TYPE_MISMATCH, "$.AccessToken"),
    ]


def test_item_ids_and_nested_session_urls_converge(normalizer):
    v108 = {"Items": [{
        "Id": "item-108",
        "MediaSources": [
            {"TranscodingUrl": "https://media/stream?SessionId=abc123&codec=aac"},
        ],
    }]}
    v109 = {"Items": [{
        "Id": "item-109",
        "MediaSources": [
            {"TranscodingUrl": "https://media/stream?SessionId=xyz789&codec=aac"},
        ],
    }]}
    state_mapping = {"item-108": "item:reference", "item-109": "item:reference"}

    assert compare_normalized(
        normalizer, ITEMS_ENDPOINT, v108, v109, state_mapping,
    ) == []
