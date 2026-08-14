// 模型配置：用户自配 LLM 方案（OpenAI 兼容）的列表 + 新建/编辑/激活/删除/测试。
// api_key 用服务端下发的 RSA 公钥加密后再发送（jsencrypt），落库与传输皆密文。
import { useCallback, useEffect, useState } from "react";
import { JSEncrypt } from "jsencrypt";
import { api } from "../api";
import { CheckIcon, PencilIcon, PlusIcon, TestTubeIcon, TrashIcon, XIcon } from "./icons";
import type { LlmProfile } from "../types";

// 预设提供方（全 OpenAI 兼容）：选提供方自动填 base_url，可再改
const PROVIDER_PRESETS: { value: string; label: string; base_url: string }[] = [
  { value: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1" },
  { value: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com" },
  { value: "moonshot", label: "Moonshot（Kimi）", base_url: "https://api.moonshot.cn/v1" },
  { value: "dashscope", label: "通义千问（DashScope）", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { value: "glm", label: "智谱 GLM", base_url: "https://open.bigmodel.cn/api/paas/v4" },
  { value: "minimax", label: "MiniMax", base_url: "https://api.minimax.io/v1" },
  { value: "custom", label: "自定义（OpenAI 兼容）", base_url: "" },
];

function providerLabel(value: string): string {
  return PROVIDER_PRESETS.find((p) => p.value === value)?.label ?? value;
}

interface FormState {
  label: string;
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
}

const EMPTY_FORM: FormState = { label: "", provider: "deepseek", base_url: "https://api.deepseek.com", api_key: "", model: "" };

function rsaEncrypt(publicKeyPem: string, text: string): string {
  const enc = new JSEncrypt();
  enc.setPublicKey(publicKeyPem);
  const cipher = enc.encrypt(text);
  if (!cipher) throw new Error("api_key 加密失败，请重试");
  return cipher;
}

export default function ModelProfiles() {
  const [profiles, setProfiles] = useState<LlmProfile[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<LlmProfile | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState<number | null>(null);
  const [testMsg, setTestMsg] = useState<{ id: number; ok: boolean; detail: string } | null>(null);
  const [pubKey, setPubKey] = useState("");

  const load = useCallback(async () => {
    try {
      setProfiles(await api<LlmProfile[]>("/llm-profiles"));
    } catch (e: any) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    api<{ public_key: string }>("/llm-profiles/public-key")
      .then((r) => setPubKey(r.public_key))
      .catch(() => setPubKey("")); // 拿不到公钥时保存会提示，避免静默失败
  }, [load]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setMsg("");
    setErr("");
    setFormOpen(true);
  }

  function openEdit(p: LlmProfile) {
    setEditing(p);
    setForm({ label: p.label, provider: p.provider, base_url: p.base_url, api_key: "", model: p.model });
    setMsg("");
    setErr("");
    setFormOpen(true);
  }

  async function save() {
    setBusy(true);
    setErr("");
    setMsg("");
    const body: Record<string, string> = {
      label: form.label.trim(),
      provider: form.provider,
      base_url: form.base_url.trim(),
      model: form.model.trim(),
    };
    if (form.api_key.trim()) {
      if (!pubKey) {
        setBusy(false);
        setErr("加密公钥未就绪，请刷新页面重试");
        return;
      }
      body.api_key = rsaEncrypt(pubKey, form.api_key.trim());
    }
    try {
      if (editing) {
        await api(`/llm-profiles/${editing.id}`, { method: "PUT", body: JSON.stringify(body) });
      } else {
        await api("/llm-profiles", { method: "POST", body: JSON.stringify(body) });
      }
      setFormOpen(false);
      setMsg(editing ? "方案已更新" : "方案已创建并激活");
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function activate(p: LlmProfile) {
    setErr("");
    setMsg("");
    try {
      await api(`/llm-profiles/${p.id}/activate`, { method: "POST" });
      setMsg(`已切换到「${p.label}」`);
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function remove(p: LlmProfile) {
    if (!window.confirm(`确认删除方案「${p.label}」？`)) return;
    setErr("");
    setMsg("");
    try {
      await api(`/llm-profiles/${p.id}`, { method: "DELETE" });
      setMsg("方案已删除");
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function test(p: LlmProfile) {
    setTesting(p.id);
    setTestMsg(null);
    try {
      const r = await api<{ ok: boolean; detail: string }>(`/llm-profiles/${p.id}/test`, { method: "POST" });
      setTestMsg({ id: p.id, ok: r.ok, detail: r.detail });
    } catch (e: any) {
      setTestMsg({ id: p.id, ok: false, detail: e.message });
    } finally {
      setTesting(null);
    }
  }

  function onProviderChange(value: string) {
    setForm((f) => {
      const preset = PROVIDER_PRESETS.find((p) => p.value === value);
      return { ...f, provider: value, base_url: preset?.base_url ?? f.base_url };
    });
  }

  const valid = form.label.trim() && form.base_url.trim() && form.model.trim() && (editing || form.api_key.trim());

  return (
    <div className="panel rise">
      <div className="panel__head">
        <h3>模型配置</h3>
        <button className="btn btn-sm btn-primary" onClick={openCreate}>
          <PlusIcon size={14} />
          新建配置
        </button>
      </div>
      <p className="muted" style={{ marginBottom: 12, lineHeight: 1.7 }}>
        配置你自己的 LLM 模型（OpenAI 兼容：API 密钥 + 端点 + 模型）。激活的方案用于你的对局推演与猜词；
        未配置任何方案时使用服务器默认模型。API 密钥加密传输、加密存储，绝不回传明文。
      </p>
      {profiles.length === 0 ? (
        <p className="muted">还没有配置方案。</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {profiles.map((p) => (
            <div
              key={p.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 12px",
                borderRadius: 12,
                border: p.is_active ? "1px solid color-mix(in srgb, var(--accent) 50%, transparent)" : "1px solid var(--line)",
                background: p.is_active ? "color-mix(in srgb, var(--accent) 6%, transparent)" : "var(--surface)",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <strong>{p.label}</strong>
                  {p.is_active && (
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: "var(--accent)",
                        border: "1px solid color-mix(in srgb, var(--accent) 45%, transparent)",
                        borderRadius: 999,
                        padding: "0 8px",
                        lineHeight: 1.5,
                      }}
                    >
                      使用中
                    </span>
                  )}
                </div>
                <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                  {providerLabel(p.provider)} · {p.model}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                {!p.is_active && (
                  <button className="btn btn-sm btn-ghost" onClick={() => activate(p)}>
                    <CheckIcon size={13} />
                    激活
                  </button>
                )}
                <button className="btn btn-sm btn-ghost" onClick={() => test(p)} disabled={testing === p.id}>
                  <TestTubeIcon size={13} />
                  {testing === p.id ? "测试中" : "测试"}
                </button>
                <button className="btn btn-sm btn-ghost" onClick={() => openEdit(p)} aria-label={`编辑 ${p.label}`}>
                  <PencilIcon size={13} />
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => remove(p)} aria-label={`删除 ${p.label}`}>
                  <TrashIcon size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {testMsg && (
        <p className={testMsg.ok ? "summary" : "err"} style={{ marginTop: 10 }}>
          {testMsg.detail}
        </p>
      )}
      {msg && <p className="summary" style={{ marginTop: 10 }}>{msg}</p>}
      {err && <p className="err" style={{ marginTop: 10 }}>{err}</p>}

      {formOpen && (
        <div className="modal-overlay" onClick={() => !busy && setFormOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="modal__head">
              <h3>{editing ? `编辑方案「${editing.label}」` : "新建配置方案"}</h3>
              <button className="modal__close" onClick={() => setFormOpen(false)} aria-label="关闭" disabled={busy}>
                <XIcon size={16} />
              </button>
            </div>
            <div className="field">
              <label>方案名称</label>
              <input
                className="input"
                value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })}
                placeholder="如：我的 DeepSeek"
                autoFocus
              />
            </div>
            <div className="field">
              <label>提供方</label>
              <select className="input" value={form.provider} onChange={(e) => onProviderChange(e.target.value)}>
                {PROVIDER_PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>API 密钥</label>
              <input
                className="input"
                type="password"
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                placeholder={editing ? "已配置，留空保持不变" : "sk-..."}
              />
            </div>
            <div className="field">
              <label>默认模型</label>
              <input
                className="input"
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                placeholder="如 deepseek-chat、gpt-4o-mini"
              />
            </div>
            <div className="field">
              <label>Base URL <span className="hint">OpenAI 兼容端点，选择提供方后自动填入</span></label>
              <input
                className="input"
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                placeholder="https://..."
              />
            </div>
            {err && <p className="err" style={{ marginTop: 2 }}>{err}</p>}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setFormOpen(false)} disabled={busy}>
                作罢
              </button>
              <button className="btn btn-primary" onClick={save} disabled={busy || !valid}>
                <CheckIcon size={15} />
                {busy ? "保存中…" : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
