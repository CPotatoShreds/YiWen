import { useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { useApiQuery } from "../useApiQuery";
import type { Scenario } from "../types";
import { ScrollIcon } from "../components/icons";

export default function Scenarios() {
  const query = useApiQuery<Scenario[]>("/scenarios");
  const [search, setSearch] = useState("");
  const items = (query.data ?? []).filter(item => (item.name + item.subtitle + item.introduction).includes(search.trim()));
  return <PageShell title="小天下集" icon={<ScrollIcon size={22} />} subtitle="阅览天下异闻师记录的刻印，使用自己的奇人奇术推演过招" back={{to:"/home",label:"返回首页"}}>
    <div className="collection-toolbar"><label className="search-field"><span>搜索</span><input className="input" type="search" placeholder="卷名或内容" value={search} onChange={event=>setSearch(event.target.value)} /></label><span aria-live="polite">{query.isPending ? "载入中" : `${items.length} 卷`}</span><button className="btn btn-ghost" onClick={()=>void query.refetch()} disabled={query.isFetching}>刷新</button></div>
    {query.isError && <div className="ds-state" role="alert"><p>{query.error.message}</p><button className="btn" onClick={()=>void query.refetch()}>重试</button></div>}
    {query.isPending ? <div className="skeleton" style={{height:260}} aria-label="载入中" /> : !query.isError && !items.length ? <div className="ds-state"><h2>{search ? "未找到相应的卷" : "尚无已发布的卷"}</h2>{search && <button className="btn" onClick={()=>setSearch("")}>清除搜索</button>}</div> : <div className="volume-catalog">{items.map(scenario=><Link className="volume-card" to={`/scenarios/${scenario.slug}`} key={scenario.id}><span className="volume-spine" aria-hidden="true" /><div><span className="volume-subtitle">{scenario.subtitle}</span><h2>{scenario.name}</h2><p>{scenario.introduction}</p></div></Link>)}</div>}
  </PageShell>;
}
