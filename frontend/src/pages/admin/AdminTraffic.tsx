import { useEffect, useState } from "react";
import { api } from "../../api";
import BarChart from "../../components/BarChart";
import type { Traffic } from "./types";

export default function AdminTraffic() {
  const [data, setData] = useState<Traffic | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api<Traffic>("/admin/traffic").then(setData).catch((e: Error) => setErr(e.message)); }, []);
  if (err) return <p className="err">{err}</p>;
  if (!data) return <div className="skeleton" style={{ height: 420 }} />;
  const max = Math.max(...data.endpoints.map((e) => e.count), 1);
  return <div className="admin-page">
    <div className="admin-stats admin-stats--traffic"><div className="admin-stat"><span className="muted">总请求</span><b>{data.total_requests}</b></div><div className="admin-stat"><span className="muted">近 24 小时</span><b>{data.last_24h}</b></div><div className="admin-stat"><span className="muted">平均 TTFB</span><b>{data.avg_ms.toFixed(1)}<small> ms</small></b></div></div>
    <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">REQUESTS / 7 DAYS</span><h2>请求走势</h2></div></div><BarChart data={data.daily.map((d) => ({ label: d.date.slice(5), value: d.count }))} /></section>
    <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">ENDPOINT TOP 12</span><h2>接口排行</h2></div></div>{data.endpoints.length === 0 ? <p className="muted">暂无流量记录。自动采集暂未开启。</p> : <div className="endpoint-list">{data.endpoints.map((ep) => <div className="endpoint-row" key={ep.path}><div className="endpoint-row__head"><span className="mono">{ep.path}</span><span>{ep.count} 次 · {ep.avg_ms.toFixed(1)} ms</span></div><div className="endpoint-track"><span style={{ width: `${(ep.count / max) * 100}%` }} /></div></div>)}</div>}</section>
    <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">LATEST REQUESTS</span><h2>最近请求</h2></div></div>{data.recent.length === 0 ? <p className="muted">暂无请求记录。</p> : <div className="tbl-list">{data.recent.map((log) => <div className="tbl-row" key={log.id}><span className="tbl-col mono">{log.method}</span><span className="tbl-col tbl-col--main mono">{log.path}</span><span className="tbl-col">{log.status_code}</span><span className="tbl-col mono">{log.duration_ms} ms</span></div>)}</div>}</section>
  </div>;
}
