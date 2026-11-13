import { useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { useApiQuery } from "../useApiQuery";
import type { Scenario } from "../types";

export default function Scenarios() {
  const query = useApiQuery<Scenario[]>("/scenarios");
  const [search, setSearch] = useState("");
  const items = (query.data ?? []).filter(item => (item.name + item.subtitle + item.introduction).includes(search.trim()));
  return <PageShell title="小天下集" subtitle="一卷一方天地。挑选卷中刻印，以你的奇人赴一场对局。" back={{to:"/home",label:"返回书院"}}>
    <div className="collection-toolbar"><label className="search-field"><span>寻卷</span><input className="input" type="search" placeholder="按卷名或内容查找" value={search} onChange={event=>setSearch(event.target.value)} /></label><span aria-live="polite">{query.isPending ? "正在展卷" : `${items.length} 卷`}</span><button className="btn btn-ghost" onClick={()=>void query.refetch()} disabled={query.isFetching}>刷新</button></div>
    {query.isError && <div className="ds-state" role="alert"><h2>暂时未能展卷</h2><p>{query.error.message}</p><button className="btn" onClick={()=>void query.refetch()}>重新载入</button></div>}
    {query.isPending ? <div className="skeleton" style={{height:260}} aria-label="载入中" /> : !query.isError && !items.length ? <div className="ds-state"><h2>{search ? "未找到相应的卷" : "卷架待新篇"}</h2><p>{search ? "换一个卷名或关键词再试。" : "尚无已发布的卷。可以先去异闻录收录奇人。"}</p>{search ? <button className="btn" onClick={()=>setSearch("")}>清除搜索</button> : <Link className="btn" to="/yiwenlu">前往异闻录</Link>}</div> : <div className="volume-catalog">{items.map(scenario=><Link className="volume-card" to={`/scenarios/${scenario.slug}`} key={scenario.id}><span className="volume-spine" aria-hidden="true">小天下集</span><div><span className="volume-subtitle">{scenario.subtitle}</span><h2>{scenario.name}</h2><p>{scenario.introduction}</p><span className="volume-open">展卷，查看刻印 <span aria-hidden="true">↗</span></span></div></Link>)}</div>}
  </PageShell>;
}
