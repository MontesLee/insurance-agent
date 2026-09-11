[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$Root = Split-Path -Parent $PSScriptRoot
$AnalysisScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-analysis.ps1"
$EvalScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-eval.ps1"
$AnalysisTestDir = Join-Path $Root "02-requirement-analysis\tests\analysis"

function Run-Analysis {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $AnalysisScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "analysis_status")
}

function Run-Eval {
    param([string]$JsonPath)
    return (Invoke-RaScriptToObject -ScriptPath $EvalScript -Arguments @{ AnalysisJsonPath = $JsonPath } -ExpectedTopLevelProperty "eval_status")
}

function Write-CaseResult {
    param(
        [string]$CaseName,
        [string]$Expected,
        [string]$Actual,
        [string]$Score,
        [string]$FailureType,
        [string]$Evidence,
        [bool]$Passed
    )

    $prefix = "[PASS]"
    $color = "Green"
    if (-not $Passed) {
        $prefix = "[FAIL]"
        $color = "Red"
    }

    Write-Host "$prefix case=$CaseName expected=$Expected actual=$Actual score=$Score failure_type=$FailureType evidence=$Evidence" -ForegroundColor $color
}

function Save-TempJson {
    param(
        $Object,
        [string]$Name
    )

    $path = Join-Path ([System.IO.Path]::GetTempPath()) $Name
    $Object | ConvertTo-Json -Depth 40 | Set-Content -Path $path -Encoding UTF8
    return $path
}

function New-ValidEvalFixture {
    param($AnalysisObject)

    $copy = $AnalysisObject | ConvertTo-Json -Depth 40 | ConvertFrom-Json
    $evidenceEntries = @($copy.evidence)
    $riskEntries = @($copy.risk_map)
    $coverageEntries = @($copy.coverage_gaps)

    for ($i = 0; $i -lt $riskEntries.Count; $i++) {
        if ($i -lt $evidenceEntries.Count) {
            $riskEntries[$i].evidence_refs = @($evidenceEntries[$i].evidence_id)
        }
    }

    for ($i = 0; $i -lt $coverageEntries.Count; $i++) {
        if ($i -lt $evidenceEntries.Count) {
            $coverageEntries[$i].evidence_refs = @($evidenceEntries[$i].evidence_id)
        }
    }

    $copy.risk_map = @($riskEntries)
    $copy.coverage_gaps = @($coverageEntries)
    return $copy
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Eval Test" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

$failedCases = @()

# Baseline PASS case
$baselineInput = Join-Path $AnalysisTestDir "multi_scope_priority.input.json"
$baselineAnalysis = New-ValidEvalFixture -AnalysisObject (Run-Analysis -InputPath $baselineInput)
$baselinePath = Save-TempJson -Object $baselineAnalysis -Name "ra-eval-baseline.json"
$baselineEval = Run-Eval -JsonPath $baselinePath
$baselinePassed = ($baselineEval.eval_status -eq "PASS")
Write-CaseResult -CaseName "baseline_pass" -Expected "PASS" -Actual $baselineEval.eval_status -Score $baselineEval.score -FailureType "NONE" -Evidence ("issues={0}" -f @($baselineEval.issues).Count) -Passed $baselinePassed
if (-not $baselinePassed) { $failedCases += "baseline_pass" }

# Case 1: Unsupported Conclusion
$unsupportedInput = Join-Path $AnalysisTestDir "life_complete.input.json"
$unsupportedAnalysis = New-ValidEvalFixture -AnalysisObject (Run-Analysis -InputPath $unsupportedInput)
$unsupportedAnalysis.risk_map[0].evidence_refs = @()
$unsupportedPath = Save-TempJson -Object $unsupportedAnalysis -Name "ra-eval-unsupported.json"
$unsupportedEval = Run-Eval -JsonPath $unsupportedPath
$unsupportedIssue = @($unsupportedEval.issues | Where-Object { $_.type -eq "UNSUPPORTED_CONCLUSION" })
$unsupportedPassed = ($unsupportedEval.eval_status -eq "FAIL" -and $unsupportedIssue.Count -ge 1)
Write-CaseResult -CaseName "unsupported_conclusion" -Expected "FAIL + UNSUPPORTED_CONCLUSION" -Actual $unsupportedEval.eval_status -Score $unsupportedEval.score -FailureType (($unsupportedIssue | Select-Object -First 1).type) -Evidence (($unsupportedIssue | Select-Object -First 1).evidence) -Passed $unsupportedPassed
if (-not $unsupportedPassed) { $failedCases += "unsupported_conclusion" }

# Case 2: Missing Risk
$missingRiskInput = Join-Path $AnalysisTestDir "life_complete.input.json"
$missingRiskAnalysis = New-ValidEvalFixture -AnalysisObject (Run-Analysis -InputPath $missingRiskInput)
$missingRiskAnalysis.risk_map = @()
$missingRiskPath = Save-TempJson -Object $missingRiskAnalysis -Name "ra-eval-missing-risk.json"
$missingRiskEval = Run-Eval -JsonPath $missingRiskPath
$missingRiskIssue = @($missingRiskEval.issues | Where-Object { $_.type -eq "MISSING_RISK" })
$missingRiskPassed = ($missingRiskEval.eval_status -eq "FAIL" -and $missingRiskIssue.Count -ge 1)
Write-CaseResult -CaseName "missing_risk" -Expected "FAIL + MISSING_RISK" -Actual $missingRiskEval.eval_status -Score $missingRiskEval.score -FailureType (($missingRiskIssue | Select-Object -First 1).type) -Evidence (($missingRiskIssue | Select-Object -First 1).evidence) -Passed $missingRiskPassed
if (-not $missingRiskPassed) { $failedCases += "missing_risk" }

# Case 3: Insufficient Information but analyzed anyway
$insufficientInput = Join-Path $AnalysisTestDir "need_more_information.input.json"
$insufficientAnalysis = New-ValidEvalFixture -AnalysisObject (Run-Analysis -InputPath $insufficientInput)
$insufficientAnalysis.requirements = @(
    [pscustomobject]@{
        requirement_id = "REQ999"
        requirement_type = "savings"
        summary = "Need savings solution"
        priority = "P1_HIGH"
        boundary = "requirement_only"
    }
)
$insufficientAnalysis.risk_map = @(
    [pscustomobject]@{
        requirement_type = "savings"
        risk_exposure = "Forced fake risk"
        potential_financial_impact = "Forced fake impact"
        existing_protection = "UNKNOWN"
        coverage_gap = "Forced fake gap"
        priority = "P1_HIGH"
        reasoning = "Forced fake reasoning"
        evidence_refs = @("EV999")
    }
)
$insufficientPath = Save-TempJson -Object $insufficientAnalysis -Name "ra-eval-insufficient.json"
$insufficientEval = Run-Eval -JsonPath $insufficientPath
$insufficientIssue = @($insufficientEval.issues | Where-Object { $_.type -eq "INSUFFICIENT_INFORMATION" })
$insufficientPassed = ($insufficientEval.eval_status -eq "FAIL" -and $insufficientIssue.Count -ge 1)
Write-CaseResult -CaseName "insufficient_information" -Expected "FAIL + INSUFFICIENT_INFORMATION" -Actual $insufficientEval.eval_status -Score $insufficientEval.score -FailureType (($insufficientIssue | Select-Object -First 1).type) -Evidence (($insufficientIssue | Select-Object -First 1).evidence) -Passed $insufficientPassed
if (-not $insufficientPassed) { $failedCases += "insufficient_information" }

# Case 4: Product Recommendation Leak
$productInput = Join-Path $AnalysisTestDir "life_complete.input.json"
$productAnalysis = New-ValidEvalFixture -AnalysisObject (Run-Analysis -InputPath $productInput)
$productAnalysis.requirements[0].summary = "Recommend buying a company product plan immediately."
$productPath = Save-TempJson -Object $productAnalysis -Name "ra-eval-product-leak.json"
$productEval = Run-Eval -JsonPath $productPath
$productIssue = @($productEval.issues | Where-Object { $_.type -eq "PRODUCT_RECOMMENDATION_LEAK" })
$productPassed = ($productEval.eval_status -eq "FAIL" -and $productIssue.Count -ge 1)
Write-CaseResult -CaseName "product_boundary_violation" -Expected "FAIL + PRODUCT_RECOMMENDATION_LEAK" -Actual $productEval.eval_status -Score $productEval.score -FailureType (($productIssue | Select-Object -First 1).type) -Evidence (($productIssue | Select-Object -First 1).evidence) -Passed $productPassed
if (-not $productPassed) { $failedCases += "product_boundary_violation" }

# Case 5: Logical Inconsistency
$logicInput = Join-Path $AnalysisTestDir "life_complete.input.json"
$logicAnalysis = New-ValidEvalFixture -AnalysisObject (Run-Analysis -InputPath $logicInput)
$logicAnalysis.requirements[0].priority = "P3_LOW"
$logicPath = Save-TempJson -Object $logicAnalysis -Name "ra-eval-logic.json"
$logicEval = Run-Eval -JsonPath $logicPath
$logicIssue = @($logicEval.issues | Where-Object { $_.type -eq "LOGICAL_INCONSISTENCY" })
$logicPassed = ($logicEval.eval_status -eq "FAIL" -and $logicIssue.Count -ge 1)
Write-CaseResult -CaseName "logical_inconsistency" -Expected "FAIL + LOGICAL_INCONSISTENCY" -Actual $logicEval.eval_status -Score $logicEval.score -FailureType (($logicIssue | Select-Object -First 1).type) -Evidence (($logicIssue | Select-Object -First 1).evidence) -Passed $logicPassed
if (-not $logicPassed) { $failedCases += "logical_inconsistency" }

Write-Host ""
if ($failedCases.Count -gt 0) {
    Write-Host "Eval test failed: $($failedCases -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "All eval tests passed." -ForegroundColor Green
exit 0
