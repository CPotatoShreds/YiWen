export interface Ability {
  id: string;
  name: string;
  effect: string;
  detail?: string;
  understanding?: string;
}

// 奇术因果槽位（时序三相因果守恒律的 JSON 解析，见 services/ability_understanding.py）
export interface UnderstandingPhase {
  present: boolean;
  text: string;
}

export interface Understanding {
  verdict: { zero_phase: boolean; source_phases: string[]; summary: string };
  pre: UnderstandingPhase;
  mid: UnderstandingPhase;
  post: UnderstandingPhase;
}

function _normPhase(p: unknown): UnderstandingPhase {
  const o = (p && typeof p === "object" ? p : {}) as Record<string, unknown>;
  return {
    present: !!o.present,
    text: typeof o.text === "string" ? o.text : "",
  };
}

// 安全解析槽位 JSON：非法/缺失返回 null（渲染方据此显示「解析中/待生成」）
export function parseUnderstanding(json: string | undefined | null): Understanding | null {
  if (!json) return null;
  try {
    const u = JSON.parse(json) as Record<string, unknown>;
    if (!u || typeof u !== "object" || !u.verdict) return null;
    const v = u.verdict as Record<string, unknown>;
    return {
      verdict: {
        zero_phase: !!v.zero_phase,
        source_phases: Array.isArray(v.source_phases) ? v.source_phases.filter((s) => typeof s === "string") : [],
        summary: typeof v.summary === "string" ? v.summary : "",
      },
      pre: _normPhase(u.pre),
      mid: _normPhase(u.mid),
      post: _normPhase(u.post),
    };
  } catch {
    return null;
  }
}

export interface Loadout {
  id: number;
  name: string;
  style: string;
  enabled: boolean;
  tactic: string;
  abilities: Ability[];
}

// 一条原子判定：对用户猜测中一个原子片段的四态点评（服务端已剥离内部 reason）
export interface GuessCommentaryItem {
  text: string; // 被单独判定的原子片段（忠实引用用户原文）
  verdict: string; // 四态之一：是 / 否 / 半对 / 不能确定
}

// 一个点评回合对单门的原子判定组（index = 卡序号+1；旧版整轮点评 index=0）
export interface GuessCommentaryGroup {
  index: number;
  items: GuessCommentaryItem[];
}

export interface GuessCard {
  index: number;
  cracked: boolean;
  name?: string;
  effect?: string;
}

// 单个猜词者视角的猜词面板（和局双方各一，my_guess/opp_guess）
export interface GuessBlock {
  total: number;
  cards?: GuessCard[] | null;
  history: string[];
  comments: GuessCommentaryGroup[][]; // 与 history 平行：每轮点评 = 逐门原子判定组列表
  attempts_used: number;
  attempts_max: number;
  verified_round?: number | null; // 最近一次检定时的点评数
  can_verify: boolean; // 自上次检定后又有新点评，可发起检定
  done: boolean;
  flipped: boolean;
}

// 奇人榜条目（冻结刻印）：奇术保密，仅展示数量
export interface BoardEntry {
  id: number;
  user: string;
  name: string;
  style: string;
  ability_count: number;
  challenge_count: number;
  win_rate: number | null; // 刻印胜率（被挑战场次中刻印胜场占比；无挑战 → null）
  avg_crack_attempts: number | null; // 平均每门看破花费的猜测次数（无看破 → null）
  mine: boolean;
  cracked: boolean; // 当前查看者是否已看破该刻印全部奇术
  created_at: string;
}

// 榜主追踪：某刻印的挑战者摘要
export interface BoardChallenger {
  user_id: number;
  username: string;
  total_guesses: number; // 累计猜词次数
  cracked: number; // 已看破门数
  total: number; // 该刻印门数（供「已看破 X/Z」）
}

// 榜主追踪：挑战者对某刻印的单条猜词记录
export interface GuessPathRecord {
  battle_id: number; // 对应战报（榜主己方视角打开）
  round: number; // 本场内第几次猜测（1 起）
  text: string; // 提交的猜测原文
  commentary: string; // 该次猜测得到的点评文本
  cracked_after: number; // 截至目前已看破门数
  at: string; // 发生时间（ISO）
}

// 刻印单门奇术的进度卡：已看破亮出真实名/效果，未看破仅标记
export interface BoardAbility {
  index: number;
  cracked: boolean;
  name?: string | null;
  effect?: string | null;
}

// 条目详情：查看者（挑战者）视角的看破进度 + 与该刻印的对战记录
export interface BoardDetail extends BoardEntry {
  progress: BoardAbility[];
  battles: Battle[];
}

export interface BattleStory {
  narration?: string;
  narration_a?: string;
  narration_b?: string;
  abilities_a?: Ability[];
  abilities_b?: Ability[];
}

export interface Battle {
  id: number;
  created_at: string;
  user_a: string;
  user_b: string;
  fighter_a: string;
  fighter_b: string;
  status: string;
  winner: string | null;
  winner_fighter?: string | null;
  rank_delta_a: number;
  rank_delta_b: number;
  share_token: string;
  share_token_b?: string;
  story: BattleStory | null;
  board_entry_id?: number | null;
  unlocked?: boolean;
  can_guess: boolean;
  guessed: boolean;
  guess_hit: boolean | null;
  guess_score?: number;
  guess_by?: string | null;
  guess_history: string[];
  guess_comments: GuessCommentaryGroup[][]; // 与 guess_history 平行：每轮点评 = 逐门原子判定组列表
  guess_text: string;
  guess_total: number;
  guess_cards?: GuessCard[] | null;
  guess_attempts_used: number;
  guess_attempts_max: number;
  can_verify: boolean; // 自上次检定后又有新点评，可发起检定
  revealed: boolean;
  friendly: boolean;
  my_guess?: GuessBlock | null;
  opp_guess?: GuessBlock | null;
}

export const LOADOUT_NUMBERS = ["壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖", "拾"];

export function loadoutLabel(loadout: Loadout, index: number): string {
  return loadout.name || `奇人·${LOADOUT_NUMBERS[index] ?? index + 1}`;
}

// 站内通知（铃铛）：type 决定跳转语义
export interface NotificationItem {
  id: number;
  type: string; // board_challenge / battle_report / guess_progress
  title: string;
  body: string;
  ref_type: string | null; // battle / board
  ref_id: number | null;
  read: boolean;
  created_at: string;
}

export interface NotificationList {
  items: NotificationItem[];
  unread: number;
}

// 自配 LLM 方案：api_key 明文永不回传，只给 has_api_key
export interface LlmProfile {
  id: number;
  label: string;
  provider: string;
  base_url: string;
  model: string;
  has_api_key: boolean;
  is_active: boolean;
  created_at: string;
}
