#requires -Version 5.1
<#
    test-risk-analysis-anatomy.ps1
    -------------------------------
    check-skill-anatomy.ps1 的回归 + 反橡皮图章自检。

    基线必须全 PASS；随后把 skill 复制到 tmp 并注入 4 种污染，
    每种污染守卫都必须 FAIL —— 否则守卫是橡皮图章。
#>
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$tmp       = Join-Path $skillRoot 'tmp'
$guard     = Join-Path $PSScriptRoot 'check-skill-anatomy.ps1'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }

$results = [System.Collections.Generic.List[object]]::new()

function Assert-True { param([bool]$Cond, [string]$Message) if (-not $Cond) { throw $Message } }
function Run-Case {
    param([string]$Name, [scriptblock]$Body)
    try { & $Body; $results.Add([pscustomobject]@{ name = $Name; status = 'PASS'; message = '' }) | Out-Null
          Write-Output "[PASS] $Name" }
    catch { $results.Add([pscustomobject]@{ name = $Name; status = 'FAIL'; message = $_.Exception.Message }) | Out-Null
            Write-Output "[FAIL] $Name :: $($_.Exception.Message)" }
}

function Invoke-Guard {
    param([string]$Dir)
    $out = & $guard -SkillDir $Dir 2>&1
    return @{ Exit = $LASTEXITCODE; Text = ($out -join "`n") }
}

function New-SkillCopy {
    param([string]$Name)
    # 每次用唯一目录名：避免删除上一轮副本（删除会触发批量删除确认，且 tmp 本就不计入基线）
    $dst = Join-Path $tmp ($Name + '_' + (Get-Date -Format 'HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 6))
    New-Item -ItemType Directory -Path $dst | Out-Null
    foreach ($sub in @('references', 'schemas', 'evals', 'resources', 'scripts')) {
        $src = Join-Path $skillRoot $sub
        if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force }
    }
    foreach ($f in @('SKILL.md', 'CONTRACT.md')) {
        $src = Join-Path $skillRoot $f
        if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination $dst -Force }
    }
    return $dst
}

# ---------------------------------------------------------------- 1 基线
Run-Case 'baseline: 守卫全 PASS' {
    $r = Invoke-Guard -Dir $skillRoot
    Assert-True ($r.Exit -eq 0) ("基线守卫应 PASS，实际 exit=" + $r.Exit + "`n" + $r.Text)
}

# ---------------------------------------------------------------- 2 删文件
Run-Case 'probe: 删除 evals/eval-policy.md → 守卫必须 FAIL' {
    $d = New-SkillCopy 'anatomy_probe_missing'
    [System.IO.File]::Delete((Join-Path $d 'evals/eval-policy.md'))
    $r = Invoke-Guard -Dir $d
    Assert-True ($r.Exit -ne 0) '缺文件竟未被检出（A8 失效）'
    Assert-True ($r.Text -match 'A8_eval_policy') '应命中 A8_eval_policy'
}

# ---------------------------------------------------------------- 3 死配置
Run-Case 'probe: 注入未被消费的规则键 → 守卫必须 FAIL' {
    $d = New-SkillCopy 'anatomy_probe_deadkey'
    $p = Join-Path $d 'resources/config/risk-scoring.rules.json'
    $o = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
    # 键名必须运行时生成：若写成字面量，它会出现在本测试脚本自身的文本里，
    # 被守卫的"是否被脚本引用"扫描命中 → 假阴性（守卫扫的是全部脚本文本）
    $deadKey = 'zz_dead_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $o | Add-Member -NotePropertyName $deadKey -NotePropertyValue 0.5 -Force
    ($o | ConvertTo-Json -Depth 24) | Set-Content -LiteralPath $p -Encoding UTF8
    $r = Invoke-Guard -Dir $d
    Assert-True ($r.Exit -ne 0) '死配置竟未被检出（B2 失效）'
    Assert-True ($r.Text -match 'B2_no_dead_rule_keys') '应命中 B2_no_dead_rule_keys'
}

# ---------------------------------------------------------------- 4 override 缺 enabled
Run-Case 'probe: priority_overrides 去掉 enabled → 守卫必须 FAIL' {
    $d = New-SkillCopy 'anatomy_probe_override'
    $p = Join-Path $d 'resources/config/risk-scoring.rules.json'
    $o = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
    $kept = @()
    foreach ($ov in @($o.priority_overrides)) {
        $c = [pscustomobject][ordered]@{ id = $ov.id; if = $ov.if }
        if ($null -ne $ov.max_priority) { $c | Add-Member -NotePropertyName 'max_priority' -NotePropertyValue $ov.max_priority }
        if ($null -ne $ov.min_priority) { $c | Add-Member -NotePropertyName 'min_priority' -NotePropertyValue $ov.min_priority }
        $kept += $c
    }
    $o.priority_overrides = $kept
    ($o | ConvertTo-Json -Depth 24) | Set-Content -LiteralPath $p -Encoding UTF8
    $r = Invoke-Guard -Dir $d
    Assert-True ($r.Exit -ne 0) 'override 缺 enabled 竟未被检出（B3 失效）'
    Assert-True ($r.Text -match 'B3_overrides_explicit_enabled') '应命中 B3'
}

# ---------------------------------------------------------------- 5 去 BOM
Run-Case 'probe: 剥掉 .ps1 的 BOM → 守卫必须 FAIL' {
    $d = New-SkillCopy 'anatomy_probe_bom'
    $p = Join-Path $d 'scripts/invoke-risk-analysis-sufficiency.ps1'
    $bytes = [System.IO.File]::ReadAllBytes($p)
    if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        [System.IO.File]::WriteAllBytes($p, $bytes[3..($bytes.Length - 1)])
    }
    $r = Invoke-Guard -Dir $d
    Assert-True ($r.Exit -ne 0) '丢 BOM 竟未被检出（B5 失效）'
    Assert-True ($r.Text -match 'B5_ps1_bom') '应命中 B5_ps1_bom'
}

# ---------------------------------------------------------------- 6 悬空引用
Run-Case 'probe: 文档引用不存在的文件且未标 ⏳ → 守卫必须 FAIL' {
    $d = New-SkillCopy 'anatomy_probe_dangling'
    $p = Join-Path $d 'references/02-sufficiency.md'
    Add-Content -LiteralPath $p -Value '详见 references/99-not-exist.md 的说明。' -Encoding UTF8
    $r = Invoke-Guard -Dir $d
    Assert-True ($r.Exit -ne 0) '悬空引用竟未被检出（B1 失效）'
    Assert-True ($r.Text -match 'B1_no_dangling_refs') '应命中 B1_no_dangling_refs'
}

# ---------------------------------------------------------------- 汇总
$pass = @($results | Where-Object { $_.status -eq 'PASS' }).Count
$fail = @($results | Where-Object { $_.status -eq 'FAIL' }).Count
Write-Output "ANATOMY TESTS: total=$($results.Count) passed=$pass failed=$fail"

[ordered]@{ total = $results.Count; pass = $pass; fail = $fail; cases = @($results) } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $tmp 'anatomy_test_result.json') -Encoding UTF8

if ($fail -gt 0) { exit 1 }
exit 0
