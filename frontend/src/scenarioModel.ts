// 小天下集推演的共享模型：阶段、行迹文案、历史条目形状。
// 单主视角制（2026-09-15）：不再有视角切换——书页只呈现"自己"的叙述，推演全文经看破解锁后附加。
export type Stage = "loading" | "compare" | "ready" | "thinking" | "views" | "result";
export type Message = {
  role: string;
  text?: string;
  challenger_text?: string;
  guardian_text?: string;
  omniscient?: string;
  created_at?: string;
};

export const STAGE_TEXT: Record<Stage, string> = {
  loading: "正在接入小天下集",
  compare: "奇术比对中",
  ready: "等待你的指导",
  thinking: "推演中",
  views: "正在转写双方视角",
  result: "本次推演已成卷",
};
export const STAGE_STEPS: Stage[] = ["compare", "ready", "thinking", "views", "result"];

export type ScenarioHistoryItem = {
  id: string;
  status: string;
  challenge_number: number;
  is_preview?: boolean;
  won: boolean | null;
  created_at?: string;
  challenger_character_name?: string;
  challenger_character_id?: string | null;
  strategy?: string;
};

const IN_PROGRESS = new Set(["preparing", "active", "resolving"]);

/** 未终局的回合仍属当前擂台，不归档。 */
export const isInProgress = (status: string) => IN_PROGRESS.has(status);

const DIGITS = "〇一二三四五六七八九";

/** 页码用的中文数字：1–99 转「一 / 十二 / 二十一」，超出范围回落阿拉伯数字。 */
export function chineseNumber(value: number) {
  if (!Number.isInteger(value) || value <= 0 || value >= 100) return String(value);
  if (value < 10) return DIGITS[value];
  const tens = Math.floor(value / 10);
  const ones = value % 10;
  return (tens > 1 ? DIGITS[tens] : "") + "十" + (ones ? DIGITS[ones] : "");
}