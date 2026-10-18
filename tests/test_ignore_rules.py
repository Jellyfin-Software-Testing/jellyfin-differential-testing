"""Task G2-03 Test Suite: Validation for Configuration-Driven ignore-rules.json.

Verifies that all normalization, masking, and ignore rules adhere to the G2-03
specification: defining mandatory fields (path, reason, scope, risk), valid
JSONPath expressions, proper scope and risk tiers, and preserving known differences.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "config" / "ignore-rules.json"

MANDATORY_FIELDS = {"path", "reason", "scope", "risk"}
ALLOWED_SCOPES = {"global", "endpoint"}
ALLOWED_RISKS = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_ACTIONS = {"mask", "normalize", "ignore"}


@pytest.fixture(scope="module")
def rules_data() -> Dict[str, Any]:
    """Loads and parses config/ignore-rules.json."""
    assert RULES_PATH.exists(), f"Configuration file not found: {RULES_PATH}"
    content = RULES_PATH.read_text(encoding="utf-8")
    assert content.strip(), "Configuration file is empty"
    return json.loads(content)


@pytest.fixture(scope="module")
def all_active_rules(rules_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gathers all active rules across mask, format_normalization, and ignore blocks."""
    rules = []
    rules.extend(rules_data.get("mask_rules", []))
    rules.extend(rules_data.get("format_normalization_rules", []))
    rules.extend(rules_data.get("ignore_rules", []))
    return rules


def test_ignore_rules_file_exists_and_is_valid_json(rules_data: Dict[str, Any]) -> None:
    """Verifies that ignore-rules.json exists and parses cleanly."""
    assert isinstance(rules_data, dict)
    assert "_metadata" in rules_data


def test_metadata_specification(rules_data: Dict[str, Any]) -> None:
    """Verifies that _metadata contains task identifier G2-03 and schema definitions."""
    meta = rules_data["_metadata"]
    assert meta.get("task") == "G2-03"
    assert "version" in meta
    assert "schema_specification" in meta
    schema_spec = meta["schema_specification"]
    assert set(schema_spec.get("mandatory_fields", [])) == MANDATORY_FIELDS


def test_mandatory_fields_present_in_all_rules(all_active_rules: List[Dict[str, Any]]) -> None:
    """G2-03 Requirement: Every rule MUST define path, reason, scope, and risk."""
    assert len(all_active_rules) > 0, "No active rules found in configuration"
    for rule in all_active_rules:
        rule_id = rule.get("rule_id", rule.get("path", "UNKNOWN"))
        missing = MANDATORY_FIELDS - set(rule.keys())
        assert not missing, f"Rule '{rule_id}' is missing mandatory fields: {missing}"
        # Ensure values are non-empty strings
        for field_name in MANDATORY_FIELDS:
            assert isinstance(rule[field_name], str), f"Rule '{rule_id}' field '{field_name}' must be string"
            assert rule[field_name].strip(), f"Rule '{rule_id}' field '{field_name}' cannot be empty"


def test_scope_values_valid(all_active_rules: List[Dict[str, Any]]) -> None:
    """Verifies that scope is strictly 'global' or 'endpoint'."""
    for rule in all_active_rules:
        rule_id = rule.get("rule_id", rule.get("path"))
        scope = rule["scope"]
        assert scope in ALLOWED_SCOPES, f"Rule '{rule_id}' has invalid scope '{scope}'. Allowed: {ALLOWED_SCOPES}"
        if scope == "endpoint":
            has_endpoint = ("endpoint" in rule and rule["endpoint"]) or ("endpoints" in rule and rule["endpoints"])
            assert has_endpoint, f"Rule '{rule_id}' has scope='endpoint' but specifies no endpoint or endpoints"


def test_risk_values_valid(all_active_rules: List[Dict[str, Any]]) -> None:
    """Verifies that risk is strictly 'LOW', 'MEDIUM', or 'HIGH'."""
    for rule in all_active_rules:
        rule_id = rule.get("rule_id", rule.get("path"))
        risk = rule["risk"]
        assert risk in ALLOWED_RISKS, f"Rule '{rule_id}' has invalid risk '{risk}'. Allowed: {ALLOWED_RISKS}"
        # Medium and High risk rules should have mitigation documented
        if risk in {"MEDIUM", "HIGH"}:
            assert "risk_mitigation" in rule, f"Rule '{rule_id}' with risk={risk} must document 'risk_mitigation'"


def test_action_values_valid(all_active_rules: List[Dict[str, Any]]) -> None:
    """Verifies that action is 'mask', 'normalize', or 'ignore'."""
    for rule in all_active_rules:
        rule_id = rule.get("rule_id", rule.get("path"))
        action = rule.get("action")
        assert action in ALLOWED_ACTIONS, f"Rule '{rule_id}' has invalid action '{action}'. Allowed: {ALLOWED_ACTIONS}"
        if action == "mask":
            assert "replacement" in rule, f"Mask rule '{rule_id}' must define 'replacement'"
        elif action == "normalize":
            assert "strategy" in rule, f"Normalize rule '{rule_id}' must define 'strategy'"


def test_jsonpath_syntax_valid(all_active_rules: List[Dict[str, Any]]) -> None:
    """Verifies that all paths conform to JSONPath root syntax (starts with '$')."""
    for rule in all_active_rules:
        rule_id = rule.get("rule_id", rule.get("path"))
        path = rule["path"]
        assert path.startswith("$"), f"Rule '{rule_id}' path '{path}' must start with '$' (JSONPath root)"


def test_rule_ids_unique(all_active_rules: List[Dict[str, Any]]) -> None:
    """Verifies that all rule_id values are unique."""
    rule_ids = [r["rule_id"] for r in all_active_rules if "rule_id" in r]
    duplicates = [rid for rid in rule_ids if rule_ids.count(rid) > 1]
    assert not duplicates, f"Found duplicate rule IDs: {set(duplicates)}"


def test_known_differences_preserved(rules_data: Dict[str, Any]) -> None:
    """Verifies that known_differences list is preserved with expected entries (> 100)."""
    assert "known_differences" in rules_data
    diffs = rules_data["known_differences"]
    assert isinstance(diffs, list)
    assert len(diffs) >= 100, f"Expected at least 100 known differences, found {len(diffs)}"
    for diff in diffs:
        assert "path" in diff
        assert "endpoint" in diff
        assert "description" in diff
