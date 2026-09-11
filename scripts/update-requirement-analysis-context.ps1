[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputJsonPath,
    [Parameter(Mandatory = $true)]
    [string]$UpdateJsonPath,
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

function ConvertTo-ArrayList {
    param($Value)
    $list = New-Object System.Collections.ArrayList
    foreach ($item in (To-JsonArray -Value $Value)) {
        [void]$list.Add($item)
    }
    return ,$list
}

$input = Read-JsonFile -Path $InputJsonPath
$update = Read-JsonFile -Path $UpdateJsonPath

$facts = ConvertTo-ArrayList -Value $input.client_profile.facts
$askedQuestions = ConvertTo-ArrayList -Value $input.question_context.asked_questions
$answeredFields = ConvertTo-ArrayList -Value $input.question_context.answered_fields
$conflicts = ConvertTo-ArrayList -Value $input.conflicts

foreach ($item in (To-JsonArray -Value $update.answered_facts)) {
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
            field = $item.field
            status = "answered"
            ask_count = [int]$existingAsked.ask_count
            last_question = $existingAsked.last_question
        }
    } else {
        [void]$askedQuestions.Add([pscustomobject]@{
            field = $item.field
            status = "answered"
            ask_count = 0
            last_question = ""
        })
    }
}

foreach ($item in (To-JsonArray -Value $update.asked_questions)) {
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
            field = $item.field
            status = $item.status
            ask_count = ([int]$previous.ask_count + 1)
            last_question = $item.last_question
        }
    } else {
        [void]$askedQuestions.Add([pscustomobject]@{
            field = $item.field
            status = $item.status
            ask_count = 1
            last_question = $item.last_question
        })
    }
}

foreach ($field in (To-JsonArray -Value $update.resolved_conflict_fields)) {
    for ($i = $conflicts.Count - 1; $i -ge 0; $i--) {
        if ($conflicts[$i].field -eq $field) {
            $conflicts.RemoveAt($i)
        }
    }
}

$input.client_profile.facts = @($facts)
$input.question_context.asked_questions = @($askedQuestions)
$input.question_context.answered_fields = @($answeredFields)
$input.conflicts = @($conflicts)

$jsonOutput = $input | ConvertTo-Json -Depth 20
$targetPath = $OutputJsonPath
if ([string]::IsNullOrWhiteSpace($targetPath)) {
    $targetPath = $InputJsonPath
}

Set-Content -Path $targetPath -Value $jsonOutput -Encoding UTF8
Write-Output $jsonOutput
