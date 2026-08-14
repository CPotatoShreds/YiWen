export interface Ability {
  id: string;
  name: string;
  effect: string;
  detail?: string;
  tactic?: string;
  understanding?: string;
}

export interface Loadout {
  id: number;
  name: string;
  style: string;
  enabled: boolean;
  tactic: string;
  abilities: Ability[];
}

export interface GuessCard {
  index: number;
  matched: string[];
  progress: number;
  cracked: boolean;
  name?: string;
  effect?: string;
}

// 单个猜词者视角的猜词面板（和局双方各一，my_guess/opp_guess）
export interface GuessBlock {
  total: number;
  cards?: GuessCard[] | null;
  history: string[];
  attempts_used: number;
  attempts_max: number;
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
  mine: boolean;
  created_at: string;
}

// 刻印单门奇术的进度卡：已看破亮出真实名/效果，未看破仅线索片段
export interface BoardAbility {
  index: number;
  cracked: boolean;
  matched: string[];
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
  guess_text: string;
  guess_total: number;
  guess_cards?: GuessCard[] | null;
  guess_attempts_used: number;
  guess_attempts_max: number;
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
