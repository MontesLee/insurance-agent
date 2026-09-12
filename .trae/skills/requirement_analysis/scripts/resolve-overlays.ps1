<#
.SYNOPSIS
  resolve-overlays.ps1 —— 确定性解析：本次分析应激活哪些险种 Overlay

.DESCRIPTION
  Lawgent Domain Overlay 模式的执行器部分。
  职责：把"analysis_scope / 目标类型 / 输入文本"确定性映射为"激活哪些 overlay"。
  不做语义理解，只做 scope / goal_type / keyword 匹配 —— 概率判断交给 Agent，
  "激活哪些险种"这类可枚举判定交给代码。

  用法：
    .\resolve-overlays.ps1 -Scope "life,critical_illness"
    .\resolve-overlays.ps1 -InputText "担心生大病和身故" -Scope "medical"
    .\resolve-overlays.ps1 -List
    .\resolve-overlays.ps1 -Scope "life" -OutputJsonPath out.json

  退出码：0 = 正常；1 = 未命中任何 overlay；2 = 结构错误
#>
[CmdletBinding()]
param(
    [string]$Scope          = "",
    [string]$InputText      = "",
    [switch]$IncludeDraft,
    [switch]$List,
    [string]$OutputJsonPath = ""
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$SkillDir = Split-Path -Parent $PSScriptRoot
$OvDir    = Join-Path $SkillDir "overlays"
if (-not (Test-Path -LiteralPath $OvDir)) {
    Write-Output "FATAL: overlays 目录不存在：$OvDir"
    exit 2
}

# ---------- 极简 YAML 解析（PS5.1 无 ConvertFrom-Yaml）----------
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

# ---------- 载入所有 overlay ----------
$overlays = @()
Get-ChildItem -LiteralPath $OvDir -Directory | Where-Object { $_.Name -ne '_template' } | ForEach-Object {
    $yp = Join-Path $_.FullName "overlay.yaml"
    if (-not (Test-Path -LiteralPath $yp)) { return }
    $y = Parse-OverlayYaml -Path $yp
    $pr = 0
    [int]::TryParse([string]($y['priority'] | Select-Object -First 1), [ref]$pr) | Out-Null
    $overlays += [pscustomobject]@{
        Id        = [string]$y['id']
        Name      = [string]$y['name']
        Status    = [string]$y['status']
        Priority  = $pr
        GoalTypes = @($y['goal_types'])
        Keywords  = @($y['keywords'])
        Dimensions= [string]$y['dimensions']
        DirName   = $_.Name
    }
}

if ($overlays.Count -eq 0) {
    Write-Output "FATAL: 未找到任何 overlay 定义"
    exit 2
}

# ---------- -List ----------
if ($List) {
    Write-Output "=== Overlay 清单（共 $($overlays.Count) 个）==="
    Write-Output ""
    foreach ($o in ($overlays | Sort-Object { -$_.Priority })) {
        $flag = if ($o.Status -eq 'active') { 'ACTIVE' } else { 'DRAFT ' }
        Write-Output ("[{0}] {1,-18} {2,-22} priority={3,-3} goal_types={4}" -f $flag, $o.Id, $o.Name, $o.Priority, ($o.GoalTypes -join ','))
    }
    Write-Output ""
    Write-Output "说明：draft 状态默认不激活，需 -IncludeDraft。"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Scope) -and [string]::IsNullOrWhiteSpace($InputText)) {
    Write-Output "FATAL: -Scope 与 -InputText 至少提供一个（或用 -List 查看清单）"
    exit 2
}

$scopeList = @()
if (-not [string]::IsNullOrWhiteSpace($Scope)) {
    $scopeList = @($Scope -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

# ---------- 匹配：scope 命中即激活；无 scope 时退回关键词 ----------
$candidates = @()
foreach ($o in $overlays) {
    if ($o.Status -ne 'active' -and -not $IncludeDraft) { continue }

    $hits = @()
    foreach ($s in $scopeList) {
        if ($o.GoalTypes -contains $s) { $hits += "scope:$s" }
    }
    if ([string]::IsNullOrWhiteSpace($Scope) -and -not [string]::IsNullOrWhiteSpace($InputText)) {
        foreach ($kw in $o.Keywords) {
            if ([string]::IsNullOrWhiteSpace($kw)) { continue }
            if ($InputText -match [regex]::Escape($kw)) { $hits += "keyword:$kw" }
        }
    }
    if ($hits.Count -eq 0) { continue }

    $candidates += [pscustomobject]@{
        id              = $o.Id
        name            = $o.Name
        priority        = $o.Priority
        status          = $o.Status
        hits            = $hits
        dimensions_file = ("overlays/" + $o.DirName + "/" + $o.Dimensions)
    }
}

$candidates = @($candidates | Sort-Object { -$_.priority })

Write-Output "=== Overlay 解析结果 ==="
Write-Output ("analysis_scope: [{0}] | 输入长度: {1} 字符" -f ($scopeList -join ','), $InputText.Length)
Write-Output ""

if ($candidates.Count -eq 0) {
    Write-Output "未命中任何 overlay —— 本次不产生任何险种需求结论（这是正常结果，不是错误）。"
    if ($OutputJsonPath) {
        $obj = [ordered]@{ scope = $scopeList; candidates = @(); active_ids = @() }
        [System.IO.File]::WriteAllText($OutputJsonPath, ($obj | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $true))
    }
    exit 1
}

foreach ($c in $candidates) {
    Write-Output ("[ACTIVE] {0,-18} {1,-22} priority={2,-3} hits={3}" -f $c.id, $c.name, $c.priority, ($c.hits -join ', '))
    Write-Output ("         维度文件: {0}" -f $c.dimensions_file)
}

Write-Output ""
Write-Output ("汇总: 命中 {0} 个 | 已激活 {1} 个" -f $candidates.Count, $candidates.Count)
Write-Output ""
Write-Output "下一步："
Write-Output "  1. 仅对 ACTIVE overlay 的需求类型执行分析"
Write-Output "  2. 各 overlay 的 analysis.* 规则由 invoke-requirement-analysis-analysis.ps1 消费"
Write-Output "  3. 未命中的险种一律不产出结论（防止凭空制造需求）"

if ($OutputJsonPath) {
    $obj = [ordered]@{
        scope       = $scopeList
        include_draft = [bool]$IncludeDraft
        candidates  = @($candidates)
        active_ids  = @($candidates | ForEach-Object { $_.id })
    }
    [System.IO.File]::WriteAllText($OutputJsonPath, ($obj | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $true))
    Write-Output ""
    Write-Output "JSON 已写入: $OutputJsonPath"
}

exit 0
