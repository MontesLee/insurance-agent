#requires -Version 5.1
<#
    test-risk-analysis-discovery.ps1
    --------------------------------
    risk-analysis · Discovery 阶段单元测试

    覆盖 9 个 fixture（含 2 个对抗用例）+ 1 个规则外置负向用例 + 1 个与充分性阶段的集成用例。
    结果落盘 tmp/discovery_test_result.json（CI 友好），stdout 同时输出摘要。

    Lawgent 纪律：
      - 只有可机检断言才判 PASS
      - 负向用例必须证明"改规则 → 结论变"，证明规则真的外置而非硬编码
#>
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }

$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$fx     = Join-Path $skillRoot 'evals'
$fx     = Join-Path $fx 'fixtures'
$fx     = Join-Path $fx 'unit'
$fxDisc = Join-Path $fx 'discovery'
$fxSuff = Join-Path $fx 'sufficiency'
$tmp    = Join-Path $skillRoot 'tmp'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Path $tmp | Out-Null }
$engine = Join-Path $skillRoot 'scripts'
$engine = Join-Path $engine 'invoke-risk-analysis-discovery.ps1'
$suffEngine = Join-Path $skillRoot 'scripts'
$suffEngine = Join-Path $suffEngine 'invoke-risk-analysis-sufficiency.ps1'
$rulesPath = Join-Path $skillRoot 'resources'
$rulesPath = Join-Path $rulesPath 'config'
$rulesPath = Join-Path $rulesPath 'risk-discovery.rules.json'

$results = [System.Collections.Generic.List[object]]::new()

# ------------------------------------------------------------------ assert helpers
function Assert-True {
    param([bool]$Cond, [string]$Message)
    if (-not $Cond) { throw $Message }
}
function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ([string]$Actual -ne [string]$Expected) {
        throw "$Message | expected=[$Expected] actual=[$Actual]"
    }
}
function Assert-Contains {
    param($Array, [string]$Item, [string]$Message)
    if (@($Array) -notcontains $Item) {
        throw "$Message | missing=[$Item] actual=[$(@($Array) -join ',')]"
    }
}
function Get-RdCandidate {
    param($Out, [string]$Domain)
    $c = @($Out.risk_candidates | Where-Object { $_.risk_category -eq $Domain })[0]
    if ($null -eq $c) { throw "candidate not found: $Domain" }
    return $c
}
function Invoke-RdDiscovery {
    param([string]$Fixture, [string]$OutName, [string]$Rules = '', [string]$SuffJson = '', [string]$FixtureDir = '')
    if ([string]::IsNullOrWhiteSpace($FixtureDir)) { $FixtureDir = $fxDisc }
    $inPath  = Join-Path $FixtureDir $Fixture
    $outPath = Join-Path $tmp $OutName
    if (Test-Path -LiteralPath $outPath) { [System.IO.File]::Delete($outPath) }
    # 注意：必须用哈希表 splatting。数组 splatting 会按位置绑定，
    # 把 '-InputJsonPath' 当成参数值传给第一个形参（PS 5.1 实测坑）。
    $params = @{ InputJsonPath = $inPath; OutputJsonPath = $outPath }
    if (-not [string]::IsNullOrWhiteSpace($Rules)) { $params.RulesPath = $Rules }
    if (-not [string]::IsNullOrWhiteSpace($SuffJson)) { $params.SufficiencyJsonPath = $SuffJson }
    & $engine @params | Out-Null
    if (-not (Test-Path -LiteralPath $outPath)) { throw "engine produced no output for $Fixture" }
    return (Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Assert-RdStageShape {
    param($Out, [int]$ExpectedCandidates)
    Assert-Equal $Out.stage 'discovery' 'stage 必须是 discovery'
    Assert-Equal $Out.taxonomy_version '1.0' 'taxonomy_version 必须是 1.0'
    Assert-Equal $Out.discovery.method 'risk_dependency_graph_v1' 'method 必须是 risk_dependency_graph_v1'
    Assert-True (@($Out.risk_candidates).Count -eq $ExpectedCandidates) "risk_candidates 数量应为 $ExpectedCandidates"
    Assert-True ($Out.guardrails.product_recommendation_included -eq $false) 'guardrails: 不得含产品推荐'
    Assert-True ($Out.guardrails.sales_language_detected -eq $false) 'guardrails: 不得含销售话术'

    foreach ($c in @($Out.risk_candidates)) {
        Assert-True ($c.risk_id -match '^R[1-9]-001$') "risk_id 必须匹配 ^R\d-001$，实际 $($c.risk_id)"
        Assert-True (@('R1', 'R2', 'R3', 'R4', 'R5') -contains $c.risk_category) 'risk_category 枚举'
        Assert-True (@('IDENTIFIED', 'NOT_IDENTIFIED', 'UNDETERMINED') -contains $c.discovery_status) 'discovery_status 枚举'
        Assert-True (@('KNOWN', 'UNKNOWN', 'ESTIMATED', 'ASSUMED', 'INFERRED') -contains $c.status) 'risk status 枚举'
        Assert-True (-not [string]::IsNullOrWhiteSpace($c.trigger.event)) 'trigger.event 不得为空'
        Assert-True (-not [string]::IsNullOrWhiteSpace($c.exposure.why_exposed)) 'exposure.why_exposed 不得为空'

        # 证据锚点：UNDETERMINED 无可引事实，允许为空（宁可没有，不得伪造）；
        # IDENTIFIED / NOT_IDENTIFIED 必须至少 1 个锚点。
        if ($c.discovery_status -eq 'UNDETERMINED') {
            foreach ($ref in @($c.reasoning_evidence_refs)) {
                Assert-True ($ref -match '^REQ-[0-9]{3}$') "UNDETERMINED 不得引用事实证据，只允许需求层锚点：$ref"
            }
        } else {
            Assert-True (@($c.reasoning_evidence_refs).Count -ge 1) "$($c.risk_id) 必须至少有 1 个证据锚点"
        }

        # Phase 4 不得产出 Phase 5 的字段（占位值一律禁止）
        foreach ($forbidden in @('severity', 'likelihood', 'residual_risk', 'priority', 'impact_estimate', 'coverage_assessment', 'potential_impact')) {
            $p = $c.PSObject.Properties[$forbidden]
            Assert-True ($null -eq $p) "discovery 阶段不得产出 $forbidden（那是 Phase 5 的职责）"
        }

        if ($c.discovery_status -eq 'IDENTIFIED') {
            Assert-True ([string]$c.risk_exists -eq 'True') "$($c.risk_id) IDENTIFIED 时 risk_exists 必须为 true"
            Assert-True (@($c.evidence).Count -ge 1) "$($c.risk_id) IDENTIFIED 必须至少有 1 条证据"
        } elseif ($c.discovery_status -eq 'NOT_IDENTIFIED') {
            Assert-True ([string]$c.risk_exists -eq 'False') "$($c.risk_id) NOT_IDENTIFIED 时 risk_exists 必须为 false"
            Assert-True (@($c.evidence).Count -ge 1) "$($c.risk_id) NOT_IDENTIFIED 必须给出消极证据"
        } else {
            Assert-True ($null -eq $c.risk_exists) "$($c.risk_id) UNDETERMINED 时 risk_exists 必须为 null"
            Assert-Equal $c.status 'UNKNOWN' "$($c.risk_id) UNDETERMINED 时 status 必须为 UNKNOWN"
        }

        foreach ($ref in @($c.reasoning_evidence_refs)) {
            Assert-True ($ref -match '^(E[0-9]{3}|REQ-[0-9]{3})$') "证据锚点格式非法：$ref"
        }
        foreach ($e in @($c.evidence)) {
            Assert-True ($e.evidence_id -match '^E[0-9]{3}$') 'evidence_id 必须匹配 ^E\d{3}$'
            Assert-Equal $e.source.layer 'client_state' 'discovery 阶段的证据必须来自 client_state'
            Assert-True ($e.source.status -ne 'UNVERIFIED') '不得产出不可溯源证据'
            Assert-True (-not [string]::IsNullOrWhiteSpace($e.fact)) 'evidence.fact 不得为空'
        }
    }

    Assert-True (@($Out.next_information_needed).Count -le 3) '每轮追问 ≤ 3'
    $rvs = @($Out.next_information_needed | ForEach-Object { $_.expected_information_value })
    for ($i = 1; $i -lt $rvs.Count; $i++) {
        Assert-True ($rvs[$i] -le $rvs[$i - 1]) 'next_information_needed 必须按 resolution_value 降序'
    }
    foreach ($q in @($Out.next_information_needed)) {
        Assert-True ($q.question_id -match '^Q[0-9]{3}$') 'question_id 必须匹配 ^Q\d{3}$'
        Assert-True (-not [string]::IsNullOrWhiteSpace($q.question)) 'question 不得为空'
        Assert-True (-not [string]::IsNullOrWhiteSpace($q.why_needed)) 'why_needed 不得为空'
        Assert-True (@($q.affects_risks).Count -ge 1) 'affects_risks 不得为空'
        Assert-True (@('HIGH', 'MEDIUM', 'LOW') -contains $q.priority) 'question priority 枚举'
    }
}

# ------------------------------------------------------------------ cases
$cases = [System.Collections.Generic.List[object]]::new()

$cases.Add(@{
    Name = 'dual-income-family: 双职工 + 房贷 + 子女 → 5 域全部 IDENTIFIED'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-dual-income-family.json' -OutName 'disc_dual.json'
        Assert-RdStageShape $o 5
        Assert-Equal (@($o.discovery.identified).Count) 5 '5 个域应全部 IDENTIFIED'
        Assert-Equal (@($o.discovery.undetermined).Count) 0 '不应有 UNDETERMINED'
        $r2 = Get-RdCandidate $o 'R2'
        Assert-Contains $r2.reasoning_evidence_refs 'REQ-002' 'R2 必须引用匹配的需求 REQ-002'
        Assert-True ($r2.reasoning_evidence_refs -notcontains 'REQ-001') 'R2 不得引用 life 域的 REQ-001'
        $r4 = Get-RdCandidate $o 'R4'
        Assert-True (@($r4.evidence | Where-Object { $_.fact -match '已有人身寿险保额' }).Count -eq 1) 'R4 应把"寿险保额 0"作为放大因素证据'
        $asm = @($r4.assumptions)
        Assert-True ($asm.Count -ge 1) 'ESTIMATED 事实必须进入 assumptions'
        Assert-True (-not [string]::IsNullOrWhiteSpace($asm[0].reason)) 'assumption 必须写明依据'
        # 状态取最弱环节：存在 ESTIMATED 证据 → 不得升格为 KNOWN
        Assert-Equal (Get-RdCandidate $o 'R2').status 'ESTIMATED' '存在 ESTIMATED 证据时 risk.status 必须为 ESTIMATED'
    }
})

$cases.Add(@{
    Name = 'single-no-dependents: 单身无责任 → R4 NOT_IDENTIFIED，且给出消极证据'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-single-no-dependents.json' -OutName 'disc_single.json'
        Assert-RdStageShape $o 5
        Assert-Contains $o.discovery.not_identified 'R4' 'R4 应判 NOT_IDENTIFIED'
        Assert-Contains $o.discovery.identified 'R1' 'R1 普适暴露，仍应 IDENTIFIED'
        Assert-Contains $o.discovery.identified 'R2' '有收入 → R2 IDENTIFIED'
        $r4 = Get-RdCandidate $o 'R4'
        Assert-True ($r4.exposure.why_exposed -match '未识别到构成该风险的事实') 'R4 的 exposure 必须说明未识别到暴露事实'
        Assert-True (@($r4.evidence).Count -ge 3) 'R4 的消极证据应覆盖责任组多个字段'
    }
})

$cases.Add(@{
    Name = 'retired-no-income: 无收入且非高风险职业 → R2/R3 NOT_IDENTIFIED'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-retired-no-income.json' -OutName 'disc_retired.json'
        Assert-RdStageShape $o 5
        Assert-Contains $o.discovery.not_identified 'R2' '无收入 → R2 不成立'
        Assert-Contains $o.discovery.not_identified 'R3' '无收入且职业非高风险 → R3 不成立'
        Assert-Contains $o.discovery.not_identified 'R4' '无责任 → R4 不成立'
        Assert-Contains $o.discovery.identified 'R1' 'R1 普适暴露'
        Assert-Contains $o.discovery.identified 'R5' '已知年龄 → R5 成立'
    }
})

$cases.Add(@{
    Name = 'all-unknown: 全字段 UNKNOWN → 5 域全部 UNDETERMINED，零证据零推断'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-all-unknown.json' -OutName 'disc_allunknown.json'
        Assert-RdStageShape $o 5
        Assert-Equal (@($o.discovery.undetermined).Count) 5 '全未知时 5 个域都应 UNDETERMINED'
        Assert-Equal (@($o.discovery.identified).Count) 0 '全未知时不得 IDENTIFIED 任何域'
        foreach ($c in @($o.risk_candidates)) {
            Assert-True (@($c.evidence).Count -eq 0) 'UNDETERMINED 不得伪造证据'
        }
        Assert-Equal $o.analysis_status 'NEED_MORE_INFORMATION' 'analysis_status'
        Assert-True (@($o.next_information_needed).Count -eq 3) '应产出 3 个追问（每轮上限）'
        $first = @($o.next_information_needed)[0]
        Assert-True (@($first.affects_risks).Count -ge 2) 'resolution_value 最高的问题应影响 ≥2 个域'
    }
})

$cases.Add(@{
    Name = 'high-risk-occupation: 收入未知但高风险职业 → R3 IDENTIFIED / R2 UNDETERMINED'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-high-risk-occupation.json' -OutName 'disc_highrisk.json'
        Assert-RdStageShape $o 5
        Assert-Contains $o.discovery.identified 'R3' '高风险职业足以认定 R3 成立'
        Assert-Contains $o.discovery.undetermined 'R2' '收入未知 → R2 不得判定'
        $r3 = Get-RdCandidate $o 'R3'
        Assert-True (@($r3.evidence | Where-Object { $_.fact -match '职业' }).Count -eq 1) 'R3 必须引用职业事实作为证据'
        Assert-Contains $r3.reasoning_evidence_refs 'REQ-003' 'accident 类需求必须锚定到 R3（域映射不得错位）'
        $r2 = Get-RdCandidate $o 'R2'
        Assert-True (@($r2.unknowns | Where-Object { $_.field -eq 'annual_income' }).Count -eq 1) 'annual_income 必须进 R2 的 unknowns'
    }
})

$cases.Add(@{
    Name = 'income-conflict: 收入冲突 → R2/R3 UNDETERMINED + CONFLICTING_INFORMATION，禁止择一'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-income-conflict.json' -OutName 'disc_conflict.json'
        Assert-RdStageShape $o 5
        Assert-Equal $o.analysis_status 'CONFLICTING_INFORMATION' '存在冲突 → CONFLICTING_INFORMATION'
        Assert-Contains $o.discovery.undetermined 'R2' '冲突字段不得用于判定 R2'
        Assert-Contains $o.discovery.undetermined 'R3' '冲突字段不得用于判定 R3'
        $r2 = Get-RdCandidate $o 'R2'
        $u = @($r2.unknowns | Where-Object { $_.field -eq 'household_income' })[0]
        Assert-True ($null -ne $u) '冲突字段必须进 R2 的 unknowns'
        Assert-True ($u.reason -match 'CONFLICT_UNRESOLVED') '冲突字段的 reason 必须标注 CONFLICT_UNRESOLVED'
        $q = @($o.next_information_needed | Where-Object { $_.why_needed -match '冲突待澄清' })[0]
        Assert-True ($null -ne $q) '冲突字段必须进入追问且标注待澄清'
    }
})

$cases.Add(@{
    Name = 'no-requirements: 上游需求缺失 → 无 REQ 锚点，风险发现照常'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-no-requirements.json' -OutName 'disc_noreq.json'
        Assert-RdStageShape $o 5
        foreach ($c in @($o.risk_candidates)) {
            foreach ($ref in @($c.reasoning_evidence_refs)) {
                Assert-True ($ref -notmatch '^REQ-') "无需求层输入时不得出现 REQ 锚点：$ref"
            }
        }
        Assert-Equal (@($o.discovery.identified).Count) 5 '事实层完整 → 5 域照常发现'
    }
})

$cases.Add(@{
    Name = 'adversarial: 有房贷但收入未知 → R2 必须 UNDETERMINED（不得由责任推断收入）'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-responsibility-without-income.json' -OutName 'disc_resp_noincome.json'
        Assert-RdStageShape $o 5
        Assert-Contains $o.discovery.identified 'R4' '有房贷 + 子女 → R4 成立'
        Assert-Contains $o.discovery.undetermined 'R2' '收入未知时不得因房贷推断 R2 成立'
        $r2 = Get-RdCandidate $o 'R2'
        Assert-True ($r2.exposure.why_exposed -match 'REQ-004') '需求层关注必须记录但不得构成 gate 命中'
        Assert-True (@($r2.evidence).Count -eq 0) 'UNDETERMINED 的 R2 不得携带证据'
    }
})

$cases.Add(@{
    Name = 'adversarial: 中文负向 token（无房贷/没有/0）→ R4 NOT_IDENTIFIED'
    Run  = {
        $o = Invoke-RdDiscovery -Fixture 'case-chinese-negative-tokens.json' -OutName 'disc_negtokens.json'
        Assert-RdStageShape $o 5
        Assert-Contains $o.discovery.not_identified 'R4' '中文负向表述必须被识别为"明确无责任"'
        Assert-Contains $o.discovery.identified 'R2' '"约 25 万"必须解析为 250000 且 > 0'
        $r2 = Get-RdCandidate $o 'R2'
        # R2 IDENTIFIED 本身即证明"约 25 万"被解析为 > 0 的数值（解析失败会落 UNDETERMINED）
        Assert-True (@($r2.evidence | Where-Object { $_.fact -match '本人年收入' }).Count -eq 1) 'R2 必须引用本人年收入作为证据'
        Assert-True (@($r2.evidence | Where-Object { $_.fact -eq '本人年收入：约 25 万' }).Count -eq 1) '证据必须保留上游原始表述，不得改写为解析值'
    }
})

$cases.Add(@{
    Name = 'negative: 清空 negative_tokens → 结论必须改变（证明规则真外置）'
    Run  = {
        $r = (Get-Content -LiteralPath $rulesPath -Raw -Encoding UTF8) | ConvertFrom-Json
        $r.negative_tokens = @()
        $r.negative_prefixes = @()
        $corrupt = Join-Path $tmp 'corrupt-rules-no-negative.json'
        ($r | ConvertTo-Json -Depth 32) | Set-Content -LiteralPath $corrupt -Encoding UTF8
        try {
            $o = Invoke-RdDiscovery -Fixture 'case-chinese-negative-tokens.json' -OutName 'disc_corrupt.json' -Rules $corrupt
            $r4 = Get-RdCandidate $o 'R4'
            Assert-True ($r4.discovery_status -ne 'NOT_IDENTIFIED') '规则被清空后 R4 结论必须改变（否则说明规则被硬编码）'
        } finally {
            if (Test-Path -LiteralPath $corrupt) { [System.IO.File]::Delete($corrupt) }
        }
    }
})

$cases.Add(@{
    Name = 'integration: 传入 sufficiency 产物 → 继承 analysis_status 且追问去重'
    Run  = {
        $suffOut = Join-Path $tmp 'disc_integ_suff.json'
        $inPath  = Join-Path $fxDisc 'case-high-risk-occupation.json'
        if (Test-Path -LiteralPath $suffOut) { [System.IO.File]::Delete($suffOut) }
        $suffParams = @{ InputJsonPath = $inPath; OutputJsonPath = $suffOut }
        & $suffEngine @suffParams | Out-Null
        $suff = (Get-Content -LiteralPath $suffOut -Raw -Encoding UTF8 | ConvertFrom-Json)

        $o = Invoke-RdDiscovery -Fixture 'case-high-risk-occupation.json' -OutName 'disc_integ.json' -SuffJson $suffOut
        Assert-RdStageShape $o 5

        # analysis_status 按 precedence 取更严重者
        $prec = @('FAILED', 'NEEDS_REVIEW', 'CONFLICTING_INFORMATION', 'NEED_MORE_INFORMATION', 'PRELIMINARY', 'FORMAL')
        $iSuff = [array]::IndexOf($prec, [string]$suff.analysis_status)
        $iDisc = [array]::IndexOf($prec, 'NEED_MORE_INFORMATION')
        $expected = if ($iSuff -lt $iDisc) { [string]$suff.analysis_status } else { 'NEED_MORE_INFORMATION' }
        Assert-Equal $o.analysis_status $expected 'analysis_status 必须按 precedence 合并'

        # 追问去重：充分性阶段已问过的字段，发现阶段不得重复问
        $shared = (Get-Content -LiteralPath (Join-Path (Join-Path $skillRoot 'resources') (Join-Path 'config' 'risk-sufficiency.rules.json')) -Raw -Encoding UTF8) | ConvertFrom-Json
        $textToField = @{}
        foreach ($p in $shared.question_templates.PSObject.Properties) {
            $textToField[[string]$p.Value.question] = [string]$p.Name
        }
        $asked = [System.Collections.Generic.HashSet[string]]::new()
        foreach ($q in @($suff.next_information_needed)) {
            $f = $textToField[[string]$q.question]
            if (-not [string]::IsNullOrWhiteSpace($f)) { [void]$asked.Add($f) }
        }
        Assert-True ($asked.Count -ge 1) '充分性阶段应至少产出 1 个可映射字段的追问（否则本用例失去意义）'
        foreach ($q in @($o.next_information_needed)) {
            $f = $textToField[[string]$q.question]
            if (-not [string]::IsNullOrWhiteSpace($f)) {
                Assert-True (-not $asked.Contains($f)) "字段 $f 已在充分性阶段问过，发现阶段不得重复问"
            }
        }
    }
})

# ------------------------------------------------------------------ run
foreach ($c in $cases) {
    try {
        & $c.Run
        $results.Add([pscustomobject]@{ case = $c.Name; status = 'PASS'; detail = '' })
        Write-Output ('[PASS] ' + $c.Name)
    } catch {
        $results.Add([pscustomobject]@{ case = $c.Name; status = 'FAIL'; detail = $_.Exception.Message })
        Write-Output ('[FAIL] ' + $c.Name)
        Write-Output ('       ' + $_.Exception.Message)
    }
}

$passed = @($results | Where-Object { $_.status -eq 'PASS' }).Count
$failed = @($results | Where-Object { $_.status -eq 'FAIL' }).Count

$payload = [ordered]@{
    stage  = 'discovery'
    total  = $results.Count
    passed = $passed
    failed = $failed
    cases  = @($results)
}
$json = $payload | ConvertTo-Json -Depth 12
$resPath = Join-Path $tmp 'discovery_test_result.json'
[System.IO.File]::WriteAllText($resPath, $json, [System.Text.UTF8Encoding]::new($true))

Write-Output ''
Write-Output ('TOTAL=' + $results.Count + ' PASSED=' + $passed + ' FAILED=' + $failed)
Write-Output ('RESULT_FILE=' + $resPath)

if ($failed -gt 0) { exit 1 }
exit 0
