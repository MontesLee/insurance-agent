[CmdletBinding()]
param(
    [string]$InputJsonPath = "",
    [string]$ExistingAnalysisJsonPath = "",
    [string]$OutputJsonPath = ""
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"
$MAX_RETRY = 2

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$AnalysisScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-analysis.ps1"
$EvalScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-eval.ps1"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Encoding UTF8 -Path $Path | ConvertFrom-Json)
}

function To-JsonArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value)
}

function Save-JsonFile {
    param(
        $Object,
        [string]$Path
    )
    $Object | ConvertTo-Json -Depth 50 | Set-Content -Path $Path -Encoding UTF8
}

function Invoke-AnalysisFromInput {
    param([string]$InputPath)
    $tempPath = Join-Path ([System.IO.Path]::GetTempPath()) ("ra-analysis-{0}.json" -f ([guid]::NewGuid().ToString("N")))
    $null = Invoke-RaScriptToFile -ScriptPath $AnalysisScript -Arguments @{ InputJsonPath = $InputPath; OutputJsonPath = $tempPath } -OutputJsonPath $tempPath -ValidateMinSize -MinSizeBytes 400
    return (Read-JsonFile -Path $tempPath)
}

function Invoke-EvalForAnalysis {
    param($AnalysisObject)
    $tempPath = Join-Path ([System.IO.Path]::GetTempPath()) ("ra-eval-{0}.json" -f ([guid]::NewGuid().ToString("N")))
    Save-JsonFile -Object $AnalysisObject -Path $tempPath
    return (Invoke-RaScriptToObject -ScriptPath $EvalScript -Arguments @{ AnalysisJsonPath = $tempPath } -ExpectedTopLevelProperty "eval_status")
}

function Get-EvidenceByRequirementType {
    param($AnalysisObject)
    $map = @{}
    foreach ($ev in (To-JsonArray -Value $AnalysisObject.evidence)) {
        $conclusion = [string]$ev.conclusion
        if ($conclusion -match "^(medical|critical_illness|accident|life|savings) requirement priority is") {
            $map[$Matches[1]] = $ev.evidence_id
        }
    }
    return $map
}

function Repair-UnsupportedConclusion {
    param($AnalysisObject)
    $evidenceMap = Get-EvidenceByRequirementType -AnalysisObject $AnalysisObject

    foreach ($risk in (To-JsonArray -Value $AnalysisObject.risk_map)) {
        if ($evidenceMap.ContainsKey($risk.requirement_type)) {
            $risk.evidence_refs = @($evidenceMap[$risk.requirement_type])
        }
    }

    foreach ($gap in (To-JsonArray -Value $AnalysisObject.coverage_gaps)) {
        if ($evidenceMap.ContainsKey($gap.requirement_type)) {
            $gap.evidence_refs = @($evidenceMap[$gap.requirement_type])
        }
    }

    return $AnalysisObject
}

function Repair-ProductLeak {
    param($AnalysisObject)

    foreach ($req in (To-JsonArray -Value $AnalysisObject.requirements)) {
        $req.boundary = "requirement_only"
        if ([string]$req.summary -match "recommend|buy|product|company|policy|保险公司|产品推荐|购买|保单") {
            $req.summary = "Need further requirement-level assessment before any solution discussion."
        }
    }

    foreach ($risk in (To-JsonArray -Value $AnalysisObject.risk_map)) {
        foreach ($prop in @("risk_exposure", "potential_financial_impact", "existing_protection", "coverage_gap", "reasoning")) {
            $value = [string]$risk.$prop
            if ($value -match "recommend|buy|product|company|policy|保险公司|产品推荐|购买|保单") {
                $risk.$prop = "Requirement-level assessment remains needed; detailed solution discussion is out of scope here."
            }
        }
    }

    $AnalysisObject.guardrails.product_recommendation_included = $false
    return $AnalysisObject
}

function Repair-LogicalInconsistency {
    param($AnalysisObject)

    $priorityMap = @{}
    foreach ($risk in (To-JsonArray -Value $AnalysisObject.risk_map)) {
        $priorityMap[$risk.requirement_type] = $risk.priority
    }

    foreach ($req in (To-JsonArray -Value $AnalysisObject.requirements)) {
        if ($priorityMap.ContainsKey($req.requirement_type)) {
            $req.priority = $priorityMap[$req.requirement_type]
        }
    }

    foreach ($gap in (To-JsonArray -Value $AnalysisObject.coverage_gaps)) {
        if ($priorityMap.ContainsKey($gap.requirement_type)) {
            $gap.priority = $priorityMap[$gap.requirement_type]
        }
    }

    foreach ($priorityEntry in (To-JsonArray -Value $AnalysisObject.priorities)) {
        foreach ($req in (To-JsonArray -Value $AnalysisObject.requirements)) {
            if ($priorityEntry.target_id -eq $req.requirement_id) {
                $priorityEntry.priority = $req.priority
            }
        }
    }

    return $AnalysisObject
}

function Repair-InsufficientInformation {
    param($AnalysisObject)
    $AnalysisObject.risk_map = @()
    $AnalysisObject.coverage_gaps = @()
    $AnalysisObject.requirements = @()
    $AnalysisObject.priorities = @()
    $AnalysisObject.evidence = @()
    return $AnalysisObject
}

function Apply-TargetedRepairs {
    param(
        $AnalysisObject,
        $EvalObject,
        [string]$InputPath
    )

    $repaired = $AnalysisObject | ConvertTo-Json -Depth 50 | ConvertFrom-Json
    $actions = New-Object System.Collections.ArrayList

    foreach ($issue in (To-JsonArray -Value $EvalObject.issues)) {
        switch ([string]$issue.type) {
            "UNSUPPORTED_CONCLUSION" {
                $repaired = Repair-UnsupportedConclusion -AnalysisObject $repaired
                if ($actions -notcontains "realign_evidence_refs") { [void]$actions.Add("realign_evidence_refs") }
            }
            "PRODUCT_RECOMMENDATION_LEAK" {
                $repaired = Repair-ProductLeak -AnalysisObject $repaired
                if ($actions -notcontains "sanitize_product_language") { [void]$actions.Add("sanitize_product_language") }
            }
            "LOGICAL_INCONSISTENCY" {
                $repaired = Repair-LogicalInconsistency -AnalysisObject $repaired
                if ($actions -notcontains "synchronize_priorities") { [void]$actions.Add("synchronize_priorities") }
            }
            "INSUFFICIENT_INFORMATION" {
                $repaired = Repair-InsufficientInformation -AnalysisObject $repaired
                if ($actions -notcontains "remove_formal_analysis_for_insufficient_scope") { [void]$actions.Add("remove_formal_analysis_for_insufficient_scope") }
            }
            "MISSING_RISK" {
                if (-not [string]::IsNullOrWhiteSpace($InputPath)) {
                    $repaired = Invoke-AnalysisFromInput -InputPath $InputPath
                    if ($actions -notcontains "rebuild_analysis_from_input") { [void]$actions.Add("rebuild_analysis_from_input") }
                }
            }
            "INVALID_OUTPUT" {
                if (-not [string]::IsNullOrWhiteSpace($InputPath)) {
                    $repaired = Invoke-AnalysisFromInput -InputPath $InputPath
                    if ($actions -notcontains "rebuild_analysis_from_input") { [void]$actions.Add("rebuild_analysis_from_input") }
                }
            }
        }
    }

    return [pscustomobject]@{
        analysis = $repaired
        actions = @($actions)
    }
}

if ([string]::IsNullOrWhiteSpace($InputJsonPath) -and [string]::IsNullOrWhiteSpace($ExistingAnalysisJsonPath)) {
    throw "Either InputJsonPath or ExistingAnalysisJsonPath must be provided."
}

$currentAnalysis = $null
if (-not [string]::IsNullOrWhiteSpace($ExistingAnalysisJsonPath)) {
    $currentAnalysis = Read-JsonFile -Path $ExistingAnalysisJsonPath
} elseif (-not [string]::IsNullOrWhiteSpace($InputJsonPath)) {
    $currentAnalysis = Invoke-AnalysisFromInput -InputPath $InputJsonPath
}

$repairHistory = New-Object System.Collections.ArrayList
$attemptCount = 0
$finalStatus = "HUMAN_REVIEW_REQUIRED"
$finalEval = $null

while ($attemptCount -le $MAX_RETRY) {
    $currentEval = Invoke-EvalForAnalysis -AnalysisObject $currentAnalysis
    $finalEval = $currentEval

    if ($currentEval.eval_status -eq "PASS") {
        $finalStatus = "PASS"
        break
    }

    if ($attemptCount -ge $MAX_RETRY) {
        $finalStatus = "HUMAN_REVIEW_REQUIRED"
        break
    }

    $repairResult = Apply-TargetedRepairs -AnalysisObject $currentAnalysis -EvalObject $currentEval -InputPath $InputJsonPath
    $currentAnalysis = $repairResult.analysis

    [void]$repairHistory.Add([pscustomobject]@{
        attempt = ($attemptCount + 1)
        issue_types = @(To-JsonArray -Value ($currentEval.issues | ForEach-Object { $_.type }))
        repair_actions = @($repairResult.actions)
        eval_score_before = $currentEval.score
    })

    $attemptCount++
}

$result = [pscustomobject]@{
    repair_summary = [pscustomobject]@{
        final_eval_status = if ($null -ne $finalEval) { [string]$finalEval.eval_status } else { "UNKNOWN" }
        final_eval_score = if ($null -ne $finalEval) { [int]$finalEval.score } else { -1 }
        repair_iterations = $attemptCount
        final_status = $finalStatus
    }
    final_status = $finalStatus
    attempt_count = $attemptCount
    final_analysis = $currentAnalysis
    final_eval = $finalEval
    repair_history = @($repairHistory)
}

$jsonOutput = $result | ConvertTo-Json -Depth 60
if (-not [string]::IsNullOrWhiteSpace($OutputJsonPath)) {
    Set-Content -Path $OutputJsonPath -Value $jsonOutput -Encoding UTF8
}

Write-Output $jsonOutput
