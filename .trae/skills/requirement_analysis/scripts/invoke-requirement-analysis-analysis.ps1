[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputJsonPath,
    [string]$OutputJsonPath = ""
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$RuntimeLib = Join-Path $PSScriptRoot "lib\requirement-analysis-runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLib)) { throw "Missing runtime lib: $RuntimeLib" }
. $RuntimeLib

$SufficiencyScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-sufficiency.ps1"
$QuestioningScript = Join-Path $PSScriptRoot "invoke-requirement-analysis-questioning.ps1"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Encoding UTF8 -Path $Path | ConvertFrom-Json)
}

function To-JsonArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    return @($Value)
}

function Get-FactMap {
    param($Facts)
    $map = @{}
    foreach ($fact in (To-JsonArray -Value $Facts)) {
        $map[$fact.field] = $fact
    }
    return $map
}

function Get-FactValue {
    param(
        [string]$Field,
        $FactMap
    )

    if ($FactMap.ContainsKey($Field)) {
        return $FactMap[$Field].value
    }
    return $null
}

function Has-KnownFact {
    param(
        [string]$Field,
        $FactMap
    )

    if (-not $FactMap.ContainsKey($Field)) {
        return $false
    }

    return $FactMap[$Field].value_status -eq "KNOWN"
}

function Get-FactStatus {
    param(
        [string]$Field,
        $FactMap
    )

    if (-not $FactMap.ContainsKey($Field)) {
        return "MISSING"
    }

    return [string]$FactMap[$Field].value_status
}

function Has-UsableFact {
    param(
        [string]$Field,
        $FactMap
    )

    # F1 fix: ESTIMATED / ASSUMED facts are still analyzable evidence.
    # Only MISSING / UNKNOWN should block a requirement type. The reduced
    # confidence is surfaced through evidence.value_status and through an
    # explicit entry in `assumptions`, instead of silently dropping the
    # whole requirement type from risk_map / coverage_gaps / requirements.
    return (@("KNOWN", "ESTIMATED", "ASSUMED") -contains (Get-FactStatus -Field $Field -FactMap $FactMap))
}

function Get-SoftFactFields {
    param(
        $Fields,
        $FactMap
    )

    $soft = New-Object System.Collections.ArrayList
    foreach ($field in (To-JsonArray -Value $Fields)) {
        $status = Get-FactStatus -Field $field -FactMap $FactMap
        if ($status -eq "ESTIMATED" -or $status -eq "ASSUMED") {
            [void]$soft.Add(("{0}({1})" -f $field, $status))
        }
    }
    return ,$soft
}

function Add-SoftFactAssumption {
    param(
        [string]$RequirementType,
        $SoftFields,
        [System.Collections.ArrayList]$Assumptions
    )

    if ($null -eq $SoftFields -or $SoftFields.Count -eq 0) {
        return
    }

    Add-AssumptionEntry -Field $RequirementType `
        -Assumption ("{0} analysis relies on approximate or assumed values: {1}." -f $RequirementType, ($SoftFields -join ", ")) `
        -Reason "Non-KNOWN dependency fields remain analyzable, but conclusion precision is limited and should be refined once exact values are provided." `
        -Assumptions $Assumptions
}

function Get-EvidenceValueStatus {
    param(
        $FactRefs,
        $FactMap
    )

    $statuses = New-Object System.Collections.ArrayList
    foreach ($field in (To-JsonArray -Value $FactRefs)) {
        if ($FactMap.ContainsKey($field)) {
            [void]$statuses.Add($FactMap[$field].value_status)
        }
    }

    if ($statuses -contains "UNKNOWN") { return "UNKNOWN" }
    if ($statuses -contains "ASSUMED") { return "ASSUMED" }
    if ($statuses -contains "ESTIMATED") { return "ESTIMATED" }
    return "KNOWN"
}

# F2 helpers: make life / critical_illness priority value-sensitive instead of
# a binary "has any coverage -> lower priority". Uses the intake gap formulas
# (life need = income*10 + mortgage + 20万/child; CI need = 50万 + income*3).
# Priority model:
#   - client explicitly confirmed ZERO coverage  -> P0_CRITICAL (confirmed, fully
#     unmet, actionable gap)
#   - coverage presence UNKNOWN                  -> P1_HIGH (must confirm before the
#     gap can be judged; NOT more urgent than a confirmed total gap)
#   - coverage present & adequate vs need estimate -> P2_MEDIUM
#   - coverage present but inadequate             -> P1_HIGH
# Confidence (ESTIMATED/UNKNOWN) is surfaced via evidence.value_status and
# assumptions, never by silently changing the priority tier.

function Get-AmountWan {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    $t = [string]$Text
    if ($t -match '(\d+(?:\.\d+)?)\s*(万|w|万元|元|k|千)') {
        $num = [double]$Matches[1]
        switch ([string]$Matches[2]) {
            '万'   { return $num }
            'w'    { return $num }
            '万元' { return $num }
            '元'   { return $num / 10000.0 }
            'k'    { return $num / 10.0 }
            '千'   { return $num / 10.0 }
        }
    }
    return $null
}

function Get-CoverageCategory {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "unknown" }
    $t = [string]$Text
    if ($t -match '从未|没买|没有|未投保|均无|零|none|no coverage|no life|no critical') {
        return "none"
    }
    return "some"
}

function Get-ChildrenCount {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 0 }
    $t = [string]$Text
    if ($t -match '(\d+)\s*(?:个)?\s*child') { return [int]$Matches[1] }
    if ($t -match '(\d+)\s*个孩子') { return [int]$Matches[1] }
    if ($t -match 'one\s+child') { return 1 }
    if ($t -match 'two\s+children') { return 2 }
    if ($t -match 'three\s+children') { return 3 }
    return 0
}

function Get-LifeNeedWan {
    param($FactMap)
    $income = Get-AmountWan -Text (Get-FactValue -Field "annual_income" -FactMap $FactMap)
    $mortgage = Get-AmountWan -Text (Get-FactValue -Field "mortgage_balance" -FactMap $FactMap)
    $children = Get-ChildrenCount -Text (Get-FactValue -Field "children_info" -FactMap $FactMap)
    if ($null -eq $income -or $null -eq $mortgage) { return $null }
    return ($income * 10.0 + $mortgage + $children * 20.0)
}

function Get-CiNeedWan {
    param($FactMap)
    $income = Get-AmountWan -Text (Get-FactValue -Field "annual_income" -FactMap $FactMap)
    if ($null -eq $income) { return $null }
    return (50.0 + $income * 3.0)
}

function Add-RequirementPackage {
    param(
        [string]$RequirementType,
        [string]$RiskExposure,
        [string]$PotentialFinancialImpact,
        [string]$ExistingProtection,
        [string]$CoverageGap,
        [string]$Priority,
        [string]$Reasoning,
        $FactRefs,
        $FactMap,
        [System.Collections.ArrayList]$RiskMap,
        [System.Collections.ArrayList]$CoverageGaps,
        [System.Collections.ArrayList]$Requirements,
        [System.Collections.ArrayList]$Priorities,
        [System.Collections.ArrayList]$Evidence
    )

    $nextIndex = $Requirements.Count + 1
    $evidenceId = ("EV{0:d3}" -f $nextIndex)
    $requirementId = ("REQ{0:d3}" -f $nextIndex)

    [void]$Evidence.Add([pscustomobject]@{
        evidence_id = $evidenceId
        fact_refs = @($FactRefs)
        value_status = (Get-EvidenceValueStatus -FactRefs $FactRefs -FactMap $FactMap)
        reasoning = $Reasoning
        conclusion = ("{0} requirement priority is {1}" -f $RequirementType, $Priority)
    })

    [void]$RiskMap.Add([pscustomobject]@{
        requirement_type = $RequirementType
        risk_exposure = $RiskExposure
        potential_financial_impact = $PotentialFinancialImpact
        existing_protection = $ExistingProtection
        coverage_gap = $CoverageGap
        priority = $Priority
        reasoning = $Reasoning
        evidence_refs = @($evidenceId)
    })

    [void]$CoverageGaps.Add([pscustomobject]@{
        requirement_type = $RequirementType
        gap_summary = $CoverageGap
        priority = $Priority
        evidence_refs = @($evidenceId)
    })

    [void]$Requirements.Add([pscustomobject]@{
        requirement_id = $requirementId
        requirement_type = $RequirementType
        summary = $CoverageGap
        priority = $Priority
        boundary = "requirement_only"
    })

    [void]$Priorities.Add([pscustomobject]@{
        target_id = $requirementId
        priority = $Priority
        reason = $Reasoning
    })
}

function Add-AssumptionEntry {
    param(
        [string]$Field,
        [string]$Assumption,
        [string]$Reason,
        [System.Collections.ArrayList]$Assumptions
    )

    [void]$Assumptions.Add([pscustomobject]@{
        field = $Field
        assumption = $Assumption
        reason = $Reason
    })
}

# ============================================================
# Domain Overlay 支持（Lawgent overlay 模式）
#   overlay 提供每个险种的确定性规则（必填事实 / 证据引用 / 已有保障字段 /
#   缺口公式 / 优先级档位）。overlay 缺失或字段缺失时回退内置默认值，
#   保证分析行为不因配置缺口而崩坏。
# ============================================================

function Get-RaOverlayRoot {
    $d = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($d)) { $d = Split-Path -Parent $MyInvocation.MyCommand.Path }
    if ([string]::IsNullOrWhiteSpace($d)) { return "" }
    $skill = Split-Path -Parent $d
    if ([string]::IsNullOrWhiteSpace($skill)) { return "" }
    return (Join-Path $skill "overlays")
}

function Parse-RaOverlayYaml {
    param([string]$Path)
    $yaml = [ordered]@{}
    $cur  = $null
    foreach ($raw in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $line = $raw -replace '#.*$', ''
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        # 优先匹配带双引号的值，使文本内可安全包含冒号
        if ($line -match '^\s*(\S[^:]*):\s*"(.*)"\s*$') {
            $k = $matches[1].Trim(); $cur = $k
            $yaml[$k] = $matches[2]
            continue
        }
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

$RaScopeToOverlay = @{
    'life'             = 'life'
    'critical_illness' = 'critical-illness'
    'medical'          = 'medical'
    'accident'         = 'accident'
    'savings'          = 'savings'
}

function Get-RaOverlay {
    param([string]$RequirementType)
    $root = Get-RaOverlayRoot
    if ([string]::IsNullOrWhiteSpace($root)) { return $null }
    if (-not $RaScopeToOverlay.ContainsKey($RequirementType)) { return $null }
    $yp = Join-Path (Join-Path $root $RaScopeToOverlay[$RequirementType]) "overlay.yaml"
    if (-not (Test-Path -LiteralPath $yp)) { return $null }
    return (Parse-RaOverlayYaml -Path $yp)
}

function Get-RaOvList {
    param($Overlay, [string]$Key, [string[]]$Default)
    if ($null -eq $Overlay) { return @($Default) }
    $v = $Overlay[$Key]
    if ($null -eq $v) { return @($Default) }
    $arr = @($v | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($arr.Count -eq 0) { return @($Default) }
    return $arr
}

function Get-RaOvStr {
    param($Overlay, [string]$Key, [string]$Default)
    if ($null -eq $Overlay) { return $Default }
    $v = [string]$Overlay[$Key]
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v
}

function Get-RaDomainSpec {
    param([string]$RequirementType)

    $ov = Get-RaOverlay -RequirementType $RequirementType

    switch ($RequirementType) {
        'life' {
            $req  = @('annual_income','family_responsibility','mortgage_balance','children_info','spouse_income')
            $evi  = @('annual_income','family_responsibility','mortgage_balance','children_info','spouse_income','existing_life_coverage')
            $cov  = 'existing_life_coverage'
            $need = 'life_income_x10_mortgage_children20w'
            $rule = 'coverage_value_sensitive'
            $gOk  = 'P2_MEDIUM'; $gNo = 'P1_HIGH'
        }
        'critical_illness' {
            $req  = @('annual_income','family_responsibility')
            $evi  = @('annual_income','family_responsibility','existing_critical_illness_coverage')
            $cov  = 'existing_critical_illness_coverage'
            $need = 'ci_50w_plus_income_x3'
            $rule = 'coverage_value_sensitive'
            $gOk  = 'P2_MEDIUM'; $gNo = 'P1_HIGH'
        }
        'medical' {
            $req  = @('customer_health')
            $evi  = @('customer_health','social_insurance_status','existing_medical_coverage')
            $cov  = 'existing_medical_coverage'
            $need = 'none'
            $rule = 'medical_gate'
            $gOk  = 'P2_MEDIUM'; $gNo = 'P1_HIGH'
        }
        'accident' {
            $req  = @('occupation')
            $evi  = @('occupation','family_responsibility','existing_accident_coverage')
            $cov  = 'existing_accident_coverage'
            $need = 'none'
            $rule = 'accident_gate'
            $gOk  = 'P1_HIGH'; $gNo = 'P2_MEDIUM'
        }
        'savings' {
            $req  = @('annual_income','annual_expense','liabilities','cash_flow','financial_goals')
            $evi  = @('annual_income','annual_expense','liabilities','cash_flow','financial_goals','assets')
            $cov  = 'assets'
            $need = 'none'
            $rule = 'savings_assets_gate'
            $gOk  = 'P2_MEDIUM'; $gNo = 'P1_HIGH'
        }
        default {
            $req = @(); $evi = @(); $cov = ''; $need = 'none'; $rule = 'coverage_value_sensitive'
            $gOk = 'P2_MEDIUM'; $gNo = 'P1_HIGH'
        }
    }

    return [pscustomobject]@{
        RequirementType = $RequirementType
        Overlay         = $ov
        RequiredFields  = (Get-RaOvList -Overlay $ov -Key 'required_fields'    -Default $req)
        EvidenceRefs    = (Get-RaOvList -Overlay $ov -Key 'evidence_fact_refs' -Default $evi)
        CoverageField   = (Get-RaOvStr  -Overlay $ov -Key 'coverage_field'     -Default $cov)
        NeedFormula     = (Get-RaOvStr  -Overlay $ov -Key 'need_formula'       -Default $need)
        PriorityRule    = (Get-RaOvStr  -Overlay $ov -Key 'priority_rule'      -Default $rule)
        PNoInfo         = (Get-RaOvStr  -Overlay $ov -Key 'priority_when_no_coverage_info'   -Default 'P1_HIGH')
        PZero           = (Get-RaOvStr  -Overlay $ov -Key 'priority_when_zero_coverage'      -Default 'P0_CRITICAL')
        PAdequate       = (Get-RaOvStr  -Overlay $ov -Key 'priority_when_adequate'           -Default 'P2_MEDIUM')
        PInadequate     = (Get-RaOvStr  -Overlay $ov -Key 'priority_when_inadequate'         -Default 'P1_HIGH')
        PGateOk         = (Get-RaOvStr  -Overlay $ov -Key 'priority_when_gate_satisfied'     -Default $gOk)
        PGateNo         = (Get-RaOvStr  -Overlay $ov -Key 'priority_when_gate_unsatisfied'   -Default $gNo)
        Texts           = @{
            Risk          = (Get-RaOvStr -Overlay $ov -Key 'risk'           -Default $RaDomainTexts[$RequirementType].Risk)
            Impact        = (Get-RaOvStr -Overlay $ov -Key 'impact'         -Default $RaDomainTexts[$RequirementType].Impact)
            ImpactUnknown = (Get-RaOvStr -Overlay $ov -Key 'impact_unknown' -Default $RaDomainTexts[$RequirementType].ImpactUnknown)
            Gap           = (Get-RaOvStr -Overlay $ov -Key 'gap'            -Default $RaDomainTexts[$RequirementType].Gap)
            Reasoning     = (Get-RaOvStr -Overlay $ov -Key 'reasoning'      -Default $RaDomainTexts[$RequirementType].Reasoning)
        }
    }
}

function Get-RaNeedWan {
    param($Spec, $FactMap)
    switch ($Spec.NeedFormula) {
        'life_income_x10_mortgage_children20w' { return (Get-LifeNeedWan -FactMap $FactMap) }
        'ci_50w_plus_income_x3'                { return (Get-CiNeedWan -FactMap $FactMap) }
        default                                 { return $null }
    }
}

# 各险种结论表述（属措辞层，规则一律来自 overlay）
$RaDomainTexts = @{
    'life' = @{
        Risk     = "Primary earner dependency plus debt and child responsibility create meaningful life-risk exposure."
        Impact   = "Income interruption or death would likely affect mortgage servicing and child-related household obligations."
        Gap      = "Need to evaluate whether family responsibility, mortgage burden and current life protection are aligned."
        Reasoning= "Known income, mortgage and child responsibility indicate a clear dependency on the primary earner. Life priority reflects coverage presence and adequacy: a confirmed zero-coverage client is the most urgent actionable gap, while unknown coverage is a confirmation task rather than a higher tier than a confirmed gap."
    }
    'critical_illness' = @{
        Risk     = "Major illness may create both treatment expenses and income interruption risk."
        Impact   = "Household cash flow and recovery-stage financial pressure may rise materially."
        Gap      = "Need to evaluate whether current critical illness protection is sufficient for recovery-stage income interruption and family responsibility."
        Reasoning= "Income and family responsibility imply a major illness could create treatment costs plus income interruption. CI priority stays high when existing coverage is inadequate against the need estimate (50万 base + income*3), rather than dropping solely because some coverage exists."
    }
    'accident' = @{
        Risk     = "Occupation-related accident exposure may affect earnings continuity and household stability."
        Impact   = "Accident events may cause short-term treatment cost and temporary income disruption."
        Gap      = "Need to confirm whether current accident protection matches occupation exposure and family responsibility."
        Reasoning= "Occupation and family responsibility together determine whether an accident would create meaningful income disruption or liability pressure."
    }
    'medical' = @{
        Risk     = "Household may face medical reimbursement and treatment cost exposure."
        Impact   = "Medical costs and out-of-pocket treatment burden may pressure household cash flow."
        ImpactUnknown = "UNKNOWN: social insurance status is not clear, so self-pay exposure cannot be judged precisely."
        Gap      = "Need to clarify and evaluate medical protection adequacy before formal product-level discussion."
        Reasoning= "Known health information suggests medical protection should be reviewed. Existing protection and social insurance status directly affect the likely reimbursement gap."
    }
    'savings' = @{
        Risk     = "Long-term savings goals may be under-supported if current cash flow and liabilities leave limited room for accumulation."
        Impact   = "Delayed goal achievement may affect education, retirement or other long-horizon plans."
        Gap      = "Need to evaluate whether current cash flow and asset base can support stated long-term savings goals."
        Reasoning= "Savings analysis depends on income, expense, liabilities, cash flow and goals. If asset base is unclear, the direction can still be identified but the adequacy judgment remains incomplete."
    }
}

function Build-DomainAnalysis {
    param(
        [string]$RequirementType,
        $FactMap,
        [System.Collections.ArrayList]$RiskMap,
        [System.Collections.ArrayList]$CoverageGaps,
        [System.Collections.ArrayList]$Requirements,
        [System.Collections.ArrayList]$Priorities,
        [System.Collections.ArrayList]$Evidence,
        [System.Collections.ArrayList]$Assumptions
    )

    $spec = Get-RaDomainSpec -RequirementType $RequirementType
    if ($spec.RequiredFields.Count -eq 0) { return }

    # 必填事实齐备才产出结论（ESTIMATED / ASSUMED 仍可分析；MISSING / UNKNOWN 阻断）
    foreach ($f in $spec.RequiredFields) {
        if (-not (Has-UsableFact -Field $f -FactMap $FactMap)) { return }
    }

    # 措辞优先取自 overlay 的 texts: 小节；缺失时回退内置表（防配置缺口崩坏）
    $texts = $spec.Texts
    if ($null -eq $texts) { $texts = $RaDomainTexts[$RequirementType] }
    $existingProtection = "UNKNOWN"
    $priority = ""

    $hasCoverage = $false
    if (-not [string]::IsNullOrWhiteSpace($spec.CoverageField)) {
        $hasCoverage = (Has-UsableFact -Field $spec.CoverageField -FactMap $FactMap)
    }

    switch ($spec.PriorityRule) {
        'medical_gate' {
            $hasInsStatus = (Has-UsableFact -Field "social_insurance_status" -FactMap $FactMap)
            if ($hasCoverage) {
                $existingProtection = [string](Get-FactValue -Field $spec.CoverageField -FactMap $FactMap)
            }
            $priority = $spec.PGateNo
            if ($hasInsStatus -and $hasCoverage) { $priority = $spec.PGateOk }
        }
        'accident_gate' {
            $hasResp = (Has-UsableFact -Field "family_responsibility" -FactMap $FactMap)
            if ($hasCoverage) {
                $existingProtection = [string](Get-FactValue -Field $spec.CoverageField -FactMap $FactMap)
            }
            $priority = $spec.PGateNo
            if ($hasResp -and -not $hasCoverage) { $priority = $spec.PGateOk }
        }
        'savings_assets_gate' {
            if ($hasCoverage) {
                $existingProtection = ("Known liquid or accumulated assets: {0}" -f (Get-FactValue -Field $spec.CoverageField -FactMap $FactMap))
            } else {
                $existingProtection = "Current asset base is UNKNOWN"
            }
            $priority = $spec.PGateNo
            if ($hasCoverage) { $priority = $spec.PGateOk }
        }
        default {
            # coverage_value_sensitive：按"是否有保障信息 / 零保障 / 足额 / 不足额"四档判定
            $priority = $spec.PNoInfo
            if ($hasCoverage) {
                $covValue   = [string](Get-FactValue -Field $spec.CoverageField -FactMap $FactMap)
                $existingProtection = $covValue
                $covCategory = Get-CoverageCategory -Text $covValue
                if ($covCategory -eq "none") {
                    $priority = $spec.PZero
                } else {
                    $covAmount = Get-AmountWan -Text $covValue
                    $need      = Get-RaNeedWan -Spec $spec -FactMap $FactMap
                    if ($null -ne $covAmount -and $null -ne $need -and $covAmount -ge $need) {
                        $priority = $spec.PAdequate
                    } else {
                        $priority = $spec.PInadequate
                    }
                }
            }
        }
    }

    $impact = $texts.Impact
    if ($RequirementType -eq "medical") {
        $hasInsStatus = (Has-UsableFact -Field "social_insurance_status" -FactMap $FactMap)
        if (-not $hasInsStatus) { $impact = $texts.ImpactUnknown }
    }

    $softFields = Get-SoftFactFields -Fields $spec.EvidenceRefs -FactMap $FactMap
    Add-SoftFactAssumption -RequirementType $RequirementType -SoftFields $softFields -Assumptions $Assumptions

    Add-RequirementPackage -RequirementType $RequirementType `
        -RiskExposure $texts.Risk `
        -PotentialFinancialImpact $impact `
        -ExistingProtection $existingProtection `
        -CoverageGap $texts.Gap `
        -Priority $priority `
        -Reasoning $texts.Reasoning `
        -FactRefs $spec.EvidenceRefs `
        -FactMap $FactMap `
        -RiskMap $RiskMap `
        -CoverageGaps $CoverageGaps `
        -Requirements $Requirements `
        -Priorities $Priorities `
        -Evidence $Evidence
}

$input = Read-JsonFile -Path $InputJsonPath
$result = Invoke-RaScriptToObject -ScriptPath $QuestioningScript -Arguments @{ InputJsonPath = $InputJsonPath } -ExpectedTopLevelProperty "question_plan"
$factMap = Get-FactMap -Facts $input.client_profile.facts

$riskMap = New-Object System.Collections.ArrayList
$coverageGaps = New-Object System.Collections.ArrayList
$requirements = New-Object System.Collections.ArrayList
$priorities = New-Object System.Collections.ArrayList
$evidence = New-Object System.Collections.ArrayList
$assumptions = New-Object System.Collections.ArrayList

$canAnalyze = @("COMPLETE", "PRELIMINARY") -contains $result.analysis_status
if ($canAnalyze) {
    foreach ($scope in (To-JsonArray -Value $input.analysis_scope)) {
        if ($RaScopeToOverlay.ContainsKey([string]$scope)) {
            Build-DomainAnalysis -RequirementType ([string]$scope) -FactMap $factMap `
                -RiskMap $riskMap -CoverageGaps $coverageGaps -Requirements $requirements `
                -Priorities $priorities -Evidence $evidence -Assumptions $assumptions
        }
    }
}

$result.risk_map = @($riskMap)
$result.coverage_gaps = @($coverageGaps)
$result.requirements = @($requirements)
$result.priorities = @($priorities)
$result.evidence = @($evidence)
$result.assumptions = @($assumptions)
$result.guardrails.product_recommendation_included = $false

$jsonOutput = $result | ConvertTo-Json -Depth 30
if (-not [string]::IsNullOrWhiteSpace($OutputJsonPath)) {
    Set-Content -Path $OutputJsonPath -Value $jsonOutput -Encoding UTF8
}

Write-Output $jsonOutput
