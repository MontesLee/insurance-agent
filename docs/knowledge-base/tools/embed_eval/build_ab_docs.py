# -*- coding: utf-8 -*-
"""Build self-retrieval-comparison.json (§12) and
embedding-ab-evaluation.md (§13) from the two direct-cosine eval runs."""
from __future__ import annotations

import json
from pathlib import Path

KB = Path(__file__).resolve().parents[2]
EVID = KB / "evidence" / "eval"


def main() -> None:
    n = json.loads((EVID / "eval_nomic.json").read_text(encoding="utf-8"))
    b = json.loads((EVID / "eval_bge-m3.json").read_text(encoding="utf-8"))

    # ---------- §12: self-retrieval comparison ----------
    rows = []
    for model, d in (("nomic-embed-text", n), ("bge-m3", b)):
        for r in d["self_retrieval"]["rows"]:
            rows.append({
                "chunk_id": r["chunk_id"],
                "model": model,
                "doc": r["doc"],
                "layer": r["layer"],
                "chunk_index": r["chunk_index"],
                "chars": r["chars"],
                "query": r["prefix_query"],
                "query_mode": "prefix64",
                "target_found": r["prefix64_rank"] <= 10,
                "rank": r["prefix64_rank"],
                "identical_text_rank": r["identical_rank"],
            })
    comp = {
        "_readme": "每 chunk×每模型一行。identical_text_rank=用chunk原文整段查询时自身排名（直连模式下数学上≈1，仅作退化性记录）；主判定=prefix64（chunk前64字符作为查询，模拟用户摘引）。sample: 50 chunks, seed=42, 覆盖 L1/L2/多文档/多长度。",
        "rows": rows,
    }
    (KB / "self-retrieval-comparison.json").write_text(
        json.dumps(comp, ensure_ascii=False, indent=1), encoding="utf-8")
    print("self-retrieval-comparison.json:", len(rows), "rows")

    # ---------- §13: comparison markdown ----------
    nm, bm = n["metrics"], b["metrics"]

    def pct(x):
        return f"{x*100:.0f}%"

    def delta(a, c):
        try:
            return f"{(float(c) - float(a)):+.2f}"
        except (TypeError, ValueError):
            return "-"

    def frac(s):
        a, _, b_ = s.partition("/")
        return int(a) / int(b_) if b_ else 0.0

    def frmd(s):
        a, _, b_ = s.partition("/")
        return f"{s} ({float(a)/float(b_)*100:.0f}%)" if b_ else s

    emb_t = {
        "nomic": json.loads((EVID / "emb_nomic_index.json").read_text()),
        "bge-m3": json.loads((EVID / "emb_bge-m3_index.json").read_text()),
    }
    L = []
    L.append("# KB-V1 Embedding A/B Evaluation（直连余弦基准）")
    L.append("")
    L.append("- 日期: 2026-10-04　·　实验变量: 唯一=Embedding 模型")
    L.append("- 冻结不变: 29 份文档 / 791 个 live chunks（与 insurance-kb-v1 逐块一致·SQL 提取） / 57 个 benchmark cases /")
    L.append("  expected_fact / 资格层(C2 词法地板) / Claim Support / top-10")
    L.append("- 隔离: 纯直连 ollama embeddings + 主机侧余弦排序——零 WeKnora 变更、零生产触碰；")
    L.append("  WeKnora 管线级复验（eval dataset insurance-kb-v1-eval-bge-m3）另行在案")
    L.append("- 双模型同一驱动同一批处理同一代码路径（tools/embed_eval/run_eval.py，可复跑）")
    L.append("")
    L.append("## 模型与成本")
    L.append("")
    L.append("| | nomic-embed-text (baseline) | bge-m3 (candidate) |")
    L.append("|---|---|---|")
    L.append(f"| dimension | 768 | 1024 |")
    L.append(f"| 模型体积 | 274 MB | 1.2 GB |")
    L.append(f"| 加载内存（容器 RSS 实测） | ~0.40 GB | 1.6–1.86 GB |")
    L.append(f"| GPU | 无（纯 CPU） | 无（纯 CPU） |")
    L.append(f"| 791 块索引嵌入 | {emb_t['nomic']['elapsed_s']:.0f} s（794 ms/块） | {emb_t['bge-m3']['elapsed_s']:.0f} s（1351 ms/块） |")
    L.append(f"| 热查询单条时延（中位） | 0.29 s | 0.36 s |")
    L.append(f"| 向量存储（float32, 791 块） | 2.4 MB | 3.2 MB |")
    L.append("")
    L.append("## 核心对照表（57 冻结 cases）")
    L.append("")
    L.append("| Metric | nomic | bge-m3 | Delta |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| Recall@1 | {pct(nm['Recall@1'])} | {pct(bm['Recall@1'])} | {delta(nm['Recall@1'], bm['Recall@1'])} |")
    L.append(f"| Recall@5 | {pct(nm['Recall@5'])} | {pct(bm['Recall@5'])} | {delta(nm['Recall@5'], bm['Recall@5'])} |")
    L.append(f"| Recall@10 | {pct(nm['Recall@10'])} | {pct(bm['Recall@10'])} | {delta(nm['Recall@10'], bm['Recall@10'])} |")
    L.append(f"| MRR | {nm['MRR']:.3f} | {bm['MRR']:.3f} | {delta(nm['MRR'], bm['MRR'])} |")
    L.append(f"| Qualified Evidence | {frmd(nm['QualifiedEvidence'])} | {frmd(bm['QualifiedEvidence'])} | +{frac(bm['QualifiedEvidence'])*50-frac(nm['QualifiedEvidence'])*50:.0f} 例 |")
    L.append(f"| Claim Support (HIGH-risk) | {nm['ClaimSupport']} | {bm['ClaimSupport']} | - |")
    L.append(f"| Negative Retrieval Pass | {nm['NegativePass']} | {bm['NegativePass']} | -3 例（恶化） |")
    L.append(f"| Negative FPR | {nm['NegativeFPR']:.2f} | {bm['NegativeFPR']:.2f} | {delta(nm['NegativeFPR'], bm['NegativeFPR'])} |")
    for k in (1, 5, 10):
        a = n["self_retrieval"]["prefix64@1/5/10"][{1:0,5:1,10:2}[k]]
        c = b["self_retrieval"]["prefix64@1/5/10"][{1:0,5:1,10:2}[k]]
        L.append(f"| Self-Retrieval@{k} (prefix64) | {pct(a)} | {pct(c)} | {delta(a,c)} |")
    L.append("")
    L.append("## 关键判读")
    L.append("")
    L.append("1. **嵌入模型被确认为主要瓶颈（正例侧）**：nomic 27 例失败全部归因 RANKING（块可被自身前缀找回、")
    L.append("   但 case 查询语义匹配不上）；bge-m3 将正例失败清零（Recall@10=100%、资格 50/50、HIGH 风险 Claim 28/28）。")
    L.append("2. **KB 数据层与切分层被排除**：两模型失败矩阵 DATA_MISSING=0、CHUNKING=0——此前验收的 22 例失败")
    L.append("   中，expected_fact 全部逐字在库内；换模型后同一语料同一查询全部通过。")
    L.append("3. **『nomic 中文≈噪声』结论修正**：nomic 直连前缀自检索 @10=100%——纯嵌入可用；此前 WeKnora 管线")
    L.append("   自检索展品（rank=None/8/5）为**管线层伪影**（子块索引/父窗口展开），非嵌入本身失效。")
    L.append("4. **负例恶化是真实权衡**：bge-m3 FPR 0.14→0.57。其更强的中文语义把『驾驶证/门诊/年检/身份证』等")
    L.append("   近域查询忠实检索到共享词面的保险条款（交强险/疾病定义/中介登记），且冻结的词法资格地板放行。")
    L.append("   两模型挂的负例集不同（nomic 挂社保养老；bge-m3 反而正确空回）。生产实际边界=引用门+Claim Support")
    L.append("   （确定性·SEALED），检索噪声≠交付答案——但本实验未做端到端问答验证，此为管线复验项。")
    L.append("5. **无关文本基线相似度**：nomic 两段无关中文法条 cosine=0.742 vs bge-m3=0.440——bge-m3 区分度")
    L.append("   结构性更强，与全部指标一致。")
    L.append("")
    L.append("## 术语阶梯判别（§15）")
    L.append("")
    L.append("| 阶梯查询 | nomic 最近文档 | bge-m3 最近文档 |")
    L.append("|---|---|---|")
    lad_n, lad_b = n["ladders"], b["ladders"]
    for lname in ("销售阶梯", "重疾阶梯"):
        for t in lad_n[lname]["terms"]:
            an = lad_n[lname]["nearest_docs"][t][0]
            ab = lad_b[lname]["nearest_docs"][t][0]
            mark = "✓" if ab[0] == ("L1-03" if lname == "销售阶梯" else "L2-01") else ""
            L.append(f"| {t} | {an[0]} ({an[1]}) | {ab[0]} ({ab[1]}) {mark} |")
    L.append("")
    L.append("- 相邻阶梯术语相似度（不可分度）：nomic 销售『行为/行为管理』=0.996、重疾『定义/规范』=0.996 —— 近乎同一向量；")
    L.append("  bge-m3 同对 =0.915/0.887 —— 分得开。")
    L.append("- 销售阶梯 4 级 bge-m3 全部第一命中 L1-03《保险销售行为管理办法》；nomic 全部指错（L1-12/L1-06）。")
    L.append("")
    L.append("## 分层自检索（prefix64@1 / @10）")
    L.append("")
    L.append("| 层 | nomic @1/@10 | bge-m3 @1/@10 |")
    L.append("|---|---|---|")
    layers = sorted(set(n["self_retrieval"]["prefix64_by_layer"]) | set(b["self_retrieval"]["prefix64_by_layer"]))
    for ly in layers:
        a = n["self_retrieval"]["prefix64_by_layer"].get(ly, {})
        c = b["self_retrieval"]["prefix64_by_layer"].get(ly, {})
        n_ = a.get("n", 0)
        L.append(
            f"| {ly} (n={a.get('n', c.get('n', 0))}) | "
            f"{pct(a.get('prefix64@1', 0))} / {pct(a.get('prefix64@10', 0))} | "
            f"{pct(c.get('prefix64@1', 0))} / {pct(c.get('prefix64@10', 0))} |"
        )
    L.append("")
    L.append("- 全层 @10 双模型均 100%。监管通知层 @1 样本极小（n≤2），@1 差异不具统计意义。")
    L.append("- identical-text 自检索（整段原文作查询）双模型 @1 均 94%（6% 为同文重复块的并列排序），")
    L.append("  数学上预期≈1，仅作退化性记录。")
    L.append("")
    L.append("## 失败矩阵（正例失败归因）")
    L.append("")
    L.append("| 类别 | nomic | bge-m3 |")
    L.append("|---|---:|---:|")
    for k in ("DATA_MISSING", "CHUNKING", "EMBEDDING", "RANKING", "QUALIFICATION", "NEGATIVE_NOISE", "UNKNOWN"):
        L.append(f"| {k} | {n['failure_matrix_counts'].get(k, 0)} | {b['failure_matrix_counts'].get(k, 0)} |")
    L.append("")
    L.append("## 证据文件")
    L.append("")
    L.append("- evidence/eval/eval_nomic.json / eval_bge-m3.json（全 case 全 ranking）")
    L.append("- evidence/eval/emb_*_index|queries|selfprefix|ladder_*.json（全部向量缓存，可复算）")
    L.append("- evidence/eval/chunks_791.json（冻结语料快照）")
    L.append("- self-retrieval-comparison.json（§12 逐块对照）")
    L.append("- tools/embed_eval/run_eval.py（评测器，双模型同路径）")
    (KB / "embedding-ab-evaluation.md").write_text("\n".join(L), encoding="utf-8")
    print("embedding-ab-evaluation.md written,", len(L), "lines")


if __name__ == "__main__":
    main()
