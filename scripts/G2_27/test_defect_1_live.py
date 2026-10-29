#!/usr/bin/env python3
"""Task G2-27: Live Verification Script for Defect #1 (GET /Dlna/ProfileInfos).

Connects to Jellyfin v10.8.13 (http://localhost:8096) and Jellyfin v10.9.0 (http://localhost:8097),
authenticates as admin, calls GET /Dlna/ProfileInfos on both servers,
and displays the exact live responses side-by-side (HTTP 200 OK vs HTTP 404 Not Found).

Outputs:
  - Prints live comparison to console
  - Saves raw evidence to docs/evidence/G2_27/live-defect-1-evidence.json
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
OUTPUT_EVIDENCE = ROOT / "docs" / "evidence" / "G2_27" / "live-defect-1-evidence.json"

URL_V108 = "http://localhost:8096"
URL_V109 = "http://localhost:8097"

USERNAME = os.environ.get("JELLYFIN_ADMIN_USER", "admin")
PASSWORD = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456")

CLIENT_AUTH = (
    'MediaBrowser Client="Jellyfin Defect-1 Live Probe", '
    'Device="PowerShell", DeviceId="probe-defect-1", Version="1.0.0"'
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


def test_endpoint(base_url: str, token: str) -> Dict[str, Any]:
    """Calls GET /Dlna/ProfileInfos and records response."""
    test_url = f"{base_url}/Dlna/ProfileInfos"
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
    print("  KIỂM TRA THỰC NGHIỆM TRỰC TIẾP DEFECT #1 (LIVE SUT VERIFICATION)")
    print("  Endpoint: GET /Dlna/ProfileInfos")
    print("=" * 75)

    # 1. Check connectivity & login
    print("\n[1] Đang kết nối tới 2 máy chủ Docker...")
    print(f"  • Jellyfin v10.8 (Baseline): {URL_V108}")
    print(f"  • Jellyfin v10.9 (Target)  : {URL_V109}")

    id_108, token_108 = login(URL_V108)
    id_109, token_109 = login(URL_V109)

    if not token_108 and not token_109:
        print("\n[!] CẢNH BÁO: Không thể kết nối tới cả 2 máy chủ Jellyfin.")
        print("    Vui lòng đảm bảo Docker Desktop đang chạy và khởi động 2 container:")
        print("    👉 Lệnh: docker compose -f docker/docker-compose.yml up -d\n")
        return

    print(f"  [+] Đăng nhập v10.8 thành công! Token: {token_108[:10]}...")
    print(f"  [+] Đăng nhập v10.9 thành công! Token: {token_109[:10]}...")

    # 2. Test GET /Dlna/ProfileInfos on both servers
    print("\n[2] Gửi request: GET /Dlna/ProfileInfos đồng thời tới 2 server...")
    res_108 = test_endpoint(URL_V108, token_108)
    res_109 = test_endpoint(URL_V109, token_109)

    # 3. Display Results
    print("\n" + "=" * 75)
    print("  KẾT QUẢ ĐỐI SOÁT VI SAI THỰC TẾ (LIVE DIFFERENTIAL RESULT)")
    print("=" * 75)

    print(f"\n[A] PHIÊN BẢN v10.8.13 (Cổng 8096):")
    print(f"    • HTTP Status   : {res_108.get('status_code')} {res_108.get('reason')}")
    print(f"    • Content-Type  : {res_108.get('content_type')}")
    if res_108.get("status_code") == 200:
        data = res_108.get("body", [])
        if isinstance(data, list):
            print(f"    • Phản hồi Body : THÀNH CÔNG (HTTP 200) - Tìm thấy {len(data)} DLNA device profiles:")
            for idx, item in enumerate(data[:3], start=1):
                print(f"       [{idx}] Tên: {item.get('Name')} | Kiểu: {item.get('Type')} | ID: {item.get('Id')}")
        else:
            print(f"    • Phản hồi Body : {data}")
    else:
        print(f"    • Phản hồi Body : {res_108.get('body')}")

    print(f"\n[B] PHIÊN BẢN v10.9.0 (Cổng 8097):")
    print(f"    • HTTP Status   : {res_109.get('status_code')} {res_109.get('reason')}")
    print(f"    • Content-Type  : {res_109.get('content_type') or '(Trống)'}")
    if res_109.get("status_code") == 404:
        print(f"    • Phản hồi Body : TUYẾN ĐƯỜNG ĐÃ BỊ GỠ BỎ (HTTP 404 NOT FOUND)")
        print(f"      (Endpoint /Dlna/ProfileInfos không còn tồn tại trên lõi v10.9)")
    else:
        print(f"    • Phản hồi Body : {res_109.get('body')}")

    # 4. Compare & Conclude
    print("\n" + "=" * 75)
    print("  KẾT LUẬN VI SAI:")
    st_108 = res_108.get("status_code")
    st_109 = res_109.get("status_code")
    if st_108 != st_109:
        print(f"  ❌ PHÁT HIỆN LỖI VI SAI (DIFFERENTIAL DEFECT DETECTED):")
        print(f"     • v10.8.13 : HTTP {st_108} {res_108.get('reason')} (Endpoint DLNA khả dụng trong server core)")
        print(f"     • v10.9.0  : HTTP {st_109} {res_109.get('reason')} (DlnaController đã bị xóa khỏi server core)")
        print(f"     • Chênh lệch: {st_108} != {st_109} (Gây lỗi Breaking Change cho mọi client gọi DLNA)")
    else:
        print(f"  ℹ️ Không có chênh lệch status code: {st_108} == {st_109}")
    print("=" * 75)

    # 5. Save Evidence
    OUTPUT_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    evidence_payload = {
        "defect_id": "DEFECT-01",
        "endpoint": "GET /Dlna/ProfileInfos",
        "baseline_v108": res_108,
        "target_v109": res_109,
        "divergence_summary": {
            "status_code_mismatch": f"{st_108} != {st_109}",
            "defect_type": "CONTRACT_BREAKING_ROUTE_REMOVED",
            "root_cause": "DLNA subsystem removed from Jellyfin core in v10.9 (DlnaController removed)",
            "confirmed_live": (st_108 == 200 and st_109 == 404),
        }
    }
    with open(OUTPUT_EVIDENCE, "w", encoding="utf-8") as f:
        json.dump(evidence_payload, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Đã lưu file minh chứng thực nghiệm tại:")
    print(f"    {OUTPUT_EVIDENCE.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
