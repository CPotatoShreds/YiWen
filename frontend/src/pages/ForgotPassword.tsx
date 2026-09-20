import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { SealStamp } from "../components/Ornaments";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
      setSent(true);
    } catch (e2: any) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth__card rise">
        <div className="auth__brand">
          <span className="brand__mark">
            <SealStamp char="异" size={40} />
          </span>
          <h1>找回口令</h1>
        </div>
        {sent ? (
          <p className="auth__sub">若该邮箱已绑定账号，重置链接已寄出（15 分钟内有效），请查收邮件。</p>
        ) : (
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="fp-email">绑定邮箱</label>
              <input
                id="fp-email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>
            {err && <p className="err">{err}</p>}
            <button className="btn btn-primary btn-block" disabled={busy || !email}>
              {busy ? "寄送中…" : "寄出重置链接"}
            </button>
          </form>
        )}
        <p className="auth__foot">
          <Link to="/login">返回登录</Link>
        </p>
      </div>
    </div>
  );
}
