// 提示词方案管理页：管理员预设若干套提示词方案（各环节整段 system 指令覆盖，空 = 冻结默认），
// 供战报页对某场行迹用不同方案重跑对比。v1 生效环节：讨论/推演/转写/校验/修复；
// usage/猜词三列仅存储，v2 重放猜词时启用。

import { useEffect, useState } from "react";
import { api } from "../../api";
import { PencilIcon, PlusIcon, TrashIcon, XIcon } from "../../components/icons";
import type { PromptScheme, PromptStage } from "./types";

type Form = { name: string; description: string; enabled: boolean } & Record<PromptStage, string>;

const STAGES: { key: PromptStage; label: string; hint: string; live: boolean }[] = [
  { key: "discuss_prompt", label: "奇术比对", hint: "数据槽：{ability_a} {ability_b}", live: true },
  { key: "deduce_prompt", label: "推演（上帝视角）", hint: "数据槽：{info} {discuss_report} {opening} {ending_a/b/draw}", live: true },
  { key: "transcribe_prompt", label: "转写（双视角）", hint: "数据槽：{info} {god} {viewer_name}", live: true },
  { key: "validate_prompt", label: "转写校验", hint: "数据槽：{info} {god} {viewer_name} {narration}", live: true },
  { key: "repair_prompt", label: "转写修复", hint: "数据槽：{info} {god} {viewer_name} {narration} {violations}", live: true },
  { key: "usage_prompt", label: "奇术使用判定", hint: "v2 生效（当前仅存储）", live: false },
  { key: "guess_pair_prompt", label: "猜词·配对", hint: "v2 生效（当前仅存储）", live: false },
  { key: "guess_verify_prompt", label: "猜词·检定", hint: "v2 生效（当前仅存储）", live: false },
];

const blank = (): Form => ({
  name: "",
  description: "",
  enabled: true,
  discuss_prompt: "",
  deduce_prompt: "",
  transcribe_prompt: "",
  validate_prompt: "",
  repair_prompt: "",
  usage_prompt: "",
  guess_pair_prompt: "",
  guess_verify_prompt: "",
});

const toForm = (s: PromptScheme): Form => ({
  name: s.name,
  description: s.description,
  enabled: s.enabled,
  discuss_prompt: s.discuss_prompt ?? "",
  deduce_prompt: s.deduce_prompt ?? "",
  transcribe_prompt: s.transcribe_prompt ?? "",
  validate_prompt: s.validate_prompt ?? "",
  repair_prompt: s.repair_prompt ?? "",
  usage_prompt: s.usage_prompt ?? "",
  guess_pair_prompt: s.guess_pair_prompt ?? "",
  guess_verify_prompt: s.guess_verify_prompt ?? "",
});

// 空文本框 → null（= 冻结默认），避免 "" 与 None 双态
const toBody = (form: Form): Record<string, unknown> => {
  const body: Record<string, unknown> = { name: form.name.trim(), description: form.description, enabled: form.enabled };
  for (const { key } of STAGES) body[key] = form[key].trim() || null;
  return body;
};

function SchemeModal({ editing, onClose, onSave, busy }: { editing: PromptScheme | null; onClose: () => void; onSave: (form: Form) => void; busy: boolean }) {
  const [form, setForm] = useState<Form>(editing ? toForm(editing) : blank());
  const update = (p: Partial<Form>) => setForm((v) => ({ ...v, ...p }));
  const overridden = STAGES.filter(({ key }) => form[key].trim()).length;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal--wide" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>{editing ? `修订方案「${editing.name}」` : "新建提示词方案"}</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭"><XIcon size={16} /></button>
        </div>
        <div className="field"><label>方案名 <span className="hint">必填</span></label><input className="input" value={form.name} onChange={(e) => update({ name: e.target.value })} autoFocus /></div>
        <div className="field"><label>描述 <span className="hint">可选</span></label><input className="input" value={form.description} onChange={(e) => update({ description: e.target.value })} /></div>
        <label className="toggle"><input type="checkbox" checked={form.enabled} onChange={(e) => update({ enabled: e.target.checked })} /><span className="toggle__track" /><span className="toggle__label">启用（停用方案不可用于重跑）</span></label>
        <p className="muted" style={{ marginBottom: 10 }}>
          各环节整段 system 指令：留空 = 用冻结默认（生产提示词不变）。已覆盖 {overridden}/8 环节。
        </p>
        <div className="admin-form-grid">
          {STAGES.map(({ key, label, hint, live }) => (
            <div className="field" key={key}>
              <label>{label} {live ? "" : <span className="hint">（v2 生效）</span>}</label>
              <textarea className="textarea" rows={4} value={form[key]} onChange={(e) => update({ [key]: e.target.value } as Partial<Form>)} placeholder={hint} />
            </div>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>作罢</button>
          <button className="btn btn-primary" disabled={busy || !form.name.trim()} onClick={() => onSave(form)}>
            <PlusIcon size={15} />{busy ? "写入中…" : "保存方案"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PromptSchemes() {
  const [items, setItems] = useState<PromptScheme[]>([]);
  const [editing, setEditing] = useState<PromptScheme | null | undefined>(undefined);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api<PromptScheme[]>("/admin/prompt-schemes").then(setItems).catch((e: Error) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function save(form: Form) {
    setBusy(true);
    try {
      await api(editing ? `/admin/prompt-schemes/${editing.id}` : "/admin/prompt-schemes", {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify(toBody(form)),
      });
      setEditing(undefined);
      await load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  async function remove(item: PromptScheme) {
    if (!window.confirm(`确认删除方案「${item.name}」？其调试记录一并删除。`)) return;
    try { await api(`/admin/prompt-schemes/${item.id}`, { method: "DELETE" }); await load(); } catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">PROMPT SCHEMES</span>
          <h2>提示词方案</h2>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing(null)}><PlusIcon size={15} />新建方案</button>
      </div>
      <p className="muted">
        预设若干套提示词方案，在战报页对某场行迹用不同方案重跑、对比三视角差异。v1 生效：讨论 / 推演 / 转写 / 校验 / 修复；猜词与使用判定三列仅存储。
      </p>
      {err && <p className="err">{err}</p>}
      <div className="tbl-list">
        {items.length === 0 && <p className="muted">暂无方案，点「新建方案」创建。</p>}
        {items.map((item) => {
          const overridden = STAGES.filter(({ key }) => item[key]).map(({ label }) => label);
          return (
            <div className="tbl-row tbl-row--wrap" key={item.id}>
              <span className="tbl-col tbl-col--main">
                <b>{item.name}</b>
                <small>
                  {item.enabled ? "" : "（停用） · "}
                  覆盖 {overridden.length ? `${overridden.join("、")}` : "无（全部冻结默认）"}
                  {item.description ? ` · ${item.description}` : ""}
                </small>
              </span>
              <span className="tbl-col tbl-actions">
                <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditing(item)} title="编辑"><PencilIcon size={14} /></button>
                <button className="btn btn-danger btn-icon btn-sm" onClick={() => remove(item)} title="删除"><TrashIcon size={14} /></button>
              </span>
            </div>
          );
        })}
      </div>
      {editing !== undefined && <SchemeModal editing={editing} busy={busy} onClose={() => setEditing(undefined)} onSave={save} />}
    </div>
  );
}
