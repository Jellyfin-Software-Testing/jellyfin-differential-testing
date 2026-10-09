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

