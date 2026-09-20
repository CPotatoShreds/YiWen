import { api } from "./api";

// 起笔与再战共用入口：后端每次调用都新建一条挑战记录（ScenarioChallengeRun），
// 奇术逐对比对走奇术级缓存。返回新挑战 id，由调用方决定跳转与策略参数。
export async function startScenarioChallenge(rosterId: string, characterId: string): Promise<string> {
  const created = await api<{ id: string }>(`/scenario-rosters/${rosterId}/challenges`, {
    method: "POST",
    body: JSON.stringify({ character_id: characterId }),
  });
  return created.id;
}
