#Requires -Version 5.1
<#
    resolve-overlays.ps1 — 确定性解析：本次应激活哪些险种 Overlay

    Lawgent Domain Overlay 模式的执行器部分。
    职责：把"客户说了什么"确定性映射为"激活哪些 overlay"。
    不做任何语义理解，只做关键词/目标类型匹配 —— 概率判断交给 Agent，
    "要不要激活"这类可枚举的判定交给代码。

    用法：
      .resolve-overlays.ps1 -InputText "我想买个重疾险，怕生大病"
      .resolve-overlays.ps1 -InputText "..." -GoalTypes "critical_illness,medical"
      .resolve-overlays.ps1 -InputText "..." -ConfirmedIds "critical-illness"
      .resolve-overlays.ps1 -List
      .resolve-overlays.ps1 -InputText "..." -OutputJsonPath out.json

    退出码：0 = 正常；1 = 未命中任何 overlay；2 = 结构错误
#>
[CmdletBinding()]
param(
    [string]$InputText      = "",
    [string]$GoalTypes      = "",
    [string]$ConfirmedIds   = "",
    [switch]$IncludeDraft,
    [switch]$List,
    [string]$OutputJsonPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------- 路径 ----------
$SkillDir = Split-Path -Parent $PSScriptRoot
$OvDir    = Join-Path $SkillDir "overlays"
if (-not (Test-Path -LiteralPath $OvDir)) {
    Write-Output "FATAL: overlays 目录不存在：$OvDir"
    exit 2
}

# ---------- 极简 YAML 解析（PS5.1 无 ConvertFrom-Yaml）----------
# 支持：顶层 key: value / 顶层 key: + 缩进列表 / 缩进 key: + 更缩进列表
function Parse-OverlayYaml {
    param([string]$Path)

    $yaml = [ordered]@{}
    $cur  = $null

    foreach ($raw in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        # 跳过注释与空行
        $line = $raw -replace '#.*$', ''
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        if ($line -match '^(\S[^:]*):\s*(.*)$') {
            $k = $matches[1].Trim()
            $v = $matches[2].Trim()
            $cur = $k
            if ($v -eq '') { $yaml[$k] = @() } else { $yaml[$k] = $v }
            continue
        }

        if ($line -match '^\s+-\s*(.*)$') {
            if ($cur -ne $null) { $yaml[$cur] += @($matches[1].Trim()) }
            continue
        }

        if ($line -match '^\s+(\S[^:]*):\s*(.*)$') {
            $k = $matches[1].Trim()
            $v = $matches[2].Trim()
            $cur = $k
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
    $overlays += [pscustomobject]@{
        Id           = [string]$y['id']
        Name         = [string]$y['name']
        Status       = [string]$y['status']
        Priority     = [int]($y['priority'] | Select-Object -First 1)
        Keywords     = @($y['keywords'])
        GoalTypes    = @($y['goal_types'])
        RequiresConfirm = ([string]$y['requires_confirm']) -eq 'true'
        Dimensions   = [string]$y['dimensions']
        Dir          = $_.FullName
        DirName      = $_.Name
    }
}

if ($overlays.Count -eq 0) {
    Write-Output "FATAL: 未找到任何 overlay 定义"
    exit 2
}

# ---------- -List：列出全部 ----------
if ($List) {
    Write-Output "=== Overlay 清单（共 $($overlays.Count) 个）==="
    Write-Output ""
    foreach ($o in ($overlays | Sort-Object { -$_.Priority })) {
        $flag = if ($o.Status -eq 'active') { 'ACTIVE' } else { 'DRAFT ' }
        Write-Output ("[{0}] {1,-18} {2,-14} priority={3,-3} keywords={4}" -f $flag, $o.Id, $o.Name, $o.Priority, $o.Keywords.Count)
    }
    Write-Output ""
    Write-Output "说明：draft 状态默认不激活，需 -IncludeDraft。"
    exit 0
}

# ---------- 输入校验 ----------
if ([string]::IsNullOrWhiteSpace($InputText) -and [string]::IsNullOrWhiteSpace($GoalTypes)) {
    Write-Output "FATAL: -InputText 与 -GoalTypes 至少提供一个（或用 -List 查看清单）"
    exit 2
}

# ---------- 解析确认列表 ----------
$confirmed = @()
if (-not [string]::IsNullOrWhiteSpace($ConfirmedIds)) {
    $confirmed = @($ConfirmedIds -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

$goalList = @()
if (-not [string]::IsNullOrWhiteSpace($GoalTypes)) {
    $goalList = @($GoalTypes -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

# ---------- 匹配 ----------
$candidates = @()
foreach ($o in $overlays) {
    if ($o.Status -ne 'active' -and -not $IncludeDraft) { continue }

    $hits = @()
    foreach ($kw in $o.Keywords) {
        if ([string]::IsNullOrWhiteSpace($kw)) { continue }
        if ($InputText -match [regex]::Escape($kw)) { $hits += "keyword:$kw" }
    }
    foreach ($gt in $GoalTypes) {
        if ([string]::IsNullOrWhiteSpace($gt)) { continue }
        if ($o.GoalTypes -contains $gt) { $hits += "goal_type:$gt" }
    }
    if ($hits.Count -eq 0) { continue }

    $isConfirmed = $confirmed -contains $o.Id
    # requires_confirm=true 且未确认 → 维度不进入 required，只产生一条确认提问
    $state = if ($o.RequiresConfirm -and -not $isConfirmed) { 'PENDING_CONFIRM' } else { 'ACTIVE' }

    $candidates += [pscustomobject]@{
        id               = $o.Id
        name             = $o.Name
        priority         = $o.Priority
        status           = $o.Status
        state            = $state
        requires_confirm = $o.RequiresConfirm
        confirmed        = $isConfirmed
        hits             = $hits
        dimensions_file  = ("overlays/" + $o.DirName + "/" + $o.Dimensions)
    }
}

$candidates = @($candidates | Sort-Object { -$_.priority })

# ---------- 输出 ----------
Write-Output "=== Overlay 解析结果 ==="
Write-Output ("输入长度: {0} 字符 | 目标类型: [{1}] | 已确认: [{2}]" -f $InputText.Length, ($goalList -join ','), ($confirmed -join ','))
Write-Output ""

if ($candidates.Count -eq 0) {
    Write-Output "未命中任何 overlay —— 本次按通用层 H1-H6 采集，不追加险种专项维度。"
    Write-Output "(这是正常结果，不是错误：客户若未表达具体险种意向，不应凭空追问险种细节。)"
    if ($OutputJsonPath) {
        $obj = [ordered]@{
            input_length     = $InputText.Length
            goal_types       = $goalList
            confirmed_ids    = $confirmed
            candidates       = @()
            active_count     = 0
            pending_confirm  = @()
        }
        $enc = New-Object System.Text.UTF8Encoding $true
        [System.IO.File]::WriteAllText($OutputJsonPath, ($obj | ConvertTo-Json -Depth 6), $enc)
        Write-Output "JSON 已写入: $OutputJsonPath"
    }
    exit 1
}

foreach ($c in $candidates) {
    $tag = if ($c.state -eq 'ACTIVE') { 'ACTIVE' } else { 'PENDING_CONFIRM' }
    Write-Output ("[{0}] {1,-18} {2,-14} priority={3,-3} hits={4}" -f $tag, $c.id, $c.name, $c.priority, ($c.hits -join ', '))
    Write-Output ("     维度文件: {0}" -f $c.dimensions_file)
    if ($c.state -eq 'PENDING_CONFIRM') {
        Write-Output "     → 需先向客户确认是否纳入本次范围；确认前其维度不进入 required"
    }
}

Write-Output ""
$actives  = @($candidates | Where-Object { $_.state -eq 'ACTIVE' })
$pendings = @($candidates | Where-Object { $_.state -eq 'PENDING_CONFIRM' })
Write-Output ("汇总: 命中 {0} 个 | 已激活 {1} 个 | 待确认 {2} 个" -f $candidates.Count, $actives.Count, $pendings.Count)
Write-Output ""
Write-Output "下一步："
Write-Output "  1. 对 PENDING_CONFIRM 生成一条确认提问（占用 next_questions 配额，≤3 条）"
Write-Output "  2. 仅对 ACTIVE 的 overlay 加载对应 intake-dimensions.md"
Write-Output "  3. ACTIVE overlay 的 A 类维度并入 Step 5 Gap Analysis 与 Step 6 Completion Check"
Write-Output "  4. 未命中的险种一律不追问（防止信息轰炸）"

if ($OutputJsonPath) {
    $obj = [ordered]@{
        input_length    = $InputText.Length
        goal_types      = $goalList
        confirmed_ids   = $confirmed
        include_draft   = [bool]$IncludeDraft
        candidates      = @($candidates)
        active_ids      = @($actives  | ForEach-Object { $_.id })
        pending_confirm = @($pendings | ForEach-Object { $_.id })
    }
    $enc = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($OutputJsonPath, ($obj | ConvertTo-Json -Depth 6), $enc)
    Write-Output ""
    Write-Output "JSON 已写入: $OutputJsonPath"
}

exit 0
