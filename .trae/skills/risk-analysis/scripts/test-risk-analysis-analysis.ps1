#requires -Version 5.1
<#
    test-risk-analysis-analysis.ps1
    -------------------------------
    risk-analysis · Analysis（风险量化）阶段单元测试

    覆盖：10 个用例（含对抗用例 + 规则外置负向用例 + 与充分性阶段集成用例）。
    每个用例先跑 discovery 引擎得到候选，再跑 analysis 引擎得到量化结果，最后断言。
    结果落盘 tmp/analysis_test_result.json（CI 友好），stdout 同时输出摘要。

    Lawgent 纪律：
      - 只有可机检断言才判 PASS
      - 负向用例必须证明"改规则 → 结论变"，证明规则真的外置而非硬编码
#>
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }

$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$fx     = Join-Path $skillRoot 'evals'; $fx = Join-Path $fx 'fixtures'; $fx = Join-Path $fx 'unit'
$fxDisc = Join-Path $fx 'discovery'
$tmp    = Join-Path $skillRoot 'tmp'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }

$discEngine = Join-Path $skillRoot 'scripts'; $discEngine = Join-Path $discEngine 'invoke-risk-analysis-discovery.ps1'
$anaEngine  = Join-Path $skillRoot 'scripts'; $anaEngine  = Join-Path $anaEngine 'invoke-risk-analysis-analysis.ps1'
$discRules  = Join-Path $skillRoot 'resources'; $discRules = Join-Path $discRules 'config'; $discRules = Join-Path $discRules 'risk-discovery.rules.json'
$scorRules  = Join-Path $skillRoot 'resources'; $scorRules = Join-Path $scorRules 'config'; $scorRules = Join-Path $scorRules 'risk-scoring.rules.json'

$results = [System.Collections.Generic.List[object]]::new()

# ------------------------------------------------------------------ assert helpers
function Assert-True {
    param([bool]$Cond, [string]$Message)
    if (-not $Cond) { throw $Message }
}
function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ([string]$Actual -ne [string]$Expected) { throw "$Message | expected=[$Expected] actual=[$Actual]" }
}
function Assert-Contains {
    param($Array, [string]$Item, [string]$Message)
    if (@($Array) -notcontains $Item) { throw "$Message | missing=[$Item] actual=[$(@($Array) -join ',')]" }
}
function Get-RaRisk {
    param($Out, [string]$Domain)
    $r = @($Out.risks | Where-Object { $_.risk_category -eq $Domain })[0]
    if ($null -eq $r) { throw "risk not found in risks[]: $Domain (risks=$(@($Out.risks.risk_category) -join ','))" }
    return $r
}
function Invoke-RaDiscovery {
    param([string]$Fixture, [string]$OutName, [string]$Rules = '')
    $inPath  = Join-Path $fxDisc $Fixture
    $outPath = Join-Path $tmp $OutName
    if (Test-Path -LiteralPath $outPath) { [System.IO.File]::Delete($outPath) }
    $params = @{ InputJsonPath = $inPath; OutputJsonPath = $outPath }
    if (-not [string]::IsNullOrWhiteSpace($Rules)) { $params.RulesPath = $Rules }
    & $discEngine @params | Out-Null
    if (-not (Test-Path -LiteralPath $outPath)) { throw "discovery produced no output for $Fixture" }
    return (Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Invoke-RaAnalysis {
    param([string]$Fixture, [string]$DiscOut, [string]$OutName, [string]$Rules = '', [string]$SuffJson = '')
    $inPath  = Join-Path $fxDisc $Fixture
    $discPath = Join-Path $tmp $DiscOut
    $outPath = Join-Path $tmp $OutName
    if (Test-Path -LiteralPath $outPath) { [System.IO.File]::Delete($outPath) }
    $params = @{ InputJsonPath = $inPath; OutputJsonPath = $outPath; DiscoveryJsonPath = $discPath }
    if (-not [string]::IsNullOrWhiteSpace($Rules)) { $params.RulesPath = $Rules }
    if (-not [string]::IsNullOrWhiteSpace($SuffJson)) { $params.SufficiencyJsonPath = $SuffJson }
    & $anaEngine @params | Out-Null
    if (-not (Test-Path -LiteralPath $outPath)) { throw "analysis produced no output for $DiscOut" }
    return (Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Run-Case {
    param([string]$Name, [scriptblock]$Body)
    try {
        & $Body
        $results.Add([pscustomobject][ordered]@{ name = $Name; status = 'PASS' })
        Write-Output ("[PASS] " + $Name)
    } catch {
        $results.Add([pscustomobject][ordered]@{ name = $Name; status = 'FAIL'; error = $_.Exception.Message })
        Write-Output ("[FAIL] " + $Name + " :: " + $_.Exception.Message)
    }
}

# ------------------------------------------------------------------ 用例 1：双职工有房贷 + 子女
Run-Case 'dual-income: 5 risks + R2 HIGH/P2 + R4 CRITICAL/P2 + R5 P3' {
    $d = Invoke-RaDiscovery -Fixture 'case-dual-income-family.json' -OutName 'ana_dual_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-dual-income-family.json' -DiscOut 'ana_dual_disc.json' -OutName 'ana_dual.json'
    Assert-Equal $o.stage 'analysis' 'stage 必须是 analysis'
    Assert-Equal (@($o.risks).Count) 5 'dual-income 应有 5 个风险对象（含 NOT_IDENTIFIED）'
    $r2 = Get-RaRisk $o 'R2'
    Assert-True ($r2.risk_exists -eq $true) 'R2 应成立'
    Assert-Equal $r2.severity 'HIGH' 'R2 severity=HIGH'
    Assert-Equal $r2.likelihood 'MEDIUM' 'R2 likelihood=MEDIUM'
    Assert-Equal $r2.residual_risk 'HIGH' 'R2 residual=HIGH'
    Assert-Equal $r2.priority 'P2' 'R2 severity=HIGH 且 likelihood=MEDIUM → 按矩阵 P2'
    Assert-True ([double]$r2.impact_estimate.amount -eq 2100000) ('R2 影响额应=2,100,000，实际=' + $r2.impact_estimate.amount)
    $r4 = Get-RaRisk $o 'R4'
    Assert-Equal $r4.severity 'CRITICAL' 'R4 severity=CRITICAL'
    Assert-Equal $r4.priority 'P2' 'R4 有房贷≠P0，应为 P2'
    $r5 = Get-RaRisk $o 'R5'
    Assert-Equal $r5.priority 'P3' 'R5 应被 R5_always_low 封顶 P3'
    Assert-True ($o.guardrails.product_recommendation_included -eq $false) 'guardrails 不得含产品推荐'
}

# ------------------------------------------------------------------ 用例 2：单身无子女无负债
Run-Case 'single-no-dependents: R4 NOT_IDENTIFIED + 5 risks + R2 amount 1,200,000' {
    $d = Invoke-RaDiscovery -Fixture 'case-single-no-dependents.json' -OutName 'ana_single_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-single-no-dependents.json' -DiscOut 'ana_single_disc.json' -OutName 'ana_single.json'
    Assert-Equal (@($o.risks).Count) 5 'single 应有 5 个风险对象'
    $r4 = Get-RaRisk $o 'R4'
    Assert-True ($r4.risk_exists -eq $false) 'R4 应不成立'
    Assert-Equal $r4.severity 'LOW' 'R4 severity=LOW'
    Assert-Equal $r4.priority 'P3' 'R4 priority=P3'
    $r2 = Get-RaRisk $o 'R2'
    Assert-True ([double]$r2.impact_estimate.amount -eq 1200000) ('R2 影响额应=1,200,000，实际=' + $r2.impact_estimate.amount)
    Assert-True ([double]$r2.coverage_assessment.unprotected_amount -eq 1200000) 'R2 无重疾保障，unprotected=全额'
}

# ------------------------------------------------------------------ 用例 3：已退休无收入
Run-Case 'retired-no-income: R2/R3/R4 NOT_IDENTIFIED + R5 P3' {
    $d = Invoke-RaDiscovery -Fixture 'case-retired-no-income.json' -OutName 'ana_retired_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-retired-no-income.json' -DiscOut 'ana_retired_disc.json' -OutName 'ana_retired.json'
    Assert-Equal (@($o.risks).Count) 5 'retired 应有 5 个风险对象'
    $r2 = Get-RaRisk $o 'R2'; Assert-True ($r2.risk_exists -eq $false) 'R2 无收入不成立'
    $r3 = Get-RaRisk $o 'R3'; Assert-True ($r3.risk_exists -eq $false) 'R3 无收入不成立'
    $r4 = Get-RaRisk $o 'R4'; Assert-True ($r4.risk_exists -eq $false) 'R4 无责任不成立'
    $r5 = Get-RaRisk $o 'R5'; Assert-True ($r5.risk_exists -eq $true) 'R5 应成立'
    Assert-Equal $r5.priority 'P3' 'R5 封顶 P3'
}

# ------------------------------------------------------------------ 用例 4：有房贷但收入 UNKNOWN（对抗）
Run-Case 'responsibility-without-income: R2/R3 UNDETERMINED 不进 risks + status NEED_MORE' {
    $d = Invoke-RaDiscovery -Fixture 'case-responsibility-without-income.json' -OutName 'ana_resp_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-responsibility-without-income.json' -DiscOut 'ana_resp_disc.json' -OutName 'ana_resp.json'
    Assert-Equal (@($o.risks).Count) 3 'resp 只应有 3 个风险对象（R1/R4/R5）'
    Assert-Contains (@($o.risks.risk_category)) 'R1'
    Assert-Contains (@($o.risks.risk_category)) 'R4'
    Assert-Contains (@($o.risks.risk_category)) 'R5'
    Assert-True (@($o.risks.risk_category) -notcontains 'R2') 'R2 UNDETERMINED 不进 risks[]'
    Assert-True (@($o.risks.risk_category) -notcontains 'R3') 'R3 UNDETERMINED 不进 risks[]'
    Assert-Equal $o.analysis_status 'NEED_MORE_INFORMATION' '存在 UNDETERMINED → NEED_MORE_INFORMATION'
}

# ------------------------------------------------------------------ 用例 5：中文负向 token
Run-Case 'chinese-negative-tokens: R4 NOT_IDENTIFIED + R2 amount ~1,050,000' {
    $d = Invoke-RaDiscovery -Fixture 'case-chinese-negative-tokens.json' -OutName 'ana_neg_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-chinese-negative-tokens.json' -DiscOut 'ana_neg_disc.json' -OutName 'ana_neg.json'
    $r4 = Get-RaRisk $o 'R4'
    Assert-True ($r4.risk_exists -eq $false) '中文负向「无房贷/没有/无」应识别为已知无责任'
    $r2 = Get-RaRisk $o 'R2'
    Assert-True ([double]$r2.impact_estimate.amount -eq 1050000) ('R2 应解析「约25万」=250000×3+300000=1,050,000，实际=' + $r2.impact_estimate.amount)
}

# ------------------------------------------------------------------ 用例 6：高风险职业
Run-Case 'high-risk-occupation: R3 IDENTIFIED + likelihood HIGH' {
    $d = Invoke-RaDiscovery -Fixture 'case-high-risk-occupation.json' -OutName 'ana_hr_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-high-risk-occupation.json' -DiscOut 'ana_hr_disc.json' -OutName 'ana_hr.json'
    $r3 = Get-RaRisk $o 'R3'
    Assert-True ($r3.risk_exists -eq $true) 'R3 应成立'
    Assert-Equal $r3.likelihood 'HIGH' '高风险职业 → R3 likelihood=HIGH'
}

# ------------------------------------------------------------------ 用例 7：冲突字段
Run-Case 'income-conflict: analysis_status CONFLICTING + 存在 UNDETERMINED' {
    $d = Invoke-RaDiscovery -Fixture 'case-income-conflict.json' -OutName 'ana_conf_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-income-conflict.json' -DiscOut 'ana_conf_disc.json' -OutName 'ana_conf.json'
    Assert-Equal $o.analysis_status 'CONFLICTING_INFORMATION' '冲突字段 → CONFLICTING_INFORMATION'
    Assert-True (@($o.unknowns).Count -gt 0) '冲突应进入 unknowns'
}

# ------------------------------------------------------------------ 用例 8：全未知
Run-Case 'all-unknown: risks 为空 + NEED_MORE_INFORMATION' {
    $d = Invoke-RaDiscovery -Fixture 'case-all-unknown.json' -OutName 'ana_au_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-all-unknown.json' -DiscOut 'ana_au_disc.json' -OutName 'ana_au.json'
    Assert-Equal (@($o.risks).Count) 0 '全 UNDETERMINED → risks[] 为空'
    Assert-True (@($o.unknowns).Count -gt 0) '全未知应有 unknowns'
    Assert-Equal $o.analysis_status 'NEED_MORE_INFORMATION' '全未知 → NEED_MORE_INFORMATION'
}

# ------------------------------------------------------------------ 用例 9：规则外置负向（清空 negative_tokens → R4 翻转）
Run-Case 'rule-externality: blank negative_tokens flips R4 to IDENTIFIED' {
    # 用文本替换清空 negative_tokens / negative_prefixes（避免 JSON 重序列化）
    $discText = (Get-Content -LiteralPath $discRules -Raw -Encoding UTF8)
    $discText = $discText -replace '"negative_tokens":\s*\[[^\]]*\]', '"negative_tokens": []'
    $discText = $discText -replace '"negative_prefixes":\s*\[[^\]]*\]', '"negative_prefixes": []'
    $discOff = Join-Path $tmp 'negoff_discovery.rules.json'
    [System.IO.File]::WriteAllText($discOff, $discText, [System.Text.UTF8Encoding]::new($true))
    $scorText = (Get-Content -LiteralPath $scorRules -Raw -Encoding UTF8)
    $scorText = $scorText -replace '"negative_tokens":\s*\[[^\]]*\]', '"negative_tokens": []'
    $scorText = $scorText -replace '"negative_prefixes":\s*\[[^\]]*\]', '"negative_prefixes": []'
    $scorOff = Join-Path $tmp 'negoff_scoring.rules.json'
    [System.IO.File]::WriteAllText($scorOff, $scorText, [System.Text.UTF8Encoding]::new($true))

    $d = Invoke-RaDiscovery -Fixture 'case-single-no-dependents.json' -OutName 'ana_negoff_disc.json' -Rules $discOff
    $o = Invoke-RaAnalysis -Fixture 'case-single-no-dependents.json' -DiscOut 'ana_negoff_disc.json' -OutName 'ana_negoff.json' -Rules $scorOff
    $r4 = Get-RaRisk $o 'R4'
    Assert-True ($r4.risk_exists -eq $true) 'negative_tokens 清空后，mortgage「0」被误判为存在暴露 → R4 翻转成立（证明规则外置）'
    # 对照：默认规则下 R4 应不成立
    $d2 = Invoke-RaDiscovery -Fixture 'case-single-no-dependents.json' -OutName 'ana_single_disc2.json'
    $o2 = Invoke-RaAnalysis -Fixture 'case-single-no-dependents.json' -DiscOut 'ana_single_disc2.json' -OutName 'ana_single2.json'
    $r4b = Get-RaRisk $o2 'R4'
    Assert-True ($r4b.risk_exists -eq $false) '默认规则下 R4 应不成立（对照）'
}

# ------------------------------------------------------------------ 用例 10：与充分性阶段集成
Run-Case 'integration-sufficiency: sufficiency NEED_MORE → analysis 继承' {
    # 构造一个 sufficiency 产物（analysis_status=NEED_MORE_INFORMATION）
    $suff = [ordered]@{
        stage = 'sufficiency'; analysis_status = 'NEED_MORE_INFORMATION'
        sufficiency_status = 'INSUFFICIENT'
        domain_results = @()
        blocking_fields = @('annual_income'); conflict_fields = @()
    }
    $suffPath = Join-Path $tmp 'ana_suff_needmore.json'
    $suff | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $suffPath -Encoding UTF8

    $d = Invoke-RaDiscovery -Fixture 'case-dual-income-family.json' -OutName 'ana_int_disc.json'
    $o = Invoke-RaAnalysis -Fixture 'case-dual-income-family.json' -DiscOut 'ana_int_disc.json' -OutName 'ana_int.json' -SuffJson $suffPath
    Assert-Equal $o.analysis_status 'NEED_MORE_INFORMATION' 'sufficiency 的 NEED_MORE_INFORMATION 应被继承'
}

# ------------------------------------------------------------------ 汇总
$pass = 0; $fail = 0
foreach ($r in $results) { if ($r.status -eq 'PASS') { $pass++ } else { $fail++ } }
Write-Output ('TOTAL=' + $results.Count + ' PASS=' + $pass + ' FAIL=' + $fail)

$resultObj = [ordered]@{
    total = $results.Count
    pass = $pass
    fail = $fail
    cases = @($results)
}
$resultObj | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $tmp 'analysis_test_result.json') -Encoding UTF8

if ($fail -gt 0) { exit 1 }
exit 0
