import { useEffect, useState } from "react";
import { api } from "../../api";

type Scenario = {
  id: string; name: string; subtitle: string; introduction: string; background: string; rules: string[]; victory_condition: string; judgement_rules: string[];
  status: "draft" | "published" | "deleted"; published_at?: string | null;
};

export default function AdminScenarios() {
  const [items, setItems] = useState<Scenario[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = () => api<Scenario[]>("/admin/scenarios").then(setItems).catch((e: Error) => setError(e.message));
  useEffect(() => { void load(); }, []);
  const action = async (item: Scenario, operation: "publish" | "delete") => {
    setBusy(item.id); setError("");
    try { await api(`/admin/scenarios/${item.id}/${operation}`, { method: "POST" }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "操作失败"); }
    finally { setBusy(""); }
  };
  return <div className="admin-page">
    <div className="admin-toolbar"><div><h2>小天下集卷册</h2><p className="muted">管理卷册草稿、发布状态与下线。</p></div><button className="btn btn-ghost" onClick={() => void load()}>刷新</button></div>
    {error && <p className="err">{error}</p>}
    {items.length === 0 ? <div className="empty"><p>暂无卷册。</p></div> : <div className="review-list">{items.map((item) => <article className="review-item" key={item.id}>
      <div className="review-item__head"><h3>{item.name}</h3><span className="muted">{item.subtitle} · {item.status === "published" ? "已发布" : item.status === "deleted" ? "已下线" : "草稿"}</span></div>
      <p>{item.introduction}</p><details><summary>查看背景、规则与判定条件</summary><p>{item.background}</p><p><b>卷规则：</b></p><ul>{item.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul><p><b>胜利条件：</b>{item.victory_condition}</p><p><b>判定规则：</b></p><ul>{item.judgement_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul></details>
      <div className="review-item__actions">{item.status === "draft" && <button className="btn btn-primary" disabled={busy === item.id} onClick={() => void action(item, "publish")}>发布</button>}{item.status !== "deleted" && <button className="btn btn-danger" disabled={busy === item.id} onClick={() => void action(item, "delete")}>下线</button>}</div>
    </article>)}</div>}
  </div>;
}
