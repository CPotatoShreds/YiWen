// LLM 链路适配视图：把各环节 trace 的 request/response 解析成"环节定制"的展示数据。
// 纯函数，无 React；渲染组件在 TraceViews.tsx。

import type { LlmTrace, LlmTraceDetail } from "./types";
import { parseUtc } from "../../time";

/** 行迹状态 → 中文标签。 */
export const statusLabel = (s: string) =>
  s === "pending" ? "推演中" : s === "failed" ? "失手" : "已落成";

export const fmtMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);

/** 后端 naive UTC → 本地（北京）时间，YYYY-MM-DD HH:mm:ss。 */
export const fmtDt = (iso: string) => {
  const d = parseUtc(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

/** 消息数组里的 system 提示词原文（battle 环节的 dict 形态无提示词）。 */
export function systemContent(d: LlmTraceDetail): string {
  const req = d.request_json as unknown;
  if (!Array.isArray(req)) return "";
  for (const m of req) {
    if (m && m["type"] === "system" && typeof m["content"] === "string") return m["content"];
  }
  return "";
}

/** 消息数组里的最后一条 human 消息（点评/检定环节为单条消息：整段提示词即该消息）。 */
export function humanContent(d: LlmTraceDetail): string {
  const req = d.request_json as unknown;
  if (!Array.isArray(req)) return "";
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
export const CAT_DISCUSS = "discuss";
export const CAT_DEDUCE = "deduce";
export const CAT_TRANSCRIBE = "transcribe";
export const CAT_VALIDATE = "validate";
export const CAT_REPAIR = "repair";
export const CAT_USAGE = "usage";
export const CAT_GUESS_COMMENTARY = "guess_commentary";
export const CAT_GUESS_PAIR = "guess_pair";
export const CAT_GUESS_VERIFY = "guess_verify";
export const CAT_RAW = "raw";

export function categorize(op: string): string {
  switch (op) {
    case "discuss": return CAT_DISCUSS;
    case "ability_pair": return CAT_DISCUSS;
    case "deduce": return CAT_DEDUCE;
    case "transcribe": return CAT_TRANSCRIBE;
    case "validate": return CAT_VALIDATE;
    case "repair": return CAT_REPAIR;
    case "usage": return CAT_USAGE;
    case "guess_commentary": return CAT_GUESS_COMMENTARY;
    case "guess_pair": return CAT_GUESS_PAIR;
    case "guess_verify": return CAT_GUESS_VERIFY;
    default: return CAT_RAW;
  }
}

/** 新版战前对比节点返回结构化判定；汇总为讨论页签可读的 Markdown。 */
export function buildPairReport(details: LlmTraceDetail[]): string {
  const rows = details
    .map((d) => d.response_json)
    .filter((v): v is Record<string, unknown> => Boolean(v) && typeof v === "object" && !Array.isArray(v))
    .filter((v) => typeof v.conflict === "boolean");
  if (!rows.length) return "";

  const lines = ["【奇术对比分析】"];
  for (const row of rows) {
    if (typeof row.stronger_ability === "string") {
      const relation = row.conflict ? "冲突" : "无直接冲突";
      const conflictReason = typeof row.conflict_reason === "string" ? row.conflict_reason : "未说明";
      const strongerReason = typeof row.stronger_reason === "string" ? row.stronger_reason : "未说明";
      lines.push(`- ${relation}：${conflictReason}。${row.stronger_ability}占优：${strongerReason}`);
    } else if (typeof row.ability_a === "string" && typeof row.ability_b === "string" && row.conflict) {
      const abilityA = row.ability_a;
      const abilityB = row.ability_b;
      const interaction = typeof row.interaction === "string" && row.interaction ? row.interaction : "矛与盾式碰撞";
      const winnerText: Record<string, string> = { A: "A 侧占优", B: "B 侧占优", none: "不相上下" };
      const winner = winnerText[String(row.winner)] ?? "不相上下";
      const reasoning = typeof row.reasoning === "string" ? row.reasoning : "";
      lines.push(`- ${abilityA} × ${abilityB}：冲突（${interaction}），依三相共鸣理论，${winner}。${reasoning}`);
    } else if (typeof row.ability_a === "string" && typeof row.ability_b === "string") {
      const abilityA = row.ability_a;
      const abilityB = row.ability_b;
      lines.push(`- ${abilityA} × ${abilityB}：无直接冲突。`);
    }
  }
  return lines.join("\n");
}

export const CAT_LABEL: Record<string, string> = {
  [CAT_DISCUSS]: "讨论（战前预演）",
  [CAT_DEDUCE]: "写意开局（上帝视角生成）",
  [CAT_TRANSCRIBE]: "转写（双视角讲述）",
  [CAT_VALIDATE]: "校验",
  [CAT_REPAIR]: "修复",
  [CAT_USAGE]: "奇术使用判定",
  [CAT_GUESS_COMMENTARY]: "猜词 · 点评",
  [CAT_GUESS_PAIR]: "猜词 · 配对（旧链路）",
  [CAT_GUESS_VERIFY]: "猜词 · 检定",
  [CAT_RAW]: "原始链路",
};

// ---------- 点评 ----------
export function commentaryInfo(d: LlmTraceDetail): { text: string; commentary: string } {
  const sys = systemContent(d);
  const text = sys.match(/用户的猜测：\s*\n?([^\n]+)/)?.[1]?.trim() || "";
  const resp = (d.response_json ?? {}) as Record<string, unknown>;
  return { text, commentary: String(resp.commentary ?? "") };
}

// ---------- 检定 ----------
export interface VerifyInfo {
  ability: string;
  cracked: boolean;
  missing: string;
}

export function verifyInfo(d: LlmTraceDetail): VerifyInfo {
  const sys = systemContent(d);
  const ability = sys.match(/人物实际使用的能力：\s*\n?([^\n]+)/)?.[1]?.trim() || "";
  const resp = (d.response_json ?? {}) as Record<string, unknown>;
  return { ability, cracked: Boolean(resp.cracked), missing: String(resp.missing ?? "") };
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
