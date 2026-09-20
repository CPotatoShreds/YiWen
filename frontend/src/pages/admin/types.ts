export interface AdminUser { id: number; username: string; is_admin: boolean; created_at: string; ability_count: number }
export interface Ability { id: string; name: string; effect: string; detail: string; understanding: string }
export interface Stats { total_users: number; total_abilities: number }
export interface DailyPoint { date: string; count: number }
export interface EndpointStat { path: string; count: number; avg_ms: number }
export interface RequestLog { id: number; method: string; path: string; status_code: number; duration_ms: number; user_id: number | null; created_at: string }
export interface Traffic { total_requests: number; last_24h: number; avg_ms: number; daily: DailyPoint[]; endpoints: EndpointStat[]; recent: RequestLog[] }
