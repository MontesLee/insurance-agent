#requires -Version 5.1
<#
    invoke-risk-analysis-sufficiency.ps1
    -------------------------------------
    risk-analysis · Stage: Sufficiency（信息充分性检查）

    输入：RiskAnalysisInput   [schemas/risk-analysis-input.schema.json]
    输出：Sufficiency 阶段结果（JSON，UTF-8 BOM）
          其中 sufficiency / next_information_needed 两段严格符合
          schemas/risk-analysis-output.schema.json 的对应子结构。

    判定方法：risk_dependency_graph_v1（不使用单一百分比）
      - 每个风险域有独立依赖图（required / important / optional）
      - 任一 required 未满足 → 该域 INSUFFICIENT，与总分无关
      - 域冲突 → CONFLICTING，整体 CONFLICTING_INFORMATION
      - 追问按 Expected Information Value 排序，每轮 ≤ max_questions_per_round

    规则全部外置于 resources/config/risk-sufficiency.rules.json，
    本脚本只做确定性计算，不含任何业务判断硬编码，不依赖 LLM。
#>
param(
    [Parameter(Mandatory = $true)][string]$InputJsonPath,
    [Parameter(Mandatory = $true)][string]$OutputJsonPath,
    [string]$RulesPath = ''
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

function Test-RaFieldSatisfied {
    param($Entry, [string[]]$SatisfiedStatus)
    if ($null -eq $Entry) { return $false }
    if ($SatisfiedStatus -notcontains $Entry.status) { return $false }
    $v = $Entry.value
    if ($null -eq $v) { return $false }
    if ($v -is [string] -and [string]::IsNullOrWhiteSpace([string]$v)) { return $false }
    return $true
}

# ------------------------------------------------------------------ load
$skillRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($RulesPath)) {
    $rulesPath = Join-Path $skillRoot 'resources'
    $rulesPath = Join-Path $rulesPath 'config'
    $rulesPath = Join-Path $rulesPath 'risk-sufficiency.rules.json'
}

if (-not (Test-Path -LiteralPath $rulesPath)) { throw "rules file not found: $rulesPath" }
if (-not (Test-Path -LiteralPath $InputJsonPath)) { throw "input not found: $InputJsonPath" }

$rules   = (Get-Content -LiteralPath $rulesPath -Raw -Encoding UTF8) | ConvertFrom-Json
$raInput = (Get-Content -LiteralPath $InputJsonPath -Raw -Encoding UTF8) | ConvertFrom-Json

$satStatus       = Get-RaStringArray -Value $rules.status_satisfied
$sufficientScore = [double](Get-RaMember -Object $rules.thresholds -Name 'sufficient_score')
$groups          = Get-RaMember -Object $rules -Name 'groups'

# ------------------------------------------------------------------ field map
# 单一真源：resources/config/risk-sufficiency.rules.json#profile_names
# （Phase 9 Review：此前三个引擎各硬编码一份 profile 列表，规则文件另有 field_profile_index 未被消费）
$profileNames = @(Get-RaStringArray -Value $rules.profile_names)
if (@($profileNames).Count -eq 0) { throw "rules 缺 profile_names：不得回退硬编码（会造成规则外置假象）" }

$fieldMap = @{}
foreach ($pn in $profileNames) {
    $prof = Get-RaMember -Object $raInput.client_state -Name $pn
    if ($null -eq $prof) { continue }
    foreach ($prop in $prof.PSObject.Properties) {
        $fname = [string]$prop.Name
        if ($fieldMap.ContainsKey($fname)) { continue }
        $fv = $prop.Value
        $st = [string](Get-RaMember -Object $fv -Name 'status')
        if ([string]::IsNullOrWhiteSpace($st)) { $st = 'UNKNOWN' }
        $fieldMap[$fname] = [pscustomobject]@{
            field      = $fname
            profile    = $pn
            value      = Get-RaMember -Object $fv -Name 'value'
            status     = $st
            confidence = Get-RaMember -Object $fv -Name 'confidence'
            note       = Get-RaMember -Object $fv -Name 'note'
        }
    }
}

# ------------------------------------------------------------------ conflicts
$conflictFieldSet  = [System.Collections.Generic.HashSet[string]]::new()
$conflictReasonMap = @{}
foreach ($c in @(Get-RaMember -Object $raInput.client_state -Name 'conflicts')) {
    if ($null -eq $c) { continue }
    $f = [string](Get-RaMember -Object $c -Name 'field')
    if ([string]::IsNullOrWhiteSpace($f)) { continue }
    [void]$conflictFieldSet.Add($f)
    $conflictReasonMap[$f] = [string](Get-RaMember -Object $c -Name 'reason')
}

# ------------------------------------------------------------------ scope
$scope = Get-RaStringArray -Value $raInput.analysis_scope
if ($scope.Count -eq 0) { $scope = @('R1', 'R2', 'R3', 'R4', 'R5') }

$domainResults   = [System.Collections.Generic.List[object]]::new()
$allBlocking     = [System.Collections.Generic.HashSet[string]]::new()
$allConflict     = [System.Collections.Generic.HashSet[string]]::new()
$fieldDomainMap  = @{}   # field -> List[domain]
$fieldTierMap    = @{}   # "domain|field" -> max weight
$scoreSum        = 0.0

$tierWeights = Get-RaMember -Object $rules -Name 'tier_weights'

foreach ($did in $scope) {
    $spec = Get-RaMember -Object $rules.domains -Name $did
    if ($null -eq $spec) { continue }

    $blockingHere  = [System.Collections.Generic.HashSet[string]]::new()
    $conflictsHere = [System.Collections.Generic.HashSet[string]]::new()
    $weightSum     = 0.0
    $earnedSum     = 0.0

    foreach ($tier in @('required', 'important', 'optional')) {
        $tierSpec = Get-RaMember -Object $spec -Name $tier
        if ($null -eq $tierSpec) { continue }
        $w = [double](Get-RaMember -Object $tierWeights -Name $tier)

        # --- 单字段 ---
        foreach ($f in (Get-RaStringArray -Value (Get-RaMember -Object $tierSpec -Name 'fields'))) {
            if (-not $fieldDomainMap.ContainsKey($f)) { $fieldDomainMap[$f] = [System.Collections.Generic.List[string]]::new() }
            if (-not $fieldDomainMap[$f].Contains($did)) { $fieldDomainMap[$f].Add($did) }
            $key = "$did|$f"
            if (-not $fieldTierMap.ContainsKey($key) -or $fieldTierMap[$key] -lt $w) { $fieldTierMap[$key] = $w }

            $weightSum += $w
            $entry = if ($fieldMap.ContainsKey($f)) { $fieldMap[$f] } else { $null }
            if (Test-RaFieldSatisfied -Entry $entry -SatisfiedStatus $satStatus) {
                $earnedSum += $w
            }
            elseif ($tier -eq 'required') {
                [void]$blockingHere.Add($f)
            }
            if ($conflictFieldSet.Contains($f)) { [void]$conflictsHere.Add($f) }
        }

        # --- any_of 组 ---
        foreach ($g in (Get-RaStringArray -Value (Get-RaMember -Object $tierSpec -Name 'groups'))) {
            $gspec   = Get-RaMember -Object $groups -Name $g
            $members = Get-RaStringArray -Value (Get-RaMember -Object $gspec -Name 'any_of')
            $weightSum += $w
            $anySatisfied = $false
            foreach ($m in $members) {
                if (-not $fieldDomainMap.ContainsKey($m)) { $fieldDomainMap[$m] = [System.Collections.Generic.List[string]]::new() }
                if (-not $fieldDomainMap[$m].Contains($did)) { $fieldDomainMap[$m].Add($did) }
                $key = "$did|$m"
                if (-not $fieldTierMap.ContainsKey($key) -or $fieldTierMap[$key] -lt $w) { $fieldTierMap[$key] = $w }

                $entry = if ($fieldMap.ContainsKey($m)) { $fieldMap[$m] } else { $null }
                if (Test-RaFieldSatisfied -Entry $entry -SatisfiedStatus $satStatus) { $anySatisfied = $true }
                if ($conflictFieldSet.Contains($m)) { [void]$conflictsHere.Add($m) }
            }
            if ($anySatisfied) {
                $earnedSum += $w
            }
            elseif ($tier -eq 'required') {
                foreach ($m in $members) { [void]$blockingHere.Add($m) }
            }
        }
    }

    $dScore = if ($weightSum -gt 0) { [math]::Round($earnedSum / $weightSum, 4) } else { 0.0 }

    $dStatus = 'PARTIAL'
    if ($conflictsHere.Count -gt 0) { $dStatus = 'CONFLICTING' }
    elseif ($blockingHere.Count -gt 0) { $dStatus = 'INSUFFICIENT' }
    elseif ($dScore -ge $sufficientScore) { $dStatus = 'SUFFICIENT' }

    foreach ($b in $blockingHere)  { [void]$allBlocking.Add($b) }
    foreach ($c in $conflictsHere) { [void]$allConflict.Add($c) }
    $scoreSum += $dScore

    $domainResults.Add([pscustomobject][ordered]@{
        risk_category   = $did
        score           = $dScore
        status          = $dStatus
        blocking_fields = @($blockingHere  | Sort-Object)
        conflict_fields = @($conflictsHere | Sort-Object)
    })
}

# ------------------------------------------------------------------ overall
$statuses = @($domainResults | ForEach-Object { $_.status })
if ($statuses -contains 'CONFLICTING') { $suffStatus = 'CONFLICTING' }
elseif ($statuses -contains 'INSUFFICIENT') { $suffStatus = 'INSUFFICIENT' }
elseif (@($statuses | Where-Object { $_ -ne 'SUFFICIENT' }).Count -eq 0) { $suffStatus = 'SUFFICIENT' }
else { $suffStatus = 'PARTIAL' }

$suffScore = if ($domainResults.Count -gt 0) { [math]::Round($scoreSum / $domainResults.Count, 4) } else { 0.0 }
$analysisStatus = [string](Get-RaMember -Object $rules.analysis_status_rules.by_sufficiency_status -Name $suffStatus)
if ([string]::IsNullOrWhiteSpace($analysisStatus)) { $analysisStatus = 'PRELIMINARY' }

# ------------------------------------------------------------------ unknowns / assumptions
$unknowns    = [System.Collections.Generic.List[object]]::new()
$assumptions = [System.Collections.Generic.List[object]]::new()

$missingIndex = @{}
foreach ($m in @(Get-RaMember -Object $raInput.client_state -Name 'missing_from_upstream')) {
    if ($null -eq $m) { continue }
    $missingIndex[[string](Get-RaMember -Object $m -Name 'field')] = [string](Get-RaMember -Object $m -Name 'reason')
}

foreach ($f in ($fieldDomainMap.Keys | Sort-Object)) {
    $entry = if ($fieldMap.ContainsKey($f)) { $fieldMap[$f] } else { $null }
    $st = if ($null -eq $entry) { 'UNKNOWN' } else { $entry.status }
    if ([string]::IsNullOrWhiteSpace($st)) { $st = 'UNKNOWN' }

    if ($st -eq 'UNKNOWN') {
        $reason = if ($missingIndex.ContainsKey($f)) {
            'MISSING_FROM_UPSTREAM: ' + $missingIndex[$f]
        } else {
            '上游未提供该字段（status=UNKNOWN）。不得推断、不得用默认值替代。'
        }
        $unknowns.Add([pscustomobject][ordered]@{ field = $f; reason = $reason })
    }
    elseif (@('ESTIMATED', 'ASSUMED', 'INFERRED') -contains $st) {
        $noteText = [string]$entry.note
        $reason = if (-not [string]::IsNullOrWhiteSpace($noteText)) {
            $noteText
        } else {
            '状态为 ' + $st + ' 但未填写依据（note），unknown_integrity 检查将判定不合规。'
        }
        $assumptions.Add([pscustomobject][ordered]@{
            field      = $f
            assumption = '当前取值：' + [string]$entry.value
            reason     = $reason
        })
    }
}

# ------------------------------------------------------------------ EIV 追问
$eivCfg          = Get-RaMember -Object $rules -Name 'eiv'
$maxQuestions    = [int]$eivCfg.max_questions_per_round
$blockingMult    = [double]$eivCfg.blocking_multiplier
$nonBlockingMult = [double]$eivCfg.non_blocking_multiplier
$spreadBase      = [double]$eivCfg.cross_domain_base
$spreadStep      = [double]$eivCfg.cross_domain_step
$spreadCap       = [double]$eivCfg.cross_domain_cap
$conflictBonus   = [double]$eivCfg.conflict_bonus
$normalizer      = [double]$eivCfg.normalizer
$statusFactorCfg = Get-RaMember -Object $eivCfg -Name 'status_factor'
$thrHigh         = [double](Get-RaMember -Object $eivCfg.priority_thresholds -Name 'HIGH')
$thrMedium       = [double](Get-RaMember -Object $eivCfg.priority_thresholds -Name 'MEDIUM')

$candidates = [System.Collections.Generic.List[object]]::new()

foreach ($f in ($fieldDomainMap.Keys | Sort-Object)) {
    $entry = if ($fieldMap.ContainsKey($f)) { $fieldMap[$f] } else { $null }
    $st    = if ($null -eq $entry) { 'UNKNOWN' } else { $entry.status }
    if ([string]::IsNullOrWhiteSpace($st)) { $st = 'UNKNOWN' }

    $satisfied  = Test-RaFieldSatisfied -Entry $entry -SatisfiedStatus $satStatus
    $isConflict = $conflictFieldSet.Contains($f)
    # 只问"缺失"或"冲突"的信息；已满足（KNOWN/ESTIMATED/…）不进追问列表
    if ($satisfied -and -not $isConflict) { continue }

    $sfProp = $statusFactorCfg.PSObject.Properties[$st]
    $sf = if ($null -ne $sfProp) { [double]$sfProp.Value } else { 1.0 }
    if ($isConflict -and $sf -le 0) { $sf = 1.0 }

    $domains = @($fieldDomainMap[$f] | Sort-Object)
    $tierW = 0.0
    foreach ($d in $domains) {
        $k = "$d|$f"
        if ($fieldTierMap.ContainsKey($k) -and $fieldTierMap[$k] -gt $tierW) { $tierW = $fieldTierMap[$k] }
    }

    $mult   = if ($allBlocking.Contains($f)) { $blockingMult } else { $nonBlockingMult }
    $spread = [math]::Min($spreadBase + $spreadStep * ($domains.Count - 1), $spreadCap)
    $bonus  = if ($isConflict) { $conflictBonus } else { 0.0 }

    $raw = $tierW * $mult * $spread * $sf + $bonus
    $eiv = [math]::Min([math]::Round($raw / $normalizer, 4), 1.0)

    $prio = 'LOW'
    if ($eiv -ge $thrHigh) { $prio = 'HIGH' }
    elseif ($eiv -ge $thrMedium) { $prio = 'MEDIUM' }

    $candidates.Add([pscustomobject][ordered]@{
        field         = $f
        status        = $st
        eiv           = $eiv
        priority      = $prio
        affects_risks = $domains
        is_conflict   = $isConflict
    })
}

$templates = Get-RaMember -Object $rules -Name 'question_templates'
$fallback  = Get-RaMember -Object $rules -Name 'fallback_question_template'

$selected = @($candidates | Sort-Object -Property @{Expression = 'eiv'; Descending = $true }, @{Expression = 'field'; Ascending = $true} | Select-Object -First $maxQuestions)

$questions = [System.Collections.Generic.List[object]]::new()
$idx = 1
foreach ($c in $selected) {
    $tpl = Get-RaMember -Object $templates -Name $c.field
    if ($null -eq $tpl) { $tpl = $fallback }
    $qText = [string](Get-RaMember -Object $tpl -Name 'question')
    $wText = [string](Get-RaMember -Object $tpl -Name 'why_needed')
    if ([string]::IsNullOrWhiteSpace($qText)) { $qText = '请补充字段 ' + $c.field + ' 的具体信息？' }
    if ([string]::IsNullOrWhiteSpace($wText)) { $wText = '该字段参与至少一个在范围内的风险域判定。' }
    $qText = $qText.Replace('{field}', $c.field)
    $wText = $wText.Replace('{field}', $c.field)
    if ($c.is_conflict) {
        $cr = if ($conflictReasonMap.ContainsKey($c.field)) { $conflictReasonMap[$c.field] } else { '存在不一致取值' }
        $wText = '【冲突待澄清：' + $cr + '】' + $wText
    }

    $questions.Add([pscustomobject][ordered]@{
        question_id                = ('Q{0:D3}' -f $idx)
        question                   = $qText
        why_needed                 = $wText
        affects_risks              = @($c.affects_risks)
        priority                   = $c.priority
        expected_information_value = $c.eiv
    })
    $idx++
}

# ------------------------------------------------------------------ missing_from_upstream
# 上游与本阶段可能就同一缺失各记一条（如 requirement-analysis 未提供）→ 按 source+field 去重，
# 避免下游读到重复条目后重复追问。
$mfuRaw = [System.Collections.Generic.List[object]]::new()
foreach ($m in @(Get-RaMember -Object $raInput.client_state -Name 'missing_from_upstream')) {
    if ($null -eq $m) { continue }
    $mfuRaw.Add([pscustomobject][ordered]@{
        source = 'client-intake'
        field  = [string](Get-RaMember -Object $m -Name 'field')
        reason = [string](Get-RaMember -Object $m -Name 'reason')
    })
}
$upCI = Get-RaMember -Object $raInput.upstream -Name 'client_intake'
if ($null -ne $upCI -and -not [bool](Get-RaMember -Object $upCI -Name 'provided')) {
    $mfuRaw.Add([pscustomobject][ordered]@{
        source = 'client-intake'
        field  = 'client_state'
        reason = 'MISSING_FROM_UPSTREAM: 未提供 client-intake CLIENT_PROFILE，ClientState 全字段降级为 UNKNOWN。'
    })
}
$upRA = Get-RaMember -Object $raInput.upstream -Name 'requirement_analysis'
if ($null -eq $upRA -or -not [bool](Get-RaMember -Object $upRA -Name 'provided')) {
    $mfuRaw.Add([pscustomobject][ordered]@{
        source = 'requirement-analysis'
        field  = 'requirements'
        reason = 'MISSING_FROM_UPSTREAM: 未提供 requirement-analysis 输出，requirements 视为空；不阻塞风险分析（事实层仍完整）。'
    })
}

$mfu = [System.Collections.Generic.List[object]]::new()
$mfuSeen = [System.Collections.Generic.HashSet[string]]::new()
foreach ($m in $mfuRaw) {
    $key = [string]$m.source + '|' + [string]$m.field
    if ($mfuSeen.Add($key)) { $mfu.Add($m) }
}

# ------------------------------------------------------------------ emit
$result = [ordered]@{
    stage          = 'sufficiency'
    stage_version  = '1.0'
    rules_version  = [string]$rules.rules_version
    analysis_status = $analysisStatus
    sufficiency    = [ordered]@{
        sufficiency_status = $suffStatus
        method             = [string]$rules.method
        sufficiency_score  = $suffScore
        domain_results     = @($domainResults)
        blocking_fields    = @($allBlocking | Sort-Object)
        conflict_fields    = @($allConflict | Sort-Object)
    }
    unknowns               = @($unknowns)
    assumptions            = @($assumptions)
    next_information_needed = @($questions)
    missing_from_upstream  = @($mfu)
    guardrails             = [ordered]@{
        product_recommendation_included = $false
        sales_language_detected         = $false
        layer_note                      = 'risk_analysis 层 · sufficiency 阶段：仅做信息充分性判定与追问规划，不涉及任何保险产品建议。'
    }
}

$json = $result | ConvertTo-Json -Depth 24
[System.IO.File]::WriteAllText($OutputJsonPath, $json, [System.Text.UTF8Encoding]::new($true))

# ---- stdout summary（CI 友好，落盘读取）----
Write-Output ('SUFFICIENCY_STATUS=' + $suffStatus)
Write-Output ('ANALYSIS_STATUS=' + $analysisStatus)
Write-Output ('SUFFICIENCY_SCORE=' + $suffScore)
foreach ($dr in $domainResults) {
    Write-Output ('DOMAIN ' + $dr.risk_category + ' score=' + $dr.score + ' status=' + $dr.status + ' blocking=' + ($dr.blocking_fields -join ','))
}
Write-Output ('BLOCKING_FIELDS=' + (@($allBlocking | Sort-Object) -join ','))
Write-Output ('CONFLICT_FIELDS=' + (@($allConflict | Sort-Object) -join ','))
Write-Output ('QUESTION_COUNT=' + @($questions).Count)
foreach ($q in $questions) {
    Write-Output ('Q ' + $q.question_id + ' eiv=' + $q.expected_information_value + ' prio=' + $q.priority + ' affects=' + ($q.affects_risks -join ',') + ' | ' + $q.question)
}
Write-Output ('OUTPUT=' + $OutputJsonPath)

exit 0
