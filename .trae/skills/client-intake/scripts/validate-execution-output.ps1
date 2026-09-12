# client-intake — 本轮执行输出 JSON 契约校验（binding）
# 用途：把 schemas/execution-output.schema.json 的 binding 约束变成可判定检查。
# 用法：& .\validate-execution-output.ps1 -JsonPath <execution-output.json> [-ReportPath <out.md>]
# 退出码：0 = 全部通过；1 = 存在 FAIL

param(
    [Parameter(Mandatory = $true)][string]$JsonPath,
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $JsonPath)) {
    Write-Output "[FAIL] C0 文件不存在: $JsonPath"
    exit 1
}

$raw = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8
try {
    $j = $raw | ConvertFrom-Json
} catch {
    Write-Output "[FAIL] C0 JSON 无法解析 -> HF06 Output Contract Broken"
    exit 1
}

$results = New-Object System.Collections.ArrayList
function Add-R { param([bool]$Ok, [string]$Code, [string]$Msg)
    if ($Ok) { [void]$results.Add("[PASS] $Code $Msg") }
    else { [void]$results.Add("[FAIL] $Code $Msg") }
}
function Has-Prop { param($Obj, [string]$Name)
    if ($null -eq $Obj) { return $false }
    return ($Obj.PSObject.Properties.Name -contains $Name)
}

# C1 顶层必填
$topRequired = @('round', 'source_of_truth', 'this_round_updates', 'completion_check', 'next_questions', 'state_write_result')
foreach ($k in $topRequired) {
    $ok = Has-Prop $j $k
    if ($ok) { Add-R $true "C1" "顶层字段存在: $k" }
    else { Add-R $false "C1" "顶层字段缺失: $k" }
}

# C2 round
$roundOk = (Has-Prop $j 'round') -and ($j.round -is [int]) -and ($j.round -ge 0)
Add-R $roundOk "C2" "round 必须是 >=0 的整数"

# C3 source_of_truth
$sotOk = $true
if (Has-Prop $j 'source_of_truth') {
    foreach ($k in @('client_profile', 'conversation_log', 'pending')) {
        if (-not (Has-Prop $j.source_of_truth $k)) { $sotOk = $false; Add-R $false "C3" "source_of_truth 缺失: $k" }
        elseif ([string]::IsNullOrWhiteSpace([string]$j.source_of_truth.$k)) { $sotOk = $false; Add-R $false "C3" "source_of_truth.$k 为空" }
    }
} else { $sotOk = $false }
if ($sotOk) { Add-R $true "C3" "source_of_truth 三份状态文件路径完整" }

# C4 this_round_updates 四键
$truOk = $true
if (Has-Prop $j 'this_round_updates') {
    foreach ($k in @('confirmed', 'inferred', 'missing', 'pending')) {
        if (-not (Has-Prop $j.this_round_updates $k)) { $truOk = $false; Add-R $false "C4" "this_round_updates 缺失: $k" }
    }
} else { $truOk = $false }
if ($truOk) { Add-R $true "C4" "this_round_updates 四分类齐全" }

# C5 inferred 必须有 basis（I5 白名单纪律）
$infFail = @()
if (Has-Prop $j 'this_round_updates') {
    foreach ($it in @($j.this_round_updates.inferred)) {
        if ($null -eq $it) { continue }
        $hasBasis = (Has-Prop $it 'basis') -and -not [string]::IsNullOrWhiteSpace([string]$it.basis)
        if (-not $hasBasis) { $infFail += $it }
    }
}
Add-R ($infFail.Count -eq 0) "C5" "每条 inferred 必须写 basis（缺 $($infFail.Count) 条）"

# C6 completion_check
$ccOk = $true
if (Has-Prop $j 'completion_check') {
    $cc = $j.completion_check
    if (-not (Has-Prop $cc 'intake_complete')) { $ccOk = $false; Add-R $false "C6" "completion_check.intake_complete 缺失" }
    elseif (-not ($cc.intake_complete -is [bool])) { $ccOk = $false; Add-R $false "C6" "intake_complete 必须是布尔" }
    foreach ($k in @('blocking_items', 'follow_up_items')) {
        if (-not (Has-Prop $cc $k)) { $ccOk = $false; Add-R $false "C6" "completion_check 缺失: $k" }
    }
} else { $ccOk = $false }
if ($ccOk) { Add-R $true "C6" "completion_check 结构完整" }

# C7 next_questions
$nq = @()
if (Has-Prop $j 'next_questions') { $nq = @($j.next_questions) }
Add-R ($nq.Count -le 3) "C7" "next_questions 不得超过 3 条（当前 $($nq.Count)）"
$qFail = 0
foreach ($q in $nq) {
    if ($null -eq $q) { $qFail++; continue }
    if (-not (Has-Prop $q 'id')) { $qFail++ }
    elseif ([string]$q.id -notmatch '^Q\d{3}$') { $qFail++ }
    if (-not (Has-Prop $q 'priority')) { $qFail++ }
    elseif (@('P0', 'P1', 'P2', 'P3') -notcontains [string]$q.priority) { $qFail++ }
    if (-not ((Has-Prop $q 'question') -and -not [string]::IsNullOrWhiteSpace([string]$q.question))) { $qFail++ }
    if (-not ((Has-Prop $q 'reason') -and -not [string]::IsNullOrWhiteSpace([string]$q.reason))) { $qFail++ }
}
Add-R ($qFail -eq 0) "C7" "next_questions 每条需 id(Q###)/priority(P0-P3)/question/reason（问题 $qFail 处）"

# C8 state_write_result
$swrOk = $true
if (Has-Prop $j 'state_write_result') {
    foreach ($k in @('profile_updated', 'conversation_log_updated', 'pending_updated')) {
        if (-not (Has-Prop $j.state_write_result $k)) { $swrOk = $false; Add-R $false "C8" "state_write_result 缺失: $k" }
    }
} else { $swrOk = $false }
if ($swrOk) { Add-R $true "C8" "state_write_result 三份写回标记齐全" }

# C9 I5：intake_complete=true -> blocking_items 空 + next_questions 空
if ((Has-Prop $j 'completion_check') -and (Has-Prop $j.completion_check 'intake_complete') -and ($j.completion_check.intake_complete -eq $true)) {
    $blk = @($j.completion_check.blocking_items)
    Add-R ($blk.Count -eq 0) "C9/I5" "intake_complete=true 时 blocking_items 必须为空（当前 $($blk.Count)）"
    Add-R ($nq.Count -eq 0) "C9/I5" "intake_complete=true 时 next_questions 必须为空（HF09，当前 $($nq.Count)）"
} else {
    # C10 Gate：未完成时必须有追问，或有 notes 说明为何本轮不追问
    $hasNotes = (Has-Prop $j 'notes') -and -not [string]::IsNullOrWhiteSpace([string]$j.notes)
    Add-R (($nq.Count -ge 1) -or $hasNotes) "C10" "intake_complete=false 时应给出追问，或在 notes 说明本轮不追问的原因"
}

$failCount = @($results | Where-Object { $_.StartsWith("[FAIL]") }).Count
$passCount = @($results | Where-Object { $_.StartsWith("[PASS]") }).Count

Write-Output "===== execution-output 契约校验 ====="
Write-Output "file: $JsonPath"
foreach ($r in $results) { Write-Output $r }
Write-Output "--------------------------------------"
Write-Output "PASS=$passCount  FAIL=$failCount"

if ($ReportPath -ne "") {
    $lines = @("# execution-output 契约校验报告", "", "- 文件：$JsonPath", "- 时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", "- PASS=$passCount  FAIL=$failCount", "")
    $lines += $results
    [System.IO.File]::WriteAllLines($ReportPath, $lines, (New-Object System.Text.UTF8Encoding $true))
}

if ($failCount -gt 0) { exit 1 }
exit 0
