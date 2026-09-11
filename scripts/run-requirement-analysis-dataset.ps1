[CmdletBinding()]
param(
    [string]$DatasetPath = "d:\Workspace\insurance-agent\02-requirement-analysis\tests\dataset\requirement-analysis.dataset.json",
    [string]$OutputJsonPath = ""
)

$ErrorActionPreference = "Stop"

$AnalysisScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-analysis.ps1"
$EvalScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-eval.ps1"
$QuestioningScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-questioning.ps1"
$UpdateContextScript = Join-Path $PSScriptRoot "update-requirement-analysis-context.ps1"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Encoding UTF8 -Path $Path | ConvertFrom-Json)
}

function To-JsonArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value)
}

function Save-TempJson {
    param(
        $Object,
        [string]$Prefix
    )
    $path = Join-Path ([System.IO.Path]::GetTempPath()) ("{0}-{1}.json" -f $Prefix, ([guid]::NewGuid().ToString("N")))
    $Object | ConvertTo-Json -Depth 80 | Set-Content -Path $path -Encoding UTF8
    return $path
}

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) {
    throw "Missing runtime lib: $RuntimeLib"
}
. $RuntimeLib

function ConvertTo-ArrayList {
    param($Value)
    $list = New-Object System.Collections.ArrayList
    foreach ($item in (To-JsonArray -Value $Value)) {
        [void]$list.Add($item)
    }
    return ,$list
}

function Merge-UpdatesIntoInputObject {
    param(
        $InputObject,
        $UpdateObject
    )
    $facts = ConvertTo-ArrayList -Value $InputObject.client_profile.facts
    $askedQuestions = ConvertTo-ArrayList -Value $InputObject.question_context.asked_questions
    $answeredFields = ConvertTo-ArrayList -Value $InputObject.question_context.answered_fields
    $conflicts = ConvertTo-ArrayList -Value $InputObject.conflicts

    foreach ($item in (To-JsonArray -Value $UpdateObject.answered_facts)) {
        $existingIndex = -1
        for ($i = 0; $i -lt $facts.Count; $i++) {
            if ($facts[$i].field -eq $item.field) {
                $existingIndex = $i
                break
            }
        }
        if ($existingIndex -ge 0) {
            $facts[$existingIndex] = $item
        } else {
            [void]$facts.Add($item)
        }
        if ($answeredFields -notcontains $item.field) {
            [void]$answeredFields.Add($item.field)
        }

        $askedIndex = -1
        for ($j = 0; $j -lt $askedQuestions.Count; $j++) {
            if ($askedQuestions[$j].field -eq $item.field) {
                $askedIndex = $j
                break
            }
        }
        if ($askedIndex -ge 0) {
            $existingAsked = $askedQuestions[$askedIndex]
            $askedQuestions[$askedIndex] = [pscustomobject]@{
                field        = $item.field
                status       = "answered"
                ask_count    = [int]$existingAsked.ask_count
                last_question = $existingAsked.last_question
            }
        } else {
            [void]$askedQuestions.Add([pscustomobject]@{
                field        = $item.field
                status       = "answered"
                ask_count    = 0
                last_question = ""
            })
        }
    }

    foreach ($item in (To-JsonArray -Value $UpdateObject.asked_questions)) {
        $askedIndex = -1
        for ($i = 0; $i -lt $askedQuestions.Count; $i++) {
            if ($askedQuestions[$i].field -eq $item.field) {
                $askedIndex = $i
                break
            }
        }
        if ($askedIndex -ge 0) {
            $previous = $askedQuestions[$askedIndex]
            $askedQuestions[$askedIndex] = [pscustomobject]@{
                field        = $item.field
                status       = $item.status
                ask_count    = ([int]$previous.ask_count + 1)
                last_question = $item.last_question
            }
        } else {
            [void]$askedQuestions.Add([pscustomobject]@{
                field        = $item.field
                status       = $item.status
                ask_count    = 1
                last_question = $item.last_question
            })
        }
    }

    foreach ($field in (To-JsonArray -Value $UpdateObject.resolved_conflict_fields)) {
        for ($i = $conflicts.Count - 1; $i -ge 0; $i--) {
            if ($conflicts[$i].field -eq $field) {
                $conflicts.RemoveAt($i)
            }
        }
    }

    $InputObject.client_profile.facts = @($facts)
    $InputObject.question_context.asked_questions = @($askedQuestions)
    $InputObject.question_context.answered_fields = @($answeredFields)
    $InputObject.conflicts = @($conflicts)
    return $InputObject
}

function Invoke-QuestioningFile {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $QuestioningScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "question_plan")
}

function Invoke-AnalysisFile {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $AnalysisScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "analysis_status")
}

function Invoke-EvalObject {
    param($AnalysisObject)
    $analysisPath = Save-TempJson -Object $AnalysisObject -Prefix "ra-dataset-analysis"
    return (Invoke-RaScriptToObject -ScriptPath $EvalScript -Arguments @{ AnalysisJsonPath = $analysisPath } -ExpectedTopLevelProperty "eval_status")
}

function Apply-UpdatesToInput {
    param(
        [string]$InputPath,
        $Updates
    )

    $currentPath = $InputPath
    foreach ($update in (To-JsonArray -Value $Updates)) {
        $inputObject = Read-JsonFile -Path $currentPath
        $merged = Merge-UpdatesIntoInputObject -InputObject $inputObject -UpdateObject $update
        $nextPath = Join-Path ([System.IO.Path]::GetTempPath()) ("ra-updated-input-{0}.json" -f ([guid]::NewGuid().ToString("N")))
        $merged | ConvertTo-Json -Depth 40 | Set-Content -Path $nextPath -Encoding UTF8
        $currentPath = $nextPath
    }

    return $currentPath
}

function Apply-Mutation {
    param(
        $AnalysisObject,
        $Mutation
    )

    $mutated = $AnalysisObject | ConvertTo-Json -Depth 80 | ConvertFrom-Json
    if ($null -eq $Mutation) {
        return $mutated
    }

    switch ([string]$Mutation.type) {
        "clear_evidence_refs_first_risk" {
            if (@($mutated.risk_map).Count -gt 0) {
                $mutated.risk_map[0].evidence_refs = @()
            }
        }
        "clear_fact_refs_first_evidence" {
            if (@($mutated.evidence).Count -gt 0) {
                $mutated.evidence[0].fact_refs = @()
            }
        }
        "clear_risk_map" {
            $mutated.risk_map = @()
        }
        "inject_product_summary" {
            if (@($mutated.requirements).Count -gt 0) {
                $mutated.requirements[0].summary = "Recommend buying a company product plan immediately."
            }
        }
    }

    return $mutated
}

function Has-ProductLeak {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    return ($Text -match "保险公司|产品推荐|购买|保单|product plan|buy|policy|insurance company")
}

function Test-ExpectedQuestions {
    param(
        $QuestionFields,
        $ExpectedQuestions
    )
    foreach ($field in (To-JsonArray -Value $ExpectedQuestions)) {
        if (-not (@($QuestionFields) -contains $field)) {
            return $false
        }
    }
    return $true
}

function Test-ExpectedRisks {
    param(
        $RequirementTypes,
        $ExpectedRisks
    )
    foreach ($risk in (To-JsonArray -Value $ExpectedRisks)) {
        if (-not (@($RequirementTypes) -contains $risk)) {
            return $false
        }
    }
    return $true
}

function Test-ExpectedPriority {
    param(
        $Requirements,
        $ExpectedPriority
    )

    foreach ($property in $ExpectedPriority.PSObject.Properties) {
        $matched = @($Requirements | Where-Object { $_.requirement_type -eq $property.Name })
        if ($matched.Count -eq 0) { return $false }
        if ([string]$matched[0].priority -ne [string]$property.Value) { return $false }
    }
    return $true
}

function Test-ExpectedEvidence {
    param(
        $EvidenceEntries,
        $ExpectedEvidence
    )

    $allRefs = New-Object System.Collections.ArrayList
    foreach ($entry in (To-JsonArray -Value $EvidenceEntries)) {
        foreach ($factRef in (To-JsonArray -Value $entry.fact_refs)) {
            if ($allRefs -notcontains $factRef) {
                [void]$allRefs.Add($factRef)
            }
        }
    }

    foreach ($field in (To-JsonArray -Value $ExpectedEvidence)) {
        if ($allRefs -notcontains $field) {
            return $false
        }
    }
    return $true
}

function Test-ForbiddenBehavior {
    param(
        $AnalysisObject,
        $EvalObject,
        $ForbiddenBehavior
    )

    foreach ($rule in (To-JsonArray -Value $ForbiddenBehavior)) {
        switch ([string]$rule) {
            "formal_analysis_when_insufficient" {
                if ((@($AnalysisObject.risk_map).Count -gt 0) -or (@($AnalysisObject.requirements).Count -gt 0)) {
                    return $false
                }
            }
            "product_recommendation" {
                if ($EvalObject.eval_status -eq "FAIL" -and @($EvalObject.issues | Where-Object { $_.type -eq "PRODUCT_RECOMMENDATION_LEAK" }).Count -gt 0) {
                    return $false
                }
                foreach ($req in (To-JsonArray -Value $AnalysisObject.requirements)) {
                    if (Has-ProductLeak -Text ([string]$req.summary)) { return $false }
                }
            }
        }
    }
    return $true
}

$dataset = Read-JsonFile -Path $DatasetPath
$caseResults = New-Object System.Collections.ArrayList
$evalTotals = [ordered]@{
    completeness = 0
    evidence_grounding = 0
    information_sufficiency = 0
    logical_consistency = 0
    product_boundary = 0
}
$totalCases = 0
$passedCases = 0

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Dataset Run" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

foreach ($case in (To-JsonArray -Value $dataset.cases)) {
    $totalCases++
    $inputPath = Save-TempJson -Object $case.input -Prefix ("ra-dataset-input-{0}" -f $case.case_id)

    $preUpdateQuestionPass = $true
    $preUpdateQuestionFields = @()
    if ((To-JsonArray -Value $case.pre_update_expected_questions).Count -gt 0) {
        $questioningResult = Invoke-QuestioningFile -InputPath $inputPath
        $preUpdateQuestionFields = @($questioningResult.question_plan.selected_questions | ForEach-Object { $_.field })
        $preUpdateQuestionPass = Test-ExpectedQuestions -QuestionFields $preUpdateQuestionFields -ExpectedQuestions $case.pre_update_expected_questions
    }

    $effectiveInputPath = $inputPath
    if ((To-JsonArray -Value $case.updates).Count -gt 0) {
        $effectiveInputPath = Apply-UpdatesToInput -InputPath $inputPath -Updates $case.updates
    }

    $analysis = Invoke-AnalysisFile -InputPath $effectiveInputPath
    $analysisForEval = Apply-Mutation -AnalysisObject $analysis -Mutation $case.mutation
    $eval = Invoke-EvalObject -AnalysisObject $analysisForEval

    $actualRequirementTypes = @($analysisForEval.requirements | ForEach-Object { $_.requirement_type })
    $actualIssueTypes = @($eval.issues | ForEach-Object { $_.type })
    $actualQuestionFields = @($analysis.question_plan.selected_questions | ForEach-Object { $_.field })

    $statusPass = ([string]$analysis.analysis_status -eq [string]$case.expected_status)
    $riskPass = Test-ExpectedRisks -RequirementTypes $actualRequirementTypes -ExpectedRisks $case.expected_risks
    $priorityPass = Test-ExpectedPriority -Requirements @($analysisForEval.requirements) -ExpectedPriority $case.expected_priority
    $questionPass = $true
    if ((To-JsonArray -Value $case.expected_questions).Count -gt 0) {
        $questionPass = Test-ExpectedQuestions -QuestionFields $actualQuestionFields -ExpectedQuestions $case.expected_questions
    }
    $evidencePass = $true
    if ((To-JsonArray -Value $case.expected_evidence).Count -gt 0) {
        $evidencePass = Test-ExpectedEvidence -EvidenceEntries @($analysisForEval.evidence) -ExpectedEvidence $case.expected_evidence
    }
    $evalStatusPass = ([string]$eval.eval_status -eq [string]$case.eval_requirements.expected_eval_status)

    $issuePass = $true
    foreach ($issueType in (To-JsonArray -Value $case.eval_requirements.expected_issue_types)) {
        if (-not (@($actualIssueTypes) -contains $issueType)) {
            $issuePass = $false
        }
    }

    $forbiddenPass = Test-ForbiddenBehavior -AnalysisObject $analysisForEval -EvalObject $eval -ForbiddenBehavior $case.forbidden_behavior

    $casePass = $preUpdateQuestionPass -and $statusPass -and $riskPass -and $priorityPass -and $questionPass -and $evidencePass -and $evalStatusPass -and $issuePass -and $forbiddenPass
    if ($casePass) { $passedCases++ }

    $evalTotals.completeness += [int]$eval.checks.completeness
    $evalTotals.evidence_grounding += [int]$eval.checks.evidence_grounding
    $evalTotals.information_sufficiency += [int]$eval.checks.information_sufficiency
    $evalTotals.logical_consistency += [int]$eval.checks.logical_consistency
    $evalTotals.product_boundary += [int]$eval.checks.requirement_product_separation

    [void]$caseResults.Add([pscustomobject]@{
        case_id = $case.case_id
        category = $case.category
        passed = $casePass
        expected_status = $case.expected_status
        actual_status = $analysis.analysis_status
        expected_eval_status = $case.eval_requirements.expected_eval_status
        actual_eval_status = $eval.eval_status
        expected_issue_types = @(To-JsonArray -Value $case.eval_requirements.expected_issue_types)
        actual_issue_types = @($actualIssueTypes)
        actual_risks = @($actualRequirementTypes)
        actual_question_fields = @($actualQuestionFields)
        pre_update_question_fields = @($preUpdateQuestionFields)
        eval_score = $eval.score
    })

    $marker = "[PASS]"
    $color = "Green"
    if (-not $casePass) {
        $marker = "[FAIL]"
        $color = "Red"
    }
    Write-Host "$marker $($case.case_id) category=$($case.category) status=$($analysis.analysis_status) eval=$($eval.eval_status) score=$($eval.score)" -ForegroundColor $color
}

$overallPassRate = 0
if ($totalCases -gt 0) {
    $overallPassRate = [math]::Round(($passedCases * 100.0 / $totalCases), 2)
}

$summary = [pscustomobject]@{
    total_cases = $totalCases
    passed_cases = $passedCases
    overall_pass_rate = $overallPassRate
    averages = [pscustomobject]@{
        completeness = [math]::Round(($evalTotals.completeness / $totalCases), 2)
        evidence_grounding = [math]::Round(($evalTotals.evidence_grounding / $totalCases), 2)
        information_sufficiency = [math]::Round(($evalTotals.information_sufficiency / $totalCases), 2)
        logical_consistency = [math]::Round(($evalTotals.logical_consistency / $totalCases), 2)
        product_boundary = [math]::Round(($evalTotals.product_boundary / $totalCases), 2)
    }
    case_results = @($caseResults)
}

Write-Host ""
Write-Host ("Overall Pass Rate: {0}%" -f $summary.overall_pass_rate) -ForegroundColor Cyan
Write-Host ("Completeness: {0}" -f $summary.averages.completeness) -ForegroundColor Cyan
Write-Host ("Evidence Grounding: {0}" -f $summary.averages.evidence_grounding) -ForegroundColor Cyan
Write-Host ("Information Sufficiency: {0}" -f $summary.averages.information_sufficiency) -ForegroundColor Cyan
Write-Host ("Logical Consistency: {0}" -f $summary.averages.logical_consistency) -ForegroundColor Cyan
Write-Host ("Product Boundary: {0}" -f $summary.averages.product_boundary) -ForegroundColor Cyan

$jsonOutput = $summary | ConvertTo-Json -Depth 60
if (-not [string]::IsNullOrWhiteSpace($OutputJsonPath)) {
    Set-Content -Path $OutputJsonPath -Value $jsonOutput -Encoding UTF8
}

if ($passedCases -ne $totalCases) {
    Write-Host ""
    Write-Host "Dataset run completed with failures." -ForegroundColor Yellow
    Write-Output $jsonOutput
    exit 1
}

Write-Host ""
Write-Host "Dataset run completed successfully." -ForegroundColor Green
Write-Output $jsonOutput
exit 0
