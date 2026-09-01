import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ScrollIcon } from "../components/icons";

type Scenario = { id: string; name: string; summary: string; background: string; victory_condition: string };
type Roster = { id: string; kind: string; name: string; owner_name: string; character_name: string; character_bio: string; guidance: string; ability_count: number; challenge_count: number; challenger_win_rate: number | null; first_victory_avg_challenges: number | null };

export default function ScenarioDetail() {
  const { id } = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { if (!id) return; Promise.all([api<Scenario>(`/scenarios/${id}`), api<Roster[]>(`/scenarios/${id}/rosters`)]).then(([item, list]) => { setScenario(item); setRosters(list); }).catch((cause: Error) => setError(cause.message)); }, [id]);
  if (!scenario) return error ? <p className="err">{error}</p> : <div className="skeleton" style={{ height: 320 }} />;
  const card = (roster: Roster) => <Link className="panel scenario-roster-card scenario-roster-card--link" key={roster.id} to={`/scenarios/${scenario.id}/rosters/${roster.id}`}><header className="scenario-roster-card__head"><div><span className="muted">{roster.kind === "official" ? "官方阵容" : "玩家阵容"} · {roster.owner_name}</span><h3>{roster.name}</h3></div><span className="scenario-roster-card__count">{roster.challenge_count} 次挑战</span></header><div className="scenario-roster-card__identity"><strong>{roster.character_name}</strong><span>{roster.character_bio || "暂无简介"}</span></div><div className="scenario-roster-card__stats"><span>{roster.ability_count} 门奇术</span><span>胜率 {roster.challenger_win_rate == null ? "暂无数据" : `${Math.round(roster.challenger_win_rate * 100)}%`}</span><span>首胜平均 {roster.first_victory_avg_challenges == null ? "暂无数据" : `${roster.first_victory_avg_challenges.toFixed(1)} 次`}</span></div><p className="scenario-roster-card__guidance">{roster.guidance || "作者未提供指导策略"}</p><footer><span className="muted">查看阵容详情 →</span></footer></Link>;
  return <><div className="section-head scenario-detail-head"><div><h1 className="section-title"><ScrollIcon size={22} /> {scenario.name}</h1><p className="muted">小天下集情景</p></div><Link className="muted" to="/scenarios">返回小天下集</Link></div><section className="world-post-intro"><div className="scenario-intro__copy"><p className="scenario-intro__summary">{scenario.summary}</p><p>{scenario.background}</p><p className="scenario-intro__condition"><strong>挑战者胜利条件</strong><span>{scenario.victory_condition}</span></p></div></section>{error && <p className="err">{error}</p>}<section className="scenario-roster-section"><div className="scenario-roster-section__head"><div><h2>官方阵容</h2><p className="muted">由异闻师预设的挑战方式</p></div></div><div className="scenario-roster-grid">{rosters.filter((roster) => roster.kind === "official").map(card)}</div></section><section className="scenario-roster-section"><div className="scenario-roster-section__head"><div><h2>玩家阵容</h2><p className="muted">其他玩家为这个情景提供的不同解法</p></div></div><div className="scenario-roster-grid">{rosters.filter((roster) => roster.kind === "player").map(card)}</div></section></>;
}
