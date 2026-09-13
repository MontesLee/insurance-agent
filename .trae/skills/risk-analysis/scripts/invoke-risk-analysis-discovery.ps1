#requires -Version 5.1
<#
    invoke-risk-analysis-discovery.ps1
    ----------------------------------
    risk-analysis · Stage: Discovery（风险发现）

    输入：RiskAnalysisInput   [schemas/risk-analysis-input.schema.json]
    可选：Sufficiency 阶段产物（用于继承 analysis_status 与追问去重）
    输出：Discovery 阶段结果（JSON，UTF-8 BOM）
          - risk_candidates：R1–R5 的发现结果（IDENTIFIED / NOT_IDENTIFIED / UNDETERMINED）
          - 不产出 severity / likelihood / residual_risk / priority / impact_estimate
            / coverage_assessment / potential_impact（那是 Phase 5 scoring 的职责）

    判定方法：risk_dependency_graph_v1
      - gate.any_of 信号逐条求值 → MATCHED / ABSENT / UNRESOLVED
      - ∃ MATCHED        → IDENTIFIED      (risk_exists = true)
      - ∄ MATCHED ∧ ∃ UNRESOLVED → UNDETERMINED (risk_exists = null)
      - ∄ MATCHED ∧ ∀ ABSENT     → NOT_IDENTIFIED (risk_exists = false)

    规则全部外置于 resources/config/risk-discovery.rules.json（groups 与 question_templates
    复用 risk-sufficiency.rules.json，单一真源）。本脚本只做确定性计算，不依赖 LLM。
#>
param(
    [Parameter(Mandatory = $true)][string]$InputJsonPath,
    [Parameter(Mandatory = $true)][string]$OutputJsonPath,
    [string]$RulesPath = '',
    [string]$SharedRulesPath = '',
    [string]$SufficiencyJsonPath = ''
)

# --- PSScriptRoot 兜底（以 -File 方式被调用时可能为空） ---
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------ helpers
function Get-RdMember {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Get-RdStringArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function ConvertTo-RdNumber {
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

function Test-RdNegative {
    param($Value, [string[]]$Tokens, [string[]]$Prefixes, [string[]]$Substrings)
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
    # 子串否定：客户原话常是整句（"父母有退休金，无需固定赡养" / "不承担赡养"），
    # 整值匹配与前缀匹配都会漏判，导致把"已知不存在"读成"存在"而抬高风险等级。
    foreach ($x in $Substrings) {
        $xl = ([string]$x).ToLowerInvariant()
        if ($xl.Length -gt 0 -and $s.Contains($xl)) { return $true }
    }
    return $false
}

# ------------------------------------------------------------------ load
$skillRoot = Split-Path -Parent $PSScriptRoot
$configDir = Join-Path $skillRoot 'resources'
$configDir = Join-Path $configDir 'config'

if ([string]::IsNullOrWhiteSpace($RulesPath)) {
    $RulesPath = Join-Path $configDir 'risk-discovery.rules.json'
}
if ([string]::IsNullOrWhiteSpace($SharedRulesPath)) {
    $SharedRulesPath = Join-Path $configDir 'risk-sufficiency.rules.json'
}

if (-not (Test-Path -LiteralPath $RulesPath)) { throw "rules file not found: $RulesPath" }
if (-not (Test-Path -LiteralPath $SharedRulesPath)) { throw "shared rules file not found: $SharedRulesPath" }
if (-not (Test-Path -LiteralPath $InputJsonPath)) { throw "input not found: $InputJsonPath" }

$rules  = (Get-Content -LiteralPath $RulesPath -Raw -Encoding UTF8) | ConvertFrom-Json
$shared = (Get-Content -LiteralPath $SharedRulesPath -Raw -Encoding UTF8) | ConvertFrom-Json
$raInput = (Get-Content -LiteralPath $InputJsonPath -Raw -Encoding UTF8) | ConvertFrom-Json

$satStatus    = Get-RdStringArray -Value $rules.status_satisfied
$negTokens    = Get-RdStringArray -Value $rules.negative_tokens
$negPrefixes  = Get-RdStringArray -Value $rules.negative_prefixes
$negSubstr    = Get-RdStringArray -Value $rules.negative_substrings
$units        = Get-RdMember -Object $rules -Name 'number_units'
$labels       = Get-RdMember -Object $rules -Name 'field_labels'
$tpl          = Get-RdMember -Object $rules -Name 'text_templates'
$reasonTpl    = Get-RdMember -Object $rules -Name 'unknown_reason_templates'
$asmDefault   = [string](Get-RdMember -Object $rules -Name 'assumption_reason_default')
$reqMap       = Get-RdMember -Object $rules -Name 'requirement_type_to_domain'
$qCfg         = Get-RdMember -Object $rules -Name 'questioning'

# groups：共享（充分性）+ 本文件专有，同名以本文件为准
$groups = [ordered]@{}
$sharedGroups = Get-RdMember -Object $shared -Name 'groups'
if ($null -ne $sharedGroups) {
    foreach ($p in $sharedGroups.PSObject.Properties) { $groups[$p.Name] = $p.Value }
}
$localGroups = Get-RdMember -Object $rules -Name 'groups'
if ($null -ne $localGroups) {
    foreach ($p in $localGroups.PSObject.Properties) { $groups[$p.Name] = $p.Value }
}

$templates       = Get-RdMember -Object $shared -Name 'question_templates'
$fallbackTpl     = Get-RdMember -Object $shared -Name 'fallback_question_template'
$precedence      = Get-RdStringArray -Value (Get-RdMember -Object $shared.analysis_status_rules -Name 'precedence')
if (@($precedence).Count -eq 0) { throw "shared rules 缺 analysis_status_rules.precedence：不得回退硬编码" }

# ------------------------------------------------------------------ field map
# 单一真源：risk-sufficiency.rules.json#profile_names（不允许本脚本自带一份）
$profileNames = @(Get-RdStringArray -Value (Get-RdMember -Object $shared -Name 'profile_names'))
if (@($profileNames).Count -eq 0) { throw "shared rules 缺 profile_names：不得回退硬编码" }

$fieldMap = @{}
foreach ($pn in $profileNames) {
    $prof = Get-RdMember -Object $raInput.client_state -Name $pn
    if ($null -eq $prof) { continue }
    foreach ($prop in $prof.PSObject.Properties) {
        $fname = [string]$prop.Name
        if ($fieldMap.ContainsKey($fname)) { continue }
        $fv = $prop.Value
        $st = [string](Get-RdMember -Object $fv -Name 'status')
        if ([string]::IsNullOrWhiteSpace($st)) { $st = 'UNKNOWN' }
        $src      = Get-RdMember -Object $fv -Name 'source'
        $origin   = Get-RdMember -Object $src -Name 'origin'
        $oSkill   = [string](Get-RdMember -Object $origin -Name 'skill')
        $oField   = [string](Get-RdMember -Object $origin -Name 'field')
        if (@('client-intake', 'requirement-analysis', 'unknown') -notcontains $oSkill) { $oSkill = 'client-intake' }
        if ([string]::IsNullOrWhiteSpace($oField)) { $oField = $fname }
        $fieldMap[$fname] = [pscustomobject]@{
            field      = $fname
            profile    = $pn
            value      = Get-RdMember -Object $fv -Name 'value'
            status     = $st
            confidence = Get-RdMember -Object $fv -Name 'confidence'
            note       = Get-RdMember -Object $fv -Name 'note'
            origin     = [pscustomobject]@{ skill = $oSkill; field = $oField }
        }
    }
}

# ------------------------------------------------------------------ conflicts
$conflictFieldSet  = [System.Collections.Generic.HashSet[string]]::new()
$conflictReasonMap = @{}
foreach ($c in @(Get-RdMember -Object $raInput.client_state -Name 'conflicts')) {
    if ($null -eq $c) { continue }
    $f = [string](Get-RdMember -Object $c -Name 'field')
    if ([string]::IsNullOrWhiteSpace($f)) { continue }
    [void]$conflictFieldSet.Add($f)
    $conflictReasonMap[$f] = [string](Get-RdMember -Object $c -Name 'reason')
}

# ------------------------------------------------------------------ requirements index
$reqByDomain = @{}
foreach ($r in @(Get-RdMember -Object $raInput -Name 'requirements')) {
    if ($null -eq $r) { continue }
    $rt = [string](Get-RdMember -Object $r -Name 'requirement_type')
    $d  = [string](Get-RdMember -Object $reqMap -Name $rt)
    if ([string]::IsNullOrWhiteSpace($d)) { continue }
    if (-not $reqByDomain.ContainsKey($d)) { $reqByDomain[$d] = [System.Collections.Generic.List[object]]::new() }
    $reqByDomain[$d].Add($r)
}

# ------------------------------------------------------------------ evidence registry
$evidenceList  = [System.Collections.Generic.List[object]]::new()
$evidenceIndex = @{}

function Add-RdEvidence {
    param([string]$Field)
    if ($evidenceIndex.ContainsKey($Field)) { return $evidenceIndex[$Field] }
    if (-not $fieldMap.ContainsKey($Field)) { return $null }
    $e  = $fieldMap[$Field]
    $st = $e.status
    if ($satStatus -notcontains $st) { return $null }
    $v = $e.value
    if ($null -eq $v) { return $null }
    if ($v -is [string] -and [string]::IsNullOrWhiteSpace([string]$v)) { return $null }

    $id = ('E{0:D3}' -f ($evidenceList.Count + 1))
    $label = [string](Get-RdMember -Object $labels -Name $Field)
    if ([string]::IsNullOrWhiteSpace($label)) { $label = $Field }

    $sourceStatus = $st
    if (@('KNOWN', 'UNKNOWN', 'ESTIMATED', 'ASSUMED', 'INFERRED', 'UNVERIFIED') -notcontains $sourceStatus) { $sourceStatus = 'UNVERIFIED' }

    $evidenceList.Add([pscustomobject][ordered]@{
        evidence_id = $id
        fact        = $label + '：' + [string]$v
        source      = [ordered]@{
            layer  = 'client_state'
            field  = $e.profile + '.' + $Field
            origin = [ordered]@{ skill = $e.origin.skill; field = $e.origin.field }
            status = $sourceStatus
        }
    })
    $evidenceIndex[$Field] = $id
    return $id
}

# ------------------------------------------------------------------ signal evaluation
function Get-RdFieldSignalState {
    param($Signal, [string]$Field)
    $res = [pscustomobject]@{
        state             = 'UNRESOLVED'
        matched_fields   = [System.Collections.Generic.List[string]]::new()
        unresolved_fields = [System.Collections.Generic.List[string]]::new()
        absent_fields     = [System.Collections.Generic.List[string]]::new()
    }
    if ($conflictFieldSet.Contains($Field)) { $res.unresolved_fields.Add($Field); return $res }

    $op      = [string](Get-RdMember -Object $Signal -Name 'op')
    $absFlag = [bool](Get-RdMember -Object $Signal -Name 'absent_when_false')

    if (-not $fieldMap.ContainsKey($Field)) { $res.unresolved_fields.Add($Field); return $res }
    $entry = $fieldMap[$Field]
    if ($satStatus -notcontains $entry.status) { $res.unresolved_fields.Add($Field); return $res }

    $v = $entry.value
    if ($null -eq $v) { $res.unresolved_fields.Add($Field); return $res }
    if ($v -is [string] -and [string]::IsNullOrWhiteSpace([string]$v)) { $res.unresolved_fields.Add($Field); return $res }

    $isNeg = Test-RdNegative -Value $v -Tokens $negTokens -Prefixes $negPrefixes -Substrings $negSubstr

    switch -Regex ($op) {
        '^status_satisfied$' {
            if ($isNeg) { $res.state = 'ABSENT'; $res.absent_fields.Add($Field) }
            else { $res.state = 'MATCHED'; $res.matched_fields.Add($Field) }
        }
        '^status_absent$' {
            if ($isNeg) { $res.state = 'MATCHED'; $res.matched_fields.Add($Field) }
            else { $res.state = 'UNRESOLVED'; $res.unresolved_fields.Add($Field) }
        }
        '^numeric_(gt|gte|lt|lte|eq)$' {
            $num = ConvertTo-RdNumber -Value $v -Units $units
            if ($isNeg) { $num = 0.0 }
            if ($null -eq $num) { $res.state = 'UNRESOLVED'; $res.unresolved_fields.Add($Field); break }
            $thr = [double](Get-RdMember -Object $Signal -Name 'value')
            $ok = switch ($op) {
                'numeric_gt'  { $num -gt  $thr }
                'numeric_gte' { $num -ge  $thr }
                'numeric_lt'  { $num -lt  $thr }
                'numeric_lte' { $num -le  $thr }
                'numeric_eq'  { $num -eq  $thr }
                default       { $false }
            }
            if ($ok) { $res.state = 'MATCHED'; $res.matched_fields.Add($Field) }
            elseif ($absFlag) { $res.state = 'ABSENT'; $res.absent_fields.Add($Field) }
            else { $res.state = 'UNRESOLVED'; $res.unresolved_fields.Add($Field) }
        }
        '^string_(in|contains)$' {
            $sv  = ([string]$v).Trim().ToLowerInvariant()
            $lst = Get-RdStringArray -Value (Get-RdMember -Object $Signal -Name 'value')
            $hit = $false
            foreach ($k in $lst) {
                $kk = ([string]$k).Trim().ToLowerInvariant()
                if ([string]::IsNullOrWhiteSpace($kk)) { continue }
                if ($op -eq 'string_in') { if ($sv -eq $kk) { $hit = $true; break } }
                else { if ($sv.Contains($kk)) { $hit = $true; break } }
            }
            if ($hit) { $res.state = 'MATCHED'; $res.matched_fields.Add($Field) }
            elseif ($absFlag) { $res.state = 'ABSENT'; $res.absent_fields.Add($Field) }
            else { $res.state = 'UNRESOLVED'; $res.unresolved_fields.Add($Field) }
        }
        default {
            $res.state = 'UNRESOLVED'; $res.unresolved_fields.Add($Field)
        }
    }
    return $res
}

function Get-RdSignalState {
    param($Signal)
    $group = [string](Get-RdMember -Object $Signal -Name 'group')
    if ([string]::IsNullOrWhiteSpace($group)) {
        $f = [string](Get-RdMember -Object $Signal -Name 'field')
        return (Get-RdFieldSignalState -Signal $Signal -Field $f)
    }

    # 注意：$groups 是 OrderedDictionary，哈希表没有 PSObject.Properties 键，
    # 必须走 ContainsKey + 索引器（PS 5.1 实测坑）。
    $gspec = $null
    if ($groups.Contains($group)) { $gspec = $groups[$group] }
    $members = Get-RdStringArray -Value (Get-RdMember -Object $gspec -Name 'any_of')
    $op      = [string](Get-RdMember -Object $Signal -Name 'op')

    $memberOp = 'status_satisfied'
    if ($op -eq 'group_numeric_gt') { $memberOp = 'numeric_gt' }

    $agg = [pscustomobject]@{
        state             = 'UNRESOLVED'
        matched_fields   = [System.Collections.Generic.List[string]]::new()
        unresolved_fields = [System.Collections.Generic.List[string]]::new()
        absent_fields     = [System.Collections.Generic.List[string]]::new()
    }

    $memberSignal = [pscustomobject]@{
        op                = $memberOp
        value             = Get-RdMember -Object $Signal -Name 'value'
        absent_when_false = Get-RdMember -Object $Signal -Name 'absent_when_false'
    }

    $anyMatched = $false
    $anyUnresolved = $false
    $anyAbsent = $false

    foreach ($m in $members) {
        $r = Get-RdFieldSignalState -Signal $memberSignal -Field $m
        if ($r.state -eq 'MATCHED') {
            $anyMatched = $true
            $agg.matched_fields.Add($m)
        } elseif ($r.state -eq 'ABSENT') {
            $anyAbsent = $true
            $agg.absent_fields.Add($m)
        } else {
            $anyUnresolved = $true
            $agg.unresolved_fields.Add($m)
        }
    }

    if ($anyMatched) { $agg.state = 'MATCHED' }
    elseif ($anyUnresolved) { $agg.state = 'UNRESOLVED' }
    elseif ($anyAbsent) { $agg.state = 'ABSENT' }
    else { $agg.state = 'UNRESOLVED' }

    return $agg
}

function Get-RdFieldLabel {
    param([string]$Field)
    $l = [string](Get-RdMember -Object $labels -Name $Field)
    if ([string]::IsNullOrWhiteSpace($l)) { return $Field }
    return $l
}

# ------------------------------------------------------------------ scope
$scope = Get-RdStringArray -Value $raInput.analysis_scope
if (@($scope).Count -eq 0) { $scope = @('R1', 'R2', 'R3', 'R4', 'R5') }

# ------------------------------------------------------------------ discovery loop
$candidates  = [System.Collections.Generic.List[object]]::new()
$identified  = [System.Collections.Generic.List[string]]::new()
$notIdent    = [System.Collections.Generic.List[string]]::new()
$undet       = [System.Collections.Generic.List[string]]::new()
$stageUnknownFields = @{}   # field -> List[domain]
$stageAssumptionKeys = [System.Collections.Generic.HashSet[string]]::new()
$stageAssumptions = [System.Collections.Generic.List[object]]::new()

foreach ($did in $scope) {
    $spec = Get-RdMember -Object $rules.domains -Name $did
    if ($null -eq $spec) { continue }

    $gateSpec = Get-RdMember -Object $spec -Name 'gate'
    $gateSignals = @(Get-RdMember -Object $gateSpec -Name 'any_of')

    $sigRecords = [System.Collections.Generic.List[object]]::new()
    $matchedList = [System.Collections.Generic.List[object]]::new()
    $absentList  = [System.Collections.Generic.List[object]]::new()
    $unresList   = [System.Collections.Generic.List[object]]::new()

    foreach ($sig in $gateSignals) {
        $st = Get-RdSignalState -Signal $sig
        $rec = [pscustomobject][ordered]@{
            signal_id  = [string](Get-RdMember -Object $sig -Name 'id')
            target     = if (-not [string]::IsNullOrWhiteSpace([string](Get-RdMember -Object $sig -Name 'group'))) { [string](Get-RdMember -Object $sig -Name 'group') } else { [string](Get-RdMember -Object $sig -Name 'field') }
            op         = [string](Get-RdMember -Object $sig -Name 'op')
            state      = $st.state
            fields     = [ordered]@{ matched = @($st.matched_fields); absent = @($st.absent_fields); unresolved = @($st.unresolved_fields) }
            description = [string](Get-RdMember -Object $sig -Name 'description')
        }
        $sigRecords.Add($rec)
        if ($st.state -eq 'MATCHED') { $matchedList.Add($rec) }
        elseif ($st.state -eq 'ABSENT') { $absentList.Add($rec) }
        else { $unresList.Add($rec) }
    }

    $status3 = 'UNDETERMINED'
    if (@($matchedList).Count -gt 0) { $status3 = 'IDENTIFIED' }
    elseif (@($unresList).Count -eq 0 -and @($absentList).Count -gt 0) { $status3 = 'NOT_IDENTIFIED' }

    # ---- evidence ----
    $riskEvidenceIds = [System.Collections.Generic.List[string]]::new()
    $attachFields = [System.Collections.Generic.List[string]]::new()

    if ($status3 -eq 'IDENTIFIED') {
        foreach ($rec in $matchedList) { foreach ($f in $rec.fields.matched) { $attachFields.Add($f) } }
    } elseif ($status3 -eq 'NOT_IDENTIFIED') {
        foreach ($rec in $absentList) { foreach ($f in $rec.fields.absent) { $attachFields.Add($f) } }
    }

    foreach ($f in $attachFields) {
        $eid = Add-RdEvidence -Field $f
        if ($null -ne $eid -and -not $riskEvidenceIds.Contains($eid)) { $riskEvidenceIds.Add($eid) }
    }

    # ---- amplifiers（仅 IDENTIFIED 时求值，避免在风险不成立时制造噪音）----
    $ampRecords = [System.Collections.Generic.List[object]]::new()
    if ($status3 -eq 'IDENTIFIED') {
        foreach ($amp in @(Get-RdMember -Object $spec -Name 'amplifiers')) {
            $ast = Get-RdSignalState -Signal $amp
            $arec = [pscustomobject][ordered]@{
                signal_id   = [string](Get-RdMember -Object $amp -Name 'id')
                target      = if (-not [string]::IsNullOrWhiteSpace([string](Get-RdMember -Object $amp -Name 'group'))) { [string](Get-RdMember -Object $amp -Name 'group') } else { [string](Get-RdMember -Object $amp -Name 'field') }
                op          = [string](Get-RdMember -Object $amp -Name 'op')
                state       = $ast.state
                fields      = [ordered]@{ matched = @($ast.matched_fields); absent = @($ast.absent_fields); unresolved = @($ast.unresolved_fields) }
                description = [string](Get-RdMember -Object $amp -Name 'description')
            }
            $ampRecords.Add($arec)
            if ($ast.state -eq 'MATCHED') {
                foreach ($f in @($ast.matched_fields)) {
                    $eid = Add-RdEvidence -Field $f
                    if ($null -ne $eid -and -not $riskEvidenceIds.Contains($eid)) { $riskEvidenceIds.Add($eid) }
                }
            }
        }
    }

    # ---- exposure text ----
    $joiner = [string](Get-RdMember -Object $tpl -Name 'joiner')
    if ([string]::IsNullOrWhiteSpace($joiner)) { $joiner = '；' }

    $why = ''
    if ($status3 -eq 'IDENTIFIED') {
        $mt = (@($matchedList | ForEach-Object { $_.description })) -join $joiner
        $why = [string](Get-RdMember -Object $tpl -Name 'identified')
        $why = $why.Replace('{matched}', $mt)
        $ampMatched = @($ampRecords | Where-Object { $_.state -eq 'MATCHED' })
        if (@($ampMatched).Count -gt 0) {
            $at = (@($ampMatched | ForEach-Object { $_.description })) -join $joiner
            $ampText = [string](Get-RdMember -Object $tpl -Name 'identified_amplifiers')
            $why = $why + ' ' + $ampText.Replace('{amplifiers}', $at)
        }
    } elseif ($status3 -eq 'NOT_IDENTIFIED') {
        $facts = [System.Collections.Generic.List[string]]::new()
        foreach ($rec in $absentList) {
            foreach ($f in $rec.fields.absent) {
                if ($fieldMap.ContainsKey($f)) {
                    $facts.Add((Get-RdFieldLabel -Field $f) + '：' + [string]$fieldMap[$f].value)
                } else {
                    $facts.Add((Get-RdFieldLabel -Field $f) + '：未提供')
                }
            }
        }
        $why = [string](Get-RdMember -Object $tpl -Name 'not_identified')
        $why = $why.Replace('{absent}', (@($facts) -join $joiner))
    } else {
        $names = [System.Collections.Generic.List[string]]::new()
        foreach ($rec in $unresList) {
            foreach ($f in $rec.fields.unresolved) {
                $nm = Get-RdFieldLabel -Field $f
                if (-not $names.Contains($nm)) { $names.Add($nm) }
            }
        }
        $why = [string](Get-RdMember -Object $tpl -Name 'undetermined')
        $why = $why.Replace('{unresolved}', (@($names) -join '、'))
    }

    # ---- requirement 关注备注（不得单独构成 gate 命中）----
    $reqRefs = [System.Collections.Generic.List[string]]::new()
    if ($reqByDomain.ContainsKey($did)) {
        foreach ($r in $reqByDomain[$did]) {
            $rid = [string](Get-RdMember -Object $r -Name 'requirement_id')
            $reqRefs.Add($rid)
            if ($status3 -ne 'IDENTIFIED') {
                $rt = [string](Get-RdMember -Object $r -Name 'requirement_type')
                $note = [string](Get-RdMember -Object $tpl -Name 'requirement_attention')
                $note = $note.Replace('{requirement_type}', $rt).Replace('{requirement_id}', $rid)
                $why = $why + ' ' + $note
            }
        }
    }

    # ---- status of the risk（证据最弱环节）----
    $riskStatus = 'UNKNOWN'
    if ($status3 -ne 'UNDETERMINED') {
        $rank = @{ 'KNOWN' = 3; 'ESTIMATED' = 2; 'ASSUMED' = 2; 'INFERRED' = 1 }
        $weakest = 99
        $weakName = ''
        foreach ($eid in $riskEvidenceIds) {
            $entry = $null
            foreach ($e in $evidenceList) { if ($e.evidence_id -eq $eid) { $entry = $e; break } }
            if ($null -eq $entry) { continue }
            $s = [string]$entry.source.status
            $rv = if ($rank.ContainsKey($s)) { [int]$rank[$s] } else { 0 }
            if ($rv -lt $weakest) { $weakest = $rv; $weakName = $s }
        }
        if ($weakest -eq 99 -or [string]::IsNullOrWhiteSpace($weakName)) { $riskStatus = 'INFERRED' }
        else { $riskStatus = $weakName }
    }

    # ---- unknowns of this risk ----
    $riskUnknowns = [System.Collections.Generic.List[object]]::new()
    foreach ($rec in $unresList) {
        foreach ($f in $rec.fields.unresolved) {
            if ($conflictFieldSet.Contains($f)) {
                $cr = if ($conflictReasonMap.ContainsKey($f)) { $conflictReasonMap[$f] } else { '存在不一致取值' }
                $reason = [string](Get-RdMember -Object $reasonTpl -Name 'conflict') + '（' + $cr + '）'
            } else {
                $reason = [string](Get-RdMember -Object $reasonTpl -Name 'unresolved')
                $reason = $reason.Replace('{domain}', $did)
            }
            $riskUnknowns.Add([pscustomobject][ordered]@{ field = $f; reason = $reason })
            if (-not $stageUnknownFields.ContainsKey($f)) { $stageUnknownFields[$f] = [System.Collections.Generic.List[string]]::new() }
            if (-not $stageUnknownFields[$f].Contains($did)) { $stageUnknownFields[$f].Add($did) }
        }
    }

    # ---- assumptions of this risk ----
    $riskAssumptions = [System.Collections.Generic.List[object]]::new()
    foreach ($eid in $riskEvidenceIds) {
        $entry = $null
        foreach ($e in $evidenceList) { if ($e.evidence_id -eq $eid) { $entry = $e; break } }
        if ($null -eq $entry) { continue }
        $s = [string]$entry.source.status
        if (@('ESTIMATED', 'ASSUMED', 'INFERRED') -notcontains $s) { continue }
        $fname = [string]$entry.source.field
        if ($fname.Contains('.')) { $fname = $fname.Split('.')[1] }
        $noteText = ''
        if ($fieldMap.ContainsKey($fname)) { $noteText = [string]$fieldMap[$fname].note }
        $reason = if ([string]::IsNullOrWhiteSpace($noteText)) {
            $asmDefault.Replace('{status}', $s)
        } else { $noteText }
        $riskAssumptions.Add([pscustomobject][ordered]@{
            field      = $fname
            assumption = '当前取值：' + [string]($entry.fact.Split('：')[1])
            reason     = $reason
        })
        if (-not $stageAssumptionKeys.Contains($fname)) {
            $stageAssumptionKeys.Add($fname)
            $stageAssumptions.Add([pscustomobject][ordered]@{
                field      = $fname
                assumption = '当前取值：' + [string]($entry.fact.Split('：')[1])
                reason     = $reason
            })
        }
    }

    # ---- next_information_needed of this risk ----
    $riskNext = [System.Collections.Generic.List[object]]::new()
    foreach ($rec in $unresList) {
        foreach ($f in $rec.fields.unresolved) {
            $t = Get-RdMember -Object $templates -Name $f
            if ($null -eq $t) { $t = $fallbackTpl }
            $q = [string](Get-RdMember -Object $t -Name 'question')
            $w = [string](Get-RdMember -Object $t -Name 'why_needed')
            if ([string]::IsNullOrWhiteSpace($q)) { $q = '请补充字段 ' + $f + ' 的具体信息？' }
            if ([string]::IsNullOrWhiteSpace($w)) { $w = '该字段用于判定 ' + $did + ' 是否成立。' }
            $riskNext.Add([pscustomobject][ordered]@{
                field      = $f
                question   = $q.Replace('{field}', $f)
                why_needed = $w.Replace('{field}', $f)
            })
        }
    }

    $riskExists = $null
    if ($status3 -eq 'IDENTIFIED') { $riskExists = $true }
    elseif ($status3 -eq 'NOT_IDENTIFIED') { $riskExists = $false }

    $refs = [System.Collections.Generic.List[string]]::new()
    foreach ($eid in $riskEvidenceIds) { $refs.Add($eid) }
    foreach ($rr in $reqRefs) { $refs.Add($rr) }

    $candidates.Add([pscustomobject][ordered]@{
        risk_id                 = $did + '-001'
        risk_category           = $did
        risk_name               = [string](Get-RdMember -Object $spec -Name 'name')
        risk_name_zh            = [string](Get-RdMember -Object $spec -Name 'name_zh')
        status                  = $riskStatus
        risk_exists             = $riskExists
        discovery_status        = $status3
        trigger                 = [ordered]@{ event = [string](Get-RdMember -Object $spec -Name 'trigger_event') }
        exposure                = [ordered]@{ why_exposed = $why }
        exposure_signals        = @($sigRecords)
        amplifier_signals       = @($ampRecords)
        evidence                = @($evidenceList | Where-Object { $riskEvidenceIds -contains $_.evidence_id })
        reasoning_evidence_refs = @($refs)
        assumptions             = @($riskAssumptions)
        unknowns                = @($riskUnknowns)
        next_information_needed = @($riskNext)
    })

    if ($status3 -eq 'IDENTIFIED') { $identified.Add($did) }
    elseif ($status3 -eq 'NOT_IDENTIFIED') { $notIdent.Add($did) }
    else { $undet.Add($did) }
}

# ------------------------------------------------------------------ stage unknowns
$stageUnknowns = [System.Collections.Generic.List[object]]::new()
foreach ($f in ($stageUnknownFields.Keys | Sort-Object)) {
    $reason = if ($conflictFieldSet.Contains($f)) {
        $cr = if ($conflictReasonMap.ContainsKey($f)) { $conflictReasonMap[$f] } else { '存在不一致取值' }
        [string](Get-RdMember -Object $reasonTpl -Name 'conflict') + '（' + $cr + '）'
    } else {
        [string](Get-RdMember -Object $reasonTpl -Name 'unresolved').Replace('{domain}', (@($stageUnknownFields[$f] | Sort-Object) -join '/'))
    }
    $stageUnknowns.Add([pscustomobject][ordered]@{ field = $f; reason = $reason })
}

# ------------------------------------------------------------------ stage questions
$alreadyAsked = [System.Collections.Generic.HashSet[string]]::new()
if (-not [string]::IsNullOrWhiteSpace($SufficiencyJsonPath) -and (Test-Path -LiteralPath $SufficiencyJsonPath)) {
    $suffDoc = (Get-Content -LiteralPath $SufficiencyJsonPath -Raw -Encoding UTF8) | ConvertFrom-Json
    foreach ($q in @(Get-RdMember -Object $suffDoc -Name 'next_information_needed')) {
        if ($null -eq $q) { continue }
        $qt = [string](Get-RdMember -Object $q -Name 'question')
        foreach ($kv in $templates.PSObject.Properties) {
            if ([string]::IsNullOrWhiteSpace([string]$kv.Value.question)) { continue }
            if ($qt -eq [string]$kv.Value.question) { [void]$alreadyAsked.Add($kv.Name) }
        }
    }
}

$qMax     = [int](Get-RdMember -Object $qCfg -Name 'max_questions')
$qStep    = [double](Get-RdMember -Object $qCfg -Name 'spread_step')
$qCap     = [double](Get-RdMember -Object $qCfg -Name 'spread_cap')
$qNorm    = [double](Get-RdMember -Object $qCfg -Name 'normalizer')
$qThrHigh = [double](Get-RdMember -Object $qCfg.priority_thresholds -Name 'HIGH')
$qThrMed  = [double](Get-RdMember -Object $qCfg.priority_thresholds -Name 'MEDIUM')

$qCands = [System.Collections.Generic.List[object]]::new()
foreach ($f in ($stageUnknownFields.Keys | Sort-Object)) {
    if ($alreadyAsked.Contains($f)) { continue }
    $domains = @($stageUnknownFields[$f] | Sort-Object)
    $spread = [math]::Min(1.0 + $qStep * ($domains.Count - 1), $qCap)
    $rv = [math]::Min([math]::Round(1.0 * $spread / $qNorm, 4), 1.0)
    $prio = 'LOW'
    if ($rv -ge $qThrHigh) { $prio = 'HIGH' }
    elseif ($rv -ge $qThrMed) { $prio = 'MEDIUM' }
    $qCands.Add([pscustomobject][ordered]@{
        field         = $f
        rv            = $rv
        priority      = $prio
        affects_risks = $domains
    })
}

$stageQuestions = [System.Collections.Generic.List[object]]::new()
$qi = 1
foreach ($c in @($qCands | Sort-Object -Property @{Expression = 'rv'; Descending = $true }, @{Expression = 'field'; Ascending = $true} | Select-Object -First $qMax)) {
    $t = Get-RdMember -Object $templates -Name $c.field
    if ($null -eq $t) { $t = $fallbackTpl }
    $q = [string](Get-RdMember -Object $t -Name 'question')
    $w = [string](Get-RdMember -Object $t -Name 'why_needed')
    if ([string]::IsNullOrWhiteSpace($q)) { $q = '请补充字段 ' + $c.field + ' 的具体信息？' }
    if ([string]::IsNullOrWhiteSpace($w)) { $w = '该字段用于判定风险是否成立。' }
    $q = $q.Replace('{field}', $c.field)
    $w = $w.Replace('{field}', $c.field)
    if ($conflictFieldSet.Contains($c.field)) {
        $cr = if ($conflictReasonMap.ContainsKey($c.field)) { $conflictReasonMap[$c.field] } else { '存在不一致取值' }
        $w = '【冲突待澄清：' + $cr + '】' + $w
    } else {
        $w = '【用于判定 ' + (@($c.affects_risks) -join '/') + ' 是否成立】' + $w
    }
    $stageQuestions.Add([pscustomobject][ordered]@{
        question_id                = ('Q{0:D3}' -f $qi)
        question                   = $q
        why_needed                 = $w
        affects_risks              = @($c.affects_risks)
        priority                   = $c.priority
        expected_information_value = $c.rv
    })
    $qi++
}

# ------------------------------------------------------------------ analysis_status
# 基线取充分性阶段结论（未提供时退化为 PRELIMINARY）。
# 早先这里把"无未决、无冲突"硬编码成 PRELIMINARY，导致信息完全充分的用例永远拿不到 FORMAL，
# 与 CONTRACT §7「全部域 SUFFICIENT 且无 conflict → FORMAL」冲突。发现阶段只能**加严**，不能放宽。
$discoveryStatus = 'PRELIMINARY'
$suffStatus = ''
if (-not [string]::IsNullOrWhiteSpace($SufficiencyJsonPath) -and (Test-Path -LiteralPath $SufficiencyJsonPath)) {
    $suffStatus = [string](Get-RdMember -Object $suffDoc -Name 'analysis_status')
    if (-not [string]::IsNullOrWhiteSpace($suffStatus) -and ([array]::IndexOf($precedence, $suffStatus) -ge 0)) {
        $discoveryStatus = $suffStatus
    } else {
        $suffStatus = ''
    }
}

# 加严：存在未决域 → 至少 NEED_MORE_INFORMATION；存在冲突 → 至少 CONFLICTING_INFORMATION
$iCur = [array]::IndexOf($precedence, $discoveryStatus)
if (@($undet).Count -gt 0) {
    $iNeed = [array]::IndexOf($precedence, 'NEED_MORE_INFORMATION')
    if ($iNeed -ge 0 -and ($iCur -lt 0 -or $iNeed -lt $iCur)) { $discoveryStatus = 'NEED_MORE_INFORMATION'; $iCur = $iNeed }
}
if ($conflictFieldSet.Count -gt 0) {
    $iConf = [array]::IndexOf($precedence, 'CONFLICTING_INFORMATION')
    if ($iConf -ge 0 -and ($iCur -lt 0 -or $iConf -lt $iCur)) { $discoveryStatus = 'CONFLICTING_INFORMATION'; $iCur = $iConf }
}

$analysisStatus = $discoveryStatus

# ------------------------------------------------------------------ emit
$result = [ordered]@{
    stage           = 'discovery'
    stage_version   = '1.0'
    rules_version   = [string]$rules.rules_version
    taxonomy_version = [string]$rules.taxonomy_version
    analysis_status = $analysisStatus
    discovery       = [ordered]@{
        method          = [string]$rules.method
        domains_evaluated = @($scope)
        identified      = @($identified)
        not_identified  = @($notIdent)
        undetermined    = @($undet)
    }
    risk_candidates        = @($candidates)
    unknowns               = @($stageUnknowns)
    assumptions            = @($stageAssumptions)
    next_information_needed = @($stageQuestions)
    guardrails             = [ordered]@{
        product_recommendation_included = $false
        sales_language_detected         = $false
        layer_note                      = 'risk_analysis 层 · discovery 阶段：仅判定风险是否成立，不做严重度/优先级评估，不涉及任何保险产品建议。'
    }
}

$json = $result | ConvertTo-Json -Depth 32
[System.IO.File]::WriteAllText($OutputJsonPath, $json, [System.Text.UTF8Encoding]::new($true))

# ---- stdout summary（CI 友好，落盘读取）----
Write-Output ('ANALYSIS_STATUS=' + $analysisStatus)
Write-Output ('IDENTIFIED=' + (@($identified) -join ','))
Write-Output ('NOT_IDENTIFIED=' + (@($notIdent) -join ','))
Write-Output ('UNDETERMINED=' + (@($undet) -join ','))
foreach ($c in $candidates) {
    Write-Output ('RISK ' + $c.risk_id + ' ' + $c.discovery_status + ' exists=' + $c.risk_exists + ' status=' + $c.status + ' evidence=' + (@($c.evidence)).Count + ' refs=' + (@($c.reasoning_evidence_refs) -join '|'))
}
Write-Output ('EVIDENCE_COUNT=' + $evidenceList.Count)
Write-Output ('UNKNOWN_FIELDS=' + (@($stageUnknownFields.Keys | Sort-Object) -join ','))
Write-Output ('QUESTION_COUNT=' + @($stageQuestions).Count)
foreach ($q in $stageQuestions) {
    Write-Output ('Q ' + $q.question_id + ' rv=' + $q.expected_information_value + ' prio=' + $q.priority + ' affects=' + ($q.affects_risks -join ',') + ' | ' + $q.question)
}
Write-Output ('OUTPUT=' + $OutputJsonPath)

exit 0
