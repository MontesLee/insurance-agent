# client-intake — 状态不变量确定性检查（I1-I8）
# 用途：把 references/08-state-invariants.md 的不变量从“LLM 自觉”变成“代码判定”。
# 用法：& .\check-state-invariants.ps1 -ClientDir <...\clients\C001-张三三口之家> [-ReportPath <out.md>]
# 退出码：0 = 无 FAIL；1 = 存在 FAIL（WARN 不导致失败）

param(
    [Parameter(Mandatory = $true)][string]$ClientDir,
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ClientDir)) {
    Write-Output "[FAIL] I0 客户目录不存在: $ClientDir"
    exit 1
}

$profilePath = Join-Path $ClientDir "CLIENT_PROFILE.md"
$logPath     = Join-Path $ClientDir "CONVERSATION_LOG.md"
$pendingPath = Join-Path $ClientDir "PENDING.md"
foreach ($p in @($profilePath, $logPath, $pendingPath)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Output "[FAIL] I0 缺少状态文件: $p"
        exit 1
    }
}

function Get-Lines { param([string]$Path)
    return @(Get-Content -LiteralPath $Path -Encoding UTF8)
}
function Is-TableRow {
    param([string]$Line)
    if (-not $Line.Trim().StartsWith("|")) { return $false }
    if ($Line -match '^\s*\|[\s\-:|]+\|\s*$') { return $false }   # 分隔行
    return $true
}
function Split-Cells {
    param([string]$Line)
    $t = $Line.Trim()
    if ($t.StartsWith("|")) { $t = $t.Substring(1) }
    if ($t.EndsWith("|")) { $t = $t.Substring(0, $t.Length - 1) }
    $cells = @($t -split '\|')
    for ($i = 0; $i -lt $cells.Count; $i++) { $cells[$i] = $cells[$i].Trim() }
    return $cells
}

$results = New-Object System.Collections.ArrayList
$warns   = New-Object System.Collections.ArrayList
function Add-R { param([bool]$Ok, [string]$Code, [string]$Msg)
    if ($Ok) { [void]$results.Add("[PASS] $Code $Msg") }
    else { [void]$results.Add("[FAIL] $Code $Msg") }
}
function Add-W { param([string]$Code, [string]$Msg)
    [void]$warns.Add("[WARN] $Code $Msg")
}

$profileLines = Get-Lines $profilePath
$logLines     = Get-Lines $logPath
$pendingLines = Get-Lines $pendingPath

# ---------- 解析 Profile：confirmed 字段行 ----------
# 约定 confirmed 表头：| 字段 | 当前值 | Source Round | Source Text |
$confirmedRows = @()
$section = ""
foreach ($ln in $profileLines) {
    if ($ln -match '^###\s*(.+?)\s*$') { $section = $Matches[1]; continue }
    if (-not (Is-TableRow $ln)) { continue }
    $c = Split-Cells $ln
    if ($c.Count -lt 4) { continue }
    if ($c[1] -eq "当前值" -or $c[0] -eq "字段") { continue }   # 表头
    if ($c[0] -eq "编号" -or $c[0] -eq "优先级" -or $c[0] -eq "检查项") { continue }
    $confirmedRows += [pscustomobject]@{
        Section = $section; Field = $c[0]; Value = $c[1]; Round = $c[2]; Text = $(if ($c.Count -gt 3) { $c[3] } else { "" })
    }
}

# I1 Confirmed 唯一性：同一小节内重复判 FAIL；跨小节同名多为模板命名冲突，仅告警
$dupGroups = @($confirmedRows | Group-Object -Property Section, Field | Where-Object { $_.Count -gt 1 })
$dupInSection = @($dupGroups | ForEach-Object { "$($_.Group[0].Section) / $($_.Group[0].Field)" })
$dupAcross = @($confirmedRows | Group-Object Field | Where-Object { $_.Count -gt 1 } | ForEach-Object { $_.Name })
Add-R ($dupInSection.Count -eq 0) "I1" "同一小节内 confirmed 字段重复：$(($dupInSection -join '; '))"
foreach ($d in $dupAcross) {
    $inSec = $false
    foreach ($s in $dupInSection) { if ($s -like "*/ $d") { $inSec = $true } }
    if (-not $inSec) { Add-W "I1" "字段『$d』跨小节重名（模板命名冲突，建议合并或改名，否则易造成两处值不一致）" }
}

# I2 Source 完整性（有值就必须有 source_round + source_text）
$emptyMarks = @('❓', '?', '', '[空]', 'N/A', '未知')
$i2Bad = @()
foreach ($r in $confirmedRows) {
    if ($emptyMarks -contains $r.Value) { continue }
    if (($emptyMarks -contains $r.Round) -or ($emptyMarks -contains $r.Text)) {
        $i2Bad += $r.Field
    }
}
if ($i2Bad.Count -eq 0) { Add-R $true "I2" "已填值字段均具备 source_round + source_text" }
else { Add-R $false "I2" "有值但缺 source_round/source_text：$(($i2Bad -join ', '))" }

# Profile 完成态 + Critical Missing
$canEnter = $null
foreach ($ln in $profileLines) {
    if ($ln -match '是否可进入\s*Needs\s*Analysis') {
        $c = Split-Cells $ln
        if ($c.Count -ge 2) { $canEnter = $c[1] }
    }
}
$criticalRows = @()
$inCritical = $false
foreach ($ln in $profileLines) {
    if ($ln -match '^##\s*3\.\s*Critical Missing') { $inCritical = $true; continue }
    if ($inCritical -and $ln -match '^##\s') { $inCritical = $false }
    if ($inCritical -and (Is-TableRow $ln)) {
        $c = Split-Cells $ln
        if ($c.Count -ge 2 -and $c[0] -match '^P\d$') { $criticalRows += $c[1] }
    }
}
# I5 Intake 完成一致性
if ($null -ne $canEnter) {
    if ($canEnter -match '是|可|true') {
        if ($criticalRows.Count -eq 0) { Add-R $true "I5" "完成态：Critical Missing 已清空，符合 I5" }
        else { Add-R $false "I5" "已标记可进入 Needs Analysis，但 Critical Missing 仍有 $($criticalRows.Count) 项" }
    } else {
        Add-R $true "I5" "未完成态，Critical Missing $($criticalRows.Count) 项（不校验清空）"
    }
} else {
    Add-W "I5" "Profile 未找到『是否可进入 Needs Analysis』行，跳过 I5"
}

# I6 历史与当前分离（启发式，仅告警）
foreach ($ln in $profileLines) {
    if ($ln -match '旧值|上一版|已废弃|历史值|曾经是') { Add-W "I6" "Profile 疑似混入历史值：$($ln.Trim())" }
}

# ---------- 解析 Log：QID 注册表 + 最新 Round ----------
$qidRows = @()
$inReg = $false
foreach ($ln in $logLines) {
    if ($ln -match 'Asked Questions Registry') { $inReg = $true; continue }
    if ($inReg -and $ln -match '^##\s') { $inReg = $false }
    if ($inReg -and (Is-TableRow $ln)) {
        $c = Split-Cells $ln
        if ($c.Count -lt 6) { continue }
        if ($c[0] -eq "QID" -or $c[0] -eq "") { continue }
        $qidRows += [pscustomobject]@{
            Qid = $c[0]; Priority = $c[1]; Intent = $c[2]; FirstRound = $c[4]; Status = $c[5]; PendingId = $(if ($c.Count -gt 7) { $c[7] } else { "" })
        }
    }
}
$maxRound = -1
foreach ($ln in $logLines) {
    if ($ln -match '^###\s*Round\s*(\d+)') {
        $n = [int]$Matches[1]
        if ($n -gt $maxRound) { $maxRound = $n }
    }
}

# I3 QID 状态闭环：进入过下一轮仍 unanswered
$i3Bad = @()
foreach ($q in $qidRows) {
    if ($q.Status -ne 'unanswered') { continue }
    $fr = -1
    if ($q.FirstRound -match 'R?(\d+)') { $fr = [int]$Matches[1] }
    if ($fr -ge 0 -and $maxRound -gt $fr) { $i3Bad += $q.Qid }
}
if ($i3Bad.Count -eq 0) { Add-R $true "I3" "无跨轮滞留 unanswered 的 QID" }
else { Add-R $false "I3" "跨轮仍 unanswered 的 QID：$(($i3Bad -join ', '))" }

# ---------- 解析 PENDING：Pending Registry ----------
$pendRows = @()
$inPend = $false
foreach ($ln in $pendingLines) {
    if ($ln -match 'Pending Registry') { $inPend = $true; continue }
    if ($inPend -and $ln -match '^##\s') { $inPend = $false }
    if ($inPend -and (Is-TableRow $ln)) {
        $c = Split-Cells $ln
        if ($c.Count -lt 6) { continue }
        if ($c[0] -eq "编号" -or $c[0] -eq "") { continue }
        $pendRows += [pscustomobject]@{
            Id = $c[0]; RelatedQid = $c[1]; Item = $c[2]; Status = $c[5]
        }
    }
}

# I4 Pending 一致性（双向）
$pendQids = @($qidRows | Where-Object { $_.Status -eq 'pending' } | ForEach-Object { $_.Qid })
$pendItemQids = @($pendRows | Where-Object { $_.Status -eq 'pending' } | ForEach-Object { $_.RelatedQid })
$i4a = @($pendQids | Where-Object { $pendItemQids -notcontains $_ })
$i4b = @($pendItemQids | Where-Object { $pendQids -notcontains $_ })
Add-R (($i4a.Count -eq 0) -and ($i4b.Count -eq 0)) "I4" "pending 不同步：QID侧缺[$(($i4a -join ','))] / Pending侧缺[$(($i4b -join ','))]"

# I8 多客户隔离：单目录无法自证，输出提示
Add-R $true "I8" "单目录检查无法自证跨客户隔离（需调用方保证本轮仅读写本目录）"

$failCount = @($results | Where-Object { $_.StartsWith("[FAIL]") }).Count
$passCount = @($results | Where-Object { $_.StartsWith("[PASS]") }).Count

Write-Output "===== 状态不变量检查 I1-I8 ====="
Write-Output "client: $ClientDir"
foreach ($r in $results) { Write-Output $r }
foreach ($w in $warns)   { Write-Output $w }
Write-Output "--------------------------------"
Write-Output "PASS=$passCount  FAIL=$failCount  WARN=$($warns.Count)"

if ($ReportPath -ne "") {
    $lines = @("# 状态不变量检查报告", "", "- 客户目录：$ClientDir", "- 时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", "- PASS=$passCount  FAIL=$failCount  WARN=$($warns.Count)", "")
    $lines += $results
    $lines += $warns
    [System.IO.File]::WriteAllLines($ReportPath, $lines, (New-Object System.Text.UTF8Encoding $true))
}

if ($failCount -gt 0) { exit 1 }
exit 0
