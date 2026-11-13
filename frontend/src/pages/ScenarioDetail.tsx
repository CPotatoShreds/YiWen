import { Link, useParams } from "react-router-dom";
import { useApiQuery } from "../useApiQuery";
import PageShell from "../components/PageShell";
import { ScrollIcon } from "../components/icons";
import { SealStamp, CloudDivider } from "../components/Ornaments";
import type { Scenario } from "../types";

type Roster = { id: string; name: string; owner_name: string; character_bio: string; ability_count: number; challenge_count: number; challenger_win_rate: number | null; first_victory_avg_challenges: number | null };

export default function ScenarioDetail() {
  const { slug } = useParams<{ slug: string }>();
  const volume = useApiQuery<Scenario>(`/scenarios/${slug}`, !!slug);
  const rosterQuery = useApiQuery<Roster[]>(`/scenarios/${slug}/rosters`, !!slug);
  const scenario = volume.data;
  const rosters = rosterQuery.data ?? [];
  if (!scenario) return volume.isError ? <div className="ds-state" role="alert"><p>{volume.error.message}</p><button className="btn" onClick={() => void volume.refetch()}>重新展卷</button><Link className="btn" to="/scenarios">返回卷架</Link></div> : <div className="skeleton" aria-label="正在展卷" style={{ height: 320 }} />;
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
        <div><dt>对局</dt><dd>{roster.challenge_count} 次</dd></div>
      </dl>
    </Link>
  );
  return (
    <PageShell
      title={scenario.name}
      icon={<ScrollIcon size={22} />}
      subtitle={scenario.subtitle}
      back={{ to: "/scenarios", label: "返回小天下集" }}
      actions={<Link className="btn btn-primary" to={`/scenarios/${scenario.slug}/rosters/new`}>刻印奇人</Link>}
    >
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
    <section className="scenario-roster-section">
      <div className="scenario-roster-section__head">
        <div>
          <h2>刻印</h2>
        </div>
      </div>
      <CloudDivider />
      {rosterQuery.isError ? <div role="alert" className="ds-state"><p>{rosterQuery.error.message}</p><button className="btn" onClick={() => void rosterQuery.refetch()}>重新载入刻印</button></div> : rosterQuery.isPending ? <p role="status" className="muted">正在寻访卷中奇人…</p> : <div className="scenario-roster-grid">{rosters.length ? rosters.map(card) : <p className="muted">这一卷还没有刻印。</p>}</div>}
    </section>
    </PageShell>
  );
}
