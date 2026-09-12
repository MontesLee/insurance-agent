# invoke-risk-analysis-eval.ps1
# 独立 Eval 引擎（Phase 6）：对 RiskAnalysisOutput 跑 7 项确定性机检。
# 输入：分析阶段产物 JSON + 反销售词典（anti-sales.rules.json）
# 输出：EvalResult JSON（对齐 eval-result.schema.json）
# 不调用 LLM。所有判定确定性、可复现。

param(
    [string]$AnalysisJsonPath = "",
    [string]$DiscoveryJsonPath = "",
    [string]$OutputJsonPath   = "",
    [string]$AntiSalesRulesPath = "",
    [string]$ScoringRulesPath = "",
    [string]$EvalSchemaPath   = "",
    [switch]$PatchOutput
)

# ----- PSScriptRoot 兜底（被 -File 调用时常见为空） -----
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

# ----- 路径解析（Join-Path 仅接受 2 参数） -----
if ([string]::IsNullOrEmpty($AnalysisJsonPath)) { Write-Error "缺少 -AnalysisJsonPath"; exit 2 }
if ([string]::IsNullOrEmpty($OutputJsonPath))   { Write-Error "缺少 -OutputJsonPath"; exit 2 }

$skillRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrEmpty($AntiSalesRulesPath)) {
    $AntiSalesRulesPath = Join-Path (Join-Path $skillRoot "resources") (Join-Path "config" "anti-sales.rules.json")
}
if ([string]::IsNullOrEmpty($ScoringRulesPath)) {
    $ScoringRulesPath = Join-Path (Join-Path $skillRoot "resources") (Join-Path "config" "risk-scoring.rules.json")
}
if ([string]::IsNullOrEmpty($EvalSchemaPath)) {
    $EvalSchemaPath = Join-Path $skillRoot (Join-Path "schemas" "eval-result.schema.json")
}

# ----- 档位 rank 映射（schema 枚举，稳定，内置于引擎） -----
$script:sevRank = @{ LOW = 1; MEDIUM = 2; HIGH = 3; CRITICAL = 4 }
$script:resRank = @{ LOW = 1; MEDIUM = 2; HIGH = 3; CRITICAL = 4 }
$script:likRank = @{ LOW = 1; MEDIUM = 2; HIGH = 3; UNKNOWN = 2 }
$script:priRank = @{ P3 = 3; P2 = 2; P1 = 1; P0 = 0 }
$script:validCats = @{ R1 = 1; R2 = 1; R3 = 1; R4 = 1; R5 = 1 }
$script:validSev  = @{ LOW = 1; MEDIUM = 1; HIGH = 1; CRITICAL = 1 }
$script:validRes  = @{ LOW = 1; MEDIUM = 1; HIGH = 1; CRITICAL = 1 }
$script:validLik  = @{ LOW = 1; MEDIUM = 1; HIGH = 1; UNKNOWN = 1 }
$script:validPri  = @{ P0 = 1; P1 = 1; P2 = 1; P3 = 1 }

# ----- 工具函数 -----
function Get-RaText {
    param($Risk)
    $parts = @()
    if ($Risk.reasoning)               { $parts += [string]$Risk.reasoning }
    if ($Risk.conclusion)              { $parts += [string]$Risk.conclusion }
    if ($Risk.trigger -and $Risk.trigger.event)               { $parts += [string]$Risk.trigger.event }
    if ($Risk.exposure -and $Risk.exposure.why_exposed)       { $parts += [string]$Risk.exposure.why_exposed }
    if ($Risk.existing_protection)     { $parts += [string]$Risk.existing_protection }
    if ($Risk.potential_impact) {
        if ($Risk.potential_impact.financial)            { $parts += [string]$Risk.potential_impact.financial }
        if ($Risk.potential_impact.lifestyle)            { $parts += [string]$Risk.potential_impact.lifestyle }
        if ($Risk.potential_impact.family_responsibility){ $parts += [string]$Risk.potential_impact.family_responsibility }
    }
    return ($parts -join " ")
}

function Test-RaHasToken {
    param([string]$Text, $Tokens, [bool]$IgnoreCase = $true)
    if ([string]::IsNullOrEmpty($Text)) { return $false }
    $lower = $Text.ToLower()
    foreach ($t in $Tokens) {
        if ($IgnoreCase) {
            if ($lower.Contains($t.ToLower())) { return $true }
        } else {
            if ($Text.Contains($t)) { return $true }
        }
    }
    return $false
}

function Get-RaRank {
    param($Map, $Val)
    if ($null -eq $Val) { return 0 }
    $v = [string]$Val
    if ($Map.ContainsKey($v)) { return $Map[$v] }
    return 0
}

function New-RaIssue {
    param([string]$Code, [string]$Severity, [string]$RiskId, [string]$Message, [string]$Evidence)
    $o = [ordered]@{ code = $Code; severity = $Severity; risk_id = $RiskId; message = $Message }
    if (-not [string]::IsNullOrEmpty($Evidence)) { $o.evidence = $Evidence }
    return [pscustomobject]$o
}

function New-RaCheck {
    param([string]$Status, [double]$Score, $Issues, [string]$Note)
    $o = [ordered]@{ status = $Status; score = $Score; issues = $Issues }
    if (-not [string]::IsNullOrEmpty($Note)) { $o.note = $Note }
    return [pscustomobject]$o
}

function Get-RaMember {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }
    return $null
}

# ----- 载入 -----
$A = (Get-Content -LiteralPath $AnalysisJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json)
$asRules = (Get-Content -LiteralPath $AntiSalesRulesPath -Raw -Encoding UTF8 | ConvertFrom-Json)
$scorRules = (Get-Content -LiteralPath $ScoringRulesPath -Raw -Encoding UTF8 | ConvertFrom-Json)
$resThr = Get-RaMember -Object $scorRules -Name "residual_thresholds"
$resW = Get-RaMember -Object $scorRules -Name "residual_weights"
if (-not $resThr -or -not $resW) { Write-Error "scoring rules 缺少 residual_thresholds / residual_weights"; exit 2 }

$panicTokens  = @(Get-RaMember -Object $asRules -Name "panic_tokens")
$exagTokens   = @(Get-RaMember -Object $asRules -Name "exaggeration_tokens")
$salesVerbs   = @(Get-RaMember -Object $asRules -Name "sales_verbs")
$prodNames    = @(Get-RaMember -Object $asRules -Name "product_names")
$asRulesMap   = Get-RaMember -Object $asRules -Name "rules"
$panicBlocking = $true; $exagWarning = $true; $leakNeedsVerb = $true; $ignoreCase = $true
if ($asRulesMap) {
    if ($null -ne (Get-RaMember -Object $asRulesMap -Name "panic_is_blocking"))        { $panicBlocking = [bool]$asRulesMap.panic_is_blocking }
    if ($null -ne (Get-RaMember -Object $asRulesMap -Name "exaggeration_is_warning"))  { $exagWarning  = [bool]$asRulesMap.exaggeration_is_warning }
    if ($null -ne (Get-RaMember -Object $asRulesMap -Name "product_leak_requires_verb")){ $leakNeedsVerb = [bool]$asRulesMap.product_leak_requires_verb }
    if ($null -ne (Get-RaMember -Object $asRulesMap -Name "case_insensitive_match"))   { $ignoreCase   = [bool]$asRulesMap.case_insensitive_match }
}

$risks = @(Get-RaMember -Object $A -Name "risks")
if ($null -eq $risks) { $risks = @() }

# 可选：Discovery 产物。提供后 completeness 才能做「应发现域是否遗漏」的交叉比对；
# 不提供则该子检查不执行（只做结构完整性校验）。
$script:expectedCats = @{}
if (-not [string]::IsNullOrEmpty($DiscoveryJsonPath) -and (Test-Path -LiteralPath $DiscoveryJsonPath)) {
    $D = (Get-Content -LiteralPath $DiscoveryJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json)
    foreach ($c in @(Get-RaMember -Object $D -Name "risk_candidates")) {
        # 注意：候选的 `status` 是 FactValue 溯源状态（KNOWN/ESTIMATED/...），
        # 三态结论在 `discovery_status`（IDENTIFIED/NOT_IDENTIFIED/UNDETERMINED）。
        $st = [string](Get-RaMember -Object $c -Name "discovery_status")
        if ([string]::IsNullOrWhiteSpace($st)) {
            # 兜底：无 discovery_status 时用 risk_exists 推导
            $rex = Get-RaMember -Object $c -Name "risk_exists"
            $st = if ($null -ne $rex -and [bool]$rex) { "IDENTIFIED" } else { "NOT_IDENTIFIED" }
        }
        # UNDETERMINED 不提升为 Risk 对象（CONTRACT §11），故不属于「应出现」集合
        if ($st -ne "IDENTIFIED" -and $st -ne "NOT_IDENTIFIED") { continue }
        $cat = [string](Get-RaMember -Object $c -Name "risk_category")
        if (-not [string]::IsNullOrWhiteSpace($cat)) { $script:expectedCats[$cat] = $st }
    }
}
$script:hasDiscoveryScope = (@($script:expectedCats.Keys).Count -gt 0)
$riskMatrix = @(Get-RaMember -Object $A -Name "risk_matrix")
if ($null -eq $riskMatrix) { $riskMatrix = @() }
$analysisScope = Get-RaMember -Object $A -Name "analysis_scope"

# ===== 各检查 =====
# --- 1. completeness ---
$compIssues = @()
$seenIds = @{}
foreach ($r in $risks) {
    $rid = [string]$r.risk_id
    $cat = [string]$r.risk_category
    if ($seenIds.ContainsKey($rid)) {
        $compIssues += New-RaIssue -Code "INVALID_OUTPUT" -Severity "WARNING" -RiskId $rid -Message "重复 risk_id" -Evidence $rid
    } else { $seenIds[$rid] = 1 }

    if (-not $script:validCats.ContainsKey($cat)) {
        $compIssues += New-RaIssue -Code "INVALID_OUTPUT" -Severity "WARNING" -RiskId $rid -Message "risk_category 非法: $cat" -Evidence $cat
    }
    if ($analysisScope -and @($analysisScope).Count -gt 0) {
        $inScope = $false
        foreach ($s in $analysisScope) { if ([string]$s -eq $cat) { $inScope = $true; break } }
        if (-not $inScope) {
            $compIssues += New-RaIssue -Code "INVALID_OUTPUT" -Severity "WARNING" -RiskId $rid -Message "risk_category 越出 analysis_scope" -Evidence $cat
        }
    }
    $exists = $true
    if ($null -ne (Get-RaMember -Object $r -Name "risk_exists")) { $exists = [bool]$r.risk_exists }

    if ($exists) {
        $sev = [string]$r.severity; $lik = [string]$r.likelihood; $res = [string]$r.residual_risk; $pri = [string]$r.priority
        if (-not $script:validSev.ContainsKey($sev)) { $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "BLOCKING" -RiskId $rid -Message "缺少合法 severity" -Evidence $sev }
        if (-not $script:validLik.ContainsKey($lik)) { $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "BLOCKING" -RiskId $rid -Message "缺少合法 likelihood" -Evidence $lik }
        if (-not $script:validRes.ContainsKey($res)) { $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "BLOCKING" -RiskId $rid -Message "缺少合法 residual_risk" -Evidence $res }
        if (-not $script:validPri.ContainsKey($pri)) { $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "BLOCKING" -RiskId $rid -Message "缺少合法 priority" -Evidence $pri }
        $ie = Get-RaMember -Object $r -Name "impact_estimate"
        if (-not $ie) {
            $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "BLOCKING" -RiskId $rid -Message "risk_exists=true 但缺少 impact_estimate 对象" -Evidence ($rid)
        } elseif ($null -eq $ie.amount -or [double]$ie.amount -le 0) {
            # 基础缺失导致的部分分析（CONTRACT §7 允许）记 WARNING，不阻断
            $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "WARNING" -RiskId $rid -Message "risk_exists=true 但 impact_estimate.amount 非正（部分分析 / 量化基础未知，建议补充信息）" -Evidence ($rid)
        }
    }
    # risk_matrix 覆盖
    $inMatrix = $false
    foreach ($m in $riskMatrix) { if ([string]$m.risk_id -eq $rid) { $inMatrix = $true; break } }
    if (-not $inMatrix) {
        $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "BLOCKING" -RiskId $rid -Message "risk_matrix 缺少该 risk_id" -Evidence $rid
    }
}
# 「应发现域是否遗漏」：仅当提供 Discovery 产物时可执行（CONTRACT §8 completeness 本义）
if ($script:hasDiscoveryScope) {
    $presentCats = @{}
    foreach ($r in $risks) { $presentCats[[string]$r.risk_category] = 1 }
    foreach ($cat in $script:expectedCats.Keys) {
        if (-not $presentCats.ContainsKey($cat)) {
            $compIssues += New-RaIssue -Code "MISSING_RISK" -Severity "BLOCKING" -RiskId ($cat + "-001") -Message "Discovery 判定为 $($script:expectedCats[$cat]) 的风险域 $cat 未出现在 risks[] 中" -Evidence $cat
        }
    }
}
$compBlocking = @($compIssues | Where-Object { $_.severity -eq "BLOCKING" }).Count
$compScore = if ($compBlocking -gt 0) { [math]::Max(0.0, 1.0 - 0.2 * $compBlocking) } else { [math]::Max(0.0, 1.0 - 0.05 * $compIssues.Count) }
$compStatus = if ($compBlocking -gt 0) { "FAIL" } else { "PASS" }
$compNote = if ($script:hasDiscoveryScope) { "结构完整性 + 应发现域覆盖（对照 Discovery 候选）" } else { "结构完整性（未提供 Discovery 产物，「应发现域覆盖」子检查未执行）" }
$checkCompleteness = New-RaCheck -Status $compStatus -Score $compScore -Issues $compIssues -Note $compNote

# --- 2. evidence_grounding ---
$egIssues = @()
foreach ($r in $risks) {
    $rid = [string]$r.risk_id
    $ev = @(Get-RaMember -Object $r -Name "evidence")
    if ($ev.Count -eq 0) {
        $egIssues += New-RaIssue -Code "UNSUPPORTED_CONCLUSION" -Severity "BLOCKING" -RiskId $rid -Message "无 evidence 条目" -Evidence $rid
        continue
    }
    $evIds = @{}
    foreach ($e in $ev) { $evIds[[string]$e.evidence_id] = 1 }
    $refs = @(Get-RaMember -Object $r -Name "reasoning_evidence_refs")
    if ($refs.Count -eq 0) {
        $egIssues += New-RaIssue -Code "UNSUPPORTED_CONCLUSION" -Severity "BLOCKING" -RiskId $rid -Message "reasoning_evidence_refs 为空" -Evidence $rid
        continue
    }
    foreach ($ref in $refs) {
        $rs = [string]$ref
        if ($rs.StartsWith("E")) {
            if (-not $evIds.ContainsKey($rs)) {
                $egIssues += New-RaIssue -Code "UNSUPPORTED_CONCLUSION" -Severity "BLOCKING" -RiskId $rid -Message "悬空证据锚点: $rs" -Evidence $rs
            }
        }
        # REQ-### 跨阶段引用不校验
    }
}
$egBlocking = @($egIssues | Where-Object { $_.severity -eq "BLOCKING" }).Count
$egScore = if ($egBlocking -gt 0) { [math]::Max(0.0, 1.0 - 0.2 * $egBlocking) } else { 1.0 }
$egStatus = if ($egBlocking -gt 0) { "FAIL" } else { "PASS" }
$checkEvidence = New-RaCheck -Status $egStatus -Score $egScore -Issues $egIssues -Note "每个结论 ≥1 可解析 E### 锚点"

# --- 3. reasoning_consistency ---
$rcIssues = @()
foreach ($r in $risks) {
    $rid = [string]$r.risk_id
    $sev = [string]$r.severity; $lik = [string]$r.likelihood; $res = [string]$r.residual_risk
    $sr = Get-RaRank -Map $script:sevRank -Val $sev
    $lr = Get-RaRank -Map $script:likRank -Val $lik
    $rr = Get-RaRank -Map $script:resRank -Val $res
    $exists = $true
    if ($null -ne (Get-RaMember -Object $r -Name "risk_exists")) { $exists = [bool]$r.risk_exists }
    if ($exists) {
        # 复算 residual 公式（与 analysis 引擎一致）：0.6*severity_rank + 0.4*likelihood_rank → 分档
        # 仅对 risk_exists=true 生效：NOT_IDENTIFIED 时引擎按契约强制 residual=LOW（置低档），
        # 且 likelihood 保留域 base 值，公式不再适用。
        if ($sr -gt 0 -and $lr -gt 0 -and $rr -gt 0) {
            $wSev = [double](Get-RaMember -Object $resW -Name "severity")
            $wLik = [double](Get-RaMember -Object $resW -Name "likelihood")
            $score = $sr * $wSev + $lr * $wLik
            $expRes = 'LOW'
            if ($score -ge [double]$resThr.CRITICAL) { $expRes = 'CRITICAL' }
            elseif ($score -ge [double]$resThr.HIGH) { $expRes = 'HIGH' }
            elseif ($score -ge [double]$resThr.MEDIUM) { $expRes = 'MEDIUM' }
            if ($expRes -ne $res) {
                $rcIssues += New-RaIssue -Code "LOGICAL_INCONSISTENCY" -Severity "BLOCKING" -RiskId $rid -Message "residual_risk($res) 与公式复算($expRes) 不一致（sev=$sev, lik=$lik）" -Evidence "$sev/$lik/$res"
            }
        }
    } else {
        $pri = [string]$r.priority
        if ($sev -ne "LOW" -or $res -ne "LOW" -or $pri -ne "P3") {
            $rcIssues += New-RaIssue -Code "LOGICAL_INCONSISTENCY" -Severity "BLOCKING" -RiskId $rid -Message "risk_exists=false 须 LOW/LOW/P3，实际 $sev/$res/$pri" -Evidence "$sev/$res/$pri"
        }
    }
}
$rcBlocking = @($rcIssues | Where-Object { $_.severity -eq "BLOCKING" }).Count
$rcScore = if ($rcBlocking -gt 0) { [math]::Max(0.0, 1.0 - 0.2 * $rcBlocking) } else { [math]::Max(0.0, 1.0 - 0.05 * $rcIssues.Count) }
$rcStatus = if ($rcBlocking -gt 0) { "FAIL" } else { "PASS" }
$checkReasoning = New-RaCheck -Status $rcStatus -Score $rcScore -Issues $rcIssues -Note "risk_exists=true 时 residual 须等于公式复算(0.6*sev+0.4*lik 分档)；risk_exists=false 须 LOW/LOW/P3"

# --- 4. separation ---
$sepIssues = @()
foreach ($r in $risks) {
    $rid = [string]$r.risk_id
    if ($r.PSObject.Properties.Name -contains "requirement") {
        $sepIssues += New-RaIssue -Code "PRODUCT_RECOMMENDATION_LEAK" -Severity "BLOCKING" -RiskId $rid -Message "Risk 对象含 requirement 字段" -Evidence "requirement"
    }
    $txt = Get-RaText -Risk $r
    $hasProd = Test-RaHasToken -Text $txt -Tokens $prodNames -IgnoreCase $ignoreCase
    $hasVerb = Test-RaHasToken -Text $txt -Tokens $salesVerbs -IgnoreCase $ignoreCase
    if ($leakNeedsVerb) {
        if ($hasProd -and $hasVerb) {
            $sepIssues += New-RaIssue -Code "PRODUCT_RECOMMENDATION_LEAK" -Severity "BLOCKING" -RiskId $rid -Message "文本同时含产品名与销售动词（风险被变成产品需求）" -Evidence $txt.Substring(0, [math]::Min(60, $txt.Length))
        }
    } else {
        if ($hasProd) {
            $sepIssues += New-RaIssue -Code "PRODUCT_RECOMMENDATION_LEAK" -Severity "BLOCKING" -RiskId $rid -Message "文本含产品名（疑似产品泄露）" -Evidence $txt.Substring(0, [math]::Min(60, $txt.Length))
        }
    }
}
$sepBlocking = @($sepIssues | Where-Object { $_.severity -eq "BLOCKING" }).Count
$sepScore = if ($sepBlocking -gt 0) { [math]::Max(0.0, 1.0 - 0.25 * $sepBlocking) } else { 1.0 }
$sepStatus = if ($sepBlocking -gt 0) { "FAIL" } else { "PASS" }
$checkSeparation = New-RaCheck -Status $sepStatus -Score $sepScore -Issues $sepIssues -Note "风险 ≠ 产品需求；产品名+销售动词共现判漏"

# --- 5. unknown_integrity ---
$uiIssues = @()
foreach ($r in $risks) {
    $rid = [string]$r.risk_id
    $ev = @(Get-RaMember -Object $r -Name "evidence")
    $knownLike = 0; $total = 0
    foreach ($e in $ev) {
        $total++
        $src = Get-RaMember -Object $e -Name "source"
        $st = if ($src) { [string](Get-RaMember -Object $src -Name "status") } else { "" }
        if ($st -in @("KNOWN","ESTIMATED","ASSUMED","INFERRED")) { $knownLike++ }
        # 注：EvidenceEntry 无 note 字段（schema additionalProperties:false），
        #     ESTIMATED 的 note 在 client_state 源 FactValue，由上游/契约校验负责，此处不查。
    }
    $rStatus = [string]$r.status
    if ($rStatus -eq "KNOWN" -and $total -gt 0 -and $knownLike -eq 0) {
        $uiIssues += New-RaIssue -Code "UNKNOWN_AS_KNOWN" -Severity "BLOCKING" -RiskId $rid -Message "risk status=KNOWN 但所有 evidence 均 UNKNOWN/UNVERIFIED" -Evidence $rid
    }
    $ie = Get-RaMember -Object $r -Name "impact_estimate"
    if ($ie -and $null -ne $ie.amount -and [double]$ie.amount -gt 0 -and $total -gt 0 -and $knownLike -eq 0) {
        $uiIssues += New-RaIssue -Code "UNKNOWN_AS_KNOWN" -Severity "BLOCKING" -RiskId $rid -Message "impact_estimate>0 但无 KNOWN/ESTIMATED 类证据支撑" -Evidence $rid
    }
    # existing_resources FactValue 同样检查 note
    $er = Get-RaMember -Object $r -Name "existing_resources"
    if ($er) {
        foreach ($k in $er.PSObject.Properties.Name) {
            $fv = $er.$k
            if ($null -eq $fv) { continue }
            $st = [string](Get-RaMember -Object $fv -Name "status")
            if ($st -in @("ESTIMATED","ASSUMED","INFERRED")) {
                $note = Get-RaMember -Object $fv -Name "note"
                if ([string]::IsNullOrEmpty([string]$note)) {
                    $uiIssues += New-RaIssue -Code "UNKNOWN_AS_KNOWN" -Severity "WARNING" -RiskId $rid -Message "existing_resources.$k status=$st 但 note 为空" -Evidence $k
                }
            }
        }
    }
}
$uiBlocking = @($uiIssues | Where-Object { $_.severity -eq "BLOCKING" }).Count
$uiScore = if ($uiBlocking -gt 0) { [math]::Max(0.0, 1.0 - 0.2 * $uiBlocking) } else { [math]::Max(0.0, 1.0 - 0.05 * $uiIssues.Count) }
$uiStatus = if ($uiBlocking -gt 0) { "FAIL" } else { "PASS" }
$checkUnknown = New-RaCheck -Status $uiStatus -Score $uiScore -Issues $uiIssues -Note "不把 UNKNOWN 当 KNOWN；非 KNOWN 状态须带 note"

# --- 6. priority_consistency ---
$pcIssues = @()
foreach ($r in $risks) {
    $rid = [string]$r.risk_id
    $pri = [string]$r.priority; $res = [string]$r.residual_risk
    $pr = Get-RaRank -Map $script:priRank -Val $pri
    $rr = Get-RaRank -Map $script:resRank -Val $res
    if ($pr -in @(0,1) -and $rr -in @(1,2)) {
        $pcIssues += New-RaIssue -Code "PRIORITY_INCONSISTENT" -Severity "BLOCKING" -RiskId $rid -Message "priority=$pri 但 residual_risk=$res（高优先级须高剩余风险）" -Evidence "$pri/$res"
    }
    if ($pri -eq "P0" -and $res -ne "CRITICAL") {
        $pcIssues += New-RaIssue -Code "PRIORITY_INCONSISTENT" -Severity "WARNING" -RiskId $rid -Message "P0 理想为 residual=CRITICAL，实际 $res" -Evidence $res
    }
    if ($pri -eq "P3" -and $res -eq "CRITICAL") {
        $pcIssues += New-RaIssue -Code "PRIORITY_INCONSISTENT" -Severity "WARNING" -RiskId $rid -Message "priority=P3 但 residual=CRITICAL（封顶与残险矛盾，需确认 override）" -Evidence "P3/CRITICAL"
    }
}
$pcBlocking = @($pcIssues | Where-Object { $_.severity -eq "BLOCKING" }).Count
$pcScore = if ($pcBlocking -gt 0) { [math]::Max(0.0, 1.0 - 0.2 * $pcBlocking) } else { [math]::Max(0.0, 1.0 - 0.05 * $pcIssues.Count) }
$pcStatus = if ($pcBlocking -gt 0) { "FAIL" } else { "PASS" }
$checkPriority = New-RaCheck -Status $pcStatus -Score $pcScore -Issues $pcIssues -Note "P0/P1 须 residual∈{HIGH,CRITICAL}"

# --- 7. anti_sales ---
$asIssues = @()
foreach ($r in $risks) {
    $rid = [string]$r.risk_id
    $txt = Get-RaText -Risk $r
    if ($panicBlocking -and (Test-RaHasToken -Text $txt -Tokens $panicTokens -IgnoreCase $ignoreCase)) {
        $asIssues += New-RaIssue -Code "SALES_BIAS" -Severity "BLOCKING" -RiskId $rid -Message "命中恐吓/焦虑话术（panic_token）" -Evidence $txt.Substring(0, [math]::Min(60, $txt.Length))
    }
    if ($exagWarning -and (Test-RaHasToken -Text $txt -Tokens $exagTokens -IgnoreCase $ignoreCase)) {
        $asIssues += New-RaIssue -Code "SALES_BIAS" -Severity "WARNING" -RiskId $rid -Message "命中夸大/绝对化表述（exaggeration_token）" -Evidence $txt.Substring(0, [math]::Min(60, $txt.Length))
    }
}
$asBlocking = @($asIssues | Where-Object { $_.severity -eq "BLOCKING" }).Count
$asScore = if ($asBlocking -gt 0) { [math]::Max(0.0, 1.0 - 0.25 * $asBlocking) } else { [math]::Max(0.0, 1.0 - 0.05 * $asIssues.Count) }
$asStatus = if ($asBlocking -gt 0) { "FAIL" } else { "PASS" }
$checkAntiSales = New-RaCheck -Status $asStatus -Score $asScore -Issues $asIssues -Note "无恐吓/夸大；产品泄露由 separation 负责"

# ===== 汇总 =====
$allFail = @()
foreach ($c in @($checkCompleteness, $checkEvidence, $checkReasoning, $checkSeparation, $checkUnknown, $checkPriority, $checkAntiSales)) {
    if ($c.status -eq "FAIL") { $allFail += $c }
}
$evalStatus = if ($allFail.Count -gt 0) { "FAIL" } else { "PASS" }

$checksObj = [ordered]@{
    completeness          = $checkCompleteness
    evidence_grounding    = $checkEvidence
    reasoning_consistency = $checkReasoning
    separation            = $checkSeparation
    unknown_integrity     = $checkUnknown
    priority_consistency  = $checkPriority
    anti_sales            = $checkAntiSales
}

$allIssues = @()
foreach ($c in @($checkCompleteness, $checkEvidence, $checkReasoning, $checkSeparation, $checkUnknown, $checkPriority, $checkAntiSales)) {
    foreach ($i in @($c.issues)) { $allIssues += $i }
}
# failures 只收 BLOCKING：WARNING 不阻断、不应出现在"失败清单"里
# （否则 eval_status=PASS 时 failures 非空，下游 Repair 逻辑会误判）
$blockingIssues = @($allIssues | Where-Object { $_.severity -eq "BLOCKING" })

$result = [ordered]@{
    eval_status          = $evalStatus
    checks               = $checksObj
    failures             = @($blockingIssues)
    repair_required      = ($evalStatus -eq "FAIL")
    repair_attempts      = 0
    max_repair_attempts  = 2
}
# 若为 FAIL 给出 needs_review_note 占位（Repair Loop 填充）
if ($evalStatus -eq "FAIL") {
    $blk = @($blockingIssues | ForEach-Object { "$($_.code):$($_.risk_id)" })
    $result.needs_review_note = "Eval FAIL，待 Repair Loop（≤2）。BLOCKING: " + ($blk -join ", ")
}

# ----- 轻量自校验（完整 schema 校验由 verify-contract.py §8 负责） -----
$reqCheckKeys = @("completeness","evidence_grounding","reasoning_consistency","separation","unknown_integrity","priority_consistency","anti_sales")
foreach ($k in $reqCheckKeys) {
    if (-not ($checksObj.Keys -contains $k)) { Write-Error "EvalResult 缺少 check: $k"; exit 3 }
    $cs = [string]$checksObj[$k].status
    if ($cs -notin @("PASS","FAIL","MANUAL","NOT_EXECUTED")) { Write-Error "非法 check status: $cs"; exit 3 }
}

# ----- 可选：回填 guardrails 到分析产物 -----
if ($PatchOutput) {
    if ($asStatus -eq "FAIL") { $A.guardrails.sales_language_detected = $true }
    if ($sepStatus -eq "FAIL") { $A.guardrails.product_recommendation_included = $true }
    $A.eval = [pscustomobject]$result
    $aText = ($A | ConvertTo-Json -Depth 20)
    [System.IO.File]::WriteAllText($AnalysisJsonPath, $aText, [System.Text.UTF8Encoding]::new($false))
}

# ----- 写出 EvalResult -----
$outText = ($result | ConvertTo-Json -Depth 12)
[System.IO.File]::WriteAllText($OutputJsonPath, $outText, [System.Text.UTF8Encoding]::new($false))

# stdout 摘要（信息流不可靠，落盘为主；此处给人类一个快速信号）
$passCount = @($checksObj.Values | Where-Object { $_.status -eq "PASS" }).Count
Write-Output "EVAL_STATUS=$evalStatus CHECKS_PASS=$passCount/7 ISSUES=$($allIssues.Count)"
exit 0
