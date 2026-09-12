<#
.SYNOPSIS
  Skill Anatomy 守卫 —— 验证 requirement_analysis skill 结构合规（Lawgent Step 10）。
.DESCRIPTION
  纯确定性检查，输出 PASS/FAIL 计数；任一 FAIL 退出码 1。
  设计为可被负向测试击破：注入污染后必须出现 FAIL。
#>
[CmdletBinding()]
param(
    [string]$SkillDir = ""
)

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($SkillDir)) { $SkillDir = Split-Path -Parent $PSScriptRoot }
$ErrorActionPreference = "Stop"
$pass = 0; $fail = 0
$lines = @()

function Check {
    param([string]$Id, [bool]$Ok, [string]$Detail)
    if ($Ok) { $script:pass++; $script:lines += "- [PASS] $Id : $Detail" }
    else { $script:fail++; $script:lines += "- [FAIL] $Id : $Detail" }
}

$skillMd = Join-Path $SkillDir "SKILL.md"
$refsDir = Join-Path $SkillDir "references"
$schemasDir = Join-Path $SkillDir "schemas"
$scriptsDir = Join-Path $SkillDir "scripts"
$evalsDir = Join-Path $SkillDir "evals"

# A1 SKILL.md 存在
Check "A1_skill_md_exists" (Test-Path $skillMd) "SKILL.md 存在"

# A2 SKILL.md <= 100 行
if (Test-Path $skillMd) {
    $lc = (Get-Content $skillMd -Encoding UTF8).Count
    Check "A2_skill_md_le100" ($lc -le 100) "SKILL.md 行数=$lc (阈值 100)"
} else { Check "A2_skill_md_le100" $false "SKILL.md 缺失无法计数" }

# A3 frontmatter 含 name + description
if (Test-Path $skillMd) {
    $txt = Get-Content $skillMd -Raw -Encoding UTF8
    $hasFm = $txt -match '(?s)^---\s*\n.*?---'
    $hasName = $txt -match 'name:\s*".*?"'
    $hasDesc = $txt -match 'description:\s*".*?"'
    Check "A3_frontmatter" ($hasFm -and $hasName -and $hasDesc) "frontmatter name=$hasName description=$hasDesc"
} else { Check "A3_frontmatter" $false "SKILL.md 缺失" }

# A4 Knowledge Routing 表存在
if (Test-Path $skillMd) {
    $txt = Get-Content $skillMd -Raw -Encoding UTF8
    Check "A4_routing_table" ($txt -match 'Knowledge Routing') "SKILL.md 含 Knowledge Routing 表"
} else { Check "A4_routing_table" $false "SKILL.md 缺失" }

# A5 references 7 份齐全
$expectedRefs = @(
    '01-boundary.md','02-information-model.md','03-status-enums.md',
    '04-information-sufficiency.md','05-questioning.md','06-analysis.md','07-repair-loop.md'
)
$missingRefs = @()
foreach ($r in $expectedRefs) {
    if (-not (Test-Path (Join-Path $refsDir $r))) { $missingRefs += $r }
}
Check "A5_references_complete" ($missingRefs.Count -eq 0) "缺失 references: $($missingRefs -join ', ')"

# A6 schemas 三件套
$expectedSchemas = @('input.schema.json','output.schema.json','eval-output.schema.json')
$missingSch = @()
foreach ($s in $expectedSchemas) {
    if (-not (Test-Path (Join-Path $schemasDir $s))) { $missingSch += $s }
}
Check "A6_schemas_complete" ($missingSch.Count -eq 0) "缺失 schemas: $($missingSch -join ', ')"

# A7 关键脚本齐全
$expectedScripts = @(
    'invoke-requirement-analysis-analysis.ps1',
    'invoke-requirement-analysis-sufficiency.ps1',
    'invoke-requirement-analysis-questioning.ps1',
    'invoke-requirement-analysis-repair-loop.ps1',
    'invoke-requirement-analysis-eval.ps1',
    'run-requirement-analysis-dataset.ps1',
    'adapter-from-client-profile.ps1',
    'test-requirement-analysis-adapter.ps1',
    'check-skill-anatomy.ps1'
)
$missingScripts = @()
foreach ($s in $expectedScripts) {
    if (-not (Test-Path (Join-Path $scriptsDir $s))) { $missingScripts += $s }
}
Check "A7_scripts_present" ($missingScripts.Count -eq 0) "缺失 scripts: $($missingScripts -join ', ')"

# A8 eval-policy 存在
Check "A8_eval_policy" (Test-Path (Join-Path $evalsDir "eval-policy.md")) "evals/eval-policy.md 存在"

# A9 无遗留 .bak / legacy 污染
$legacy = @()
Get-ChildItem $SkillDir -Recurse -Force -File | Where-Object {
    $_.Name -match '\.bak$|\.bak-|\.legacy|~$' -or $_.Name -like 'CONTRACT.md' -or $_.Name -like 'USAGE_GUIDE.md'
} | ForEach-Object { $legacy += $_.FullName.Replace($SkillDir,'') }
Check "A9_no_legacy" ($legacy.Count -eq 0) "遗留文件: $($legacy -join '; ')"

# B1 边界硬编码守卫：references 不得出现产品推荐越界表述（仅作为结构提示，不机检内容正确性）
# B1 检查旧路径 02-requirement-analysis / 01-client-intake 是否已清除（防回退）
$stale = @()
    $selfPath = $MyInvocation.MyCommand.Path
    Get-ChildItem $SkillDir -Recurse -Force -File -Include '*.md','*.ps1','*.json' | Where-Object { $_.FullName -ne $selfPath -and $_.Name -ne 'REFACTOR_REPORT.md' } | ForEach-Object {
    $c = Get-Content $_.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($c -match '02-requirement-analysis/|01-client-intake/') { $stale += $_.FullName.Replace($SkillDir,'') }
}
Check "B1_no_stale_paths" ($stale.Count -eq 0) "仍含旧路径的文件: $($stale -join '; ')"


# ---------- Domain Overlay 架构守卫（Lawgent overlay 模式）----------
$ovRoot = Join-Path $SkillDir "overlays"
Check "A10_overlay_root" (Test-Path $ovRoot) "overlays 目录存在"
Check "A10b_overlay_readme" (Test-Path (Join-Path $ovRoot "README.md")) "overlays/README.md（协议）存在"
Check "A10c_overlay_template" (Test-Path (Join-Path $ovRoot "_template")) "overlays/_template（新险种模板）存在"

$skRaw2 = if (Test-Path $skillMd) { (Get-Content $skillMd -Raw -Encoding UTF8) } else { "" }
Check "A10d_skill_overlay_section" ($skRaw2 -match 'Domain Overlays') "SKILL.md 缺 'Domain Overlays' 节（扩展层未接入 manifest）"

function Parse-OvYamlGuard {
    param([string]$Path)
    $yaml = [ordered]@{}
    $cur  = $null
    foreach ($raw in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $line = $raw -replace '#.*$', ''
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        # 与引擎 Parse-RaOverlayYaml 同构：优先匹配带双引号的值，使文本可含冒号
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

$ovDirs = @()
if (Test-Path $ovRoot) { $ovDirs = @(Get-ChildItem -LiteralPath $ovRoot -Directory | Where-Object { $_.Name -ne '_template' }) }
Check "A11_overlay_count" ($ovDirs.Count -gt 0) "overlay 数量 = $($ovDirs.Count)（0 说明扩展层未落地）"

$allTerms  = @{}
$parsedOv  = @()

foreach ($d in $ovDirs) {
    $id = $d.Name
    $yp = Join-Path $d.FullName "overlay.yaml"
    $hasY = Test-Path -LiteralPath $yp
    Check "A12_$id`_yaml" $hasY "$id/overlay.yaml 存在"
    if (-not $hasY) { continue }

    $y = Parse-OvYamlGuard -Path $yp

    $missing = @()
    foreach ($k in @('id','name','status','priority','dimensions')) {
        if (-not $y.Contains($k) -or [string]::IsNullOrWhiteSpace([string]$y[$k])) { $missing += $k }
    }
    Check "A13_$id`_fields" ($missing.Count -eq 0) "$id 必需字段缺失: $($missing -join ', ')"

    $yid = [string]$y['id']
    Check "A14_$id`_id_match" ($yid -eq $id) "$id 的 id='$yid' 与目录名不一致"

    $st = [string]$y['status']
    Check "A15_$id`_status" (($st -eq 'active') -or ($st -eq 'draft')) "$id status='$st' 非法（应为 active|draft）"

    $pr = 0
    $okPr = [int]::TryParse([string]($y['priority'] | Select-Object -First 1), [ref]$pr)
    Check "A16_$id`_priority" $okPr "$id priority 不是整数"

    $terms = @($y['contamination_terms'] | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    Check "A17_$id`_terms" ($terms.Count -gt 0) "$id contamination_terms 为空（该险种守不住架构边界）"

    foreach ($t in $terms) {
        if ($allTerms.ContainsKey($t)) {
            Check "A18_$id`_dup" $false "术语 '$t' 与 overlay '$($allTerms[$t])' 重复声明"
        } else { $allTerms[$t] = $id }
    }

    # 占位符未替换（防止复制模板后忘记填写就宣称"新增了险种"）
    $placeholders = @()
    foreach ($k in @('id','name','version','status','priority','dimensions')) {
        $v = [string]$y[$k]
        if ($v -match '<' -or $v -match '待填' -or $v -match 'TODO' -or $v -match 'XXX') { $placeholders += "$k=$v" }
    }
    foreach ($t in (@($y['keywords']) + @($y['goal_types']) + @($y['contamination_terms']) + @($y['must_not']) + @($y['required_fields']))) {
        $ts = [string]$t
        if ($ts -match '<' -or $ts -match '待填' -or $ts -match 'TODO' -or $ts -match 'XXX') { $placeholders += "list:$ts" }
    }
    Check "A19_$id`_placeholders" ($placeholders.Count -eq 0) "$id 存在未替换占位符: $($placeholders -join ', ')"

    $dimName = [string]$y['dimensions']
    if ([string]::IsNullOrWhiteSpace($dimName)) { $dimName = 'requirement-dimensions.md' }
    $dimPath = Join-Path $d.FullName $dimName
    Check "A20_$id`_dims" (Test-Path -LiteralPath $dimPath) "$id 维度文件缺失: $dimName"

    # A21 措辞契约：active 险种必须自带结论措辞，禁止把措辞硬编码回通用脚本
    if ($st -eq 'active') {
        $missTexts = @()
        foreach ($tk in @('risk','impact','gap','reasoning')) {
            $tv = [string]$y[$tk]
            if ([string]::IsNullOrWhiteSpace($tv)) { $missTexts += $tk }
            elseif ($tv -match '<' -or $tv -match '待填' -or $tv -match 'TODO' -or $tv -match 'XXX') { $missTexts += "$tk(占位未替换)" }
        }
        Check "A21_$id`_texts" ($missTexts.Count -eq 0) "$id texts 缺失或占位: $($missTexts -join ', ')"
    }

    $parsedOv += [pscustomobject]@{ Id = $id; Terms = $terms; DimPath = $dimPath }
}

# 维度文档必备小节
foreach ($o in $parsedOv) {
    if (-not (Test-Path -LiteralPath $o.DimPath)) { continue }
    $txt = Get-Content -LiteralPath $o.DimPath -Raw -Encoding UTF8
    foreach ($sec in @('## A. 必填事实维度', '## B. 需求口径与缺口计算', '## D. 本险种特有的边界红线')) {
        Check "C1_$($o.Id)`_sections" ($txt -match [regex]::Escape($sec)) "$($o.Id) 维度文档缺少小节: $sec"
    }
}

# ---------- Adapter 守卫（跨 Skill 手递手入口必须存在且可执行）----------
$adapterScript = Join-Path $scriptsDir "adapter-from-client-profile.ps1"
$adapterTest   = Join-Path $scriptsDir "test-requirement-analysis-adapter.ps1"
Check "A22_adapter_script" (Test-Path -LiteralPath $adapterScript) "scripts/adapter-from-client-profile.ps1 缺失（client-intake → RA 唯一官方入口）"
Check "A22b_adapter_test"  (Test-Path -LiteralPath $adapterTest)   "scripts/test-requirement-analysis-adapter.ps1 缺失（Adapter 回归）"

if (Test-Path -LiteralPath $adapterScript) {
    $adpRaw = Get-Content -LiteralPath $adapterScript -Raw -Encoding UTF8
    Check "A22c_adapter_discipline" ($adpRaw -match "value_status -ne 'UNKNOWN'") "Adapter 缺少 UNKNOWN 不入 answered_fields 的纪律实现（会导致关键项漏问）"
    # 静态解析：源文件必须是可解析的 PowerShell（BOM/编码问题会在此暴露）
    $adpErr = $null; $adpTok = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($adapterScript, [ref]$adpTok, [ref]$adpErr)
    Check "A22d_adapter_parses" (($adpErr | Measure-Object).Count -eq 0) "Adapter 脚本解析失败（多半是编码/BOM 问题）: $(($adpErr | Select-Object -First 1).Message)"
}

# B2 领域污染：通用层（SKILL.md / references / schemas）不得出现险种专有术语
$genericPaths = @()
if (Test-Path $skillMd) { $genericPaths += $skillMd }
Get-ChildItem -Path (Join-Path $SkillDir "references") -Filter '*.md' -File -ErrorAction SilentlyContinue | ForEach-Object { $genericPaths += $_.FullName }
Get-ChildItem -Path (Join-Path $SkillDir "schemas") -Filter '*.json' -File -ErrorAction SilentlyContinue | ForEach-Object { $genericPaths += $_.FullName }

$pollution = @()
foreach ($o in $parsedOv) {
    foreach ($t in $o.Terms) {
        foreach ($p in $genericPaths) {
            $c = Get-Content -LiteralPath $p -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if ($c -match [regex]::Escape($t)) {
                $pollution += ("{0}@{1}" -f $t, ($p.Replace($SkillDir, '.')))
            }
        }
    }
}
Check "B2_no_domain_contamination" ($pollution.Count -eq 0) "通用层被领域术语污染: $($pollution -join '; ')"

Write-Output "=== requirement_analysis Skill Anatomy ==="
$lines | ForEach-Object { Write-Output $_ }
Write-Output ""
Write-Output "PASS=$pass FAIL=$fail"
if ($fail -gt 0) { exit 1 } else { exit 0 }
