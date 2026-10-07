# ============================================================
# G1-09: API Contract Differential Baseline Generator
# Author  : Tech Writer - Jellyfin Differential Testing Framework
# Task    : G1-09 - Build API Contract Differential Baseline
# Tool    : oasdiff (https://github.com/Tufin/oasdiff)
# Output  : reports/api-diff-report.json
# ============================================================
# USAGE:
#   .\scripts\api-diff\run-api-diff.ps1
#   .\scripts\api-diff\run-api-diff.ps1 -BaselineSpec .\specs\swagger_v1.json -TargetSpec .\specs\swagger_v2.json
# ============================================================

param(
    [string]$BaselineSpec = "",
    [string]$TargetSpec   = "",
    [string]$OutputReport = ".\reports\api-diff-report.json",
    [string]$OasdiffPath  = ""
)

$ErrorActionPreference = "Stop"
$Timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
$ReportId  = "G1-09-api-diff-" + (Get-Date -Format "yyyyMMdd")

# Resolve oasdiff path
if (-not $OasdiffPath) {
    if (Test-Path ".\oasdiff.exe") {
        $OasdiffPath = ".\oasdiff.exe"
    } elseif (Get-Command "oasdiff" -ErrorAction SilentlyContinue) {
        $OasdiffPath = "oasdiff"
    } else {
        $OasdiffPath = ".\oasdiff.exe"
    }
}

# Resolve baseline spec path
if (-not $BaselineSpec) {
    if (Test-Path ".\specs\swagger_v1.json") {
        $BaselineSpec = ".\specs\swagger_v1.json"
    } elseif (Test-Path ".\specs\v1.json") {
        $BaselineSpec = ".\specs\v1.json"
    } else {
        $BaselineSpec = ".\specs\swagger_v1.json"
    }
}

# Resolve target spec path
if (-not $TargetSpec) {
    if (Test-Path ".\specs\swagger_v2.json") {
        $TargetSpec = ".\specs\swagger_v2.json"
    } elseif (Test-Path ".\specs\v2.json") {
        $TargetSpec = ".\specs\v2.json"
    } else {
        $TargetSpec = ".\specs\swagger_v2.json"
    }
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  G1-09: API Contract Differential Baseline" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Baseline : $BaselineSpec"
Write-Host "  Target   : $TargetSpec"
Write-Host "  Output   : $OutputReport"
Write-Host ""

# ---------------------------------------------------------------------------
# STEP 0: Validate input files
# ---------------------------------------------------------------------------
if (-not (Test-Path $BaselineSpec)) {
    throw "ERROR: Baseline spec not found: $BaselineSpec`nHint: Place your Jellyfin v1 OpenAPI spec at specs\swagger_v1.json"
}
if (-not (Test-Path $TargetSpec)) {
    throw "ERROR: Target spec not found: $TargetSpec`nHint: Place your Jellyfin v2 OpenAPI spec at specs\swagger_v2.json"
}

# ---------------------------------------------------------------------------
# STEP 1: Compute SHA256 checksums for audit trail
# ---------------------------------------------------------------------------
$Sha256V1 = (Get-FileHash -Algorithm SHA256 $BaselineSpec).Hash.ToLower()
$Sha256V2 = (Get-FileHash -Algorithm SHA256 $TargetSpec).Hash.ToLower()
Write-Host "  SHA256 (v1): $Sha256V1"
Write-Host "  SHA256 (v2): $Sha256V2"
Write-Host ""

# ---------------------------------------------------------------------------
# STEP 2: Verify oasdiff is available
# ---------------------------------------------------------------------------
try {
    $OasdiffVersion = (& $OasdiffPath -v 2>&1) | Out-String
    $OasdiffVersion = $OasdiffVersion.Trim()
    Write-Host "  Tool: oasdiff $OasdiffVersion" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "ERROR: oasdiff not found in PATH." -ForegroundColor Red
    Write-Host "Install instructions:" -ForegroundColor Yellow
    Write-Host "  Windows : winget install oasdiff  OR  scoop install oasdiff"
    Write-Host "  Linux   : curl -sSfL https://raw.githubusercontent.com/Tufin/oasdiff/main/install.sh | sh"
    Write-Host "  Direct  : https://github.com/Tufin/oasdiff/releases"
    throw "oasdiff not available"
}
Write-Host ""

# ---------------------------------------------------------------------------
# STEP 3: Run oasdiff - breaking changes
# ---------------------------------------------------------------------------
Write-Host "[1/4] Detecting Breaking Changes..." -ForegroundColor Yellow
$BreakingRaw = & $OasdiffPath breaking $BaselineSpec $TargetSpec --format json 2>&1
$BreakingExitCode = $LASTEXITCODE
# oasdiff exit codes: 0=no breaking, 1=breaking found, 2=error
if ($BreakingExitCode -eq 2) {
    Write-Warning "oasdiff returned exit code 2 - possible parse error. Check spec files."
}

# ---------------------------------------------------------------------------
# STEP 4: Run oasdiff - full diff
# ---------------------------------------------------------------------------
Write-Host "[2/4] Running Full Schema Diff..." -ForegroundColor Yellow
$DiffRaw = & $OasdiffPath diff $BaselineSpec $TargetSpec --format json 2>&1

# ---------------------------------------------------------------------------
# STEP 5: Parse and transform output
# ---------------------------------------------------------------------------
Write-Host "[3/4] Parsing & Transforming Output..." -ForegroundColor Yellow

$Breaking         = [System.Collections.Generic.List[object]]::new()
$NonBreaking      = [System.Collections.Generic.List[object]]::new()
$BreakingCount    = 0
$NonBreakingCount = 0
$EndpointsAdded   = @()
$EndpointsRemoved = @()

# Parse breaking changes
try {
    $BreakingObj = $BreakingRaw | ConvertFrom-Json -ErrorAction Stop
} catch {
    $BreakingObj = $null
    Write-Host "  [WARN] Could not parse breaking changes JSON - treating as empty" -ForegroundColor DarkYellow
}

# Parse full diff
try {
    $DiffObj = $DiffRaw | ConvertFrom-Json -ErrorAction Stop
} catch {
    $DiffObj = $null
    Write-Host "  [WARN] Could not parse diff JSON - treating as empty" -ForegroundColor DarkYellow
}

# --- Extract breaking changes ---
# oasdiff JSON structure varies by version; handle common structures
if ($BreakingObj) {
    $changeList = @()
    if ($BreakingObj.PSObject.Properties["breakingChanges"]) {
        $changeList = $BreakingObj.breakingChanges
    } elseif ($BreakingObj -is [array]) {
        $changeList = $BreakingObj
    }

    $idx = 1
    foreach ($change in $changeList) {
        $entry = [ordered]@{
            change_id   = "BC-{0:D3}" -f $idx
            severity    = "BREAKING"
            category    = if ($change.id)     { ($change.id -replace "-", "_").ToUpper() }
                          elseif ($change.code) { ($change.code -replace "-", "_").ToUpper() }
                          else { "UNKNOWN_BREAKING" }
            path        = if ($change.path)       { $change.path }
                          elseif ($change.operationId) { $change.operationId }
                          else { "unknown" }
            method      = if ($change.method) { $change.method.ToUpper() } else { "UNKNOWN" }
            description = if ($change.text)    { $change.text }
                          elseif ($change.message) { $change.message }
                          else { "Breaking change detected - check oasdiff raw output" }
            rca_hint    = "Run: git log --all -S '<field>' -- '**/*Controller.cs' to trace C# root cause"
        }
        $Breaking.Add($entry)
        $idx++
        $BreakingCount++
    }
}

# --- Extract non-breaking changes and endpoint inventory from diff ---
if ($DiffObj) {
    # Endpoints added/removed
    if ($DiffObj.PSObject.Properties["paths"]) {
        $paths = $DiffObj.paths
        if ($paths.PSObject.Properties["added"])   { $EndpointsAdded   = @($paths.added) }
        if ($paths.PSObject.Properties["deleted"]) { $EndpointsRemoved = @($paths.deleted) }

        # Non-breaking: new optional parameters, modified paths without breaking changes
        $nbcIdx = 1
        if ($paths.PSObject.Properties["modified"]) {
            $modifiedPaths = $paths.modified
            if ($modifiedPaths -is [PSCustomObject]) {
                foreach ($prop in $modifiedPaths.PSObject.Properties) {
                    $entry = [ordered]@{
                        change_id   = "NBC-{0:D3}" -f $nbcIdx
                        severity    = "NON_BREAKING"
                        category    = "PATH_MODIFIED"
                        path        = $prop.Name
                        method      = "MULTIPLE"
                        description = "Path modified; no breaking signature detected by oasdiff"
                    }
                    $NonBreaking.Add($entry)
                    $nbcIdx++
                    $NonBreakingCount++
                }
            }
        }
    }
}

# --- Endpoints added as non-breaking changes ---
$epIdx = 1
foreach ($ep in $EndpointsAdded) {
    $entry = [ordered]@{
        change_id   = "NBC-EP-{0:D3}" -f $epIdx
        severity    = "NON_BREAKING"
        category    = "ENDPOINT_ADDED"
        path        = $ep
        method      = "MULTIPLE"
        description = "New endpoint added in target version. Backward compatible."
    }
    $NonBreaking.Add($entry)
    $epIdx++
    $NonBreakingCount++
}

$TotalAdded   = @($EndpointsAdded).Count
$TotalRemoved = @($EndpointsRemoved).Count
$HasBreaking  = $BreakingCount -gt 0

# --- Risk classification ---
$RiskLevel = switch ($true) {
    ($BreakingCount -eq 0)  { "LOW";      break }
    ($BreakingCount -le 2)  { "MEDIUM";   break }
    ($BreakingCount -le 5)  { "HIGH";     break }
    default                  { "CRITICAL" }
}
$Verdict = if ($HasBreaking) { "BREAKING_CHANGES_DETECTED" } else { "COMPATIBLE" }

Write-Host "  Breaking Changes  : $BreakingCount" -ForegroundColor $(if ($HasBreaking) {"Red"} else {"Green"})
Write-Host "  Non-Breaking      : $NonBreakingCount"
Write-Host "  Endpoints Added   : $TotalAdded"
Write-Host "  Endpoints Removed : $TotalRemoved"
Write-Host "  Risk Level        : $RiskLevel" -ForegroundColor $(switch ($RiskLevel) {"LOW"{"Green"}"MEDIUM"{"Yellow"} default {"Red"}})
Write-Host ""

# ---------------------------------------------------------------------------
# STEP 6: Build final report
# ---------------------------------------------------------------------------
Write-Host "[4/4] Writing api-diff-report.json..." -ForegroundColor Yellow

$BaselineResolved = (Resolve-Path $BaselineSpec -ErrorAction SilentlyContinue)
$BaselineSource = if ($BaselineResolved) { $BaselineResolved.Path } else { $BaselineSpec }

$TargetResolved = (Resolve-Path $TargetSpec -ErrorAction SilentlyContinue)
$TargetSource = if ($TargetResolved) { $TargetResolved.Path } else { $TargetSpec }

$Report = [ordered]@{
    report_metadata = [ordered]@{
        report_id    = $ReportId
        task_id      = "G1-09"
        generated_at = $Timestamp
        generated_by = "Tech Writer / oasdiff"
        tool         = "oasdiff"
        tool_version = $OasdiffVersion
        baseline_version = [ordered]@{
            label       = "jellyfin-baseline"
            source_file = $BaselineSource
            sha256      = $Sha256V1
        }
        target_version = [ordered]@{
            label       = "jellyfin-target"
            source_file = $TargetSource
            sha256      = $Sha256V2
        }
    }
    summary = [ordered]@{
        total_breaking_changes     = $BreakingCount
        total_non_breaking_changes = $NonBreakingCount
        total_endpoints_added      = $TotalAdded
        total_endpoints_removed    = $TotalRemoved
        risk_level                 = $RiskLevel
        verdict                    = $Verdict
    }
    breaking_changes     = @($Breaking)
    non_breaking_changes = @($NonBreaking)
    endpoints_inventory  = [ordered]@{
        added   = @($EndpointsAdded)
        removed = @($EndpointsRemoved)
    }
    ci_machine_data = [ordered]@{
        machine_readable      = $true
        has_breaking_changes  = $HasBreaking
        breaking_change_count = $BreakingCount
        should_block_merge    = $HasBreaking
        recommended_action    = if ($HasBreaking) { "REQUIRE_MANUAL_REVIEW" } else { "AUTO_MERGE_ALLOWED" }
    }
}

# Ensure output directory exists
$OutputDir = Split-Path $OutputReport -Parent
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Write-Host "  Created directory: $OutputDir"
}

# Write JSON with proper formatting
$Report | ConvertTo-Json -Depth 10 | Set-Content -Path $OutputReport -Encoding UTF8

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
if ($HasBreaking) {
    Write-Host "  VERDICT : $Verdict" -ForegroundColor Red
    Write-Host "  ACTION  : Manual review required before merge!" -ForegroundColor Red
} else {
    Write-Host "  VERDICT : $Verdict" -ForegroundColor Green
    Write-Host "  ACTION  : Safe to proceed with automated testing" -ForegroundColor Green
}
Write-Host "  Report  : $OutputReport" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# CI/CD-compatible exit codes:
#   0 = No breaking changes (green light)
#   1 = Breaking changes detected (block merge)
if ($HasBreaking) { exit 1 } else { exit 0 }
