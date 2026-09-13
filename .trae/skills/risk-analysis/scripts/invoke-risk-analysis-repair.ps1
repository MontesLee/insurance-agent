# invoke-risk-analysis-repair.ps1
# Repair Loop 引擎（Phase 7）：Eval FAIL → 应用确定性修复 → 重评（≤2）→ 仍失败转 NEEDS_REVIEW。
# 红线：只做确定性重算与降级撤回；绝不发明事实、绝不清洗立场问题。
# 不调用 LLM。修复动作清单外置于 resources/config/repair.rules.json。

param(
    [string]$AnalysisJsonPath       = "",
    [string]$DiscoveryJsonPath      = "",
    [string]$EvalOutputJsonPath     = "",
    [string]$RepairedOutputJsonPath = "",
    [string]$RepairRulesPath        = "",
    [string]$ScoringRulesPath       = "",
    [string]$AntiSalesRulesPath     = "",
    [string]$EvalSchemaPath         = ""
)

# ----- PSScriptRoot 兜底（被 -File 调用时常见为空） -----
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrEmpty($AnalysisJsonPath))   { Write-Error "缺少 -AnalysisJsonPath"; exit 2 }
if ([string]::IsNullOrEmpty($EvalOutputJsonPath)) { Write-Error "缺少 -EvalOutputJsonPath"; exit 2 }

# ----- 路径解析（Join-Path 仅接受 2 参数） -----
$skillRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$cfgDir    = Join-Path $skillRoot (Join-Path "resources" "config")
$tmpDir    = Join-Path $skillRoot "tmp"

if ([string]::IsNullOrEmpty($RepairRulesPath))  { $RepairRulesPath  = Join-Path $cfgDir "repair.rules.json" }
if ([string]::IsNullOrEmpty($ScoringRulesPath)) { $ScoringRulesPath = Join-Path $cfgDir "risk-scoring.rules.json" }
if ([string]::IsNullOrEmpty($AntiSalesRulesPath)) { $AntiSalesRulesPath = Join-Path $cfgDir "anti-sales.rules.json" }
if ([string]::IsNullOrEmpty($EvalSchemaPath))   { $EvalSchemaPath   = Join-Path $skillRoot (Join-Path "schemas" "eval-result.schema.json") }
if ([string]::IsNullOrEmpty($RepairedOutputJsonPath)) { $RepairedOutputJsonPath = Join-Path $tmpDir "rp_work.json" }
if (-not (Test-Path -LiteralPath $tmpDir)) { New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null }

$evalEngine = Join-Path $PSScriptRoot "invoke-risk-analysis-eval.ps1"
if (-not (Test-Path -LiteralPath $evalEngine)) { Write-Error "找不到 Eval 引擎: $evalEngine"; exit 2 }

# ----- 工具函数（加载规则即需用到，故前置） -----
function Get-RpMember {
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

function Write-RpJson {
    param($Object, [string]$Path)
    $text = ($Object | ConvertTo-Json -Depth 20)
    [System.IO.File]::WriteAllText($Path, $text, [System.Text.UTF8Encoding]::new($false))
}

# ----- 加载规则 -----
$repRules = (Get-Content -LiteralPath $RepairRulesPath -Raw -Encoding UTF8 | ConvertFrom-Json)
$scRules  = (Get-Content -LiteralPath $ScoringRulesPath -Raw -Encoding UTF8 | ConvertFrom-Json)

$maxAttempts = 2
if ($null -ne (Get-RpMember -Object $repRules -Name "max_attempts")) { $maxAttempts = [int]$repRules.max_attempts }
$stopOnNoChange = $true
if ($null -ne (Get-RpMember -Object $repRules -Name "stop_on_no_change")) { $stopOnNoChange = [bool]$repRules.stop_on_no_change }

$actionsMap = Get-RpMember -Object $repRules -Name "actions"
if (-not $actionsMap) { Write-Error "repair.rules.json 缺少 actions"; exit 2 }

# ----- 档位 rank（与 analysis / eval 引擎一致） -----
$script:sevRank = @{ LOW = 1; MEDIUM = 2; HIGH = 3; CRITICAL = 4 }
$script:resRank = @{ LOW = 1; MEDIUM = 2; HIGH = 3; CRITICAL = 4 }
$script:likRank = @{ LOW = 1; MEDIUM = 2; HIGH = 3; UNKNOWN = 2 }
$script:priRank = @{ P3 = 3; P2 = 2; P1 = 1; P0 = 0 }

# ----- 修复动作函数 -----
function Invoke-RpEval {
    param([string]$AnalysisPath, [string]$OutPath)
    if (Test-Path -LiteralPath $OutPath) { [System.IO.File]::Delete($OutPath) }
    $p = @{ AnalysisJsonPath = $AnalysisPath; OutputJsonPath = $OutPath;
            AntiSalesRulesPath = $AntiSalesRulesPath; ScoringRulesPath = $ScoringRulesPath }
    if (-not [string]::IsNullOrEmpty($DiscoveryJsonPath)) { $p.DiscoveryJsonPath = $DiscoveryJsonPath }
    & $evalEngine @p | Out-Null
    if (-not (Test-Path -LiteralPath $OutPath)) { throw "Eval 引擎未产出结果: $OutPath" }
    return (Get-Content -LiteralPath $OutPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-RpRiskExists {
    param($Risk)
    $v = Get-RpMember -Object $Risk -Name "risk_exists"
    if ($null -eq $v) { return $true }
    return [bool]$v
}

# 由 issue code + risk 状态决定 action_id；无法判定返回 $null
function Resolve-RpAction {
    param($Issue, $Risk)
    $code = [string](Get-RpMember -Object $Issue -Name "code")
    switch ($code) {
        'LOGICAL_INCONSISTENCY' {
            if ($null -eq $Risk) { return $null }
            if (-not (Get-RpRiskExists $Risk)) { return 'CLAMP_NOT_IDENTIFIED_BANDS' }
            return 'RECOMPUTE_RESIDUAL'
        }
        'PRIORITY_INCONSISTENT' {
            if ($null -eq $Risk) { return $null }
            return 'RECOMPUTE_PRIORITY'
        }
        'UNSUPPORTED_CONCLUSION' {
            if ($null -eq $Risk) { return 'ESCALATE_UNSUPPORTED' }
            $d = Get-RpDangling -Risk $Risk
            if ($d.dangling.Count -gt 0 -and $d.kept.Count -ge 1) { return 'DROP_DANGLING_REFS' }
            return 'ESCALATE_UNSUPPORTED'
        }
        'MISSING_RISK'                  { return 'ESCALATE_MISSING_RISK' }
        'UNKNOWN_AS_KNOWN'              { return 'ESCALATE_UNKNOWN_AS_KNOWN' }
        'SALES_BIAS'                    { return 'ESCALATE_SALES_BIAS' }
        'PRODUCT_RECOMMENDATION_LEAK'   { return 'ESCALATE_PRODUCT_LEAK' }
        'INVALID_OUTPUT'                { return 'ESCALATE_INVALID_OUTPUT' }
    }
    return $null
}

function Get-RpDangling {
    param($Risk)
    $evIds = @{}
    foreach ($e in @(Get-RpMember -Object $Risk -Name "evidence")) {
        $eid = [string](Get-RpMember -Object $e -Name "evidence_id")
        if (-not [string]::IsNullOrWhiteSpace($eid)) { $evIds[$eid] = 1 }
    }
    $kept = @(); $dangling = @()
    foreach ($rs in @(Get-RpMember -Object $Risk -Name "reasoning_evidence_refs")) {
        $s = [string]$rs
        if ($s -match '^E[0-9]{3}$') {
            if ($evIds.ContainsKey($s)) { $kept += $s } else { $dangling += $s }
        } else {
            $kept += $s   # REQ-### 为跨 Skill 引用，不做本地校验、不删
        }
    }
    return @{ kept = $kept; dangling = $dangling }
}

# 返回 $true 表示产物确实被改变
function Invoke-RpAction {
    param([string]$ActionId, $Risk)
    switch ($ActionId) {

        'CLAMP_NOT_IDENTIFIED_BANDS' {
            $changed = $false
            if ([string]$Risk.severity      -ne 'LOW') { $Risk.severity = 'LOW'; $changed = $true }
            if ([string]$Risk.residual_risk -ne 'LOW') { $Risk.residual_risk = 'LOW'; $changed = $true }
            if ([string]$Risk.priority      -ne 'P3')  { $Risk.priority = 'P3'; $changed = $true }
            return $changed
        }

        'RECOMPUTE_RESIDUAL' {
            $sev = [string]$Risk.severity; $lik = [string]$Risk.likelihood; $res = [string]$Risk.residual_risk
            if (-not $script:sevRank.ContainsKey($sev)) { return $false }
            if (-not $script:likRank.ContainsKey($lik)) { return $false }
            $wSev = [double](Get-RpMember -Object (Get-RpMember -Object $scRules -Name "residual_weights") -Name "severity")
            $wLik = [double](Get-RpMember -Object (Get-RpMember -Object $scRules -Name "residual_weights") -Name "likelihood")
            $thr  = Get-RpMember -Object $scRules -Name "residual_thresholds"
            $score = ([double]$script:sevRank[$sev]) * $wSev + ([double]$script:likRank[$lik]) * $wLik
            $exp = 'LOW'
            if ($score -ge [double](Get-RpMember -Object $thr -Name "CRITICAL"))      { $exp = 'CRITICAL' }
            elseif ($score -ge [double](Get-RpMember -Object $thr -Name "HIGH"))      { $exp = 'HIGH' }
            elseif ($score -ge [double](Get-RpMember -Object $thr -Name "MEDIUM"))    { $exp = 'MEDIUM' }
            if ($exp -ne $res) { $Risk.residual_risk = $exp; return $true }
            return $false
        }

        'RECOMPUTE_PRIORITY' {
            $sev = [string]$Risk.severity; $lik = [string]$Risk.likelihood
            $res = [string]$Risk.residual_risk; $cat = [string]$Risk.risk_category
            $prio = [string](Get-RpMember -Object (Get-RpMember -Object (Get-RpMember -Object $scRules -Name "priority_matrix") -Name $sev) -Name $lik)
            if ([string]::IsNullOrWhiteSpace($prio)) { return $false }
            $exists = Get-RpRiskExists $Risk
            foreach ($ov in @(Get-RpMember -Object $scRules -Name "priority_overrides")) {
                $ovEnabledProp = Get-RpMember -Object $ov -Name 'enabled'
                if ($null -eq $ovEnabledProp) { throw "priority_overrides 项 '$(Get-RpMember -Object $ov -Name 'id')' 缺 enabled 字段（禁止隐式启用）" }
                if ([string]$ovEnabledProp -eq 'False') { continue }
                $if = Get-RpMember -Object $ov -Name 'if'
                $match = $true
                if ($null -ne (Get-RpMember -Object $if -Name 'category'))   { if ([string]$if.category   -ne $cat)   { $match = $false } }
                if ($null -ne (Get-RpMember -Object $if -Name 'residual'))   { if ([string]$if.residual   -ne $res)   { $match = $false } }
                if ($null -ne (Get-RpMember -Object $if -Name 'likelihood')) { if ([string]$if.likelihood -ne $lik)   { $match = $false } }
                if ($null -ne (Get-RpMember -Object $if -Name 'risk_exists')) {
                    $want = if ([string]$if.risk_exists -eq 'false') { $false } else { $true }
                    if ($want -ne $exists) { $match = $false }
                }
                if ($match) {
                    if ($null -ne (Get-RpMember -Object $ov -Name 'max_priority')) {
                        $cur = [int]$script:priRank[$prio]; $mx = [int]$script:priRank[[string]$ov.max_priority]
                        if ($cur -lt $mx) { $prio = [string]$ov.max_priority }
                    }
                    if ($null -ne (Get-RpMember -Object $ov -Name 'min_priority')) {
                        $cur = [int]$script:priRank[$prio]; $mn = [int]$script:priRank[[string]$ov.min_priority]
                        # rank 越小越紧急：「至少 P_mn」= 当前更不紧急（rank 更大）时收紧
                        if ($cur -gt $mn) { $prio = [string]$ov.min_priority }
                    }
                }
            }
            if ($prio -ne [string]$Risk.priority) { $Risk.priority = $prio; return $true }
            return $false
        }

        'DROP_DANGLING_REFS' {
            $d = Get-RpDangling -Risk $Risk
            if ($d.dangling.Count -eq 0 -or $d.kept.Count -lt 1) { return $false }
            $Risk.reasoning_evidence_refs = @($d.kept)
            return $true
        }
    }
    return $false
}

# ------------------------------------------------------------------ 主循环
$A = (Get-Content -LiteralPath $AnalysisJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json)
Write-RpJson -Object $A -Path $RepairedOutputJsonPath
$evalTmp = Join-Path $tmpDir "rp_eval_tmp.json"

$attempt  = 0
$repairRequired = $false
$repairLog = @()

$eval = Invoke-RpEval -AnalysisPath $RepairedOutputJsonPath -OutPath $evalTmp

while ([string]$eval.eval_status -eq 'FAIL' -and $attempt -lt $maxAttempts) {
    $repairRequired = $true
    $blocking = @(Get-RpMember -Object $eval -Name "failures")
    if ($blocking.Count -eq 0) { break }

    # risk_id → risk 对象
    $riskById = @{}
    foreach ($r in @(Get-RpMember -Object $A -Name "risks")) {
        $rid = [string](Get-RpMember -Object $r -Name "risk_id")
        if (-not [string]::IsNullOrWhiteSpace($rid)) { $riskById[$rid] = $r }
    }

    # 解析动作：只保留 AUTO
    $autoActions = @{}
    $codesSeen   = @{}
    $appliedIds  = @()
    foreach ($i in $blocking) {
        $code = [string](Get-RpMember -Object $i -Name "code")
        $codesSeen[$code] = 1
        $rid = [string](Get-RpMember -Object $i -Name "risk_id")
        $risk = $null
        if (-not [string]::IsNullOrWhiteSpace($rid) -and $riskById.ContainsKey($rid)) { $risk = $riskById[$rid] }
        $aid = Resolve-RpAction -Issue $i -Risk $risk
        if ([string]::IsNullOrWhiteSpace($aid)) { continue }
        $cfg = Get-RpMember -Object $actionsMap -Name $aid
        $mode = if ($cfg) { [string](Get-RpMember -Object $cfg -Name "mode") } else { "REVIEW" }
        if ($mode -ne 'AUTO') { continue }
        $key = "$aid|$rid"
        if (-not $autoActions.ContainsKey($key)) { $autoActions[$key] = @{ action = $aid; risk = $risk } }
    }

    if ($autoActions.Count -eq 0) { break }   # 无可安全修复 → 不空转

    # 应用修复
    $before = [System.IO.File]::ReadAllText($RepairedOutputJsonPath)
    foreach ($k in @($autoActions.Keys)) {
        $item = $autoActions[$k]
        if ($null -eq $item.risk) { continue }
        $null = Invoke-RpAction -ActionId $item.action -Risk $item.risk
        $appliedIds += $item.action
    }
    Write-RpJson -Object $A -Path $RepairedOutputJsonPath
    $after = [System.IO.File]::ReadAllText($RepairedOutputJsonPath)

    if ($stopOnNoChange -and $before -eq $after) { break }   # 确定性修复的不动点

    $attempt++
    $codes = @($codesSeen.Keys)
    $actText = (@($appliedIds | Sort-Object -Unique)) -join ", "
    $repairLog += [pscustomobject][ordered]@{
        attempt      = $attempt
        failed_codes = @($codes)
        action       = $actText
    }

    $eval = Invoke-RpEval -AnalysisPath $RepairedOutputJsonPath -OutPath $evalTmp
}

# ------------------------------------------------------------------ 收尾
$finalStatus = [string]$eval.eval_status
if ($finalStatus -eq 'FAIL') {
    $finalStatus = 'NEEDS_REVIEW'
    $blocking = @(Get-RpMember -Object $eval -Name "failures")
    $codeList = @()
    $reasonList = @()
    $seenR = @{}
    foreach ($i in $blocking) {
        $code = [string](Get-RpMember -Object $i -Name "code")
        $rid  = [string](Get-RpMember -Object $i -Name "risk_id")
        $codeList += $(if ([string]::IsNullOrWhiteSpace($rid)) { $code } else { "$code($rid)" })
        # 反查该 code 对应的 review_reason
        if (-not $seenR.ContainsKey($code)) {
            $seenR[$code] = 1
            $reason = ""
            foreach ($an in @($actionsMap.PSObject.Properties.Name)) {
                $cfg = Get-RpMember -Object $actionsMap -Name $an
                $cs = @(Get-RpMember -Object $cfg -Name "codes")
                if ($cs -contains $code) {
                    $rr = [string](Get-RpMember -Object $cfg -Name "review_reason")
                    if (-not [string]::IsNullOrWhiteSpace($rr)) { $reason = $rr; break }
                }
            }
            $reason = [string]$reason -replace '[。.]+$', ''
            if (-not [string]::IsNullOrWhiteSpace($reason)) { $reasonList += "$code：$reason" }
        }
    }
    $tpl  = [string](Get-RpMember -Object $repRules -Name "needs_review_note_template")
    $ask  = [string](Get-RpMember -Object $repRules -Name "needs_review_ask")
    if ([string]::IsNullOrWhiteSpace($tpl)) { $tpl = "Repair Loop 未能收敛（attempts={attempts}/{max}）。剩余 BLOCKING：{codes}。无法可靠判断项：{reasons}。需人工确认：{ask}" }
    if ([string]::IsNullOrWhiteSpace($ask)) { $ask = "逐项确认是补充事实、撤回结论，还是调整判定规则。" }
    $note = $tpl.Replace('{attempts}', [string]$attempt).Replace('{max}', [string]$maxAttempts).
                 Replace('{codes}', (($codeList | Sort-Object -Unique) -join ", ")).
                 Replace('{reasons}', ($reasonList -join " ")).
                 Replace('{ask}', $ask)
    $eval | Add-Member -MemberType NoteProperty -Name "needs_review_note" -Value $note -Force
} else {
    if ($null -ne (Get-RpMember -Object $eval -Name "needs_review_note")) {
        $eval.PSObject.Properties.Remove('needs_review_note')
    }
}

$eval.eval_status     = $finalStatus
$eval.repair_required = $repairRequired
$eval.repair_attempts = $attempt
$eval | Add-Member -MemberType NoteProperty -Name "repair_log" -Value @($repairLog) -Force

Write-RpJson -Object $eval -Path $EvalOutputJsonPath

exit 0
