import { useEffect, useState } from "react";
import { api } from "../../api";
import { PencilIcon, PlusIcon, TrashIcon, XIcon } from "../../components/icons";
import { parseUnderstanding } from "../../types";
import type { Ability } from "./types";

type Form = { name: string; effect: string; detail: string };
const blank: Form = { name: "", effect: "", detail: "" };

// 字段字数上限（与后端 AbilityAdminIn 的 max_length 对齐）
const FIELD_LIMITS = { name: 10, effect: 50, detail: 500 };

// 三相因果槽位的展示配置（与后端 Phase 对应）
const PHASE_LABELS: { key: "pre" | "mid" | "post"; label: string }[] = [
  { key: "pre", label: "契相" },
  { key: "mid", label: "显相" },
  { key: "post", label: "果相" },
];

// 三相因果槽位展示：有槽位显示零相提示 + 各相；无槽位显示「解析中」
function AbilitySlotView({ json }: { json: string }) {
  const slot = json ? parseUnderstanding(json) : null;
  if (!slot) return <p className="ability-item__pending">因果解析生成中…</p>;
  if (!(slot.verdict.zero_phase || PHASE_LABELS.some(({ key }) => slot[key].present))) return null;
  return (
    <div className="ability-slot">
      {slot.verdict.zero_phase && (
        <div className="ability-slot__zero">
          <span className="ability-slot__zero-pill">三相皆无</span>
          <span className="ability-slot__zero-note">奇术效果被削弱至近乎为零</span>
        </div>
      )}
      {PHASE_LABELS.map(({ key, label }) => {
        const ph = slot[key];
        if (!ph.present) return null;
        return (
          <div className="ability-slot__phase" key={key}>
            <span className="ability-slot__phase-label">{label}</span>
            <span className="ability-slot__phase-text">{ph.text}</span>
          </div>
        );
      })}
    </div>
  );
}

function AbilityModal({ editing, onClose, onSave, busy }: { editing: Ability | null; onClose: () => void; onSave: (form: Form) => void; busy: boolean }) {
  const [form, setForm] = useState<Form>(editing ? { name: editing.name, effect: editing.effect, detail: editing.detail } : blank);
  const update = (p: Partial<Form>) => setForm((v) => ({ ...v, ...p }));
  const over = form.name.length > FIELD_LIMITS.name || form.effect.length > FIELD_LIMITS.effect || form.detail.length > FIELD_LIMITS.detail;
  return <div className="modal-overlay" onClick={onClose}><div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}><div className="modal__head"><h3>{editing ? `修订「${editing.name}」` : "新增奇术"}</h3><button className="modal__close" onClick={onClose} aria-label="关闭"><XIcon size={16} /></button></div><div className="field"><label>名目</label><span className={`char-count${form.name.length > FIELD_LIMITS.name ? " char-count--over" : ""}`}>{form.name.length}/{FIELD_LIMITS.name}</span><input className="input" value={form.name} maxLength={FIELD_LIMITS.name} onChange={(e) => update({ name: e.target.value })} autoFocus /></div><div className="field"><label>效果</label><span className={`char-count${form.effect.length > FIELD_LIMITS.effect ? " char-count--over" : ""}`}>{form.effect.length}/{FIELD_LIMITS.effect}</span><textarea className="textarea" rows={3} value={form.effect} maxLength={FIELD_LIMITS.effect} onChange={(e) => update({ effect: e.target.value })} /></div><div className="field"><label>补充说明 <span className="hint">可选</span></label><span className={`char-count${form.detail.length > FIELD_LIMITS.detail ? " char-count--over" : ""}`}>{form.detail.length}/{FIELD_LIMITS.detail}</span><textarea className="textarea" rows={2} value={form.detail} maxLength={FIELD_LIMITS.detail} onChange={(e) => update({ detail: e.target.value })} /></div><div className="modal-actions"><button className="btn btn-ghost" onClick={onClose}>作罢</button><button className="btn btn-primary" disabled={busy || over || !form.name.trim() || !form.effect.trim()} onClick={() => onSave(form)}><PlusIcon size={15} />{busy ? "写入中…" : "保存奇术"}</button></div></div></div>;
}

export default function AdminAbilities() {
  const [items, setItems] = useState<Ability[]>([]); const [editing, setEditing] = useState<Ability | null | undefined>(undefined); const [err, setErr] = useState(""); const [msg, setMsg] = useState(""); const [busy, setBusy] = useState(false); const [backfilling, setBackfilling] = useState(false);
  const load = () => api<Ability[]>("/admin/abilities").then(setItems).catch((e: Error) => setErr(e.message));
  useEffect(() => { load(); }, []);
  async function save(form: Form) { setBusy(true); try { await api(editing ? `/admin/abilities/${editing.id}` : "/admin/abilities", { method: editing ? "PUT" : "POST", body: JSON.stringify(form) }); setEditing(undefined); await load(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } }
  async function remove(item: Ability) { if (!window.confirm(`确认删除「${item.name}」？它会从所有异闻师与奇人中移除。`)) return; try { await api(`/admin/abilities/${item.id}`, { method: "DELETE" }); await load(); } catch (e: any) { setErr(e.message); } }
  async function backfill() { setBackfilling(true); setMsg(""); setErr(""); try { const r = await api<{ scheduled: number }>("/admin/abilities/backfill", { method: "POST" }); await load(); setMsg(r.scheduled > 0 ? `已为 ${r.scheduled} 个奇术调度三相解析生成` : "所有奇术均已具备三相解析"); } catch (e: any) { setErr(e.message); } finally { setBackfilling(false); } }
  return <div className="admin-page"><div className="admin-toolbar"><div><span className="eyebrow">ABILITY ARCHIVE</span><h2>奇术档案</h2></div><div style={{ display: "flex", gap: 8 }}><button className="btn btn-ghost" disabled={backfilling} onClick={backfill}>{backfilling ? "生成中…" : "补全三相解析"}</button><button className="btn btn-primary" onClick={() => setEditing(null)}><PlusIcon size={15} />新增奇术</button></div></div>{err && <p className="err">{err}</p>}{msg && <p className="muted">{msg}</p>}<div className="ability-list">{items.map((item) => <div className="ability-item" key={item.id}><div className="ability-item__body"><div className="ability-item__name">{item.name}</div><p className="ability-item__effect">{item.effect}</p>{item.detail && <p className="muted">{item.detail}</p>}<AbilitySlotView json={item.understanding} /></div><div className="ability-item__actions"><button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditing(item)} title="编辑"><PencilIcon size={14} /></button><button className="btn btn-danger btn-icon btn-sm" onClick={() => remove(item)} title="删除"><TrashIcon size={14} /></button></div></div>)}</div>{items.length === 0 && <div className="empty"><p>暂无奇术档案。</p></div>}{editing !== undefined && <AbilityModal editing={editing} busy={busy} onClose={() => setEditing(undefined)} onSave={save} />}</div>;
}
