#requires -Version 5.1
<#
    check-skill-anatomy.ps1
    ------------------------
    risk-analysis Skill 架构守卫（Lawgent Step 10 / Phase 9）

    纯确定性检查；任一 FAIL → 退出码 1。
    设计为可被负向测试击破：注入污染（删文件 / 加死键 / 去 BOM / 拆结构）后必须出现 FAIL。

    检查组：
      A 骨架      SKILL.md 行数 / frontmatter / references / schemas / scripts / evals / resources
      B 纪律      文档悬空引用 / 规则死键 / override 显式开关 / 遗留污染 / BOM 与可解析 / 不写上游
#>
param(
    [string]$SkillDir = ""
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($SkillDir)) { $SkillDir = Split-Path -Parent $PSScriptRoot }
$ErrorActionPreference = 'Stop'

$pass = 0; $fail = 0
$lines = [System.Collections.Generic.List[string]]::new()

function Check {
    param([string]$Id, [bool]$Ok, [string]$Detail)
    if ($Ok) { $script:pass++; [void]$script:lines.Add("- [PASS] $Id : $Detail") }
    else     { $script:fail++; [void]$script:lines.Add("- [FAIL] $Id : $Detail") }
}

function Get-JsonFile {
    param([string]$Path)
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

# ---------------------------------------------------------------- 路径
$skillMd     = Join-Path $SkillDir 'SKILL.md'
$contractMd  = Join-Path $SkillDir 'CONTRACT.md'
$refsDir     = Join-Path $SkillDir 'references'
$schemasDir  = Join-Path $SkillDir 'schemas'
$scriptsDir  = Join-Path $SkillDir 'scripts'
$evalsDir    = Join-Path $SkillDir 'evals'
$resourcesDir= Join-Path $SkillDir 'resources'
$cfgDir      = Join-Path $resourcesDir 'config'

# ================================================================ A 骨架
Check "A1_skill_md_exists" (Test-Path -LiteralPath $skillMd) "SKILL.md 存在"

if (Test-Path -LiteralPath $skillMd) {
    $lc = (Get-Content -LiteralPath $skillMd -Encoding UTF8).Count
    Check "A2_skill_md_le100" ($lc -le 100) "SKILL.md 行数=$lc（AGENTS.md §7 要求 ≤100）"
    $raw = Get-Content -LiteralPath $skillMd -Raw -Encoding UTF8
    Check "A3_frontmatter" (($raw -match '(?s)^---\s*\r?\n.*?\r?\n---') -and ($raw -match '(?m)^name:\s*\S') -and ($raw -match '(?m)^description:\s*\S')) "frontmatter 含 name + description"
} else {
    Check "A2_skill_md_le100" $false "SKILL.md 缺失"
    Check "A3_frontmatter" $false "SKILL.md 缺失"
}

Check "A4_contract_exists" (Test-Path -LiteralPath $contractMd) "CONTRACT.md 存在（跨 Skill 依赖必备）"

# A5 references 编号连续：01..NN 无缺号
$refFiles = @()
if (Test-Path -LiteralPath $refsDir) { $refFiles = @(Get-ChildItem -LiteralPath $refsDir -Filter '*.md' -File | Select-Object -ExpandProperty Name) }
$refNums = @()
foreach ($n in $refFiles) {
    if ($n -match '^(\d{2})-') { $refNums += [int]$matches[1] }
}
$refNums = @($refNums | Sort-Object)
$expectedNums = @()
if ($refNums.Count -gt 0) { $expectedNums = @(1..$refNums[$refNums.Count - 1]) }
$missingNums = @()
foreach ($e in $expectedNums) { if ($refNums -notcontains $e) { $missingNums += $e } }
Check "A5_references_sequential" (($refNums.Count -gt 0) -and ($missingNums.Count -eq 0)) "references 编号缺号: $($missingNums -join ',')（现有 $($refNums -join ',')）"

# A6 schemas 五件套
$needSchemas = @('client-state.schema.json', 'risk-analysis-input.schema.json', 'risk.schema.json',
                 'risk-analysis-output.schema.json', 'eval-result.schema.json')
$missSch = @()
foreach ($s in $needSchemas) { if (-not (Test-Path -LiteralPath (Join-Path $schemasDir $s))) { $missSch += $s } }
Check "A6_schemas_complete" ($missSch.Count -eq 0) "缺失 schemas: $($missSch -join ', ')"

# A7 关键脚本
$needScripts = @(
    'invoke-risk-analysis-sufficiency.ps1', 'invoke-risk-analysis-discovery.ps1',
    'invoke-risk-analysis-analysis.ps1', 'invoke-risk-analysis-eval.ps1',
    'invoke-risk-analysis-repair.ps1', 'run-risk-analysis-dataset.ps1',
    'test-risk-analysis-sufficiency.ps1', 'test-risk-analysis-discovery.ps1',
    'test-risk-analysis-analysis.ps1', 'test-risk-analysis-eval.ps1',
    'test-risk-analysis-repair.ps1', 'test-risk-analysis-dataset.ps1',
    'test-risk-analysis-anatomy.ps1', 'check-skill-anatomy.ps1',
    'verify-contract.py', 'gen-dataset-cases.py', 'gen-repair-fixtures.py'
)
$missScr = @()
foreach ($s in $needScripts) { if (-not (Test-Path -LiteralPath (Join-Path $scriptsDir $s))) { $missScr += $s } }
Check "A7_scripts_complete" ($missScr.Count -eq 0) "缺失 scripts: $($missScr -join ', ')"

# A8 evals 结构
Check "A8_eval_policy"  (Test-Path -LiteralPath (Join-Path $evalsDir 'eval-policy.md')) "evals/eval-policy.md 存在"
Check "A8b_case_manifest" (Test-Path -LiteralPath (Join-Path $evalsDir 'cases/manifest.json')) "evals/cases/manifest.json 存在（Eval 用例单一真源）"
Check "A8c_dataset_manifest" (Test-Path -LiteralPath (Join-Path $evalsDir 'cases/dataset-manifest.json')) "evals/cases/dataset-manifest.json 存在"

# A9 fixtures 每阶段有夹具
$fixtureRoot = Join-Path $evalsDir 'fixtures/unit'
$needStages = @('sufficiency', 'discovery', 'eval', 'repair')
$missFx = @()
foreach ($st in $needStages) {
    $d = Join-Path $fixtureRoot $st
    $n = 0
    if (Test-Path -LiteralPath $d) { $n = @(Get-ChildItem -LiteralPath $d -Filter '*.json' -File).Count }
    if ($n -eq 0) { $missFx += "$st(0)" }
}
Check "A9_fixtures_per_stage" ($missFx.Count -eq 0) "无夹具的阶段: $($missFx -join ', ')"

# A10 resources
Check "A10_usage_guide" (Test-Path -LiteralPath (Join-Path $resourcesDir 'usage-guide.md')) "resources/usage-guide.md 存在（调用模板）"
$ruleFiles = @('risk-sufficiency.rules.json', 'risk-discovery.rules.json', 'risk-scoring.rules.json',
               'anti-sales.rules.json', 'repair.rules.json')
$missRule = @()
foreach ($r in $ruleFiles) { if (-not (Test-Path -LiteralPath (Join-Path $cfgDir $r))) { $missRule += $r } }
Check "A10b_rules_complete" ($missRule.Count -eq 0) "缺失规则文件: $($missRule -join ', ')"

# ================================================================ B 纪律
# B1 文档悬空引用：md 中的相对路径必须存在；不存在则该行必须标 ⏳
$mdFiles = @()
$mdFiles += @(Get-ChildItem -LiteralPath $SkillDir -Filter '*.md' -File)
if (Test-Path -LiteralPath $refsDir)      { $mdFiles += @(Get-ChildItem -LiteralPath $refsDir -Filter '*.md' -File) }
if (Test-Path -LiteralPath $resourcesDir) { $mdFiles += @(Get-ChildItem -LiteralPath $resourcesDir -Filter '*.md' -File) }
if (Test-Path -LiteralPath $evalsDir)     { $mdFiles += @(Get-ChildItem -LiteralPath $evalsDir -Filter '*.md' -File) }

$dangling = @()
foreach ($f in $mdFiles) {
    $ln = 0
    foreach ($line in (Get-Content -LiteralPath $f.FullName -Encoding UTF8)) {
        $ln++
        foreach ($m in [regex]::Matches($line, '(?<![\w./-])((?:references|schemas|scripts|resources|evals)/[A-Za-z0-9._/-]+\.(?:md|json|ps1|py))')) {
            $rel = $m.Groups[1].Value
            if ($rel -match '\.\.') { continue }
            $target = Join-Path $SkillDir $rel
            if (-not (Test-Path -LiteralPath $target)) {
                $pending = $line -match '⏳'
                if (-not $pending) { $dangling += ("{0}:{1} -> {2}" -f $f.Name, $ln, $rel) }
            }
        }
    }
}
Check "B1_no_dangling_refs" ($dangling.Count -eq 0) "悬空引用（未标 ⏳ 即视为假引用）: $($dangling -join ' | ')"

# B2 规则文件不得有死顶层键
$META_KEYS = @('rules_version', 'taxonomy_version', 'method', 'description', 'note', 'shared_sources',
               'anti_sales_version', 'repair_version', 'repair_method', 'principles', 'version',
               'scoring_version', 'scoring_method', 'documentation')
$scriptText = ''
if (Test-Path -LiteralPath $scriptsDir) {
    foreach ($sf in @(Get-ChildItem -LiteralPath $scriptsDir -Include '*.ps1', '*.py' -File -Recurse)) {
        $scriptText += (Get-Content -LiteralPath $sf.FullName -Raw -Encoding UTF8)
    }
}
$deadKeys = @()
if (Test-Path -LiteralPath $cfgDir) {
    foreach ($cf in @(Get-ChildItem -LiteralPath $cfgDir -Filter '*.rules.json' -File)) {
        $obj = Get-JsonFile -Path $cf.FullName
        foreach ($p in $obj.PSObject.Properties) {
            if ($META_KEYS -contains $p.Name) { continue }
            if (-not ($scriptText -match [regex]::Escape($p.Name))) { $deadKeys += ("{0}#{1}" -f $cf.Name, $p.Name) }
        }
    }
}
Check "B2_no_dead_rule_keys" ($deadKeys.Count -eq 0) "未被任何脚本消费的规则顶层键（假外置）: $($deadKeys -join ', ')"

# B3 priority_overrides 必须显式 enabled（禁止静默 no-op）
$ovIssues = @()
$scorPath = Join-Path $cfgDir 'risk-scoring.rules.json'
if (Test-Path -LiteralPath $scorPath) {
    $sc = Get-JsonFile -Path $scorPath
    foreach ($ov in @($sc.priority_overrides)) {
        $hasEnabled = @($ov.PSObject.Properties.Name) -contains 'enabled'
        if (-not $hasEnabled) { $ovIssues += ("{0}(缺 enabled)" -f $ov.id) }
    }
}
Check "B3_overrides_explicit_enabled" ($ovIssues.Count -eq 0) "priority_overrides 缺显式 enabled: $($ovIssues -join ', ')"

# B4 无遗留污染（.bak / ~ / nul / _ 前缀临时脚本）
$legacy = @()
foreach ($f in @(Get-ChildItem -LiteralPath $SkillDir -Recurse -Force -File)) {
    $rel = $f.FullName.Replace($SkillDir, '')
    if ($rel -match '^[\\/]tmp[\\/]') { continue }     # tmp/ 是运行产物，不计基线
    if ($f.Name -match '\.bak$' -or $f.Name -match '~$' -or $f.Name -eq 'nul' -or $f.Name -like '_*') { $legacy += $rel }
}
Check "B4_no_legacy_files" ($legacy.Count -eq 0) "遗留/临时文件: $($legacy -join '; ')"

# B5 每个 .ps1：UTF-8 BOM + 可解析
$bomIssues = @(); $parseIssues = @()
if (Test-Path -LiteralPath $scriptsDir) {
    foreach ($sf in @(Get-ChildItem -LiteralPath $scriptsDir -Filter '*.ps1' -File)) {
        $bytes = [System.IO.File]::ReadAllBytes($sf.FullName)
        if ($bytes.Length -lt 3 -or $bytes[0] -ne 0xEF -or $bytes[1] -ne 0xBB -or $bytes[2] -ne 0xBF) { $bomIssues += $sf.Name }
        $errs = $null; $toks = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($sf.FullName, [ref]$toks, [ref]$errs)
        if (($errs | Measure-Object).Count -gt 0) { $parseIssues += ("{0}:{1}" -f $sf.Name, ($errs | Select-Object -First 1).Message) }
    }
}
Check "B5_ps1_bom" ($bomIssues.Count -eq 0) "缺 UTF-8 BOM 的脚本: $($bomIssues -join ', ')"
Check "B5b_ps1_parses" ($parseIssues.Count -eq 0) "解析失败的脚本: $($parseIssues -join ' | ')"

# B6 上游不可变：脚本不得写上游 Skill 目录
$upstreamWrites = @()
if (Test-Path -LiteralPath $scriptsDir) {
    foreach ($sf in @(Get-ChildItem -LiteralPath $scriptsDir -Filter '*.ps1' -File)) {
        $ln = 0
        foreach ($line in (Get-Content -LiteralPath $sf.FullName -Encoding UTF8)) {
            $ln++
            if ($line -match 'Set-Content|Out-File|Add-Content|WriteAllText|Remove-Item' -and
                $line -match 'client-intake|requirement_analysis') {
                $upstreamWrites += ("{0}:{1}" -f $sf.Name, $ln)
            }
        }
    }
}
Check "B6_no_upstream_write" ($upstreamWrites.Count -eq 0) "疑似写上游的语句: $($upstreamWrites -join ', ')"

# ---------------------------------------------------------------- 输出
Write-Output "=== risk-analysis Skill Anatomy ==="
$lines | ForEach-Object { Write-Output $_ }
Write-Output ""
Write-Output "PASS=$pass FAIL=$fail"

$outObj = [ordered]@{ skill = 'risk-analysis'; pass = $pass; fail = $fail; checks = @($lines) }
$outDir = Join-Path $SkillDir 'tmp'
if (-not (Test-Path -LiteralPath $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
($outObj | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath (Join-Path $outDir 'anatomy_result.json') -Encoding UTF8

if ($fail -gt 0) { exit 1 }
exit 0
