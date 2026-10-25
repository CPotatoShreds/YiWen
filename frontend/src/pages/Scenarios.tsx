import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../api";
import { ScrollIcon, UsersIcon } from "../components/icons";
import { EmptyScroll, SealStamp } from "../components/Ornaments";
import type { Scenario } from "../types";

export default function Scenarios() {
  const [items, setItems] = useState<Scenario[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<Scenario[]>("/scenarios").then(setItems).catch((cause: Error) => setError(cause.message)); }, []);
  return (
    <PageShell
      title="小天下集"
      icon={<ScrollIcon size={22} />}
      subtitle="浏览异闻师发布的各卷，择一位奇人入场推演。"
      back={{ to: "/home", label: "返回首页" }}
    >
      {error && <p className="err">{error}</p>}
      {items === null ? <div className="skeleton" style={{ height: 260 }} /> : items.length === 0 ? <div className="empty empty--scroll"><EmptyScroll size={168} /><h3>尚无已发布的卷</h3><p>卷架空空，待第一位异闻师落笔成卷。</p></div> : <div className="world-feed">{items.map((scenario) => <Link className="world-post-row" to={`/scenarios/${scenario.slug}`} key={scenario.id}><span className="world-post-row__seal"><SealStamp char="闻" size={30} /></span><div className="world-post-row__main"><h2>{scenario.name}</h2><p>{scenario.introduction}</p><span className="world-post-row__byline muted"><UsersIcon size={14} /> {scenario.subtitle}</span></div><div className="world-post-row__meta"><span>规则与胜利条件已公布</span><span className="world-post-row__cue">展卷 <b>→</b></span></div></Link>)}</div>}
    </PageShell>
  );
}
