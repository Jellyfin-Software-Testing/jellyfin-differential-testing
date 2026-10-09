import json
from pathlib import Path
import re

import pytest

from normalizer import NormalizerConfigError, SemanticNormalizer

ROOT = Path(__file__).resolve().parent.parent


def load_rules(tmp_path: Path, rules: list) -> SemanticNormalizer:
    config_file = tmp_path / "rules.json"
    config_file.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    return SemanticNormalizer.from_file(config_file)


def test_loads_real_ignore_rules():
    normalizer = SemanticNormalizer.from_file(ROOT / "config" / "ignore-rules.json")
    assert normalizer.rule_count == 6


def test_accepts_supported_field_and_wildcard_paths(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.AccessToken", "action": "DROP"},
        {"path": "$.User.Id", "action": "MAP_STATE"},
        {
            "path": "$.MediaSources[*].TranscodingUrl",
            "action": "REGEX_REPLACE",
            "pattern": "token=[^&]+",
            "replacement": "token=<MASKED>",
        },
    ])
    assert normalizer.rule_count == 3


@pytest.mark.parametrize(("document", "message"), [
    ([], "root must be an object"),
    ({}, "missing 'rules' list"),
    ({"rules": {}}, "'rules' must be a list"),
    ({"rules": ["bad"]}, "rule 0"),
    ({"rules": [{"action": "DROP"}]}, "rule 0"),
    ({"rules": [{"path": "Items[*].Id", "action": "DROP"}]}, "Items[*].Id"),
    ({"rules": [{"path": "$.Items[0].Id", "action": "DROP"}]}, "$.Items[0].Id"),
    ({"rules": [{"path": "$.Id", "action": "MASK"}]}, "MASK"),
    ({"rules": [{"path": "$.Url", "action": "REGEX_REPLACE"}]}, "pattern"),
    ({"rules": [{"path": "$.Url", "action": "REGEX_REPLACE", "pattern": "[", "replacement": "x"}]}, "$.Url"),
])
def test_rejects_invalid_configuration(tmp_path, document, message):
    config_file = tmp_path / "invalid.json"
    config_file.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(NormalizerConfigError, match=re.escape(message)):
        SemanticNormalizer.from_file(config_file)


@pytest.mark.parametrize("bad_replacement", [None, 123, []])
def test_rejects_missing_or_non_string_replacement(tmp_path, bad_replacement):
    rule = {
        "path": "$.Url",
        "action": "REGEX_REPLACE",
        "pattern": "token=[^&]+",
    }
    if bad_replacement is not None:
        rule["replacement"] = bad_replacement
    config_file = tmp_path / "bad_replacement.json"
    config_file.write_text(json.dumps({"rules": [rule]}), encoding="utf-8")
    with pytest.raises(NormalizerConfigError, match="replacement"):
        SemanticNormalizer.from_file(config_file)


def test_rejects_invalid_replacement_group_reference(tmp_path):
    config_file = tmp_path / "invalid_group.json"
    config_file.write_text(
        json.dumps({
            "rules": [
                {
                    "path": "$.Url",
                    "action": "REGEX_REPLACE",
                    "pattern": "(x)",
                    "replacement": r"\2",
                }
            ]
        }),
        encoding="utf-8",
    )
    with pytest.raises(NormalizerConfigError, match=re.escape("$.Url")):
        SemanticNormalizer.from_file(config_file)


def test_wraps_malformed_json(tmp_path):
    config_file = tmp_path / "malformed.json"
    config_file.write_text("{bad json", encoding="utf-8")
    with pytest.raises(NormalizerConfigError) as exc_info:
        SemanticNormalizer.from_file(config_file)
    assert str(config_file) in str(exc_info.value)


def test_wraps_missing_file(tmp_path):
    config_file = tmp_path / "nonexistent.json"
    with pytest.raises(NormalizerConfigError) as exc_info:
        SemanticNormalizer.from_file(config_file)
    assert str(config_file) in str(exc_info.value)


def test_drop_removes_root_and_nested_dictionary_fields(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.AccessToken", "action": "DROP"},
        {"path": "$.User.Id", "action": "DROP"},
    ])
    payload = {
        "AccessToken": "secret",
        "Keep": 123,
        "User": {"Id": "user-1", "Name": "Alice"},
    }
    result = normalizer.normalize(payload)
    assert result == {
        "Keep": 123,
        "User": {"Name": "Alice"},
    }


def test_drop_through_wildcard_applies_to_every_dictionary(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.Users[*].Id", "action": "DROP"},
    ])
    payload = {
        "Users": [
            {"Id": "a", "Name": "A"},
            {"Id": "b"},
        ]
    }
    result = normalizer.normalize(payload)
    assert result == {
        "Users": [
            {"Name": "A"},
            {},
        ]
    }


def test_drop_direct_list_elements_replaces_them_with_none(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.Values[*]", "action": "DROP"},
    ])
    payload = {"Values": [1, 2]}
    result = normalizer.normalize(payload)
    assert result == {"Values": [None, None]}


def test_normalize_does_not_mutate_input(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.AccessToken", "action": "DROP"},
    ])
    payload = {"AccessToken": "secret", "Data": {"nested": "value"}}
    result = normalizer.normalize(payload)
    assert payload["AccessToken"] == "secret"
    assert result is not payload
    assert result["Data"] is not payload["Data"]


def test_empty_rules_return_equal_distinct_deep_copy(tmp_path):
    normalizer = load_rules(tmp_path, [])
    payload = {"key": "value", "list": [1, 2, {"inner": "data"}]}
    result = normalizer.normalize(payload)
    assert result == payload
    assert result is not payload
    assert result["list"] is not payload["list"]
    assert result["list"][2] is not payload["list"][2]


def test_regex_replace_replaces_matching_substrings(tmp_path):
    normalizer = load_rules(tmp_path, [
        {
            "path": "$.MediaSources[*].TranscodingUrl",
            "action": "REGEX_REPLACE",
            "pattern": "(?<=SessionId=)[a-zA-Z0-9]+",
            "replacement": "<MASKED_SESSION>",
        }
    ])
    payload = {
        "MediaSources": [
            {"TranscodingUrl": "http://stream?SessionId=abc12345&codec=h264"},
            {"TranscodingUrl": "http://stream?SessionId=xyz98765&codec=aac"},
            {"OtherField": "no-url"},
        ]
    }
    result = normalizer.normalize(payload)
    assert result == {
        "MediaSources": [
            {"TranscodingUrl": "http://stream?SessionId=<MASKED_SESSION>&codec=h264"},
            {"TranscodingUrl": "http://stream?SessionId=<MASKED_SESSION>&codec=aac"},
            {"OtherField": "no-url"},
        ]
    }


def test_regex_replace_non_string_leaves_remain_unchanged(tmp_path):
    normalizer = load_rules(tmp_path, [
        {
            "path": "$.Count",
            "action": "REGEX_REPLACE",
            "pattern": r"\d+",
            "replacement": "NUM",
        },
        {
            "path": "$.Details",
            "action": "REGEX_REPLACE",
            "pattern": "foo",
            "replacement": "bar",
        },
    ])
    payload = {"Count": 12345, "Details": None}
    result = normalizer.normalize(payload)
    assert result == {"Count": 12345, "Details": None}


def test_wildcard_mixed_element_types_only_affects_compatible_branches(tmp_path):
    normalizer = load_rules(tmp_path, [
        {
            "path": "$.Items[*].Name",
            "action": "REGEX_REPLACE",
            "pattern": "^test-",
            "replacement": "item-",
        }
    ])
    payload = {
        "Items": [
            {"Name": "test-movie"},
            "a scalar item",
            [1, 2, 3],
            {"Name": 999},
            {"Other": "value"},
            {"Name": "test-show"},
        ]
    }
    result = normalizer.normalize(payload)
    assert result == {
        "Items": [
            {"Name": "item-movie"},
            "a scalar item",
            [1, 2, 3],
            {"Name": 999},
            {"Other": "value"},
            {"Name": "item-show"},
        ]
    }


def test_missing_path_leaves_payload_unchanged(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.Nonexistent.Field", "action": "DROP"},
        {"path": "$.Missing[*].Child", "action": "DROP"},
    ])
    payload = {"Existing": "data"}
    result = normalizer.normalize(payload)
    assert result == {"Existing": "data"}


def test_incompatible_container_type_mismatch_leaves_payload_unchanged(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.Field.Nested", "action": "DROP"},
        {"path": "$.Items[*].Name", "action": "DROP"},
    ])
    payload = {
        "Field": ["not", "a", "dict"],
        "Items": {"not": "a list"},
    }
    result = normalizer.normalize(payload)
    assert result == {
        "Field": ["not", "a", "dict"],
        "Items": {"not": "a list"},
    }


def test_map_state_converges_version_ids_to_one_canonical_id(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.Id", "action": "MAP_STATE"},
        {"path": "$.User.Id", "action": "MAP_STATE"},
    ])
    state_mapping = {
        "v108-id": "user:admin",
        "v109-id": "user:admin",
        42: "item:42",
    }
    payload_v108 = {"Id": "v108-id", "User": {"Id": "v108-id"}}
    payload_v109 = {"Id": "v109-id", "User": {"Id": "v109-id"}}

    res_108 = normalizer.normalize(payload_v108, state_mapping=state_mapping)
    res_109 = normalizer.normalize(payload_v109, state_mapping=state_mapping)

    assert res_108 == {"Id": "user:admin", "User": {"Id": "user:admin"}}
    assert res_109 == {"Id": "user:admin", "User": {"Id": "user:admin"}}
    assert res_108 == res_109


def test_map_state_preserves_missing_and_unhashable_values(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.UnmappedId", "action": "MAP_STATE"},
        {"path": "$.DictLeaf", "action": "MAP_STATE"},
        {"path": "$.ListLeaf", "action": "MAP_STATE"},
    ])
    state_mapping = {"v108-id": "user:admin"}
    payload = {
        "UnmappedId": "unknown-uuid",
        "DictLeaf": {"nested": 1},
        "ListLeaf": [1, 2, 3],
    }
    result = normalizer.normalize(payload, state_mapping=state_mapping)
    assert result == {
        "UnmappedId": "unknown-uuid",
        "DictLeaf": {"nested": 1},
        "ListLeaf": [1, 2, 3],
    }


def test_map_state_supports_known_hashable_non_string_values(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.ItemId", "action": "MAP_STATE"},
    ])
    state_mapping = {42: "item:42"}
    payload = {"ItemId": 42}
    result = normalizer.normalize(payload, state_mapping=state_mapping)
    assert result == {"ItemId": "item:42"}


def test_rules_apply_in_file_order(tmp_path):
    normalizer = load_rules(tmp_path, [
        {
            "path": "$.Token",
            "action": "REGEX_REPLACE",
            "pattern": "^foo",
            "replacement": "bar",
        },
        {"path": "$.Token", "action": "DROP"},
    ])
    payload = {"Token": "foosecret"}
    result = normalizer.normalize(payload)
    assert "Token" not in result


def test_scalar_payload_is_deep_copied_without_change(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.Id", "action": "DROP"},
    ])
    assert normalizer.normalize(123) == 123
    assert normalizer.normalize("text") == "text"
    assert normalizer.normalize(True) is True
    assert normalizer.normalize(None) is None
