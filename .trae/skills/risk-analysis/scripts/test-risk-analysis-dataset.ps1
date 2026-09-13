#requires -Version 5.1
<#
    test-risk-analysis-dataset.ps1
    ------------------------------
    risk-analysis · Phase 8 Dataset 回归测试。

    两部分：
      A. 基线：跑 run-risk-analysis-dataset.ps1，断言 15/15 通过、退出码 0、五维均分达标。
      B. 反橡皮图章探针（3 个）：注入被篡改的规则副本，数据集**必须**掉下来。
         若篡改规则后数据集仍然全绿，说明期望值是照抄引擎输出的假通过。

    结果落盘 tmp/dataset_test_result.json；任一失败退出码非 0。
#>
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$tmp      = Join-Path $skillRoot 'tmp'
$cfgDir   = Join-Path $skillRoot (Join-Path 'resources' 'config')
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }

$runner      = Join-Path $PSScriptRoot 'run-risk-analysis-dataset.ps1'
$discRules   = Join-Path $cfgDir 'risk-discovery.rules.json'
$scoreRules  = Join-Path $cfgDir 'risk-scoring.rules.json'
$antiRules   = Join-Path $cfgDir 'anti-sales.rules.json'
foreach ($f in @($runner, $discRules, $scoreRules, $antiRules)) {
    if (-not (Test-Path -LiteralPath $f)) { Write-Error "缺少依赖: $f"; exit 2 }
}

$results = New-Object System.Collections.ArrayList

function Assert-True {
    param([bool]$Cond, [string]$Message)
    if (-not $Cond) { throw $Message }
}
function Run-Case {
    param([string]$Name, [scriptblock]$Body)
    try {
        & $Body
        [void]$results.Add([pscustomobject]@{ name = $Name; status = 'PASS' })
        Write-Output ("[PASS] " + $Name)
    } catch {
        [void]$results.Add([pscustomobject]@{ name = $Name; status = 'FAIL'; error = $_.Exception.Message })
        Write-Output ("[FAIL] " + $Name + " :: " + $_.Exception.Message)
    }
}
function Read-Json {
    param([string]$Path)
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Write-RulesCopy {
    param([string]$SourcePath, [string]$Name, [scriptblock]$Mutate)
    $obj = Read-Json -Path $SourcePath
    & $Mutate $obj | Out-Null
    $dest = Join-Path $tmp $Name
    ($obj | ConvertTo-Json -Depth 32) | Set-Content -LiteralPath $dest -Encoding UTF8
    return $dest
}
function Invoke-Dataset {
    param([string]$OutJson, [string]$DiscoveryRules = "", [string]$ScoringRules = "", [string]$AntiSalesRules = "")
    $p = @{ OutputJsonPath = $OutJson; ReportPath = (Join-Path $tmp ([System.IO.Path]::GetFileNameWithoutExtension($OutJson) + '.md')) }
    if (-not [string]::IsNullOrWhiteSpace($DiscoveryRules)) { $p.DiscoveryRulesPath = $DiscoveryRules }
    if (-not [string]::IsNullOrWhiteSpace($ScoringRules))   { $p.ScoringRulesPath = $ScoringRules }
    if (-not [string]::IsNullOrWhiteSpace($AntiSalesRules)) { $p.AntiSalesRulesPath = $AntiSalesRules }
    & $runner @p | Out-Null
    return $LASTEXITCODE
}

# ------------------------------------------------------------------ A. 基线
$baseJson = Join-Path $tmp 'dataset_result.json'
Run-Case 'dataset 基线：全量用例通过且退出码 0' {
    $code = Invoke-Dataset -OutJson $baseJson
    Assert-True ($code -eq 0) "数据集运行器退出码应为 0，实际 $code"
    $r = Read-Json -Path $baseJson
    Assert-True ($r.failed_cases -eq 0) ("不应有用例失败，实际失败 " + $r.failed_cases)
    Assert-True ($r.total_cases -ge 15) ("用例数应 ≥15，实际 " + $r.total_cases)
    Assert-True ([double]$r.overall -ge 90.0) ("综合均分应 ≥90，实际 " + $r.overall)
    Assert-True ([double]$r.averages.evidence_grounding -eq 100.0) ("evidence_grounding 应满分，实际 " + $r.averages.evidence_grounding)
    Assert-True ([double]$r.averages.product_boundary -ge 95.0) ("product_boundary 应 ≥95，实际 " + $r.averages.product_boundary)
}

Run-Case 'dataset 基线：用例分三类且变异类确被判出' {
    $r = Read-Json -Path $baseJson
    $cats = @($r.cases | ForEach-Object { $_.category } | Sort-Object -Unique)
    Assert-True ($cats -contains 'positive') '应含 positive 类'
    Assert-True ($cats -contains 'degraded') '应含 degraded 类'
    Assert-True ($cats -contains 'mutation') '应含 mutation 类'
    $mut = @($r.cases | Where-Object { $_.category -eq 'mutation' })
    Assert-True (@($mut | Where-Object { $_.eval_status -eq 'NEEDS_REVIEW' }).Count -ge 3) '至少 3 个变异用例应上报 NEEDS_REVIEW（事实/立场问题不得自动清洗）'
    Assert-True (@($mut | Where-Object { $_.repair_attempts -ge 1 }).Count -ge 2) '至少 2 个变异用例应由 AUTO 修复收敛'
}

# ------------------------------------------------------------------ B. 反橡皮图章探针
Run-Case 'probe: 清空 negative_substrings → 数据集必须失败（整句否定用例翻转）' {
    $copy = Write-RulesCopy -SourcePath $discRules -Name 'probe-disc-no-substring.json' -Mutate { param($o) $o.negative_substrings = @() }
    $out = Join-Path $tmp 'dataset_probe_substring.json'
    $code = Invoke-Dataset -OutJson $out -DiscoveryRules $copy
    Assert-True ($code -ne 0) '清空子串否定词表后数据集必须失败（否则期望值是照抄引擎输出的假通过）'
    $r = Read-Json -Path $out
    Assert-True ($r.failed_cases -ge 1) "应有用例失败，实际 failed=$($r.failed_cases)"
}

Run-Case 'probe: 篡改 priority_matrix → 数据集必须失败（优先级期望失配）' {
    $copy = Write-RulesCopy -SourcePath $scoreRules -Name 'probe-score-matrix.json' -Mutate { param($o) $o.priority_matrix.CRITICAL.HIGH = 'P3' }
    $out = Join-Path $tmp 'dataset_probe_matrix.json'
    $code = Invoke-Dataset -OutJson $out -ScoringRules $copy
    Assert-True ($code -ne 0) '篡改优先级矩阵后数据集必须失败'
    $r = Read-Json -Path $out
    Assert-True ($r.failed_cases -ge 1) "应有用例失败，实际 failed=$($r.failed_cases)"
}

Run-Case 'probe: 清空 panic_tokens → 数据集必须失败（恐吓话术漏检）' {
    $copy = Write-RulesCopy -SourcePath $antiRules -Name 'probe-anti-no-panic.json' -Mutate { param($o) $o.panic_tokens = @() }
    $out = Join-Path $tmp 'dataset_probe_panic.json'
    $code = Invoke-Dataset -OutJson $out -AntiSalesRules $copy
    Assert-True ($code -ne 0) '清空恐吓词典后数据集必须失败（否则反销售检查形同虚设）'
    $r = Read-Json -Path $out
    $mut3 = @($r.cases | Where-Object { $_.case_id -eq 'ds-mut-03-sales-language' })
    Assert-True (@($mut3).Count -eq 1) '应包含 ds-mut-03-sales-language 用例'
    Assert-True (-not $mut3[0].passed) '恐吓话术用例在词典被清空后必须失败'
}

# 探针会往 tmp/ds_<id>_*.json 写入被污染的规则下的产物；收尾必须再跑一次基线，
# 保证 verify-contract.py §10 读到的是默认规则下的产物（否则会用探针残留误判）。
$restoreCode = Invoke-Dataset -OutJson $baseJson
if ($restoreCode -ne 0) { Write-Output '[WARN] 探针后重跑基线未全绿，请检查规则文件是否被污染' }

# ------------------------------------------------------------------ 汇总
$passed = @($results | Where-Object { $_.status -eq 'PASS' }).Count
$failed = @($results | Where-Object { $_.status -eq 'FAIL' }).Count
$payload = [ordered]@{
    stage  = 'dataset'
    total  = $results.Count
    passed = $passed
    failed = $failed
    cases  = @($results)
}
$resPath = Join-Path $tmp 'dataset_test_result.json'
[System.IO.File]::WriteAllText($resPath, ($payload | ConvertTo-Json -Depth 10), [System.Text.UTF8Encoding]::new($false))

Write-Output ''
Write-Output ("DATASET TESTS: total=" + $results.Count + " passed=" + $passed + " failed=" + $failed)
if ($failed -gt 0) { exit 1 }
exit 0
