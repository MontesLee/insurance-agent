#requires -Version 5.1
<#
    test-risk-analysis-repair.ps1
    -----------------------------
    risk-analysis · Repair Loop（Phase 7）单元 + 回归测试。

    用例由 evals/cases/repair-manifest.json 驱动（单一真源）：
      可修复类 → 断言收敛到 PASS 且 repair_attempts 符合预期；
      不可修复类 → 断言 NEEDS_REVIEW、repair_attempts=0 且产物原样未改（留痕，禁止清洗）；
      边界类 → 多轮收敛 / 不动点提前终止 / 规则外置翻转。

    结果落盘 tmp/repair_test_result.json（CI 友好）；任一失败退出码非 0。
#>
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$tmp    = Join-Path $skillRoot 'tmp'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }
$fx     = Join-Path $skillRoot 'evals'; $fx = Join-Path $fx 'fixtures'; $fx = Join-Path $fx 'unit'
$fxRepair = Join-Path $fx 'repair'
$fxEval   = Join-Path $fx 'eval'
$casesDir = Join-Path $skillRoot (Join-Path 'evals' 'cases')

$repairEngine = Join-Path $PSScriptRoot 'invoke-risk-analysis-repair.ps1'
if (-not (Test-Path -LiteralPath $repairEngine)) { Write-Error "找不到 Repair 引擎: $repairEngine"; exit 2 }

$manifestPath = Join-Path $casesDir 'repair-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { Write-Error "找不到用例清单: $manifestPath"; exit 2 }
$manifest = (Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json)

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

# 结构化等价比较：两边都经 ConvertFrom-Json → ConvertTo-Json 归一，避免缩进差异
function Get-RpCanon {
    param([string]$Path)
    $o = (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
    return ($o | ConvertTo-Json -Depth 20 -Compress)
}

function Get-RtMember {
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

# ------------------------------------------------------------------ 逐用例执行
foreach ($c in @($manifest.cases)) {
    $cname   = [string]$c.name
    $dirKey  = [string]$(if (Get-RtMember -Object $c -Name 'dir') { $c.dir } else { 'repair' })
    $baseDir = if ($dirKey -eq 'eval') { $fxEval } else { $fxRepair }
    $fixture = Join-Path $baseDir ([string]$c.fixture)

    $evalOut = Join-Path $tmp ("rpt_" + $cname + "_e.json")
    $repOut  = Join-Path $tmp ("rpt_" + $cname + "_a.json")
    if (Test-Path -LiteralPath $evalOut) { [System.IO.File]::Delete($evalOut) }
    if (Test-Path -LiteralPath $repOut)  { [System.IO.File]::Delete($repOut) }

    Run-Case ("repair: " + $cname) {
        Assert-True (Test-Path -LiteralPath $fixture) ("fixture 不存在: " + $fixture)

        $p = @{ AnalysisJsonPath = $fixture; EvalOutputJsonPath = $evalOut; RepairedOutputJsonPath = $repOut }
        $sc = Get-RtMember -Object $c -Name 'scoring'
        if ($sc) { $p.ScoringRulesPath = Join-Path $fxRepair ([string]$sc) }
        $rr = Get-RtMember -Object $c -Name 'repair_rules'
        if ($rr) { $p.RepairRulesPath = Join-Path $fxRepair ([string]$rr) }
        $dv = Get-RtMember -Object $c -Name 'discovery'
        if ($dv) { $p.DiscoveryJsonPath = Join-Path $baseDir ([string]$dv) }
        & $repairEngine @p | Out-Null

        Assert-True (Test-Path -LiteralPath $evalOut) "Repair 未产出 EvalResult"
        Assert-True (Test-Path -LiteralPath $repOut)  "Repair 未产出修复后产物"
        $e = (Get-Content -LiteralPath $evalOut -Raw -Encoding UTF8 | ConvertFrom-Json)

        $exp = $c.expect
        Assert-Equal $e.eval_status $exp.eval_status ("eval_status (" + $cname + ")")
        Assert-Equal $e.repair_attempts $exp.repair_attempts ("repair_attempts (" + $cname + ")")
        Assert-Equal $e.max_repair_attempts 2 ("max_repair_attempts 契约固定为 2")
        Assert-True ([int]$e.repair_attempts -le 2) "repair_attempts 不得超过上限 2"

        if ($null -ne (Get-RtMember -Object $exp -Name 'repair_required')) {
            Assert-Equal $e.repair_required $exp.repair_required ("repair_required (" + $cname + ")")
        }

        # repair_log 条数必须与 attempt 数一致
        $log = @(Get-RtMember -Object $e -Name 'repair_log')
        Assert-Equal $log.Count ([int]$e.repair_attempts) ("repair_log 条数应等于 repair_attempts (" + $cname + ")")

        # 期望命中的动作 / code（取自第一轮日志）
        $wantAction = Get-RtMember -Object $exp -Name 'action'
        if ($wantAction -and $log.Count -ge 1) {
            Assert-True ([string]$log[0].action -match [string]$wantAction) ("repair_log[0].action 应含 " + $wantAction + "，实际=" + [string]$log[0].action)
        }
        $wantCode = Get-RtMember -Object $exp -Name 'code'
        if ($wantCode -and $log.Count -ge 1) {
            $codes = @($log[0].failed_codes)
            Assert-True ($codes -contains [string]$wantCode) ("repair_log[0].failed_codes 应含 " + $wantCode + "，实际=" + ($codes -join ","))
        }

        # 不可修复类：产物必须原样保留（禁止清洗留痕项）
        if ((Get-RtMember -Object $exp -Name 'output_unchanged') -eq $true) {
            $a = Get-RpCanon -Path $fixture
            $b = Get-RpCanon -Path $repOut
            Assert-True ($a -eq $b) ("不可自动修复的用例不得改动产物（" + $cname + "）")
        }

        # PASS 不得残留 needs_review_note；NEEDS_REVIEW 必须给出说明
        if ([string]$exp.eval_status -eq 'PASS') {
            Assert-True ($null -eq (Get-RtMember -Object $e -Name 'needs_review_note')) "PASS 不应残留 needs_review_note"
        } else {
            $note = [string](Get-RtMember -Object $e -Name 'needs_review_note')
            Assert-True (-not [string]::IsNullOrWhiteSpace($note)) "NEEDS_REVIEW 必须给出 needs_review_note"
            Assert-True ($note -match '需人工确认') "needs_review_note 必须含『需人工确认』段"
        }

        # 悬空锚点必须被清除
        $absent = Get-RtMember -Object $exp -Name 'absent_ref'
        if ($absent) {
            $repaired = (Get-Content -LiteralPath $repOut -Raw -Encoding UTF8 | ConvertFrom-Json)
            foreach ($r in @($repaired.risks)) {
                $refs = @($r.reasoning_evidence_refs)
                Assert-True (-not ($refs -contains [string]$absent)) ("修复后仍残留锚点 " + $absent + " (" + $r.risk_id + ")")
            }
        }
    }
}

# ------------------------------------------------------------------ 汇总
$passed = @($results | Where-Object { $_.status -eq 'PASS' }).Count
$failed = @($results | Where-Object { $_.status -eq 'FAIL' }).Count
$summary = [pscustomobject][ordered]@{
    total  = $results.Count
    passed = $passed
    failed = $failed
    cases  = $results
}
$summaryPath = Join-Path $tmp 'repair_test_result.json'
($summary | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Output ("REPAIR SUMMARY: total=" + $results.Count + " passed=" + $passed + " failed=" + $failed)
if ($failed -gt 0) { exit 1 }
exit 0
