#Requires -Version 5.1
<#
    apply-execution.ps1 — 把「执行规格」渲染为三份状态文件 + per-round 快照

    用途：
      1. 让 8 个 Eval Case 能被"真正执行"：由结构化规格生成 CLIENT_PROFILE /
         CONVERSATION_LOG / PENDING 三份状态文件，格式与 resources/templates 一致。
      2. 同时按 Round 落盘 execution-output 快照（round-R<N>.json），
         供 run-eval.ps1 机检时序性断言（解决"中间轮无法判定"问题）。

    输入：evals/executions/<CASE_ID>.json
    输出：clients/<client_dir>/{CLIENT_PROFILE,CONVERSATION_LOG,PENDING}.md
          clients/<client_dir>/snapshots/round-R<N>.json

    本脚本只做"格式渲染"，不做任何业务判断。规格内容是否合规由人/Agent 负责；
    渲染后应用 check-state-invariants.ps1 与 run-eval.ps1 验证。

    用法：
      .apply-execution.ps1 -CaseId CASE_001
      .apply-execution.ps1                      # 渲染 evals/executions/ 下全部
      .apply-execution.ps1 -CaseId CASE_001 -Validate   # 渲染后顺带跑不变量检查
#>
[CmdletBinding()]
param(
    [string]$CaseId   = "",
    [string]$Root     = "",
    [switch]$Validate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------- 路径 ----------
$SkillDir = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Root)) {
    # scripts/ -> <skill>/.trae/skills/client-intake -> .trae/skills -> .trae -> 工程根
    $Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $SkillDir))
}
$ExecDir    = Join-Path $SkillDir "evals\executions"
$ClientRoot = Join-Path $SkillDir "evals\clients"
$enc        = New-Object System.Text.UTF8Encoding $true

if (-not (Test-Path -LiteralPath $ExecDir)) {
    Write-Output "FATAL: 执行规格目录不存在：$ExecDir"
    exit 2
}

# ---------- Profile 标准小节字段（与 resources/templates 保持一致）----------
$SectionFields = [ordered]@{
    "1.1" = @("年龄","性别","城市","职业","婚姻状况")
    "1.2" = @("配偶年龄","配偶职业 / 状态","子女人数","子女信息","父母赡养情况")
    "1.3" = @("本人收入","配偶收入","家庭年支出","收入来源")
    "1.4" = @("房贷余额","房贷剩余年限","其他负债 / 担保","社保医保","商保概况","团险 / 福利")
    "1.5" = @("客户本人健康","配偶健康","子女健康","父母健康","生活习惯","核心风险关注点")
}
$SectionTitle = [ordered]@{
    "1.1" = "基本信息"; "1.2" = "家庭结构"; "1.3" = "收入与支出"
    "1.4" = "负债与保障"; "1.5" = "健康与风险"
}

function Get-Cell {
    param($Obj, [string]$Name, [string]$Default = "")
    if ($null -eq $Obj) { return $Default }
    $p = $Obj.PSObject.Properties[$Name]
    if ($null -eq $p) { return $Default }
    $v = [string]$p.Value
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v
}

# 列表转展示串（空则显示"无"）
function Join-Or-None {
    param($Items, [string]$Prop)
    $vals = @()
    foreach ($i in @($Items)) {
        $v = Get-Cell $i $Prop
        if ($v -ne "") { $vals += $v }
    }
    if ($vals.Count -eq 0) { return "无" }
    return ($vals -join "、")
}

function Render-Profile {
    param($Spec, $Rounds)

    # 累加所有 confirmed：同字段后者覆盖前者
    $latest = [ordered]@{}
    $order  = @()
    foreach ($r in $Rounds) {
        foreach ($c in @($r.confirmed)) {
            $f = Get-Cell $c 'f'
            if ($f -eq "") { continue }
            if (-not $latest.Contains($f)) { $order += $f }
            $latest[$f] = [pscustomobject]@{
                S = Get-Cell $c 's' '1.1'
                V = Get-Cell $c 'v'
                R = ("R" + (Get-Cell $c 'round' $r.round))
                T = Get-Cell $c 't'
            }
        }
    }

    $lastRound = $Rounds[$Rounds.Count - 1]

    $doneFlag = "进行中"
    if ([bool]$lastRound.intake_complete) { $doneFlag = "已完成" }

    $L = New-Object System.Collections.ArrayList
    [void]$L.Add("# Client Profile")
    [void]$L.Add("")
    [void]$L.Add("> 角色：客户信息唯一长期状态源")
    [void]$L.Add("> 读取优先级：最高")
    [void]$L.Add("> 供谁使用：当前 Client Intake Skill + 后续 Needs Analysis Skill")
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## Client Summary")
    [void]$L.Add("")
    [void]$L.Add("| 项 | 值 |")
    [void]$L.Add("|----|----|")
    $clientNo = Get-Cell $Spec 'client_dir'
    [void]$L.Add("| 客户编号 | $clientNo |")
    [void]$L.Add("| Intake 状态 | $doneFlag |")
    $lastR = [string]$lastRound.round
    [void]$L.Add("| 已完成轮次 | R$lastR |")
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 1. Confirmed Facts")
    [void]$L.Add("")

    foreach ($sec in $SectionFields.Keys) {
        $secTitle = $SectionTitle[$sec]
        [void]$L.Add("### $sec $secTitle")
        [void]$L.Add("")
        [void]$L.Add("| 字段 | 当前值 | Source Round | Source Text |")
        [void]$L.Add("|------|--------|--------------|-------------|")
        $std = $SectionFields[$sec]
        foreach ($f in $std) {
            if ($latest.Contains($f)) {
                $it = $latest[$f]
                [void]$L.Add("| $f | $($it.V) | $($it.R) | $($it.T) |")
            } else {
                [void]$L.Add("| $f | ❓ | | |")
            }
        }
        foreach ($f in $order) {
            if ($std -contains $f) { continue }
            $it = $latest[$f]
            if ($it.S -ne $sec) { continue }
            [void]$L.Add("| $f | $($it.V) | $($it.R) | $($it.T) |")
        }
        [void]$L.Add("")
    }

    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 2. Inferred Notes")
    [void]$L.Add("")
    [void]$L.Add('> 仅允许记录 `references/02-information-model.md` 白名单内的 inferred。')
    [void]$L.Add("")
    [void]$L.Add("| 编号 | 推断内容 | Basis | 来源 Round |")
    [void]$L.Add("|------|----------|-------|-----------|")
    $infIdx = 0
    foreach ($r in $Rounds) {
        foreach ($i in @($r.inferred)) {
            $infIdx++
            $ic = Get-Cell $i 'c'
            $ib = Get-Cell $i 'b'
            $ir = "R" + (Get-Cell $i 'round' $r.round)
            [void]$L.Add("| IN$infIdx | $ic | $ib | $ir |")
        }
    }
    if ($infIdx -eq 0) { [void]$L.Add("| | | | |") }
    [void]$L.Add("")

    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 3. Critical Missing Items")
    [void]$L.Add("")
    [void]$L.Add("> 这里只保留仍会阻塞进入 Needs Analysis 的关键缺口。")
    [void]$L.Add("")
    [void]$L.Add("| 优先级 | 项目 | 原因 |")
    [void]$L.Add("|--------|------|------|")
    $blk = @($lastRound.blocking)
    if ($blk.Count -eq 0) {
        [void]$L.Add("| | （无）| Hard Required 已全部满足 |")
    } else {
        foreach ($b in $blk) { [void]$L.Add("| P0 | $b | Hard Required 未满足 |") }
    }
    [void]$L.Add("")

    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 4. Completion Status")
    [void]$L.Add("")
    [void]$L.Add("| 检查项 | 当前状态 | 说明 |")
    [void]$L.Add("|--------|----------|------|")
    $hDesc = @{ "H1"="年龄"; "H2"="城市"; "H3"="职业"; "H4"="家庭责任"; "H5"="收入"; "H6"="支出" }
    foreach ($h in @("H1","H2","H3","H4","H5","H6")) {
        $st = "❓"
        if ($lastRound.h_status -and $lastRound.h_status.PSObject.Properties[$h]) {
            $st = [string]$lastRound.h_status.$h
        }
        $note = "未满足"
        if ($st -match '满足|是|已') { $note = "已收集" }
        $hd = $hDesc[$h]
        [void]$L.Add("| $h $hd | $st | $note |")
    }
    $canEnter = "否"
    $canNote  = "仍有 $($blk.Count) 项 Hard Required 未满足"
    if ([bool]$lastRound.intake_complete) {
        $canEnter = "是"
        $canNote  = "H1-H6 已满足，可进入 Needs Analysis"
    }
    [void]$L.Add("| 是否可进入 Needs Analysis | $canEnter | $canNote |")
    [void]$L.Add("")

    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 5. Follow-up Items")
    [void]$L.Add("")
    [void]$L.Add("> Intake 完成后仍待补的内容写这里。")
    [void]$L.Add("")
    $fu = @($lastRound.followup)
    if ($fu.Count -eq 0) { [void]$L.Add("- [空]") } else { foreach ($x in $fu) { [void]$L.Add("- $x") } }
    [void]$L.Add("")

    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 6. Handoff Notes")
    [void]$L.Add("")
    [void]$L.Add('```')
    $caseIdTxt = Get-Cell $Spec 'case_id'
    $handoff = "由 apply-execution.ps1 依据 evals/executions/" + $caseIdTxt + ".json 渲染"
    [void]$L.Add($handoff)
    [void]$L.Add('```')
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 7. Profile Change Notes")
    [void]$L.Add("")
    foreach ($r in $Rounds) {
        $fl = Join-Or-None -Items $r.confirmed -Prop 'f'
        $rn = [string]$r.round
        [void]$L.Add("- Round $rn：$fl")
    }
    [void]$L.Add("")
    return ,$L
}

function Render-Log {
    param($Spec, $Rounds)

    # QID 累积：后出现的状态覆盖先前的
    $qids = [ordered]@{}
    foreach ($r in $Rounds) {
        foreach ($q in @($r.qids)) {
            $id = Get-Cell $q 'id'
            if ($id -eq "") { continue }
            $qids[$id] = $q
        }
    }

    $L = New-Object System.Collections.ArrayList
    [void]$L.Add("# Conversation Log")
    [void]$L.Add("")
    [void]$L.Add("> 角色：保存历史问答、QID 注册表、逐轮原文")
    [void]$L.Add("> 不作为长期事实源")
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 1. Asked Questions Registry")
    [void]$L.Add("")
    [void]$L.Add("| QID | Priority | Question Intent | 问题原文 | 首次出现 Round | 当前状态 | 客户回答原文 | Related Pending ID | 最后操作 Round |")
    [void]$L.Add("|-----|----------|-----------------|----------|----------------|----------|--------------|--------------------|---------------|")
    if ($qids.Count -eq 0) {
        [void]$L.Add("| | | | | | | | | |")
    } else {
        foreach ($k in $qids.Keys) {
            $q = $qids[$k]
            $cId  = Get-Cell $q 'id'
            $cP   = Get-Cell $q 'p'
            $cInt = Get-Cell $q 'intent'
            $cQ   = Get-Cell $q 'q'
            $cF   = "R" + (Get-Cell $q 'first')
            $cSt  = Get-Cell $q 'status'
            $cAns = Get-Cell $q 'answer'
            $cPid = Get-Cell $q 'pid'
            $cLst = "R" + (Get-Cell $q 'last')
            [void]$L.Add("| $cId | $cP | $cInt | $cQ | $cF | $cSt | $cAns | $cPid | $cLst |")
        }
    }
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## 2. Round History")
    [void]$L.Add("")

    foreach ($r in $Rounds) {
        $rn = [string]$r.round
        [void]$L.Add("### Round $rn")
        [void]$L.Add("")
        [void]$L.Add("- 客户原文：")
        [void]$L.Add("")
        [void]$L.Add('```text')
        foreach ($ln in ([string]$r.customer_text -split "`n")) { [void]$L.Add($ln.TrimEnd()) }
        [void]$L.Add('```')
        [void]$L.Add("")
        $nf = Join-Or-None -Items $r.confirmed -Prop 'f'
        $ni = Join-Or-None -Items $r.inferred  -Prop 'c'
        $np = Join-Or-None -Items $r.pending   -Prop 'item'
        $nq = Join-Or-None -Items $r.next_questions -Prop 'id'
        [void]$L.Add("- 本轮新增 confirmed：$nf")
        [void]$L.Add("- 本轮新增 inferred：$ni")
        [void]$L.Add("- 本轮新增 pending：$np")
        [void]$L.Add("- 本轮新增 QID：$nq")
        $icTxt = [string]$r.intake_complete
        [void]$L.Add("- Completion Check：intake_complete = $icTxt")
        [void]$L.Add("")
        [void]$L.Add("---")
        [void]$L.Add("")
    }

    [void]$L.Add("## 3. Conflict Notes")
    [void]$L.Add("")
    [void]$L.Add("> 客户前后说法出现冲突时，写在这里，方便后续核对。")
    [void]$L.Add("")
    $conf = @()
    foreach ($r in $Rounds) { foreach ($x in @($r.conflicts)) { $conf += $x } }
    if ($conf.Count -eq 0) { [void]$L.Add("- [空]") } else { foreach ($x in $conf) { [void]$L.Add("- $x") } }
    [void]$L.Add("")
    return ,$L
}

function Render-Pending {
    param($Spec, $Rounds)

    # Pending 累积：同 id 后者覆盖
    $ps = [ordered]@{}
    foreach ($r in $Rounds) {
        foreach ($p in @($r.pending)) {
            $id = Get-Cell $p 'id'
            if ($id -eq "") { continue }
            $ps[$id] = $p
        }
    }

    $L = New-Object System.Collections.ArrayList
    [void]$L.Add("# Pending Items")
    [void]$L.Add("")
    [void]$L.Add("> 角色：保存客户答应补充但尚未提供的资料")
    [void]$L.Add("> 不存客户长期事实")
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    # 小节名与列顺序严格对齐 resources/templates/PENDING.md（check-state-invariants 的 I4 依赖此结构）
    [void]$L.Add("## Pending Registry")
    [void]$L.Add("")
    [void]$L.Add("| 编号 | Related QID | 项目 | 客户承诺原文 | 进入 Pending Round | 当前状态 | 已提醒次数 | 下次提醒 Round | 备注 |")
    [void]$L.Add("|------|-------------|------|--------------|-------------------|----------|------------|----------------|------|")
    if ($ps.Count -eq 0) {
        [void]$L.Add("| | | | | | | | | |")
    } else {
        foreach ($k in $ps.Keys) {
            $p = $ps[$k]
            $cId   = Get-Cell $p 'id'
            $cQid  = Get-Cell $p 'qid'
            $cItem = Get-Cell $p 'item'
            $cPm   = Get-Cell $p 'pm'
            $cR    = "R" + (Get-Cell $p 'round')
            $cSt   = Get-Cell $p 'status' 'pending'
            $cCnt  = Get-Cell $p 'reminded' '0'
            $cNext = Get-Cell $p 'next'
            $cMemo = Get-Cell $p 'memo'
            [void]$L.Add("| $cId | $cQid | $cItem | $cPm | $cR | $cSt | $cCnt | $cNext | $cMemo |")
        }
    }
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## Reminder Notes")
    [void]$L.Add("")
    [void]$L.Add("- 第 1 次提醒：进入 Pending 后第 2 个后续 Round")
    [void]$L.Add("- 第 2 次提醒：进入 Pending 后第 4 个后续 Round")
    [void]$L.Add("- 第 3 次提醒：进入 Pending 后第 6 个后续 Round")
    [void]$L.Add("")
    [void]$L.Add("---")
    [void]$L.Add("")
    [void]$L.Add("## History")
    [void]$L.Add("")
    $any = $false
    foreach ($r in $Rounds) {
        foreach ($p in @($r.pending)) {
            $any = $true
            $cId   = Get-Cell $p 'id'
            $cItem = Get-Cell $p 'item'
            $cSt   = Get-Cell $p 'status' 'pending'
            $cR    = "R" + (Get-Cell $p 'round')
            [void]$L.Add("- ${cR}：$cId 新增（$cItem），状态 $cSt")
        }
    }
    if (-not $any) { [void]$L.Add("- [空]") }
    [void]$L.Add("")
    return ,$L
}

# ---------- 主流程 ----------
$files = @()
if ($CaseId -ne "") { $files += (Get-Item (Join-Path $ExecDir "$CaseId.json")) }
else { $files += @(Get-ChildItem $ExecDir -Filter '*.json' | Sort-Object Name) }

$report = @()
foreach ($f in $files) {
    $spec = (Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8) | ConvertFrom-Json
    $cid   = Get-Cell $spec 'case_id' $f.BaseName
    $cdir  = Get-Cell $spec 'client_dir' ($cid + "-Regression")
    $target = Join-Path $ClientRoot $cdir

    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $snapDir = Join-Path $target "snapshots"
    New-Item -ItemType Directory -Path $snapDir -Force | Out-Null

    $rounds = @($spec.rounds)

    # 1) 三份状态文件
    $pLines = Render-Profile -Spec $spec -Rounds $rounds
    $lLines = Render-Log     -Spec $spec -Rounds $rounds
    $dLines = Render-Pending -Spec $spec -Rounds $rounds
    [System.IO.File]::WriteAllLines((Join-Path $target "CLIENT_PROFILE.md"),  $pLines, $enc)
    [System.IO.File]::WriteAllLines((Join-Path $target "CONVERSATION_LOG.md"), $lLines, $enc)
    [System.IO.File]::WriteAllLines((Join-Path $target "PENDING.md"),          $dLines, $enc)

    # 2) per-round 快照（供 run-eval 机检时序断言）
    $confAll = [ordered]@{}
    $pendAll = [ordered]@{}
    $qidAll  = [ordered]@{}
    foreach ($r in $rounds) {
        foreach ($c in @($r.confirmed)) {
            $fk = Get-Cell $c 'f'
            if ($fk -eq "") { continue }
            $confAll[$fk] = [ordered]@{
                key          = Get-Cell $c 'k'
                field        = $fk
                section      = Get-Cell $c 's' '1.1'
                value        = Get-Cell $c 'v'
                source_round = ("R" + (Get-Cell $c 'round' $r.round))
                source_text  = Get-Cell $c 't'
            }
        }

        # 累积到本轮为止的 pending（用于判定"本轮 PENDING 是否为空"这类时序断言）
        # 注意：reminded / next / pm 必须一并落盘，否则 reminder_count、next_reminder_round
        # 这类断言只能拿最终态判定，中间轮会误判（CASE_007 Branch C 依赖此点）。
        foreach ($pd in @($r.pending)) {
            $pid2 = Get-Cell $pd 'id'
            if ($pid2 -eq "") { continue }
            $pendAll[$pid2] = [ordered]@{
                id       = $pid2
                item     = Get-Cell $pd 'item'
                qid      = Get-Cell $pd 'qid'
                status   = Get-Cell $pd 'status' 'pending'
                round    = Get-Cell $pd 'round' $r.round
                reminded = Get-Cell $pd 'reminded' '0'
                next     = Get-Cell $pd 'next'
                pm       = Get-Cell $pd 'pm'
            }
        }

        # 累积 QID 状态（供 run-eval 机检"旧 QID 是否已转出 unanswered"）
        foreach ($q in @($r.qids)) {
            $qid = Get-Cell $q 'id'
            if ($qid -eq "") { continue }
            $qidAll[$qid] = [ordered]@{
                id       = $qid
                intent   = Get-Cell $q 'intent'
                question = Get-Cell $q 'q'
                status   = Get-Cell $q 'status' 'unanswered'
                first    = Get-Cell $q 'first' $r.round
                last     = Get-Cell $q 'last' $r.round
                pid      = Get-Cell $q 'pid'
            }
        }

        $snap = [ordered]@{
            round              = [int]$r.round
            case_id            = $cid
            source_of_truth    = [ordered]@{
                client_profile   = Join-Path $target "CLIENT_PROFILE.md"
                conversation_log = Join-Path $target "CONVERSATION_LOG.md"
                pending          = Join-Path $target "PENDING.md"
            }
            this_round_updates = [ordered]@{
                confirmed = @(@($r.confirmed) | ForEach-Object {
                    [ordered]@{ key = (Get-Cell $_ 'k'); field = (Get-Cell $_ 'f'); value = (Get-Cell $_ 'v'); source_round = ("R" + (Get-Cell $_ 'round' $r.round)); source_text = (Get-Cell $_ 't') }
                })
                inferred  = @(@($r.inferred) | ForEach-Object { [ordered]@{ content = (Get-Cell $_ 'c'); basis = (Get-Cell $_ 'b') } })
                missing   = @($r.blocking)
                pending   = @(@($r.pending) | ForEach-Object { [ordered]@{ id = (Get-Cell $_ 'id'); item = (Get-Cell $_ 'item') } })
            }
            confirmed          = @($confAll.Values)
            pending_items      = @($pendAll.Values)
            qids               = @($qidAll.Values)
            completion_check   = [ordered]@{
                intake_complete = [bool]$r.intake_complete
                blocking_items  = @($r.blocking)
                follow_up_items = @($r.followup)
            }
            next_questions     = @(@($r.next_questions) | ForEach-Object {
                [ordered]@{ id = (Get-Cell $_ 'id'); priority = (Get-Cell $_ 'p'); intent = (Get-Cell $_ 'intent'); question = (Get-Cell $_ 'q'); reason = (Get-Cell $_ 'reason') }
            })
            state_write_result = [ordered]@{ profile_updated = $true; conversation_log_updated = $true; pending_updated = $true }
            notes              = Get-Cell $r 'notes' ""
        }
        $snapPath = Join-Path $snapDir ("round-R" + $r.round + ".json")
        [System.IO.File]::WriteAllText($snapPath, ($snap | ConvertTo-Json -Depth 8), $enc)
    }

    $report += ("{0}: rounds={1} -> {2}" -f $cid, $rounds.Count, $target)

    if ($Validate) {
        $inv = & (Join-Path $PSScriptRoot "check-state-invariants.ps1") -ClientDir $target 2>&1 | Out-String
        $m = [regex]::Match($inv, 'PASS\s*=\s*(\d+)\s+FAIL\s*=\s*(\d+)')
        if ($m.Success) { $report += ("    invariants: PASS={0} FAIL={1}" -f $m.Groups[1].Value, $m.Groups[2].Value) }
    }
}

Write-Output "=== apply-execution 完成 ==="
foreach ($x in $report) { Write-Output $x }
