import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { BookIcon, LockIcon, ScrollIcon, SwordIcon, UsersIcon } from "../components/icons";
import type { Booklet, Loadout, VolumeDetail } from "../types";

function Stat({ label, value }: { label: string; value: string }) { return <span className="world-stat"><b>{value}</b>{label}</span>; }

export default function Volume() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [volume, setVolume] = useState<VolumeDetail | null>(null);
  const [loadouts, setLoadouts] = useState<Loadout[]>([]);
  const [addingBooklet, setAddingBooklet] = useState(false);
  const [selected, setSelected] = useState("");
  const [temporaryName, setTemporaryName] = useState("");
  const [temporaryEffect, setTemporaryEffect] = useState("");
  const [opening, setOpening] = useState("");
  const [brief, setBrief] = useState("");
  const [challenging, setChallenging] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => { if (!id) return; try { setVolume(await api<VolumeDetail>(`/collections/volumes/${id}`)); setLoadouts(await api<Loadout[]>("/loadouts")); } catch (error: any) { setErr(error.message); } };
  useEffect(() => { load(); }, [id]);
  const usable = loadouts.filter((loadout) => loadout.abilities.length > 0);
  const selectedMember = () => selected === "__new__"
    ? { name: temporaryName, abilities: [{ name: "临时奇术", effect: temporaryEffect }] }
    : { loadout_id: Number(selected) };
  const invalidSelection = !selected || (selected === "__new__" && (!temporaryName.trim() || !temporaryEffect.trim()));

  async function addBooklet(event: FormEvent) {
    event.preventDefault(); if (!id) return; setBusy(true); setErr("");
    try { await api(`/collections/volumes/${id}/booklets`, { method: "POST", body: JSON.stringify({ defenders: [selectedMember()], opening, guardian_brief: brief }) }); setAddingBooklet(false); await load(); }
    catch (error: any) { setErr(error.message); } finally { setBusy(false); }
  }
  async function challenge(booklet: Booklet) {
    setBusy(true); setErr("");
    try { const result = await api<{ id: number }>(`/collections/booklets/${booklet.id}/challenges`, { method: "POST", body: JSON.stringify({ challengers: [selectedMember()] }) }); nav(`/collections/challenges/${result.id}`); }
    catch (error: any) { setErr(error.message); } finally { setBusy(false); }
  }
  async function closeBooklet(bookletId: number) { setBusy(true); try { await api(`/collections/booklets/${bookletId}/close`, { method: "POST" }); await load(); } catch (error: any) { setErr(error.message); } finally { setBusy(false); } }
  if (!volume) return err ? <p className="err">{err}</p> : <div className="skeleton" style={{ height: 320 }} />;

  return <>
    <div className="section-head"><h1 className="section-title"><ScrollIcon size={22} /> {volume.title}</h1><Link className="muted" to="/collections">返回小天下集</Link></div>
    <section className="world-post-intro"><p>{volume.introduction}</p><span className="muted">{volume.author} 新添 · 已收 {volume.booklet_count} 册</span></section>
    <div className="world-volume-rules"><section><h2>入卷标准</h2><p>{volume.booklet_requirements}</p></section><section><h2>挑战者胜利条件</h2><p>{volume.victory_condition}</p></section><section><h2><LockIcon size={16} /> 天机</h2>{volume.tianji.map((item) => <p key={item.name}><b>{item.name}</b>：{item.description}</p>)}</section></div>
    {err && <p className="err">{err}</p>}
    <button className="btn btn-primary" onClick={() => setAddingBooklet((value) => !value)}><BookIcon size={15} /> 在此卷下新添册</button>
    {addingBooklet && <form className="panel world-form" onSubmit={addBooklet}>
      <div className="panel__head"><h3>新添册</h3><span className="muted">册发布后即冻结守方阵容与场景设定。</span></div>
      <label>册中奇人<select value={selected} onChange={(event) => setSelected(event.target.value)} required><option value="">择一位奇人</option>{usable.map((loadout) => <option key={loadout.id} value={loadout.id}>{loadout.name || `奇人#${loadout.id}`} · {loadout.abilities.length} 门奇术</option>)}<option value="__new__">临时新建奇人</option></select><Link className="muted" to="/abilities">去异闻录新建或整编奇人</Link></label>
      {selected === "__new__" && <><label>临时奇人姓名<input value={temporaryName} maxLength={80} onChange={(event) => setTemporaryName(event.target.value)} required /></label><label>临时奇术效果<textarea value={temporaryEffect} maxLength={1200} onChange={(event) => setTemporaryEffect(event.target.value)} required /></label></>}
      <label>公开开场<textarea value={opening} onChange={(event) => setOpening(event.target.value)} placeholder="挑战者第一步行动前会看到这一段。" required /></label>
      <label>私密守册意图<textarea value={brief} onChange={(event) => setBrief(event.target.value)} placeholder="仅供守方 LLM 代理执行，不向挑战者展示。" required /></label>
      <div className="world-form__actions"><button className="btn btn-ghost" type="button" onClick={() => setAddingBooklet(false)}>作罢</button><button className="btn btn-primary" disabled={busy || invalidSelection}>新添册</button></div>
    </form>}
    <section className="world-answer-list"><h2>卷下诸册</h2>{volume.booklets.length === 0 ? <div className="empty"><UsersIcon size={22} /><p>暂无新添册。</p></div> : volume.booklets.map((booklet) => <article className="world-answer" key={booklet.id}>
      <header><span className="seal">册</span><div><h3>{booklet.author} 的册</h3><p className="muted">守方 {booklet.defender_people} 人 · 声明 {booklet.defender_ability_count} 门奇术</p></div>{booklet.mine && <span className="chip chip--ability">我的册</span>}</header>
      <p className="world-answer__opening">“{booklet.opening}”</p>
      <div className="world-stats"><Stat label="挑战" value={String(booklet.stats.challenge_count)} /><Stat label="衍破" value={String(booklet.stats.derived_count)} /><Stat label="堪破" value={String(booklet.stats.cracked_count)} /><Stat label="平均衍破世界" value={booklet.stats.avg_worldlines_to_derive?.toFixed(1) ?? "-"} /><Stat label="平均堪算原子" value={booklet.stats.avg_atoms_to_crack?.toFixed(1) ?? "-"} /></div>
      {booklet.can_manage && booklet.challenges_open && <div className="world-answer__actions"><button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => closeBooklet(booklet.id)}>关闭新挑战</button></div>}
      {!booklet.mine && booklet.challenges_open && <div className="world-answer__actions">{challenging === booklet.id ? <><select value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">点将出阵</option>{usable.map((loadout) => <option key={loadout.id} value={loadout.id}>{loadout.name || `奇人#${loadout.id}`} · {loadout.abilities.length} 术</option>)}<option value="__new__">临时新建奇人</option></select>{selected === "__new__" && <><input value={temporaryName} maxLength={80} onChange={(event) => setTemporaryName(event.target.value)} placeholder="临时奇人" /><input value={temporaryEffect} maxLength={1200} onChange={(event) => setTemporaryEffect(event.target.value)} placeholder="临时奇术效果" /></>}<Link className="muted" to="/abilities">整编</Link><button className="btn btn-primary btn-sm" disabled={invalidSelection || busy} onClick={() => challenge(booklet)}><SwordIcon size={14} /> 入场衍算</button></> : <button className="btn btn-primary btn-sm" onClick={() => setChallenging(booklet.id)}><SwordIcon size={14} /> 点将挑战</button>}</div>}
      {booklet.history.length > 0 && <div className="world-history">{booklet.history.map((item) => <Link key={item.id} to={`/collections/challenges/${item.id}`}>第 {item.worldline_count} 世界 · {item.derived ? "已衍破" : "未衍破"} · {item.cracked ? "已堪破" : "未堪破"} · 查看挑战</Link>)}</div>}
    </article>)}</section>
  </>;
}
