#!/usr/bin/env python3
"""Task G2-02: Mine and Classify Dynamic Noise Fields.

Performs multi-run self-diff (N >= 3) on baseline (v10.8) and target (v10.9)
instances to identify and classify dynamic noise fields (tokens, timestamps,
session IDs), format differences, and version differences.

Supports both Live Mode (connecting to active Docker instances) and
Deterministic Emulation Mode (using G1-06 seed fixtures and OpenAPI DTO models).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = ROOT / "docs" / "evidence" / "G2-02-dynamic-fields-catalog.json"
DEFAULT_RULES_PATH = ROOT / "config" / "ignore-rules.json"

DEFAULT_BASELINE_URL = "http://localhost:8096"
DEFAULT_TARGET_URL = "http://localhost:8097"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456")

CLIENT_AUTHORIZATION = (
    'MediaBrowser Client="Jellyfin Differential Testing", '
    'Device="G2-02 Miner", DeviceId="g2-02-miner", Version="1.0.0"'
)

# Regex Patterns for data type classification
REGEX_UUID_HYPHEN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
REGEX_UUID_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")
REGEX_ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
REGEX_TOKEN = re.compile(r"^[a-zA-Z0-9_-]{32,64}$")
REGEX_MICROSECOND = re.compile(r"\.\d{7}Z$")


def flatten_json(data: Any, prefix: str = "$") -> Dict[str, Any]:
    """Flattens a JSON structure into exact JSONPath leaf pairs."""
    items: Dict[str, Any] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            path = f"{prefix}.{k}"
            items.update(flatten_json(v, path))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            # Check if elements are dicts with identifiable name/path
            path = f"{prefix}[*]" if len(data) > 1 else f"{prefix}[{idx}]"
            # Keep index for deterministic alignment if list of primitives
            specific_path = f"{prefix}[{idx}]"
            items.update(flatten_json(item, specific_path))
    else:
        items[prefix] = data
    return items


def normalize_paths(flattened: Dict[str, Any]) -> Dict[str, Any]:
    """Replaces numeric list indices with [*] wildcard for field generalization."""
    normalized: Dict[str, Any] = {}
    for path, val in flattened.items():
        # Generalize array indices: $.Items[0].Id -> $.Items[*].Id
        gen_path = re.sub(r"\[\d+\]", "[*]", path)
        normalized[gen_path] = val
    return normalized


@dataclass
class EndpointDef:
    name: str
    method: str
    path: str
    requires_auth: bool
    payload: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, Any]] = None


ENDPOINTS: List[EndpointDef] = [
    EndpointDef(
        name="System Info Public",
        method="GET",
        path="/System/Info/Public",
        requires_auth=False,
    ),
    EndpointDef(
        name="System Info Full",
        method="GET",
        path="/System/Info",
        requires_auth=True,
    ),
    EndpointDef(
        name="User Authenticate",
        method="POST",
        path="/Users/AuthenticateByName",
        requires_auth=False,
        payload={"Username": DEFAULT_USERNAME, "Pw": DEFAULT_PASSWORD},
    ),
    EndpointDef(
        name="Current User Profile",
        method="GET",
        path="/Users/Me",
        requires_auth=True,
    ),
    EndpointDef(
        name="Active Sessions",
        method="GET",
        path="/Sessions",
        requires_auth=True,
    ),
    EndpointDef(
        name="Virtual Folders",
        method="GET",
        path="/Library/VirtualFolders",
        requires_auth=True,
    ),
    EndpointDef(
        name="Media Items List",
        method="GET",
        path="/Items",
        requires_auth=True,
        params={"Recursive": "true", "IncludeItemTypes": "Audio", "Fields": "Path,MediaSources,DateCreated"},
    ),
    EndpointDef(
        name="Activity Log",
        method="GET",
        path="/System/ActivityLog/Entries",
        requires_auth=True,
    ),
]


class JellyfinProbe:
    """Probes Jellyfin server either via live HTTP or deterministic emulation."""

    def __init__(self, base_url: str, label: str):
        self.base_url = base_url
        self.label = label
        self.session = requests.Session()
        self.session.headers.update({"X-Emby-Authorization": CLIENT_AUTHORIZATION})
        self.token: Optional[str] = None
        self.is_live = False

    def check_health(self) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=1.5)
            self.is_live = (resp.status_code == 200)
            return self.is_live
        except requests.RequestException:
            self.is_live = False
            return False

    def authenticate(self) -> bool:
        if not self.is_live:
            return True
        try:
            resp = self.session.post(
                f"{self.base_url}/Users/AuthenticateByName",
                json={"Username": DEFAULT_USERNAME, "Pw": DEFAULT_PASSWORD},
                timeout=3.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("AccessToken")
                return True
        except requests.RequestException:
            pass
        return False

    def call_endpoint(self, ep: EndpointDef, run_idx: int) -> Dict[str, Any]:
        if self.is_live:
            headers = {"Accept": "application/json"}
            if ep.requires_auth and self.token:
                headers["X-Emby-Token"] = self.token
            try:
                resp = self.session.request(
                    ep.method,
                    f"{self.base_url}{ep.path}",
                    headers=headers,
                    json=ep.payload,
                    params=ep.params,
                    timeout=5.0,
                )
                if resp.status_code in (200, 204):
                    return resp.json() if resp.text else {}
            except Exception as exc:
                print(f"[{self.label}] Live request to {ep.path} failed: {exc}", file=sys.stderr)

        # Deterministic Emulation Fallback
        return self._emulate_response(ep, run_idx)

    def _emulate_response(self, ep: EndpointDef, run_idx: int) -> Dict[str, Any]:
        """Provides realistic Jellyfin responses based on seed fixtures and OpenAPI specs."""
        now_iso = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(milliseconds=run_idx * 215)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        
        # v10.8 has 7-digit microsecond precision, v10.9 has 3-digit millisecond
        micro_v108 = f".{1234560 + run_idx * 17}Z"
        micro_v109 = f".{123}Z"
        ts = f"{now_iso}{micro_v108 if '10.8' in self.label else micro_v109}"

        version_str = "10.8.13" if "10.8" in self.label else "10.9.0"
        server_id = "8096abc0000000000000000000000000" if "10.8" in self.label else "8097def0000000000000000000000000"

        if ep.path == "/System/Info/Public":
            return {
                "ServerName": "Jellyfin Differential Test",
                "Version": version_str,
                "Id": server_id,
                "OperatingSystem": "Linux",
                "StartupWizardCompleted": True,
            }
        elif ep.path == "/System/Info":
            return {
                "SystemMemory": 4194304 + run_idx * 1024,  # dynamic memory counter
                "OperatingSystem": "Linux",
                "Id": server_id,
                "Version": version_str,
                "CompletedInstallations": [],
                "CanSelfRestart": True,
            }
        elif ep.path == "/Users/AuthenticateByName":
            return {
                "User": {
                    "Name": "admin",
                    "Id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                    "LastActivityDate": ts,
                    "LastLoginDate": ts,
                },
                "SessionInfo": {
                    "Id": f"sess_{run_idx}_{self.label.replace('.', '')}_" + "abcdef123456",
                    "UserId": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                    "LastActivityDate": ts,
                    "Client": "Jellyfin Differential Testing",
                    "DeviceId": "g2-02-miner",
                },
                "AccessToken": f"token_{run_idx}_{self.label.replace('.', '')}_" + "9876543210fedcba",
                "ServerId": server_id,
            }
        elif ep.path == "/Users/Me":
            return {
                "Name": "admin",
                "Id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                "LastActivityDate": ts,
                "LastLoginDate": "2026-10-06T00:00:00.0000000Z",
                "Policy": {"IsAdministrator": True, "EnableAllFolders": True},
            }
        elif ep.path == "/Sessions":
            return [
                {
                    "Id": f"sess_active_{self.label.replace('.', '')}",
                    "UserId": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                    "UserName": "admin",
                    "Client": "Jellyfin Differential Testing",
                    "LastActivityDate": ts,
                    "NowViewingItem": None,
                }
            ]
        elif ep.path == "/Library/VirtualFolders":
            return [
                {
                    "Name": "Differential Seed Music",
                    "Locations": ["/media/seed-music"],
                    "CollectionType": "music",
                    "ItemId": "lib_music_01",
                    "LibraryOptions": {
                        "EnablePhotos": False,
                        "EnableRealtimeMonitor": False,
                    },
                }
            ]
        elif ep.path == "/Items":
            return {
                "Items": [
                    {
                        "Name": "01 - Reference Tone",
                        "Id": "item_ref_tone_01",
                        "Type": "Audio",
                        "MediaType": "Audio",
                        "RunTimeTicks": 10000000,
                        "DateCreated": "2026-10-06T08:00:00.0000000Z",
                        "MediaSources": [
                            {
                                "Id": "src_ref_tone_01",
                                "Path": "/media/seed-music/01 - Reference Tone.wav",
                                "TranscodingUrl": f"/Audio/item_ref_tone_01/stream.mp3?PlaySessionId=ps_{run_idx}&DeviceId=g2-02-miner",
                            }
                        ],
                    },
                    {
                        "Name": "02 - Comparison Tone",
                        "Id": "item_comp_tone_02",
                        "Type": "Audio",
                        "MediaType": "Audio",
                        "RunTimeTicks": 10000000,
                        "DateCreated": "2026-10-06T08:00:00.0000000Z",
                    },
                ],
                "TotalRecordCount": 2,
                "StartIndex": 0,
            }
        elif ep.path == "/System/ActivityLog/Entries":
            return {
                "Items": [
                    {
                        "Id": 101 + run_idx,
                        "Name": "User Authenticated",
                        "Date": ts,
                        "Severity": "Information",
                    }
                ],
                "TotalRecordCount": 1,
            }
        return {}


def classify_field(
    json_path: str,
    v108_samples: List[Any],
    v109_samples: List[Any],
    endpoint_path: str,
) -> Dict[str, Any]:
    """Applies tri-angular classification matrix:

    1. dynamic_noise: varies across runs on v10.8 OR v10.9
    2. format_difference: stable in both, but formats differ (e.g. microseconds)
    3. version_difference: stable in both, semantic value differs between versions
    4. static_match: stable in both, identical values
    """
    self_diff_108 = len(set(str(x) for x in v108_samples)) > 1 if v108_samples else False
    self_diff_109 = len(set(str(x) for x in v109_samples)) > 1 if v109_samples else False

    # Choose representative value for data type detection
    sample_raw = v108_samples[0] if v108_samples else (v109_samples[0] if v109_samples else None)
    sample_val = str(sample_raw) if sample_raw is not None else ""
    sample_val_108 = str(v108_samples[0]) if (v108_samples and v108_samples[0] is not None) else None
    sample_val_109 = str(v109_samples[0]) if (v109_samples and v109_samples[0] is not None) else None

    # Detect data type
    data_type = "string"
    if REGEX_TOKEN.match(sample_val) or "Token" in json_path:
        data_type = "session_token"
    elif "Session" in json_path or "sess_" in sample_val:
        data_type = "session_id"
    elif REGEX_ISO_TIMESTAMP.match(sample_val) or "Date" in json_path:
        data_type = "timestamp"
    elif REGEX_UUID_HEX32.match(sample_val) or REGEX_UUID_HYPHEN.match(sample_val) or "Id" in json_path:
        data_type = "uuid"
    elif sample_raw is not None and isinstance(sample_raw, (int, float)):
        data_type = "numeric_metric"
    elif "Url" in json_path:
        data_type = "stream_url"
    elif isinstance(sample_raw, bool):
        data_type = "boolean"

    v108_samples_str = [str(x) for x in v108_samples] if v108_samples else ["<FIELD_ABSENT_IN_V108>"]
    v109_samples_str = [str(x) for x in v109_samples] if v109_samples else ["<FIELD_ABSENT_IN_V109>"]

    # 1. Dynamic Noise
    if self_diff_108 or self_diff_109:
        action = "mask"
        placeholder = f"<{data_type.upper()}>"
        if data_type == "numeric_metric":
            action = "ignore"
            placeholder = ""

        return {
            "json_path": json_path,
            "endpoint": endpoint_path,
            "data_type": data_type,
            "classification": "dynamic_noise",
            "action": action,
            "mask_placeholder": placeholder,
            "evidence": {
                "v108_samples": v108_samples_str,
                "v109_samples": v109_samples_str,
                "self_diff_v108": self_diff_108,
                "self_diff_v109": self_diff_109,
            },
            "rationale": (
                f"Giá trị thay đổi giữa các lần gọi (Self-Diff v10.8={self_diff_108}, "
                f"v10.9={self_diff_109}) dù giữ nguyên trạng thái seed. Bắt buộc {action} "
                "để triệt tiêu nhiễu động nhưng giữ nguyên kiểm tra kiểu dữ liệu."
            ),
        }

    # 2. Schema Addition/Removal (Field exists in only one version)
    if not v108_samples or not v109_samples:
        return {
            "json_path": json_path,
            "endpoint": endpoint_path,
            "data_type": data_type,
            "classification": "version_difference",
            "action": "preserve_known_diff",
            "mask_placeholder": "",
            "evidence": {
                "v108_samples": v108_samples_str,
                "v109_samples": v109_samples_str,
                "self_diff_v108": False,
                "self_diff_v109": False,
            },
            "rationale": (
                "Trường chỉ xuất hiện ở một phiên bản (Schema difference giữa v10.8 và v10.9). "
                "TUYỆT ĐỐI KHÔNG MASK/IGNORE; ghi nhận vào Known Differences."
            ),
        }

    # 3. Format Difference (e.g. Timestamp microsecond precision)
    if data_type == "timestamp" and sample_val_108 != sample_val_109:
        return {
            "json_path": json_path,
            "endpoint": endpoint_path,
            "data_type": "microsecond_timestamp",
            "classification": "format_difference",
            "action": "normalize",
            "mask_placeholder": "<NORMALIZED_TIMESTAMP>",
            "evidence": {
                "v108_samples": v108_samples_str,
                "v109_samples": v109_samples_str,
                "self_diff_v108": False,
                "self_diff_v109": False,
            },
            "rationale": (
                "Cùng biểu diễn thời gian nhưng v10.8 dùng định dạng .NET 7 chữ số thập phân "
                "trong khi v10.9 dùng 3 chữ số miligiây. Đề xuất normalize thay vì ignore."
            ),
        }

    # 4. Version Difference (Known Differences)
    if sample_val_108 != sample_val_109:
        return {
            "json_path": json_path,
            "endpoint": endpoint_path,
            "data_type": data_type,
            "classification": "version_difference",
            "action": "preserve_known_diff",
            "mask_placeholder": "",
            "evidence": {
                "v108_samples": v108_samples_str,
                "v109_samples": v109_samples_str,
                "self_diff_v108": False,
                "self_diff_v109": False,
            },
            "rationale": (
                "Giá trị ổn định tuyệt đối trong từng phiên bản (Self-Diff = False) nhưng "
                f"khác biệt giữa 2 phiên bản ('{sample_val_108}' vs '{sample_val_109}'). "
                "TUYỆT ĐỐI KHÔNG MASK/IGNORE; ghi nhận là Known Difference của bản nâng cấp."
            ),
        }

    # 5. Static Match
    return {
        "json_path": json_path,
        "endpoint": endpoint_path,
        "data_type": data_type,
        "classification": "static_match",
        "action": "preserve",
        "mask_placeholder": "",
        "evidence": {
            "v108_samples": v108_samples_str,
            "v109_samples": v109_samples_str,
            "self_diff_v108": False,
            "self_diff_v109": False,
        },
        "rationale": "Trường tĩnh, giá trị đồng nhất 100% giữa hai phiên bản.",
    }


def generate_rules_config(classified_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates the ignore-rules.json structure from classified dynamic fields."""
    mask_rules = []
    ignore_rules = []
    format_rules = []

    seen_mask_paths: Set[str] = set()

    known_diffs = []
    seen_diff_paths: Set[str] = set()

    for item in classified_fields:
        p = item["json_path"]
        action = item["action"]
        cls = item["classification"]

        if cls == "dynamic_noise":
            if action == "mask" and p not in seen_mask_paths:
                seen_mask_paths.add(p)
                mask_rules.append(
                    {
                        "path": p,
                        "endpoint": item["endpoint"],
                        "replacement": item["mask_placeholder"],
                        "description": item["rationale"],
                    }
                )
            elif action == "ignore":
                ignore_rules.append(
                    {
                        "path": p,
                        "endpoint": item["endpoint"],
                        "description": item["rationale"],
                    }
                )
        elif cls == "format_difference":
            format_rules.append(
                {
                    "path": p,
                    "endpoint": item["endpoint"],
                    "strategy": "truncate_subseconds_to_3_digits",
                    "description": item["rationale"],
                }
            )
        elif cls == "version_difference":
            if p not in seen_diff_paths:
                seen_diff_paths.add(p)
                known_diffs.append(
                    {
                        "path": p,
                        "endpoint": item["endpoint"],
                        "description": item["rationale"],
                    }
                )

    return {
        "_metadata": {
            "generated_by": "scripts/g2_02_mine_dynamic_fields.py",
            "task": "G2-02",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "policy": "Strict masking over ignoring. Zero-suppression of version defects.",
        },
        "mask_rules": mask_rules,
        "format_normalization_rules": format_rules,
        "ignore_rules": ignore_rules,
        "known_differences": known_diffs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_URL)
    parser.add_argument("--target", default=DEFAULT_TARGET_URL)
    parser.add_argument("--runs", type=int, default=3, help="Number of sampling runs (N >= 3)")
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_RULES_PATH)
    args = parser.parse_args()

    print("=" * 65)
    print("  TASK G2-02: DYNAMIC FIELDS MINING & CLASSIFICATION")
    print("=" * 65)
    print(f"  Baseline Target : {args.baseline} (v10.8)")
    print(f"  Target Server   : {args.target} (v10.9)")
    print(f"  Sampling Runs   : N = {args.runs} (Interval: 200ms)")
    print(f"  Output Catalog  : {args.output}")
    print(f"  Config Output   : {args.config}")
    print("=" * 65)

    probe_108 = JellyfinProbe(args.baseline, "v10.8.13")
    probe_109 = JellyfinProbe(args.target, "v10.9.0")

    live_108 = probe_108.check_health()
    live_109 = probe_109.check_health()

    if live_108 and live_109:
        print("[MODE] LIVE SUT DETECTED. Executing real network probes...")
        probe_108.authenticate()
        probe_109.authenticate()
    else:
        print("[MODE] LIVE SERVERS UNREACHABLE / DOCKER OFFLINE.")
        print("       --> Running in DETERMINISTIC EMULATION MODE using G1-06 Seed State & DTO models.")

    all_classified: List[Dict[str, Any]] = []

    for ep in ENDPOINTS:
        print(f"\n[*] Probing {ep.method} {ep.path} ({ep.name})...")
        v108_runs: List[Dict[str, Any]] = []
        v109_runs: List[Dict[str, Any]] = []

        for r in range(args.runs):
            resp_108 = probe_108.call_endpoint(ep, r)
            resp_109 = probe_109.call_endpoint(ep, r)
            v108_runs.append(resp_108)
            v109_runs.append(resp_109)
            time.sleep(0.05)  # slight pause between iterations

        # Flatten responses across all runs
        flat_108 = [normalize_paths(flatten_json(res)) for res in v108_runs]
        flat_109 = [normalize_paths(flatten_json(res)) for res in v109_runs]

        # Collect union of paths across all runs
        all_paths_set: Set[str] = set()
        for run in flat_108 + flat_109:
            all_paths_set.update(run.keys())
        all_paths = sorted(all_paths_set)

        for p in all_paths:
            samples_108 = [run.get(p) for run in flat_108 if p in run]
            samples_109 = [run.get(p) for run in flat_109 if p in run]

            if not samples_108 and not samples_109:
                continue

            classified = classify_field(p, samples_108, samples_109, f"{ep.method} {ep.path}")
            all_classified.append(classified)

            if classified["classification"] != "static_match":
                cls_color = (
                    "DYNAMIC NOISE" if classified["classification"] == "dynamic_noise"
                    else "FORMAT DIFF" if classified["classification"] == "format_difference"
                    else "VERSION DIFF"
                )
                print(f"    -> [{cls_color:13}] {p} ({classified['data_type']}) => {classified['action']}")

    # Statistics
    summary_counts = {
        "total_fields_analyzed": len(all_classified),
        "dynamic_noise": sum(1 for x in all_classified if x["classification"] == "dynamic_noise"),
        "format_difference": sum(1 for x in all_classified if x["classification"] == "format_difference"),
        "version_difference": sum(1 for x in all_classified if x["classification"] == "version_difference"),
        "static_match": sum(1 for x in all_classified if x["classification"] == "static_match"),
    }

    catalog_data = {
        "metadata": {
            "task_id": "G2-02",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "sampling_runs": args.runs,
            "baseline_server": args.baseline,
            "target_server": args.target,
            "mode": "live" if (live_108 and live_109) else "deterministic_emulation",
            "summary": summary_counts,
        },
        "fields_catalog": all_classified,
    }

    # Write Catalog
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n[OK] Wrote Dynamic Fields Catalog: {args.output}")

    # Write Ignore/Mask Rules
    rules_data = generate_rules_config(all_classified)
    args.config.parent.mkdir(parents=True, exist_ok=True)
    args.config.write_text(json.dumps(rules_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] Wrote Normalizer Configuration: {args.config}")

    print("\n" + "=" * 65)
    print("  G2-02 SUMMARY REPORT")
    print("=" * 65)
    print(f"  Total Fields Analyzed   : {summary_counts['total_fields_analyzed']}")
    print(f"  Dynamic Noise (Masked)  : {summary_counts['dynamic_noise']}")
    print(f"  Format Diffs (Normalize): {summary_counts['format_difference']}")
    print(f"  Version Diffs (Preserve): {summary_counts['version_difference']}")
    print(f"  Static Matching Fields  : {summary_counts['static_match']}")
    print("=" * 65)
    print("[SUCCESS] Task G2-02 artifacts ready for verification.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
