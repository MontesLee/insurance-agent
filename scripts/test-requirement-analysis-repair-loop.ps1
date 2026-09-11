[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$Root = Split-Path -Parent $PSScriptRoot
$AnalysisScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-analysis.ps1"
$RepairLoopScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-repair-loop.ps1"
$AnalysisTestDir = Join-Path $Root "02-requirement-analysis\tests\analysis"

function Run-Analysis {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $AnalysisScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "analysis_status")
}

function Save-TempJson {
    param(
        $Object,
        [string]$Name
    )
    $path = Join-Path ([System.IO.Path]::GetTempPath()) $Name
    $Object | ConvertTo-Json -Depth 60 | Set-Content -Path $path -Encoding UTF8
    return $path
}

function Run-RepairLoop {
    param(
        [string]$InputPath = "",
        [string]$ExistingAnalysisPath = ""
    )

    $args = @{}
    if (-not [string]::IsNullOrWhiteSpace($InputPath)) { $args["InputJsonPath"] = $InputPath }
    if (-not [string]::IsNullOrWhiteSpace($ExistingAnalysisPath)) { $args["ExistingAnalysisJsonPath"] = $ExistingAnalysisPath }
    return (Invoke-RaScriptToObject -ScriptPath $RepairLoopScript -Arguments $args -ExpectedTopLevelProperty "repair_summary")
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Repair Loop Test" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

$failedCases = @()

$cases = @(
    @{
        Name = "unsupported_conclusion_repair"
        Validate = {
            $inputPath = Join-Path $AnalysisTestDir "life_complete.input.json"
            $analysis = Run-Analysis -InputPath $inputPath
            $analysis.risk_map[0].evidence_refs = @()
            $brokenPath = Save-TempJson -Object $analysis -Name "ra-repair-unsupported.json"
            $result = Run-RepairLoop -InputPath $inputPath -ExistingAnalysisPath $brokenPath

            Assert-True ($result.final_status -eq "PASS") "unsupported_conclusion_repair should end PASS"
            Assert-True ($result.attempt_count -eq 1) "unsupported_conclusion_repair should pass after one repair"
            Assert-True (@($result.repair_history[0].repair_actions | Where-Object { $_ -eq "realign_evidence_refs" }).Count -ge 1) "unsupported_conclusion_repair should realign evidence refs"
        }
    },
    @{
        Name = "missing_risk_repair"
        Validate = {
            $inputPath = Join-Path $AnalysisTestDir "life_complete.input.json"
            $analysis = Run-Analysis -InputPath $inputPath
            $analysis.risk_map = @()
            $brokenPath = Save-TempJson -Object $analysis -Name "ra-repair-missing-risk.json"
            $result = Run-RepairLoop -InputPath $inputPath -ExistingAnalysisPath $brokenPath

            Assert-True ($result.final_status -eq "PASS") "missing_risk_repair should end PASS"
            Assert-True (@($result.final_analysis.risk_map).Count -ge 1) "missing_risk_repair should restore risk_map"
            Assert-True (@($result.repair_history[0].repair_actions | Where-Object { $_ -eq "rebuild_analysis_from_input" }).Count -ge 1) "missing_risk_repair should rebuild from source input"
        }
    },
    @{
        Name = "product_leak_repair"
        Validate = {
            $inputPath = Join-Path $AnalysisTestDir "life_complete.input.json"
            $analysis = Run-Analysis -InputPath $inputPath
            $analysis.requirements[0].summary = "Recommend buying a company product plan immediately."
            $brokenPath = Save-TempJson -Object $analysis -Name "ra-repair-product.json"
            $result = Run-RepairLoop -InputPath $inputPath -ExistingAnalysisPath $brokenPath

            Assert-True ($result.final_status -eq "PASS") "product_leak_repair should end PASS"
            Assert-True ($result.final_analysis.requirements[0].boundary -eq "requirement_only") "product_leak_repair should restore requirement boundary"
            Assert-True ($result.final_analysis.requirements[0].summary -notmatch "Recommend|buy|product|company") "product_leak_repair should sanitize product language"
        }
    },
    @{
        Name = "human_review_required_after_two_retries"
        Validate = {
            $inputPath = Join-Path $AnalysisTestDir "life_complete.input.json"
            $analysis = Run-Analysis -InputPath $inputPath
            $analysis.risk_map = @()
            $brokenPath = Save-TempJson -Object $analysis -Name "ra-repair-human-review.json"
            $result = Run-RepairLoop -ExistingAnalysisPath $brokenPath

            Assert-True ($result.final_status -eq "HUMAN_REVIEW_REQUIRED") "human_review_required_after_two_retries should require human review"
            Assert-True ($result.attempt_count -eq 2) "human_review_required_after_two_retries should stop at MAX_RETRY=2"
            Assert-True (@($result.final_eval.issues | Where-Object { $_.type -eq "MISSING_RISK" }).Count -ge 1) "human_review_required_after_two_retries should still contain MISSING_RISK"
        }
    }
)

foreach ($case in $cases) {
    try {
        & $case.Validate
        Write-Host "[PASS] $($case.Name)" -ForegroundColor Green
    } catch {
        $failedCases += $case.Name
        Write-Host "[FAIL] $($case.Name)" -ForegroundColor Red
        Write-Host "  - $($_.Exception.Message)" -ForegroundColor DarkRed
    }
}

Write-Host ""
if ($failedCases.Count -gt 0) {
    Write-Host "Repair loop test failed: $($failedCases -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "All repair loop tests passed." -ForegroundColor Green
exit 0
