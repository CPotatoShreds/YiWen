// LLM 链路适配视图：把各环节 trace 的 request/response 解析成"环节定制"的展示数据。
// 纯函数，无 React；渲染组件在 TraceViews.tsx。

import type { LlmTrace, LlmTraceDetail } from "./types";

function norm(s: string): string {
  return s.replace(/\s+/g, "").replace(/[，。；：、,.;：]/g, "");
}

/** 消息数组里的 system 提示词原文（battle 环节的 dict 形态无提示词）。 */
export function systemContent(d: LlmTraceDetail): string {
  const req = d.request_json as unknown;
  if (!Array.isArray(req)) return "";
  for (const m of req) {
    if (m && m["type"] === "system" && typeof m["content"] === "string") return m["content"];
  }
  return "";
}

/** 消息数组里的最后一条 human 消息（配对/检定环节为单条消息：整段提示词即该消息）。 */
export function humanContent(d: LlmTraceDetail): string {
  const req = d.request_json as unknown;
  if (!Array.isArray(req)) return "";
  for (let i = req.length - 1; i >= 0; i--) {
    const m = req[i] as Record<string, unknown> | null;
    if (m && m["type"] === "human" && typeof m["content"] === "string") return m["content"];
  }
  return "";
}

/** 单条消息形态（配对/检定）取整段提示词；dict 形态（battle 环节）取 system。 */
export function promptText(d: LlmTraceDetail): string {
  const req = d.request_json as unknown;
  if (!Array.isArray(req)) return "";
  const sys = req.find((m) => m && m["type"] === "system" && typeof m["content"] === "string");
  if (sys && typeof sys["content"] === "string") return sys["content"];
  for (let i = req.length - 1; i >= 0; i--) {
    const m = req[i] as Record<string, unknown> | null;
    if (m && m["type"] === "human" && typeof m["content"] === "string") return m["content"];
  }
  return "";
}

/** dict 形态 request 的变量提取（battle 环节用），可传多个 key 依次尝试。 */
export function extractVar(d: LlmTraceDetail, ...keys: string[]): string {
  const req = d.request_json as Record<string, unknown> | null;
  if (!req || Array.isArray(req)) return "";
  for (const k of keys) {
    const v = req[k];
    if (typeof v === "string") return v;
  }
  return "";
}

// ---------- 分类 ----------
export const CAT_DEDUCE = "deduce";
export const CAT_TRANSCRIBE = "transcribe";
export const CAT_VALIDATE = "validate";
export const CAT_REPAIR = "repair";
export const CAT_USAGE = "usage";
export const CAT_GUESS_SPLIT = "guess_split";
export const CAT_GUESS_PAIR = "guess_pair";
export const CAT_GUESS_VERIFY = "guess_verify";
export const CAT_RAW = "raw";

export function categorize(op: string): string {
  switch (op) {
    case "deduce": return CAT_DEDUCE;
    case "transcribe": return CAT_TRANSCRIBE;
    case "validate": return CAT_VALIDATE;
    case "repair": return CAT_REPAIR;
    case "usage": return CAT_USAGE;
    case "guess_split": return CAT_GUESS_SPLIT;
    case "guess_pair": return CAT_GUESS_PAIR;
    case "guess_verify": return CAT_GUESS_VERIFY;
    default: return CAT_RAW;
  }
}

export const CAT_LABEL: Record<string, string> = {
  [CAT_DEDUCE]: "写意开局（上帝视角生成）",
  [CAT_TRANSCRIBE]: "转写（双视角讲述）",
  [CAT_VALIDATE]: "校验",
  [CAT_REPAIR]: "修复",
  [CAT_USAGE]: "奇术使用判定",
  [CAT_GUESS_SPLIT]: "猜词 · 环节一（拆分）",
  [CAT_GUESS_PAIR]: "猜词 · 环节二（配对）",
  [CAT_GUESS_VERIFY]: "猜词 · 环节三（检定）",
  [CAT_RAW]: "原始链路",
};

// ---------- 环节一：拆分 ----------
/** 败方本轮道出的原始猜测文本（从提示词变量提取）。 */
export function splitInput(d: LlmTraceDetail): string {
  const sys = systemContent(d);
  return sys.match(/败方本轮道出的猜测文本：\s*\n?([^\n]+)/)?.[1]?.trim() ?? "";
}

/** 环节一输出：拆分出的原子叙述条目。 */
export function splitItems(d: LlmTraceDetail): string[] {
  const resp = (d.response_json ?? {}) as { items?: { text?: string }[] };
  return (resp.items ?? []).map((it) => it.text ?? "").filter(Boolean);
}

// ---------- 环节二：配对 ----------
export interface PairRow {
  ability: string; // 对家实际使用的奇术（原文）
  cells: { itemText: string; snippet: string }[];
}

export function pairRows(details: LlmTraceDetail[]): { items: string[]; rows: PairRow[] } {
  const items: string[] = [];
  const seenItem = new Set<string>();
  const rows: PairRow[] = [];
  const rowByAbility = new Map<string, PairRow>();

  for (const d of details) {
    if (d.operation !== "guess_pair") continue;
    const sys = promptText(d);
    const itemText = sys.match(/用户的猜测：\s*\n?([^\n]+)/)?.[1]?.trim() || "";
    const ability = sys.match(/人物实际使用的能力：\s*\n?([^\n]+)/)?.[1]?.trim() || "";
    if (!itemText || !ability) continue;
    if (!seenItem.has(norm(itemText))) {
      seenItem.add(norm(itemText));
      items.push(itemText);
    }
    let row = rowByAbility.get(ability);
    if (!row) {
      row = { ability, cells: [] };
      rowByAbility.set(ability, row);
      rows.push(row);
    }
    const resp = (d.response_json ?? {}) as Record<string, unknown>;
    row.cells.push({ itemText, snippet: String(resp.snippet ?? "") });
  }
  return { items, rows };
}

// ---------- 环节三：检定 ----------
export interface VerifyInfo {
  ability: string;
  matched: string[];
  guessed: boolean;
  reason: string;
}

export function verifyInfo(d: LlmTraceDetail): VerifyInfo {
  const sys = promptText(d);
  const ability = sys.match(/人物实际使用的能力：\s*\n?([^\n]+)/)?.[1]?.trim() || "";
  const matched = [...(sys.match(/用户已积累的全部线索：\n((?:- .*\n?)*)/)?.[1]?.matchAll(/- (.*)/g) ?? [])].map((m) => m[1]);
  const resp = (d.response_json ?? {}) as Record<string, unknown>;
  return { ability, matched, guessed: Boolean(resp.guessed), reason: String(resp.reason ?? "") };
}

// ---------- 汇总：usage 实际使用奇术编号 ----------
export interface TraceSummary {
  usedAbilityIdx: number[];
  usageFailed: boolean;
}

export function buildSummary(traces: LlmTrace[], detailMap: Record<number, LlmTraceDetail>): TraceSummary {
  const usedAbilityIdx: number[] = [];
  let usageFailed = false;
  let found = false;
  for (const t of traces) {
    if (t.operation !== "usage") continue;
    found = true;
    const d = detailMap[t.id];
    const resp = (d?.response_json ?? {}) as Record<string, unknown>;
    const indices = resp["indices"];
    if (Array.isArray(indices)) {
      for (const x of indices) {
        const n = Number(x);
        if (Number.isFinite(n)) usedAbilityIdx.push(n);
      }
    } else {
      usageFailed = true;
    }
  }
  return { usedAbilityIdx: [...new Set(usedAbilityIdx)], usageFailed: found && usageFailed };
}

/** 提示词 → 简短摘要（用于 battle 环节的"输入"横条）。 */
export function foldPrompt(prompt: string): string {
  const line = (s: string) => s.replace(/\s+/g, " ").trim();
  const has = (re: RegExp) => re.test(prompt);
  const caps: string[] = [];
  if (has(/拆成|拆分|原子猜测条目/)) caps.push("拆成互不相干的原子猜测条目");
  if (has(/价值判定|有价值时给出|严禁.*泄露|禁止.*泄露/)) caps.push("判定价值，禁止泄露真实奇术");
  if (has(/完整猜出|全覆盖|判定规则/)) caps.push("全覆盖才算完整猜出");
  if (has(/实际使用过|装配奇术清单/)) caps.push("判定实际使用过的奇术");
  if (has(/不涉及|只依据文本本身/)) caps.push("只依据文本本身");
  if (has(/不偏向|全知叙述/)) caps.push("全知叙述者");
  return caps.length ? `规则 · ${caps.join(" · ")}` : line(prompt).slice(0, 40) || "（无提示词）";
}
