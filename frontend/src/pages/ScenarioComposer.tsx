import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";

type Scenario = { id: string; name: string };
type Character = { id: string; current_title: string };

export default function ScenarioComposer() {
  const navigate = useNavigate(); const [params] = useSearchParams(); const scenarioId = params.get("scenario_id") ?? "";
  const [scenario, setScenario] = useState<Scenario | null>(null); const [characters, setCharacters] = useState<Character[]>([]); const [characterId, setCharacterId] = useState(""); const [guidance, setGuidance] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  useEffect(() => { if (!scenarioId) return; Promise.all([api<Scenario>(`/scenarios/${scenarioId}`), api<{ items: Character[] }>("/creator/assets?kind=character&limit=100")]).then(([item, assets]) => { setScenario(item); setCharacters(assets.items); }).catch((e: Error) => setError(e.message)); }, [scenarioId]);
  const create = async () => { if (!scenarioId || !characterId) { setError("请选择目标情景和守方奇人"); return; } setBusy(true); setError(""); try { await api(`/creator/scenarios/${scenarioId}/rosters`, { method: "POST", body: JSON.stringify({ character_asset_id: characterId, guidance }) }); navigate(`/scenarios/${scenarioId}`); } catch (e) { setError(e instanceof Error ? e.message : "创建失败"); } finally { setBusy(false); } };
  if (!scenarioId) return <section className="panel"><h1>添加我的阵容</h1><p className="muted">请从小天下集的情景详情进入。</p><Link className="btn btn-ghost" to="/scenarios">浏览小天下集</Link></section>;
  return <section className="scenario-composer panel"><div className="section-head"><div><h1 className="section-title">添加我的阵容</h1><p className="muted">情景：{scenario?.name ?? "读取中"}</p></div><Link className="muted" to={scenario ? `/scenarios/${scenario.id}` : "/scenarios"}>返回情景</Link></div><div className="creator-form"><label className="field"><span>选择自己的奇人</span><select className="input" value={characterId} onChange={(e) => setCharacterId(e.target.value)}><option value="">请选择私有奇人</option>{characters.map((character) => <option key={character.id} value={character.id}>{character.current_title}</option>)}</select></label><label className="field"><span>指导策略<small>{guidance.length}/1000</small></span><textarea className="textarea" rows={8} maxLength={1000} value={guidance} onChange={(e) => setGuidance(e.target.value)} placeholder="给挑战者的策略提示" /></label></div>{error && <p className="err">{error}</p>}<div className="creator-canvas__actions"><button className="btn btn-primary" disabled={busy} onClick={() => void create()}>保存并公开阵容</button></div></section>;
}
