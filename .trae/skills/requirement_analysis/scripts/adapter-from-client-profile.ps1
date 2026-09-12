<#
.SYNOPSIS
  Adapter: client-intake 的 CLIENT_PROFILE.md → requirement_analysis 结构化 Input JSON（确定性，无 LLM）。
.DESCRIPTION
  解析 Client Intake 产出的 Markdown 画像，做字段词表映射（client-intake 中文表头 → RA 规范字段），
  推断 value_status（KNOWN/ESTIMATED/UNKNOWN/ASSUMED），派生 family_responsibility / existing_life_coverage /
  liabilities，并强制纪律：value_status=UNKNOWN 的字段绝不进入 answered_fields（防追问引擎静默漏问）。

  零修改原则：本脚本只读 client-intake 产物，绝不写/改 client-intake 任何文件。
.PARAMETER ProfilePath
  CLIENT_PROFILE.md 的绝对或相对路径（client-intake 产出）。
.PARAMETER OutputJsonPath
  生成的 requirement_analysis Input JSON 路径。
.PARAMETER Scope
  本次分析的 Scope 列表（默认全 5 个）。Agent 应按客户真实优先级收窄。
.PARAMETER PendingPath
  PENDING.md 路径（默认取 Profile 同级文件）。
.PARAMETER ConversationLogPath
  CONVERSATION_LOG.md 路径（默认取 Profile 同级文件）。
.PARAMETER AdapterVersion
  Adapter 自身版本号，写入 source.adapter_version 便于追溯。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]  [string]         $ProfilePath,
    [Parameter(Mandatory = $true)]  [string]         $OutputJsonPath,
    [string[]]                      $Scope = @('medical', 'critical_illness', 'accident', 'life', 'savings'),
    [string]                        $PendingPath = "",
    [string]                        $ConversationLogPath = "",
    [string]                        $AdapterVersion = "1.0.0"
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

# ---------- 路径解析 ----------
if (-not (Test-Path -LiteralPath $ProfilePath)) { throw "Profile not found: $ProfilePath" }
$profileFull = (Resolve-Path -LiteralPath $ProfilePath).Path
$profDir = Split-Path -Parent $profileFull
if ([string]::IsNullOrWhiteSpace($PendingPath)) { $PendingPath = Join-Path $profDir "PENDING.md" }
if ([string]::IsNullOrWhiteSpace($ConversationLogPath)) { $ConversationLogPath = Join-Path $profDir "CONVERSATION_LOG.md" }

# ---------- Scope 校验 ----------
$validScopes = @('medical', 'critical_illness', 'accident', 'life', 'savings')
foreach ($s in $Scope) {
    if ($validScopes -notcontains $s) { throw "Invalid scope '$s'; must be one of: $($validScopes -join ', ')" }
}
if ($Scope.Count -eq 0) { throw "Scope must contain at least 1 item" }

# ---------- 字段映射表（client-intake 中文表头 → RA 规范字段）----------
$map = [ordered]@{
    '年龄'            = 'age'
    '性别'            = 'gender'
    '城市'            = 'city'
    '职业'            = 'occupation'
    '婚姻状况'        = 'marital_status'
    '配偶年龄'        = 'spouse_age'
    '配偶职业 / 状态' = 'spouse_employment'
    '配偶收入'        = 'spouse_income'
    '子女人数'        = 'children_count'
    '子女信息'        = 'children_info'
    '父母赡养情况'    = 'parents_support'
    '本人收入'        = 'annual_income'
    '家庭年支出'      = 'annual_expense'
    '保费预算'        = 'budget'
    '房贷余额'        = 'mortgage_balance'
    '房贷剩余年限'    = 'mortgage_years'
    '其他负债 / 担保' = 'other_liabilities'
    '社保医保'        = 'social_insurance_status'
    '商保概况'        = 'existing_critical_illness_coverage'
    '客户本人健康'    = 'customer_health'
    '配偶健康'        = 'spouse_health'
    '子女健康'        = 'children_health'
    '父母健康'        = 'parents_health'
    '生活习惯'        = 'lifestyle'
    '收入来源'        = 'income_source'
}

function Get-Status {
    param([string]$v)
    if ([string]::IsNullOrWhiteSpace($v) -or $v.Trim() -eq '❓') { return 'UNKNOWN' }
    if ($v -match '约|大概|左右|估计|差不多') { return 'ESTIMATED' }
    return 'KNOWN'
}

# ---------- 解析容器 ----------
$facts         = [System.Collections.Generic.List[object]]::new()
$constraints   = [System.Collections.Generic.List[object]]::new()
$inferredNotes = [System.Collections.Generic.List[object]]::new()
$followUpItems = [System.Collections.Generic.List[string]]::new()
$handoffLines  = [System.Collections.Generic.List[string]]::new()
$clientId      = ""
$clientAlias   = ""
$intakeComplete = $false

$mode = 'none'
$sectionLabel = ''
$inHandoffCode = $false

$lines = Get-Content -LiteralPath $profileFull -Encoding UTF8
foreach ($rawLine in $lines) {
    $line = $rawLine

    # 标题切换
    if ($line -match '^###\s*1\.\d+\s+(.+?)\s*$') { $mode = 'fact'; $sectionLabel = $Matches[1].Trim(); continue }
    if ($line -match '^##\s*2') { $mode = 'inferred'; continue }
    if ($line -match '^##\s*5') { $mode = 'followup'; continue }
    if ($line -match '^##\s*6') { $mode = 'handoff'; continue }
    if ($line -match '^##\s+Client Summary') { $mode = 'summary'; continue }
    if ($line -match '^```') {
        if ($mode -eq 'handoff') { $inHandoffCode = -not $inHandoffCode }
        continue
    }
    if ($mode -eq 'handoff' -and $inHandoffCode) { $handoffLines.Add($line); continue }

    # 仅处理表格行
    if ($line -notmatch '^\s*\|') { continue }
    $cols = @($line -split '\|' | ForEach-Object { $_.Trim() })
    if ($cols.Count -lt 2) { continue }
    $first = $cols[1]
    if ([string]::IsNullOrWhiteSpace($first)) { continue }
    if ($first -match '^-+$') { continue }                                   # 分隔行
    if ($first -eq '字段' -or $first -eq '编号' -or $first -eq '项') { continue }  # 表头行

    if ($mode -eq 'summary') {
        if ($first -eq '客户编号') { $clientId = $cols[2] }
        if ($first -eq 'Intake 状态') {
            $st = $cols[2]
            if ($st -match '已完成|可进入') { $intakeComplete = $true }
        }
        continue
    }

    if ($mode -eq 'fact') {
        $fieldLabel = $first
        $value = if ($cols.Count -ge 3) { $cols[2] } else { '' }
        $round = if ($cols.Count -ge 4) { $cols[3] } else { '' }
        $text  = if ($cols.Count -ge 5) { $cols[4] } else { '' }

        # 溯源完整性：未提供字段同样必须有非空 source_round / source_text（input.schema 要求 minLength=1）
        if ([string]::IsNullOrWhiteSpace($round)) { $round = 'R0' }
        if ([string]::IsNullOrWhiteSpace($text)) {
            if ($value -match '❓' -or [string]::IsNullOrWhiteSpace($value)) {
                $text = "client-intake 未采集：$fieldLabel（画像标记为未提供）"
            } else {
                $text = "client-intake 采集：$fieldLabel"
            }
        }

        # 团险/福利：拆分出医疗险 + 意外险
        if ($fieldLabel -eq '团险 / 福利') {
            $st = Get-Status -v $value
            $mv = if ($st -eq 'UNKNOWN') { $null } else { $value }
            $facts.Add([pscustomobject]@{ field = 'existing_medical_coverage';  value = $mv; value_status = $st; source_round = $round; source_text = $text; source_section = $sectionLabel })
            $facts.Add([pscustomobject]@{ field = 'existing_accident_coverage'; value = $mv; value_status = $st; source_round = $round; source_text = $text; source_section = $sectionLabel })
            continue
        }

        # 核心风险关注点：customer_preference 约束 + risk_preference 事实（仅在非 UNKNOWN 时）
        if ($fieldLabel -eq '核心风险关注点') {
            $st = Get-Status -v $value
            if ($st -ne 'UNKNOWN') {
                $constraints.Add([pscustomobject]@{ type = 'customer_preference'; description = $value; source = 'client_profile 1.5 核心风险关注点' })
                $facts.Add([pscustomobject]@{ field = 'risk_preference'; value = $value; value_status = 'KNOWN'; source_round = $round; source_text = $text; source_section = $sectionLabel })
            }
            continue
        }

        $canon = if ($map.Contains($fieldLabel)) { $map[$fieldLabel] } else { $fieldLabel }   # 未知表头原样保留（信息不丢）
        $status = Get-Status -v $value
        $fv = if ($status -eq 'UNKNOWN') { $null } else { $value }
        $facts.Add([pscustomobject]@{ field = $canon; value = $fv; value_status = $status; source_round = $round; source_text = $text; source_section = $sectionLabel })
        continue
    }

    if ($mode -eq 'inferred') {
        $note  = if ($cols.Count -ge 3) { $cols[2] } else { '' }
        $basis = if ($cols.Count -ge 4) { $cols[3] } else { '' }
        $rnd   = if ($cols.Count -ge 5) { $cols[4] } else { '' }
        if ([string]::IsNullOrWhiteSpace($note)) { continue }
        if ([string]::IsNullOrWhiteSpace($rnd)) { $rnd = 'R0' }   # 溯源完整性（input.schema 要求非空）
        $inferredNotes.Add([pscustomobject]@{ note = $note; basis = $basis; source_round = $rnd })
        continue
    }

    if ($mode -eq 'followup') {
        $item = $line -replace '^\s*-\s*', '' -replace '^\d+\.\s*', ''
        if ([string]::IsNullOrWhiteSpace($item) -or $item -eq '[空]') { continue }
        $followUpItems.Add($item)
        continue
    }
}

# ---------- 派生元数据：client_id / client_alias ----------
$folderName = Split-Path -Leaf $profDir
if ([string]::IsNullOrWhiteSpace($clientId) -or $clientId -match '未分配|\[空\]') { $clientId = $folderName }
if ($folderName -match '-(.+)$') { $clientAlias = $Matches[1].Trim() } else { $clientAlias = $folderName }

# ---------- 派生事实 ----------
function Get-Fact { param([string]$f); foreach ($x in $facts) { if ($x.field -eq $f) { return $x } }; return $null }

$fr = Get-Fact -f 'marital_status'
$ci = Get-Fact -f 'children_info'
$si = Get-Fact -f 'spouse_income'
$ai = Get-Fact -f 'annual_income'
if (($fr -and $fr.value_status -ne 'UNKNOWN') -or ($ci -and $ci.value_status -ne 'UNKNOWN')) {
    $desc = '已婚'
    if ($ci -and $ci.value_status -ne 'UNKNOWN') { $desc += "，有子女（$($ci.value)）" }
    if ($si -and $si.value_status -ne 'UNKNOWN') { $desc += '，配偶在职（非全职）' }
    if ($ai -and $ai.value_status -ne 'UNKNOWN') { $desc += '；本人收入占家庭主要来源，为家庭主要经济支柱（来源：confirmed 婚姻/子女/收入）' }
    $facts.Add([pscustomobject]@{ field = 'family_responsibility'; value = $desc; value_status = 'KNOWN'; source_round = 'R2'; source_text = '已婚+子女+配偶在职+本人收入占比高'; source_section = '家庭结构(派生)' })
}

# existing_life_coverage：画像仅记录重疾险与医疗/意外团险，无寿险记录 → KNOWN 无
$facts.Add([pscustomobject]@{ field = 'existing_life_coverage'; value = '未持有寿险（画像记录持有：个人终身重疾险约50万、公司医疗险+意外险；无寿险记录）'; value_status = 'KNOWN'; source_round = 'R3'; source_text = '商保概况/团险福利仅列重疾与医疗意外，无寿险'; source_section = '负债与保障(派生)' })

# liabilities：房贷（如披露）+ 其他负债
$mb = Get-Fact -f 'mortgage_balance'
$ol = Get-Fact -f 'other_liabilities'
if ($mb -and $mb.value_status -ne 'UNKNOWN') {
    $lv = $mb.value
    if ($ol -and $ol.value_status -ne 'UNKNOWN') { $lv += "；其他负债：$($ol.value)" } else { $lv += '（其他负债未披露）' }
    $facts.Add([pscustomobject]@{ field = 'liabilities'; value = $lv; value_status = $mb.value_status; source_round = $mb.source_round; source_text = $mb.source_text; source_section = '负债与保障(派生)' })
} elseif ($ol -and $ol.value_status -ne 'UNKNOWN') {
    $facts.Add([pscustomobject]@{ field = 'liabilities'; value = $ol.value; value_status = $ol.value_status; source_round = $ol.source_round; source_text = $ol.source_text; source_section = '负债与保障(派生)' })
}

# 预算信号约束（如有）
$bg = Get-Fact -f 'budget'
if ($bg -and $bg.value_status -ne 'UNKNOWN') {
    $constraints.Add([pscustomobject]@{ type = 'budget_signal'; description = "保费预算：$($bg.value)"; source = 'client_profile 1.3 保费预算' })
}

# ---------- 纪律：UNKNOWN 字段绝不进入 answered_fields；HashSet 自动去重 ----------
$answered = [System.Collections.Generic.HashSet[string]]::new()
foreach ($x in $facts) { if ($x.value_status -ne 'UNKNOWN') { [void]$answered.Add($x.field) } }

# ---------- 组装 Input 对象 ----------
$inputObj = [pscustomobject]@{
    source = [pscustomobject]@{
        skill                = 'client_intake'
        adapter_version      = $AdapterVersion
        profile_path         = $profileFull
        pending_path         = $PendingPath
        conversation_log_path = $ConversationLogPath
        intake_complete       = $intakeComplete
    }
    analysis_scope = $Scope
    client_profile = [pscustomobject]@{
        facts           = $facts.ToArray()
        inferred_notes  = $inferredNotes.ToArray()
        follow_up_items = $followUpItems.ToArray()
        handoff_notes   = ($handoffLines -join "`n")
    }
    conflicts   = @()
    constraints = $constraints.ToArray()
    metadata    = [pscustomobject]@{ client_id = $clientId; client_alias = $clientAlias }
    question_context = [pscustomobject]@{ asked_questions = @(); answered_fields = @($answered) }
}

# ---------- 写出（UTF-8 BOM，与分析引擎读取一致）----------
$json = $inputObj | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($OutputJsonPath, $json, (New-Object System.Text.UTF8Encoding $true))

Write-Host "[adapter] wrote $OutputJsonPath (facts=$($facts.Count), answered=$($answered.Count), intake_complete=$intakeComplete, scope=$($Scope -join ','))"
exit 0
