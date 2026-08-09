import { useEffect, useState } from "react";
import { api } from "../../api";
import { PencilIcon, PlusIcon, TrashIcon, XIcon } from "../../components/icons";
import type { Ability } from "./types";

type Form = { name: string; effect: string; detail: string; tactic: string };
const blank: Form = { name: "", effect: "", detail: "", tactic: "" };

function AbilityModal({ editing, onClose, onSave, busy }: { editing: Ability | null; onClose: () => void; onSave: (form: Form) => void; busy: boolean }) {
  const [form, setForm] = useState<Form>(editing ? { name: editing.name, effect: editing.effect, detail: editing.detail, tactic: editing.tactic } : blank);
  const update = (p: Partial<Form>) => setForm((v) => ({ ...v, ...p }));
  return <div className="modal-overlay" onClick={onClose}><div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}><div className="modal__head"><h3>{editing ? `修订「${editing.name}」` : "新增奇术"}</h3><button className="modal__close" onClick={onClose} aria-label="关闭"><XIcon size={16} /></button></div><div className="field"><label>名目</label><input className="input" value={form.name} onChange={(e) => update({ name: e.target.value })} autoFocus /></div><div className="field"><label>效果</label><textarea className="textarea" rows={3} value={form.effect} onChange={(e) => update({ effect: e.target.value })} /></div><div className="field"><label>补充说明 <span className="hint">可选</span></label><textarea className="textarea" rows={2} value={form.detail} onChange={(e) => update({ detail: e.target.value })} /></div><div className="field"><label>战术 <span className="hint">可选</span></label><textarea className="textarea" rows={2} value={form.tactic} onChange={(e) => update({ tactic: e.target.value })} /></div><div className="modal-actions"><button className="btn btn-ghost" onClick={onClose}>作罢</button><button className="btn btn-primary" disabled={busy || !form.name.trim() || !form.effect.trim()} onClick={() => onSave(form)}><PlusIcon size={15} />{busy ? "写入中…" : "保存奇术"}</button></div></div></div>;
}

export default function AdminAbilities() {
  const [items, setItems] = useState<Ability[]>([]); const [editing, setEditing] = useState<Ability | null | undefined>(undefined); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const load = () => api<Ability[]>("/admin/abilities").then(setItems).catch((e: Error) => setErr(e.message));
  useEffect(() => { load(); }, []);
  async function save(form: Form) { setBusy(true); try { await api(editing ? `/admin/abilities/${editing.id}` : "/admin/abilities", { method: editing ? "PUT" : "POST", body: JSON.stringify(form) }); setEditing(undefined); await load(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } }
  async function remove(item: Ability) { if (!window.confirm(`确认删除「${item.name}」？它会从所有异闻师与奇人中移除。`)) return; try { await api(`/admin/abilities/${item.id}`, { method: "DELETE" }); await load(); } catch (e: any) { setErr(e.message); } }
  return <div className="admin-page"><div className="admin-toolbar"><div><span className="eyebrow">ABILITY ARCHIVE</span><h2>奇术档案</h2></div><button className="btn btn-primary" onClick={() => setEditing(null)}><PlusIcon size={15} />新增奇术</button></div>{err && <p className="err">{err}</p>}<div className="ability-list">{items.map((item) => <div className="ability-item" key={item.id}><div className="ability-item__body"><div className="ability-item__name">{item.name}</div><p className="ability-item__effect">{item.effect}</p>{item.detail && <p className="muted">{item.detail}</p>}</div><div className="ability-item__actions"><button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditing(item)} title="编辑"><PencilIcon size={14} /></button><button className="btn btn-danger btn-icon btn-sm" onClick={() => remove(item)} title="删除"><TrashIcon size={14} /></button></div></div>)}</div>{items.length === 0 && <div className="empty"><p>暂无奇术档案。</p></div>}{editing !== undefined && <AbilityModal editing={editing} busy={busy} onClose={() => setEditing(undefined)} onSave={save} />}</div>;
}
