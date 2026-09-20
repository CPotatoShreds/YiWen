import { useEffect, useState } from "react";
import { api } from "../api";

/** 绑定/换绑邮箱：提交后向新邮箱寄验证链接，验证通过才落库（见 /auth/me/email）。 */
export default function EmailBinding() {
  const [email, setEmail] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ email: string | null }>("/auth/me")
      .then((me) => setEmail(me.email))
      .catch(() => {});
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("/auth/me/email", { method: "POST", body: JSON.stringify({ email: draft }) });
      setSent(true);
    } catch (e2: any) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2 className="panel-title">绑定邮箱</h2>
      <p className="muted">
        {email ? `当前绑定：${email}（换绑同样需要新邮箱验证）` : "尚未绑定。绑定后可用邮箱找回口令。"}
      </p>
      {sent ? (
        <p className="muted">验证链接已寄出（15 分钟内有效），请到邮箱点击完成绑定。</p>
      ) : (
        <form onSubmit={submit} className="inline-form">
          <input
            className="input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
          <button className="btn btn-primary" disabled={busy || !draft || draft === email}>
            {busy ? "寄送中…" : email ? "换绑邮箱" : "绑定邮箱"}
          </button>
        </form>
      )}
      {err && <p className="err">{err}</p>}
    </div>
  );
}
