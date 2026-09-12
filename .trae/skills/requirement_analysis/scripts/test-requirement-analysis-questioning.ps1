[CmdletBinding()]
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$Root = Split-Path -Parent $PSScriptRoot
$TestDir = Join-Path $Root "evals\fixtures\unit\questioning"
$QuestionScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-questioning.ps1"
$UpdateScript = Join-Path $PSScriptRoot "update-requirement-analysis-context.ps1"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-Questioning {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $QuestionScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "question_plan")
}

function Get-Fields {
    param($QuestionEntries)
    return @($QuestionEntries | ForEach-Object { $_.field })
}

$failedCases = @()

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Questioning Test" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

$cases = @(
    @{
        Name = "priority_selection"
        Validate = {
            $path = Join-Path $TestDir "priority_selection.input.json"
            $result = Invoke-Questioning -InputPath $path
            $fields = Get-Fields -QuestionEntries $result.question_plan.selected_questions

            Assert-True ($result.question_plan.question_status -eq "READY_TO_ASK") "priority_selection should be READY_TO_ASK"
            Assert-True ($fields[0] -eq "social_insurance_status") "priority_selection should ask social_insurance_status first"
            Assert-True ($fields -contains "budget") "priority_selection should include budget"
            Assert-True (-not ($fields -contains "city")) "priority_selection should not prioritize city into selected questions"
        }
    },
    @{
        Name = "no_repeat_after_answer"
        Validate = {
            $path = Join-Path $TestDir "no_repeat_after_answer.input.json"
            $result = Invoke-Questioning -InputPath $path
            $fields = Get-Fields -QuestionEntries $result.question_plan.selected_questions

            Assert-True (-not ($fields -contains "existing_life_coverage")) "no_repeat_after_answer should not ask existing_life_coverage again"
            Assert-True ($fields -contains "mortgage_years") "no_repeat_after_answer should move to the remaining gap"
        }
    },
    @{
        Name = "multi_turn_collection"
        Validate = {
            $path = Join-Path $TestDir "multi_turn.input.json"
            $round1 = Invoke-Questioning -InputPath $path
            $round1Fields = Get-Fields -QuestionEntries $round1.question_plan.selected_questions

            Assert-True ($round1Fields -contains "financial_goals") "multi_turn_collection round1 should include financial_goals"
            Assert-True ($round1Fields -contains "assets") "multi_turn_collection round1 should include assets"

            $tempUpdate = Join-Path ([System.IO.Path]::GetTempPath()) "requirement-analysis-phase3-update.json"
            $updatePayload = [pscustomobject]@{
                answered_facts = @(
                    [pscustomobject]@{
                        field = "financial_goals"
                        value = "education_and_retirement"
                        value_status = "KNOWN"
                        source_round = "R2"
                        source_text = "primary goal is education and retirement"
                        source_section = "Requirement Analysis Follow-up"
                    },
                    [pscustomobject]@{
                        field = "assets"
                        value = "800k savings"
                        value_status = "KNOWN"
                        source_round = "R2"
                        source_text = "around 800k savings"
                        source_section = "Requirement Analysis Follow-up"
                    }
                )
                asked_questions = @(
                    [pscustomobject]@{
                        field = "financial_goals"
                        status = "answered"
                        last_question = "What is the primary savings goal?"
                    },
                    [pscustomobject]@{
                        field = "assets"
                        status = "answered"
                        last_question = "How much liquid assets do you have?"
                    }
                )
                resolved_conflict_fields = @()
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $tempUpdate -Value $updatePayload -Encoding UTF8

            $updatedInput = Join-Path ([System.IO.Path]::GetTempPath()) "requirement-analysis-phase3-updated-input.json"
            Invoke-RaScriptToFile -ScriptPath $UpdateScript -Arguments @{
                InputJsonPath  = $path
                UpdateJsonPath = $tempUpdate
                OutputJsonPath = $updatedInput
            } -OutputJsonPath $updatedInput -ValidateMinSize -MinSizeBytes 1000

            $round2 = Invoke-Questioning -InputPath $updatedInput
            $round2Fields = Get-Fields -QuestionEntries $round2.question_plan.selected_questions

            Assert-True (-not ($round2Fields -contains "financial_goals")) "multi_turn_collection round2 should not repeat financial_goals"
            Assert-True (-not ($round2Fields -contains "assets")) "multi_turn_collection round2 should not repeat assets"
            Assert-True ($round2Fields -contains "budget") "multi_turn_collection round2 should move to budget"
        }
    },
    @{
        Name = "conflict_confirmation"
        Validate = {
            $path = Join-Path $TestDir "conflict_confirmation.input.json"
            $result = Invoke-Questioning -InputPath $path
            $first = $result.question_plan.selected_questions[0]

            Assert-True ($result.question_plan.question_status -eq "CONFLICT_CONFIRMATION_REQUIRED") "conflict_confirmation should require confirmation"
            Assert-True ($first.field -eq "annual_income") "conflict_confirmation should prioritize annual_income conflict"
            Assert-True ($first.question_type -eq "conflict_confirmation") "conflict_confirmation should generate conflict confirmation question"
        }
    },
    @{
        Name = "duplicate_field_no_duplicate_question"
        Validate = {
            # F5 regression: information_gaps may contain the same field multiple
            # times (one per scope). The questioning phase must de-duplicate by
            # field so no field is asked twice, and a field whose rule only had a
            # conflict_template (e.g. annual_income) must still get a non-empty
            # gap_fill question from question_templates.
            $path = Join-Path $TestDir "duplicate_annual_income.input.json"
            $result = Invoke-Questioning -InputPath $path
            $aiEntries = @($result.question_plan.selected_questions | Where-Object { $_.field -eq "annual_income" })

            Assert-True ($aiEntries.Count -le 1) "duplicate_field: annual_income must appear at most once in selected questions (was $($aiEntries.Count))"
            if ($aiEntries.Count -eq 1) {
                Assert-True (-not [string]::IsNullOrWhiteSpace($aiEntries[0].question)) "duplicate_field: annual_income question text must not be empty"
            }

            $emptyCount = @($result.question_plan.selected_questions | Where-Object { [string]::IsNullOrWhiteSpace($_.question) }).Count
            Assert-True ($emptyCount -eq 0) "duplicate_field: no selected question should have empty text (was $emptyCount)"
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
    Write-Host "Questioning test failed: $($failedCases -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "All questioning tests passed." -ForegroundColor Green
exit 0
