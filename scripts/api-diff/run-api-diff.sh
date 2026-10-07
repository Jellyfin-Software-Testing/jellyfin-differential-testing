#!/usr/bin/env bash
# ============================================================
# G1-09: API Contract Differential Baseline Generator (Linux/macOS)
# Author  : Tech Writer — Jellyfin Differential Testing Framework
# Task    : G1-09 — Build API Contract Differential Baseline
# Tool    : oasdiff (https://github.com/Tufin/oasdiff)
# Output  : reports/api-diff-report.json
# ============================================================
# USAGE:
#   chmod +x scripts/api-diff/run-api-diff.sh
#   ./scripts/api-diff/run-api-diff.sh
#   ./scripts/api-diff/run-api-diff.sh specs/swagger_v1.json specs/swagger_v2.json reports/api-diff-report.json
# ============================================================

set -euo pipefail

BASELINE_SPEC="${1:-specs/swagger_v1.json}"
TARGET_SPEC="${2:-specs/swagger_v2.json}"
OUTPUT_REPORT="${3:-reports/api-diff-report.json}"
OASDIFF="${OASDIFF_PATH:-oasdiff}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")
REPORT_ID="G1-09-api-diff-$(date +%Y%m%d)"

echo ""
echo "========================================="
echo "  G1-09: API Contract Differential Baseline"
echo "========================================="
echo "  Baseline : $BASELINE_SPEC"
echo "  Target   : $TARGET_SPEC"
echo "  Output   : $OUTPUT_REPORT"
echo ""

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------
[[ -f "$BASELINE_SPEC" ]] || { echo "ERROR: Baseline spec not found: $BASELINE_SPEC"; exit 2; }
[[ -f "$TARGET_SPEC"   ]] || { echo "ERROR: Target spec not found: $TARGET_SPEC"; exit 2; }

# ---------------------------------------------------------------------------
# SHA256 checksums
# ---------------------------------------------------------------------------
if command -v sha256sum &>/dev/null; then
    SHA256_V1=$(sha256sum "$BASELINE_SPEC" | awk '{print $1}')
    SHA256_V2=$(sha256sum "$TARGET_SPEC"   | awk '{print $1}')
elif command -v shasum &>/dev/null; then
    SHA256_V1=$(shasum -a 256 "$BASELINE_SPEC" | awk '{print $1}')
    SHA256_V2=$(shasum -a 256 "$TARGET_SPEC"   | awk '{print $1}')
else
    SHA256_V1="unavailable"
    SHA256_V2="unavailable"
fi
echo "  SHA256 (v1): $SHA256_V1"
echo "  SHA256 (v2): $SHA256_V2"

# ---------------------------------------------------------------------------
# Verify oasdiff
# ---------------------------------------------------------------------------
if ! command -v "$OASDIFF" &>/dev/null; then
    echo ""
    echo "ERROR: oasdiff not found. Install with:"
    echo "  curl -sSfL https://raw.githubusercontent.com/Tufin/oasdiff/main/install.sh | sh -s -- -b /usr/local/bin"
    exit 2
fi
OASDIFF_VERSION=$("$OASDIFF" version 2>&1 || echo "unknown")
echo "  Tool: oasdiff $OASDIFF_VERSION"
echo ""

# ---------------------------------------------------------------------------
# Run oasdiff
# ---------------------------------------------------------------------------
echo "[1/3] Detecting breaking changes..."
BREAKING_JSON=$("$OASDIFF" breaking "$BASELINE_SPEC" "$TARGET_SPEC" --format json 2>&1) || BREAKING_EXIT=$?
BREAKING_EXIT="${BREAKING_EXIT:-0}"

echo "[2/3] Running full schema diff..."
DIFF_JSON=$("$OASDIFF" diff "$BASELINE_SPEC" "$TARGET_SPEC" --format json 2>&1) || true

# ---------------------------------------------------------------------------
# Build report with Python (available on most CI environments)
# ---------------------------------------------------------------------------
echo "[3/3] Writing $OUTPUT_REPORT..."

mkdir -p "$(dirname "$OUTPUT_REPORT")"

python3 - <<PYTHON_SCRIPT
import json, sys, os
from datetime import datetime

breaking_raw  = '''${BREAKING_JSON}'''
diff_raw      = '''${DIFF_JSON}'''

def safe_parse(raw):
    try:
        return json.loads(raw)
    except:
        return None

breaking_obj = safe_parse(breaking_raw)
diff_obj     = safe_parse(diff_raw)

breaking_list     = []
non_breaking_list = []
endpoints_added   = []
endpoints_removed = []
breaking_count    = 0

# Extract breaking changes
change_list = []
if isinstance(breaking_obj, list):
    change_list = breaking_obj
elif isinstance(breaking_obj, dict):
    change_list = breaking_obj.get("breakingChanges", [])

for i, change in enumerate(change_list, 1):
    code = change.get("id", change.get("code", "UNKNOWN"))
    breaking_list.append({
        "change_id":   f"BC-{i:03d}",
        "severity":    "BREAKING",
        "category":    code.replace("-", "_").upper(),
        "path":        change.get("path", change.get("operationId", "unknown")),
        "method":      (change.get("method") or "UNKNOWN").upper(),
        "description": change.get("text", change.get("message", "Breaking change detected")),
        "rca_hint":    "Trace via: git log --all -S '<field>' -- '**/*Controller.cs'"
    })
    breaking_count += 1

# Extract endpoints from diff
if isinstance(diff_obj, dict) and "paths" in diff_obj:
    paths = diff_obj["paths"]
    endpoints_added   = paths.get("added",   [])
    endpoints_removed = paths.get("deleted", [])
    nbc_idx = 1
    for path_key in (paths.get("modified") or {}).keys():
        non_breaking_list.append({
            "change_id":   f"NBC-{nbc_idx:03d}",
            "severity":    "NON_BREAKING",
            "category":    "PATH_MODIFIED",
            "path":        path_key,
            "method":      "MULTIPLE",
            "description": "Path modified; no breaking signature detected"
        })
        nbc_idx += 1
    for i, ep in enumerate(endpoints_added, 1):
        non_breaking_list.append({
            "change_id":   f"NBC-EP-{i:03d}",
            "severity":    "NON_BREAKING",
            "category":    "ENDPOINT_ADDED",
            "path":        ep,
            "method":      "MULTIPLE",
            "description": "New endpoint added. Backward compatible."
        })

has_breaking = breaking_count > 0
risk = "LOW" if breaking_count == 0 else "MEDIUM" if breaking_count <= 2 else "HIGH" if breaking_count <= 5 else "CRITICAL"

report = {
    "report_metadata": {
        "report_id":    "${REPORT_ID}",
        "task_id":      "G1-09",
        "generated_at": "${TIMESTAMP}",
        "generated_by": "Tech Writer / oasdiff",
        "tool":         "oasdiff",
        "tool_version": "${OASDIFF_VERSION}",
        "baseline_version": {
            "label":       "jellyfin-baseline",
            "source_file": "${BASELINE_SPEC}",
            "sha256":      "${SHA256_V1}"
        },
        "target_version": {
            "label":       "jellyfin-target",
            "source_file": "${TARGET_SPEC}",
            "sha256":      "${SHA256_V2}"
        }
    },
    "summary": {
        "total_breaking_changes":     breaking_count,
        "total_non_breaking_changes": len(non_breaking_list),
        "total_endpoints_added":      len(endpoints_added),
        "total_endpoints_removed":    len(endpoints_removed),
        "risk_level":                 risk,
        "verdict":                    "BREAKING_CHANGES_DETECTED" if has_breaking else "COMPATIBLE"
    },
    "breaking_changes":     breaking_list,
    "non_breaking_changes": non_breaking_list,
    "endpoints_inventory": {
        "added":   endpoints_added,
        "removed": endpoints_removed
    },
    "ci_machine_data": {
        "machine_readable":      True,
        "has_breaking_changes":  has_breaking,
        "breaking_change_count": breaking_count,
        "should_block_merge":    has_breaking,
        "recommended_action":    "REQUIRE_MANUAL_REVIEW" if has_breaking else "AUTO_MERGE_ALLOWED"
    }
}

with open("${OUTPUT_REPORT}", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"  Breaking Changes  : {breaking_count}")
print(f"  Non-Breaking      : {len(non_breaking_list)}")
print(f"  Risk Level        : {risk}")
PYTHON_SCRIPT

echo ""
echo "========================================="
VERDICT=$(python3 -c "import json; d=json.load(open('${OUTPUT_REPORT}')); print(d['summary']['verdict'])")
if [ "$VERDICT" = "BREAKING_CHANGES_DETECTED" ]; then
    echo "  VERDICT : $VERDICT — MANUAL REVIEW REQUIRED"
    echo "  Report  : $OUTPUT_REPORT"
    echo "========================================="
    exit 1
else
    echo "  VERDICT : $VERDICT — Safe to proceed"
    echo "  Report  : $OUTPUT_REPORT"
    echo "========================================="
    exit 0
fi
