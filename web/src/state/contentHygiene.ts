/**
 * Consumer content hygiene (28.K.25-S1, frontend delivery defense).
 *
 * The backend sanitizes at the source (LLM context) and at delivery
 * (_finish_run chat message, K.22 validated chunks). This is the final
 * render-time defense for the LIVE agent-loop stream, where an id may
 * be SPLIT across delta chunks (a per-chunk regex could not catch it —
 * sanitizing the ACCUMULATED buffer at render time does).
 *
 * Patterns mirror runtime/consumer_hygiene.py and are deliberately
 * narrow: ART-/EVAL- needs a word boundary + hyphen + suffix (product
 * codes like P001 and prose like SMART-1 are out of scope); run_/chat_/
 * evt_/appr_/agentcase_ need an 8+ tail. Amounts, dates, clause numbers
 * and normal abbreviations are never touched.
 */
const ART_EVAL = /(\(?[（(]\s*)?\b(ART|EVAL)-[0-9A-Za-z]{1,12}\b\.?(\s*[)）])?/gi;
const RUNLIKE = /\b(?:run|chat|evt|appr|agentcase)_[0-9a-zA-Z]{8,}\b/g;

function artSub(open: string | undefined, body: string, close: string | undefined): string {
  if (open || close) return "";
  return body.toUpperCase().startsWith("ART") ? "相关结果" : "校验记录";
}

export function sanitizeConsumerText(text: string): string {
  if (!text) return text;
  let out = text.replace(
    ART_EVAL,
    (...groups: string[]) => artSub(groups[1], groups[2] ?? "", groups[3]),
  );
  out = out.replace(RUNLIKE, "本次处理");
  return out;
}
