[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AnalysisJsonPath,
    [string]$OutputJsonPath = ""
)

$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Encoding UTF8 -Path $Path | ConvertFrom-Json)
}

function To-JsonArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value)
}

function Add-Issue {
    param(
        [System.Collections.ArrayList]$Issues,
        [string]$Type,
        [string]$Location,
        [string]$Reason,
        [string]$Evidence
    )

    [void]$Issues.Add([pscustomobject]@{
        type = $Type
        location = $Location
        reason = $Reason
        evidence = $Evidence
    })
}

function Has-ProductLeak {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $false
    }

    $patterns = @(
        "保险公司",
        "产品推荐",
        "购买",
        "推荐",
        "保单",
        "product plan",
        "buy",
        "policy",
        "insurance company"
    )

    foreach ($pattern in $patterns) {
        if ($Text -match [regex]::Escape($pattern)) {
            return $true
        }
    }

    return $false
}

function Get-EvidenceMap {
    param($EvidenceEntries)
    $map = @{}
    foreach ($entry in (To-JsonArray -Value $EvidenceEntries)) {
        $map[$entry.evidence_id] = $entry
    }
    return $map
}

function Get-RequirementMap {
    param($Requirements)
    $map = @{}
    foreach ($item in (To-JsonArray -Value $Requirements)) {
        $map[$item.requirement_type] = $item
    }
    return $map
}

function Get-CoverageMap {
    param($CoverageGaps)
    $map = @{}
    foreach ($item in (To-JsonArray -Value $CoverageGaps)) {
        $map[$item.requirement_type] = $item
    }
    return $map
}

function Get-PriorityMap {
    param($PriorityEntries)
    $map = @{}
    foreach ($item in (To-JsonArray -Value $PriorityEntries)) {
        $map[$item.target_id] = $item
    }
    return $map
}

$analysis = Read-JsonFile -Path $AnalysisJsonPath
$issues = New-Object System.Collections.ArrayList
$checkScores = [ordered]@{
    completeness = 100
    evidence_grounding = 100
    logical_consistency = 100
    information_sufficiency = 100
    requirement_product_separation = 100
}

$riskEntries = To-JsonArray -Value $analysis.risk_map
$requirements = To-JsonArray -Value $analysis.requirements
$coverageGaps = To-JsonArray -Value $analysis.coverage_gaps
$priorityEntries = To-JsonArray -Value $analysis.priorities
$evidenceEntries = To-JsonArray -Value $analysis.evidence
$scopeResults = To-JsonArray -Value $analysis.information_sufficiency.scope_results

$evidenceMap = Get-EvidenceMap -EvidenceEntries $evidenceEntries
$requirementMap = Get-RequirementMap -Requirements $requirements
$coverageMap = Get-CoverageMap -CoverageGaps $coverageGaps
$priorityMap = Get-PriorityMap -PriorityEntries $priorityEntries

foreach ($scope in $scopeResults) {
    $analyzable = @("SUFFICIENT", "PARTIAL") -contains $scope.scope_status
    if ($analyzable) {
        $hasRisk = @($riskEntries | Where-Object { $_.requirement_type -eq $scope.requirement_type }).Count -gt 0
        if (-not $hasRisk) {
            Add-Issue -Issues $issues -Type "MISSING_RISK" -Location ("scope_results[{0}]" -f $scope.requirement_type) -Reason "Analyzable scope is missing risk_map entry." -Evidence ("scope_status={0}" -f $scope.scope_status)
            $checkScores.completeness = [Math]::Max(0, $checkScores.completeness - 40)
        }
    } else {
        $hasRisk = @($riskEntries | Where-Object { $_.requirement_type -eq $scope.requirement_type }).Count -gt 0
        $hasRequirement = @($requirements | Where-Object { $_.requirement_type -eq $scope.requirement_type }).Count -gt 0
        if ($hasRisk -or $hasRequirement) {
            Add-Issue -Issues $issues -Type "INSUFFICIENT_INFORMATION" -Location ("scope_results[{0}]" -f $scope.requirement_type) -Reason "Non-analyzable scope still contains formal analysis output." -Evidence ("scope_status={0}" -f $scope.scope_status)
            $checkScores.information_sufficiency = [Math]::Max(0, $checkScores.information_sufficiency - 40)
        }
    }
}

foreach ($risk in $riskEntries) {
    $location = "risk_map[{0}]" -f $risk.requirement_type
    $evidenceRefs = To-JsonArray -Value $risk.evidence_refs
    if ($evidenceRefs.Count -eq 0) {
        Add-Issue -Issues $issues -Type "UNSUPPORTED_CONCLUSION" -Location $location -Reason "Risk entry does not reference evidence." -Evidence "evidence_refs=[]"
        $checkScores.evidence_grounding = [Math]::Max(0, $checkScores.evidence_grounding - 35)
        continue
    }

    foreach ($ref in $evidenceRefs) {
        if (-not $evidenceMap.ContainsKey($ref)) {
            Add-Issue -Issues $issues -Type "UNSUPPORTED_CONCLUSION" -Location $location -Reason "Risk entry references missing evidence id." -Evidence ("missing evidence_id={0}" -f $ref)
            $checkScores.evidence_grounding = [Math]::Max(0, $checkScores.evidence_grounding - 25)
            continue
        }

        $ev = $evidenceMap[$ref]
        if ((To-JsonArray -Value $ev.fact_refs).Count -eq 0) {
            Add-Issue -Issues $issues -Type "UNSUPPORTED_CONCLUSION" -Location ("evidence[{0}]" -f $ref) -Reason "Evidence entry has no fact refs." -Evidence "fact_refs=[]"
            $checkScores.evidence_grounding = [Math]::Max(0, $checkScores.evidence_grounding - 20)
        }
    }
}

foreach ($req in $requirements) {
    if ($req.boundary -ne "requirement_only") {
        Add-Issue -Issues $issues -Type "PRODUCT_RECOMMENDATION_LEAK" -Location ("requirements[{0}]" -f $req.requirement_type) -Reason "Requirement entry crossed product boundary." -Evidence ("boundary={0}" -f $req.boundary)
        $checkScores.requirement_product_separation = [Math]::Max(0, $checkScores.requirement_product_separation - 60)
    }

    if (Has-ProductLeak -Text $req.summary) {
        Add-Issue -Issues $issues -Type "PRODUCT_RECOMMENDATION_LEAK" -Location ("requirements[{0}].summary" -f $req.requirement_type) -Reason "Requirement summary contains product-level language." -Evidence $req.summary
        $checkScores.requirement_product_separation = [Math]::Max(0, $checkScores.requirement_product_separation - 40)
    }
}

foreach ($risk in $riskEntries) {
    foreach ($field in @($risk.risk_exposure, $risk.potential_financial_impact, $risk.existing_protection, $risk.coverage_gap, $risk.reasoning)) {
        if (Has-ProductLeak -Text ([string]$field)) {
            Add-Issue -Issues $issues -Type "PRODUCT_RECOMMENDATION_LEAK" -Location ("risk_map[{0}]" -f $risk.requirement_type) -Reason "Risk entry contains product-level language." -Evidence ([string]$field)
            $checkScores.requirement_product_separation = [Math]::Max(0, $checkScores.requirement_product_separation - 25)
            break
        }
    }
}

if (([string]$analysis.analysis_status -eq "NEED_MORE_INFORMATION") -or ([string]$analysis.analysis_status -eq "CONFLICTING_INFORMATION")) {
    if ($riskEntries.Count -gt 0 -or $requirements.Count -gt 0) {
        Add-Issue -Issues $issues -Type "INSUFFICIENT_INFORMATION" -Location "analysis_status" -Reason "Analysis produced formal conclusions despite insufficient/conflicting status." -Evidence ("analysis_status={0}" -f $analysis.analysis_status)
        $checkScores.information_sufficiency = [Math]::Max(0, $checkScores.information_sufficiency - 70)
    }
}

if ((([string]$analysis.information_sufficiency.sufficiency_status -eq "INSUFFICIENT") -or ([string]$analysis.information_sufficiency.sufficiency_status -eq "CONFLICTING")) -and ($riskEntries.Count -gt 0 -or $requirements.Count -gt 0)) {
    Add-Issue -Issues $issues -Type "INSUFFICIENT_INFORMATION" -Location "information_sufficiency" -Reason "Output contains formal analysis while sufficiency state is not analyzable." -Evidence ("sufficiency_status={0}" -f $analysis.information_sufficiency.sufficiency_status)
    $checkScores.information_sufficiency = [Math]::Max(0, $checkScores.information_sufficiency - 40)
}

foreach ($risk in $riskEntries) {
    $req = $requirementMap[$risk.requirement_type]
    $cov = $coverageMap[$risk.requirement_type]

    if ($null -eq $req) {
        Add-Issue -Issues $issues -Type "LOGICAL_INCONSISTENCY" -Location ("risk_map[{0}]" -f $risk.requirement_type) -Reason "Risk exists without matching requirement." -Evidence ("requirement_type={0}" -f $risk.requirement_type)
        $checkScores.logical_consistency = [Math]::Max(0, $checkScores.logical_consistency - 25)
        continue
    }

    if ($risk.priority -ne $req.priority) {
        Add-Issue -Issues $issues -Type "LOGICAL_INCONSISTENCY" -Location ("risk_map[{0}]" -f $risk.requirement_type) -Reason "Risk priority and requirement priority do not match." -Evidence ("risk={0}; requirement={1}" -f $risk.priority, $req.priority)
        $checkScores.logical_consistency = [Math]::Max(0, $checkScores.logical_consistency - 25)
    }

    if ($null -ne $cov -and $cov.priority -ne $risk.priority) {
        Add-Issue -Issues $issues -Type "LOGICAL_INCONSISTENCY" -Location ("coverage_gaps[{0}]" -f $risk.requirement_type) -Reason "Coverage gap priority and risk priority do not match." -Evidence ("coverage_gap={0}; risk={1}" -f $cov.priority, $risk.priority)
        $checkScores.logical_consistency = [Math]::Max(0, $checkScores.logical_consistency - 20)
    }

    if (-not $priorityMap.ContainsKey($req.requirement_id)) {
        Add-Issue -Issues $issues -Type "LOGICAL_INCONSISTENCY" -Location ("requirements[{0}]" -f $risk.requirement_type) -Reason "Requirement is missing matching priority entry." -Evidence ("requirement_id={0}" -f $req.requirement_id)
        $checkScores.logical_consistency = [Math]::Max(0, $checkScores.logical_consistency - 20)
    }
}

foreach ($key in @("analysis_status", "analysis_scope", "information_sufficiency", "risk_map", "coverage_gaps", "requirements", "priorities", "evidence", "guardrails")) {
    if ($null -eq $analysis.$key) {
        Add-Issue -Issues $issues -Type "INVALID_OUTPUT" -Location $key -Reason "Missing required output section." -Evidence ("missing field {0}" -f $key)
        $checkScores.completeness = [Math]::Max(0, $checkScores.completeness - 20)
    }
}

$overallScore = [Math]::Round((($checkScores.completeness + $checkScores.evidence_grounding + $checkScores.logical_consistency + $checkScores.information_sufficiency + $checkScores.requirement_product_separation) / 5), 0)
$evalStatus = "PASS"
$repairRequired = $false
if ($issues.Count -gt 0) {
    $evalStatus = "FAIL"
    $repairRequired = $true
}

$result = [pscustomobject]@{
    eval_status = $evalStatus
    score = [int]$overallScore
    checks = [pscustomobject]@{
        completeness = [int]$checkScores.completeness
        evidence_grounding = [int]$checkScores.evidence_grounding
        logical_consistency = [int]$checkScores.logical_consistency
        information_sufficiency = [int]$checkScores.information_sufficiency
        requirement_product_separation = [int]$checkScores.requirement_product_separation
    }
    issues = @($issues)
    repair_required = $repairRequired
}

$jsonOutput = $result | ConvertTo-Json -Depth 20
if (-not [string]::IsNullOrWhiteSpace($OutputJsonPath)) {
    Set-Content -Path $OutputJsonPath -Value $jsonOutput -Encoding UTF8
}

Write-Output $jsonOutput
