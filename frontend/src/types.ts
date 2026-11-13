import type { components } from "./generated/api";

interface UnderstandingPhase { present: boolean; text: string }
interface Understanding { verdict: { zero_phase: boolean; source_phases: string[]; summary: string }; pre: UnderstandingPhase; mid: UnderstandingPhase; post: UnderstandingPhase }
function phase(p: unknown): UnderstandingPhase { const o = (p && typeof p === "object" ? p : {}) as Record<string, unknown>; return { present: !!o.present, text: typeof o.text === "string" ? o.text : "" }; }
export function parseUnderstanding(json: string | undefined | null): Understanding | null { if (!json) return null; try { const u = JSON.parse(json) as Record<string, unknown>; if (!u || typeof u !== "object" || !u.verdict) return null; const v = u.verdict as Record<string, unknown>; return { verdict: { zero_phase: !!v.zero_phase, source_phases: Array.isArray(v.source_phases) ? v.source_phases.filter((s) => typeof s === "string") : [], summary: typeof v.summary === "string" ? v.summary : "" }, pre: phase(u.pre), mid: phase(u.mid), post: phase(u.post) }; } catch { return null; } }
export type LlmProfile = components["schemas"]["LlmProfileOut"];
export type Character = Pick<components["schemas"]["CharacterOut"], "id" | "owner_id" | "name" | "bio"> & Required<Pick<components["schemas"]["CharacterOut"], "ability_ids">>;
export type Ability = components["schemas"]["AbilityOut"];
export type Scenario = components["schemas"]["ScenarioOut"];
/** 立卷提交体：与后端 ScenarioIn 同形（app/schemas/scenario_domain.py），slug/status 由服务端派生 */
export type ScenarioDraft = components["schemas"]["ScenarioIn"];
