import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ScrollIcon } from "../components/icons";
import { CloudDivider, SealStamp } from "../components/Ornaments";

type Scenario = { id: string; slug: string; name: string; subtitle: string; introduction: string; background: string; rules: string[]; victory_condition: string; judgement_rules: string[] };
type Roster = { id: string; name: string; owner_name: string; character_bio: string; ability_count: number; challenge_count: number; challenger_win_rate: number | null; first_victory_avg_challenges: number | null };

export default function ScenarioDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { if (!slug) return; Promise.all([api<Scenario>(`/scenarios/${slug}`), api<Roster[]>(`/scenarios/${slug}/rosters`)]).then(([item, list]) => { setScenario(item); setRosters(list); }).catch((cause: Error) => setError(cause.message)); }, [slug]);
  if (!scenario) return error ? <p className="err">{error}</p> : <div className="skeleton" style={{ height: 320 }} />;
  const card = (roster: Roster) => (
    <Link className="panel scenario-roster-card scenario-roster-card--link" key={roster.id} to={`/scenarios/${scenario.slug}/rosters/${roster.id}`}>
      <header className="scenario-roster-card__head">
        <div>
          <span className="muted">{roster.owner_name}</span>
          <h3>{roster.name}</h3>
        </div>
        <span className="scenario-roster-card__seal"><SealStamp char="阵" size={26} /></span>
      </header>
      <div className="scenario-roster-card__identity">
        <span>{roster.character_bio || "暂无简介"}</span>
      </div>
      <dl className="scenario-roster-card__stats">
        <div><dt>奇术</dt><dd>{roster.ability_count} 门</dd></div>
        <div><dt>胜率</dt><dd>{roster.challenger_win_rate == null ? "暂无" : `${Math.round(roster.challenger_win_rate * 100)}%`}</dd></div>
        <div><dt>首胜</dt><dd>{roster.first_victory_avg_challenges == null ? "暂无" : `${roster.first_victory_avg_challenges.toFixed(1)} 次`}</dd></div>
        <div><dt>挑战</dt><dd>{roster.challenge_count} 次</dd></div>
      </dl>
    </Link>
  );
  return <>
    <div className="section-head scenario-detail-head">
      <div>
        <h1 className="section-title"><ScrollIcon size={22} /> {scenario.name}</h1>
        <p className="muted">{scenario.subtitle}</p>
      </div>
      <div className="scenario-detail-head__actions">
        <Link className="btn btn-primary" to={`/creator/scenarios/new?scenario_id=${scenario.id}`}>排布阵容</Link>
        <Link className="muted" to="/scenarios">返回小天下集</Link>
      </div>
    </div>
    <CloudDivider />
    <section className="scroll-head">
      <div className="scroll-head__lead">
        <p className="scroll-head__summary">{scenario.introduction}</p>
        <p className="scroll-head__bg">{scenario.background}</p>
      </div>
      <div className="scroll-head__rules">
        <div className="scroll-rule">
          <strong>规则</strong>
          <ul>{scenario.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        </div>
        <div className="scroll-rule scroll-rule--judge">
          <strong>挑战者胜利条件</strong>
          <p>{scenario.victory_condition}</p>
          <ul className="scroll-rule__judgement">{scenario.judgement_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        </div>
      </div>
    </section>
    {error && <p className="err">{error}</p>}
    <section className="scenario-roster-section">
      <div className="scenario-roster-section__head">
        <div>
          <h2>阵容</h2>
          <p className="muted">由异闻师为这个情景提供的挑战方式</p>
        </div>
      </div>
      <CloudDivider />
      <div className="scenario-roster-grid">{rosters.length ? rosters.map(card) : <p className="muted">暂未有可挑战的阵容。</p>}</div>
    </section>
  </>;
}
