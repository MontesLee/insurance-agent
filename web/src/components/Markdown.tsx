import type { ReactNode } from "react";

/**
 * Minimal, safe markdown renderer for the runtime's own report output.
 * Produces React nodes directly — never dangerouslySetInnerHTML.
 * Supports the subset the report engine emits: #/##/###/#### headings,
 * - lists, > blockquotes, | tables |, **bold**, _italic_, `code`.
 */
export function Markdown({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  return <div className="space-y-3 text-[13.5px] leading-relaxed text-slate-800">{blocks}</div>;
}

function parseBlocks(src: string): ReactNode[] {
  const lines = src.split(/\r?\n/);
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;
  const k = () => `b${key++}`;

  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (!line.trim()) {
      i++;
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      out.push(renderHeading(h[1]!.length, h[2]!, k()));
      i++;
      continue;
    }
    if (line.startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && (lines[i] ?? "").startsWith(">")) {
        quote.push((lines[i] ?? "").replace(/^>\s?/, ""));
        i++;
      }
      out.push(
        <blockquote key={k()} className="border-l-2 border-slate-300 bg-slate-50 px-3 py-2 text-[12.5px] text-slate-600">
          {inline(quote.join(" "))}
        </blockquote>,
      );
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && (lines[i] ?? "").startsWith("|")) {
        rows.push(splitRow(lines[i] ?? ""));
        i++;
      }
      const real = rows.filter((r) => !r.every((c) => /^[-\s:]*$/.test(c)));
      const [header, ...body] = real;
      out.push(
        <div key={k()} className="overflow-x-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr>
                {(header ?? []).map((c, ci) => (
                  <th key={ci} className="border border-slate-200 bg-slate-50 px-2 py-1 text-left font-semibold text-slate-600">
                    {inline(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, ci) => (
                    <td key={ci} className="border border-slate-200 px-2 py-1 align-top">
                      {inline(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i] ?? "")) {
        items.push((lines[i] ?? "").replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      out.push(
        <ul key={k()} className="list-disc space-y-1 pl-5">
          {items.map((it, ii) => (
            <li key={ii}>{inline(it)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? "").trim() &&
      !/^(#{1,4})\s/.test(lines[i] ?? "") &&
      !(lines[i] ?? "").startsWith(">") &&
      !(lines[i] ?? "").startsWith("|") &&
      !/^\s*[-*]\s+/.test(lines[i] ?? "")
    ) {
      para.push(lines[i] ?? "");
      i++;
    }
    out.push(<p key={k()}>{inline(para.join(" "))}</p>);
  }
  return out;
}

function renderHeading(level: number, text: string, key: string): ReactNode {
  const cls = ["text-xl font-bold", "text-base font-bold", "text-sm font-semibold", "text-[13px] font-semibold"][
    level - 1
  ] ?? "text-sm font-semibold";
  const Tag = (`h${Math.min(level, 4)}`) as "h1" | "h2" | "h3" | "h4";
  return <Tag key={key} className={`${cls} mt-4 text-slate-900 first:mt-0`}>{inline(text)}</Tag>;
}

function splitRow(line: string): string[] {
  return line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

/** Inline formatting: **bold**, _italic_, `code` — via split, not HTML. */
function inline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      parts.push(<strong key={key++} className="font-semibold text-slate-900">{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith("`")) {
      parts.push(<code key={key++} className="rounded bg-slate-100 px-1 font-mono text-[11.5px] text-slate-700">{tok.slice(1, -1)}</code>);
    } else {
      parts.push(<em key={key++} className="text-slate-500">{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
