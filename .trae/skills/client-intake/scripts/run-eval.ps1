# client-intake — 真·Eval 执行器（Assertion-driven，不做自评打分）
# 设计原则：
#   1. 不硬编码任何通过结果；无法判定的断言一律记 UNVERIFIED，绝不计为 PASS。
#   2. 只有"可确定性机检"的断言才做 PASS/FAIL 判定；自然语言描述类断言记 MANUAL（需人工/Agent 判定）。
#   3. 若 Case 从未真正执行（客户目录不存在或仍是 R0 空壳），整 Case 记 NOT_EXECUTED，
#      所有断言记 UNVERIFIED —— 这是与旧 run-regression.ps1「假评估」的根本区别。
# 用法：
#   & .\run-eval.ps1 [-CaseId CASE_001] [-CaseDir <...>] [-ClientRoot <...>] [-OutDir <...>]
# 退出码：0 = 无 FAIL；1 = 存在 FAIL

param(
    [string]$CaseId = "",
    [string]$CaseDir = "",
    [string]$ClientRoot = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

# ---- 路径推导 ----
$SkillDir  = Split-Path -Parent $PSScriptRoot
# client-intake -> skills -> .trae -> 工程根
$Root      = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $SkillDir))
if ($CaseDir -eq "")    { $CaseDir = Join-Path $SkillDir "evals\cases" }
if ($ClientRoot -eq "") { $ClientRoot = Join-Path $SkillDir "evals\clients" }
if ($OutDir -eq "")     { $OutDir = Join-Path $SkillDir "evals\runs" }

if (-not (Test-Path -LiteralPath $CaseDir)) { Write-Output "[FAIL] 用例目录不存在: $CaseDir"; exit 1 }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $OutDir "eval_$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Get-Text { param([string]$Path) return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8) }

# ---------- 解析 CASE：按 Round 分段（支持 Branch 分支用例）----------
# 支持三种标题：
#   ## Round N                              -> 公共轮次（Branch = ""）
#   ## Branch A / Round 3 — 说明            -> 分支轮次（Branch = "A"）
#   ### Round N（位于某个 ## Branch 之下）   -> 分支轮次（继承当前 Branch）
# 分支用例（如 CASE_007）各分支互斥，需拆成独立客户目录分别评估。
function Parse-Case {
    param([string]$Path)
    $raw = Get-Text $Path
    $bt = [char]96; $tb3 = $bt.ToString() + $bt.ToString() + $bt.ToString()
    $lines = $raw -split "`r?`n"

    $marks = @()
    $curBranch = ""
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $ln = $lines[$i]
        if ($ln -match '^##\s*Branch\s+(\w+)(?:\s*/.*?Round\s*(\d+))?') {
            $curBranch = $Matches[1]
            # 注意：不能再对 $Matches[2] 做 -match，那会覆盖 $Matches 使 $Matches[2] 变空（-> Round 0）
            $brNum = $Matches[2]
            if ($brNum -match '^\d+$') {
                $marks += [pscustomobject]@{ Line = $i; Round = [int]$brNum; Branch = $curBranch }
            }
            continue
        }
        if ($ln -match '^#{2,3}\s*Round\s*(\d+)') {
            $rn = $Matches[1]
            $marks += [pscustomobject]@{ Line = $i; Round = [int]$rn; Branch = $curBranch }
            continue
        }
    }

    $rounds = @()
    for ($k = 0; $k -lt $marks.Count; $k++) {
        $s = $marks[$k].Line
        $e = if ($k + 1 -lt $marks.Count) { $marks[$k + 1].Line } else { $lines.Count }
        $seg = ""
        if ($e -gt $s) { $seg = ($lines[$s..($e - 1)] -join "`n") }

        # 分支下的输入块可能没有「### 客户输入」标题，故设为可选
        $inputText = ""
        $m1 = [regex]::Match($seg, '(?:###\s*客户输入\s*)?' + $tb3 + 'text\s*(.+?)\s*' + $tb3, [System.Text.RegularExpressions.RegexOptions]::Singleline)
        if ($m1.Success) { $inputText = $m1.Groups[1].Value.Trim() }

        $yaml = ""
        $m2 = [regex]::Match($seg, '(?:###\s*Assertions\s*)?' + $tb3 + 'yaml\s*(.+?)\s*' + $tb3, [System.Text.RegularExpressions.RegexOptions]::Singleline)
        if ($m2.Success) { $yaml = $m2.Groups[1].Value.Trim() }

        $rounds += [pscustomobject]@{
            Round  = $marks[$k].Round
            Branch = $marks[$k].Branch
            Input  = $inputText
            Yaml   = $yaml
        }
    }
    return $rounds
}

# ---------- 解析 YAML 断言块（简易，够用即可） ----------
function Parse-Assertions {
    param([string]$Yaml)
    $a = [ordered]@{
        must_have = @(); must_not_have = @(); must_update_profile = @()
        must_update_log = @(); must_update_pending = @()
        completion = ""; first = @()
        qstates = @()
    }
    $key = ""
    $lines = $Yaml -split "[`r`n]+"
    $cur = $null
    foreach ($ln in $lines) {
        if ($ln -match '^\s*([a-z_]+):\s*$') {
            $key = $Matches[1]
            if ($key -eq 'question_state_assertions') { $cur = $null }
            continue
        }
        if ($ln -match '^\s*intake_complete:\s*(\S+)') { $a.completion = $Matches[1]; continue }
        if ($ln -match '^\s*first:\s*$') { $key = 'first'; continue }
        if ($ln -match '^\s*first:\s*\[\s*\]') { $key = ''; continue }
        if ($ln -match '^\s*-\s+question_intent:\s*(.+?)\s*$') { $cur = [pscustomobject]@{ intent = $Matches[1]; status = "" }; continue }
        if ($ln -match '^\s*expected_status:\s*(.+?)\s*$') {
            if ($null -ne $cur) { $cur.status = $Matches[1]; $a.qstates += $cur; $cur = $null }
            continue
        }
        if ($ln -match '^\s*-\s+(.+?)\s*$') {
            $v = $Matches[1].Trim()
            switch ($key) {
                'must_have'           { $a.must_have += $v }
                'must_not_have'       { $a.must_not_have += $v }
                'must_update_profile' { $a.must_update_profile += $v }
                'must_update_log'     { $a.must_update_log += $v }
                'must_update_pending' { $a.must_update_pending += $v }
                'first'               { $a.first += $v }
            }
        }
    }
    return $a
}

# ---------- 断言分类：可机检 or 需人工 ----------
function Classify-Assertion {
    param([string]$Text)
    # k = v 形式（中英文键名均可）
    if ($Text -match '^\s*([A-Za-z_ ]+?)\s*=\s*(.+?)\s*$') {
        return [pscustomobject]@{ Kind = "KV"; Key = $Matches[1].Trim(); Val = $Matches[2].Trim() }
    }
    if ($Text -match '^\s*pending:\s*(.+?)\s*$') {
        return [pscustomobject]@{ Kind = "PENDING"; Key = "pending"; Val = $Matches[1].Trim() }
    }
    return [pscustomobject]@{ Kind = "MANUAL"; Key = ""; Val = $Text }
}

# 数值多形态候选：800000 <-> 80万
function Get-ValueCandidates {
    param([string]$Val)
    $cands = @($Val)
    if ($Val -match '^\d+$') {
        $n = [double]$Val
        if ($n -ge 10000 -and ($n % 10000) -eq 0) { $cands += ("{0}万" -f ($n / 10000)) }
    }
    if ($Val -match '^(\d+(?:\.\d+)?)万$') {
        $cands += ("{0}" -f ([double]$Matches[1] * 10000))
    }
    return $cands
}

function Test-ValueInProfile {
    param([string]$ProfileText, [string]$Val, [string]$FieldKey = "")
    foreach ($c in (Get-ValueCandidates $Val)) {
        if ($ProfileText -match [regex]::Escape($c)) { return $true }
    }
    return $false
}

# ---------- 结构化语义层：Pending / QID 行读取（快照优先，无快照才回退最终文件）----------
# 说明：字面搜索"received""expired"等状态词会把自然语言断言变成假通过，
#       因此状态类断言一律走结构化行读取，绝不在 Profile 里搜状态词。
function Get-PendingRows {
    param($Snap, [string]$PendingText)
    $rows = @()
    if ($null -ne $Snap -and ($Snap.PSObject.Properties.Name -contains 'pending_items')) {
        foreach ($pi in @($Snap.pending_items)) {
            $rows += [pscustomobject]@{
                Id       = [string]$pi.id
                Qid      = [string]$pi.qid
                Item     = [string]$pi.item
                Status   = [string]$pi.status
                Reminded = [string]$pi.reminded
                Next     = [string]$pi.next
            }
        }
        return ,$rows
    }
    # 回退：解析 PENDING.md 的 Pending Registry 表格（列序对齐 resources/templates/PENDING.md）
    foreach ($ln in ($PendingText -split "`n")) {
        if ($ln -notmatch '^\s*\|') { continue }
        $cells = @(($ln.Trim().Trim('|') -split '\|') | ForEach-Object { $_.Trim() })
        if ($cells.Count -lt 8) { continue }
        if ($cells[0] -eq '' -or $cells[0] -match '编号' -or $cells[0] -match '^-+$') { continue }
        $rows += [pscustomobject]@{
            Id       = $cells[0]; Qid = $cells[1]; Item = $cells[2]
            Status   = $cells[5]; Reminded = $cells[6]; Next = $cells[7]
        }
    }
    return ,$rows
}

function Get-QidRows {
    param($Snap, [string]$LogText)
    $rows = @()
    if ($null -ne $Snap -and ($Snap.PSObject.Properties.Name -contains 'qids')) {
        foreach ($q in @($Snap.qids)) {
            $rows += [pscustomobject]@{
                Id       = [string]$q.id
                Intent   = [string]$q.intent
                Question = [string]$q.question
                Status   = [string]$q.status
                First    = [int]$q.first
                Last     = [int]$q.last
            }
        }
        return ,$rows
    }
    foreach ($ln in ($LogText -split "`n")) {
        if ($ln -notmatch '^\s*\|') { continue }
        $cells = @(($ln.Trim().Trim('|') -split '\|') | ForEach-Object { $_.Trim() })
        if ($cells.Count -lt 9) { continue }
        if ($cells[0] -match 'QID|^-+$' -or $cells[0] -eq '') { continue }
        $f = 0; $l = 0
        [int]::TryParse(($cells[4] -replace 'R',''), [ref]$f) | Out-Null
        [int]::TryParse(($cells[8] -replace 'R',''), [ref]$l) | Out-Null
        $rows += [pscustomobject]@{
            Id = $cells[0]; Intent = $cells[2]; Question = $cells[3]
            Status = $cells[5]; First = $f; Last = $l
        }
    }
    return ,$rows
}

# Pending 状态类 KV 断言：pending_item_status / reminder_count / next_reminder_round
function Test-PendingKV {
    param($Rows, [string]$Key, [string]$Val)
    foreach ($rw in $Rows) {
        switch -Regex ($Key) {
            'pending_item_status'  { if ($rw.Status   -eq $Val) { return $true } }
            'reminder_count'       { if ($rw.Reminded -eq $Val) { return $true } }
            'next_reminder_round'  { if ($rw.Next     -eq $Val) { return $true } }
            default {
                if (($rw.Item -match [regex]::Escape($Val)) -or ($rw.Status -match [regex]::Escape($Val))) { return $true }
            }
        }
    }
    return $false
}

function Get-PendingDigest {
    param($Rows)
    if ($Rows.Count -eq 0) { return "无 Pending 条目" }
    return ("status=$($Rows[0].Status) reminded=$($Rows[0].Reminded) next=$($Rows[0].Next) item=$($Rows[0].Item)")
}

# 断言里的中文字段简称 -> Profile 标准字段名（与 resources/templates/CLIENT_PROFILE.md 一致）
# 只收录不会引起歧义的映射；无法映射的 token 一律跳过，绝不猜测。
$FieldAliases = [ordered]@{
    '配偶年龄'   = @('配偶年龄'); '配偶职业' = @('配偶职业 / 状态')
    '子女人数'   = @('子女人数'); '子女信息' = @('子女信息'); '子女' = @('子女人数','子女信息')
    '父母赡养情况' = @('父母赡养情况'); '父母' = @('父母赡养情况')
    '婚姻状况'   = @('婚姻状况'); '婚姻' = @('婚姻状况')
    '房贷余额'   = @('房贷余额'); '房贷剩余年限' = @('房贷剩余年限'); '房贷' = @('房贷余额')
    '家庭年支出' = @('家庭年支出'); '年支出' = @('家庭年支出'); '支出' = @('家庭年支出')
    '商保概况'   = @('商保概况'); '商保' = @('商保概况')
    '社保医保'   = @('社保医保'); '社保' = @('社保医保')
    '团险 / 福利' = @('团险 / 福利'); '团险' = @('团险 / 福利')
    '生活习惯'   = @('生活习惯')
    '核心风险关注点' = @('核心风险关注点'); '风险' = @('核心风险关注点')
    '其他负债 / 担保' = @('其他负债 / 担保'); '负债' = @('其他负债 / 担保')
    '收入来源'   = @('收入来源')
    '年龄'       = @('年龄'); '性别' = @('性别'); '城市' = @('城市'); '职业' = @('职业')
    '本人收入'   = @('本人收入'); '配偶收入' = @('配偶收入')
    '去年收入'   = @('去年收入'); '今年收入预估' = @('今年收入预估')
    '客户本人健康' = @('客户本人健康'); '配偶健康' = @('配偶健康')
    '子女健康'   = @('子女健康'); '父母健康' = @('父母健康')
}
# 从断言文本中解析出需要落盘的标准字段名（按长短优先，避免"收入"抢先命中"配偶收入"）
function Resolve-FieldTokens {
    param([string]$Text)
    $want = @()
    $work = $Text
    foreach ($alias in ($FieldAliases.Keys | Sort-Object { $_.Length } -Descending)) {
        if ($work -match [regex]::Escape($alias)) {
            foreach ($f in $FieldAliases[$alias]) { if ($want -notcontains $f) { $want += $f } }
            # 命中即挖掉，避免短别名在长别名内部重复命中（如"收入"命中"收入来源"）
            $work = $work -replace [regex]::Escape($alias), ([string][char]0)
        }
    }
    return $want
}

# ---------- 主流程 ----------
$caseFiles = @()
if ($CaseId -ne "") { $caseFiles += (Get-Item (Join-Path $CaseDir "$CaseId.md")) }
else { $caseFiles += @(Get-ChildItem $CaseDir -Filter 'CASE_*.md' | Sort-Object Name) }

$summary = @()
$allLines = @()

# 展开待评估单元：分支用例（如 CASE_007 的 A/B/C）拆成多个独立单元，
# 每个单元 = 公共轮次 + 该分支轮次，并对应独立客户目录。
$units = @()
foreach ($cf in $caseFiles) {
    $baseId = [System.IO.Path]::GetFileNameWithoutExtension($cf.Name)
    $allRounds = Parse-Case -Path $cf.FullName
    $brs = @($allRounds | Where-Object { $_.Branch -ne "" } | ForEach-Object { $_.Branch } | Select-Object -Unique)
    if ($brs.Count -eq 0) {
        $units += [pscustomobject]@{ Id = $baseId; Rounds = $allRounds; Dir = (Join-Path $ClientRoot ($baseId + "-Regression")) }
    } else {
        $common = @($allRounds | Where-Object { $_.Branch -eq "" })
        foreach ($br in $brs) {
            $brR = @($allRounds | Where-Object { $_.Branch -eq $br })
            $units += [pscustomobject]@{
                Id     = ($baseId + "-" + $br)
                Rounds = @($common + $brR)
                Dir    = (Join-Path $ClientRoot ($baseId + "-" + $br + "-Regression"))
            }
        }
    }
}

foreach ($u in $units) {
    $cid = $u.Id
    $rounds = @($u.Rounds)
    $clientDir = $u.Dir
    if (-not (Test-Path -LiteralPath $clientDir)) {
        $cand = Get-ChildItem $ClientRoot -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "$cid*" } | Select-Object -First 1
        if ($cand) { $clientDir = $cand.FullName }
    }

    $cnt = [ordered]@{ PASS = 0; FAIL = 0; UNVERIFIED = 0; MANUAL = 0 }
    $caseLines = @()
    $caseLines += "## $cid"

    # 判定是否真正执行过：CONVERSATION_LOG 中存在 Round >= 1 才是真执行
    $executed = $false
    $notExecReason = ""
    if (-not (Test-Path -LiteralPath $clientDir)) {
        $notExecReason = "客户目录不存在：$clientDir"
    } else {
        $pPath = Join-Path $clientDir "CLIENT_PROFILE.md"
        $lPath = Join-Path $clientDir "CONVERSATION_LOG.md"
        if (-not (Test-Path -LiteralPath $pPath)) {
            $notExecReason = "缺少 CLIENT_PROFILE.md"
        } elseif (-not (Test-Path -LiteralPath $lPath)) {
            $notExecReason = "缺少 CONVERSATION_LOG.md"
        } else {
            $lText0 = Get-Text $lPath
            $maxR = -1
            foreach ($mm in [regex]::Matches($lText0, '(?m)^###\s*Round\s*(\d+)')) {
                $n = [int]$mm.Groups[1].Value
                if ($n -gt $maxR) { $maxR = $n }
            }
            if ($maxR -lt 1) {
                $notExecReason = "LOG 中最大 Round = $maxR（仅初始化），该 Case 从未真正执行过 Skill"
            } else { $executed = $true }
        }
    }

    if (-not $executed) {
        $caseLines += ""
        $caseLines += "- 执行状态：**NOT_EXECUTED**（$notExecReason）"
        $caseLines += "- 结论：**本 Case 无法评估**。所有断言记为 UNVERIFIED，不计通过。"
        $totalAssert = 0
        foreach ($r in $rounds) { $totalAssert += (Parse-Assertions $r.Yaml).must_have.Count + (Parse-Assertions $r.Yaml).must_not_have.Count }
        $cnt.UNVERIFIED = $totalAssert
        $summary += [pscustomobject]@{ Case = $cid; Status = "NOT_EXECUTED"; PASS = 0; FAIL = 0; UNVERIFIED = $totalAssert; MANUAL = 0 }
        $allLines += $caseLines
        $allLines += ""
        continue
    }

    $pText  = Get-Text (Join-Path $clientDir "CLIENT_PROFILE.md")
    $lText  = Get-Text (Join-Path $clientDir "CONVERSATION_LOG.md")
    $pdText = Get-Text (Join-Path $clientDir "PENDING.md")

    # must_not_have 只针对"已确认事实"：剔除 Follow-up Items 小节（那是待补清单，出现关键词不代表已记录）
    $pTextNoFollowup = [regex]::Replace($pText, '(?ms)^##\s*\d*\.?\s*Follow-up Items.*?(?=^##\s|\z)', '')

    $caseLines += ""
    $caseLines += "- 执行状态：EXECUTED（$clientDir）"

    $lastRound = ($rounds | Sort-Object Round | Select-Object -Last 1)
    foreach ($r in $rounds) {
        $a = Parse-Assertions $r.Yaml
        $caseLines += ""
        $caseLines += "### Round $($r.Round)"

        # ---- per-round 快照（解决"多 Round 时序断言无快照"问题）----
        # 约定路径：clients/<客户>/snapshots/round-R<N>.json
        # 存在则时序断言可机检；不存在仍记 MANUAL/UNVERIFIED，绝不冒充通过。
        $snap = $null
        $snapPath = Join-Path $clientDir ("snapshots" + [IO.Path]::DirectorySeparatorChar + "round-R" + $r.Round + ".json")
        if (Test-Path -LiteralPath $snapPath) {
            try { $snap = (Get-Text $snapPath) | ConvertFrom-Json } catch { $snap = $null }
        }
        if ($snap) { $caseLines += "- 快照：round-R$($r.Round).json 已加载（时序断言可机检）" }
        else { $caseLines += "- 快照：round-R$($r.Round).json 缺失（时序断言仍记 MANUAL/UNVERIFIED）" }

        # must_have
        foreach ($item in $a.must_have) {
            $c = Classify-Assertion $item
            if ($c.Kind -eq "MANUAL") { $cnt.MANUAL++; $caseLines += "- [MANUAL] must_have: $item"; continue }
            if ($c.Kind -eq "PENDING") {
                # 容错：断言"保单待补" vs 记录"保单"，允许去尾词与前 2 字匹配
                $cands = @($c.Val)
                $trimmed = [regex]::Replace($c.Val, '(待补|资料|信息|明细|具体险种)$', '')
                if ($trimmed -ne $c.Val) { $cands += $trimmed }
                if ($c.Val.Length -ge 2) { $cands += $c.Val.Substring(0, 2) }
                $ok = $false
                foreach ($cd in $cands) { if ($pdText -match [regex]::Escape($cd)) { $ok = $true; break } }
                if ($ok) { $cnt.PASS++; $caseLines += "- [PASS] must_have(pending): $item" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_have(pending): $item（PENDING 中未找到）" }
                continue
            }
            if ($c.Kind -eq "KV" -and ($c.Key -match '(?i)pending|reminder')) {
                # 状态类断言走结构化 Pending 行，绝不在 Profile 里搜状态词
                $prows = Get-PendingRows -Snap $snap -PendingText $pdText
                $psrc  = if ($snap) { "Round $($r.Round) 快照" } else { "最终 PENDING.md" }
                if ($prows.Count -eq 0) {
                    $cnt.FAIL++; $caseLines += "- [FAIL] must_have: $item（$psrc 无 Pending 条目）"
                } elseif (Test-PendingKV -Rows $prows -Key $c.Key -Val $c.Val) {
                    $cnt.PASS++; $caseLines += "- [PASS] must_have: $item（$psrc 命中）"
                } else {
                    $cnt.FAIL++; $caseLines += "- [FAIL] must_have: $item（$psrc 未命中，实际 $(Get-PendingDigest $prows)）"
                }
                continue
            }
            $ok = Test-ValueInProfile -ProfileText $pText -Val $c.Val -FieldKey $c.Key
            if ($ok) { $cnt.PASS++; $caseLines += "- [PASS] must_have: $item" }
            else { $cnt.FAIL++; $caseLines += "- [FAIL] must_have: $item（Profile 中未找到值『$($c.Val)』）" }
        }

        # must_not_have
        foreach ($item in $a.must_not_have) {
            $c = Classify-Assertion $item
            if ($c.Kind -eq "MANUAL") {
                # ---- 语义化否定断言：结构化机检，避免字面搜索把断言变成假通过 ----
                $psrc = if ($snap) { "Round $($r.Round) 快照" } else { "最终 PENDING.md" }

                # 1) "保持/仍然是 pending"：不应还有状态为 pending 的条目
                if ($item -match '(?i)(保持|仍然|继续|还是)\s*pending') {
                    $prows = Get-PendingRows -Snap $snap -PendingText $pdText
                    $still = @($prows | Where-Object { $_.Status -eq 'pending' })
                    if ($still.Count -gt 0) {
                        $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（$psrc 仍有 $($still.Count) 条 pending）"
                    } else {
                        $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（$psrc 已无 pending 条目）"
                    }
                    continue
                }
                # 2) "多个/重复 Pending Item"：条目数不得超过 1
                if ($item -match '(?i)(多个|重复).*Pending|Pending.*(重复)') {
                    $prows = Get-PendingRows -Snap $snap -PendingText $pdText
                    if ($prows.Count -gt 1) {
                        $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（$psrc 有 $($prows.Count) 条 Pending）"
                    } else {
                        $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（$psrc Pending 条目数 = $($prows.Count)）"
                    }
                    continue
                }
                # 3) "创建/新增新 QID"：本轮不得产生新的提问
                if ($item -match '(?i)(创建|新增|新)\s*(的)?\s*QID') {
                    if ($snap) {
                        $nqc = @($snap.next_questions).Count
                        if ($nqc -eq 0) { $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（Round $($r.Round) 快照 next_questions 为空）" }
                        else { $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（Round $($r.Round) 快照新增了 $nqc 个提问）" }
                    } else { $cnt.MANUAL++; $caseLines += "- [MANUAL] must_not_have: $item（缺本轮快照，需人工判定）" }
                    continue
                }
                # 4) "第 N 次提醒"：已提醒次数必须严格小于 N
                if ($item -match '第\s*(\d+)\s*次.*提醒') {
                    $limit = [int]$Matches[1]
                    $prows = Get-PendingRows -Snap $snap -PendingText $pdText
                    $mx = 0
                    foreach ($rw in $prows) {
                        $v = 0; [int]::TryParse([string]$rw.Reminded, [ref]$v) | Out-Null
                        if ($v -gt $mx) { $mx = $v }
                    }
                    if ($mx -ge $limit) { $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（$psrc 已提醒 $mx 次）" }
                    else { $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（$psrc 已提醒 $mx 次 < $limit）" }
                    continue
                }
                # 5) "旧 QID 仍保持 unanswered"：跨轮后旧问题不得还挂着 unanswered
                if ($item -match '(?i)QID.*unanswered') {
                    $qrows = Get-QidRows -Snap $snap -LogText $lText
                    $stale = @($qrows | Where-Object { ($_.Status -eq 'unanswered') -and ($_.First -lt $r.Round) })
                    if ($stale.Count -gt 0) {
                        $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（$($stale[0].Id) 自 R$($stale[0].First) 起仍为 unanswered）"
                    } else {
                        $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（无跨轮遗留的 unanswered QID）"
                    }
                    continue
                }
                # 6) "机械重复上一轮同一问法"：本轮首问文本不得与上一轮完全相同
                if ($item -match '(?i)(重复|复读).*(原问题|原文|同一问题|同一问法)') {
                    if ($snap) {
                        $prev = $null
                        for ($pr = ($r.Round - 1); $pr -ge 1; $pr--) {
                            $pp = Join-Path $clientDir ("snapshots" + [IO.Path]::DirectorySeparatorChar + "round-R" + $pr + ".json")
                            if (Test-Path -LiteralPath $pp) { try { $prev = (Get-Text $pp) | ConvertFrom-Json } catch { $prev = $null } ; break }
                        }
                        $curQ = ""; if (@($snap.next_questions).Count -gt 0) { $curQ = [string]$snap.next_questions[0].question }
                        if ($null -eq $prev) { $cnt.MANUAL++; $caseLines += "- [MANUAL] must_not_have: $item（缺上一轮快照，无法比对）" }
                        elseif ($curQ -eq "") { $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（本轮无提问）" }
                        else {
                            $prevQ = ""; if (@($prev.next_questions).Count -gt 0) { $prevQ = [string]$prev.next_questions[0].question }
                            if ($curQ -ne "" -and $curQ -eq $prevQ) { $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（本轮首问与上一轮完全相同）" }
                            else { $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（本轮首问已换问法）" }
                        }
                    } else { $cnt.MANUAL++; $caseLines += "- [MANUAL] must_not_have: $item（缺本轮快照，需人工判定）" }
                    continue
                }
                # 自然语言：按关键词在全部状态文件中搜索
                $hit = ($pTextNoFollowup -match [regex]::Escape($item)) -or ($lText -match [regex]::Escape($item)) -or ($pdText -match [regex]::Escape($item))
                if ($hit) { $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（状态文件中出现）" }
                else { $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（未出现）" }
                continue
            }
            if ($c.Val -match '任意数字|任意值') {
                # 时序性断言：本轮结束时不该有值（后续轮才允许填入）—— 必须用本轮快照判定
                if (-not $snap) {
                    $cnt.MANUAL++
                    $caseLines += "- [MANUAL] must_not_have: $item（时序性断言，缺 round-R$($r.Round) 快照，无法机检）"
                    continue
                }
                $rows = @(@($snap.confirmed) | Where-Object { $_.key -eq $c.Key })
                $hasVal = $false
                $gotVal = ""
                foreach ($rw in $rows) {
                    $v = [string]$rw.value
                    if ([string]::IsNullOrWhiteSpace($v)) { continue }
                    if ($v -eq '❓') { continue }
                    if ($c.Val -match '任意数字' -and ($v -notmatch '\d')) { continue }
                    $hasVal = $true; $gotVal = $v; break
                }
                if ($hasVal) { $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（Round $($r.Round) 快照中已有值『$gotVal』）" }
                else { $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item（Round $($r.Round) 快照中确无值）" }
                continue
            }
            $hit2 = $pText -match [regex]::Escape($c.Val)
            if ($hit2) { $cnt.FAIL++; $caseLines += "- [FAIL] must_not_have: $item（Profile 中出现『$($c.Val)』）" }
            else { $cnt.PASS++; $caseLines += "- [PASS] must_not_have: $item" }
        }

        # completion_expectation：仅最后一轮可机检（Profile 为最终态）
        if ($a.completion -ne "") {
            if ($r.Round -eq $lastRound.Round) {
                $row = ($pText -split "`n") | Where-Object { $_ -match '是否可进入\s*Needs\s*Analysis' } | Select-Object -First 1
                $actual = ""
                if ($row) { $cells = ($row.Trim().Trim('|') -split '\|'); if ($cells.Count -ge 2) { $actual = $cells[1].Trim() } }
                $expectBool = ($a.completion -match 'true')
                $actualBool = ($actual -match '是|可|true')
                if ($actual -eq "") { $cnt.UNVERIFIED++; $caseLines += "- [UNVERIFIED] completion_expectation: 无法解析 Profile 完成态" }
                elseif ($expectBool -eq $actualBool) { $cnt.PASS++; $caseLines += "- [PASS] completion_expectation: intake_complete=$($a.completion)（Profile 实际『$actual』）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] completion_expectation: 期望 $($a.completion)，Profile 实际『$actual』" }
            } elseif ($snap -and ($snap.PSObject.Properties.Name -contains 'completion_check') -and ($snap.completion_check.PSObject.Properties.Name -contains 'intake_complete')) {
                $expectBool = ($a.completion -match 'true')
                $actualBool = [bool]$snap.completion_check.intake_complete
                if ($expectBool -eq $actualBool) {
                    $cnt.PASS++
                    $caseLines += "- [PASS] completion_expectation: intake_complete=$($a.completion)（Round $($r.Round) 快照实际=$actualBool）"
                } else {
                    $cnt.FAIL++
                    $caseLines += "- [FAIL] completion_expectation: 期望 $($a.completion)，Round $($r.Round) 快照实际=$actualBool"
                }
            } else {
                $cnt.UNVERIFIED++; $caseLines += "- [UNVERIFIED] completion_expectation(Round $($r.Round)): 无本轮快照，无法机检"
            }
        }

        # question_state_assertions
        foreach ($qs in $a.qstates) {
            $row = ($lText -split "`n") | Where-Object { ($_ -match '^\|') -and ($_ -match [regex]::Escape($qs.intent)) } | Select-Object -First 1
            if (-not $row) { $cnt.UNVERIFIED++; $caseLines += "- [UNVERIFIED] QID『$($qs.intent)』未注册，无法判定状态"; continue }
            $cells = ($row.Trim().Trim('|') -split '\|')
            $status = if ($cells.Count -ge 6) { $cells[5].Trim() } else { "" }
            if ($status -eq $qs.status) { $cnt.PASS++; $caseLines += "- [PASS] QID『$($qs.intent)』状态=$status" }
            else { $cnt.FAIL++; $caseLines += "- [FAIL] QID『$($qs.intent)』期望=$($qs.status)，实际=$status" }
        }

        # next_question_priority / must_update_* -> MANUAL（需 Agent 判定或 per-round 输出快照）
        if ($a.first.Count -gt 0) {
          if ($snap -and ($snap.PSObject.Properties.Name -contains 'next_questions')) {
            $nq = @($snap.next_questions)
            if ($a.first.Count -gt 1) {
                # 多个候选 = one_of 语义：首问命中任一候选即算 1 条断言（否则同一首问会被重复判 FAIL）
                $candTxt = ($a.first -join ' / ')
                if ($nq.Count -eq 0) {
                    $cnt.FAIL++; $caseLines += "- [FAIL] next_question_priority.first: [$candTxt]（期望首问，但 Round $($r.Round) 快照 next_questions 为空）"
                } else {
                    $intent   = [string]$nq[0].intent
                    $question = if ($nq[0].PSObject.Properties.Name -contains 'question') { [string]$nq[0].question } else { "" }
                    $hitAny = $false
                    foreach ($f in $a.first) {
                        if (($intent -match [regex]::Escape($f)) -or ($question -match [regex]::Escape($f))) { $hitAny = $true; break }
                    }
                    if ($hitAny) { $cnt.PASS++; $caseLines += "- [PASS] next_question_priority.first: [$candTxt] 命中首问『$intent』" }
                    else { $cnt.FAIL++; $caseLines += "- [FAIL] next_question_priority.first: [$candTxt] 未命中首问『$intent』" }
                }
            } else {
                foreach ($f in $a.first) {
                    if ($nq.Count -eq 0) {
                        $cnt.FAIL++; $caseLines += "- [FAIL] next_question_priority.first: $f（期望首问，但 Round $($r.Round) 快照 next_questions 为空）"
                        continue
                    }
                    $intent   = [string]$nq[0].intent
                    $question = if ($nq[0].PSObject.Properties.Name -contains 'question') { [string]$nq[0].question } else { "" }
                    $hitF = ($intent -match [regex]::Escape($f)) -or ($question -match [regex]::Escape($f))
                    if ($hitF) { $cnt.PASS++; $caseLines += "- [PASS] next_question_priority.first: $f（Round $($r.Round) 快照首问=『$intent』）" }
                    else { $cnt.FAIL++; $caseLines += "- [FAIL] next_question_priority.first: $f（Round $($r.Round) 快照首问=『$intent』）" }
                }
            }
          } else {
            foreach ($f in $a.first) { $cnt.MANUAL++; $caseLines += "- [MANUAL] next_question_priority.first: $f（缺本轮快照，需人工判定）" }
          }
        }
        foreach ($m in $a.must_update_profile) {
            $negated = ($m -match '不把|不在|不写|不得|禁止|避免|不应|无需写')
            # 1) 结构化：断言中提到的标准字段是否已落进 Profile（用本轮快照 confirmed 判定）
            if (-not $negated) {
                $wants = Resolve-FieldTokens $m
                if ($wants.Count -gt 0) {
                    $confRows = @()
                    if ($snap -and ($snap.PSObject.Properties.Name -contains 'confirmed')) { $confRows = @($snap.confirmed) }
                    $have = @($confRows | ForEach-Object { [string]$_.field })
                    $miss = @()
                    foreach ($w in $wants) { if (($have -contains $w) -eq $false) { $miss += $w } }
                    if ($miss.Count -eq 0) {
                        $cnt.PASS++; $caseLines += "- [PASS] must_update_profile: $m（Round $($r.Round) 快照已落字段：$($wants -join '、')）"
                    } else {
                        $cnt.FAIL++; $caseLines += "- [FAIL] must_update_profile: $m（Round $($r.Round) 快照缺少字段：$($miss -join '、')；已有：$($have -join '、')）"
                    }
                    continue
                }
            }
            # 2) 结构化：完成态 / 缺口置空 / Follow-up 转入（读 Profile 对应小节）
            if ($m -match 'Completion Status.*(已完成|完成)') {
                $rowc = ($pText -split "`n") | Where-Object { $_ -match '是否可进入\s*Needs\s*Analysis' } | Select-Object -First 1
                $okc = $false
                if ($rowc) { $cc = ($rowc.Trim().Trim('|') -split '\|'); if ($cc.Count -ge 2 -and $cc[1].Trim() -match '是') { $okc = $true } }
                if ($okc) { $cnt.PASS++; $caseLines += "- [PASS] must_update_profile: $m（Profile 完成态=是）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_profile: $m（Profile 完成态非『是』）" }
                continue
            }
            if ($m -match 'Critical Missing Items\s*置空') {
                $sec = [regex]::Match($pText, '(?ms)^##\s*\d*\.?\s*Critical Missing Items.*?(?=^##\s|\z)').Value
                if ($sec -match '（无）') { $cnt.PASS++; $caseLines += "- [PASS] must_update_profile: $m（Profile §3 已置空）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_profile: $m（Profile §3 仍有条目）" }
                continue
            }
            if ($m -match 'Follow-up Items') {
                $sec = [regex]::Match($pText, '(?ms)^##\s*\d*\.?\s*Follow-up Items.*?(?=^##\s|\z)').Value
                if ($sec -match '\[空\]') { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_profile: $m（Profile §5 仍为空）" }
                else { $cnt.PASS++; $caseLines += "- [PASS] must_update_profile: $m（Profile §5 已有条目）" }
                continue
            }
            $cnt.MANUAL++; $caseLines += "- [MANUAL] must_update_profile: $m"
        }
        # must_update_log：含「Round N 原文」可机检（检查 Log 中存在该 Round）
        foreach ($m in $a.must_update_log) {
            # ---- QID 结构化断言：用快照 qids 判定，绝不做字面搜索 ----
            $qrows = Get-QidRows -Snap $snap -LogText $lText
            $qsrc = if ($snap) { "Round $($r.Round) 快照" } else { "最终 CONVERSATION_LOG" }
            $wantSt = ""
            foreach ($w in @('answered','declined','ignored','pending','expired','received')) {
                if ($m -match ("(?i)" + $w)) { $wantSt = $w; break }
            }
            if ($wantSt -eq "" -and ($m -match '已回答')) { $wantSt = 'answered' }
            if ($wantSt -ne "" -and ($m -match '(?i)QID|问题状态')) {
                $hitq = @($qrows | Where-Object { $_.Status -eq $wantSt })
                if ($hitq.Count -gt 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_log: $m（$qsrc $($hitq[0].Id) 状态=$wantSt）" }
                elseif ($qrows.Count -eq 0) { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_log: $m（$qsrc 无 QID 记录）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_log: $m（$qsrc 实际状态：$(($qrows | ForEach-Object { $_.Id + '=' + $_.Status }) -join ', ')）" }
                continue
            }
            if ($m -match '注册\s*QID') {
                if ($qrows.Count -gt 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_log: $m（$qsrc 已注册 $($qrows.Count) 个 QID）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_log: $m（$qsrc 无 QID 注册）" }
                continue
            }
            if ($m -match '问题状态发生更新') {
                $moved = @($qrows | Where-Object { $_.Status -ne 'unanswered' })
                if ($moved.Count -gt 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_log: $m（$qsrc 有 $($moved.Count) 个 QID 已转出 unanswered）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_log: $m（$qsrc 所有 QID 仍为 unanswered）" }
                continue
            }
            if ($m -match 'Intent\s*=\s*(.+)') {
                $rest = $Matches[1] -replace '的\s*P0\s*问题', ''
                $cands = @($rest -split '或' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
                $hitI = $false
                foreach ($qr in $qrows) { foreach ($cd in $cands) { if ($qr.Intent -match [regex]::Escape($cd)) { $hitI = $true; break } } if ($hitI) { break } }
                if ($hitI) { $cnt.PASS++; $caseLines += "- [PASS] must_update_log: $m（$qsrc 命中 Intent：$(($qrows | ForEach-Object { $_.Intent }) -join '/')）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_log: $m（$qsrc Intent 实际：$(($qrows | ForEach-Object { $_.Intent }) -join '/')）" }
                continue
            }
            $mm = [regex]::Match($m, 'Round\s*(\d+)')
            if ($mm.Success -and ($m -match '原文')) {
                $rn = $mm.Groups[1].Value
                if ([regex]::IsMatch($lText, ('###\s*Round\s*' + $rn + '\b'))) {
                    $cnt.PASS++; $caseLines += "- [PASS] must_update_log: $m（Log 中存在 Round $rn）"
                } else {
                    $cnt.FAIL++; $caseLines += "- [FAIL] must_update_log: $m（Log 中未找到 Round $rn）"
                }
                continue
            }
            $cnt.MANUAL++; $caseLines += "- [MANUAL] must_update_log: $m"
        }
        # must_update_pending：保持为空 / 新增某条目 可机检。
        # 优先用本轮快照（"R1 时 PENDING 为空"是时序断言，不能拿最终态判定）；无快照才降级用最终 PENDING.md。
        foreach ($m in $a.must_update_pending) {
            $snapPend = $null
            if ($snap -and ($snap.PSObject.Properties.Name -contains 'pending_items')) { $snapPend = @($snap.pending_items) }
            $src = if ($null -ne $snapPend) { "Round $($r.Round) 快照" } else { "最终 PENDING.md" }
            $prows = Get-PendingRows -Snap $snap -PendingText $pdText

            # 0) KV 形式（如 next_reminder_round = R5）：走结构化 Pending 判定
            if ($m -match '^\s*([A-Za-z_]+)\s*=\s*(.+?)\s*$') {
                $k0 = $Matches[1]; $v0 = $Matches[2].Trim()
                if ($k0 -match '(?i)pending|reminder') {
                    if ($prows.Count -eq 0) {
                        $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 无 Pending 条目）"
                    } elseif (Test-PendingKV -Rows $prows -Key $k0 -Val $v0) {
                        $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 命中）"
                    } else {
                        $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 未命中，实际 $(Get-PendingDigest $prows)）"
                    }
                    continue
                }
            }
            # 0b) related_qid：Pending 条目必须挂上关联 QID
            if ($m -match '(?i)related_qid') {
                $linked = @($prows | Where-Object { [string]$_.Qid -ne "" })
                if ($linked.Count -gt 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 中 $($linked.Count) 条已关联 QID：$($linked[0].Qid)）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 中无条目关联 QID）" }
                continue
            }
            # 0c) "更新为 X"：Pending 状态必须等于 X
            if ($m -match '更新为\s*([A-Za-z_]+)') {
                $want = $Matches[1]
                $got = @($prows | Where-Object { $_.Status -eq $want })
                if ($got.Count -gt 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 状态 = $want）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 实际 $(Get-PendingDigest $prows)）" }
                continue
            }
            # 0d) "已提醒 N 次"：reminder_count 必须等于 N
            if ($m -match '已提醒\s*(\d+)\s*次') {
                $wantN = $Matches[1]
                $gotN = @($prows | Where-Object { $_.Reminded -eq $wantN })
                if ($gotN.Count -gt 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 已提醒 $wantN 次）" }
                else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 实际 $(Get-PendingDigest $prows)）" }
                continue
            }

            # 否定语义优先：「无新增 / 保持为空 / 无需新增」一律按"应为空"判定。
            # 注意「无新增，除非客户明确承诺补保单」这类带例外的否定句，仍属否定，不能按"应含保单"判。
            if ($m -match '保持为空|无新增|无需新增|仍为空') {
                if ($null -ne $snapPend) {
                    if ($snapPend.Count -eq 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 无 pending 条目）" }
                    else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 已有 $($snapPend.Count) 条）" }
                } else {
                    $dataRows = @($pdText -split "`n" | Where-Object {
                        ($_ -match '^\|\s*([^|\s][^|]*)\s*\|') -and
                        ($_ -notmatch '^\|[\s\-|]+\|$') -and
                        ($_ -notmatch '编号|Related QID')
                    })
                    if ($dataRows.Count -eq 0) { $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 无有效条目）" }
                    else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 仍有 $($dataRows.Count) 条）" }
                }
                continue
            }
            $kw = ""
            foreach ($w in @('保单','体检报告','收入证明','贷款合同')) {
                if ($m -match [regex]::Escape($w)) { $kw = $w; break }
            }
            if ($kw -ne "" -and ($m -match '新增|仍保留|保留')) {
                if ($null -ne $snapPend) {
                    $hit = $false
                    foreach ($pi in $snapPend) {
                        if ([string]$pi.item -match [regex]::Escape($kw)) { $hit = $true; break }
                    }
                    if ($hit) { $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 含『$kw』）" }
                    else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 未含『$kw』）" }
                } else {
                    if ($pdText -match [regex]::Escape($kw)) { $cnt.PASS++; $caseLines += "- [PASS] must_update_pending: $m（$src 含『$kw』）" }
                    else { $cnt.FAIL++; $caseLines += "- [FAIL] must_update_pending: $m（$src 未含『$kw』）" }
                }
                continue
            }
            $cnt.MANUAL++; $caseLines += "- [MANUAL] must_update_pending: $m"
        }
    }

    $status = if ($cnt.FAIL -gt 0) { "FAIL" } elseif ($cnt.PASS -gt 0) { "PARTIAL" } else { "NO_DATA" }
    $summary += [pscustomobject]@{ Case = $cid; Status = $status; PASS = $cnt.PASS; FAIL = $cnt.FAIL; UNVERIFIED = $cnt.UNVERIFIED; MANUAL = $cnt.MANUAL }
    $allLines += $caseLines
    $allLines += ""
}

# ---------- 报告 ----------
Write-Output "===== client-intake 真·Eval 执行器 ====="
Write-Output ("用例目录: " + $CaseDir)
Write-Output ("客户根目录: " + $ClientRoot)
Write-Output ""
Write-Output ("{0,-12} {1,-14} {2,6} {3,6} {4,10} {5,8}" -f "CASE", "STATUS", "PASS", "FAIL", "UNVERIFIED", "MANUAL")
Write-Output ("-" * 62)
foreach ($s in $summary) {
    Write-Output ("{0,-12} {1,-14} {2,6} {3,6} {4,10} {5,8}" -f $s.Case, $s.Status, $s.PASS, $s.FAIL, $s.UNVERIFIED, $s.MANUAL)
}
$tp = ($summary | Measure-Object PASS -Sum).Sum
$tf = ($summary | Measure-Object FAIL -Sum).Sum
$tu = ($summary | Measure-Object UNVERIFIED -Sum).Sum
$tm = ($summary | Measure-Object MANUAL -Sum).Sum
Write-Output ("-" * 62)
Write-Output ("TOTAL       {0,6} {1,6} {2,10} {3,8}" -f $tp, $tf, $tu, $tm)
Write-Output ""
Write-Output "说明：UNVERIFIED = 无法机检（多为 Case 未真正执行）；MANUAL = 需人工/Agent 判定。两者均不计为通过。"

$reportPath = Join-Path $runDir "EVAL_REPORT.md"
$head = @(
    "# client-intake Eval 报告",
    "",
    "- 时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "- 用例目录：$CaseDir",
    "- 客户根目录：$ClientRoot",
    "",
    "| CASE | STATUS | PASS | FAIL | UNVERIFIED | MANUAL |",
    "|------|--------|------|-----|-----------|--------|"
)
foreach ($s in $summary) { $head += "| $($s.Case) | $($s.Status) | $($s.PASS) | $($s.FAIL) | $($s.UNVERIFIED) | $($s.MANUAL) |" }
$head += "| **TOTAL** | | **$tp** | **$tf** | **$tu** | **$tm** |"
$head += ""
[System.IO.File]::WriteAllLines($reportPath, ($head + $allLines), (New-Object System.Text.UTF8Encoding $true))
Write-Output ""
Write-Output "报告: $reportPath"

# 结构化汇总（供 run-regression.ps1 / CI 消费）
$summaryPath = Join-Path $runDir "eval_summary.json"
$summaryObj = [ordered]@{
    timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    totals    = [ordered]@{ pass = $tp; fail = $tf; unverified = $tu; manual = $tm }
    cases     = $summary
}
[System.IO.File]::WriteAllText($summaryPath, ($summaryObj | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $true))
Write-Output "汇总: $summaryPath"

if ($tf -gt 0) { exit 1 }
exit 0
