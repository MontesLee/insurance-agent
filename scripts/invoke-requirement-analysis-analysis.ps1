[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputJsonPath,
    [string]$OutputJsonPath = ""
)

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

function Build-MedicalAnalysis {
    param(
        $FactMap,
        $AnalysisStatus,
        [System.Collections.ArrayList]$RiskMap,
        [System.Collections.ArrayList]$CoverageGaps,
        [System.Collections.ArrayList]$Requirements,
        [System.Collections.ArrayList]$Priorities,
        [System.Collections.ArrayList]$Evidence,
        [System.Collections.ArrayList]$Assumptions
    )

    $hasHealth = Has-UsableFact -Field "customer_health" -FactMap $FactMap
    $hasInsuranceStatus = Has-UsableFact -Field "social_insurance_status" -FactMap $FactMap
    $hasExistingCoverage = Has-UsableFact -Field "existing_medical_coverage" -FactMap $FactMap

    if (-not $hasHealth) {
        return
    }

    $existingProtection = "UNKNOWN"
    if ($hasExistingCoverage) {
        $existingProtection = [string](Get-FactValue -Field "existing_medical_coverage" -FactMap $FactMap)
    }

    $impact = "Medical costs and out-of-pocket treatment burden may pressure household cash flow."
    if (-not $hasInsuranceStatus) {
        $impact = "UNKNOWN: social insurance status is not clear, so self-pay exposure cannot be judged precisely."
    }

    $priority = "P2_MEDIUM"
    if (-not $hasInsuranceStatus -or -not $hasExistingCoverage) {
        $priority = "P1_HIGH"
    }

    $reasoning = "Known health information suggests medical protection should be reviewed. Existing protection and social insurance status directly affect the likely reimbursement gap."
    $softFields = Get-SoftFactFields -Fields @("customer_health", "social_insurance_status", "existing_medical_coverage") -FactMap $FactMap
    Add-SoftFactAssumption -RequirementType "medical" -SoftFields $softFields -Assumptions $Assumptions
    Add-RequirementPackage -RequirementType "medical" `
        -RiskExposure "Household may face medical reimbursement and treatment cost exposure." `
        -PotentialFinancialImpact $impact `
        -ExistingProtection $existingProtection `
        -CoverageGap "Need to clarify and evaluate medical protection adequacy before formal product-level discussion." `
        -Priority $priority `
        -Reasoning $reasoning `
        -FactRefs @("customer_health", "social_insurance_status", "existing_medical_coverage") `
        -FactMap $FactMap `
        -RiskMap $RiskMap `
        -CoverageGaps $CoverageGaps `
        -Requirements $Requirements `
        -Priorities $Priorities `
        -Evidence $Evidence
}

function Build-CriticalIllnessAnalysis {
    param(
        $FactMap,
        [System.Collections.ArrayList]$RiskMap,
        [System.Collections.ArrayList]$CoverageGaps,
        [System.Collections.ArrayList]$Requirements,
        [System.Collections.ArrayList]$Priorities,
        [System.Collections.ArrayList]$Evidence,
        [System.Collections.ArrayList]$Assumptions
    )

    $hasIncome = Has-UsableFact -Field "annual_income" -FactMap $FactMap
    $hasResponsibility = Has-UsableFact -Field "family_responsibility" -FactMap $FactMap
    $hasExistingCi = Has-UsableFact -Field "existing_critical_illness_coverage" -FactMap $FactMap

    if (-not $hasIncome -or -not $hasResponsibility) {
        return
    }

    $existingProtection = "UNKNOWN"
    $priority = "P1_HIGH"   # default: coverage presence unknown -> confirm before judging gap

    if ($hasExistingCi) {
        $covValue = [string](Get-FactValue -Field "existing_critical_illness_coverage" -FactMap $FactMap)
        $existingProtection = $covValue
        $covCategory = Get-CoverageCategory -Text $covValue
        if ($covCategory -eq "none") {
            $priority = "P0_CRITICAL"
        } else {
            $covAmount = Get-AmountWan -Text $covValue
            $ciNeed = Get-CiNeedWan -FactMap $FactMap
            if ($null -ne $covAmount -and $null -ne $ciNeed -and $covAmount -ge $ciNeed) {
                $priority = "P2_MEDIUM"
            } else {
                $priority = "P1_HIGH"
            }
        }
    }

    $reasoning = "Income and family responsibility imply a major illness could create treatment costs plus income interruption. CI priority stays high when existing coverage is inadequate against the need estimate (50万 base + income*3), rather than dropping solely because some coverage exists."
    $softFields = Get-SoftFactFields -Fields @("age", "customer_health", "annual_income", "family_responsibility", "existing_critical_illness_coverage") -FactMap $FactMap
    Add-SoftFactAssumption -RequirementType "critical_illness" -SoftFields $softFields -Assumptions $Assumptions
    Add-RequirementPackage -RequirementType "critical_illness" `
        -RiskExposure "Major illness may create both treatment expenses and income interruption risk." `
        -PotentialFinancialImpact "Household cash flow and recovery-stage financial pressure may rise materially." `
        -ExistingProtection $existingProtection `
        -CoverageGap "Need to evaluate whether current critical illness protection is sufficient for recovery-stage income interruption and family responsibility." `
        -Priority $priority `
        -Reasoning $reasoning `
        -FactRefs @("annual_income", "family_responsibility", "existing_critical_illness_coverage") `
        -FactMap $FactMap `
        -RiskMap $RiskMap `
        -CoverageGaps $CoverageGaps `
        -Requirements $Requirements `
        -Priorities $Priorities `
        -Evidence $Evidence
}

function Build-AccidentAnalysis {
    param(
        $FactMap,
        [System.Collections.ArrayList]$RiskMap,
        [System.Collections.ArrayList]$CoverageGaps,
        [System.Collections.ArrayList]$Requirements,
        [System.Collections.ArrayList]$Priorities,
        [System.Collections.ArrayList]$Evidence,
        [System.Collections.ArrayList]$Assumptions
    )

    $hasOccupation = Has-UsableFact -Field "occupation" -FactMap $FactMap
    $hasExistingAcc = Has-UsableFact -Field "existing_accident_coverage" -FactMap $FactMap
    $hasResponsibility = Has-UsableFact -Field "family_responsibility" -FactMap $FactMap

    if (-not $hasOccupation) {
        return
    }

    $existingProtection = "UNKNOWN"
    if ($hasExistingAcc) {
        $existingProtection = [string](Get-FactValue -Field "existing_accident_coverage" -FactMap $FactMap)
    }

    $priority = "P2_MEDIUM"
    if ($hasResponsibility -and -not $hasExistingAcc) {
        $priority = "P1_HIGH"
    }

    $reasoning = "Occupation and family responsibility together determine whether an accident would create meaningful income disruption or liability pressure."
    $softFields = Get-SoftFactFields -Fields @("age", "occupation", "existing_accident_coverage", "family_responsibility") -FactMap $FactMap
    Add-SoftFactAssumption -RequirementType "accident" -SoftFields $softFields -Assumptions $Assumptions
    Add-RequirementPackage -RequirementType "accident" `
        -RiskExposure "Occupation-related accident exposure may affect earnings continuity and household stability." `
        -PotentialFinancialImpact "Accident events may cause short-term treatment cost and temporary income disruption." `
        -ExistingProtection $existingProtection `
        -CoverageGap "Need to confirm whether current accident protection matches occupation exposure and family responsibility." `
        -Priority $priority `
        -Reasoning $reasoning `
        -FactRefs @("occupation", "family_responsibility", "existing_accident_coverage") `
        -FactMap $FactMap `
        -RiskMap $RiskMap `
        -CoverageGaps $CoverageGaps `
        -Requirements $Requirements `
        -Priorities $Priorities `
        -Evidence $Evidence
}

function Build-LifeAnalysis {
    param(
        $FactMap,
        [System.Collections.ArrayList]$RiskMap,
        [System.Collections.ArrayList]$CoverageGaps,
        [System.Collections.ArrayList]$Requirements,
        [System.Collections.ArrayList]$Priorities,
        [System.Collections.ArrayList]$Evidence,
        [System.Collections.ArrayList]$Assumptions
    )

    $requiredFields = @("annual_income", "family_responsibility", "mortgage_balance", "children_info", "spouse_income")
    foreach ($field in $requiredFields) {
        if (-not (Has-UsableFact -Field $field -FactMap $FactMap)) {
            return
        }
    }

    $hasExistingLife = Has-UsableFact -Field "existing_life_coverage" -FactMap $FactMap
    $existingProtection = "UNKNOWN"
    $priority = "P1_HIGH"   # default: coverage presence unknown -> confirm before judging gap

    if ($hasExistingLife) {
        $covValue = [string](Get-FactValue -Field "existing_life_coverage" -FactMap $FactMap)
        $existingProtection = $covValue
        $covCategory = Get-CoverageCategory -Text $covValue
        if ($covCategory -eq "none") {
            # Client explicitly confirmed ZERO life coverage -> confirmed, fully
            # unmet, actionable gap. This is the most urgent tier.
            $priority = "P0_CRITICAL"
        } else {
            $covAmount = Get-AmountWan -Text $covValue
            $lifeNeed = Get-LifeNeedWan -FactMap $FactMap
            if ($null -ne $covAmount -and $null -ne $lifeNeed -and $covAmount -ge $lifeNeed) {
                $priority = "P2_MEDIUM"
            } else {
                $priority = "P1_HIGH"
            }
        }
    }

    $reasoning = "Known income, mortgage and child responsibility indicate a clear dependency on the primary earner. Life priority reflects coverage presence and adequacy: a confirmed zero-coverage client is the most urgent actionable gap, while unknown coverage is a confirmation task rather than a higher tier than a confirmed gap."
    $softFields = Get-SoftFactFields -Fields (@($requiredFields) + @("existing_life_coverage")) -FactMap $FactMap
    Add-SoftFactAssumption -RequirementType "life" -SoftFields $softFields -Assumptions $Assumptions
    Add-RequirementPackage -RequirementType "life" `
        -RiskExposure "Primary earner dependency plus debt and child responsibility create meaningful life-risk exposure." `
        -PotentialFinancialImpact "Income interruption or death would likely affect mortgage servicing and child-related household obligations." `
        -ExistingProtection $existingProtection `
        -CoverageGap "Need to evaluate whether family responsibility, mortgage burden and current life protection are aligned." `
        -Priority $priority `
        -Reasoning $reasoning `
        -FactRefs @("annual_income", "family_responsibility", "mortgage_balance", "children_info", "spouse_income", "existing_life_coverage") `
        -FactMap $FactMap `
        -RiskMap $RiskMap `
        -CoverageGaps $CoverageGaps `
        -Requirements $Requirements `
        -Priorities $Priorities `
        -Evidence $Evidence
}

function Build-SavingsAnalysis {
    param(
        $FactMap,
        [System.Collections.ArrayList]$RiskMap,
        [System.Collections.ArrayList]$CoverageGaps,
        [System.Collections.ArrayList]$Requirements,
        [System.Collections.ArrayList]$Priorities,
        [System.Collections.ArrayList]$Evidence,
        [System.Collections.ArrayList]$Assumptions
    )

    $requiredFields = @("annual_income", "annual_expense", "liabilities", "cash_flow", "financial_goals")
    foreach ($field in $requiredFields) {
        if (-not (Has-UsableFact -Field $field -FactMap $FactMap)) {
            return
        }
    }

    $assetsKnown = Has-UsableFact -Field "assets" -FactMap $FactMap
    $existingProtection = "Current asset base is UNKNOWN"
    if ($assetsKnown) {
        $existingProtection = ("Known liquid or accumulated assets: {0}" -f (Get-FactValue -Field "assets" -FactMap $FactMap))
    }

    $priority = "P2_MEDIUM"
    if (-not $assetsKnown) {
        $priority = "P1_HIGH"
    }

    $reasoning = "Savings analysis depends on income, expense, liabilities, cash flow and goals. If asset base is unclear, the direction can still be identified but the adequacy judgment remains incomplete."
    $softFields = Get-SoftFactFields -Fields (@($requiredFields) + @("assets")) -FactMap $FactMap
    Add-SoftFactAssumption -RequirementType "savings" -SoftFields $softFields -Assumptions $Assumptions
    Add-RequirementPackage -RequirementType "savings" `
        -RiskExposure "Long-term savings goals may be under-supported if current cash flow and liabilities leave limited room for accumulation." `
        -PotentialFinancialImpact "Delayed goal achievement may affect education, retirement or other long-horizon plans." `
        -ExistingProtection $existingProtection `
        -CoverageGap "Need to evaluate whether current cash flow and asset base can support stated long-term savings goals." `
        -Priority $priority `
        -Reasoning $reasoning `
        -FactRefs @("annual_income", "annual_expense", "liabilities", "cash_flow", "financial_goals", "assets") `
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
        switch ($scope) {
            "medical" {
                Build-MedicalAnalysis -FactMap $factMap -AnalysisStatus $result.analysis_status -RiskMap $riskMap -CoverageGaps $coverageGaps -Requirements $requirements -Priorities $priorities -Evidence $evidence -Assumptions $assumptions
            }
            "critical_illness" {
                Build-CriticalIllnessAnalysis -FactMap $factMap -RiskMap $riskMap -CoverageGaps $coverageGaps -Requirements $requirements -Priorities $priorities -Evidence $evidence -Assumptions $assumptions
            }
            "accident" {
                Build-AccidentAnalysis -FactMap $factMap -RiskMap $riskMap -CoverageGaps $coverageGaps -Requirements $requirements -Priorities $priorities -Evidence $evidence -Assumptions $assumptions
            }
            "life" {
                Build-LifeAnalysis -FactMap $factMap -RiskMap $riskMap -CoverageGaps $coverageGaps -Requirements $requirements -Priorities $priorities -Evidence $evidence -Assumptions $assumptions
            }
            "savings" {
                Build-SavingsAnalysis -FactMap $factMap -RiskMap $riskMap -CoverageGaps $coverageGaps -Requirements $requirements -Priorities $priorities -Evidence $evidence -Assumptions $assumptions
            }
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
