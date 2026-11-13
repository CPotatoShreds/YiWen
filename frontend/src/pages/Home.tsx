import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { useApiQuery } from "../useApiQuery";
import type { Scenario, Character, Ability } from "../types";

export default function Home() {
  const { user } = useAuth();
  const volumes = useApiQuery<Scenario[]>("/scenarios");
  const characters = useApiQuery<Character[]>("/creator/characters");
  const abilities = useApiQuery<Ability[]>("/creator/abilities");
  return <div className="study-home">
    <header className="study-heading"><div><p className="study-greeting">{user?.username}，欢迎回到书院</p><h1>奇思落纸，万象成局。</h1><p>收录你的奇人奇术，在小天下集中推演过招，循着行迹看破对方的秘密。</p></div><Link className="btn btn-primary" to="/scenarios">去小天下集</Link></header>
    <div className="study-grid">
      <section className="study-volumes"><header className="block-heading"><h2>今日展卷</h2><Link to="/scenarios">查看全部卷 →</Link></header>
        {volumes.isPending ? <div className="skeleton" aria-label="正在载入卷" style={{height:200}} /> : volumes.isError ? <div className="ds-state" role="alert"><p>卷架暂时未能载入。</p><button className="btn" onClick={() => void volumes.refetch()}>重新载入</button></div> : volumes.data?.length ? volumes.data.slice(0,3).map(volume => <Link className="volume-entry" key={volume.id} to={`/scenarios/${volume.slug}`}><div><h3>{volume.name}</h3><p>{volume.introduction}</p><small>{volume.subtitle}</small></div><span aria-hidden="true">↗</span></Link>) : <div className="ds-state"><h3>卷架待新篇</h3><p>尚无已发布的卷。先收录一位奇人，准备第一场推演。</p><Link to="/yiwenlu">前往异闻录 →</Link></div>}
      </section>
      <aside className="study-collection"><h2>你的异闻录</h2><p>一位奇人，至多四门奇术。让你的构想成为可推演的力量。</p><dl className="collection-stats"><div><dt>奇人</dt><dd>{characters.data?.length ?? "—"}</dd></div><div><dt>奇术</dt><dd>{abilities.data?.length ?? "—"}</dd></div></dl>
      {(characters.isError || abilities.isError) && <p className="err">藏录暂未载入，请稍后重试。</p>}
      <Link className="btn" to="/yiwenlu">整理我的藏录 →</Link>
      <div className="study-note"><h3>三相共鸣</h3><p><b>契相</b> · 发动的限制与条件</p><p><b>显相</b> · 力量如何作用于世界</p><p><b>果相</b> · 必须承担的代价</p></div></aside>
    </div>
    <section className="study-path"><h2>从奇思到一场对局</h2><div><p><strong>收录</strong><span>创作奇术，装配奇人。</span></p><p><strong>推演</strong><span>挑选刻印，写下你的策略。</span></p><p><strong>看破</strong><span>阅读行迹，道出猜测。</span></p></div></section>
  </div>;
}
