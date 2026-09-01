import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ScrollIcon, UsersIcon } from "../components/icons";
import type { Scenario } from "../types";

export default function Scenarios() {
  const [items, setItems] = useState<Scenario[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<Scenario[]>("/scenarios").then(setItems).catch((cause: Error) => setError(cause.message)); }, []);
  return <>
    <div className="section-head world-head"><div><h1 className="section-title"><ScrollIcon size={22} /> 小天下集</h1><p className="muted">浏览异闻师发布的完整异闻，择一位奇人入场衍算。</p></div></div>
    {error && <p className="err">{error}</p>}
    {items === null ? <div className="skeleton" style={{ height: 260 }} /> : items.length === 0 ? <div className="empty"><ScrollIcon size={24} /><h3>尚无已发布情景</h3></div> : <div className="world-feed">{items.map((scenario) => <Link className="world-post-row" to={`/scenarios/${scenario.id}`} key={scenario.id}><span className="seal">闻</span><div className="world-post-row__main"><h2>{scenario.name}</h2><p>{scenario.summary}</p><span className="muted"><UsersIcon size={14} /> 小天下集情景</span></div><div className="world-post-row__meta">挑战条件已公布</div></Link>)}</div>}
  </>;
}
