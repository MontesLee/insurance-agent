[CmdletBinding()]
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$Root = Split-Path -Parent $PSScriptRoot
$TestDir = Join-Path $Root "evals\fixtures\unit\sufficiency"
$EngineScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-sufficiency.ps1"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Run-Case {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $EngineScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "analysis_status")
}

$cases = @(
    @{
        Name = "complete_info"
        Path = (Join-Path $TestDir "complete_info.input.json")
        Validate = {
            param($result)
            Assert-True ($result.analysis_status -eq "COMPLETE") "complete_info should be COMPLETE"
            Assert-True ($result.information_sufficiency.sufficiency_status -eq "SUFFICIENT") "complete_info sufficiency should be SUFFICIENT"
            Assert-True ([double]$result.information_sufficiency.sufficiency_score -ge 0.85) "complete_info score should be >= 0.85"
        }
    },
    @{
        Name = "low_impact_missing"
        Path = (Join-Path $TestDir "low_impact_missing.input.json")
        Validate = {
            param($result)
            $gapFields = @($result.information_gaps | ForEach-Object { $_.field })
            Assert-True ($result.analysis_status -eq "COMPLETE") "low_impact_missing should still be COMPLETE"
            Assert-True ($gapFields -contains "mortgage_years") "low_impact_missing should report mortgage_years gap"
        }
    },
    @{
        Name = "high_impact_missing"
        Path = (Join-Path $TestDir "high_impact_missing.input.json")
        Validate = {
            param($result)
            $blocking = @($result.information_sufficiency.blocking_fields)
            $medicalGap = @($result.information_gaps | Where-Object { $_.field -eq "social_insurance_status" })
            Assert-True ($result.analysis_status -eq "NEED_MORE_INFORMATION") "high_impact_missing should be NEED_MORE_INFORMATION"
            Assert-True ($result.information_sufficiency.sufficiency_status -eq "INSUFFICIENT") "high_impact_missing sufficiency should be INSUFFICIENT"
            Assert-True ($blocking -contains "social_insurance_status") "high_impact_missing should block on social_insurance_status"
            Assert-True ($medicalGap.Count -ge 1) "high_impact_missing should contain social_insurance_status gap"
        }
    },
    @{
        Name = "multi_missing"
        Path = (Join-Path $TestDir "multi_missing.input.json")
        Validate = {
            param($result)
            $gapFields = @($result.information_gaps | ForEach-Object { $_.field })
            Assert-True ($result.analysis_status -eq "NEED_MORE_INFORMATION") "multi_missing should be NEED_MORE_INFORMATION"
            Assert-True ($gapFields.Count -ge 4) "multi_missing should contain multiple gaps"
            Assert-True ($gapFields -contains "financial_goals") "multi_missing should include financial_goals gap"
            Assert-True ($gapFields -contains "assets") "multi_missing should include assets gap"
        }
    },
    @{
        Name = "conflicting_info"
        Path = (Join-Path $TestDir "conflicting_info.input.json")
        Validate = {
            param($result)
            $conflicts = @($result.information_sufficiency.conflict_fields)
            $conflictGap = @($result.information_gaps | Where-Object { $_.field -eq "annual_income" -and $_.gap_type -eq "CONFLICTING_INFORMATION" })
            Assert-True ($result.analysis_status -eq "CONFLICTING_INFORMATION") "conflicting_info should be CONFLICTING_INFORMATION"
            Assert-True ($result.information_sufficiency.sufficiency_status -eq "CONFLICTING") "conflicting_info sufficiency should be CONFLICTING"
            Assert-True ($conflicts -contains "annual_income") "conflicting_info should include annual_income in conflict_fields"
            Assert-True ($conflictGap.Count -ge 1) "conflicting_info should report annual_income conflict gap"
        }
    }
)

$failedCases = @()

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Sufficiency Test" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

foreach ($case in $cases) {
    try {
        $result = Run-Case -InputPath $case.Path
        & $case.Validate $result
        Write-Host "[PASS] $($case.Name) -> $($result.analysis_status) / $($result.information_sufficiency.sufficiency_status) / score=$($result.information_sufficiency.sufficiency_score)" -ForegroundColor Green
    } catch {
        $failedCases += $case.Name
        Write-Host "[FAIL] $($case.Name)" -ForegroundColor Red
        Write-Host "  - $($_.Exception.Message)" -ForegroundColor DarkRed
    }
}

Write-Host ""
if ($failedCases.Count -gt 0) {
    Write-Host "Sufficiency test failed: $($failedCases -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "All sufficiency tests passed." -ForegroundColor Green
exit 0
