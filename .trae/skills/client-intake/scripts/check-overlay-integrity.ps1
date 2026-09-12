#Requires -Version 5.1
<#
    check-overlay-integrity.ps1 — Overlay 架构守卫（Architecture Eval）

    对应 Lawgent 的 test_skill_anatomy.py 与 test_skill_no_aviation_specific_strings：
    不只测"答案对不对"，还测"架构有没有被破坏"。

    检查三层：
      A. 结构完整性  —— overlay 目录/文件/字段是否齐全
      B. 领域污染    —— 险种专有术语是否泄漏进通用层（架构退化的头号信号）
      C. 文档结构    —— intake-dimensions.md 必备小节是否齐全

    用法：
      .check-overlay-integrity.ps1
      .check-overlay-integrity.ps1 -VerboseDetail
      .check-overlay-integrity.ps1 -OutputJsonPath out.json

    退出码：0 = 全部通过；1 = 存在 FAIL
#>
[CmdletBinding()]
param(
    [switch]$VerboseDetail,
    [string]$OutputJsonPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------- 路径 ----------
$SkillDir = Split-Path -Parent $PSScriptRoot
$OvDir    = Join-Path $SkillDir "overlays"

# 通用层：这些文件绝不允许出现险种专有术语
$genericPaths = @()
$genericPaths += (Join-Path $SkillDir "SKILL.md")
Get-ChildItem -Path (Join-Path $SkillDir "references") -Filter '*.md' -File -ErrorAction SilentlyContinue |
    ForEach-Object { $genericPaths += $_.FullName }
Get-ChildItem -Path (Join-Path $SkillDir "schemas") -Filter '*.json' -File -ErrorAction SilentlyContinue |
    ForEach-Object { $genericPaths += $_.FullName }
$genericPaths = @($genericPaths | Where-Object { Test-Path -LiteralPath $_ })

# ---------- 结果收集 ----------
$results = New-Object System.Collections.ArrayList
function Add-R {
    param([bool]$Ok, [string]$Code, [string]$Msg)
    [void]$results.Add([pscustomobject]@{
        Code = $Code; Ok = $Ok; Msg = $Msg
    })
}

Write-Output "=== Overlay 架构守卫 ==="
Write-Output ("Skill 目录: {0}" -f $SkillDir)
Write-Output ""

# ---------- 0. 前置 ----------
if (-not (Test-Path -LiteralPath $OvDir)) {
    Write-Output "FATAL: overlays 目录不存在"
    exit 1
}
Add-R $true "A0" "overlays 目录存在"
Add-R (Test-Path -LiteralPath (Join-Path $OvDir "README.md")) "A0b" "overlays/README.md（协议）存在"
Add-R (Test-Path -LiteralPath (Join-Path $OvDir "_template")) "A0c" "overlays/_template（新险种模板）存在"

# ---------- A0d. Skill Anatomy（Lawgent test_skill_anatomy 精神：架构纪律） ----------
$skillMd = Join-Path $SkillDir "SKILL.md"
if (Test-Path -LiteralPath $skillMd) {
    $skLines = @(Get-Content -LiteralPath $skillMd -Encoding UTF8)
    Add-R ($skLines.Count -le 100) "A0d" ("SKILL.md 行数 {0} 超过 100 行上限（manifest 应当只是路由，不是百科全书）" -f $skLines.Count)

    $skRaw = $skLines -join "`n"
    Add-R ($skRaw -match '^---\s*\n')            "A0e" "SKILL.md 缺少 frontmatter 起始分隔线"
    Add-R ($skRaw -match '(?m)^name:\s*\S')      "A0f" "frontmatter 缺少 name"
    Add-R ($skRaw -match '(?m)^description:\s*\S') "A0g" "frontmatter 缺少 description"
    Add-R ($skRaw -match 'Output Contract \(binding\)') "A0h" "缺少 'Output Contract (binding)' 节"
    Add-R ($skRaw -match 'Domain Overlays')      "A0i" "缺少 'Domain Overlays' 节（险种扩展层未接入 manifest）"
} else {
    Add-R $false "A0d" "SKILL.md 不存在"
}

# ---------- YAML 解析 ----------
function Parse-OverlayYaml {
    param([string]$Path)
    $yaml = [ordered]@{}
    $cur  = $null
    foreach ($raw in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $line = $raw -replace '#.*$', ''
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -match '^(\S[^:]*):\s*(.*)$') {
            $k = $matches[1].Trim(); $v = $matches[2].Trim(); $cur = $k
            if ($v -eq '') { $yaml[$k] = @() } else { $yaml[$k] = $v }
            continue
        }
        if ($line -match '^\s+-\s*(.*)$') {
            if ($cur -ne $null) { $yaml[$cur] += @($matches[1].Trim()) }
            continue
        }
        if ($line -match '^\s+(\S[^:]*):\s*(.*)$') {
            $k = $matches[1].Trim(); $v = $matches[2].Trim(); $cur = $k
            if ($v -eq '') { $yaml[$k] = @() } else { $yaml[$k] = $v }
            continue
        }
    }
    return $yaml
}

# ---------- A. 结构完整性 ----------
Write-Output "--- A. 结构完整性 ---"

$ovDirs = @(Get-ChildItem -LiteralPath $OvDir -Directory | Where-Object { $_.Name -ne '_template' })
Add-R ($ovDirs.Count -gt 0) "A1" ("overlay 数量 = {0}（0 个说明扩展层未落地）" -f $ovDirs.Count)

$allTerms = @{}          # term -> overlayId
$parsed   = @()

foreach ($d in $ovDirs) {
    $id = $d.Name
    $yp = Join-Path $d.FullName "overlay.yaml"
    $hasY = Test-Path -LiteralPath $yp
    Add-R $hasY "A2/$id" "overlay.yaml 存在"
    if (-not $hasY) { continue }

    $y = Parse-OverlayYaml -Path $yp

    # A3 必需字段
    $missing = @()
    foreach ($k in @('id','name','status','priority')) {
        if (-not $y.Contains($k) -or [string]::IsNullOrWhiteSpace([string]$y[$k])) { $missing += $k }
    }
    Add-R ($missing.Count -eq 0) "A3/$id" ("必需字段缺失: {0}" -f ($missing -join ', '))

    # A4 id 与目录名一致
    $yid = [string]$y['id']
    Add-R ($yid -eq $id) "A4/$id" ("id='{0}' 与目录名不一致" -f $yid)

    # A5 status 合法
    $st = [string]$y['status']
    Add-R (($st -eq 'active') -or ($st -eq 'draft')) "A5/$id" ("status='{0}' 非法（应为 active|draft）" -f $st)

    # A6 priority 可解析为数字
    $pr = 0
    $okPr = [int]::TryParse([string]($y['priority'] | Select-Object -First 1), [ref]$pr)
    Add-R $okPr "A6/$id" "priority 不是整数"

    # A7 keywords 非空
    $kw = @($y['keywords'] | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Add-R ($kw.Count -gt 0) "A7/$id" "triggers.keywords 为空（该 overlay 永远不会被激活）"

    # A8 dimensions 文件
    $dimName = [string]$y['dimensions']
    if ([string]::IsNullOrWhiteSpace($dimName)) { $dimName = 'intake-dimensions.md' }
    $dimPath = Join-Path $d.FullName $dimName
    Add-R (Test-Path -LiteralPath $dimPath) "A8/$id" ("dimensions 文件缺失: {0}" -f $dimName)

    # A9 contamination_terms 非空
    $terms = @($y['contamination_terms'] | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Add-R ($terms.Count -gt 0) "A9/$id" "contamination_terms 为空（该险种守不住架构边界）"

    foreach ($t in $terms) {
        if ($allTerms.ContainsKey($t)) {
            Add-R $false "A10/$id" ("术语'{0}' 与 overlay '{1}' 重复声明" -f $t, $allTerms[$t])
        } else {
            $allTerms[$t] = $id
        }
    }

    # A11 占位符未替换（防止复制模板后忘记填写就宣称"新增了险种"）
    $placeholders = @()
    foreach ($k in @('id','name','version','status','priority','dimensions')) {
        $v = [string]$y[$k]
        if ($v -match '<' -or $v -match '待填' -or $v -match 'TODO' -or $v -match 'XXX') {
            $placeholders += "$k=$v"
        }
    }
    foreach ($t in (@($y['keywords']) + @($y['goal_types']) + @($y['contamination_terms']) + @($y['must_not']))) {
        $ts = [string]$t
        if ($ts -match '<' -or $ts -match '待填' -or $ts -match 'TODO' -or $ts -match 'XXX') {
            $placeholders += "list:$ts"
        }
    }
    Add-R ($placeholders.Count -eq 0) "A11/$id" ("存在未替换的占位符: {0}" -f ($placeholders -join ', '))

    $parsed += [pscustomobject]@{
        Id = $id; Name = [string]$y['name']; Status = $st
        Priority = $pr; Keywords = $kw; Terms = $terms; DimPath = $dimPath
    }
}

# ---------- C. 文档结构 ----------
Write-Output "--- C. intake-dimensions.md 结构 ---"
$requiredSections = @('## A. 必填维度', '## D. 本险种特有的边界红线', '## F. 状态文件落点')
foreach ($o in $parsed) {
    if (-not (Test-Path -LiteralPath $o.DimPath)) { continue }
    $txt = Get-Content -LiteralPath $o.DimPath -Raw -Encoding UTF8
    foreach ($sec in $requiredSections) {
        $has = $txt -match [regex]::Escape($sec)
        Add-R $has "C1/$($o.Id)" ("缺少必备小节: {0}" -f $sec)
    }
}

# ---------- B. 领域污染（核心守卫）----------
Write-Output "--- B. 领域污染检查（通用层不得含险种专有术语）---"

$genericText = @{}
foreach ($p in $genericPaths) {
    $genericText[$p] = (Get-Content -LiteralPath $p -Raw -Encoding UTF8)
}

$pollution = @()
foreach ($o in $parsed) {
    foreach ($t in $o.Terms) {
        foreach ($p in $genericPaths) {
            if ($genericText[$p] -match [regex]::Escape($t)) {
                $rel = $p.Replace($SkillDir, '.')
                $pollution += [pscustomobject]@{
                    Term = $t; Overlay = $o.Id; File = $rel
                }
            }
        }
    }
}

Add-R ($pollution.Count -eq 0) "B1" ("通用层被领域污染：{0}" -f (
    ($pollution | ForEach-Object { "{0}@{1}" -f $_.Term, $_.File }) -join '; '
))

if ($VerboseDetail -and $pollution.Count -gt 0) {
    Write-Output ""
    Write-Output "污染明细："
    foreach ($x in $pollution) {
        Write-Output ("  [{0}] 术语 '{1}' 出现在 {2}" -f $x.Overlay, $x.Term, $x.File)
    }
}

Write-Output ("扫描通用层文件 {0} 个，术语 {1} 个" -f $genericPaths.Count, $allTerms.Count)

# ---------- 汇总 ----------
Write-Output ""
Write-Output "=== 汇总 ==="
$pass = @($results | Where-Object { $_.Ok }).Count
$fail = @($results | Where-Object { -not $_.Ok }).Count
Write-Output ("PASS = {0}   FAIL = {1}" -f $pass, $fail)

if ($fail -gt 0) {
    Write-Output ""
    Write-Output "--- FAIL 明细 ---"
    foreach ($r in ($results | Where-Object { -not $_.Ok })) {
        Write-Output ("  [{0}] {1}" -f $r.Code, $r.Msg)
    }
}

Write-Output ""
Write-Output "--- Overlay 状态 ---"
foreach ($o in ($parsed | Sort-Object { -$_.Priority })) {
    $flag = if ($o.Status -eq 'active') { 'ACTIVE' } else { 'DRAFT ' }
    Write-Output ("  [{0}] {1,-18} {2,-14} p={3,-3} kw={4,-3} terms={5}" -f $flag, $o.Id, $o.Name, $o.Priority, $o.Keywords.Count, $o.Terms.Count)
}

if ($OutputJsonPath) {
    $obj = [ordered]@{
        pass = $pass
        fail = $fail
        overlay_count = $parsed.Count
        overlays = @($parsed | ForEach-Object {
            [ordered]@{ id = $_.Id; name = $_.Name; status = $_.Status; priority = $_.Priority }
        })
        pollution = @($pollution)
        failures  = @($results | Where-Object { -not $_.Ok } | ForEach-Object {
            [ordered]@{ code = $_.Code; msg = $_.Msg }
        })
    }
    $enc = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($OutputJsonPath, ($obj | ConvertTo-Json -Depth 6), $enc)
    Write-Output ""
    Write-Output "JSON 已写入: $OutputJsonPath"
}

if ($fail -gt 0) { exit 1 } else { exit 0 }
