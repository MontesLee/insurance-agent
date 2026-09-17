/**
 * WELCOME — new-chat screen (§23): honest positioning + demo prompts that FILL
 * the composer (click does not auto-send).
 */
export const DEMO_PROMPTS: { text: string; hint: string }[] = [
  { text: "给孩子配置重疾险前，我应该先考虑什么？", hint: "家庭责任与优先级" },
  { text: "一家三口需要哪些保险？", hint: "整体配置" },
  { text: "我的百万医疗险和重疾险有什么区别？", hint: "单需求·医疗" },
  { text: "帮我看看家庭保障有没有明显缺口", hint: "缺口分析" },
];

export function WelcomeScreen({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto max-w-xl px-6 py-10" data-testid="welcome">
      <p className="text-[15px] font-semibold text-slate-700">
        家庭保障，有时候不是买得越多越好。
      </p>
      <p className="mt-1 text-[13.5px] text-slate-500">
        先把真正要解决的问题弄清楚。
      </p>
      <p className="mt-5 text-[12.5px] text-slate-400">我可以帮你：</p>
      <ul className="mt-2 space-y-2">
        {DEMO_PROMPTS.map((p) => (
          <li key={p.text}>
            <button
              type="button"
              onClick={() => onPick(p.text)}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-[13px] text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
              data-testid="demo-prompt"
            >
              {p.text}
              <span className="ml-2 text-[11px] text-slate-400">{p.hint}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-6 rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-700">
        Portfolio Demo Mode：当前系统以结构化 Client State 为上游输入边界（自然语言直达
        intake 尚未接入主执行路径）。你的问题会映射到对应的演示 case，由真实 Agent
        Runtime 完整执行——需求 → 风险 → 缺口 → 方案 → 推荐 → 报告，全过程可观察。
      </p>
    </div>
  );
}
