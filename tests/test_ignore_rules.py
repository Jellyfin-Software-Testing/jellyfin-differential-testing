#!/usr/bin/env python3
"""Unit tests for config/ignore-rules.json compliance and schema verification.

Ensures that all ignore, mask, and normalization rules adhere to:
  1. Mandatory field constraints (path, reason, scope, risk, evidence) per CONTRIBUTING.md Section 5.
  2. JSONPath syntax validity (all paths must start with '$').
  3. Risk level constraint (LOW, MEDIUM, HIGH).
  4. Zero False Negatives policy: no blind suppression of true architectural differences.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "ignore-rules.json"


@pytest.fixture(scope="module")
def config_data() -> Dict[str, Any]:
    assert CONFIG_FILE.exists(), f"Configuration file not found at: {CONFIG_FILE}"
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def test_config_file_exists() -> None:
    """Kiểm tra file cấu hình config/ignore-rules.json tồn tại trong dự án."""
    assert CONFIG_FILE.is_file(), "config/ignore-rules.json phải tồn tại trên ổ đĩa"


def test_top_level_keys_present(config_data: Dict[str, Any]) -> None:
    """Kiểm tra các trường cấu trúc bắt buộc ở cấp cao nhất (Top-level keys)."""
    mandatory_keys = [
        "_metadata",
        "mask_rules",
        "environment_normalization_rules",
        "format_normalization_rules",
        "ignore_rules",
        "known_differences",
    ]
    for key in mandatory_keys:
        assert key in config_data, f"Thiếu trường bắt buộc '{key}' ở cấp cao nhất của config."


def test_metadata_contains_audit_info(config_data: Dict[str, Any]) -> None:
    """Kiểm tra metadata chứa thông tin truy vết kiểm toán (Audit Trail)."""
    meta = config_data.get("_metadata", {})
    assert "task" in meta, "Metadata phải có thông tin 'task'"
    assert "updated_at" in meta or "generated_at" in meta, "Metadata phải có dấu thời gian timestamp"
    assert "policy" in meta, "Metadata phải ghi rõ chính sách đối soát (policy)"


def test_mask_rules_mandatory_fields(config_data: Dict[str, Any]) -> None:
    """Kiểm tra từng quy tắc mask_rules phải có đầy đủ các trường bắt buộc."""
    mask_rules = config_data.get("mask_rules", [])
    assert len(mask_rules) >= 7, "Cần ít nhất 7 quy tắc mask cho các trường nhiễu động ngẫu nhiên"
    
    required_fields = ["path", "replacement", "scope", "risk", "reason", "evidence"]
    for idx, rule in enumerate(mask_rules):
        for field in required_fields:
            assert field in rule, f"mask_rules[{idx}] thiếu trường bắt buộc '{field}'"
            assert str(rule[field]).strip() != "", f"mask_rules[{idx}].{field} không được để trống"


def test_environment_normalization_rules_mandatory_fields(config_data: Dict[str, Any]) -> None:
    """Kiểm tra từng quy tắc environment_normalization_rules có đủ thông tin hạ tầng."""
    env_rules = config_data.get("environment_normalization_rules", [])
    assert len(env_rules) >= 2, "Cần có ít nhất 2 quy tắc chuẩn hóa môi trường (cổng và ID container)"
    
    required_fields = ["path", "scope", "strategy", "risk", "reason", "evidence"]
    for idx, rule in enumerate(env_rules):
        for field in required_fields:
            assert field in rule, f"environment_normalization_rules[{idx}] thiếu trường '{field}'"
            assert str(rule[field]).strip() != "", f"environment_normalization_rules[{idx}].{field} không được trống"


def test_format_normalization_rules_mandatory_fields(config_data: Dict[str, Any]) -> None:
    """Kiểm tra các quy tắc chuẩn hóa định dạng thời gian dung sai (Tolerance/Precision)."""
    format_rules = config_data.get("format_normalization_rules", [])
    assert len(format_rules) >= 4, "Cần có ít nhất 4 quy tắc chuẩn hóa độ chính xác dấu thời gian microsecond"
    
    required_fields = ["path", "scope", "strategy", "risk", "reason", "evidence"]
    for idx, rule in enumerate(format_rules):
        for field in required_fields:
            assert field in rule, f"format_normalization_rules[{idx}] thiếu trường '{field}'"
            assert str(rule[field]).strip() != "", f"format_normalization_rules[{idx}].{field} không được trống"


def test_known_differences_mandatory_fields(config_data: Dict[str, Any]) -> None:
    """Kiểm tra danh mục known_differences giữ nguyên và có đầy đủ audit fields."""
    known_diffs = config_data.get("known_differences", [])
    assert len(known_diffs) >= 100, "Phải bảo toàn toàn bộ danh mục Known Differences của phiên bản v10.9"
    
    required_fields = ["path", "scope", "risk", "reason", "evidence"]
    for idx, rule in enumerate(known_diffs):
        for field in required_fields:
            assert field in rule, f"known_differences[{idx}] thiếu trường '{field}'"
            assert str(rule[field]).strip() != "", f"known_differences[{idx}].{field} không được trống"


def test_jsonpath_syntax_validity(config_data: Dict[str, Any]) -> None:
    """Kiểm tra tính hợp lệ cú pháp JSONPath: mọi đường dẫn path phải bắt đầu bằng '$'."""
    rule_groups = [
        ("mask_rules", config_data.get("mask_rules", [])),
        ("environment_normalization_rules", config_data.get("environment_normalization_rules", [])),
        ("format_normalization_rules", config_data.get("format_normalization_rules", [])),
        ("known_differences", config_data.get("known_differences", [])),
    ]
    for group_name, rules in rule_groups:
        for idx, rule in enumerate(rules):
            path_val = rule.get("path", "")
            assert path_val.startswith("$"), (
                f"Trong {group_name}[{idx}], path '{path_val}' không đúng chuẩn JSONPath (phải bắt đầu bằng '$')"
            )


def test_risk_levels_validity(config_data: Dict[str, Any]) -> None:
    """Kiểm tra mức độ rủi ro (risk level) phải thuộc tập giá trị hợp lệ: LOW, MEDIUM, HIGH."""
    allowed_risks = {"LOW", "MEDIUM", "HIGH"}
    rule_groups = [
        ("mask_rules", config_data.get("mask_rules", [])),
        ("environment_normalization_rules", config_data.get("environment_normalization_rules", [])),
        ("format_normalization_rules", config_data.get("format_normalization_rules", [])),
        ("known_differences", config_data.get("known_differences", [])),
    ]
    for group_name, rules in rule_groups:
        for idx, rule in enumerate(rules):
            risk_val = rule.get("risk", "")
            assert risk_val in allowed_risks, (
                f"Trong {group_name}[{idx}], risk='{risk_val}' không hợp lệ (phải là LOW, MEDIUM hoặc HIGH)"
            )


def test_zero_false_negatives_policy(config_data: Dict[str, Any]) -> None:
    """Kiểm tra chính sách Zero False Negatives: không đưa các khác biệt phiên bản quan trọng vào ignore_rules."""
    ignore_rules = config_data.get("ignore_rules", [])
    # Chính sách nghiêm ngặt: không được có quy tắc ignore che giấu trường phiên bản hoặc tính năng mới
    ignored_paths = [r.get("path", "") for r in ignore_rules]
    forbidden_to_ignore = ["$.Version", "$.CanSelfRestart", "$.CastReceiverApplications"]
    for forbidden in forbidden_to_ignore:
        assert forbidden not in ignored_paths, (
            f"Vi phạm Zero False Negatives: trường '{forbidden}' là thay đổi phiên bản có chủ đích, "
            f"tuyệt đối không được đưa vào ignore_rules (phải nằm trong known_differences)!"
        )


def test_empirical_evidence_length_and_quality(config_data: Dict[str, Any]) -> None:
    """Kiểm tra chất lượng bằng chứng (evidence): phải có mô tả chi tiết từ kết quả Run-1."""
    mask_rules = config_data.get("mask_rules", [])
    for idx, rule in enumerate(mask_rules):
        evidence = rule.get("evidence", "")
        assert len(evidence) >= 15, (
            f"mask_rules[{idx}] evidence quá ngắn ('{evidence}'), "
            f"cần mô tả rõ hiện tượng quan sát thực nghiệm từ Run-1"
        )
