[CmdletBinding()]
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$Root = Split-Path -Parent $PSScriptRoot
$TestDir = Join-Path $Root "evals\fixtures\unit\analysis"
$AnalysisScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-analysis.ps1"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-Analysis {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $AnalysisScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "analysis_status")
}

$failedCases = @()

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Phase 4 Test" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

$cases = @(
    @{
        Name = "life_complete"
        Validate = {
            $result = Invoke-Analysis -InputPath (Join-Path $TestDir "life_complete.input.json")
            $requirements = @($result.requirements)
            $riskMap = @($result.risk_map)

            Assert-True ($result.analysis_status -eq "PRELIMINARY") "life_complete should remain PRELIMINARY because recommended fields are still missing"
            Assert-True ($requirements.Count -eq 1) "life_complete should generate one life requirement"
            Assert-True ($riskMap.Count -eq 1) "life_complete should generate one life risk"
            Assert-True ($requirements[0].requirement_type -eq "life") "life_complete requirement type should be life"
            Assert-True ($requirements[0].boundary -eq "requirement_only") "life_complete must stay in requirement boundary"
            Assert-True ($requirements[0].priority -eq "P1_HIGH") "life_complete should be P1_HIGH when existing life coverage is known"
            Assert-True ($result.evidence.Count -ge 1) "life_complete should contain evidence"
            Assert-True (@($result.unknowns).Count -ge 1) "life_complete should preserve unknowns for missing recommended fields"
        }
    },
    @{
        Name = "life_preliminary_unknown"
        Validate = {
            $result = Invoke-Analysis -InputPath (Join-Path $TestDir "life_preliminary_unknown.input.json")
            $riskMap = @($result.risk_map)

            Assert-True ($result.analysis_status -eq "NEED_MORE_INFORMATION") "life_preliminary_unknown should be NEED_MORE_INFORMATION because required life coverage data is missing"
            Assert-True ($riskMap.Count -eq 0) "life_preliminary_unknown should not produce a life risk entry"
            Assert-True (@($result.question_plan.selected_questions | Where-Object { $_.field -eq "existing_life_coverage" }).Count -ge 1) "life_preliminary_unknown should ask for existing_life_coverage first"
            Assert-True ($result.guardrails.product_recommendation_included -eq $false) "life_preliminary_unknown must not leak product recommendation"
        }
    },
    @{
        Name = "need_more_information"
        Validate = {
            $result = Invoke-Analysis -InputPath (Join-Path $TestDir "need_more_information.input.json")

            Assert-True ($result.analysis_status -eq "NEED_MORE_INFORMATION") "need_more_information should remain NEED_MORE_INFORMATION"
            Assert-True (@($result.risk_map).Count -eq 0) "need_more_information should not output risk_map"
            Assert-True (@($result.requirements).Count -eq 0) "need_more_information should not output requirements"
        }
    },
    @{
        Name = "multi_scope_priority"
        Validate = {
            $result = Invoke-Analysis -InputPath (Join-Path $TestDir "multi_scope_priority.input.json")
            $requirements = @($result.requirements)
            $lifeReq = @($requirements | Where-Object { $_.requirement_type -eq "life" })
            $ciReq = @($requirements | Where-Object { $_.requirement_type -eq "critical_illness" })
            $medicalReq = @($requirements | Where-Object { $_.requirement_type -eq "medical" })

            Assert-True ($result.analysis_status -eq "PRELIMINARY") "multi_scope_priority should be PRELIMINARY because some high-value fields are still missing"
            Assert-True ($requirements.Count -eq 3) "multi_scope_priority should generate 3 requirement entries"
            Assert-True ($lifeReq.Count -eq 1 -and $ciReq.Count -eq 1 -and $medicalReq.Count -eq 1) "multi_scope_priority should cover life, medical and critical_illness"
            Assert-True ($lifeReq[0].priority -ne $ciReq[0].priority -or $lifeReq[0].priority -ne $medicalReq[0].priority) "multi_scope_priority should not assign the exact same priority to all requirements"
            Assert-True ($result.evidence.Count -ge 3) "multi_scope_priority should generate evidence for multiple scopes"
            Assert-True ($result.guardrails.product_recommendation_included -eq $false) "multi_scope_priority must not leak product recommendation"
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
    Write-Host "Analysis test failed: $($failedCases -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "All analysis tests passed." -ForegroundColor Green
exit 0
