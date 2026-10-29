#!/usr/bin/env python3
"""Task G2-28: Live Verification Script for Search/Filter Defect #2.

Connects to Jellyfin v10.8.13 (http://localhost:8096) and Jellyfin v10.9.0 (http://localhost:8097),
authenticates as admin, executes Search/Filter API requests on both servers,
and displays the exact live responses side-by-side to detect Behavioral / Schema Drift.

Outputs:
  - Prints live comparison to console
  - Saves raw evidence to docs/evidence/G2_28/live-defect-2-evidence.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Fix Windows console UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import requests

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_EVIDENCE = ROOT / "docs" / "evidence" / "G2_28" / "live-defect-2-evidence.json"

URL_V108 = "http://localhost:8096"
URL_V109 = "http://localhost:8097"

USERNAME = os.environ.get("JELLYFIN_ADMIN_USER", "admin")
PASSWORD = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456")

CLIENT_AUTH = (
    'MediaBrowser Client="Jellyfin Search-Filter Defect-2 Probe", '
    'Device="PowerShell", DeviceId="probe-defect-2", Version="1.0.0"'
)


def login(base_url: str) -> tuple[str, str]:
    """Logs into Jellyfin and returns (userId, accessToken)."""
    login_url = f"{base_url}/Users/AuthenticateByName"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Emby-Authorization": CLIENT_AUTH,
    }
    payload = {"Username": USERNAME, "Pw": PASSWORD}
    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("AccessToken", "")
            user_id = data.get("User", {}).get("Id", "")
            return user_id, token
    except Exception as exc:
        print(f"[-] Không thể kết nối tới {base_url}: {exc}")
    return "", ""


def test_endpoint(base_url: str, path: str, token: str) -> Dict[str, Any]:
    """Sends request to target endpoint and records response."""
    test_url = f"{base_url}{path}"
    headers = {
        "Accept": "application/json",
        "X-Emby-Token": token,
        "X-Emby-Authorization": CLIENT_AUTH,
    }
    try:
        resp = requests.get(test_url, headers=headers, timeout=5.0)
        body = None
        try:
            body = resp.json()
        except Exception:
            body = resp.text

        return {
            "target_url": test_url,
            "status_code": resp.status_code,
            "reason": resp.reason,
            "content_type": resp.headers.get("Content-Type", ""),
            "body": body,
        }
    except Exception as exc:
        return {
            "target_url": test_url,
            "status_code": 0,
            "reason": "Connection Error",
            "content_type": "",
            "body": str(exc),
        }


def main() -> None:
    print("=" * 75)
    print("  TASK G2-28: KIỂM TRA THỰC NGHIỆM SEARCH / FILTER DEFECT #2")
    print("  Target Scope: Search Hints & Query Filters API")
    print("=" * 75)

    # 1. Check connectivity & login
    print("\n[1] Đang kết nối tới 2 máy chủ Docker...")
    print(f"  • Jellyfin v10.8 (Baseline): {URL_V108}")
    print(f"  • Jellyfin v10.9 (Target)  : {URL_V109}")

    id_108, token_108 = login(URL_V108)
    id_109, token_109 = login(URL_V109)

    if not token_108 and not token_109:
        print("\n[!] CẢNH BÁO: Không thể kết nối tới cả 2 máy chủ Jellyfin.")
        print("    Vui lòng đảm bảo Docker Desktop đang chạy:")
        print("    👉 Lệnh: docker compose -f docker/docker-compose.yml up -d\n")
        return

    print(f"  [+] Đăng nhập v10.8 thành công! Token: {token_108[:10]}...")
    print(f"  [+] Đăng nhập v10.9 thành công! Token: {token_109[:10]}...")

    # 2. Candidate Search/Filter Endpoints
    test_endpoints = [
        ("Kịch bản 1 (Search Hints)", "/Search/Hints?searchTerm=test"),
        ("Kịch bản 2 (Library Query Filters)", "/Items/Filters"),
        ("Kịch bản 3 (Search với Enum Filter fields)", "/Items?searchTerm=sample&fields=SyncInfo,BasicSyncInfo"),
    ]

    results = []

    print("\n[2] Bắt đầu gửi các luồng kiểm thử Search/Filter đồng thời tới 2 server...")

    for title, path in test_endpoints:
        print("\n" + "-" * 75)
        print(f"  >>> {title}: {path}")
        print("-" * 75)

        res_108 = test_endpoint(URL_V108, path, token_108)
        res_109 = test_endpoint(URL_V109, path, token_109)

        st_108 = res_108.get("status_code")
        st_109 = res_109.get("status_code")

        print(f"  • v10.8.13 (Cổng 8096): HTTP {st_108} {res_108.get('reason')}")
        print(f"  • v10.9.0  (Cổng 8097): HTTP {st_109} {res_109.get('reason')}")

        # Check differences
        is_status_diff = (st_108 != st_109)
        body_108 = res_108.get("body")
        body_109 = res_109.get("body")

        count_108 = len(body_108.get("SearchHints", [])) if isinstance(body_108, dict) and "SearchHints" in body_108 else (len(body_108.get("Items", [])) if isinstance(body_108, dict) and "Items" in body_108 else None)
        count_109 = len(body_109.get("SearchHints", [])) if isinstance(body_109, dict) and "SearchHints" in body_109 else (len(body_109.get("Items", [])) if isinstance(body_109, dict) and "Items" in body_109 else None)

        if count_108 is not None and count_109 is not None:
            print(f"    - Số bản ghi trả về: v10.8 = {count_108} | v10.9 = {count_109}")

        results.append({
            "scenario": title,
            "path": path,
            "baseline_v108": res_108,
            "target_v109": res_109,
            "status_mismatch": is_status_diff,
        })

    # 3. Save Raw Evidence
    OUTPUT_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    evidence_payload = {
        "defect_id": "DEFECT-02",
        "category": "SEARCH_FILTER_API_FAMILY",
        "test_results": results,
    }

    with open(OUTPUT_EVIDENCE, "w", encoding="utf-8") as f:
        json.dump(evidence_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 75)
    print("  KẾT LUẬN THỰC NGHIỆM:")
    print("  [+] Đã hoàn thành đo đạc đối soát trên 2 máy chủ live SUT.")
    print(f"  [+] Đã xuất file bằng chứng kiểm toán tại:")
    print(f"      {OUTPUT_EVIDENCE.relative_to(ROOT)}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
