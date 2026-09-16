#requires -Version 5.1
<#
    invoke-risk-analysis-analysis.ps1
    ---------------------------------
    risk-analysis · Stage: Analysis（风险量化与优先级）

    输入：
      - RiskAnalysisInput            [schemas/risk-analysis-input.schema.json]
      - Phase 4 discovery 阶段产物   （risk_candidates：IDENTIFIED / NOT_IDENTIFIED / UNDETERMINED）
      - 可选 Sufficiency 阶段产物     （前向合并 unknowns / next_information_needed / assumptions）
    输出：Analysis 阶段结果（JSON，UTF-8 BOM）
      - risks[]            ：完整 Risk 对象（对齐 schemas/risk.schema.json）
      - risk_matrix[] / top_priorities[] / family_risk_overview
      - 前向合并 unknowns / assumptions / next_information_needed

    量化链路（risk_scoring_v1，确定性，零 LLM）：
      primary_income → gross_impact（按域公式）
      → protected_amount（现有相关保障）→ unprotected_amount
      → severity（档位 + 资产吸收降档）→ likelihood（base + 指示条件）
      → residual（severity×w_s + likelihood×w_l）→ priority（矩阵 + override）

    规则全部外置于 resources/config/risk-scoring.rules.json（含所有 magic number）。
#>
param(
    [Parameter(Mandatory = $true)][string]$InputJsonPath,
    [Parameter(Mandatory = $true)][string]$DiscoveryJsonPath,
    [Parameter(Mandatory = $true)][string]$OutputJsonPath,
    [string]$RulesPath = '',
    [string]$SharedRulesPath = '',
    [string]$SufficiencyJsonPath = ''
)

# --- PSScriptRoot 兜底（以 -File 方式被调用时可能为空） ---
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------ helpers
function Get-RaMember {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}
function Get-RaStringArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}
function ConvertTo-RaNumber {
    param($Value, $Units)
    if ($null -eq $Value) { return $null }
    $s = ([string]$Value) -replace '[,，\s]', ''
    if ([string]::IsNullOrWhiteSpace($s)) { return $null }
    $m = [regex]::Match($s, '(\d+(?:\.\d+)?)(亿|千万|百万|万元|万|千|k|K|w|W)?')
    if (-not $m.Success) { return $null }
    $n = [double]$m.Groups[1].Value
    $u = [string]$m.Groups[2].Value
    if (-not [string]::IsNullOrWhiteSpace($u)) {
        $key = $null
        foreach ($p in $Units.PSObject.Properties) {
            if ([string]$p.Name -eq $u) { $key = $p.Name; break }
        }
        if ($null -eq $key) {
            $ul = $u.ToLowerInvariant()
            foreach ($p in $Units.PSObject.Properties) {
                if ([string]$p.Name.ToLowerInvariant() -eq $ul) { $key = $p.Name; break }
            }
        }
        if ($null -ne $key) { $n = $n * [double]$Units.PSObject.Properties[$key].Value }
    }
    return $n
}
function Test-RaNegative {
    param($Value, [string[]]$Tokens, [string[]]$Prefixes)
    if ($null -eq $Value) { return $false }
    $s = ([string]$Value).Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($s)) { return $false }
    if ($s -eq '0' -or $s -eq '0.0' -or $s -eq '0.00') { return $true }
    foreach ($t in $Tokens) {
        if ($s -eq ([string]$t).ToLowerInvariant()) { return $true }
    }
    foreach ($p in $Prefixes) {
        $pl = ([string]$p).ToLowerInvariant()
        if ($pl.Length -gt 0 -and $s.StartsWith($pl)) { return $true }
    }
    return $false
}
function Get-RaFactValue {
    param([string]$Field)
    if (-not $script:fieldMap.ContainsKey($Field)) { return $null }
    return $script:fieldMap[$Field]
}
function Get-RaNum {
    param([string]$Field)
    $fv = Get-RaFactValue -Field $Field
    if ($null -eq $fv) { return $null }
    if ($script:satStatus -notcontains $fv.status) { return $null }
    return (ConvertTo-RaNumber -Value $fv.value -Units $script:units)
}
function Test-RaHealthAnomaly {
    # 判「键存在」而非「值非空」：Get-RaMember 对空数组会返回 $null（PS 函数返回空数组会被展开）
    if (-not (@($rules.PSObject.Properties.Name) -contains 'health_anomaly_tokens')) {
        throw "rules 缺 health_anomaly_tokens：不得回退硬编码词表（空数组合法，表示无加成词）"
    }
    $script:healthTokens = @(Get-RaStringArray -Value $rules.health_anomaly_tokens)
    foreach ($f in @('customer_health', 'health_history')) {
        $fv = Get-RaFactValue -Field $f
        if ($null -eq $fv) { continue }
        $s = [string]$fv.value
        if ([string]::IsNullOrWhiteSpace($s)) { continue }
        $sl = $s.ToLowerInvariant()
        foreach ($t in $script:healthTokens) {
            if ($sl.Contains([string]$t.ToLowerInvariant())) { return $true }
        }
    }
    return $false
}

# ------------------------------------------------------------------ load
$skillRoot = Split-Path -Parent $PSScriptRoot
$configDir = Join-Path $skillRoot 'resources'
$configDir = Join-Path $configDir 'config'

if ([string]::IsNullOrWhiteSpace($RulesPath)) {
    $RulesPath = Join-Path $configDir 'risk-scoring.rules.json'
}
if ([string]::IsNullOrWhiteSpace($SharedRulesPath)) {
    $SharedRulesPath = Join-Path $configDir 'risk-sufficiency.rules.json'
}

if (-not (Test-Path -LiteralPath $RulesPath)) { throw "rules file not found: $RulesPath" }
if (-not (Test-Path -LiteralPath $SharedRulesPath)) { throw "shared rules file not found: $SharedRulesPath" }
if (-not (Test-Path -LiteralPath $InputJsonPath)) { throw "input not found: $InputJsonPath" }
if (-not (Test-Path -LiteralPath $DiscoveryJsonPath)) { throw "discovery output not found: $DiscoveryJsonPath" }

$rules = (Get-Content -LiteralPath $RulesPath -Raw -Encoding UTF8) | ConvertFrom-Json
$raInput = (Get-Content -LiteralPath $InputJsonPath -Raw -Encoding UTF8) | ConvertFrom-Json
$discDoc = (Get-Content -LiteralPath $DiscoveryJsonPath -Raw -Encoding UTF8) | ConvertFrom-Json

$script:satStatus = Get-RaStringArray -Value $rules.negative_tokens | Out-Null
$script:satStatus = @('KNOWN', 'ESTIMATED', 'ASSUMED', 'INFERRED')
$script:units = Get-RaMember -Object $rules -Name 'number_units'
$negTokens = Get-RaStringArray -Value $rules.negative_tokens
$negPrefixes = Get-RaStringArray -Value $rules.negative_prefixes
$labels = Get-RaMember -Object $rules -Name 'field_labels'
$params = Get-RaMember -Object $rules -Name 'impact_parameters'
$sevThr = Get-RaMember -Object $rules -Name 'severity_thresholds'
$absorption = Get-RaMember -Object $rules -Name 'absorption'
$likInd = Get-RaMember -Object $rules -Name 'likelihood_indicators'
$resW = Get-RaMember -Object $rules -Name 'residual_weights'
$resThr = Get-RaMember -Object $rules -Name 'residual_thresholds'
$prioMatrix = Get-RaMember -Object $rules -Name 'priority_matrix'
$prioOverrides = @(Get-RaMember -Object $rules -Name 'priority_overrides')
$covMap = Get-RaMember -Object $rules -Name 'coverage_map'
$resMap = Get-RaMember -Object $rules -Name 'existing_resource_map'
$potTpl = Get-RaMember -Object $rules -Name 'potential_impact_templates'
$reasonTpl = Get-RaMember -Object $rules -Name 'reasoning_templates'
$conclTpl = Get-RaMember -Object $rules -Name 'conclusion_templates'
$overviewTpl = [string](Get-RaMember -Object $rules -Name 'family_overview_template')
$prioRank = Get-RaMember -Object $rules -Name 'priority_rank'
$sevRank = Get-RaMember -Object $rules -Name 'severity_rank'
$likRank = Get-RaMember -Object $rules -Name 'likelihood_rank'
$resRank = Get-RaMember -Object $rules -Name 'residual_rank'

$sharedRules = (Get-Content -LiteralPath $SharedRulesPath -Raw -Encoding UTF8) | ConvertFrom-Json
$templates = Get-RaMember -Object $sharedRules -Name 'question_templates'

# 状态合并次序（单一真源：risk-sufficiency.rules.json#analysis_status_rules.precedence）
$precedence = @(Get-RaStringArray -Value (Get-RaMember -Object $sharedRules.analysis_status_rules -Name 'precedence'))
if (@($precedence).Count -eq 0) { throw "shared rules 缺 analysis_status_rules.precedence：不得回退硬编码" }

# ------------------------------------------------------------------ field map
# 单一真源：risk-sufficiency.rules.json#profile_names（不允许本脚本自带一份）
$profileNames = @(Get-RaStringArray -Value $sharedRules.profile_names)
if (@($profileNames).Count -eq 0) { throw "shared rules 缺 profile_names：不得回退硬编码" }
$script:fieldMap = @{}
foreach ($pn in $profileNames) {
    $prof = Get-RaMember -Object $raInput.client_state -Name $pn
    if ($null -eq $prof) { continue }
    foreach ($prop in $prof.PSObject.Properties) {
        $fname = [string]$prop.Name
        if ($script:fieldMap.ContainsKey($fname)) { continue }
        $fv = $prop.Value
        $st = [string](Get-RaMember -Object $fv -Name 'status')
        if ([string]::IsNullOrWhiteSpace($st)) { $st = 'UNKNOWN' }
        $src = Get-RaMember -Object $fv -Name 'source'
        $origin = Get-RaMember -Object $src -Name 'origin'
        $oSkill = [string](Get-RaMember -Object $origin -Name 'skill')
        $oField = [string](Get-RaMember -Object $origin -Name 'field')
        if (@('client-intake', 'requirement-analysis', 'unknown') -notcontains $oSkill) { $oSkill = 'client-intake' }
        if ([string]::IsNullOrWhiteSpace($oField)) { $oField = $fname }
        $script:fieldMap[$fname] = [pscustomobject]@{
            field      = $fname
            profile    = $pn
            value      = Get-RaMember -Object $fv -Name 'value'
            status     = $st
            confidence = Get-RaMember -Object $fv -Name 'confidence'
            note       = Get-RaMember -Object $fv -Name 'note'
            origin     = [pscustomobject]@{ skill = $oSkill; field = $oField }
            source     = $src
        }
    }
}

# ------------------------------------------------------------------ helpers：档位 / 数值
function Get-RaLabel { param([string]$Field)
    $l = [string](Get-RaMember -Object $labels -Name $Field)
    if ([string]::IsNullOrWhiteSpace($l)) { return $Field }
    return $l
}
function Format-RaWan { param($Amount)
    if ($null -eq $Amount) { return '未知' }
    $a = [double]$Amount
    if ($a -ge 10000) { return ([math]::Round($a / 10000, 1)).ToString('0.0') + ' 万元' }
    return $a.ToString('0') + ' 元'
}
function Get-RaSeverityBand { param($Amount)
    $a = [double]$Amount
    if ($a -ge [double]$sevThr.HIGH) { return 'CRITICAL' }
    if ($a -ge [double]$sevThr.MEDIUM) { return 'HIGH' }
    if ($a -ge [double]$sevThr.LOW) { return 'MEDIUM' }
    return 'LOW'
}
function Get-RaResidualBand { param($Score)
    $s = [double]$Score
    if ($s -ge [double]$resThr.CRITICAL) { return 'CRITICAL' }
    if ($s -ge [double]$resThr.HIGH) { return 'HIGH' }
    if ($s -ge [double]$resThr.MEDIUM) { return 'MEDIUM' }
    return 'LOW'
}
function Cap-RaTier { param([string]$Tier, [string]$Cap)
    $r = Get-RaMember -Object $sevRank -Name $Tier
    $c = Get-RaMember -Object $sevRank -Name $Cap
    if ($null -eq $r) { $r = 1 }
    if ($null -eq $c) { $c = 4 }
    if ($r -gt $c) { return $Cap }
    return $Tier
}
function Eval-RaCondition {
    param($Cond)
    $field = [string](Get-RaMember -Object $Cond -Name 'field')
    $op = [string](Get-RaMember -Object $Cond -Name 'op')
    $fv = Get-RaFactValue -Field $field
    if ($null -eq $fv) { return $false }
    $st = $fv.status
    $v = $fv.value
    switch ($op) {
        'numeric_gte' {
            $num = ConvertTo-RaNumber -Value $v -Units $script:units
            if ($null -eq $num) { return $false }
            return $num -ge [double](Get-RaMember -Object $Cond -Name 'value')
        }
        'numeric_lt' {
            $num = ConvertTo-RaNumber -Value $v -Units $script:units
            if ($null -eq $num) { return $false }
            return $num -lt [double](Get-RaMember -Object $Cond -Name 'value')
        }
        'numeric_gt' {
            $num = ConvertTo-RaNumber -Value $v -Units $script:units
            if ($null -eq $num) { return $false }
            return $num -gt [double](Get-RaMember -Object $Cond -Name 'value')
        }
        'string_contains' {
            $sv = ([string]$v).ToLowerInvariant()
            foreach ($k in @(Get-RaMember -Object $Cond -Name 'value')) {
                if ($sv.Contains([string]$k.ToLowerInvariant())) { return $true }
            }
            return $false
        }
        'status_satisfied' {
            return ($script:satStatus -contains $st) -and (-not [string]::IsNullOrWhiteSpace([string]$v))
        }
        'status_absent' {
            return (Test-RaNegative -Value $v -Tokens $negTokens -Prefixes $negPrefixes) -or ($st -eq 'UNKNOWN')
        }
        default { return $false }
    }
}

# ------------------------------------------------------------------ primary income 推导
function Get-RaPrimaryIncome {
    $assumptions = [System.Collections.Generic.List[object]]::new()
    $ai = Get-RaFactValue -Field 'annual_income'
    if ($null -ne $ai -and $script:satStatus -contains $ai.status -and $null -ne $ai.value -and -not [string]::IsNullOrWhiteSpace([string]$ai.value)) {
        $n = ConvertTo-RaNumber -Value $ai.value -Units $script:units
        return [pscustomobject]@{ value = $n; status = $ai.status; confidence = $ai.confidence; assumptions = $assumptions; estimated = (@('ESTIMATED','ASSUMED','INFERRED') -contains $ai.status) }
    }
    $hh = Get-RaFactValue -Field 'household_income'
    if ($null -ne $hh -and $script:satStatus -contains $hh.status -and $null -ne $hh.value -and -not [string]::IsNullOrWhiteSpace([string]$hh.value)) {
        $hn = ConvertTo-RaNumber -Value $hh.value -Units $script:units
        $sp = Get-RaFactValue -Field 'spouse_income'
        $pi = $hn
        if ($null -ne $sp -and $script:satStatus -contains $sp.status -and $null -ne $sp.value -and -not [string]::IsNullOrWhiteSpace([string]$sp.value)) {
            $pi = $hn - [double](ConvertTo-RaNumber -Value $sp.value -Units $script:units)
        } else {
            $pi = $hn * 0.6
            $assumptions.Add([pscustomobject][ordered]@{ field = 'annual_income'; assumption = '家庭年收入已知但本人年收入未知，按家庭年收入扣除配偶收入（配偶收入未知时取 60%）估算本人收入'; reason = '本人年收入缺失，需进一步核实' })
        }
        return [pscustomobject]@{ value = $pi; status = $hh.status; confidence = $hh.confidence; assumptions = $assumptions; estimated = $true }
    }
    $assumptions.Add([pscustomobject][ordered]@{ field = 'annual_income'; assumption = '本人与家庭收入均未知，收入相关影响按 0 估算'; reason = '收入信息缺失，无法量化收入中断后果' })
    return [pscustomobject]@{ value = 0.0; status = 'UNKNOWN'; confidence = 0.0; assumptions = $assumptions; estimated = $false }
}

# ------------------------------------------------------------------ scope
$scope = Get-RaStringArray -Value $raInput.analysis_scope
if (@($scope).Count -eq 0) { $scope = @('R1', 'R2', 'R3', 'R4', 'R5') }

# ------------------------------------------------------------------ analysis loop
$risks = [System.Collections.Generic.List[object]]::new()
$matrix = [System.Collections.Generic.List[object]]::new()
$identifiedList = [System.Collections.Generic.List[string]]::new()
$notIdentList = [System.Collections.Generic.List[string]]::new()
$undetList = [System.Collections.Generic.List[string]]::new()

$candByCat = @{}
foreach ($c in @(Get-RaMember -Object $discDoc -Name 'risk_candidates')) {
    if ($null -eq $c) { continue }
    $candByCat[[string]$c.risk_category] = $c
}

$topAssumptions = [System.Collections.Generic.List[object]]::new()
$topAssumptionKeys = [System.Collections.Generic.HashSet[string]]::new()

foreach ($did in $scope) {
    if (-not $candByCat.ContainsKey($did)) { continue }
    $cand = $candByCat[$did]
    $discStatus = [string]$cand.discovery_status
    if ($discStatus -eq 'UNDETERMINED') { $undetList.Add($did); continue }

    $riskName = [string]$cand.risk_name_zh
    if ([string]::IsNullOrWhiteSpace($riskName)) { $riskName = [string]$cand.risk_name }
    $riskStatus = [string]$cand.status
    $exists = ($discStatus -eq 'IDENTIFIED')

    # 复用 discovery 的 evidence / refs / assumptions / unknowns / next
    $evidence = @($cand.evidence)
    $refs = @(Get-RaStringArray -Value $cand.reasoning_evidence_refs)
    $candAssumptions = [System.Collections.Generic.List[object]]::new()
    foreach ($a in @(Get-RaMember -Object $cand -Name 'assumptions')) { $candAssumptions.Add($a) }
    $candUnknowns = @(Get-RaMember -Object $cand -Name 'unknowns')
    $candNext = @(Get-RaMember -Object $cand -Name 'next_information_needed')

    $confNote = ''
    $gross = 0.0
    $impactConf = 1.0
    $impactEstimated = $false
    $protected = 0.0
    $coverageStatus = 'UNKNOWN'
    $coverageField = [string](Get-RaMember -Object $covMap -Name $did)
    $potentialImpact = [pscustomobject][ordered]@{ financial = ''; lifestyle = ''; family_responsibility = '' }

    if ($exists) {
        $pi = Get-RaPrimaryIncome
        foreach ($a in $pi.assumptions) { $candAssumptions.Add($a) }
        if ($pi.estimated) { $impactEstimated = $true; if ($impactConf -gt 0.6) { $impactConf = 0.6 } }

        $years = Get-RaMember -Object $params.income_replacement_years -Name $did
        if ($null -eq $years) { $years = 0 }

        switch ($did) {
            'R1' {
                $gross = [double]$params.medical_base_cost
                $med = Get-RaFactValue -Field 'existing_medical_coverage'
                $medNeg = ($null -eq $med) -or ($script:satStatus -notcontains $med.status) -or (Test-RaNegative -Value $med.value -Tokens $negTokens -Prefixes $negPrefixes)
                if ($medNeg) { $gross += [double]$params.r1_no_medical_insurance_addon }
                if (Test-RaHealthAnomaly) { $gross += [double]$params.r1_health_anomaly_addon }
                $potentialImpact.financial = ([string]$potTpl.R1.financial).Replace('{amount}', (Format-RaWan $gross))
            }
            'R2' {
                $gross = $pi.value * [double]$years + [double]$params.rehab_cost_per_event
                $potentialImpact.financial = ([string]$potTpl.R2.financial).Replace('{amount}', (Format-RaWan $gross)).Replace('{income_years}', [string]$years)
            }
            'R3' {
                $gross = $pi.value * [double]$years * [double]$params.disability_factor
                $potentialImpact.financial = ([string]$potTpl.R3.financial).Replace('{amount}', (Format-RaWan $gross))
            }
            'R4' {
                $sum = 0.0
                foreach ($f in @('mortgage_balance', 'liabilities', 'children_education', 'elderly_support')) {
                    $nv = Get-RaNum -Field $f
                    if ($null -ne $nv) { $sum += $nv }
                    else { $impactEstimated = $true; if ($impactConf -gt 0.6) { $impactConf = 0.6 } }
                }
                $sum += $pi.value * [double]$years
                $gross = $sum
                $potentialImpact.financial = ([string]$potTpl.R4.financial).Replace('{amount}', (Format-RaWan $gross))
            }
            'R5' {
                $assets = Get-RaNum -Field 'assets'
                $edu = Get-RaNum -Field 'children_education'
                $basis = 0.0
                if ($null -ne $edu -and $edu -gt 0) {
                    $basis = $edu
                } else {
                    $hh = Get-RaNum -Field 'household_income'
                    if ($null -eq $hh -or $hh -le 0) {
                        $hh = Get-RaNum -Field 'household_expense'
                        if ($null -eq $hh) { $hh = 0.0; $impactEstimated = $true; if ($impactConf -gt 0.6) { $impactConf = 0.6 } }
                    }
                    $basis = $hh
                }
                $target = $basis * [double]$params.r5_retirement_income_multiple
                if ($null -eq $assets) { $assets = 0.0; $impactEstimated = $true; if ($impactConf -gt 0.6) { $impactConf = 0.6 } }
                # gross = 总退休/长期需求；unprotected 由 max(gross - protected, 0) 处理（不再在此抵扣资产）
                $gross = [double]$target
                $potentialImpact.financial = ([string]$potTpl.R5.financial).Replace('{amount}', (Format-RaWan $gross))
            }
        }
        $potentialImpact.lifestyle = [string]$potTpl.$did.lifestyle
        $potentialImpact.family_responsibility = [string]$potTpl.$did.family_responsibility

        # coverage
        if (-not [string]::IsNullOrWhiteSpace($coverageField)) {
            $cfv = Get-RaFactValue -Field $coverageField
            if ($null -ne $cfv -and $script:satStatus -contains $cfv.status -and $null -ne $cfv.value -and -not [string]::IsNullOrWhiteSpace([string]$cfv.value)) {
                $protected = [double](ConvertTo-RaNumber -Value $cfv.value -Units $script:units)
                $coverageStatus = $cfv.status
            }
        }
        $unprotected = [math]::Max($gross - $protected, 0.0)

        # severity（按 unprotected 档位 + 资产吸收降档）
        $severity = Get-RaSeverityBand -Amount $unprotected
        $liquid = Get-RaNum -Field $absorption.liquid_asset_field
        if ($null -ne $liquid -and $liquid -gt 0) {
            foreach ($cap in @($absorption.tier_caps)) {
                if ($unprotected -le ([double]$cap.max_unprotected_ratio) * $liquid) {
                    $severity = Cap-RaTier -Tier $severity -Cap ([string]$cap.cap)
                    break
                }
            }
        }

        # likelihood（base + 指示条件）
        $likSpec = Get-RaMember -Object $likInd -Name $did
        $likelihood = 'MEDIUM'
        if ($null -ne $likSpec) {
            $likelihood = [string]$likSpec.base
            foreach ($r in @(Get-RaMember -Object $likSpec -Name 'raise')) {
                $all = $true
                foreach ($cnd in @(Get-RaMember -Object $r -Name 'when')) { if (-not (Eval-RaCondition -Cond $cnd)) { $all = $false; break } }
                if ($all) { $likelihood = [string]$r.to }
            }
            foreach ($r in @(Get-RaMember -Object $likSpec -Name 'lower')) {
                $all = $true
                foreach ($cnd in @(Get-RaMember -Object $r -Name 'when')) { if (-not (Eval-RaCondition -Cond $cnd)) { $all = $false; break } }
                if ($all) { $likelihood = [string]$r.to }
            }
        }

        # residual
        $sr = [double](Get-RaMember -Object $sevRank -Name $severity); if ($sr -lt 1) { $sr = 1 }
        $lr = [double](Get-RaMember -Object $likRank -Name $likelihood); if ($lr -lt 1) { $lr = 2 }
        $resScore = $sr * [double]$resW.severity + $lr * [double]$resW.likelihood
        $residual = Get-RaResidualBand -Score $resScore

        # priority（矩阵 + override）
        $prio = [string](Get-RaMember -Object (Get-RaMember -Object $prioMatrix -Name $severity) -Name $likelihood)
        if ([string]::IsNullOrWhiteSpace($prio)) { $prio = 'P3' }
        foreach ($ov in $prioOverrides) {
            # 显式开关：每条 override 必须自带 enabled；漏写即抛错，禁止静默 no-op 复活
            $ovEnabledProp = Get-RaMember -Object $ov -Name 'enabled'
            if ($null -eq $ovEnabledProp) { throw "priority_overrides 项 '$(Get-RaMember -Object $ov -Name 'id')' 缺 enabled 字段（禁止隐式启用）" }
            if ([string]$ovEnabledProp -eq 'False') { continue }
            $if = Get-RaMember -Object $ov -Name 'if'
            $match = $true
            if ($null -ne (Get-RaMember -Object $if -Name 'category')) { if ([string]$if.category -ne $did) { $match = $false } }
            if ($null -ne (Get-RaMember -Object $if -Name 'residual')) { if ([string]$if.residual -ne $residual) { $match = $false } }
            if ($null -ne (Get-RaMember -Object $if -Name 'likelihood')) { if ([string]$if.likelihood -ne $likelihood) { $match = $false } }
            if ($null -ne (Get-RaMember -Object $if -Name 'risk_exists')) {
                $want = if ([string]$if.risk_exists -eq 'false') { $false } else { $true }
                if ($want -ne $exists) { $match = $false }
            }
            if ($match) {
                if ($null -ne (Get-RaMember -Object $ov -Name 'max_priority')) {
                    $cur = [int](Get-RaMember -Object $prioRank -Name $prio); $mx = [int](Get-RaMember -Object $prioRank -Name ([string]$ov.max_priority))
                    if ($cur -lt $mx) { $prio = [string]$ov.max_priority }
                }
                if ($null -ne (Get-RaMember -Object $ov -Name 'min_priority')) {
                    $cur = [int](Get-RaMember -Object $prioRank -Name $prio); $mn = [int](Get-RaMember -Object $prioRank -Name ([string]$ov.min_priority))
                    # rank 越小越紧急：「至少 P_mn」= 当前更不紧急（rank 更大）时收紧
                    if ($cur -gt $mn) { $prio = [string]$ov.min_priority }
                }
            }
        }

        # confidence 收敛
        $finalConf = $impactConf
        if ($coverageStatus -eq 'UNKNOWN') { $finalConf = [math]::Min($finalConf, 0.6) }

        # existing_resources 映射
        $er = [ordered]@{
            cash = $null; investments = $null; income = $null; employer_benefits = $null
            social_security = $null; existing_insurance = $null; family_support = $null
        }
        foreach ($k in @('cash', 'investments', 'income', 'employer_benefits', 'social_security', 'family_support')) {
            $mp = [string](Get-RaMember -Object $resMap -Name $k)
            if (-not [string]::IsNullOrWhiteSpace($mp) -and $script:fieldMap.ContainsKey($mp)) {
                $fm = $script:fieldMap[$mp]
                $srcLayer = [string](Get-RaMember -Object $fm.source -Name 'layer')
                if ([string]::IsNullOrWhiteSpace($srcLayer)) { $srcLayer = 'client_state' }
                $er[$k] = [pscustomobject][ordered]@{
                    value = $fm.value
                    status = $fm.status
                    source = [pscustomobject][ordered]@{
                        layer = $srcLayer
                        field = [string]$fm.profile + '.' + $mp
                        origin = $fm.origin
                        status = $fm.status
                    }
                    confidence = $fm.confidence
                    note = $fm.note
                }
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($coverageField) -and $script:fieldMap.ContainsKey($coverageField)) {
            $fm = $script:fieldMap[$coverageField]
            $srcLayer = [string](Get-RaMember -Object $fm.source -Name 'layer')
            if ([string]::IsNullOrWhiteSpace($srcLayer)) { $srcLayer = 'client_state' }
            $er['existing_insurance'] = [pscustomobject][ordered]@{
                value = $fm.value
                status = $fm.status
                source = [pscustomobject][ordered]@{
                    layer = $srcLayer
                    field = [string]$fm.profile + '.' + $coverageField
                    origin = $fm.origin
                    status = $fm.status
                }
                confidence = $fm.confidence
                note = $fm.note
            }
        }

        $protLabel = if ($protected -gt 0) { (Format-RaWan $protected) } else { '无相关保障' }
        $existingProtection = '现有相关保障：' + $protLabel + '；'
        $assets = Get-RaNum -Field 'assets'
        if ($null -ne $assets) { $existingProtection += '家庭资产 ' + (Format-RaWan $assets) + '。' } else { $existingProtection += '家庭资产未知。' }

        $liqText = '剩余暴露超过家庭可动用资产，需外部保障承接。'
        if ($null -ne $liquid -and $liquid -gt 0) {
            if ($unprotected -le 0.5 * $liquid) { $liqText = '家庭资产可覆盖大部分剩余暴露，但仍需保留应急金并关注流动性。' }
            elseif ($unprotected -le $liquid) { $liqText = '家庭资产可部分吸收剩余暴露，但流动性可能不足以匹配风险发生时点。' }
        }

        $coverageAssessment = [ordered]@{
            protected_amount = if ($protected -gt 0) { [double]$protected } else { $null }
            unprotected_amount = [double]$unprotected
            confidence = [double]$finalConf
            liquidity_constraint = $liqText
        }

        $impactEstimate = [ordered]@{
            amount = [double]$gross
            range = [ordered]@{ low = [double]([math]::Round($gross * 0.7, 0)); high = [double]([math]::Round($gross * 1.3, 0)) }
            confidence = [double]$finalConf
        }

        $evidenceList = (@($evidence | ForEach-Object { [string]$_.evidence_id }) -join '、')
        $reasoning = ([string]$reasonTpl.IDENTIFIED).Replace('{evidence_list}', $evidenceList).Replace('{domain}', $did).Replace('{amount}', (Format-RaWan $gross)).Replace('{confidence}', $finalConf.ToString('0.00')).Replace('{protected}', $protLabel).Replace('{unprotected}', (Format-RaWan $unprotected)).Replace('{absorption}', (Format-RaWan $liquid)).Replace('{severity}', $severity)
        $conclusion = ([string]$conclTpl.IDENTIFIED).Replace('{domain}', $did).Replace('{residual}', $residual).Replace('{priority}', $prio)

        $identifiedList.Add($did)
    } else {
        # NOT_IDENTIFIED：置低档，仍进 risks[] 以支持 Eval
        $severity = 'LOW'
        $likSpec = Get-RaMember -Object $likInd -Name $did
        $likelihood = if ($null -ne $likSpec) { [string]$likSpec.base } else { 'LOW' }
        $residual = 'LOW'
        $prio = 'P3'
        $potentialImpact.financial = '当前证据不足以认定该风险成立，无显著经济后果测算。'
        $potentialImpact.lifestyle = '—'
        $potentialImpact.family_responsibility = '—'
        $er = [ordered]@{ cash = $null; investments = $null; income = $null; employer_benefits = $null; social_security = $null; existing_insurance = $null; family_support = $null }
        $existingProtection = '风险不成立，无需评估对冲。'
        $coverageAssessment = [ordered]@{ protected_amount = $null; unprotected_amount = 0.0; confidence = 1.0; liquidity_constraint = '风险不成立，无剩余暴露。' }
        $impactEstimate = [ordered]@{ amount = 0.0; range = [ordered]@{ low = 0.0; high = 0.0 }; confidence = 1.0 }
        $evidenceList = (@($evidence | ForEach-Object { [string]$_.evidence_id }) -join '、')
        $reasoning = ([string]$reasonTpl.NOT_IDENTIFIED).Replace('{evidence_list}', $evidenceList).Replace('{domain}', $did)
        $conclusion = ([string]$conclTpl.NOT_IDENTIFIED).Replace('{domain}', $did)

        $notIdentList.Add($did)
    }

    # 合并推导 assumptions 去重到阶段
    foreach ($a in $candAssumptions) {
        $fk = [string](Get-RaMember -Object $a -Name 'field')
        if (-not $topAssumptionKeys.Contains($fk)) {
            $topAssumptionKeys.Add($fk)
            $topAssumptions.Add($a)
        }
    }

    $risk = [pscustomobject][ordered]@{
        risk_id = $did + '-001'
        risk_category = $did
        risk_name = $riskName
        risk_exists = $exists
        status = $riskStatus
        trigger = [ordered]@{ event = [string](Get-RaMember -Object $cand -Name 'trigger').event }
        exposure = [ordered]@{ why_exposed = [string](Get-RaMember -Object $cand -Name 'exposure').why_exposed }
        potential_impact = $potentialImpact
        impact_estimate = $impactEstimate
        existing_resources = $er
        existing_protection = $existingProtection
        coverage_assessment = $coverageAssessment
        residual_risk = $residual
        severity = $severity
        likelihood = $likelihood
        priority = $prio
        reasoning = $reasoning
        conclusion = $conclusion
        reason = ($reasoning + "，所以" + $conclusion)
        reasoning_evidence_refs = @($refs)
        evidence = @($evidence)
        assumptions = @($candAssumptions)
        unknowns = @($candUnknowns)
        next_information_needed = @($candNext)
    }
    $risks.Add($risk)
    $matrix.Add([pscustomobject][ordered]@{
        risk_id = $risk.risk_id; risk_category = $did; severity = $severity; likelihood = $likelihood; residual_risk = $residual; priority = $prio
    })
}

# ------------------------------------------------------------------ top_priorities
$prioOrder = @('P0', 'P1', 'P2', 'P3')
$sortedRisks = @($risks | Sort-Object -Property @{Expression = { [int]$prioRank[$_.priority] }}, @{Expression = { [int]$resRank[$_.residual_risk] } } -Descending)
$topPriorities = [System.Collections.Generic.List[object]]::new()
$qi = 0
foreach ($r in $sortedRisks) {
    if ([string]$r.priority -eq 'P3' -and $qi -ge 3) { continue }
    $topPriorities.Add([pscustomobject][ordered]@{
        risk_id = $r.risk_id
        priority = $r.priority
        reason = '剩余风险 ' + [string]$r.residual_risk + '、严重度 ' + [string]$r.severity + '、发生概率 ' + [string]$r.likelihood + '。'
    })
    $qi++
    if ($qi -ge 5) { break }
}

# ------------------------------------------------------------------ 前向合并 unknowns / assumptions / next
$stageUnknowns = [System.Collections.Generic.List[object]]::new()
$unkFields = [System.Collections.Generic.HashSet[string]]::new()
foreach ($u in @(Get-RaMember -Object $discDoc -Name 'unknowns')) {
    if ($null -eq $u) { continue }
    $f = [string](Get-RaMember -Object $u -Name 'field')
    if ($unkFields.Contains($f)) { continue }
    [void]$unkFields.Add($f)
    $stageUnknowns.Add($u)
}
$stageNext = [System.Collections.Generic.List[object]]::new()
$nextFields = [System.Collections.Generic.HashSet[string]]::new()
foreach ($q in @(Get-RaMember -Object $discDoc -Name 'next_information_needed')) {
    if ($null -eq $q) { continue }
    $f = [string](Get-RaMember -Object $q -Name 'field')
    if ($nextFields.Contains($f)) { continue }
    [void]$nextFields.Add($f)
    $stageNext.Add($q)
}
# 合并 sufficiency 的
if (-not [string]::IsNullOrWhiteSpace($SufficiencyJsonPath) -and (Test-Path -LiteralPath $SufficiencyJsonPath)) {
    $suffDoc = (Get-Content -LiteralPath $SufficiencyJsonPath -Raw -Encoding UTF8) | ConvertFrom-Json
    foreach ($q in @(Get-RaMember -Object $suffDoc -Name 'next_information_needed')) {
        if ($null -eq $q) { continue }
        $f = [string](Get-RaMember -Object $q -Name 'field')
        if ($nextFields.Contains($f)) { continue }
        [void]$nextFields.Add($f)
        $stageNext.Add($q)
    }
}

# $precedence 已在上方（line ~168）由 shared rules 载入，此处不再硬编码
function Get-RaPrecIndex { param([string]$S) $i = [array]::IndexOf($precedence, $S); if ($i -lt 0) { $i = 99 }; return $i }
$analysisStatus = 'FORMAL'
$discStatusIn = [string](Get-RaMember -Object $discDoc -Name 'analysis_status')
if (-not [string]::IsNullOrWhiteSpace($discStatusIn)) { $analysisStatus = $discStatusIn }
if (-not [string]::IsNullOrWhiteSpace($SufficiencyJsonPath) -and (Test-Path -LiteralPath $SufficiencyJsonPath)) {
    $suffStatus = [string](Get-RaMember -Object $suffDoc -Name 'analysis_status')
    if (-not [string]::IsNullOrWhiteSpace($suffStatus)) {
        if ((Get-RaPrecIndex $suffStatus) -lt (Get-RaPrecIndex $analysisStatus)) { $analysisStatus = $suffStatus }
    }
}

# ------------------------------------------------------------------ family overview
$topStr = (@($topPriorities | ForEach-Object { [string]$_.risk_id + '(' + [string]$_.priority + ')' }) -join '、')
if ([string]::IsNullOrWhiteSpace($topStr)) { $topStr = '无' }
$identStr = if (@($identifiedList).Count -eq 0) { '无' } else { (@($identifiedList) -join '/') }
$notIdentStr = if (@($notIdentList).Count -eq 0) { '无' } else { (@($notIdentList) -join '/') }
$undetStr = if (@($undetList).Count -eq 0) { '无' } else { (@($undetList) -join '/') }
$familyOverview = $overviewTpl
$familyOverview = $familyOverview.Replace('{scopes}', (@($scope) -join '/'))
$familyOverview = $familyOverview.Replace('{identified}', $identStr)
$familyOverview = $familyOverview.Replace('{not_identified}', $notIdentStr)
$familyOverview = $familyOverview.Replace('{undetermined}', $undetStr)
$familyOverview = $familyOverview.Replace('{status}', $analysisStatus)
$familyOverview = $familyOverview.Replace('{top_priorities}', $topStr)

# ------------------------------------------------------------------ emit
$result = [ordered]@{
    stage = 'analysis'
    stage_version = '1.0'
    rules_version = [string]$rules.scoring_version
    scoring_method = [string]$rules.scoring_method
    analysis_status = $analysisStatus
    risk_analysis = [ordered]@{ method = [string]$rules.scoring_method }
    risks = @($risks)
    risk_matrix = @($matrix)
    top_priorities = @($topPriorities)
    family_risk_overview = $familyOverview
    unknowns = @($stageUnknowns)
    assumptions = @($topAssumptions)
    next_information_needed = @($stageNext)
    guardrails = [ordered]@{
        product_recommendation_included = $false
        sales_language_detected = $false
        layer_note = 'risk_analysis 层 · analysis 阶段：仅量化风险与优先级，不涉及任何保险产品建议。'
    }
}

$json = $result | ConvertTo-Json -Depth 32
[System.IO.File]::WriteAllText($OutputJsonPath, $json, [System.Text.UTF8Encoding]::new($true))

# ---- stdout summary ----
Write-Output ('ANALYSIS_STATUS=' + $analysisStatus)
foreach ($r in $risks) {
    Write-Output ('RISK ' + $r.risk_id + ' exists=' + $r.risk_exists + ' sev=' + $r.severity + ' lik=' + $r.likelihood + ' residual=' + $r.residual_risk + ' prio=' + $r.priority + ' impact=' + $r.impact_estimate.amount + ' conf=' + $r.impact_estimate.confidence)
}
Write-Output ('TOP_PRIORITIES=' + $topStr)
Write-Output ('OUTPUT=' + $OutputJsonPath)

exit 0
