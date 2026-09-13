#requires -Version 5.1
<#
    run-risk-analysis-dataset.ps1
    -----------------------------
    risk-analysis · Phase 8 端到端数据集运行器（确定性，零 LLM）。

    每个用例跑完整链路：
        input → sufficiency → discovery → analysis → (mutation) → eval → repair

    用例与期望由 evals/cases/dataset-manifest.json 驱动（单一真源）。
    评分五维取自 EvalResult.checks（Eval 引擎是唯一裁判，不另起一套主观打分）：
        completeness / evidence_grounding / reasoning_consistency / unknown_integrity / product_boundary

    产物：
        tmp/dataset_result.json   （机读，CI 友好）
        tmp/dataset_report.md     （人读）
    退出码：任一用例不满足期望 → 1。
#>
param(
    [string]$ManifestPath = "",
    [string]$OutputJsonPath = "",
    [string]$ReportPath = "",
    [string]$DiscoveryRulesPath = "",
    [string]$ScoringRulesPath = "",
    [string]$AntiSalesRulesPath = ""
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------ 路径（Join-Path 仅接受 2 参数）
$skillRoot = Split-Path -Parent $PSScriptRoot
$tmp       = Join-Path $skillRoot 'tmp'
$casesDir  = Join-Path $skillRoot (Join-Path 'evals' 'cases')
$dsDir     = Join-Path $casesDir 'dataset'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }
if ([string]::IsNullOrWhiteSpace($ManifestPath))   { $ManifestPath   = Join-Path $casesDir 'dataset-manifest.json' }
if ([string]::IsNullOrWhiteSpace($OutputJsonPath)) { $OutputJsonPath = Join-Path $tmp 'dataset_result.json' }
if ([string]::IsNullOrWhiteSpace($ReportPath))     { $ReportPath     = Join-Path $tmp 'dataset_report.md' }

$suffEngine    = Join-Path $PSScriptRoot 'invoke-risk-analysis-sufficiency.ps1'
$discEngine    = Join-Path $PSScriptRoot 'invoke-risk-analysis-discovery.ps1'
$anaEngine     = Join-Path $PSScriptRoot 'invoke-risk-analysis-analysis.ps1'
$repairEngine  = Join-Path $PSScriptRoot 'invoke-risk-analysis-repair.ps1'
$antiSalesPath = Join-Path $skillRoot (Join-Path 'resources' (Join-Path 'config' 'anti-sales.rules.json'))

foreach ($f in @($ManifestPath, $suffEngine, $discEngine, $anaEngine, $repairEngine, $antiSalesPath)) {
    if (-not (Test-Path -LiteralPath $f)) { Write-Error "缺少依赖: $f"; exit 2 }
}

# ------------------------------------------------------------------ helpers
function Get-DsMember {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $null
    }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -ne $p) { return $p.Value }
    return $null
}
function Get-DsArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value)
}
function Read-DsJson {
    param([string]$Path)
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Write-DsJson {
    param($Object, [string]$Path)
    $json = $Object | ConvertTo-Json -Depth 40
    [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($false))
}
function Remove-DsFile {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) { [System.IO.File]::Delete($Path) }
}

$antiSalesSrc = if (-not [string]::IsNullOrWhiteSpace($AntiSalesRulesPath)) { $AntiSalesRulesPath } else { $antiSalesPath }
if (-not (Test-Path -LiteralPath $antiSalesSrc)) { Write-Error "缺少依赖: $antiSalesSrc"; exit 2 }
$antiSales = Read-DsJson -Path $antiSalesSrc
$productNames = Get-DsArray -Value (Get-DsMember -Object $antiSales -Name 'product_names')

# ------------------------------------------------------------------ 变异（只注入「引擎本不该产出」的错误）
function Apply-DsMutation {
    param($AnalysisObject, $Mutation)
    if ($null -eq $Mutation) { return $AnalysisObject }
    $rid = [string](Get-DsMember -Object $Mutation -Name 'risk_id')
    $type = [string](Get-DsMember -Object $Mutation -Name 'type')

    if ($type -eq 'drop_risk') {
        $kept = New-Object System.Collections.ArrayList
        foreach ($r in (Get-DsArray -Value $AnalysisObject.risks)) {
            if ([string]$r.risk_id -ne $rid) { [void]$kept.Add($r) }
        }
        $AnalysisObject.risks = @($kept)
        return $AnalysisObject
    }

    $target = $null
    foreach ($r in (Get-DsArray -Value $AnalysisObject.risks)) {
        if ([string]$r.risk_id -eq $rid) { $target = $r; break }
    }
    if ($null -eq $target) { throw "变异目标风险不存在: $rid" }

    switch ($type) {
        'bump_priority' {
            $target.priority = [string](Get-DsMember -Object $Mutation -Name 'priority')
        }
        'append_conclusion' {
            $target.conclusion = [string]$target.conclusion + [string](Get-DsMember -Object $Mutation -Name 'text')
        }
        'dangling_ref' {
            $refs = New-Object System.Collections.ArrayList
            foreach ($x in (Get-DsArray -Value $target.reasoning_evidence_refs)) { [void]$refs.Add($x) }
            [void]$refs.Add([string](Get-DsMember -Object $Mutation -Name 'ref'))
            $target.reasoning_evidence_refs = @($refs)
        }
        'unknown_as_known' {
            $target.status = 'KNOWN'
            foreach ($ev in (Get-DsArray -Value $target.evidence)) {
                $src = Get-DsMember -Object $ev -Name 'source'
                if ($null -ne $src) { $src.status = 'UNKNOWN' }
            }
        }
        default { throw "未知变异类型: $type" }
    }
    return $AnalysisObject
}

# ------------------------------------------------------------------ 禁止行为（Eval 之外的护栏）
function Test-DsProductLeak {
    param($AnalysisObject, $Overview)
    $texts = New-Object System.Collections.ArrayList
    if (-not [string]::IsNullOrWhiteSpace([string]$Overview)) { [void]$texts.Add([string]$Overview) }
    foreach ($r in (Get-DsArray -Value $AnalysisObject.risks)) {
        foreach ($k in @('conclusion', 'reasoning', 'existing_protection')) {
            $v = [string](Get-DsMember -Object $r -Name $k)
            if (-not [string]::IsNullOrWhiteSpace($v)) { [void]$texts.Add($v) }
        }
        $tr = Get-DsMember -Object $r -Name 'trigger'
        if ($tr) { $v = [string](Get-DsMember -Object $tr -Name 'event'); if ($v) { [void]$texts.Add($v) } }
        $ex = Get-DsMember -Object $r -Name 'exposure'
        if ($ex) { $v = [string](Get-DsMember -Object $ex -Name 'why_exposed'); if ($v) { [void]$texts.Add($v) } }
    }
    foreach ($t in $texts) {
        foreach ($pn in $productNames) {
            $name = [string](Get-DsMember -Object $pn -Name 'name')
            if ([string]::IsNullOrWhiteSpace($name)) { $name = [string]$pn }
            if ([string]::IsNullOrWhiteSpace($name)) { continue }
            if ($t.Contains($name)) { return $name }
        }
    }
    return $null
}

function Test-DsFabricatedCertainty {
    param($AnalysisObject)
    foreach ($r in (Get-DsArray -Value $AnalysisObject.risks)) {
        $ie = Get-DsMember -Object $r -Name 'impact_estimate'
        if ($null -eq $ie) { continue }
        $amt = [double](Get-DsMember -Object $ie -Name 'amount')
        if ($amt -le 0) { continue }
        $hasTraceable = $false
        foreach ($ev in (Get-DsArray -Value $r.evidence)) {
            $src = Get-DsMember -Object $ev -Name 'source'
            if ($null -eq $src) { continue }
            $st = [string](Get-DsMember -Object $src -Name 'status')
            $ly = [string](Get-DsMember -Object $src -Name 'layer')
            if ($st -ne 'UNVERIFIED' -and $st -ne 'UNKNOWN' -and $ly -ne 'unknown') { $hasTraceable = $true; break }
        }
        if (-not $hasTraceable) { return [string]$r.risk_id }
    }
    return $null
}

# ------------------------------------------------------------------ 主流程
$manifest = Read-DsJson -Path $ManifestPath
$cases    = Get-DsArray -Value (Get-DsMember -Object $manifest -Name 'cases')
if (@($cases).Count -eq 0) { Write-Error "用例清单为空: $ManifestPath"; exit 2 }

$dimTotals = [ordered]@{ completeness = 0.0; evidence_grounding = 0.0; reasoning_consistency = 0.0; unknown_integrity = 0.0; product_boundary = 0.0 }
$caseResults = New-Object System.Collections.ArrayList
$passedCases = 0

foreach ($c in $cases) {
    $cid  = [string](Get-DsMember -Object $c -Name 'case_id')
    $cat  = [string](Get-DsMember -Object $c -Name 'category')
    $exp  = Get-DsMember -Object $c -Name 'expect'
    $fail = New-Object System.Collections.ArrayList

    $inputName = [string](Get-DsMember -Object $c -Name 'input')
    if ([string]::IsNullOrWhiteSpace($inputName)) {
        $base = [string](Get-DsMember -Object $c -Name 'base_case')
        $inputName = $base + '.input.json'
    }
    $inPath = Join-Path $dsDir $inputName
    if (-not (Test-Path -LiteralPath $inPath)) {
        [void]$fail.Add("输入文件不存在: $inputName")
        [void]$caseResults.Add([pscustomobject][ordered]@{ case_id = $cid; category = $cat; passed = $false; failures = @($fail) })
        continue
    }

    $sPath = Join-Path $tmp ("ds_" + $cid + "_s.json")
    $dPath = Join-Path $tmp ("ds_" + $cid + "_d.json")
    $aPath = Join-Path $tmp ("ds_" + $cid + "_a.json")
    $mPath = Join-Path $tmp ("ds_" + $cid + "_am.json")
    $ePath = Join-Path $tmp ("ds_" + $cid + "_e.json")
    $rPath = Join-Path $tmp ("ds_" + $cid + "_ar.json")
    foreach ($p in @($sPath, $dPath, $aPath, $mPath, $ePath, $rPath)) { Remove-DsFile -Path $p }

    # --- 链路（规则路径可选覆盖：默认走 resources/config，负向测试可注入篡改后的副本）
    $p1 = @{ InputJsonPath = $inPath; OutputJsonPath = $sPath }
    & $suffEngine @p1 | Out-Null
    $p2 = @{ InputJsonPath = $inPath; OutputJsonPath = $dPath; SufficiencyJsonPath = $sPath }
    if (-not [string]::IsNullOrWhiteSpace($DiscoveryRulesPath)) { $p2.RulesPath = $DiscoveryRulesPath }
    & $discEngine @p2 | Out-Null
    $p3 = @{ InputJsonPath = $inPath; OutputJsonPath = $aPath; DiscoveryJsonPath = $dPath; SufficiencyJsonPath = $sPath }
    if (-not [string]::IsNullOrWhiteSpace($ScoringRulesPath)) { $p3.RulesPath = $ScoringRulesPath }
    & $anaEngine @p3 | Out-Null

    $anaForEvalPath = $aPath
    $mut = Get-DsMember -Object $c -Name 'mutation'
    if ($null -ne $mut) {
        $obj = Read-DsJson -Path $aPath
        $obj = Apply-DsMutation -AnalysisObject $obj -Mutation $mut
        Write-DsJson -Object $obj -Path $mPath
        $anaForEvalPath = $mPath
    }

    $p4 = @{ AnalysisJsonPath = $anaForEvalPath; DiscoveryJsonPath = $dPath; EvalOutputJsonPath = $ePath; RepairedOutputJsonPath = $rPath }
    if (-not [string]::IsNullOrWhiteSpace($ScoringRulesPath))   { $p4.ScoringRulesPath = $ScoringRulesPath }
    if (-not [string]::IsNullOrWhiteSpace($AntiSalesRulesPath)) { $p4.AntiSalesRulesPath = $AntiSalesRulesPath }
    & $repairEngine @p4 | Out-Null

    $suf = Read-DsJson -Path $sPath
    $dis = Read-DsJson -Path $dPath
    $ana = Read-DsJson -Path $aPath
    $evl = Read-DsJson -Path $ePath

    $actualStatus   = [string](Get-DsMember -Object $ana -Name 'analysis_status')
    $actualRiskList = Get-DsArray -Value (Get-DsMember -Object $ana -Name 'risks')

    # --- 期望断言
    $wantStatus = [string](Get-DsMember -Object $exp -Name 'analysis_status')
    if (-not [string]::IsNullOrWhiteSpace($wantStatus) -and $actualStatus -ne $wantStatus) {
        [void]$fail.Add("analysis_status 期望 $wantStatus，实际 $actualStatus")
    }

    $wantCount = Get-DsMember -Object $exp -Name 'risk_count'
    if ($null -ne $wantCount -and @($actualRiskList).Count -ne [int]$wantCount) {
        [void]$fail.Add("risk_count 期望 $wantCount，实际 $(@($actualRiskList).Count)")
    }

    $wantDisc = Get-DsMember -Object $exp -Name 'discovery'
    if ($null -ne $wantDisc) {
        foreach ($prop in $wantDisc.PSObject.Properties) {
            $got = $null
            foreach ($cand in (Get-DsArray -Value (Get-DsMember -Object $dis -Name 'risk_candidates'))) {
                if ([string](Get-DsMember -Object $cand -Name 'risk_category') -eq $prop.Name) { $got = [string](Get-DsMember -Object $cand -Name 'discovery_status'); break }
            }
            if ($got -ne [string]$prop.Value) { [void]$fail.Add(($prop.Name) + " discovery_status 期望 " + $prop.Value + "，实际 " + $got) }
        }
    }

    $wantExists = Get-DsMember -Object $exp -Name 'risk_exists'
    if ($null -ne $wantExists) {
        foreach ($prop in $wantExists.PSObject.Properties) {
            $got = $null
            foreach ($r in $actualRiskList) {
                if ([string](Get-DsMember -Object $r -Name 'risk_category') -eq $prop.Name) { $got = [bool](Get-DsMember -Object $r -Name 'risk_exists'); break }
            }
            if ($got -ne [bool]$prop.Value) { [void]$fail.Add(($prop.Name) + " risk_exists 期望 " + $prop.Value + "，实际 " + $got) }
        }
    }

    $wantPrio = Get-DsMember -Object $exp -Name 'priority'
    if ($null -ne $wantPrio) {
        foreach ($prop in $wantPrio.PSObject.Properties) {
            $got = $null
            foreach ($r in $actualRiskList) {
                if ([string](Get-DsMember -Object $r -Name 'risk_category') -eq $prop.Name) { $got = [string](Get-DsMember -Object $r -Name 'priority'); break }
            }
            if ($got -ne [string]$prop.Value) { [void]$fail.Add(($prop.Name) + " priority 期望 " + $prop.Value + "，实际 " + $got) }
        }
    }

    $wantEval = [string](Get-DsMember -Object $exp -Name 'eval_status')
    $actualEval = [string](Get-DsMember -Object $evl -Name 'eval_status')
    if (-not [string]::IsNullOrWhiteSpace($wantEval) -and $actualEval -ne $wantEval) {
        [void]$fail.Add("eval_status 期望 $wantEval，实际 $actualEval")
    }

    $wantAttempts = Get-DsMember -Object $exp -Name 'repair_attempts'
    $actualAttempts = [int](Get-DsMember -Object $evl -Name 'repair_attempts')
    if ($null -ne $wantAttempts -and $actualAttempts -ne [int]$wantAttempts) {
        [void]$fail.Add("repair_attempts 期望 $wantAttempts，实际 $actualAttempts")
    }

    $wantCodes = Get-DsArray -Value (Get-DsMember -Object $exp -Name 'first_failed_codes')
    if (@($wantCodes).Count -gt 0) {
        # 首轮失败码：有 repair_log 取 log[0]；attempts=0 的类（不可自动修复）没有 log，
        # 取 EvalResult.failures（契约规定只含 BLOCKING）——那里就是首轮也是唯一的判定结果。
        $log = Get-DsArray -Value (Get-DsMember -Object $evl -Name 'repair_log')
        $gotCodes = @()
        if (@($log).Count -ge 1) {
            $gotCodes = @((Get-DsArray -Value (Get-DsMember -Object $log[0] -Name 'failed_codes')) | ForEach-Object { [string]$_ })
        } else {
            $gotCodes = @((Get-DsArray -Value (Get-DsMember -Object $evl -Name 'failures')) | ForEach-Object { [string](Get-DsMember -Object $_ -Name 'code') })
        }
        foreach ($w in $wantCodes) {
            if (-not ($gotCodes -contains [string]$w)) { [void]$fail.Add("首轮失败码应含 $w，实际 " + ($gotCodes -join ',')) }
        }
    }

    $wantMfu = Get-DsArray -Value (Get-DsMember -Object $exp -Name 'missing_from_upstream_contains')
    if (@($wantMfu).Count -gt 0) {
        $gotMfu = @((Get-DsArray -Value (Get-DsMember -Object $suf -Name 'missing_from_upstream')) | ForEach-Object { [string](Get-DsMember -Object $_ -Name 'field') })
        foreach ($w in $wantMfu) {
            if (-not ($gotMfu -contains [string]$w)) { [void]$fail.Add("missing_from_upstream 应含 $w，实际 " + ($gotMfu -join ',')) }
        }
    }

    # --- 禁止行为
    $forbidden = Get-DsArray -Value (Get-DsMember -Object $c -Name 'forbidden')
    foreach ($f in $forbidden) {
        switch ([string]$f) {
            'product_leak' {
                $hit = Test-DsProductLeak -AnalysisObject $ana -Overview ([string](Get-DsMember -Object $ana -Name 'family_risk_overview'))
                if ($hit) { [void]$fail.Add("产品名泄漏: $hit") }
            }
            'fabricated_certainty' {
                $hit = Test-DsFabricatedCertainty -AnalysisObject $ana
                if ($hit) { [void]$fail.Add("无溯源证据却给出金额: $hit") }
            }
        }
    }

    # --- 五维评分（取自 Eval 引擎，不另起主观打分）
    $checks = Get-DsMember -Object $evl -Name 'checks'
    function Get-DsScore { param($Key)
        $ck = Get-DsMember -Object $checks -Name $Key
        if ($null -eq $ck) { return 0.0 }
        return [double](Get-DsMember -Object $ck -Name 'score')
    }
    $dim = [ordered]@{
        completeness         = [math]::Round((Get-DsScore 'completeness') * 100, 2)
        evidence_grounding   = [math]::Round((Get-DsScore 'evidence_grounding') * 100, 2)
        reasoning_consistency = [math]::Round((((Get-DsScore 'reasoning_consistency') + (Get-DsScore 'priority_consistency')) / 2.0) * 100, 2)
        unknown_integrity    = [math]::Round((Get-DsScore 'unknown_integrity') * 100, 2)
        product_boundary     = [math]::Round(([math]::Min((Get-DsScore 'separation'), (Get-DsScore 'anti_sales'))) * 100, 2)
    }
    $overall = [math]::Round((($dim.completeness + $dim.evidence_grounding + $dim.reasoning_consistency + $dim.unknown_integrity + $dim.product_boundary) / 5.0), 2)

    $passed = (@($fail).Count -eq 0)
    if ($passed) { $passedCases++ }
    foreach ($k in @($dimTotals.Keys)) { $dimTotals[$k] = $dimTotals[$k] + [double]$dim[$k] }

    [void]$caseResults.Add([pscustomobject][ordered]@{
        case_id = $cid
        category = $cat
        archetype = [string](Get-DsMember -Object $c -Name 'archetype')
        passed = $passed
        analysis_status = $actualStatus
        eval_status = $actualEval
        repair_attempts = $actualAttempts
        risk_count = @($actualRiskList).Count
        dimensions = [pscustomobject]$dim
        overall = $overall
        failures = @($fail)
    })
}

# ------------------------------------------------------------------ 汇总
$total = @($caseResults).Count
$avg = [ordered]@{}
foreach ($k in @($dimTotals.Keys)) { $avg[$k] = [math]::Round(($dimTotals[$k] / $total), 2) }
$avgOverall = [math]::Round((($avg.completeness + $avg.evidence_grounding + $avg.reasoning_consistency + $avg.unknown_integrity + $avg.product_boundary) / 5.0), 2)

$summary = [pscustomobject][ordered]@{
    manifest = $ManifestPath
    total_cases = $total
    passed_cases = $passedCases
    failed_cases = ($total - $passedCases)
    pass_rate = [math]::Round(($passedCases * 100.0 / $total), 2)
    averages = [pscustomobject]$avg
    overall = $avgOverall
    cases = @($caseResults)
}
Write-DsJson -Object $summary -Path $OutputJsonPath

# ------------------------------------------------------------------ 报告
$rep = New-Object System.Collections.ArrayList
[void]$rep.Add('# risk-analysis · Phase 8 Dataset 运行报告')
[void]$rep.Add('')
[void]$rep.Add('- 用例清单（单一真源）：`evals/cases/dataset-manifest.json`')
[void]$rep.Add('- 链路：`sufficiency → discovery → analysis → (mutation) → eval → repair`')
[void]$rep.Add('- 机读结果：`tmp/dataset_result.json`')
[void]$rep.Add('')
[void]$rep.Add(('通过率：**{0}/{1}（{2}%）**　综合均分：**{3}**' -f $passedCases, $total, $summary.pass_rate, $avgOverall))
[void]$rep.Add('')
[void]$rep.Add('| 维度 | 均分 |')
[void]$rep.Add('|---|---|')
foreach ($k in @($avg.Keys)) { [void]$rep.Add(('| {0} | {1} |' -f $k, $avg[$k])) }
[void]$rep.Add('')
[void]$rep.Add('| 用例 | 类别 | analysis_status | eval | repair | risks | 综合 | 结果 |')
[void]$rep.Add('|---|---|---|---|---|---|---|---|')
foreach ($cr in $caseResults) {
    $mark = if ($cr.passed) { 'PASS' } else { 'FAIL' }
    [void]$rep.Add(('| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |' -f $cr.case_id, $cr.category, $cr.analysis_status, $cr.eval_status, $cr.repair_attempts, $cr.risk_count, $cr.overall, $mark))
}
[void]$rep.Add('')
$badCases = @($caseResults | Where-Object { -not $_.passed })
if (@($badCases).Count -gt 0) {
    [void]$rep.Add('## 未通过明细')
    [void]$rep.Add('')
    foreach ($b in $badCases) {
        [void]$rep.Add(('### ' + $b.case_id))
        foreach ($f in @($b.failures)) { [void]$rep.Add(('- ' + $f)) }
        [void]$rep.Add('')
    }
} else {
    [void]$rep.Add('## 未通过明细')
    [void]$rep.Add('')
    [void]$rep.Add('无。全部用例满足清单中的期望与禁止行为约束。')
}
[System.IO.File]::WriteAllLines($ReportPath, $rep, [System.Text.UTF8Encoding]::new($false))

Write-Output ("DATASET SUMMARY: total=" + $total + " passed=" + $passedCases + " failed=" + ($total - $passedCases) + " overall=" + $avgOverall)
if ($passedCases -ne $total) { exit 1 }
exit 0
