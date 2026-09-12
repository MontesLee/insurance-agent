#requires -Version 5.1
<#
    test-risk-analysis-eval.ps1
    ----------------------------
    risk-analysis · Eval（Phase 6）单元 + 回归测试。

    用例由 evals/cases/manifest.json 驱动（单一真源）：
      正向：对 positive 列表跑 discovery → analysis → eval，断言 eval_status=PASS 且 7 项全 PASS。
      负向（对抗）：对 negative 列表跑 eval，断言 target_check FAIL 且其余 6 项 PASS（反向断言防误伤）。

    结果落盘 tmp/eval_test_result.json（CI 友好）；任一失败退出码非 0。
#>
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$tmp    = Join-Path $skillRoot 'tmp'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }
$fx     = Join-Path $skillRoot 'evals'; $fx = Join-Path $fx 'fixtures'; $fx = Join-Path $fx 'unit'
$fxDisc = Join-Path $fx 'discovery'
$fxEval = Join-Path $fx 'eval'

$discEngine = Join-Path $skillRoot 'scripts\invoke-risk-analysis-discovery.ps1'
$anaEngine  = Join-Path $skillRoot 'scripts\invoke-risk-analysis-analysis.ps1'
$evalEngine = Join-Path $skillRoot 'scripts\invoke-risk-analysis-eval.ps1'

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

# ------------------------------------------------------------------ engine wrappers
function Invoke-RaDiscovery {
    param([string]$Fixture, [string]$OutName)
    $inPath  = Join-Path $fxDisc $Fixture
    $outPath = Join-Path $tmp $OutName
    if (Test-Path -LiteralPath $outPath) { [System.IO.File]::Delete($outPath) }
    $params = @{ InputJsonPath = $inPath; OutputJsonPath = $outPath }
    & $discEngine @params | Out-Null
    if (-not (Test-Path -LiteralPath $outPath)) { throw "discovery produced no output for $Fixture" }
    return (Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Invoke-RaAnalysis {
    param([string]$Fixture, [string]$DiscOut, [string]$OutName)
    $inPath  = Join-Path $fxDisc $Fixture
    $discPath = Join-Path $tmp $DiscOut
    $outPath = Join-Path $tmp $OutName
    if (Test-Path -LiteralPath $outPath) { [System.IO.File]::Delete($outPath) }
    $params = @{ InputJsonPath = $inPath; OutputJsonPath = $outPath; DiscoveryJsonPath = $discPath }
    & $anaEngine @params | Out-Null
    if (-not (Test-Path -LiteralPath $outPath)) { throw "analysis produced no output for $DiscOut" }
    return (Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Invoke-RaEval {
    param([string]$AnalysisPath, [string]$OutName, [string]$DiscoveryPath = "")
    $outPath = Join-Path $tmp $OutName
    if (Test-Path -LiteralPath $outPath) { [System.IO.File]::Delete($outPath) }
    $params = @{ AnalysisJsonPath = $AnalysisPath; OutputJsonPath = $outPath }
    if (-not [string]::IsNullOrEmpty($DiscoveryPath)) { $params.DiscoveryJsonPath = $DiscoveryPath }
    & $evalEngine @params | Out-Null
    if (-not (Test-Path -LiteralPath $outPath)) { throw "eval produced no output for $AnalysisPath" }
    return (Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}

# ------------------------------------------------------------------ 用例清单（单一真源）
$manifestPath = Join-Path $skillRoot (Join-Path 'evals' (Join-Path 'cases' 'manifest.json'))
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "缺少用例清单: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

# ------------------------------------------------------------------ 正向：端到端 discovery→analysis→eval，断言 PASS
foreach ($c in @($manifest.positive)) {
    $fix  = [string]$c.name
    $exp  = [string]$c.expect_status
    $base = [System.IO.Path]::GetFileNameWithoutExtension($fix)
    Run-Case ("eval-positive: $fix → eval_status=$exp 且 7 项全 PASS") {
        $d = Invoke-RaDiscovery -Fixture $fix -OutName ("evd_$($base)_d.json")
        $a = Invoke-RaAnalysis  -Fixture $fix -DiscOut ("evd_$($base)_d.json") -OutName ("evd_$($base)_a.json")
        $e = Invoke-RaEval -AnalysisPath (Join-Path $tmp ("evd_$($base)_a.json")) -DiscoveryPath (Join-Path $tmp ("evd_$($base)_d.json")) -OutName ("evd_$($base)_e.json")
        Assert-Equal $e.eval_status $exp ("eval 应 $exp : $fix")
        foreach ($k in $e.checks.PSObject.Properties.Name) {
            Assert-Equal $e.checks.$k.status 'PASS' ("check [$k] 应 PASS ($fix)")
        }
    }
}

# ------------------------------------------------------------------ 负向：对抗 fixture，断言特定 check FAIL
foreach ($c in @($manifest.negative)) {
    $neg    = [string]$c.fixture
    $target = [string]$c.target_check
    $side   = [string]$c.discovery_sidecar
    Run-Case ("eval-negative: $neg → $target FAIL") {
        $path = Join-Path $fxEval $neg
        # side-car：清单指定时一并传入，以启用「应发现域覆盖」子检查
        $sideCar = if (-not [string]::IsNullOrWhiteSpace($side)) { Join-Path $fxEval $side } else { "" }
        $e = if (-not [string]::IsNullOrWhiteSpace($sideCar) -and (Test-Path -LiteralPath $sideCar)) {
            Invoke-RaEval -AnalysisPath $path -DiscoveryPath $sideCar -OutName ("evn_$($neg).json")
        } else {
            Invoke-RaEval -AnalysisPath $path -OutName ("evn_$($neg).json")
        }
        Assert-Equal $e.eval_status 'FAIL' ("eval 应 FAIL: $neg")
        Assert-Equal $e.checks.$target.status 'FAIL' ("check [$target] 应 FAIL: $neg")
        # 反向断言：除目标外的其他 6 项必须 PASS（证明变异只打中一个检查）
        foreach ($k in $e.checks.PSObject.Properties.Name) {
            if ($k -ne $target) {
                Assert-Equal $e.checks.$k.status 'PASS' ("check [$k] 应不受 $neg 影响")
            }
        }
    }
}

# ------------------------------------------------------------------ 汇总
$pass = @($results | Where-Object { $_.status -eq 'PASS' }).Count
$fail = @($results | Where-Object { $_.status -eq 'FAIL' }).Count
$summary = [ordered]@{
    total   = $results.Count
    passed  = $pass
    failed  = $fail
    cases   = $results
}
[System.IO.File]::WriteAllText((Join-Path $tmp 'eval_test_result.json'), ($summary | ConvertTo-Json -Depth 6), [System.Text.UTF8Encoding]::new($false))

if ($fail -gt 0) {
    Write-Output ("EVAL TESTS FAILED: $fail/$($results.Count)")
    exit 1
}
Write-Output ("EVAL TESTS PASSED: $pass/$($results.Count)")
exit 0
