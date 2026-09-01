import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { api } from "../api";
import { BookIcon, ScrollIcon, UsersIcon } from "../components/icons";
import { parseUtc } from "../time";
import type { Volume } from "../types";

type TianjiDraft = { name: string; description: string };

export default function Collections() {
  const { user } = useAuth();
  const [volumes, setVolumes] = useState<Volume[] | null>(null);
  const [writing, setWriting] = useState(false);
  const [title, setTitle] = useState("");
  const [introduction, setIntroduction] = useState("");
  const [requirements, setRequirements] = useState("");
  const [victory, setVictory] = useState("");
  const [tianji, setTianji] = useState<TianjiDraft[]>([{ name: "", description: "" }]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api<Volume[]>("/collections/volumes").then(setVolumes).catch((error: Error) => setErr(error.message));
  useEffect(() => { load(); }, []);

  function updateTianji(index: number, key: keyof TianjiDraft, value: string) {
    setTianji((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setErr("");
    try {
      await api("/collections/volumes", { method: "POST", body: JSON.stringify({ title, introduction, booklet_requirements: requirements, victory_condition: victory, tianji }) });
      setTitle(""); setIntroduction(""); setRequirements(""); setVictory(""); setTianji([{ name: "", description: "" }]); setWriting(false); await load();
    } catch (error: any) { setErr(error.message); } finally { setBusy(false); }
  }

  return <>
    <div className="section-head world-head">
      <div><h1 className="section-title"><ScrollIcon size={22} /> 小天下集</h1><p className="muted">集天下异闻成卷，入卷之册各守其局。</p></div>
      {user?.is_admin && <button className="btn btn-primary btn-sm" onClick={() => setWriting((value) => !value)}><BookIcon size={14} /> 新添卷</button>}
    </div>
    {err && <p className="err">{err}</p>}
    {writing && <form className="panel world-form" onSubmit={create}>
      <div className="panel__head"><h3>新添卷</h3></div>
      <label>卷名<input value={title} maxLength={80} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label>卷介<textarea value={introduction} maxLength={1200} onChange={(event) => setIntroduction(event.target.value)} required /></label>
      <label>入卷标准<textarea value={requirements} maxLength={1200} onChange={(event) => setRequirements(event.target.value)} placeholder="说明什么样的奇人与册局才可收入此卷。" required /></label>
      <label>挑战者胜利条件<textarea value={victory} maxLength={1200} onChange={(event) => setVictory(event.target.value)} placeholder="衍算检定只按此条件判定衍破。" required /></label>
      <div className="world-form__group"><b>天机</b>{tianji.map((item, index) => <div className="world-tianji-edit" key={index}><input value={item.name} maxLength={80} onChange={(event) => updateTianji(index, "name", event.target.value)} placeholder="天机名" required /><textarea value={item.description} maxLength={800} onChange={(event) => updateTianji(index, "description", event.target.value)} placeholder="不可被奇术直接影响的事物与规则" required />{tianji.length > 1 && <button className="btn btn-ghost btn-sm" type="button" onClick={() => setTianji((items) => items.filter((_, itemIndex) => itemIndex !== index))}>删去</button>}</div>)}<button className="btn btn-ghost btn-sm" type="button" onClick={() => setTianji((items) => [...items, { name: "", description: "" }])}>添一条天机</button></div>
      <div className="world-form__actions"><button className="btn btn-ghost" type="button" onClick={() => setWriting(false)}>作罢</button><button className="btn btn-primary" disabled={busy}>{busy ? "编卷中" : "新添卷"}</button></div>
    </form>}
    {volumes === null ? <div className="skeleton" style={{ height: 260 }} /> : volumes.length === 0 ? <div className="empty"><ScrollIcon size={24} /><h3>小天下集尚无卷</h3></div> : <div className="world-feed">{volumes.map((volume) => <Link className="world-post-row" to={`/collections/volumes/${volume.id}`} key={volume.id}><span className="seal">卷</span><div className="world-post-row__main"><h2>{volume.title}</h2><p>{volume.introduction}</p><span className="muted">{volume.author} 新添 · {parseUtc(volume.created_at).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}</span></div><div className="world-post-row__meta"><UsersIcon size={15} /> {volume.booklet_count} 册<br />天机 {volume.tianji.length} 条</div></Link>)}</div>}
  </>;
}
