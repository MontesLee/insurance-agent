[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputJsonPath,
    [string]$OutputJsonPath = ""
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BaseDir = $Root
$RulesPath = Join-Path $BaseDir "resources\config\information-sufficiency.rules.json"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Encoding UTF8 -Path $Path | ConvertFrom-Json)
}

function To-JsonArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value)
}

function Get-FactMap {
    param($Facts)

    $map = @{}
    foreach ($fact in (To-JsonArray -Value $Facts)) {
        if ($null -eq $fact) { continue }
        $map[$fact.field] = $fact
    }
    return $map
}

function Get-ConflictMap {
    param($Conflicts)

    $map = @{}
    foreach ($conflict in (To-JsonArray -Value $Conflicts)) {
        if ($null -eq $conflict) { continue }
        $isBlockingConflict = @("UNRESOLVED", "NEEDS_CONFIRMATION") -contains $conflict.resolution_status
        if ($isBlockingConflict) {
            $map[$conflict.field] = $conflict
        }
    }
    return $map
}

function Get-ImpactSeverityRank {
    param([string]$Impact)
    switch ($Impact) {
        "high" { return 3 }
        "medium" { return 2 }
        "low" { return 1 }
        default { return 0 }
    }
}

function Get-GapImportance {
    param(
        [string]$Category,
        [string]$Impact
    )

    if ($Category -eq "required") {
        switch ($Impact) {
            "high" { return "P0_CRITICAL" }
            "medium" { return "P1_HIGH" }
            default { return "P2_MEDIUM" }
        }
    }

    if ($Category -eq "recommended") {
        switch ($Impact) {
            "high" { return "P2_MEDIUM" }
            default { return "P3_LOW" }
        }
    }

    return "P3_LOW"
}

function Get-CategoryWeight {
    param(
        $Scoring,
        [string]$Category,
        [int]$Count
    )

    if ($Count -le 0) { return 0.0 }

    switch ($Category) {
        "required" { return ([double]$Scoring.required_total_weight / $Count) }
        "recommended" { return ([double]$Scoring.recommended_total_weight / $Count) }
        "optional" { return ([double]$Scoring.optional_total_weight / $Count) }
        default { return 0.0 }
    }
}

function Get-FieldState {
    param(
        [string]$Field,
        $FactMap,
        $ConflictMap
    )

    if ($ConflictMap.ContainsKey($Field)) {
        return [pscustomobject]@{
            normalized_state = "CONFLICTING"
            value_status = "UNKNOWN"
            gap_type = "CONFLICTING_INFORMATION"
            reason_suffix = "unresolved conflict"
        }
    }

    if ($FactMap.ContainsKey($Field)) {
        $fact = $FactMap[$Field]
        if ($fact.value_status -eq "KNOWN") {
            return [pscustomobject]@{
                normalized_state = "KNOWN"
                value_status = "KNOWN"
                gap_type = ""
                reason_suffix = ""
            }
        }
        if ($fact.value_status -eq "ESTIMATED") {
            return [pscustomobject]@{
                normalized_state = "ESTIMATED"
                value_status = "ESTIMATED"
                gap_type = "CANNOT_INFER"
                reason_suffix = "estimated only"
            }
        }
        if ($fact.value_status -eq "ASSUMED") {
            return [pscustomobject]@{
                normalized_state = "ASSUMED"
                value_status = "ASSUMED"
                gap_type = "CANNOT_INFER"
                reason_suffix = "assumed only"
            }
        }
        if ($fact.value_status -eq "UNKNOWN") {
            return [pscustomobject]@{
                normalized_state = "UNKNOWN"
                value_status = "UNKNOWN"
                gap_type = "EXPLICIT_UNKNOWN"
                reason_suffix = "explicitly unknown"
            }
        }

        return [pscustomobject]@{
            normalized_state = "UNKNOWN"
            value_status = "UNKNOWN"
            gap_type = "CANNOT_INFER"
            reason_suffix = "unrecognized value status"
        }
    }

    return [pscustomobject]@{
        normalized_state = "NOT_PROVIDED"
        value_status = "UNKNOWN"
        gap_type = "NOT_PROVIDED"
        reason_suffix = "not provided"
    }
}

function Get-StateMultiplier {
    param(
        [string]$State,
        $Scoring
    )

    switch ($State) {
        "KNOWN" { return 1.0 }
        "ESTIMATED" { return [double]$Scoring.estimated_multiplier }
        "ASSUMED" { return [double]$Scoring.assumed_multiplier }
        default { return 0.0 }
    }
}

function Invoke-ScopeSufficiency {
    param(
        $ScopeRule,
        $Scoring,
        $FactMap,
        $ConflictMap
    )

    $scopeType = $ScopeRule.requirement_type
    $requiredList = To-JsonArray -Value $ScopeRule.required_information
    $recommendedList = To-JsonArray -Value $ScopeRule.recommended_information
    $optionalList = To-JsonArray -Value $ScopeRule.optional_information

    $scopeScore = 0.0
    $gaps = New-Object System.Collections.ArrayList
    $blockingFields = New-Object System.Collections.ArrayList
    $conflictFields = New-Object System.Collections.ArrayList
    $requiredHighHardMissing = $false
    $requiredMediumMissingCount = 0
    $hasEstimatedOrAssumedRequired = $false

    $categories = @(
        @{ Name = "required"; Items = $requiredList },
        @{ Name = "recommended"; Items = $recommendedList },
        @{ Name = "optional"; Items = $optionalList }
    )

    foreach ($category in $categories) {
        $items = To-JsonArray -Value $category.Items
        $perFieldWeight = Get-CategoryWeight -Scoring $Scoring -Category $category.Name -Count $items.Count

        foreach ($item in $items) {
            $fieldState = Get-FieldState -Field $item.field -FactMap $FactMap -ConflictMap $ConflictMap
            $multiplier = Get-StateMultiplier -State $fieldState.normalized_state -Scoring $Scoring
            $scopeScore += ($perFieldWeight * $multiplier)

            if ($fieldState.normalized_state -eq "CONFLICTING") {
                [void]$conflictFields.Add($item.field)
            }

            $needsGap = $fieldState.normalized_state -ne "KNOWN"
            if ($needsGap) {
                $reason = "{0}; {1}" -f $item.reason, $fieldState.reason_suffix
                [void]$gaps.Add([pscustomobject]@{
                    field = $item.field
                    importance = (Get-GapImportance -Category $category.Name -Impact $item.impact)
                    impact = $item.impact
                    reason = $reason
                    gap_type = $fieldState.gap_type
                })
            }

            if ($category.Name -eq "required") {
                if (@("UNKNOWN", "NOT_PROVIDED", "CONFLICTING") -contains $fieldState.normalized_state) {
                    [void]$blockingFields.Add($item.field)
                }

                if (($item.impact -eq "high") -and (@("UNKNOWN", "NOT_PROVIDED", "CONFLICTING") -contains $fieldState.normalized_state)) {
                    $requiredHighHardMissing = $true
                }

                if (($item.impact -eq "medium") -and (@("UNKNOWN", "NOT_PROVIDED", "CONFLICTING") -contains $fieldState.normalized_state)) {
                    $requiredMediumMissingCount++
                }

                if (@("ESTIMATED", "ASSUMED") -contains $fieldState.normalized_state) {
                    $hasEstimatedOrAssumedRequired = $true
                }
            }
        }
    }

    $scopeStatus = "SUFFICIENT"
    if ($conflictFields.Count -gt 0) {
        $scopeStatus = "CONFLICTING"
    } elseif ($requiredHighHardMissing) {
        $scopeStatus = "INSUFFICIENT"
    } elseif ($scopeScore -lt [double]$Scoring.thresholds.partial) {
        $scopeStatus = "INSUFFICIENT"
    } elseif (($requiredMediumMissingCount -gt 0) -or ($scopeScore -lt [double]$Scoring.thresholds.sufficient) -or $hasEstimatedOrAssumedRequired) {
        $scopeStatus = "PARTIAL"
    }

    return [pscustomobject]@{
        requirement_type = $scopeType
        scope_score = [math]::Round($scopeScore, 4)
        scope_status = $scopeStatus
        blocking_fields = @($blockingFields)
        conflict_fields = @($conflictFields)
        gaps = @($gaps)
    }
}

$rules = Read-JsonFile -Path $RulesPath
$input = Read-JsonFile -Path $InputJsonPath

$factMap = Get-FactMap -Facts $input.client_profile.facts
$conflictMap = Get-ConflictMap -Conflicts $input.conflicts
$scopeResults = New-Object System.Collections.ArrayList
$allGaps = New-Object System.Collections.ArrayList
$allBlockingFields = New-Object System.Collections.ArrayList
$allConflictFields = New-Object System.Collections.ArrayList

foreach ($scope in (To-JsonArray -Value $input.analysis_scope)) {
    $scopeRule = $null
    foreach ($rule in (To-JsonArray -Value $rules.requirement_dependencies)) {
        if ($rule.requirement_type -eq $scope) {
            $scopeRule = $rule
            break
        }
    }

    if ($null -eq $scopeRule) {
        throw "Missing sufficiency rule for scope: $scope"
    }

    $scopeResult = Invoke-ScopeSufficiency -ScopeRule $scopeRule -Scoring $rules.scoring -FactMap $factMap -ConflictMap $conflictMap
    [void]$scopeResults.Add([pscustomobject]@{
        requirement_type = $scopeResult.requirement_type
        scope_score = $scopeResult.scope_score
        scope_status = $scopeResult.scope_status
        blocking_fields = $scopeResult.blocking_fields
        conflict_fields = $scopeResult.conflict_fields
    })

    foreach ($gap in (To-JsonArray -Value $scopeResult.gaps)) {
        [void]$allGaps.Add($gap)
    }
    foreach ($field in (To-JsonArray -Value $scopeResult.blocking_fields)) {
        if ($allBlockingFields -notcontains $field) {
            [void]$allBlockingFields.Add($field)
        }
    }
    foreach ($field in (To-JsonArray -Value $scopeResult.conflict_fields)) {
        if ($allConflictFields -notcontains $field) {
            [void]$allConflictFields.Add($field)
        }
    }
}

$overallScore = 0.0
if ($scopeResults.Count -gt 0) {
    foreach ($result in $scopeResults) {
        $overallScore += [double]$result.scope_score
    }
    $overallScore = $overallScore / $scopeResults.Count
}

$overallSufficiencyStatus = "SUFFICIENT"
$analysisStatus = "COMPLETE"
$decisionNote = "Current information is sufficient for formal requirement analysis."

$hasConflict = ($allConflictFields.Count -gt 0)
$hasInsufficient = $false
$hasPartial = $false
foreach ($result in $scopeResults) {
    if ($result.scope_status -eq "INSUFFICIENT") { $hasInsufficient = $true }
    if ($result.scope_status -eq "PARTIAL") { $hasPartial = $true }
    if ($result.scope_status -eq "CONFLICTING") { $hasConflict = $true }
}

if ($hasConflict) {
    $overallSufficiencyStatus = "CONFLICTING"
    $analysisStatus = "CONFLICTING_INFORMATION"
    $decisionNote = "Key conflicts exist. Formal analysis should not proceed until they are resolved."
} elseif ($hasInsufficient -or ($overallScore -lt [double]$rules.scoring.thresholds.partial)) {
    $overallSufficiencyStatus = "INSUFFICIENT"
    $analysisStatus = "NEED_MORE_INFORMATION"
    $decisionNote = "High-impact information is missing. More information is required before analysis."
} elseif ($hasPartial -or ($overallScore -lt [double]$rules.scoring.thresholds.sufficient)) {
    $overallSufficiencyStatus = "PARTIAL"
    $analysisStatus = "PRELIMINARY"
    $decisionNote = "Preliminary analysis is allowed, but uncertainty must remain explicit."
}

$unknowns = New-Object System.Collections.ArrayList
foreach ($gap in $allGaps) {
    if ($gap.gap_type -ne "CONFLICTING_INFORMATION") {
        [void]$unknowns.Add([pscustomobject]@{
            field = $gap.field
            reason = $gap.reason
        })
    }
}

$nextActions = New-Object System.Collections.ArrayList
if ($analysisStatus -eq "CONFLICTING_INFORMATION") {
    [void]$nextActions.Add([pscustomobject]@{
        action_type = "ask_user"
        description = "Resolve conflicting fields first, then re-run sufficiency."
    })
    [void]$nextActions.Add([pscustomobject]@{
        action_type = "recheck_sufficiency"
        description = "Re-run sufficiency after conflict resolution."
    })
} elseif ($analysisStatus -eq "NEED_MORE_INFORMATION") {
    [void]$nextActions.Add([pscustomobject]@{
        action_type = "ask_user"
        description = "Collect the high-impact blocking fields first."
    })
    [void]$nextActions.Add([pscustomobject]@{
        action_type = "recheck_sufficiency"
        description = "Re-run sufficiency after collecting the missing information."
    })
} elseif ($analysisStatus -eq "PRELIMINARY") {
    [void]$nextActions.Add([pscustomobject]@{
        action_type = "proceed_analysis"
        description = "Proceed with preliminary analysis and keep unknowns and assumptions explicit."
    })
    [void]$nextActions.Add([pscustomobject]@{
        action_type = "ask_user"
        description = "Collect recommended high-value fields to improve analysis stability."
    })
} else {
    [void]$nextActions.Add([pscustomobject]@{
        action_type = "proceed_analysis"
        description = "Information is sufficient. Proceed to formal requirement analysis."
    })
}

$result = [pscustomobject]@{
    analysis_status = $analysisStatus
    analysis_scope = @($input.analysis_scope)
    information_sufficiency = [pscustomobject]@{
        sufficiency_status = $overallSufficiencyStatus
        decision_note = $decisionNote
        method = "weighted_dependency_map_v1"
        sufficiency_score = [math]::Round($overallScore, 4)
        scope_results = @($scopeResults)
        blocking_fields = @($allBlockingFields)
        conflict_fields = @($allConflictFields)
    }
    information_gaps = @($allGaps)
    risk_map = @()
    coverage_gaps = @()
    requirements = @()
    priorities = @()
    evidence = @()
    assumptions = @()
    unknowns = @($unknowns)
    next_actions = @($nextActions)
    adapter_trace = [pscustomobject]@{
        source_skill = "client_intake"
        consumed_fields = @($factMap.Keys)
    }
    guardrails = [pscustomobject]@{
        product_recommendation_included = $false
    }
}

$jsonOutput = $result | ConvertTo-Json -Depth 20

if (-not [string]::IsNullOrWhiteSpace($OutputJsonPath)) {
    Set-Content -Path $OutputJsonPath -Value $jsonOutput -Encoding UTF8
}

Write-Output $jsonOutput
