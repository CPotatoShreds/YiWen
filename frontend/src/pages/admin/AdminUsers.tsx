import { useEffect, useState } from "react";
import { api } from "../../api";
import { PencilIcon, PlusIcon, TrashIcon, XIcon } from "../../components/icons";
import type { AdminUser } from "./types";

type Form = { username: string; password: string; is_admin: boolean };
const blank: Form = { username: "", password: "", is_admin: false };

function UserModal({ initial, editing, busy, onClose, onSave }: { initial: Form; editing: AdminUser | null; busy: boolean; onClose: () => void; onSave: (form: Form) => void }) {
  const [form, setForm] = useState(initial);
  const update = (p: Partial<Form>) => setForm((v) => ({ ...v, ...p }));
  return <div className="modal-overlay" onClick={onClose}><div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}><div className="modal__head"><h3>{editing ? `编辑「${editing.username}」` : "新增异闻师"}</h3><button className="modal__close" onClick={onClose} aria-label="关闭"><XIcon size={16} /></button></div><div className="field"><label>名号</label><input className="input" value={form.username} onChange={(e) => update({ username: e.target.value })} autoFocus /></div><div className="field"><label>{editing ? "新密码" : "密码"}</label><input className="input" type="password" value={form.password} onChange={(e) => update({ password: e.target.value })} /></div><label className="toggle"><input type="checkbox" checked={form.is_admin} onChange={(e) => update({ is_admin: e.target.checked })} /><span className="toggle__track" /><span className="toggle__label">管理员权限</span></label><div className="modal-actions"><button className="btn btn-ghost" onClick={onClose}>作罢</button><button className="btn btn-primary" disabled={busy || !form.username.trim() || (!editing && form.password.length < 6)} onClick={() => onSave(form)}><PlusIcon size={15} />{busy ? "保存中…" : "保存"}</button></div></div></div>;
}

export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([]); const [search, setSearch] = useState(""); const [editing, setEditing] = useState<AdminUser | null | undefined>(undefined); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const load = () => api<AdminUser[]>(`/admin/users${search ? `?search=${encodeURIComponent(search)}` : ""}`).then(setUsers).catch((e: Error) => setErr(e.message));
  useEffect(() => { load(); }, [search]);
  const formFor = (u: AdminUser | null) => u ? { username: u.username, password: "", is_admin: u.is_admin } : blank;
  async function save(form: Form) { setBusy(true); setErr(""); try { const body = { ...form, ...(form.password ? {} : { password: undefined }) }; if (editing) await api(`/admin/users/${editing.id}`, { method: "PUT", body: JSON.stringify(body) }); else await api("/admin/users", { method: "POST", body: JSON.stringify(body) }); setEditing(undefined); await load(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } }
  async function remove(u: AdminUser) { if (!window.confirm(`确认删除「${u.username}」？其奇术、奇人与挑战数据都会被清理。`)) return; try { await api(`/admin/users/${u.id}`, { method: "DELETE" }); await load(); } catch (e: any) { setErr(e.message); } }
  return <div className="admin-page"><div className="admin-toolbar"><div><span className="eyebrow">USER DIRECTORY</span><h2>异闻师名册</h2></div><div className="admin-toolbar__actions"><input className="input admin-search" placeholder="搜索名号" value={search} onChange={(e) => setSearch(e.target.value)} /><button className="btn btn-primary" onClick={() => setEditing(null)}><PlusIcon size={15} />新增</button></div></div>{err && <p className="err">{err}</p>}<div className="tbl-list">{users.map((u) => <div className="tbl-row" key={u.id}><span className="tbl-col mono">#{u.id}</span><span className="tbl-col tbl-col--main"><b>{u.username}</b>{u.is_admin && <span className="admin-chip">管理员</span>}</span><span className="tbl-col muted">奇术 {u.ability_count}</span><span className="tbl-col tbl-actions"><button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditing(u)} title="编辑"><PencilIcon size={14} /></button><button className="btn btn-danger btn-icon btn-sm" onClick={() => remove(u)} title="删除"><TrashIcon size={14} /></button></span></div>)}</div>{users.length === 0 && <div className="empty"><p>暂无异闻师。</p></div>}{editing !== undefined && <UserModal initial={formFor(editing)} editing={editing} busy={busy} onClose={() => setEditing(undefined)} onSave={save} />}</div>;
}
