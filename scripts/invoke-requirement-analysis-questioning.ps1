[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputJsonPath,
    [string]$OutputJsonPath = ""
)

$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$Root = Split-Path -Parent $PSScriptRoot
$BaseDir = Join-Path $Root "02-requirement-analysis"
$QuestionRulesPath = Join-Path $BaseDir "config\question-generation.rules.json"
$SufficiencyScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-sufficiency.ps1"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Encoding UTF8 -Path $Path | ConvertFrom-Json)
}

function To-JsonArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value)
}

function Get-FieldRuleMap {
    param($FieldRules)
    $map = @{}
    foreach ($rule in (To-JsonArray -Value $FieldRules)) {
        $map[$rule.field] = $rule
    }
    return $map
}

function Get-AskedQuestionMap {
    param($AskedQuestions)
    $map = @{}
    foreach ($item in (To-JsonArray -Value $AskedQuestions)) {
        $map[$item.field] = $item
    }
    return $map
}

function Get-TemplateByAskCount {
    param(
        $Templates,
        [int]$AskCount
    )

    $items = To-JsonArray -Value $Templates
    if ($items.Count -eq 0) {
        return ""
    }

    if ($AskCount -lt $items.Count) {
        return $items[$AskCount]
    }

    return $items[$items.Count - 1]
}

function Get-PriorityBaseScore {
    param(
        [string]$Importance,
        $QuestionRules
    )
    return [double]$QuestionRules.selection.base_priority_scores.$Importance
}

function Get-ImpactScore {
    param(
        [string]$Impact,
        $QuestionRules
    )
    return [double]$QuestionRules.selection.impact_scores.$Impact
}

function Get-GapTypeBonus {
    param(
        [string]$GapType,
        $QuestionRules
    )
    return [double]$QuestionRules.selection.gap_type_bonus.$GapType
}

function Get-DifficultyScore {
    param(
        [string]$Difficulty,
        $QuestionRules
    )
    return [double]$QuestionRules.selection.difficulty_scores.$Difficulty
}

function Get-RelatedRequirementTypes {
    param(
        [string]$Field,
        $ScopeResults
    )

    $types = New-Object System.Collections.ArrayList
    foreach ($scope in (To-JsonArray -Value $ScopeResults)) {
        $shouldInclude = ($scope.blocking_fields -contains $Field) -or ($scope.conflict_fields -contains $Field)
        if ($shouldInclude -or $scope.scope_status -ne "SUFFICIENT") {
            if ($types -notcontains $scope.requirement_type) {
                [void]$types.Add($scope.requirement_type)
            }
        }
    }

    if ($types.Count -eq 0) {
        foreach ($scope in (To-JsonArray -Value $ScopeResults)) {
            if ($types -notcontains $scope.requirement_type) {
                [void]$types.Add($scope.requirement_type)
            }
        }
    }

    return @($types)
}

function Build-QuestionEntry {
    param(
        $Gap,
        $FieldRule,
        $QuestionRules,
        $AskedQuestion,
        $ScopeResults,
        [int]$Index
    )

    $askCount = 0
    if ($null -ne $AskedQuestion) {
        $askCount = [int]$AskedQuestion.ask_count
    }

    $repeatPenalty = $askCount * [double]$QuestionRules.selection.repeat_penalty_per_ask
    $priorityScore = (Get-PriorityBaseScore -Importance $Gap.importance -QuestionRules $QuestionRules) +
        (Get-ImpactScore -Impact $Gap.impact -QuestionRules $QuestionRules) +
        (Get-GapTypeBonus -GapType $Gap.gap_type -QuestionRules $QuestionRules) +
        (Get-DifficultyScore -Difficulty $FieldRule.difficulty -QuestionRules $QuestionRules) -
        $repeatPenalty

    $questionType = "gap_fill"
    $questionText = Get-TemplateByAskCount -Templates $FieldRule.question_templates -AskCount $askCount
    if ($Gap.gap_type -eq "CONFLICTING_INFORMATION") {
        $questionType = "conflict_confirmation"
        $questionText = $FieldRule.conflict_template
    }

    return [pscustomobject]@{
        question_id = ("QAQ{0:d3}" -f $Index)
        field = $Gap.field
        question_type = $questionType
        priority_score = [math]::Round($priorityScore, 2)
        question = $questionText
        why_ask = $FieldRule.why_ask
        allow_approximate = [bool]$FieldRule.allow_approximate
        related_requirement_types = @(Get-RelatedRequirementTypes -Field $Gap.field -ScopeResults $ScopeResults)
    }
}

$input = Read-JsonFile -Path $InputJsonPath
$questionRules = Read-JsonFile -Path $QuestionRulesPath
$result = Invoke-RaScriptToObject -ScriptPath $SufficiencyScript -Arguments @{ InputJsonPath = $InputJsonPath } -ExpectedTopLevelProperty "information_sufficiency"

$fieldRuleMap = Get-FieldRuleMap -FieldRules $questionRules.field_rules
$askedQuestionMap = Get-AskedQuestionMap -AskedQuestions $input.question_context.asked_questions
$answeredFields = @($input.question_context.answered_fields)

$candidates = New-Object System.Collections.ArrayList
$deferredFields = New-Object System.Collections.ArrayList
$emittedFields = @{}

foreach ($gap in (To-JsonArray -Value $result.information_gaps)) {
    if ($answeredFields -contains $gap.field) {
        continue
    }

    if ($askedQuestionMap.ContainsKey($gap.field)) {
        $asked = $askedQuestionMap[$gap.field]
        if ($asked.status -eq "answered") {
            continue
        }
    } else {
        $asked = $null
    }

    # 字段级去重：同一字段可能因多 scope 在 information_gaps 中重复出现，
    # 只生成一次提问，避免重复询问（F5 修复）。
    if ($emittedFields.ContainsKey($gap.field)) {
        continue
    }

    if (-not $fieldRuleMap.ContainsKey($gap.field)) {
        [void]$deferredFields.Add($gap.field)
        $emittedFields[$gap.field] = $true
        continue
    }

    $fieldRule = $fieldRuleMap[$gap.field]
    $questionEntry = Build-QuestionEntry -Gap $gap -FieldRule $fieldRule -QuestionRules $questionRules -AskedQuestion $asked -ScopeResults $result.information_sufficiency.scope_results -Index ($candidates.Count + 1)
    [void]$candidates.Add($questionEntry)
    $emittedFields[$gap.field] = $true
}

$sortedCandidates = @($candidates | Sort-Object -Property @{ Expression = "priority_score"; Descending = $true }, @{ Expression = "field"; Descending = $false })
$selectedQuestions = @()
$maxQuestions = [int]$questionRules.selection.max_questions_per_round
if ($sortedCandidates.Count -gt 0) {
    $selectedQuestions = @($sortedCandidates | Select-Object -First $maxQuestions)
}

foreach ($candidate in $sortedCandidates | Select-Object -Skip $maxQuestions) {
    if ($deferredFields -notcontains $candidate.field) {
        [void]$deferredFields.Add($candidate.field)
    }
}

$questionStatus = "NOT_NEEDED"
if ($selectedQuestions.Count -gt 0) {
    $hasConflictQuestion = @($selectedQuestions | Where-Object { $_.question_type -eq "conflict_confirmation" }).Count -gt 0
    if ($hasConflictQuestion) {
        $questionStatus = "CONFLICT_CONFIRMATION_REQUIRED"
    } else {
        $questionStatus = "READY_TO_ASK"
    }
} elseif ($result.analysis_status -ne "COMPLETE") {
    $questionStatus = "WAITING_FOR_USER_RESPONSE"
}

$result | Add-Member -NotePropertyName question_plan -NotePropertyValue ([pscustomobject]@{
    question_status = $questionStatus
    selected_questions = @($selectedQuestions)
    deferred_fields = @($deferredFields)
}) -Force

$jsonOutput = $result | ConvertTo-Json -Depth 25
if (-not [string]::IsNullOrWhiteSpace($OutputJsonPath)) {
    Set-Content -Path $OutputJsonPath -Value $jsonOutput -Encoding UTF8
}

Write-Output $jsonOutput
