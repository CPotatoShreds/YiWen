export interface AdminUser {
  id: number;
  username: string;
  exp: number;
  rank_points: number;
  reveal_on_miss: boolean;
  is_admin: boolean;
  last_login_date: string | null;
  last_battle_date: string | null;
  created_at: string;
  loadout_count: number;
  ability_count: number;
  battle_count: number;
}

export interface Ability {
  id: string;
  name: string;
  effect: string;
  detail: string;
  tactic: string;
  understanding: string;
}

export interface RecentBattle {
  id: number;
  user_a: string | null;
  user_b: string | null;
  winner: string | null;
  status: string;
  friendly: boolean;
  created_at: string;
}

export interface Stats {
  total_users: number;
  total_abilities: number;
  total_loadouts: number;
  total_battles: number;
  battles_pending: number;
  battles_done: number;
  battles_failed: number;
  recent_battles: RecentBattle[];
}

export interface DailyPoint { date: string; count: number }
export interface EndpointStat { path: string; count: number; avg_ms: number }
export interface RequestLog {
  id: number;
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  user_id: number | null;
  created_at: string;
}
export interface Traffic {
  total_requests: number;
  last_24h: number;
  avg_ms: number;
  daily: DailyPoint[];
  endpoints: EndpointStat[];
  recent: RequestLog[];
}

export interface AdminBattle {
  id: number;
  user_a: string | null;
  user_b: string | null;
  winner: string | null;
  status: string;
  friendly: boolean;
  story: Record<string, unknown> | null;
  rank_delta_a: number;
  rank_delta_b: number;
  loadout_a_id: number | null;
  loadout_b_id: number | null;
  guess_by: string | null;
  guess_state: string;
  guess_hit: boolean | null;
  guess_score: number | null;
  revealed: boolean;
  share_token: string | null;
  share_token_b: string | null;
  created_at: string;
}

export interface AdminLoadout {
  id: number;
  user_id: number;
  username: string | null;
  name: string;
  style: string;
  enabled: boolean;
  tactic: string;
  ability_count: number;
  created_at: string;
}

export interface Friendship {
  user_id: number;
  friend_id: number;
  user: string | null;
  friend: string | null;
  status: string;
  created_at: string;
}
