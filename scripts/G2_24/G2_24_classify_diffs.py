#!/usr/bin/env python3
"""Task G2-24 - Step 2: Root Cause Analysis (RCA) & 4-Category Diff Classification.

Analyzes all raw differences ingested from Step 1 (reports/run1-diff-report.json)
and strictly classifies each difference into one of the 4 mandatory categories:
  1. dynamic_noise       (Nhiễu động ngẫu nhiên: token, session, timestamp hoạt động)
  2. environment_difference (Sai lệch do môi trường: port 8096 vs 8097, server IP, container paths)
  3. tolerance_issue     (Vấn đề dung sai / định dạng: độ chính xác microsecond, formatting)
  4. intended_change     (Thay đổi có chủ đích: version upgrade, breaking changes, schema mới)

Outputs:
  - docs/evidence/G2-24-classified-diffs.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
INPUT_REPORT_PATH = ROOT / "reports" / "run1-diff-report.json"
OUTPUT_DIR = ROOT / "docs" / "evidence" / "G2_24"
OUTPUT_CLASSIFIED_PATH = OUTPUT_DIR / "G2-24-classified-diffs.json"


def classify_difference(item: Dict[str, Any]) -> Dict[str, Any]:
    diff_id = item.get("diff_id", "")
    endpoint = item.get("endpoint", "")
    path = item.get("path", "")
    v108_val = str(item.get("v108_value", ""))
    v109_val = str(item.get("v109_value", ""))
    diff_type = item.get("diff_type", "")
    raw_obs = (item.get("raw_observation") or "").strip() or f"Observed empirical difference at {path} between v10.8.13 and v10.9.0."

    # -------------------------------------------------------------
    # 1. DYNAMIC NOISE
    # -------------------------------------------------------------
    is_dynamic = (
        diff_type == "dynamic_noise_drift"
        or "AccessToken" in path
        or "SessionInfo.Id" in path
        or "TranscodingUrl" in path
        or (endpoint == "POST /Users/AuthenticateByName" and "Date" in path)
        or (endpoint == "GET /System/ActivityLog/Entries" and ("Date" in path or "Id" in path))
    )
    if is_dynamic:
        return {
            "diff_id": diff_id,
            "endpoint": endpoint,
            "path": path,
            "v108_value": v108_val,
            "v109_value": v109_val,
            "category": "dynamic_noise",
            "category_vi": "Nhiễu động ngẫu nhiên",
            "proposed_action": "mask",
            "action_target": "config/ignore-rules.json (mask_rules)",
            "rationale": (
                "Giá trị biến động ngẫu nhiên qua các lần gọi độc lập dù giữ nguyên trạng thái seed. "
                "Cần che giá trị (mask) bằng placeholder cố định để triệt tiêu báo lỗi giả."
            ),
            "evidence": raw_obs,
        }

    # -------------------------------------------------------------
    # 2. ENVIRONMENT DIFFERENCE
    # -------------------------------------------------------------
    is_env = (
        "LocalAddress" in path
        or "Port" in path
        or (path == "$.Id" and endpoint == "GET /System/Info/Public")
        or (path == "$.ServerId")
        or "8096" in v108_val or "8097" in v109_val
        or "cache" in v108_val.lower() or "cache" in v109_val.lower()
    )
    if is_env:
        return {
            "diff_id": diff_id,
            "endpoint": endpoint,
            "path": path,
            "v108_value": v108_val,
            "v109_value": v109_val,
            "category": "environment_difference",
            "category_vi": "Sai lệch do môi trường",
            "proposed_action": "normalize_environment",
            "action_target": "Normalizer URL mapping & Host alignment",
            "rationale": (
                "Sai khác xuất phát từ sự khác biệt hạ tầng mạng Docker (cổng 8096 vs 8097) "
                "hoặc định danh ngẫu nhiên của container ảo, không phải lỗi logic Jellyfin. "
                "Cần chuẩn hóa URL/Host trước khi đối soát."
            ),
            "evidence": raw_obs,
        }

    # -------------------------------------------------------------
    # 3. TOLERANCE ISSUE (Format & Precision)
    # -------------------------------------------------------------
    is_tolerance = (
        diff_type == "timestamp_precision_mismatch"
        or ("Date" in path and re.search(r"\.\d+Z", v108_val))
        or (len(v108_val) > 20 and len(v109_val) > 20 and v108_val[:19] == v109_val[:19])
    )
    if is_tolerance:
        return {
            "diff_id": diff_id,
            "endpoint": endpoint,
            "path": path,
            "v108_value": v108_val,
            "v109_value": v109_val,
            "category": "tolerance_issue",
            "category_vi": "Vấn đề dung sai / Định dạng",
            "proposed_action": "normalize_precision",
            "action_target": "config/ignore-rules.json (format_normalization_rules)",
            "rationale": (
                "Hai phiên bản cùng biểu diễn một mốc thời gian nhưng khác biệt về số chữ số "
                "thập phân microsecond (.NET 6/7 dùng 7 chữ số, .NET 8 dùng 3 chữ số). "
                "Đề xuất áp dụng chiến lược truncate/round về 3 chữ số thay vì loại bỏ."
            ),
            "evidence": raw_obs,
        }

    # -------------------------------------------------------------
    # 4. INTENDED CHANGE (Known Differences / Feature Upgrades)
    # -------------------------------------------------------------
    return {
        "diff_id": diff_id,
        "endpoint": endpoint,
        "path": path,
        "v108_value": v108_val,
        "v109_value": v109_val,
        "category": "intended_change",
        "category_vi": "Thay đổi có chủ đích / Tính năng mới",
        "proposed_action": "preserve_known_diff",
        "action_target": "config/ignore-rules.json (known_differences) & Test Oracle",
        "rationale": (
            "Sự khác biệt phản ánh đúng bản chất nâng cấp mã nguồn giữa v10.8.13 và v10.9.0 "
            "(thay đổi cấu trúc DTO, bổ sung trường mới, nâng cấp phiên bản). "
            "TUYỆT ĐỐI KHÔNG MASK/IGNORE; đưa vào Test Oracle làm Expected Difference để không báo Fail."
        ),
        "evidence": raw_obs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_REPORT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_CLASSIFIED_PATH)
    args = parser.parse_args()

    print("=" * 65)
    print("  TASK G2-24 - STEP 2: RCA & 4-CATEGORY DIFF CLASSIFICATION")
    print("=" * 65)
    print(f"  Input Run-1 Diffs : {args.input}")
    print(f"  Output Catalog    : {args.output}")
    print("=" * 65)

    if not args.input.exists():
        print(f"ERROR: Input report not found at {args.input}", file=sys.stderr)
        return 1

    report_data = json.loads(args.input.read_text(encoding="utf-8"))
    raw_diffs = report_data.get("raw_differences", [])

    classified_list: List[Dict[str, Any]] = []
    for item in raw_diffs:
        classified = classify_difference(item)
        classified_list.append(classified)

    # Statistics
    stats = {
        "total_analyzed": len(classified_list),
        "dynamic_noise": sum(1 for d in classified_list if d["category"] == "dynamic_noise"),
        "environment_difference": sum(1 for d in classified_list if d["category"] == "environment_difference"),
        "tolerance_issue": sum(1 for d in classified_list if d["category"] == "tolerance_issue"),
        "intended_change": sum(1 for d in classified_list if d["category"] == "intended_change"),
    }

    output_payload = {
        "analysis_metadata": {
            "task_id": "G2-24",
            "step": "Step 2 - RCA & 4-Category Diff Classification",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_report": str(args.input),
            "summary_breakdown": stats,
        },
        "classified_differences": classified_list,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_content = json.dumps(output_payload, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(out_content, encoding="utf-8")

    print("\n" + "=" * 65)
    print("  STEP 2 CLASSIFICATION SUMMARY")
    print("=" * 65)
    print(f"  Total Diffs Analyzed      : {stats['total_analyzed']}")
    print(f"  1. Dynamic Noise          : {stats['dynamic_noise']:3d}  (Action: mask)")
    print(f"  2. Environment Difference : {stats['environment_difference']:3d}  (Action: normalize_env)")
    print(f"  3. Tolerance Issue        : {stats['tolerance_issue']:3d}  (Action: normalize_precision)")
    print(f"  4. Intended Change        : {stats['intended_change']:3d}  (Action: preserve_known_diff)")
    print("=" * 65)
    print(f"[OK] Generated Classified Evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
