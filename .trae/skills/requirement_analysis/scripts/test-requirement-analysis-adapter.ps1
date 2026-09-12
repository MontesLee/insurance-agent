<#
.SYNOPSIS
  Adapter 单元测试：验证 adapter-from-client-profile.ps1 把 client-intake 画像转成合法、守纪律的 Input JSON。
.DESCRIPTION
  4 个 case：结构契约 + UNKNOWN 纪律、C009 三 PARTIAL Scope 复现 PRELIMINARY/Eval PASS、
  C009 全 Scope 诚实判 NEED_MORE 且真实缺口进 blocking_fields、C010 空模板不崩溃。
#>
[CmdletBinding()]
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$Root           = Split-Path -Parent $PSScriptRoot
$AdapterScript  = Join-Path $PSScriptRoot "adapter-from-client-profile.ps1"
$AnalysisScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-analysis.ps1"
$EvalScript     = Join-Path $PSScriptRoot "invoke-requirement-analysis-eval.ps1"
$CiExamples     = Join-Path (Join-Path (Split-Path -Parent $Root) "client-intake") "examples"
$C009Profile    = Join-Path (Join-Path $CiExamples "C009-张先生三口之家") "CLIENT_PROFILE.md"
$C010Profile    = Join-Path (Join-Path $CiExamples "C010-李女士单亲妈妈") "CLIENT_PROFILE.md"
$TmpDir         = Join-Path $Root "tmp"
if (-not (Test-Path -LiteralPath $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null }

$valueStatusEnum   = @('KNOWN', 'UNKNOWN', 'ESTIMATED', 'ASSUMED')
$scopeEnum         = @('medical', 'critical_illness', 'accident', 'life', 'savings')
$constraintTypeEnum = @('customer_preference', 'budget_signal', 'follow_up_item', 'data_quality_note')
$factKeys          = @('field', 'value', 'value_status', 'source_round', 'source_text', 'source_section')

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Get-PropNames { param($O); if ($null -eq $O) { return @() }; return @($O.PSObject.Properties.Name) }

function Test-InputConforms {
    param($Obj)
    $errs = @()
    $reqTop = @('source', 'analysis_scope', 'client_profile', 'conflicts', 'constraints', 'metadata', 'question_context')
    foreach ($k in $reqTop) { if ($null -eq $Obj.$k) { $errs += "missing top-level: $k" } }
    if ($null -ne $Obj.source) {
        if ($Obj.source.skill -ne 'client_intake') { $errs += "source.skill must be client_intake" }
        if ([string]::IsNullOrWhiteSpace([string]$Obj.source.adapter_version)) { $errs += "source.adapter_version empty" }
        if ([string]::IsNullOrWhiteSpace([string]$Obj.source.pending_path)) { $errs += "source.pending_path empty" }
        if ([string]::IsNullOrWhiteSpace([string]$Obj.source.conversation_log_path)) { $errs += "source.conversation_log_path empty" }
        if ($Obj.source.intake_complete -isnot [bool]) { $errs += "source.intake_complete not bool" }
    }
    foreach ($s in $Obj.analysis_scope) { if ($scopeEnum -notcontains $s) { $errs += "scope invalid: $s" } }
    $answered = @($Obj.question_context.answered_fields)
    foreach ($f in $Obj.client_profile.facts) {
        $names = Get-PropNames -O $f | Sort-Object
        $expected = $factKeys | Sort-Object
        if (($names -join ',') -ne ($expected -join ',')) { $errs += "fact keys mismatch: $($names -join ',')" }
        if ([string]::IsNullOrWhiteSpace([string]$f.field)) { $errs += "fact.field empty" }
        if ($valueStatusEnum -notcontains $f.value_status) { $errs += "fact.value_status invalid: $($f.value_status)" }
        if ([string]::IsNullOrWhiteSpace([string]$f.source_round)) { $errs += "fact.source_round empty ($($f.field))" }
        if ([string]::IsNullOrWhiteSpace([string]$f.source_text)) { $errs += "fact.source_text empty ($($f.field))" }
        if ([string]::IsNullOrWhiteSpace([string]$f.source_section)) { $errs += "fact.source_section empty ($($f.field))" }
        # 纪律：UNKNOWN 字段不得进入 answered_fields
        if ($f.value_status -eq 'UNKNOWN' -and ($answered -contains $f.field)) {
            $errs += "DISCIPLINE VIOLATION: UNKNOWN field '$($f.field)' present in answered_fields"
        }
    }
    foreach ($c in $Obj.constraints) {
        if ($constraintTypeEnum -notcontains $c.type) { $errs += "constraint.type invalid: $($c.type)" }
        if ([string]::IsNullOrWhiteSpace([string]$c.description)) { $errs += "constraint.description empty" }
        if ([string]::IsNullOrWhiteSpace([string]$c.source)) { $errs += "constraint.source empty" }
    }
    if ([string]::IsNullOrWhiteSpace([string]$Obj.metadata.client_id)) { $errs += "metadata.client_id empty" }
    if ([string]::IsNullOrWhiteSpace([string]$Obj.metadata.client_alias)) { $errs += "metadata.client_alias empty" }
    return $errs
}

function Invoke-Analysis {
    param([string]$InputPath)
    return (Invoke-RaScriptToObject -ScriptPath $AnalysisScript -Arguments @{ InputJsonPath = $InputPath } -ExpectedTopLevelProperty "analysis_status")
}

function Invoke-Eval {
    param([string]$AnalysisPath)
    return (Invoke-RaScriptToObject -ScriptPath $EvalScript -Arguments @{ AnalysisJsonPath = $AnalysisPath } -ExpectedTopLevelProperty "eval_status")
}

$failedCases = @()
$failureDetails = @()

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Adapter Test" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

# ---------- Case 1: C009 结构契约 + 纪律 + 规范字段 ----------
$cases = @(
    @{
        Name = "c009_structure_and_discipline"
        Validate = {
            $out = Join-Path $TmpDir "adapter_C009.input.json"
            & $AdapterScript -ProfilePath $C009Profile -OutputJsonPath $out -Scope life, critical_illness, accident | Out-Null
            Assert-True (Test-Path -LiteralPath $out) "adapter output not written"

            $obj = Get-Content -LiteralPath $out -Raw -Encoding UTF8 | ConvertFrom-Json
            $errs = Test-InputConforms -Obj $obj
            Assert-True ($errs.Count -eq 0) "input non-conform: $($errs -join '; ')"

            # 规范字段齐全
            $fields = @($obj.client_profile.facts | ForEach-Object { $_.field })
            foreach ($need in @('age', 'annual_income', 'family_responsibility', 'mortgage_balance', 'existing_critical_illness_coverage', 'existing_life_coverage', 'social_insurance_status')) {
                Assert-True ($fields -contains $need) "missing canonical field: $need"
            }
            # social_insurance_status 真实未知 → UNKNOWN
            $si = @($obj.client_profile.facts | Where-Object { $_.field -eq 'social_insurance_status' })[0]
            Assert-True ($si.value_status -eq 'UNKNOWN') "social_insurance_status should be UNKNOWN (honest)"
            # 派生 family_responsibility 存在
            Assert-True ($fields -contains 'family_responsibility') "family_responsibility derived fact missing"
        }
    },
    @{
        Name = "c009_e2e_preliminary_pass"
        Validate = {
            $out = Join-Path $TmpDir "adapter_C009.input.json"
            if (-not (Test-Path -LiteralPath $out)) { & $AdapterScript -ProfilePath $C009Profile -OutputJsonPath $out -Scope life, critical_illness, accident | Out-Null }
            $ana = Join-Path $TmpDir "adapter_C009.analysis.json"
            $result = Invoke-Analysis -InputPath $out
            Set-Content -LiteralPath $ana -Value ($result | ConvertTo-Json -Depth 20) -Encoding UTF8

            Assert-True ($result.analysis_status -eq 'PRELIMINARY' -or $result.analysis_status -eq 'COMPLETE') "C009(3 scopes) should be PRELIMINARY/COMPLETE, got $($result.analysis_status)"

            $eval = Invoke-Eval -AnalysisPath $ana
            Assert-True ($eval.eval_status -eq 'PASS') "eval should PASS for preliminary C009, got $($eval.eval_status)"
            Assert-True ($result.guardrails.product_recommendation_included -eq $false) "product_recommendation_included must be false"
        }
    },
    @{
        Name = "c009_honest_need_more"
        Validate = {
            $out = Join-Path $TmpDir "adapter_C009_all.input.json"
            & $AdapterScript -ProfilePath $C009Profile -OutputJsonPath $out | Out-Null
            $result = Invoke-Analysis -InputPath $out
            Assert-True ($result.analysis_status -eq 'NEED_MORE_INFORMATION') "C009(all scopes) should be NEED_MORE (social_insurance truly unknown), got $($result.analysis_status)"
            $blocking = @($result.information_sufficiency.blocking_fields)
            Assert-True ($blocking -contains 'social_insurance_status') "social_insurance_status must surface in blocking_fields, got: $($blocking -join ',')"
        }
    },
    @{
        Name = "c010_empty_template"
        Validate = {
            $out = Join-Path $TmpDir "adapter_C010.input.json"
            & $AdapterScript -ProfilePath $C010Profile -OutputJsonPath $out | Out-Null
            Assert-True (Test-Path -LiteralPath $out) "C010 adapter output not written"

            $obj = Get-Content -LiteralPath $out -Raw -Encoding UTF8 | ConvertFrom-Json
            $errs = Test-InputConforms -Obj $obj
            Assert-True ($errs.Count -eq 0) "C010 input non-conform: $($errs -join '; ')"

            $result = Invoke-Analysis -InputPath $out
            Assert-True ($result.analysis_status -eq 'NEED_MORE_INFORMATION') "C010(empty) should be NEED_MORE, got $($result.analysis_status)"
        }
    }
)

foreach ($case in $cases) {
    try {
        & $case.Validate
        Write-Host "[PASS] $($case.Name)" -ForegroundColor Green
    } catch {
        $failedCases += $case.Name
        $failureDetails += "$($case.Name): $($_.Exception.Message)"
        Write-Host "[FAIL] $($case.Name)" -ForegroundColor Red
        Write-Host "  - $($_.Exception.Message)" -ForegroundColor DarkRed
    }
}

Write-Host ""
if ($failedCases.Count -gt 0) {
    Write-Host "Adapter test failed: $($failedCases -join ', ')" -ForegroundColor Red
} else {
    Write-Host "All adapter tests passed." -ForegroundColor Green
}

# 落盘结构化结果（机器可读，CI 友好；不依赖 *  重定向）
$resultObj = [pscustomobject]@{
    passed      = ($failedCases.Count -eq 0)
    total       = $cases.Count
    failed      = $failedCases.Count
    failed_cases = $failedCases
    details     = $failureDetails
}
Set-Content -Path (Join-Path $TmpDir "adapter_test_result.json") -Value ($resultObj | ConvertTo-Json -Depth 5) -Encoding UTF8

if ($failedCases.Count -gt 0) { exit 1 } else { exit 0 }
