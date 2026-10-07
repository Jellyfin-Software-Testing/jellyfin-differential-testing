# G1-09: API Contract Differential Baseline — README

## Mô tả

Script tự động so sánh 2 phiên bản OpenAPI specification của Jellyfin, phát hiện breaking changes và xuất kết quả ra `reports/api-diff-report.json`.

**Task**: G1-09 — Build API Contract Differential Baseline  
**Owner**: Tech Writer  
**Tool**: [oasdiff](https://github.com/Tufin/oasdiff)

---

## Cài đặt `oasdiff`

```powershell
# Windows (winget)
winget install oasdiff

# Windows (scoop)
scoop install oasdiff

# Linux/macOS
curl -sSfL https://raw.githubusercontent.com/Tufin/oasdiff/main/install.sh | sh -s -- -b /usr/local/bin

# Verify
oasdiff -v
```

---

## Chuẩn bị Input

### Option A: Dùng file spec tĩnh (nếu đã có spec files)

```
specs/
├── swagger_v1.json    ← OpenAPI spec của Jellyfin v10.8.x
└── swagger_v2.json    ← OpenAPI spec của Jellyfin v10.9.x
```

Download spec từ GitHub Jellyfin:
```powershell
# v10.8.x
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/jellyfin/jellyfin/v10.8.13/Jellyfin.Api/openapi.json" -OutFile specs/swagger_v1.json

# v10.9.x  
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/jellyfin/jellyfin/v10.9.11/Jellyfin.Api/openapi.json" -OutFile specs/swagger_v2.json
```

### Option B: Fetch từ live instances (dùng Postman)

```powershell
# Cài Newman nếu chưa có
npm install -g newman

# Chạy collection
newman run scripts/api-diff/G1-09-api-diff.postman_collection.json `
  -e scripts/api-diff/env-local.json `
  --reporters cli,json `
  --reporter-json-export reports/newman-fetch-log.json
```

---

## Chạy Script

### Windows (PowerShell)

```powershell
# Chạy với default paths
.\scripts\api-diff\run-api-diff.ps1

# Chạy với custom paths
.\scripts\api-diff\run-api-diff.ps1 `
  -BaselineSpec ".\specs\swagger_v1.json" `
  -TargetSpec   ".\specs\swagger_v2.json" `
  -OutputReport ".\reports\api-diff-report.json"
```

### Linux/macOS (CI/CD)

```bash
chmod +x scripts/api-diff/run-api-diff.sh
./scripts/api-diff/run-api-diff.sh
```

---

## Output

File `reports/api-diff-report.json` được tạo với cấu trúc:

```
report_metadata     ← Audit trail: tool, version, SHA256, timestamp
summary             ← Tổng hợp: breaking count, risk level, verdict
breaking_changes    ← Danh sách breaking changes (BC-001, BC-002...)
non_breaking_changes← Danh sách non-breaking changes (NBC-001...)
endpoints_inventory ← Endpoints added/removed
ci_machine_data     ← Block dành cho CI/CD automation
```

### Exit Codes (CI/CD)

| Code | Ý nghĩa |
|------|---------|
| `0`  | Không có breaking changes — safe to merge |
| `1`  | Có breaking changes — block merge, cần review |
| `2`  | Script error (file không tồn tại, oasdiff lỗi) |

---

## Xem kết quả nhanh

```powershell
# Xem summary
Get-Content .\reports\api-diff-report.json | ConvertFrom-Json | Select-Object -ExpandProperty summary

# Xem breaking changes
Get-Content .\reports\api-diff-report.json | ConvertFrom-Json | Select-Object -ExpandProperty breaking_changes

# Check CI status
$report = Get-Content .\reports\api-diff-report.json | ConvertFrom-Json
if ($report.ci_machine_data.should_block_merge) {
    Write-Host "BLOCKED: $($report.ci_machine_data.breaking_change_count) breaking changes" -ForegroundColor Red
} else {
    Write-Host "SAFE: No breaking changes" -ForegroundColor Green
}
```
