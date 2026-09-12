#requires -Version 5.1
<#
    test-risk-analysis-sufficiency.ps1
    -----------------------------------
    risk-analysis · Sufficiency 阶段单元测试

    覆盖 7 个 fixture（含 1 个对抗用例）+ 1 个规则外置负向用例。
    结果落盘 tmp/sufficiency_test_result.json（CI 友好），stdout 同时输出摘要。

    Lawgent 纪律：
      - 只有可机检断言才判 PASS
      - 负向用例必须证明"改规则 → 结论变"，证明规则真的外置而非硬编码
#>
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }

$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$fx        = Join-Path $skillRoot 'evals'
$fx        = Join-Path $fx 'fixtures'
$fx        = Join-Path $fx 'unit'
$fx        = Join-Path $fx 'sufficiency'
$tmp       = Join-Path $skillRoot 'tmp'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }
$engine    = Join-Path $skillRoot 'scripts'
$engine    = Join-Path $engine 'invoke-risk-analysis-sufficiency.ps1'

$results = [System.Collections.Generic.List[object]]::new()

# ------------------------------------------------------------------ assert helpers
function Assert-True {
    param([bool]$Cond, [string]$Message)
    if (-not $Cond) { throw $Message }
}
function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ([string]$Actual -ne [string]$Expected) {
        throw "$Message | expected=[$Expected] actual=[$Actual]"
    }
}
function Assert-Contains {
    param($Array, [string]$Item, [string]$Message)
    if (@($Array) -notcontains $Item) {
        throw "$Message | missing=[$Item] actual=[$(@($Array) -join ',')]"
    }
}
function Invoke-RaSufficiency {
    param([string]$Fixture, [string]$OutName, [string]$RulesPath = '')
    $inPath  = Join-Path $fx $Fixture
    $outPath = Join-Path $tmp $OutName
    if (Test-Path -LiteralPath $outPath) { [System.IO.File]::Delete($outPath) }
    if ([string]::IsNullOrWhiteSpace($RulesPath)) {
        & $engine -InputJsonPath $inPath -OutputJsonPath $outPath | Out-Null
    } else {
        & $engine -InputJsonPath $inPath -OutputJsonPath $outPath -RulesPath $RulesPath | Out-Null
    }
    if (-not (Test-Path -LiteralPath $outPath)) { throw "engine produced no output for $Fixture" }
    return (Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Assert-RaStageShape {
    param($Out, [int]$ExpectedDomains)
    Assert-Equal $Out.sufficiency.method 'risk_dependency_graph_v1' 'method 必须是 risk_dependency_graph_v1'
    Assert-True (@($Out.sufficiency.domain_results).Count -eq $ExpectedDomains) "domain_results 数量应为 $ExpectedDomains"
    foreach ($dr in $Out.sufficiency.domain_results) {
        Assert-True (@('R1', 'R2', 'R3', 'R4', 'R5') -contains $dr.risk_category) 'risk_category 枚举'
        Assert-True (@('SUFFICIENT', 'PARTIAL', 'INSUFFICIENT', 'CONFLICTING') -contains $dr.status) 'domain status 枚举'
        Assert-True ($dr.score -ge 0 -and $dr.score -le 1) 'domain score ∈ [0,1]'
    }
    Assert-True ($Out.guardrails.product_recommendation_included -eq $false) 'guardrails: 不得含产品推荐'
    Assert-True ($Out.guardrails.sales_language_detected -eq $false) 'guardrails: 不得含销售话术'
    Assert-True (@($Out.next_information_needed).Count -le 3) '每轮追问 ≤ 3'
    $eivs = @($Out.next_information_needed | ForEach-Object { $_.expected_information_value })
    for ($i = 1; $i -lt $eivs.Count; $i++) {
        Assert-True ($eivs[$i] -le $eivs[$i - 1]) 'next_information_needed 必须按 EIV 降序'
    }
    foreach ($q in $Out.next_information_needed) {
        Assert-True ($q.question_id -match '^Q[0-9]{3}$') 'question_id 必须匹配 ^Q\d{3}$'
        Assert-True (-not [string]::IsNullOrWhiteSpace($q.question)) 'question 不得为空'
        Assert-True (-not [string]::IsNullOrWhiteSpace($q.why_needed)) 'why_needed 不得为空（问题必须解释为什么问）'
        Assert-True (@($q.affects_risks).Count -ge 1) 'affects_risks 不得为空'
        Assert-True (@('HIGH', 'MEDIUM', 'LOW') -contains $q.priority) 'question priority 枚举'
        Assert-True ($q.expected_information_value -ge 0 -and $q.expected_information_value -le 1) 'EIV ∈ [0,1]'
    }
}

# ------------------------------------------------------------------ cases
$cases = [System.Collections.Generic.List[object]]::new()

$cases.Add(@{
    Name   = 'complete: 全字段齐备 → SUFFICIENT / FORMAL / 0 追问'
    Run    = {
        $o = Invoke-RaSufficiency -Fixture 'case-complete.json' -OutName 'suff_complete.json'
        Assert-RaStageShape $o 5
        Assert-Equal $o.sufficiency.sufficiency_status 'SUFFICIENT' 'sufficiency_status'
        Assert-Equal $o.analysis_status 'FORMAL' 'analysis_status'
        Assert-True (@($o.sufficiency.blocking_fields).Count -eq 0) 'blocking_fields 应为空'
        Assert-True (@($o.sufficiency.conflict_fields).Count -eq 0) 'conflict_fields 应为空'
        Assert-True (@($o.next_information_needed).Count -eq 0) '完整用例不应产生追问'
        Assert-True (@($o.unknowns).Count -eq 0) '完整用例不应有 UNKNOWN'
    }
})

$cases.Add(@{
    Name   = 'missing: 关键保障缺失 → INSUFFICIENT / NEED_MORE_INFORMATION / 高价值追问'
    Run    = {
        $o = Invoke-RaSufficiency -Fixture 'case-missing.json' -OutName 'suff_missing.json'
        Assert-RaStageShape $o 5
        Assert-Equal $o.sufficiency.sufficiency_status 'INSUFFICIENT' 'sufficiency_status'
        Assert-Equal $o.analysis_status 'NEED_MORE_INFORMATION' 'analysis_status'
        Assert-Contains $o.sufficiency.blocking_fields 'existing_life_coverage' '寿险保障缺失必须 blocking'
        Assert-Contains $o.sufficiency.blocking_fields 'social_insurance_status' '社保缺失必须 blocking'
        Assert-Contains $o.sufficiency.blocking_fields 'existing_medical_coverage' '商业医疗缺失必须 blocking'
        Assert-Contains ($o.unknowns | ForEach-Object { $_.field }) 'assets' 'assets 必须进 unknowns（不得推断）'
        Assert-Contains ($o.missing_from_upstream | ForEach-Object { $_.field }) 'assets' 'assets 必须登记 missing_from_upstream'
        Assert-True (@($o.next_information_needed).Count -eq 3) '缺失用例应产出 3 个高价值追问'
        # 跨域影响更广的字段必须排在前面（EIV 降序已由 shape 检查保证）
        $first = @($o.next_information_needed)[0]
        Assert-True (@($first.affects_risks).Count -ge 2) 'EIV 最高的问题应影响 ≥2 个风险域'
    }
})

$cases.Add(@{
    Name   = 'conflict: 取值冲突 → CONFLICTING / CONFLICTING_INFORMATION，禁止自行择一'
    Run    = {
        $o = Invoke-RaSufficiency -Fixture 'case-conflict.json' -OutName 'suff_conflict.json'
        Assert-RaStageShape $o 5
        Assert-Equal $o.sufficiency.sufficiency_status 'CONFLICTING' 'sufficiency_status'
        Assert-Equal $o.analysis_status 'CONFLICTING_INFORMATION' 'analysis_status'
        Assert-Contains $o.sufficiency.conflict_fields 'household_income' '冲突字段必须进入 conflict_fields'
        Assert-Contains ($o.unknowns | ForEach-Object { $_.field }) 'household_income' '冲突字段必须保持 UNKNOWN，不得择一'
        $q = @($o.next_information_needed | Where-Object { $_.question -match '家庭税后年收入' })[0]
        Assert-True ($null -ne $q) '冲突字段必须进入追问列表'
        Assert-True ($q.why_needed -match '冲突待澄清') '冲突问题的 why_needed 必须标注冲突待澄清'
    }
})

$cases.Add(@{
    Name   = 'partial: required 齐备但得分不足 → PARTIAL / PRELIMINARY（仍产出分析）'
    Run    = {
        $o = Invoke-RaSufficiency -Fixture 'case-partial.json' -OutName 'suff_partial.json'
        Assert-RaStageShape $o 1
        Assert-Equal $o.sufficiency.sufficiency_status 'PARTIAL' 'sufficiency_status'
        Assert-Equal $o.analysis_status 'PRELIMINARY' 'analysis_status'
        Assert-True (@($o.sufficiency.blocking_fields).Count -eq 0) 'required 齐备 → 无 blocking'
        Assert-True (@($o.sufficiency.domain_results)[0].score -lt 0.85) '域得分应 < 0.85'
        Assert-True (@($o.next_information_needed).Count -gt 0) 'PARTIAL 仍应给出补充信息建议'
    }
})

$cases.Add(@{
    Name   = 'no-ra: 上游 requirement-analysis 缺失 → 登记 MISSING_FROM_UPSTREAM 但不阻塞'
    Run    = {
        $o = Invoke-RaSufficiency -Fixture 'case-no-ra.json' -OutName 'suff_no_ra.json'
        Assert-RaStageShape $o 5
        Assert-Equal $o.analysis_status 'FORMAL' '事实层完整 → 上游需求缺失不阻塞'
        $src = @($o.missing_from_upstream | Where-Object { $_.source -eq 'requirement-analysis' } | ForEach-Object { $_.field })
        Assert-Contains $src 'requirements' '必须登记 MISSING_FROM_UPSTREAM: requirement-analysis'
        $asm = @($o.assumptions | ForEach-Object { $_.field })
        Assert-Contains $asm 'spouse_income' 'ESTIMATED 字段必须进入 assumptions'
        $si = @($o.assumptions | Where-Object { $_.field -eq 'spouse_income' })[0]
        Assert-True (-not [string]::IsNullOrWhiteSpace($si.reason)) 'ESTIMATED 必须写明估计依据'
    }
})

$cases.Add(@{
    Name   = 'adversarial: status=UNKNOWN 却带非空 value → 必须判为未满足'
    Run    = {
        $o = Invoke-RaSufficiency -Fixture 'case-unknown-with-value.json' -OutName 'suff_uwv.json'
        Assert-RaStageShape $o 1
        # 若引擎把 UNKNOWN（带值）当已满足，absorb_capacity 组会被判满足 → SUFFICIENT
        Assert-Equal $o.sufficiency.sufficiency_status 'INSUFFICIENT' 'UNKNOWN 带值也必须判未满足'
        Assert-Contains $o.sufficiency.blocking_fields 'assets' 'assets 必须进 blocking_fields'
    }
})

$cases.Add(@{
    Name   = 'required 缺失即 INSUFFICIENT，与总分无关（score 0.8649 ≥ 0.85 仍 INSUFFICIENT）'
    Run    = {
        $o = Invoke-RaSufficiency -Fixture 'case-required-missing.json' -OutName 'suff_reqmiss.json'
        Assert-RaStageShape $o 1
        $d = @($o.sufficiency.domain_results)[0]
        Assert-True ($d.score -ge 0.85) ('该用例域得分应 ≥0.85，实际 ' + $d.score)
        Assert-Equal $d.status 'INSUFFICIENT' 'required 缺失必须是 INSUFFICIENT'
        Assert-Equal $o.analysis_status 'NEED_MORE_INFORMATION' 'analysis_status'
    }
})

$cases.Add(@{
    Name   = 'negative: 篡改规则 status_satisfied 含 UNKNOWN → 结论必须改变（证明规则真外置）'
    Run    = {
        $rulesSrc = Join-Path $skillRoot 'resources'
        $rulesSrc = Join-Path $rulesSrc 'config'
        $rulesSrc = Join-Path $rulesSrc 'risk-sufficiency.rules.json'
        $corrupt = Join-Path $tmp 'corrupt-rules-include-unknown.json'
        $r = (Get-Content -LiteralPath $rulesSrc -Raw -Encoding UTF8) | ConvertFrom-Json
        $r.status_satisfied = @('KNOWN', 'ESTIMATED', 'ASSUMED', 'INFERRED', 'UNKNOWN')
        ($r | ConvertTo-Json -Depth 24) | Set-Content -LiteralPath $corrupt -Encoding UTF8
        try {
            $o = Invoke-RaSufficiency -Fixture 'case-unknown-with-value.json' -OutName 'suff_corrupt.json' -RulesPath $corrupt
            Assert-True ($o.sufficiency.sufficiency_status -ne 'INSUFFICIENT') '规则被篡改后结论必须改变（否则说明规则被硬编码）'
        } finally {
            if (Test-Path -LiteralPath $corrupt) { [System.IO.File]::Delete($corrupt) }
        }
    }
})

# ------------------------------------------------------------------ run
foreach ($c in $cases) {
    try {
        & $c.Run
        $results.Add([pscustomobject]@{ case = $c.Name; status = 'PASS'; detail = '' })
        Write-Output ('[PASS] ' + $c.Name)
    } catch {
        $results.Add([pscustomobject]@{ case = $c.Name; status = 'FAIL'; detail = $_.Exception.Message })
        Write-Output ('[FAIL] ' + $c.Name)
        Write-Output ('       ' + $_.Exception.Message)
    }
}

$passed = @($results | Where-Object { $_.status -eq 'PASS' }).Count
$failed = @($results | Where-Object { $_.status -eq 'FAIL' }).Count

$payload = [ordered]@{
    stage   = 'sufficiency'
    total   = $results.Count
    passed  = $passed
    failed  = $failed
    cases   = @($results)
}
$json = $payload | ConvertTo-Json -Depth 12
$resPath = Join-Path $tmp 'sufficiency_test_result.json'
[System.IO.File]::WriteAllText($resPath, $json, [System.Text.UTF8Encoding]::new($true))

Write-Output ''
Write-Output ('TOTAL=' + $results.Count + ' PASSED=' + $passed + ' FAILED=' + $failed)
Write-Output ('RESULT_FILE=' + $resPath)

if ($failed -gt 0) { exit 1 }
exit 0
